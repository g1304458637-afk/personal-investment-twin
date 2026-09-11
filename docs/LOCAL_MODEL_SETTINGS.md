# Local model settings

The macOS desktop Settings page configures DeepSeek (`deepseek-v4-flash`) once.
It uses the existing `create_model_runtime`, Responses adapter, analysis tools and
evidence validation. No financial method or Agent analysis policy changes.

## Credential boundary

- The sole credential is a generic password item in macOS Keychain, service
  `com.toujing.desktop.model-service`, account `deepseek`.
- Rust uses `security-framework` 3.7.0, not a shell command. Only status (boolean),
  save, delete and a fixed connection test are exposed; there is no secret getter.
- Input is a transient password field, cleared when submitted. No localStorage,
  database, preferences file, `.env`, command arguments, logs or repository keys.
- On every desktop `review.start`, Rust reads the current Keychain item and
  overwrites the private credential parameter before writing existing local
  stdin IPC. Missing/deleted/denied Keychain access fails closed. It never falls
  back to a Terminal environment key. Other frontend methods reject that parameter.
- Python passes a per-run mapping to the existing provider factory. It does not
  modify process environment or persist credentials in jobs/inferences/evidence.
  CLI-only usage retains its existing environment configuration.
- Deleting blocks new requests; it cannot revoke an already sent provider request.
  Provider-side revocation remains the way to invalidate a compromised API key.
- SDK model/tool payload logging is explicitly disabled in the desktop child.
  Connection errors return fixed public codes, not exception bodies.
- Ordinary browsers have no credential UI operations, HTTP Python server or shell
  access. Existing Tauri local-window capabilities and CSP remain in force.

## Connection test and lifecycle

Test sends only fixed “Connection check” text to the same model, with no tools,
account context or retrieval, reasoning none, one turn and a 15-second bound.
It may incur a small provider charge; saving itself does not call the provider.
Financial review still requires the existing per-request data-sharing consent.

Existing Rust startup/shutdown already owns Python: debug uses the project venv;
release launches the bundled `toujing-core`. The release `.app` embeds the frontend
and Python sidecar and needs neither Vite nor Terminal. The generated bundle is
`apps/desktop/src-tauri/target/release/bundle/macos/投镜.app`.
It must be rebuilt after backend changes; no installed `/Applications` copy is
automatically replaced. Unsigned/ad-hoc local builds may require macOS permission,
and rebuilding the executable can trigger another Keychain access prompt.

## Verification

Offline Python tests cover explicit credentials, deleted-key failure, provider
reuse, fixed test payload, timeout/error redaction and client cleanup. Node tests
cover desktop-only commands, password clearing, loading guard and bilingual copy.
Rust unit tests cover private parameter override and status without secret fields.
The opt-in `keychain_roundtrip_across_processes` test exercises an isolated temporary
synthetic item, including replacement and deletion, without touching the app item.
Real DeepSeek credentials are entered only by the user in the desktop UI.
