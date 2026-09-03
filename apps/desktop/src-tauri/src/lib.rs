use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const PRETRADE_ACTION: &str = "pretrade_check";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PretradePayload {
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
struct PretradeBridgeRequest {
    request_id: String,
    action: String,
    payload: PretradePayload,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct BridgeError {
    code: String,
    message: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct PretradeBridgeResponse {
    request_id: Option<String>,
    ok: bool,
    result: Option<Value>,
    error: Option<BridgeError>,
}

fn bridge_error(
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

fn run_fixed_bridge(request: &PretradeBridgeRequest) -> PretradeBridgeResponse {
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
            return bridge_error(
                &request.request_id,
                "bridge_process_failed",
                format!("failed to send request to the fixed Python bridge: {error}"),
            );
        }
    }
    match child.wait_with_output() {
        Ok(output) => decode_bridge_output(
            &request.request_id,
            output.status.success(),
            &output.stdout,
            &output.stderr,
        ),
        Err(error) => bridge_error(
            &request.request_id,
            "bridge_process_failed",
            format!("failed to read the fixed Python bridge response: {error}"),
        ),
    }
}

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![run_pretrade_check])
        .run(tauri::generate_context!())
        .expect("error while running the 投镜 desktop application");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> PretradeBridgeRequest {
        PretradeBridgeRequest {
            request_id: "request-42".to_owned(),
            action: PRETRADE_ACTION.to_owned(),
            payload: PretradePayload {
                subject_id: "demo-user:synthetic-behavior".to_owned(),
                proposed_time: "2025-01-08T23:59:00".to_owned(),
                symbol: "SYN_PAPER_WIN".to_owned(),
                side: "BUY".to_owned(),
                quantity: 200.0,
                execution_price: 13.0,
                fees: 5.0,
            },
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
}
