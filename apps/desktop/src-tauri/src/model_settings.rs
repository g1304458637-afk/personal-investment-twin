//! A single application-owned Keychain item. No shell commands or secret getter IPC.
use serde::Serialize;
use serde_json::{json, Value};

const SERVICE: &str = "com.toujing.desktop.model-service";
const ACCOUNT: &str = "deepseek";

#[derive(Serialize)]
pub struct ModelStatus {
    configured: bool,
    provider: &'static str,
    model: &'static str,
}

fn status(configured: bool) -> ModelStatus {
    ModelStatus { configured, provider: "deepseek", model: "deepseek-v4-flash" }
}

fn validate_key(key: &str) -> Result<(), String> {
    if key.is_empty() || key.len() > 512 || !key.bytes().all(|b| b.is_ascii_graphic()) {
        return Err("model_key_invalid".into());
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn read_key() -> Result<Option<String>, String> {
    use security_framework::passwords::{generic_password, PasswordOptions};
    match generic_password(PasswordOptions::new_generic_password(SERVICE, ACCOUNT)) {
        Ok(bytes) => {
            let key = String::from_utf8(bytes).map_err(|_| "model_keychain_unavailable")?;
            validate_key(&key)?;
            Ok(Some(key))
        }
        Err(e) if e.code() == -25300 => Ok(None), // errSecItemNotFound, not access denied
        Err(_) => Err("model_keychain_unavailable".into()),
    }
}

#[cfg(not(target_os = "macos"))]
fn read_key() -> Result<Option<String>, String> { Err("model_keychain_unsupported".into()) }

#[tauri::command]
pub async fn model_service_status() -> Result<ModelStatus, String> {
    tauri::async_runtime::spawn_blocking(|| read_key().map(|k| status(k.is_some())))
        .await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

#[tauri::command]
pub async fn model_service_save(api_key: String) -> Result<ModelStatus, String> {
    tauri::async_runtime::spawn_blocking(move || {
        validate_key(&api_key)?;
        #[cfg(target_os = "macos")]
        {
            security_framework::passwords::set_generic_password(SERVICE, ACCOUNT, api_key.as_bytes())
                .map_err(|_| "model_keychain_unavailable".to_owned())?;
            Ok(status(true))
        }
        #[cfg(not(target_os = "macos"))]
        { Err("model_keychain_unsupported".into()) }
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

#[tauri::command]
pub async fn model_service_delete() -> Result<ModelStatus, String> {
    tauri::async_runtime::spawn_blocking(|| {
        #[cfg(target_os = "macos")]
        {
            match security_framework::passwords::delete_generic_password(SERVICE, ACCOUNT) {
                Ok(()) => Ok(status(false)),
                Err(e) if e.code() == -25300 => Ok(status(false)),
                Err(_) => Err("model_keychain_unavailable".into()),
            }
        }
        #[cfg(not(target_os = "macos"))]
        { Err("model_keychain_unsupported".into()) }
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

fn attach_key(mut params: Value, key: Option<String>) -> Result<Value, String> {
    let object = params.as_object_mut().ok_or("invalid_params")?;
    // Ignore any frontend-supplied internal credential. Deletion never falls back to env.
    object.remove("_desktop_model_key");
    object.insert("_desktop_model_key".into(), Value::String(key.ok_or("model_not_configured")?));
    Ok(params)
}

pub async fn with_saved_key(params: Value) -> Result<Value, String> {
    let key = tauri::async_runtime::spawn_blocking(read_key).await
        .map_err(|_| "model_keychain_unavailable".to_owned())??;
    attach_key(params, key)
}

#[tauri::command]
pub async fn model_service_test(manager: tauri::State<'_, crate::runtime::RuntimeManager>)
    -> Result<crate::runtime::RuntimeResponse, String> {
    let params = with_saved_key(json!({})).await?;
    manager.request("model.test_connection", params).await
}

const BOCHA_ACCOUNT: &str = "bocha";

#[derive(Serialize)]
pub struct SearchStatus {
    configured: bool,
    enabled: bool,
    provider: &'static str,
}

fn search_status(configured: bool, enabled: bool) -> SearchStatus {
    SearchStatus { configured, enabled, provider: "bocha" }
}

const SEARCH_PREFS_FILE: &str = "research-prefs.json";

fn search_prefs_path(app_data: &std::path::Path) -> std::path::PathBuf {
    app_data.join(SEARCH_PREFS_FILE)
}

fn read_search_enabled(app_data: &std::path::Path) -> Result<bool, String> {
    let bytes = match std::fs::read(search_prefs_path(app_data)) {
        Ok(bytes) => bytes,
        // No file yet: first-run default keeps search enabled.
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(true),
        Err(_) => return Err("search_prefs_unavailable".to_owned()),
    };
    let value: Value = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(_) => {
            // A corrupt file must never re-open a feature the user closed:
            // the safe default is disabled, not enabled.
            eprintln!(
                "toujing: {} is corrupt; search stays disabled until re-enabled",
                SEARCH_PREFS_FILE
            );
            return Ok(false);
        }
    };
    match value.get("search_enabled").and_then(Value::as_bool) {
        Some(enabled) => Ok(enabled),
        None => {
            eprintln!(
                "toujing: {} has no boolean search_enabled; search stays disabled",
                SEARCH_PREFS_FILE
            );
            Ok(false)
        }
    }
}

fn write_search_enabled(app_data: &std::path::Path, enabled: bool) -> Result<(), String> {
    std::fs::create_dir_all(app_data).map_err(|_| "search_prefs_unavailable".to_owned())?;
    let payload = serde_json::to_vec(&json!({ "search_enabled": enabled }))
        .expect("search prefs payload always serializes");
    // Write to a temp file and rename so a crash can never leave a
    // half-written or corrupt prefs file behind.
    let temporary = app_data.join(format!(
        "{}.{}.tmp",
        SEARCH_PREFS_FILE,
        std::process::id()
    ));
    let committed = std::fs::write(&temporary, &payload)
        .and_then(|()| std::fs::rename(&temporary, search_prefs_path(app_data)));
    if let Err(error) = committed {
        let _ = std::fs::remove_file(&temporary);
        eprintln!("toujing: failed to persist search preferences: {error}");
        return Err("search_prefs_unavailable".into());
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn read_bocha_key() -> Result<Option<String>, String> {
    use security_framework::passwords::{generic_password, PasswordOptions};
    match generic_password(PasswordOptions::new_generic_password(SERVICE, BOCHA_ACCOUNT)) {
        Ok(bytes) => {
            let key = String::from_utf8(bytes).map_err(|_| "model_keychain_unavailable")?;
            validate_key(&key)?;
            Ok(Some(key))
        }
        Err(e) if e.code() == -25300 => Ok(None),
        Err(_) => Err("model_keychain_unavailable".into()),
    }
}

#[cfg(not(target_os = "macos"))]
fn read_bocha_key() -> Result<Option<String>, String> { Err("model_keychain_unsupported".into()) }

#[tauri::command]
pub async fn search_service_status(manager: tauri::State<'_, crate::runtime::RuntimeManager>) -> Result<SearchStatus, String> {
    let app_data = manager.app_data.clone();
    tauri::async_runtime::spawn_blocking(move || {
        Ok(search_status(read_bocha_key()?.is_some(), read_search_enabled(&app_data)?))
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

#[tauri::command]
pub async fn search_service_save(api_key: String, manager: tauri::State<'_, crate::runtime::RuntimeManager>) -> Result<SearchStatus, String> {
    let app_data = manager.app_data.clone();
    tauri::async_runtime::spawn_blocking(move || {
        validate_key(&api_key)?;
        #[cfg(target_os = "macos")]
        {
            security_framework::passwords::set_generic_password(SERVICE, BOCHA_ACCOUNT, api_key.as_bytes())
                .map_err(|_| "model_keychain_unavailable".to_owned())?;
            Ok(search_status(true, read_search_enabled(&app_data)?))
        }
        #[cfg(not(target_os = "macos"))]
        { Err("model_keychain_unsupported".into()) }
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

#[tauri::command]
pub async fn search_service_delete(manager: tauri::State<'_, crate::runtime::RuntimeManager>) -> Result<SearchStatus, String> {
    let app_data = manager.app_data.clone();
    tauri::async_runtime::spawn_blocking(move || {
        #[cfg(target_os = "macos")]
        {
            let enabled = read_search_enabled(&app_data)?;
            match security_framework::passwords::delete_generic_password(SERVICE, BOCHA_ACCOUNT) {
                Ok(()) => Ok(search_status(false, enabled)),
                Err(e) if e.code() == -25300 => Ok(search_status(false, enabled)),
                Err(_) => Err("model_keychain_unavailable".to_owned()),
            }
        }
        #[cfg(not(target_os = "macos"))]
        { Err("model_keychain_unsupported".into()) }
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())?
}

#[tauri::command]
pub async fn search_service_set_enabled(enabled: bool, manager: tauri::State<'_, crate::runtime::RuntimeManager>) -> Result<SearchStatus, String> {
    let app_data = manager.app_data.clone();
    tauri::async_runtime::spawn_blocking(move || {
        // Read the Keychain before touching the file: a Keychain failure must
        // not silently flip the stored preference.
        let configured = read_bocha_key()?.is_some();
        write_search_enabled(&app_data, enabled)?;
        Ok(search_status(configured, enabled))
    }).await.map_err(|_| "search_prefs_unavailable".to_owned())?
}

fn attach_optional_search(mut params: Value, key: Option<String>, enabled: bool) -> Result<Value, String> {
    let object = params.as_object_mut().ok_or("invalid_params")?;
    object.remove("_desktop_bocha_key");
    object.remove("_desktop_search_enabled");
    object.insert("_desktop_search_enabled".into(), Value::Bool(enabled));
    if enabled {
        if let Some(key) = key {
            object.insert("_desktop_bocha_key".into(), Value::String(key));
        }
    }
    Ok(params)
}

pub async fn with_optional_search(params: Value, app_data: &std::path::Path) -> Result<Value, String> {
    let app_data = app_data.to_path_buf();
    let (key, enabled) = tauri::async_runtime::spawn_blocking(move || {
        Ok::<_, String>((read_bocha_key()?, read_search_enabled(&app_data)?))
    }).await.map_err(|_| "model_keychain_unavailable".to_owned())??;
    attach_optional_search(params, key, enabled)
}

#[tauri::command]
pub async fn search_service_test(manager: tauri::State<'_, crate::runtime::RuntimeManager>)
    -> Result<crate::runtime::RuntimeResponse, String> {
    let key = tauri::async_runtime::spawn_blocking(read_bocha_key).await
        .map_err(|_| "model_keychain_unavailable".to_owned())??;
    let mut params = json!({});
    let object = params.as_object_mut().unwrap();
    object.insert("_desktop_bocha_key".into(), Value::String(key.ok_or("search_not_configured")?));
    manager.request("search.test_connection", params).await
}

#[tauri::command]
pub async fn quotes_service_status(manager: tauri::State<'_, crate::runtime::RuntimeManager>)
    -> Result<crate::runtime::RuntimeResponse, String> {
    manager.request("quotes.status", json!({})).await
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_or_deleted_key_never_uses_frontend_key() {
        assert_eq!(attach_key(json!({"_desktop_model_key":"untrusted"}), None).unwrap_err(), "model_not_configured");
    }
    #[test]
    fn saved_key_overrides_input_without_mutating_product_scope() {
        let result = attach_key(json!({"subject_id":"synthetic", "_desktop_model_key":"untrusted"}), Some("test-only".into())).unwrap();
        assert_eq!(result["subject_id"], "synthetic");
        assert_eq!(result["_desktop_model_key"], "test-only");
    }
    #[test]
    fn status_has_no_credential_or_key_suffix() {
        assert_eq!(serde_json::to_value(status(true)).unwrap(), json!({"configured":true,"provider":"deepseek","model":"deepseek-v4-flash"}));
    }
    #[test]
    fn search_status_has_no_credential_or_key_suffix() {
        assert_eq!(serde_json::to_value(search_status(true, false)).unwrap(), json!({"configured":true,"enabled":false,"provider":"bocha"}));
    }
    #[test]
    fn disabled_search_strips_key_and_does_not_require_one() {
        let result = attach_optional_search(json!({"subject_id":"synthetic","_desktop_bocha_key":"untrusted"}), Some("test-only".into()), false).unwrap();
        assert_eq!(result["subject_id"], "synthetic");
        assert_eq!(result["_desktop_search_enabled"], false);
        assert!(result.get("_desktop_bocha_key").is_none());
    }
    #[test]
    fn enabled_search_overrides_frontend_key() {
        let result = attach_optional_search(json!({"_desktop_bocha_key":"untrusted"}), Some("test-only".into()), true).unwrap();
        assert_eq!(result["_desktop_bocha_key"], "test-only");
        assert_eq!(result["_desktop_search_enabled"], true);
    }
    #[test]
    fn enabled_search_without_key_has_no_secret_field() {
        let result = attach_optional_search(json!({"_desktop_bocha_key":"untrusted"}), None, true).unwrap();
        assert!(result.get("_desktop_bocha_key").is_none());
        assert_eq!(result["_desktop_search_enabled"], true);
    }
    #[test]
    fn invalid_input_has_only_stable_error_code() {
        for key in ["", "secret\n", " secret", "秘密", &"x".repeat(513)] {
            assert_eq!(validate_key(key).unwrap_err(), "model_key_invalid");
        }
    }

    fn temp_app_data(tag: &str) -> std::path::PathBuf {
        let directory = std::env::temp_dir().join(format!(
            "toujing-prefs-tests-{}-{tag}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&directory);
        std::fs::create_dir_all(&directory).unwrap();
        directory
    }

    #[test]
    fn missing_prefs_file_defaults_to_enabled() {
        let app_data = temp_app_data("missing");
        assert_eq!(read_search_enabled(&app_data), Ok(true));
        std::fs::remove_dir_all(&app_data).unwrap();
    }

    #[test]
    fn corrupt_prefs_file_reports_disabled_not_enabled() {
        let app_data = temp_app_data("corrupt");
        std::fs::write(search_prefs_path(&app_data), b"{not json").unwrap();
        assert_eq!(read_search_enabled(&app_data), Ok(false));
        std::fs::write(search_prefs_path(&app_data), b"[]").unwrap();
        assert_eq!(read_search_enabled(&app_data), Ok(false));
        std::fs::write(search_prefs_path(&app_data), br#"{"search_enabled":"yes"}"#).unwrap();
        assert_eq!(read_search_enabled(&app_data), Ok(false));
        std::fs::remove_dir_all(&app_data).unwrap();
    }

    #[test]
    fn prefs_round_trip_is_atomic_without_temp_litter() {
        let app_data = temp_app_data("roundtrip");
        write_search_enabled(&app_data, false).unwrap();
        assert_eq!(read_search_enabled(&app_data), Ok(false));
        write_search_enabled(&app_data, true).unwrap();
        assert_eq!(read_search_enabled(&app_data), Ok(true));
        let leftovers: Vec<_> = std::fs::read_dir(&app_data)
            .unwrap()
            .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
            .filter(|name| name.ends_with(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "temp files left behind: {leftovers:?}");
        std::fs::remove_dir_all(&app_data).unwrap();
    }

    // Explicit opt-in integration test: only a unique, disposable synthetic item.
    // Never reads, replaces or deletes the actual application Keychain item.
    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "requires local macOS Keychain access"]
    fn keychain_roundtrip_across_processes() {
        use security_framework::passwords::{set_generic_password, delete_generic_password, generic_password, PasswordOptions};
        let name = format!("com.toujing.qa.{}.{}", std::process::id(), std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos());
        struct Cleanup(String);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = security_framework::passwords::delete_generic_password(&self.0, "qa"); } }
        let _cleanup = Cleanup(name.clone());
        set_generic_password(&name, "qa", b"invalid-synthetic-test-value").unwrap();
        let child = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "model_settings::tests::keychain_read_in_child", "--exact", "--test-threads=1"])
            .env("TOUJING_QA_KEYCHAIN_ITEM", &name).output().unwrap();
        // Child filter below uses full module path; assert at least one test actually ran.
        assert!(child.status.success());
        assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed"));
        set_generic_password(&name, "qa", b"replaced-synthetic-test-value").unwrap();
        assert_eq!(generic_password(PasswordOptions::new_generic_password(&name, "qa")).unwrap(), b"replaced-synthetic-test-value");
        delete_generic_password(&name, "qa").unwrap();
        assert_eq!(generic_password(PasswordOptions::new_generic_password(&name, "qa")).unwrap_err().code(), -25300);
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "child of disposable Keychain QA only"]
    fn keychain_read_in_child() {
        use security_framework::passwords::{generic_password, PasswordOptions};
        let name = std::env::var("TOUJING_QA_KEYCHAIN_ITEM").unwrap();
        assert!(name.starts_with("com.toujing.qa."));
        assert_eq!(generic_password(PasswordOptions::new_generic_password(&name, "qa")).unwrap(), b"invalid-synthetic-test-value");
    }
}
