# 投镜 Desktop

Tauri 2 + React + TypeScript host for the local Python financial engine.
The native app imports supported trade/price CSV files into SQLite and calls
the Python sidecar over versioned NDJSON. Configured model/search services
use desktop credentials from macOS Keychain. Public market-history requests
use AKShare. There is no brokerage login, order submission or auto-trading.

The browser preview displays bundled synthetic results; it cannot call native
RPC or execute a custom strategy. Account review and saved retrospective
episode notes have real-account paths. The full History/Twin and pretrade
demonstrations still have synthetic-only boundaries; do not present them as
accepted real-account workflows. See [restart status](../../docs/RESTART_20261023.md).

## Local development

Prerequisites: Node.js/npm, the Tauri 2 Rust toolchain, and the repository's
Python 3.11 environment with `requirements.txt` installed.

```bash
npm ci
npm run check
npm run dev
```

Open `http://127.0.0.1:1420/#/overview` for the browser preview. To run the
native shell:

```bash
npm run tauri dev
```

Production verification:

```bash
npm run build
# From the repository root: .venv/bin/python scripts/build_python_sidecar.py
# This creates the real external binary required by the following command.
npm run tauri -- build --no-bundle
```

The native build needs a real sidecar, not the CI host-check placeholder.
Distribution still requires signing, notarization, install/upgrade and recovery
acceptance. Local build success alone does not establish those checks.

Product requests use a 300-second host budget and a 330-second frontend budget.
Python owns SQLite on one FIFO worker; health checks bypass slow computation.
Queued expired requests are rejected before execution. A timeout after a write
has started reports an unconfirmed outcome; reload account data before retrying.
Health success proves control-channel liveness, not analytics progress.

The host stores public quote cache under AppData/cache via `TOUJING_CACHE_DIR`;
standalone Python falls back to the user's OS cache directory. Cache failures
do not discard successfully fetched bars. Facts/chat databases use POSIX 0600,
with the host's dedicated AppData directory restricted to 0700.

## Dependency and license boundary

Direct packages are locked in `package-lock.json`; Rust crates are locked in
`src-tauri/Cargo.lock`.

- Tauri: MIT OR Apache-2.0
- React, React Router, Radix UI, cmdk, Motion, Tailwind CSS, Vite, PostCSS,
  Autoprefixer, clsx and tailwind-merge: MIT
- Apache ECharts and TypeScript: Apache-2.0
- class-variance-authority: Apache-2.0
- Lucide: ISC

Jan, OpenPets, assistant-ui, Magic UI and Motion Primitives are source-study
references only. They are not dependencies, submodules, copied assets, or
vendored source in this application.
