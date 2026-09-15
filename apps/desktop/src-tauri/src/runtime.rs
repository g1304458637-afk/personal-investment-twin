use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
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
// Packaged cold account-context construction includes analytics imports and
// replay compilation (cold QA exceeded 180s under concurrent desktop load). Only initial context
// gets this deadline; start reuses fingerprint-bound facts, never a cached answer.
const REVIEW_CONTEXT_TIMEOUT: Duration = Duration::from_secs(300);
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
const HEALTH_PROBE_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_LINE_BYTES: usize = 64 * 1024 * 1024;
// RunEvent::Exit must never hang waiting for the sidecar; after this deadline
// the shutdown proceeds straight to kill().
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);
// Record of the running sidecar inside app_data so a restart can report a
// leftover process instead of silently orphaning it.
const SIDECAR_PIDFILE: &str = "toujing-core.pid";
fn request_timeout(method: &str) -> Duration {
    if method == "review.context" {
        REVIEW_CONTEXT_TIMEOUT
    } else {
        REQUEST_TIMEOUT
    }
}
const PRODUCT_METHODS: &[&str] = &[
    "ingestion.preview_trade_csv",
    "ingestion.commit_trade_import",
    "market.preview_price_csv",
    "market.commit_price_import",
    "account.list",
    "account.get_data_status",
    "investments.list",
    "episode.get",
    "strategy_comparison.get",
    "strategy_simulation.run_custom",
    "strategy_sensitivity.run",
    "data.delete_account",
    "review.context",
    "review.start",
    "strategy_teaching.explain",
    "review.poll",
    "review.add_note",
    "review_pack.get",
    "episode_tags.set",
    "compare.export_share",
    "compare.import_share",
    "compare.list_shares",
    "compare.revoke_share",
];
// Methods whose params get the saved internal credentials attached. Every
// entry here MUST also be in PRODUCT_METHODS (enforced by a test) or the
// branch would be unreachable dead code.
const KEYED_PRODUCT_METHODS: &[&str] = &["review.start", "strategy_teaching.explain"];

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
type ChildSlot = Arc<Mutex<Option<CommandChild>>>;

pub struct RuntimeManager {
    child: ChildSlot,
    pending: Pending,
    alive: Arc<AtomicBool>,
    next_request: AtomicU64,
    pid: AtomicU32,
    pub(crate) app_data: PathBuf,
}

#[cfg(debug_assertions)]
fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn fail_pending(pending: &Pending, code: &str, message: &str) {
    // A poisoned lock must not take the reader thread down with it: recover
    // the map contents and fail every in-flight request.
    let drained = match pending.lock() {
        Ok(mut values) => values.drain().collect::<Vec<_>>(),
        Err(poisoned) => poisoned.into_inner().drain().collect::<Vec<_>>(),
    };
    for (request_id, sender) in drained {
        let _ = sender.send(RuntimeResponse::error(
            Some(request_id),
            code,
            message.to_owned(),
        ));
    }
}

/// Feeds one stdout chunk into the line buffer and routes every complete line.
/// The sidecar speaks newline-delimited JSON, and one read may contain a
/// partial line or several lines at once.
/// Truncates and redacts sidecar diagnostics before they reach system logs:
/// a Python traceback that quotes a params blob containing `_desktop_model_key`
/// must never carry the secret into Console.app.
fn redact_secrets(text: &str) -> String {
    const MAX_LOG_BYTES: usize = 2048;
    let truncated = if text.len() > MAX_LOG_BYTES {
        let mut cut = MAX_LOG_BYTES;
        while !text.is_char_boundary(cut) {
            cut -= 1;
        }
        format!("{}…[truncated]", &text[..cut])
    } else {
        text.to_owned()
    };
    if truncated.contains("_desktop_model_key") {
        return truncated.replace("_desktop_model_key", "_desktop_[redacted]_key");
    }
    truncated
}

fn route_stdout_chunk(pending: &Pending, alive: &AtomicBool, buffer: &mut Vec<u8>, chunk: &[u8]) {
    buffer.extend_from_slice(chunk);
    // A buggy sidecar emitting one endless line must hit a heap cap, not grow
    // unboundedly.  64 MiB is orders of magnitude above any real payload.
    if buffer.len() > MAX_LINE_BYTES {
        fail_pending(pending, "runtime_protocol_error", "sidecar stdout line exceeded 64 MiB");
        buffer.clear();
        return;
    }
    while let Some(newline) = buffer.iter().position(|&byte| byte == b'\n') {
        let line: Vec<u8> = buffer.drain(..=newline).collect();
        route_stdout_line(pending, alive, &line[..line.len() - 1]);
    }
}

fn route_stdout_line(pending: &Pending, alive: &AtomicBool, line: &[u8]) {
    let value: Value = match serde_json::from_slice(line) {
        Ok(value) => value,
        Err(_) => {
            // Stray diagnostics on stdout are not protocol failures; failing
            // every in-flight request for them made one noisy line fatal.
            eprintln!(
                "toujing-core: ignoring non-protocol stdout line: {:?}",
                String::from_utf8_lossy(line)
            );
            return;
        }
    };
    let Some(request_id) = value.get("request_id").and_then(Value::as_str) else {
        eprintln!(
            "toujing-core: ignoring stdout line without request_id: {:?}",
            String::from_utf8_lossy(line)
        );
        return;
    };
    let request_id = request_id.to_owned();
    let response: RuntimeResponse = match serde_json::from_value(value) {
        Ok(response) => response,
        Err(_) => {
            // The id matches a live request but the payload is unusable: fail
            // exactly that request and leave every other one alone.
            eprintln!("toujing-core: discarding malformed payload for request {request_id}");
            if let Some(sender) = take_sender(pending, alive, &request_id) {
                let _ = sender.send(RuntimeResponse::error(
                    Some(request_id),
                    "runtime_protocol_error",
                    "the core runtime returned a malformed payload",
                ));
            }
            return;
        }
    };
    match take_sender(pending, alive, &request_id) {
        Some(sender) => {
            let _ = sender.send(response);
        }
        None => eprintln!("toujing-core: ignoring response for unknown request_id {request_id}"),
    }
}

fn take_sender(
    pending: &Pending,
    alive: &AtomicBool,
    request_id: &str,
) -> Option<oneshot::Sender<RuntimeResponse>> {
    match pending.lock() {
        Ok(mut values) => values.remove(request_id),
        Err(poisoned) => {
            eprintln!("toujing-core: pending registry poisoned; failing every in-flight request");
            // Treat poisoning like a runtime failure: release the recovered
            // lock, stop accepting requests and fail every sender.
            drop(poisoned);
            alive.store(false, Ordering::SeqCst);
            fail_pending(
                pending,
                "runtime_protocol_error",
                "the core runtime pending registry failed",
            );
            None
        }
    }
}

/// Removes one settled entry without ever panicking on a poisoned lock.
fn remove_pending(pending: &Pending, request_id: &str) {
    match pending.lock() {
        Ok(mut values) => {
            values.remove(request_id);
        }
        Err(poisoned) => {
            poisoned.into_inner().remove(request_id);
        }
    }
}

fn write_request(child: &ChildSlot, bytes: &[u8]) -> Result<(), String> {
    child
        .lock()
        .map_err(|_| "runtime child lock poisoned".to_owned())?
        .as_mut()
        .ok_or_else(|| "core runtime is unavailable".to_owned())?
        .write(bytes)
        .map_err(|error| format!("failed to write runtime request: {error}"))
}

/// Terminates the sidecar without ever blocking on the child mutex: if a
/// writer is wedged in a blocking stdin write while holding the lock, a
/// SIGKILL on the recorded pid closes the pipe and lets the writer unwind.
fn force_kill_child(child: &ChildSlot, pid: u32) {
    match child.try_lock() {
        Ok(mut guard) => {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
        Err(std::sync::TryLockError::Poisoned(poisoned)) => {
            let mut guard = poisoned.into_inner();
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
        Err(std::sync::TryLockError::WouldBlock) => {
            #[cfg(unix)]
            if pid != 0 {
                // The lock holder is blocked inside write_all; only the
                // kernel can release it.
                unsafe { libc::kill(pid as libc::pid_t, libc::SIGKILL) };
            }
            #[cfg(not(unix))]
            if let Ok(mut guard) = child.lock() {
                if let Some(child) = guard.take() {
                    let _ = child.kill();
                }
            }
        }
    }
}

#[cfg(unix)]
fn process_is_alive(pid: u32) -> bool {
    // Signal 0 only probes existence; EPERM also proves the process is there.
    let probe = unsafe { libc::kill(pid as libc::pid_t, 0) };
    probe == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

#[cfg(not(unix))]
fn process_is_alive(_pid: u32) -> bool {
    false
}

/// Reports (never kills) a sidecar left over from a previous run. With the
/// single-instance plugin the leftover can only be a true orphan, so a log
/// line is the pragmatic fix; pid reuse may produce a false warning at worst.
fn note_previous_sidecar(app_data: &Path) {
    let Ok(previous) = std::fs::read_to_string(app_data.join(SIDECAR_PIDFILE)) else {
        return;
    };
    match previous.trim().parse::<u32>() {
        Ok(pid) if process_is_alive(pid) => {
            eprintln!("toujing: previous core runtime (pid {pid}) is still running; leaving it alone");
        }
        Ok(_) => {}
        Err(_) => eprintln!("toujing: discarding malformed sidecar pidfile"),
    }
}

impl RuntimeManager {
    pub async fn start(app: &AppHandle) -> Result<Self, String> {
        let app_data = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("app data directory unavailable: {error}"))?;
        std::fs::create_dir_all(&app_data)
            .map_err(|error| format!("cannot create app data directory: {error}"))?;
        note_previous_sidecar(&app_data);
        let db_path = app_data.join("toujing-v1.sqlite3");
        let db_arg = db_path.to_string_lossy().into_owned();
        #[cfg(debug_assertions)]
        let command = {
            let root = project_root();
            let python = root.join(".venv/bin/python");
            if !python.is_file() {
                return Err(format!(
                    "development Python runtime missing at {}",
                    python.display()
                ));
            }
            app.shell()
                .command(python)
                .args(["-m", "toujing_core_runtime", "--db-path", db_arg.as_str()])
                .current_dir(root)
        };

        #[cfg(not(debug_assertions))]
        let command = app
            .shell()
            .sidecar(SIDECAR_NAME)
            .map_err(|error| format!("bundled runtime unavailable: {error}"))?
            .args(["--db-path", db_arg.as_str()]);

        let (mut events, child) = command
            // A packaged desktop must not inherit verbose model/tool payload logging.
            .env("OPENAI_AGENTS_DONT_LOG_MODEL_DATA", "1")
            .env("OPENAI_AGENTS_DONT_LOG_TOOL_DATA", "1")
            .env("OPENAI_LOG", "warning")
            .spawn()
            .map_err(|error| format!("failed to start core runtime: {error}"))?;
        let pid = child.pid();
        let _ = std::fs::write(app_data.join(SIDECAR_PIDFILE), pid.to_string());
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = Arc::new(AtomicBool::new(true));
        let reader_pending = Arc::clone(&pending);
        let reader_alive = Arc::clone(&alive);
        tauri::async_runtime::spawn(async move {
            let mut line_buffer: Vec<u8> = Vec::new();
            while let Some(event) = events.recv().await {
                match event {
                    CommandEvent::Stdout(bytes) => {
                        route_stdout_chunk(&reader_pending, &reader_alive, &mut line_buffer, &bytes)
                    }
                    CommandEvent::Stderr(bytes) => {
                        eprintln!("toujing-core: {}", redact_secrets(&String::from_utf8_lossy(&bytes)));
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
            pid: AtomicU32::new(pid),
            app_data,
        };
        let handshake = match manager
            .request_with_timeout("runtime.handshake", json!({}), STARTUP_TIMEOUT)
            .await
        {
            Ok(response) => response,
            Err(error) => {
                manager.kill();
                return Err(error);
            }
        };
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
        self.request_inner(method, params, request_timeout(method), true)
            .await
    }

    async fn request_with_timeout(
        &self,
        method: &str,
        params: Value,
        timeout: Duration,
    ) -> Result<RuntimeResponse, String> {
        self.request_inner(method, params, timeout, true).await
    }

    /// A request timeout no longer stops the shared runtime by itself: one
    /// slow replay (cold caches, big CSV preview) must fail alone instead of
    /// turning into a global outage for every other in-flight request.  The
    /// runtime is killed only when a follow-up health probe also fails —
    /// that distinguishes "slow" from "wedged" without losing the wedged-
    /// child protection.  `rescue=false` (the probe itself) skips the probe
    /// so a failing probe can never recurse.
    async fn request_inner(
        &self,
        method: &str,
        params: Value,
        timeout: Duration,
        rescue: bool,
    ) -> Result<RuntimeResponse, String> {
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
        // The deadline spans the write AND the wait: stdin writes are blocking
        // runs on the pool, so a sidecar that stops reading can never pin this
        // future past `timeout`.
        match tokio::time::timeout(timeout, self.deliver(bytes, receiver)).await {
            Ok(outcome) => {
                if outcome.is_err() {
                    remove_pending(&self.pending, &request_id);
                }
                outcome
            }
            Err(_) => {
                let error = format!("core runtime request timed out after {:?}", timeout);
                if rescue {
                    eprintln!("toujing: {error} for {method}; probing runtime health");
                    // Box::pin: the compiler cannot prove rescue=false ends
                    // the recursion, so the probe future needs indirection.
                    let probe = tokio::time::timeout(
                        HEALTH_PROBE_TIMEOUT,
                        Box::pin(
                            self.request_inner("runtime.health", json!({}), HEALTH_PROBE_TIMEOUT, false),
                        ),
                    )
                    .await;
                    let healthy = matches!(probe, Ok(Ok(response)) if response.ok);
                    if !healthy {
                        eprintln!("toujing: health probe failed; stopping the core runtime");
                        self.kill();
                    }
                } else {
                    eprintln!("toujing: {error} for {method}");
                }
                remove_pending(&self.pending, &request_id);
                Err(error)
            }
        }
    }

    /// Writes the framed request and awaits the routed response.
    async fn deliver(
        &self,
        bytes: Vec<u8>,
        receiver: oneshot::Receiver<RuntimeResponse>,
    ) -> Result<RuntimeResponse, String> {
        let (write_sender, write_receiver) = oneshot::channel::<Result<(), String>>();
        let child = Arc::clone(&self.child);
        tauri::async_runtime::spawn_blocking(move || {
            let _ = write_sender.send(write_request(&child, &bytes));
        });
        write_receiver
            .await
            .map_err(|_| "runtime write task stopped".to_owned())??;
        receiver
            .await
            .map_err(|_| "core runtime response channel closed".to_owned())
    }

    /// Bounded so RunEvent::Exit can never hang: the graceful request gets
    /// SHUTDOWN_TIMEOUT, then the sidecar is killed regardless.
    pub async fn shutdown(&self) {
        if self.alive.load(Ordering::SeqCst) {
            let _ = tokio::time::timeout(
                SHUTDOWN_TIMEOUT,
                self.request("runtime.shutdown", json!({})),
            )
            .await;
        }
        self.kill();
    }

    fn kill(&self) {
        self.alive.store(false, Ordering::SeqCst);
        force_kill_child(&self.child, self.pid.load(Ordering::SeqCst));
        let _ = std::fs::remove_file(self.app_data.join(SIDECAR_PIDFILE));
        fail_pending(
            &self.pending,
            "runtime_shutdown",
            "the core runtime was stopped",
        );
    }
}

impl Drop for RuntimeManager {
    fn drop(&mut self) {
        self.kill();
    }
}

#[tauri::command]
pub async fn runtime_health(
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeResponse, String> {
    manager.request("runtime.health", json!({})).await
}

#[tauri::command]
pub async fn runtime_core_smoke(
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeResponse, String> {
    manager.request("runtime.core_smoke", json!({})).await
}

#[tauri::command]
pub async fn runtime_product_request(
    method: String,
    params: Value,
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeResponse, String> {
    if !PRODUCT_METHODS.contains(&method.as_str()) {
        return Ok(RuntimeResponse::error(
            None,
            "method_not_allowed",
            "the desktop command only permits registered product methods",
        ));
    }
    let params = if KEYED_PRODUCT_METHODS.contains(&method.as_str()) {
        let params = crate::model_settings::with_saved_key(params).await?;
        if method == "review.start" {
            crate::model_settings::with_optional_search(params, &manager.app_data).await?
        } else {
            params
        }
    } else {
        // Internal credentials are never accepted on general product requests.
        if params.get("_desktop_model_key").is_some()
            || params.get("_desktop_bocha_key").is_some()
            || params.get("_desktop_search_enabled").is_some()
        {
            return Err("invalid_params".into());
        }
        params
    };
    manager.request(&method, params).await
}

pub fn install(builder: tauri::Builder<tauri::Wry>) -> tauri::Builder<tauri::Wry> {
    builder.plugin(tauri_plugin_shell::init()).setup(|app| {
        match tauri::async_runtime::block_on(RuntimeManager::start(app.handle())) {
            Ok(manager) => {
                app.manage(manager);
                Ok(())
            }
            Err(error) => {
                eprintln!("toujing: core runtime failed to start: {error}");
                show_startup_failure(app, &error);
                app.cleanup_before_exit();
                std::process::exit(1);
            }
        }
    })
}

fn startup_failure_message(error: &str) -> String {
    format!(
        "核心运行时启动失败，应用即将退出。\n\n{error}\n\n请重新启动应用；若持续失败，请重新安装或联系支持。"
    )
}

/// Setup failures must be visible: show a blocking dialog (the dialog plugin
/// is already initialized by the time setup hooks run) instead of panicking.
fn show_startup_failure(app: &tauri::App<tauri::Wry>, error: &str) {
    use tauri_plugin_dialog::DialogExt;
    app.dialog()
        .message(startup_failure_message(error))
        .title("投镜 · 启动失败")
        .blocking_show();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn alive_flag() -> Arc<AtomicBool> {
        Arc::new(AtomicBool::new(true))
    }

    fn manager_without_child() -> RuntimeManager {
        RuntimeManager {
            child: Arc::new(Mutex::new(None)),
            pending: Arc::new(Mutex::new(HashMap::new())),
            alive: alive_flag(),
            next_request: AtomicU64::new(1),
            pid: AtomicU32::new(0),
            app_data: std::env::temp_dir().join("toujing-runtime-tests"),
        }
    }

    fn run_blocking<F: std::future::Future>(future: F) -> F::Output {
        tauri::async_runtime::block_on(future)
    }

    #[test]
    fn cold_review_context_has_a_bounded_separate_deadline() {
        assert_eq!(request_timeout("review.context"), Duration::from_secs(300));
        for method in ["review.start", "review.poll", "account.list", "runtime.health"] {
            assert_eq!(request_timeout(method), Duration::from_secs(30));
        }
    }

    #[test]
    fn keyed_credential_methods_stay_in_the_product_allowlist() {
        for method in KEYED_PRODUCT_METHODS {
            assert!(
                PRODUCT_METHODS.contains(method),
                "{method} has a dedicated credential branch but is missing from PRODUCT_METHODS"
            );
        }
        assert!(PRODUCT_METHODS.contains(&"strategy_teaching.explain"));
    }

    /// The sidecar always terminates its JSON lines with a newline.
    fn framed(line: &[u8]) -> Vec<u8> {
        let mut bytes = line.to_vec();
        bytes.push(b'\n');
        bytes
    }

    #[test]
    fn stray_line_does_not_kill_pending_requests() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let (sender, receiver) = oneshot::channel();
        pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let mut buffer = Vec::new();
        route_stdout_chunk(&pending, &alive, &mut buffer, b"some stray log line\n");
        assert!(pending.lock().unwrap().contains_key("request-1"));
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-1","ok":true,"result":{},"error":null}"#),
        );
        assert!(receiver.blocking_recv().unwrap().ok);
    }

    #[test]
    fn line_without_request_id_is_ignored() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let (sender, receiver) = oneshot::channel();
        pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let mut buffer = Vec::new();
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"ok":false,"error":{"code":"x","message":"y"}}"#),
        );
        assert!(pending.lock().unwrap().contains_key("request-1"));
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-1","ok":true,"result":{},"error":null}"#),
        );
        assert!(receiver.blocking_recv().unwrap().ok);
    }

    #[test]
    fn corrupt_payload_fails_only_the_matching_request() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let mut receivers = HashMap::new();
        for request_id in ["request-1", "request-2"] {
            let (sender, receiver) = oneshot::channel();
            pending
                .lock()
                .unwrap()
                .insert(request_id.to_owned(), sender);
            receivers.insert(request_id.to_owned(), receiver);
        }
        // "ok" has the wrong type: the id matches but the payload is unusable.
        let mut buffer = Vec::new();
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-1","ok":"yes","result":null,"error":null}"#),
        );
        let response = receivers
            .remove("request-1")
            .unwrap()
            .blocking_recv()
            .unwrap();
        assert_eq!(response.error.unwrap().code, "runtime_protocol_error");
        assert!(pending.lock().unwrap().contains_key("request-2"));
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-2","ok":true,"result":{},"error":null}"#),
        );
        assert!(receivers
            .remove("request-2")
            .unwrap()
            .blocking_recv()
            .unwrap()
            .ok);
    }

    #[test]
    fn response_split_across_chunks_is_reassembled() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let (sender, receiver) = oneshot::channel();
        pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let mut buffer = Vec::new();
        route_stdout_chunk(&pending, &alive, &mut buffer, br#"{"request_id":"requ"#);
        assert!(pending.lock().unwrap().contains_key("request-1"));
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            br#"est-1","ok":true,"result":{},"error":null}"#,
        );
        route_stdout_chunk(&pending, &alive, &mut buffer, b"\n");
        assert!(receiver.blocking_recv().unwrap().ok);
    }

    #[test]
    fn multiple_lines_in_one_chunk_are_all_routed() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let mut receivers = Vec::new();
        for request_id in ["request-1", "request-2"] {
            let (sender, receiver) = oneshot::channel();
            pending
                .lock()
                .unwrap()
                .insert(request_id.to_owned(), sender);
            receivers.push(receiver);
        }
        let mut bytes = framed(br#"{"request_id":"request-1","ok":true,"result":{},"error":null}"#);
        bytes.extend_from_slice(&framed(
            br#"{"request_id":"request-2","ok":true,"result":{},"error":null}"#,
        ));
        let mut buffer = Vec::new();
        route_stdout_chunk(&pending, &alive, &mut buffer, &bytes);
        assert!(receivers
            .into_iter()
            .all(|receiver| receiver.blocking_recv().unwrap().ok));
    }

    #[test]
    fn response_is_routed_by_request_id() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = alive_flag();
        let (sender, receiver) = oneshot::channel();
        pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let mut buffer = Vec::new();
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-1","ok":true,"result":{"status":"ok"},"error":null}"#),
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
            pending
                .lock()
                .unwrap()
                .insert(request_id.to_owned(), sender);
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

    #[test]
    fn poisoned_pending_lock_degrades_instead_of_panicking() {
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let (sender, receiver) = oneshot::channel();
        pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let poison_source = Arc::clone(&pending);
        std::thread::spawn(move || {
            let _guard = poison_source.lock().unwrap();
            panic!("poison the pending lock");
        })
        .join()
        .unwrap_err();
        let alive = alive_flag();
        let mut buffer = Vec::new();
        route_stdout_chunk(
            &pending,
            &alive,
            &mut buffer,
            &framed(br#"{"request_id":"request-1","ok":true,"result":{},"error":null}"#),
        );
        assert!(!alive.load(Ordering::SeqCst));
        assert_eq!(
            receiver.blocking_recv().unwrap().error.unwrap().code,
            "runtime_protocol_error"
        );
    }

    #[test]
    fn product_allowlist_excludes_shell_and_sql() {
        assert!(!PRODUCT_METHODS.contains(&"shell.execute"));
        assert!(!PRODUCT_METHODS.contains(&"sql.query"));
        assert!(!PRODUCT_METHODS.contains(&"model.test_connection"));
        assert!(!PRODUCT_METHODS.contains(&"search.test_connection"));
        assert!(!PRODUCT_METHODS.contains(&"quotes.status"));
        assert!(PRODUCT_METHODS.contains(&"episode.get"));
    }

    #[test]
    fn write_failure_cleans_the_pending_entry() {
        let manager = manager_without_child();
        let response = run_blocking(manager.request_with_timeout(
            "runtime.health",
            json!({}),
            Duration::from_secs(1),
        ));
        assert_eq!(response.unwrap_err(), "core runtime is unavailable");
        assert!(manager.pending.lock().unwrap().is_empty());
    }

    #[test]
    fn poisoned_child_lock_fails_the_request_without_hanging() {
        let manager = manager_without_child();
        let poison_source = Arc::clone(&manager.child);
        std::thread::spawn(move || {
            let _guard = poison_source.lock().unwrap();
            panic!("poison the child lock");
        })
        .join()
        .unwrap_err();
        let response = run_blocking(manager.request_with_timeout(
            "runtime.health",
            json!({}),
            Duration::from_secs(1),
        ));
        assert_eq!(
            response.unwrap_err(),
            "runtime child lock poisoned"
        );
        assert!(manager.pending.lock().unwrap().is_empty());
    }

    #[test]
    fn kill_fails_pending_requests_and_rejects_later_ones() {
        let manager = manager_without_child();
        let (sender, receiver) = oneshot::channel();
        manager
            .pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        manager.kill();
        assert!(!manager.alive.load(Ordering::SeqCst));
        assert_eq!(
            receiver.blocking_recv().unwrap().error.unwrap().code,
            "runtime_shutdown"
        );
        let later = run_blocking(manager.request("runtime.health", json!({})));
        assert_eq!(later.unwrap_err(), "core runtime is unavailable");
    }

    #[test]
    fn shutdown_stays_bounded_and_stops_the_runtime() {
        let manager = manager_without_child();
        let (sender, receiver) = oneshot::channel();
        manager
            .pending
            .lock()
            .unwrap()
            .insert("request-1".to_owned(), sender);
        let started = std::time::Instant::now();
        run_blocking(manager.shutdown());
        assert!(
            started.elapsed() < SHUTDOWN_TIMEOUT + Duration::from_secs(2),
            "shutdown must not wait past its short deadline"
        );
        assert!(!manager.alive.load(Ordering::SeqCst));
        assert!(manager.pending.lock().unwrap().is_empty());
        assert_eq!(
            receiver.blocking_recv().unwrap().error.unwrap().code,
            "runtime_shutdown"
        );
    }

    #[test]
    fn force_kill_survives_missing_or_poisoned_child_slot() {
        let manager = manager_without_child();
        manager.kill();
        let poison_source = Arc::clone(&manager.child);
        std::thread::spawn(move || {
            let _guard = poison_source.lock().unwrap();
            panic!("poison the child lock");
        })
        .join()
        .unwrap_err();
        force_kill_child(&manager.child, 0);
    }

    #[test]
    fn sidecar_pidfile_records_and_reports_previous_process() {
        let app_data = std::env::temp_dir().join(format!(
            "toujing-runtime-tests-pidfile-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&app_data).unwrap();
        let pidfile = app_data.join(SIDECAR_PIDFILE);
        std::fs::write(&pidfile, std::process::id().to_string()).unwrap();
        note_previous_sidecar(&app_data);
        std::fs::write(&pidfile, "not-a-pid").unwrap();
        note_previous_sidecar(&app_data);
        std::fs::write(&pidfile, "999999999").unwrap();
        note_previous_sidecar(&app_data);
        std::fs::remove_dir_all(&app_data).unwrap();
        assert!(process_is_alive(std::process::id()));
        assert!(!process_is_alive(999_999_999));
    }
}
