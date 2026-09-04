# Real User Loop v1

## Boundary

The installed Desktop starts one bundled, persistent `toujing-core` process. Tauri resolves its app-data directory and passes an explicit SQLite path; Python never infers storage from the working directory. React can call only registered product RPC methods through one allowlisted Tauri command. It has neither SQL nor arbitrary shell access.

## Canonical storage

Migration v1 stores accounts, import batches, canonical execution facts, reconciliation decisions, market-data batches, historical price facts, and instrument resolutions. SQLite is owned exclusively by the Python runtime. Position state, average cost, PnL, returns, Episodes, behavior metrics, and counterfactuals are derived, versioned, rebuildable results—not mutable database truth.

Trade and market commits are transactional. Raw CSV content and absolute paths are not retained. Batch metadata contains the basename, file hash, import timestamp, summary, and audit decisions. In v1 market facts are account-owned; deleting an account transactionally cascades through all facts owned by that account and never touches packaged Demo fixtures.

## Product flow

`Data & Accounts` uses the native Tauri CSV picker, previews through the Python runtime, and commits only after confirmation. Exact duplicates do not create a second financial fact. Possible trade duplicates require an explicit keep/skip decision; conflicting revisions and conflicting prices fail closed.

After trade import, the account exists even if historical prices are missing. Market coverage uses the frozen exact-date/no-forward-fill contract. A real account never consumes Synthetic Demo prices. Only replay-eligible executions plus complete required market observations can produce runtime Investments and a complete Position Episode.

Demo and real-user modes are explicit. Demo continues to use the deterministic generated artifact. Real-user Investments and Episodes travel directly through Tauri to the persistent Python runtime and SQLite repository; they never pass through generated JSON.

## Known limitations

- Generic CSV v1 expects qualified instrument identity or a prior explicit resolution.
- Historical prices are user-provided daily `adjusted_close` or `total_return` observations; there is no network provider.
- There is no corporate-action calculator, FX conversion, margin, short selling, or shared cross-account market-data catalog.
- The installed runtime is currently built for macOS Apple Silicon.
