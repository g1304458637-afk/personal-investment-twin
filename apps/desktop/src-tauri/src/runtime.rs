use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
#[cfg(debug_assertions)]
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tokio::sync::oneshot;

const PROTOCOL_VERSION: &str = "1";
#[cfg(not(debug_assertions))]
const SIDECAR_NAME: &str = "toujing-core";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct RuntimeError {
    pub code: String,
    pub message: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct RuntimeResponse {
    pub request_id: Option<String>,
    pub ok: bool,
    pub result: Option<Value>,
    pub error: Option<RuntimeError>,
}

impl RuntimeResponse {
    fn error(request_id: Option<String>, code: &str, message: impl Into<String>) -> Self {
        Self {
            request_id,
            ok: false,
            result: None,
            error: Some(RuntimeError {
                code: code.to_owned(),
                message: message.into(),
            }),
        }
    }
}

type Pending = Arc<Mutex<HashMap<String, oneshot::Sender<RuntimeResponse>>>>;

pub struct RuntimeManager {
    child: Arc<Mutex<Option<CommandChild>>>,
    pending: Pending,
    alive: Arc<AtomicBool>,
    next_request: AtomicU64,
}

#[cfg(debug_assertions)]
fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn fail_pending(pending: &Pending, code: &str, message: &str) {
    let drained = {
        let mut values = pending.lock().expect("runtime pending lock poisoned");
        values.drain().collect::<Vec<_>>()
    };
    for (request_id, sender) in drained {
        let _ = sender.send(RuntimeResponse::error(
            Some(request_id),
            code,
            message.to_owned(),
        ));
    }
}

fn route_stdout(pending: &Pending, bytes: &[u8]) {
    let response: RuntimeResponse = match serde_json::from_slice(bytes) {
        Ok(value) => value,
        Err(_) => {
            fail_pending(
                pending,
                "runtime_protocol_error",
                "the core runtime returned malformed JSON",
            );
            return;
        }
    };
    let Some(request_id) = response.request_id.clone() else {
        fail_pending(
            pending,
            "runtime_protocol_error",
            "the core runtime response omitted request_id",
        );
        return;
    };
    let sender = pending
        .lock()
        .expect("runtime pending lock poisoned")
        .remove(&request_id);
    if let Some(sender) = sender {
        let _ = sender.send(response);
    }
}

impl RuntimeManager {
    pub async fn start(app: &AppHandle) -> Result<Self, String> {
        #[cfg(debug_assertions)]
        let command = {
            let root = project_root();
            let python = root.join(".venv/bin/python");
            if !python.is_file() {
                return Err(format!("development Python runtime missing at {}", python.display()));
            }
            app.shell()
                .command(python)
                .args(["-m", "toujing_core_runtime"])
                .current_dir(root)
        };

        #[cfg(not(debug_assertions))]
        let command = app
            .shell()
            .sidecar(SIDECAR_NAME)
            .map_err(|error| format!("bundled runtime unavailable: {error}"))?;

        let (mut events, child) = command
            .spawn()
            .map_err(|error| format!("failed to start core runtime: {error}"))?;
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = Arc::new(AtomicBool::new(true));
        let reader_pending = Arc::clone(&pending);
        let reader_alive = Arc::clone(&alive);
        tauri::async_runtime::spawn(async move {
            while let Some(event) = events.recv().await {
                match event {
                    CommandEvent::Stdout(bytes) => route_stdout(&reader_pending, &bytes),
                    CommandEvent::Stderr(bytes) => {
                        eprintln!("toujing-core: {}", String::from_utf8_lossy(&bytes));
                    }
                    CommandEvent::Error(message) => {
                        reader_alive.store(false, Ordering::SeqCst);
                        fail_pending(&reader_pending, "runtime_process_error", &message);
                    }
                    CommandEvent::Terminated(_) => {
                        reader_alive.store(false, Ordering::SeqCst);
                        fail_pending(
                            &reader_pending,
                            "runtime_process_exited",
                            "the core runtime exited",
                        );
                    }
                    _ => {}
                }
            }
        });
        let manager = Self {
            child: Arc::new(Mutex::new(Some(child))),
            pending,
            alive,
            next_request: AtomicU64::new(1),
        };
        let handshake = manager.request("runtime.handshake", json!({})).await?;
        if !handshake.ok
            || handshake
                .result
                .as_ref()
                .and_then(|result| result.get("protocol_version"))
                .and_then(Value::as_str)
                != Some(PROTOCOL_VERSION)
        {
            manager.kill();
            return Err("core runtime handshake is incompatible".to_owned());
        }
        Ok(manager)
    }

    pub async fn request(&self, method: &str, params: Value) -> Result<RuntimeResponse, String> {
        if !self.alive.load(Ordering::SeqCst) {
            return Err("core runtime is unavailable".to_owned());
        }
        let request_id = format!(
            "runtime-{}",
            self.next_request.fetch_add(1, Ordering::Relaxed)
        );
        let payload = json!({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "params": params,
        });
        let mut bytes = serde_json::to_vec(&payload)
            .map_err(|error| format!("runtime request serialization failed: {error}"))?;
        bytes.push(b'\n');
        let (sender, receiver) = oneshot::channel();
        self.pending
            .lock()
            .map_err(|_| "runtime pending lock poisoned".to_owned())?
            .insert(request_id.clone(), sender);
        let write_result = self
            .child
            .lock()
            .map_err(|_| "runtime child lock poisoned".to_owned())?
            .as_mut()
            .ok_or_else(|| "core runtime is unavailable".to_owned())?
            .write(&bytes);
        if let Err(error) = write_result {
            self.pending.lock().ok().and_then(|mut values| values.remove(&request_id));
            return Err(format!("failed to write runtime request: {error}"));
        }
        match tokio::time::timeout(REQUEST_TIMEOUT, receiver).await {
            Ok(Ok(response)) => Ok(response),
            Ok(Err(_)) => Err("core runtime response channel closed".to_owned()),
            Err(_) => {
                self.pending.lock().ok().and_then(|mut values| values.remove(&request_id));
                Err("core runtime request timed out".to_owned())
            }
        }
    }

    pub async fn shutdown(&self) {
        if self.alive.load(Ordering::SeqCst) {
            let _ = self.request("runtime.shutdown", json!({})).await;
        }
        self.kill();
    }

    fn kill(&self) {
        self.alive.store(false, Ordering::SeqCst);
        if let Ok(mut child) = self.child.lock() {
            if let Some(child) = child.take() {
                let _ = child.kill();
            }
        }
        fail_pending(&self.pending, "runtime_shutdown", "the core runtime was stopped");
    }
}

impl Drop for RuntimeManager {
    fn drop(&mut self) {
        self.kill();
    }
}

#[tauri::command]
pub async fn runtime_health(manager: tauri::State<'_, RuntimeManager>) -> Result<RuntimeResponse, String> {
    manager.request("runtime.health", json!({})).await
}

#[tauri::command]
pub async fn runtime_core_smoke(
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeResponse, String> {
    manager.request("runtime.core_smoke", json!({})).await
}

pub fn install(builder: tauri::Builder<tauri::Wry>) -> tauri::Builder<tauri::Wry> {
    builder
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let manager = tauri::async_runtime::block_on(RuntimeManager::start(app.handle()))
                .map_err(std::io::Error::other)?;
            app.manage(manager);
            Ok(())
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn malformed_response_fails_all_pending_requests() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let (sender, receiver) = oneshot::channel();
        pending.lock().unwrap().insert("request-1".to_owned(), sender);
        route_stdout(&pending, b"not-json");
        let response = receiver.blocking_recv().unwrap();
        assert_eq!(response.error.unwrap().code, "runtime_protocol_error");
        assert!(pending.lock().unwrap().is_empty());
    }

    #[test]
    fn response_is_routed_by_request_id() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let (sender, receiver) = oneshot::channel();
        pending.lock().unwrap().insert("request-1".to_owned(), sender);
        route_stdout(
            &pending,
            br#"{"request_id":"request-1","ok":true,"result":{"status":"ok"},"error":null}"#,
        );
        let response = receiver.blocking_recv().unwrap();
        assert!(response.ok);
        assert_eq!(response.request_id.as_deref(), Some("request-1"));
    }

    #[test]
    fn process_failure_cleans_every_pending_request() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let mut receivers = Vec::new();
        for request_id in ["one", "two"] {
            let (sender, receiver) = oneshot::channel();
            pending.lock().unwrap().insert(request_id.to_owned(), sender);
            receivers.push(receiver);
        }
        fail_pending(&pending, "runtime_process_exited", "exited");
        assert!(pending.lock().unwrap().is_empty());
        for receiver in receivers {
            assert_eq!(
                receiver.blocking_recv().unwrap().error.unwrap().code,
                "runtime_process_exited"
            );
        }
    }
}
