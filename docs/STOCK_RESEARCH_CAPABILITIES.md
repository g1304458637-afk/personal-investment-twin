# Stock research and capability discovery — 2026-09-08

This checkpoint connects a bounded public-stock research workflow and makes the
current Agent's capabilities visible throughout a conversation. It does not claim
full DSA application parity or a production trade-execution system.

## Reuse and provenance

`src/agents/stock_research_methods.py` adapts research checklists from
ZhuLinsen/daily_stock_analysis (MIT, copyright 2026 ZhuLinsen), pinned revision
`089d9d26d68f8b839ea5a74a3784e4402925f8b7`:

- `strategies/event_driven.yaml`: event classification, dates, influence pathways,
  confirmation and contradictory findings.
- `strategies/growth_quality.yaml`: same-period revenue, profit, operating cash
  flow, ROE, recurring versus one-off factors.
- `strategies/volume_breakout.yaml`: price/volume cross-check and the need for
  actual calculated confirmation before claiming a breakout.

Source base: https://github.com/ZhuLinsen/daily_stock_analysis/tree/089d9d26d68f8b839ea5a74a3784e4402925f8b7/strategies

Existing MIT notice: `src/agents/dsa_vendor/LICENSE`, already included in sidecar.
Local changes intentionally turn trading/scoring instructions into research
questions. No upstream score, buy/sell level, trend calculator, or ROE calculator
is executed. The entire 15-strategy library is NOT integrated by this checkpoint.

## Runtime

DSA loop -> `read_stock_research_method` when the user requests stock research ->
existing security/daily/quote/search tools -> existing structured answer and
per-paragraph grounding checks -> existing saved conversation.

Methods are knowledge records, not evidence of an event or signal. Each has a
distinct identity; stock facts still need actually read public records. The
method tool also returns a separate `research_status` configuration receipt, so
search-disabled explanations do not masquerade as stock facts or cite only a
method. Configuration never means a successful external connection. Daily bars
dated today are marked potentially unfinished to avoid treating partial volume
as a complete-session contraction.
The request supplies a current research timestamp, independent of Synthetic account
valuation date. Comprehensive research can use the existing five-paragraph
capacity; short follow-ups stay short. The answer schema and financial formulas
are unchanged. The result envelope adds `research_read_refs` for audited dynamic
method/status records; the frontend checks these against completed read receipts
before rendering or restoring an answer. No new model client, credentials or dependencies.

## Frontend

Persistent four-card overview: benefit, coverage, example question and local
service configuration. The existing compact shortcuts also stay by the composer.
Examples fill a draft only, never submit or grant consent. Episode scope links
explicitly to the whole-account assistant for the full toolset. Browser preview
never claims model availability. Quote-library readiness is not a live-provider
connection test. Bocha configuration is not evidence of a successful search.
Quote readiness is taken from completed account context, not a concurrent status
request that can time out while the packaged runtime is cold-starting.

Dedicated decision-preparation and comparison page links are labeled separately;
their calculations are NOT advertised as conversational tools.

## Remaining work

- Wire existing pretrade and comparison services into owned-scope Agent tools.
- Implement and verify a public technical-indicator adapter before exposing DSA
  signal strategies or computed trading levels.
- Structured financial-statement coverage, full upstream strategy library,
  scheduling and external report delivery are not part of this checkpoint.
- App source/build success is not an installed-app update; package and live QA
  results must be reported separately.

## Verified checkpoint

- Targeted Python regression: 64 passed, including backend-result-to-TypeScript
  projection, dynamic receipt validation and unfinished daily-bar semantics.
- Desktop tests: 313 passed; TypeScript check, production build and diff check passed.
- Real DeepSeek public quote research passed receipt/grounding checks with search
  disabled, including explicit unfinished-session wording. This is not complete
  news or financial-statement research acceptance.
- Packaged runtime: AKShare available; Bocha fixed-query connection test
  (上海证券交易所) connected successfully. Synthetic loss question completed, and
  the identical saved answer restored after process restart without a model call.
- Installed `/Applications/投镜.app`; ad-hoc signature verified. This is a local
  macOS build, not a notarized public distribution.
- Prior application preserved at
  `/Users/cccc/Library/Application Support/Toujing/App Backups/research-capabilities.rR4c08/投镜.app.disabled`.
- Packaged/installed backend SHA-256:
  `df71a40a796b99cc7b866519f0c8988d00c420741b0388ad660e0e5dcaed3413`.
- Native acceptance confirmed persisted chats restore and the capability cards
  remain outside the transcript. No account data or Keychain entries were edited.
- An older restored answer incorrectly described allocation pie charts as trade
  markers. That historical answer was not rewritten during this checkpoint;
  dedicated allocation-chart teaching grounding still needs targeted acceptance.
- No commit, push or amend. Existing dirty worktree preserved.

## Source-link desktop repair — 2026-09-08

Research sources previously used `target="_blank"` only. The desktop WebView
did not dispatch those links to the system browser. `SourceLink` now invokes the
narrow `open_source_url` native command on an explicit desktop click; web builds
retain ordinary links. Both layers validate HTTP(S), reject control characters,
credentials and non-web schemes. No generic shell permission is exposed to JS.
An opener failure exposes a retryable link and a selectable original URL.

TypeScript check and 316 frontend tests passed; Rust 20 passed / 2 existing
Keychain tests ignored. The signed application was replaced with user permission;
its previous version is recoverable at
`/Users/cccc/Library/Application Support/Toujing/App Backups/source-links.cOTmXO/投镜.app.disabled`.
The Python/Agent binary is unchanged from the verified hash above; no model call
or answer rewrite is needed to open existing saved sources.
Native acceptance: clicked the saved 证券日报 research source in `/Applications/投镜.app`;
the system browser (Chrome) opened the exact article path
`/shipin/shipinhangye/2026-08-21/A1787315515102.html`, with matching title and
article body visible. Existing saved chats restored without regeneration.
