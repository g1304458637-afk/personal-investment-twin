# Production Python Runtime Sidecar v1

## Runtime audit

Before this change, the Desktop pre-trade bridge started a new process for every
request and resolved both Python and the script relative to the source checkout:

`React → Rust → repository .venv/bin/python → scripts/pretrade_bridge.py`

That path is retained only for the existing development-only pre-trade command
until its product API moves onto the runtime protocol. It is not a production
fallback.

The production architecture is:

`React → narrow Tauri command → Rust RuntimeManager → bundled toujing-core → existing Python core`

The manager starts one persistent process at application startup, performs a
version handshake, correlates request IDs, enforces timeouts, handles process
exit, and requests clean shutdown. Frontend code never receives a shell command,
arguments, working directory, or environment controls.

## Packaging decision

Runtime v1 targets macOS Apple Silicon only. PyInstaller 6.22.2 packages the
Python 3.11 runtime and the current scientific stack. The build workflow first
supports an inspectable `onedir` diagnostic build; the shipped sidecar uses
`onefile`, whose extraction cost is amortized by the persistent process.

The target-triple binary is placed at
`apps/desktop/src-tauri/binaries/toujing-core-aarch64-apple-darwin` and Tauri
includes it through `bundle.externalBin`. A release build never resolves
`python`, `python3`, `.venv`, repository scripts, or the current working
directory.

## Protocol v1

Transport is newline-delimited JSON over stdin/stdout. Every request contains
exactly `protocol_version`, `request_id`, `method`, and `params`. Every response
preserves `request_id` and has either `ok: true` plus `result`, or `ok: false`
plus a structured error. Stdout is protocol-only; diagnostics go to stderr.

Initial methods are deliberately limited to:

- `runtime.handshake`
- `runtime.health`
- `runtime.core_smoke`
- `runtime.shutdown`

`runtime.core_smoke` invokes the existing vectorbt replay adapter and returns a
stable summary. It contains no duplicate financial implementation.

## Development and production

Debug builds may start `.venv/bin/python -m toujing_core_runtime` from the source
checkout. Release builds fail closed if the configured bundled sidecar is
missing. Both modes use the exact same protocol and dispatcher.

## Known boundaries

- v1 produces only an Apple Silicon binary; other targets require native builds.
- Distribution signing/notarization must include the nested sidecar during the
  normal Tauri release-signing workflow.
- Database and product methods are introduced only after the runtime checkpoint.
