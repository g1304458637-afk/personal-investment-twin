# DSA Agent integration

Status: first-stage DSA integration verified, installed, and native UI checked.

This document describes the initial migration. Later public quote/search work and
the research-method/frontend checkpoint are tracked in
`docs/STOCK_RESEARCH_CAPABILITIES.md`; the initial "not claimed" list below is
not a current capability inventory.

Upstream: https://github.com/ZhuLinsen/daily_stock_analysis
Source revision: 089d9d26d68f8b839ea5a74a3784e4402925f8b7
License: MIT, copyright 2026 ZhuLinsen.

Preserve Toujing's deterministic financial domain and existing uncommitted work.
Vendor the upstream execution subsystem with provenance; adapt only its service
boundaries. Do not import upstream financial calculations, trading strategies,
notification channels, credentials, or automatic provider fallbacks.

## Implemented boundary

`agentChatService` requests `conversation_engine=dsa` for whole-account chat.
The runtime retains the V1/V2 protocol for existing callers, and dispatches the
new explicit engine to `src/agents/dsa_conversation.py`.

1. The existing runtime resolves the authorized account and source fingerprint.
2. DSA's pinned `run_agent_loop` selects and executes existing Toujing tools.
3. A transport adapter uses the existing runtime's async Responses client, model
   and credential. Reasoning is explicitly `none`; provider-side storage is off.
4. First request requires a tool; subsequent turns may finish (matching the old
   SDK's reset-tool-choice behavior). Invalid arguments return a bounded error
   with no records, allowing correction within the same ten-step budget.
5. Exact call/output pairing and record equality establish the read allowlist.
6. The existing structured answer contract and semantic grounding reviewer are
   shared. The old analysis Agent is NOT called inside DSA research.
7. Only validated answers reach the UI and separate local chat archive.

No generic tool can execute code, SQL, browse accounts, alter records, or place
orders. Existing finance tools and formulas are unchanged. Upstream's optional
stock-normalization imports are unused; account ownership is enforced by Toujing,
not inferred from DSA's stock scope.

## Answer and failure behavior

The shared formatter has concise-writing and short-review instructions; its
schema/number/reference/psychology checks are retained. DSA additionally requests
short conversational answers instead of repeating a whole-account report.
Real Synthetic QA exposed an ambiguous private error-list judge: it emitted
negative error codes while its findings explicitly said the answer was correct.
DSA uses `explicit_paragraph_verdict_v1`: an explicit supported boolean for EVERY
paragraph, plus question and guide checks. Duplicate/missing coverage fails.
Negative verdicts map back into the existing correction/fail-closed boundary.
This changes a private judge representation, not the public answer schema or
the underlying requirements for factual, numeric and semantic support.
An additional narrow guard rejects definitive primary-cause rankings from the
current toolset, which has no causal contribution-ranking output. It requests
an observation-based correction; it does not change calculations or silently
soften unsupported claims with the word "possibly".
There is one answer correction, without repeating research. After that, DSA may
omit only paragraphs rejected for unbound numbers. Every retained paragraph and
the full retained answer still undergo strict and semantic/question review.
No surviving answer, unknown refs, incorrect guides or failed semantic review
still result in no answer. This is not a free-prose fallback.

The existing single-Episode review/ClaimOption execution remains unchanged for
historical compatibility. It has not been relabeled as DSA or silently removed.

## Local conversations

Completed account turns are stored in `<runtime DB filename>.agent-chat.sqlite3`
next to the runtime DB, in a dedicated table, with owner-only file creation.
Storage contains user questions and validated answers, not raw model responses,
tool receipts, credentials or immutable Evidence. Last 50 completed turns per
scope are retained. The latest continuation head and three-turn model context
survive restart. Old pre-migration memory-only sessions cannot be reconstructed.

Loading history performs no model call. Source changes prevent old answers from
being reused as current facts. Deleting an owned account also removes its chat
archive. In-flight/unverified answers are never restored as completed responses.
The frontend restores saved answers and offers a saved-conversation control;
consent is not silently restored. A new conversation does not delete history.

## Deliberately not claimed

- This is selective source reuse, not installation of the full DSA application.
- No DSA news/search/data-vendor tools or buy/sell scoring are active.
- Knowledge remains the existing registered concept library, not a complete
  stock-teacher knowledge retrieval system.
- Progress events are shown; token-by-token unverified model text is not streamed.
- Installed application replacement requires a successful live QA gate; source
  changes and frontend builds alone do not update `/Applications/投镜.app`.

## Reproduction

Offline: `python -m pytest tests/test_dsa_conversation.py tests/test_chat_archive.py
tests/test_account_conversation.py tests/test_account_review.py -q`

Live, fixed Synthetic only: `.venv/bin/python scripts/qa_account_conversation.py
--engine dsa --keychain`. `--question` isolates a diagnostic without changing the
fixed Synthetic account. Omit `--keychain` to use an already loaded Terminal key.
The QA script never reads real account repositories and does not persist replies.

Packaged live/restart QA: `.venv/bin/python scripts/qa_dsa_packaged.py <binary>`.
It uses the same fixed Synthetic account in a temporary repository, validates
frontend-required refs/fingerprint, then restarts the process and checks exact
answer restoration without another model call. Temporary test files are removed.

## Validation observations (2026-09-07)

- Full Python regression before the final private-verdict refinement: 962 passed.
- Relevant post-refinement regression: 58 passed; the later primary-cause guard
  and adapter suite: 19 passed.
- Post-cache account/runtime/adapter regression: 39 passed; Rust isolated
  request-deadline regression passed.
- Frontend: 298 tests passed; TypeScript and production build passed.
- Real DeepSeek three-turn chain passed (weight denominator, loss follow-up,
  exact Episode chart guidance), including the final primary-cause guard.
- Packaged live answer + process-restart restoration passed. Timing exposed
  repeated fact construction before submission (37.78s). A bounded four-scope
  context cache now reuses only identical source fingerprints, returns deep
  copies, rechecks the fingerprint, and clears on account deletion. It does not
  cache model answers. Final packaged `review.start`: **0.15s**, compared with
  37.78s before caching; its live answer passed. Final restart restoration passed
  with an exact saved answer, no model call (cold reconstruction 148.02s).
- Only `review.context` receives a 300s initial deadline (cold QA: 139–159.78s,
  and 206.04s with concurrent desktop analytics);
  other requests stay at 30s and model jobs stay at 150s.
- Cold financial smoke returned identical old/new values: final cash/value
  103855.9, position PnL 3855.9, return 0.1918358208955224, position count 1.
  Old package took 94.39s and the new isolated package 112.82s; the legacy 90s QA
  timeout therefore failed. This remains a cold-start performance limitation,
  not evidence of a financial difference. Model timeouts were not relaxed.
- DSA license and source notice are included in the frozen package.
- No Git commit, push, financial-domain migration, or credential migration.

## References and retained code

OpenAI Docs skill and the installed SDK implementation informed the existing
Responses transport mapping; no second provider client was introduced.
Reference: https://developers.openai.com/api/docs/guides/function-calling
The DSA source provenance and local extraction changes are recorded in
`src/agents/dsa_vendor/UPSTREAM.md` with its original MIT license.

## Local installation

Updated `/Applications/投镜.app` after the user's explicit restart approval and
successful final packaged QA. Ad-hoc bundle signature verified. Core SHA-256:
`ceefd0a0040d1294e06f47ac7836a2b60028e98d7d14085d9817b9eb5a989e77`.
Old application moved, not deleted, to:
`/Users/cccc/Library/Application Support/Toujing/App Backups/dsa-migration.dZA1qe/投镜.app.disabled`.
Renaming that backup back to `.app` restores the previous executable. Existing
investment files and Keychain configuration were not changed by installation.

Native acceptance: opened the exact installed path, asked the fixed Synthetic
account what the 61.97% risk-asset weight means, and received a verified contextual
answer. Navigated to Settings then back to Ask Toujing: the same answer remained,
the saved-conversation control appeared, and no re-analysis started. Inspected
the actual screenshot: existing glass styling and the single reading surface
remain intact. App is left on Ask Toujing with that example answer.

Remaining limitations: cold first-time analytics preparation is still slow;
this migration does not claim to solve frozen numerical-runtime cold start.
DSA research/news providers, broad stock-teacher retrieval, and unverified token
streaming are not enabled by this first-stage execution-core migration.
