use tauri::Manager;

mod runtime;
mod model_settings;
mod external_links;

// The fixed pre-trade bridge shells out to the repo-local Python venv via a
// build-machine path; it only ever worked in development builds.
#[cfg(debug_assertions)]
mod pretrade {
    use serde::{Deserialize, Serialize};
    use serde_json::Value;
    use std::io::{Read, Write};
    use std::path::{Path, PathBuf};
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};

    pub const PRETRADE_ACTION: &str = "pretrade_check";
    // The bridge must answer inside this budget or it is killed and the
    // caller gets a structured timeout instead of hanging forever.
    const BRIDGE_TIMEOUT: Duration = Duration::from_secs(30);

    #[derive(Clone, Debug, Deserialize, Serialize)]
    #[serde(deny_unknown_fields)]
    pub struct PretradePayload {
        subject_id: String,
        proposed_time: String,
        symbol: String,
        side: String,
        quantity: f64,
        execution_price: f64,
        fees: f64,
    }

    #[derive(Clone, Debug, Deserialize, Serialize)]
    #[serde(deny_unknown_fields)]
    pub struct PretradeBridgeRequest {
        pub(crate) request_id: String,
        action: String,
        payload: PretradePayload,
    }

    #[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
    pub struct BridgeError {
        code: String,
        message: String,
    }

    #[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
    pub struct PretradeBridgeResponse {
        request_id: Option<String>,
        ok: bool,
        result: Option<Value>,
        error: Option<BridgeError>,
    }

    pub fn bridge_error(
        request_id: &str,
        code: &str,
        message: impl Into<String>,
    ) -> PretradeBridgeResponse {
        PretradeBridgeResponse {
            request_id: Some(request_id.to_owned()),
            ok: false,
            result: None,
            error: Some(BridgeError {
                code: code.to_owned(),
                message: message.into(),
            }),
        }
    }

    fn project_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
    }

    fn resolve_dev_python(root: &Path) -> Result<PathBuf, String> {
        #[cfg(target_os = "windows")]
        let candidate = root.join(".venv/Scripts/python.exe");
        #[cfg(not(target_os = "windows"))]
        let candidate = root.join(".venv/bin/python");

        if candidate.is_file() {
            Ok(candidate)
        } else {
            Err(format!(
                "project Python runtime was not found at {}",
                candidate.display()
            ))
        }
    }

    fn decode_bridge_output(
        request_id: &str,
        exit_success: bool,
        stdout: &[u8],
        stderr: &[u8],
    ) -> PretradeBridgeResponse {
        if !exit_success {
            let detail = String::from_utf8_lossy(stderr).trim().to_owned();
            return bridge_error(
                request_id,
                "bridge_process_failed",
                if detail.is_empty() {
                    "the fixed Python bridge exited unsuccessfully".to_owned()
                } else {
                    format!("the fixed Python bridge exited unsuccessfully: {detail}")
                },
            );
        }

        let text = match std::str::from_utf8(stdout) {
            Ok(value) => value.trim(),
            Err(_) => {
                return bridge_error(
                    request_id,
                    "bridge_output_invalid",
                    "the fixed Python bridge returned non-UTF-8 output",
                )
            }
        };
        if text.is_empty() || text.lines().count() != 1 {
            return bridge_error(
                request_id,
                "bridge_output_invalid",
                "the fixed Python bridge must return exactly one JSON line",
            );
        }

        let response: PretradeBridgeResponse = match serde_json::from_str(text) {
            Ok(value) => value,
            Err(_) => {
                return bridge_error(
                    request_id,
                    "bridge_output_invalid",
                    "the fixed Python bridge returned malformed JSON",
                )
            }
        };
        if response.request_id.as_deref() != Some(request_id) {
            return bridge_error(
                request_id,
                "bridge_output_invalid",
                "the fixed Python bridge returned a mismatched request_id",
            );
        }
        response
    }

    /// Drains one pipe on a worker thread so a chatty child can never block
    /// the wait loop below.
    fn spawn_output_reader<R: Read + Send + 'static>(
        pipe: Option<R>,
    ) -> std::thread::JoinHandle<Vec<u8>> {
        std::thread::spawn(move || {
            let mut buffer = Vec::new();
            if let Some(mut pipe) = pipe {
                let _ = pipe.read_to_end(&mut buffer);
            }
            buffer
        })
    }

    enum BridgeOutcome {
        Finished(std::process::ExitStatus),
        TimedOut,
        WaitFailed(String),
    }

    /// Polls the child with a hard deadline; on expiry the process is killed
    /// and reaped so nothing is left behind.
    fn wait_bridge_child(child: &mut std::process::Child, deadline: Instant) -> BridgeOutcome {
        loop {
            match child.try_wait() {
                Ok(Some(status)) => return BridgeOutcome::Finished(status),
                Ok(None) => {
                    if Instant::now() >= deadline {
                        let _ = child.kill();
                        let _ = child.wait();
                        return BridgeOutcome::TimedOut;
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(error) => return BridgeOutcome::WaitFailed(error.to_string()),
            }
        }
    }

    pub(crate) fn run_fixed_bridge(request: &PretradeBridgeRequest) -> PretradeBridgeResponse {
        if request.action != PRETRADE_ACTION {
            return bridge_error(
                &request.request_id,
                "unsupported_action",
                format!("only action '{PRETRADE_ACTION}' is supported"),
            );
        }
        if request.request_id.trim().is_empty() {
            return bridge_error(
                &request.request_id,
                "invalid_request",
                "request_id must be a non-empty string",
            );
        }

        let root = project_root();
        let python = match resolve_dev_python(&root) {
            Ok(value) => value,
            Err(message) => {
                return bridge_error(&request.request_id, "python_runtime_unavailable", message)
            }
        };
        let bridge = root.join("scripts/pretrade_bridge.py");
        if !bridge.is_file() {
            return bridge_error(
                &request.request_id,
                "bridge_unavailable",
                format!(
                    "fixed pre-trade bridge was not found at {}",
                    bridge.display()
                ),
            );
        }

        let request_bytes = match serde_json::to_vec(request) {
            Ok(mut value) => {
                value.push(b'\n');
                value
            }
            Err(error) => {
                return bridge_error(
                    &request.request_id,
                    "invalid_request",
                    format!("request serialization failed: {error}"),
                )
            }
        };
        let mut child = match Command::new(python)
            .arg(&bridge)
            .current_dir(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(value) => value,
            Err(error) => {
                return bridge_error(
                    &request.request_id,
                    "bridge_process_failed",
                    format!("failed to start the fixed Python bridge: {error}"),
                )
            }
        };
        if let Some(mut stdin) = child.stdin.take() {
            if let Err(error) = stdin.write_all(&request_bytes) {
                let _ = child.kill();
                let _ = child.wait();
                return bridge_error(
                    &request.request_id,
                    "bridge_process_failed",
                    format!("failed to send request to the fixed Python bridge: {error}"),
                );
            }
        }
        let stdout_reader = spawn_output_reader(child.stdout.take());
        let stderr_reader = spawn_output_reader(child.stderr.take());
        let deadline = Instant::now() + BRIDGE_TIMEOUT;
        match wait_bridge_child(&mut child, deadline) {
            BridgeOutcome::Finished(status) => {
                let stdout = stdout_reader.join().unwrap_or_default();
                let stderr = stderr_reader.join().unwrap_or_default();
                decode_bridge_output(&request.request_id, status.success(), &stdout, &stderr)
            }
            BridgeOutcome::TimedOut => bridge_error(
                &request.request_id,
                "bridge_timeout",
                format!(
                    "the fixed Python bridge did not answer within {}s and was stopped",
                    BRIDGE_TIMEOUT.as_secs()
                ),
            ),
            BridgeOutcome::WaitFailed(error) => bridge_error(
                &request.request_id,
                "bridge_process_failed",
                format!("failed to read the fixed Python bridge response: {error}"),
            ),
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        fn payload() -> PretradePayload {
            PretradePayload {
                subject_id: "demo-user:synthetic-behavior".to_owned(),
                proposed_time: "2025-01-08T23:59:00".to_owned(),
                symbol: "SYN_PAPER_WIN".to_owned(),
                side: "BUY".to_owned(),
                quantity: 200.0,
                execution_price: 13.0,
                fees: 5.0,
            }
        }

        fn request() -> PretradeBridgeRequest {
            PretradeBridgeRequest {
                request_id: "request-42".to_owned(),
                action: PRETRADE_ACTION.to_owned(),
                payload: payload(),
            }
        }

        #[test]
        fn request_contract_rejects_process_control_fields() {
            let mut value = serde_json::to_value(request()).unwrap();
            value["command"] = Value::String("sh".to_owned());

            assert!(serde_json::from_value::<PretradeBridgeRequest>(value).is_err());
        }

        #[test]
        fn unknown_action_is_rejected_before_process_launch() {
            let mut value = request();
            value.action = "run_python".to_owned();

            let response = run_fixed_bridge(&value);

            assert!(!response.ok);
            assert_eq!(response.request_id.as_deref(), Some("request-42"));
            assert_eq!(response.error.unwrap().code, "unsupported_action");
        }

        #[test]
        fn nonzero_bridge_exit_is_structured() {
            let response = decode_bridge_output("request-42", false, b"", b"bridge failed");

            assert!(!response.ok);
            assert_eq!(response.request_id.as_deref(), Some("request-42"));
            assert_eq!(response.error.unwrap().code, "bridge_process_failed");
        }

        #[test]
        fn malformed_bridge_output_is_structured() {
            let response = decode_bridge_output("request-42", true, b"not-json\n", b"");

            assert!(!response.ok);
            assert_eq!(response.error.unwrap().code, "bridge_output_invalid");
        }

        #[test]
        fn matching_response_id_is_preserved() {
            let response = decode_bridge_output(
                "request-42",
                true,
                br#"{"request_id":"request-42","ok":true,"result":{"simulation_status":"complete"},"error":null}"#,
                b"",
            );

            assert!(response.ok);
            assert_eq!(response.request_id.as_deref(), Some("request-42"));
        }

        #[test]
        fn mismatched_response_id_is_rejected_and_original_is_preserved() {
            let response = decode_bridge_output(
                "request-42",
                true,
                br#"{"request_id":"other","ok":true,"result":{},"error":null}"#,
                b"",
            );

            assert!(!response.ok);
            assert_eq!(response.request_id.as_deref(), Some("request-42"));
            assert_eq!(response.error.unwrap().code, "bridge_output_invalid");
        }

        #[cfg(unix)]
        #[test]
        fn bridge_wait_kills_the_child_at_the_deadline() {
            let mut child = Command::new("sleep")
                .arg("5")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .expect("sleep should spawn on unix");
            let outcome = wait_bridge_child(&mut child, Instant::now() + Duration::from_millis(150));
            assert!(matches!(outcome, BridgeOutcome::TimedOut));
            // The kill must leave nothing behind.
            assert!(child.try_wait().unwrap().is_some());
        }

        #[cfg(unix)]
        #[test]
        fn bridge_wait_returns_when_the_child_exits_in_time() {
            let mut child = Command::new("echo")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .expect("echo should spawn on unix");
            let outcome = wait_bridge_child(&mut child, Instant::now() + Duration::from_secs(10));
            assert!(matches!(outcome, BridgeOutcome::Finished(_)));
        }
    }
}

#[cfg(debug_assertions)]
use pretrade::{bridge_error, run_fixed_bridge, PretradeBridgeRequest, PretradeBridgeResponse};

#[cfg(debug_assertions)]
#[tauri::command]
async fn run_pretrade_check(request: PretradeBridgeRequest) -> PretradeBridgeResponse {
    let request_id = request.request_id.clone();
    match tauri::async_runtime::spawn_blocking(move || run_fixed_bridge(&request)).await {
        Ok(response) => response,
        Err(error) => bridge_error(
            &request_id,
            "bridge_runtime_failure",
            format!("pre-trade bridge task failed: {error}"),
        ),
    }
}

#[cfg(debug_assertions)]
fn ipc_handler() -> fn(tauri::ipc::Invoke<tauri::Wry>) -> bool {
    tauri::generate_handler![
        external_links::open_source_url,
        run_pretrade_check,
        runtime::runtime_health,
        runtime::runtime_core_smoke,
        runtime::runtime_product_request,
        model_settings::model_service_status,
        model_settings::model_service_save,
        model_settings::model_service_delete,
        model_settings::model_service_test,
        model_settings::search_service_status,
        model_settings::search_service_save,
        model_settings::search_service_delete,
        model_settings::search_service_set_enabled,
        model_settings::search_service_test,
        model_settings::quotes_service_status
    ]
}

#[cfg(not(debug_assertions))]
fn ipc_handler() -> fn(tauri::ipc::Invoke<tauri::Wry>) -> bool {
    tauri::generate_handler![
        external_links::open_source_url,
        runtime::runtime_health,
        runtime::runtime_core_smoke,
        runtime::runtime_product_request,
        model_settings::model_service_status,
        model_settings::model_service_save,
        model_settings::model_service_delete,
        model_settings::model_service_test,
        model_settings::search_service_status,
        model_settings::search_service_save,
        model_settings::search_service_delete,
        model_settings::search_service_set_enabled,
        model_settings::search_service_test,
        model_settings::quotes_service_status
    ]
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = runtime::install(
        tauri::Builder::default().plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch just brings the existing window forward.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        })),
    )
    .plugin(tauri_plugin_dialog::init())
    .invoke_handler(|invoke| {
        if invoke.message.webview_ref().label() != "main" {
            invoke.resolver.reject("window_command_not_allowed");
            return true;
        }
        ipc_handler()(invoke)
    })
    .build(tauri::generate_context!())
    .expect("error while running the 投镜 desktop application");
    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            // Startup may have failed before the runtime was managed; never
            // panic on the way out.
            if let Some(manager) = app_handle.try_state::<runtime::RuntimeManager>() {
                tauri::async_runtime::block_on(manager.shutdown());
            }
        }
    });
}
