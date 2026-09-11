use tauri_plugin_shell::ShellExt;

fn validate_source_url(value: &str) -> Result<tauri::Url, String> {
    if value.len() > 8192 || value.chars().any(char::is_control) {
        return Err("invalid_source_url".into());
    }
    let url = tauri::Url::parse(value).map_err(|_| "invalid_source_url".to_string())?;
    if !matches!(url.scheme(), "https" | "http") || url.host_str().is_none()
        || !url.username().is_empty() || url.password().is_some()
    {
        return Err("invalid_source_url".into());
    }
    Ok(url)
}

/// Only opens a user-clicked public web source; no file, custom scheme or command.
#[tauri::command]
pub async fn open_source_url(app: tauri::AppHandle, url: String) -> Result<(), String> {
    let url = validate_source_url(&url)?;
    // Reuse the already installed shell plugin; expose no shell permission to JS.
    #[allow(deprecated)]
    app.shell().open(url.to_string(), None).map_err(|_| "source_open_failed".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_only_web_sources() {
        for value in ["https://www.zqrb.cn/finance/article.html?x=1&y=2", "http://example.com/报告#原文"] {
            assert!(validate_source_url(value).is_ok());
        }
        for value in ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,x",
            "toujing://account", "mailto:a@example.com", "//example.com", "-a Calculator",
            "https://user:pass@example.com/", "https://example.com/\n"] {
            assert!(validate_source_url(value).is_err(), "{value}");
        }
        assert!(validate_source_url(&format!("https://example.com/{}", "x".repeat(8192))).is_err());
    }
}
