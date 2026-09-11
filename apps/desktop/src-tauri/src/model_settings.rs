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

fn search_prefs_path(app_data: &std::path::Path) -> std::path::PathBuf {
    app_data.join("research-prefs.json")
}

fn read_search_enabled(app_data: &std::path::Path) -> bool {
    let Ok(bytes) = std::fs::read(search_prefs_path(app_data)) else { return true };
    serde_json::from_slice::<Value>(&bytes).ok()
        .and_then(|value| value.get("search_enabled")?.as_bool())
        .unwrap_or(true)
}

fn write_search_enabled(app_data: &std::path::Path, enabled: bool) -> Result<(), String> {
    std::fs::create_dir_all(app_data).map_err(|_| "search_prefs_unavailable".to_owned())?;
    std::fs::write(search_prefs_path(app_data), serde_json::to_vec(&json!({"search_enabled": enabled})).unwrap())
        .map_err(|_| "search_prefs_unavailable".into())
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
        Ok(search_status(read_bocha_key()?.is_some(), read_search_enabled(&app_data)))
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
            Ok(search_status(true, read_search_enabled(&app_data)))
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
            match security_framework::passwords::delete_generic_password(SERVICE, BOCHA_ACCOUNT) {
                Ok(()) => Ok(search_status(false, read_search_enabled(&app_data))),
                Err(e) if e.code() == -25300 => Ok(search_status(false, read_search_enabled(&app_data))),
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
        write_search_enabled(&app_data, enabled)?;
        Ok(search_status(read_bocha_key()?.is_some(), enabled))
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
        Ok::<_, String>((read_bocha_key()?, read_search_enabled(&app_data)))
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
