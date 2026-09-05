# Deep Decision Analysis / Same-Stock Compare v1 acceptance

## Scope and reference review

Implementation started from clean `53dc598`. The financial engines, canonical
ordering, daily market-data availability and registered counterfactual methods
are reused, not replaced. See `SAME_STOCK_REFERENCE_REVIEW.md` for actual source
paths and incompatible semantics: installed vectorbt 1.1.0, Ghostfolio holding
scope, pyfolio transaction handling, Wealthfolio / Portfolio Performance security
detail, rotki history filtering, ECharts shared axes and native tool-use examples.
Wealthfolio supplied architecture ideas only; no AGPL implementation was copied.

The user approved limited Episode-derived sharing, and separately approved only
the fixed `SYN_COMPARE_A/B` example for an actual DeepSeek acceptance request.
No real account, raw CSV or sharing credential was authorized for that request.

## Capability acceptance (do not conflate automated and product QA)

| Capability | Status | Contract / implementation | Tests and actual QA | Remaining boundary |
| --- | --- | --- | --- | --- |
| Same-Stock Compare Core | VERIFIED | `SAME_STOCK_COMPARE_CONTRACT_V1.md`; `src/compare/same_stock.py`, `demo.py` | 16 core tests; actual synthetic A -355 CNY, B +195 CNY displayed in browser and native app | Full-period results are not common-window performance. Shared data is sender-derived, not independently replayed brokerage truth. |
| Same-Stock Compare UI | VERIFIED (basic browser/native rendering and browser finding selection) | `SameStockComparisonPanel.tsx`, `SameStockTimeline.tsx`, `sameStock.ts` | Five Node tests; shared market, A/B lanes, normalized shapes, synthetic marker and finding selection checked | Physical trackpad/WKWebView gesture behavior NOT VERIFIED. Latest native workspace polish is build-checked, not fully manually re-certified. |
| Single Episode Deep Analysis | NOT VERIFIED end-to-end | `review_catalog.py`, `review.py`, `DecisionAnalysisWorkspace.tsx` | Own-account fixture goes through real ProductRuntime, scoped catalog and registered historical comparisons. Native synthetic context and prior-mark comparison inspected | Real personal-account native analysis and model-completed product flow not verified. No synthetic fallback for missing real facts. |
| Evidence-grounded Agent | NOT VERIFIED against live provider | `DECISION_REVIEW_AGENT_V1.md`; `decision_review.py` | 16 tests include the real Agents SDK loop with a scripted model, tool receipts, support/contrary grounding, prior-plan contradiction and injection rejection | Actual native attempt stopped at missing `DEEPSEEK_API_KEY`. No model answer was obtained; live outcome-bias, symmetry, correction behavior and comprehension remain unverified. |
| Self-history tool integration | VERIFIED (deterministic/runtime integration) | `review_sources.py`; existing registered HHI and mean daily turnover | Source test, SDK tool-loop tests and Node projection test; unavailable medians/counts remain unavailable | Native self-history interaction not fully manually verified; no longitudinal chasing/sequence frequency or ability estimate. |
| User-to-user authorization path | VERIFIED (contract and runtime integration) | `sharing.py`, `review_store.py`, narrow compare RPC, `reviewService.ts` | Six sharing tests plus runtime tests: signed permissions, recipient/expiry, local-only model denial, revocation, tampering and wrong signer rejection | Native export/import file-dialog round trip NOT VERIFIED. Fingerprint must be confirmed independently; no legal identity authentication or remote revocation of received offline copies. |

## Deterministic facts and financial boundaries

The dedicated pair uses one qualified synthetic CNY instrument and twelve real
calendar observation dates (2025-01-02 through 2025-01-17). Each account has five
canonical fills with one unit of recorded fee per fill. Existing vectorbt replay
produces A approximately -355 and B +195. A has two additions and one reduction;
B has one addition and two reductions. Existing before/after average-cost facts
show two versus one cost-raising additions. Relative to the *same recorded daily
trough*, zero versus one reduction occurred on earlier dates. None proves motive,
skill, an additive attribution share or that B is a strategy to copy.

Comparison rejects mismatched qualified instruments/currencies, inconsistent
owner/decision/path/result refs, missing required observations, conflicting
provenance and future market facts. Same-time executions retain canonical order;
chart offsets are visual only. Marked/realized and differing periods are disclosed.

Native inspection of the first registered historical alternative showed actual
79 CNY, fixed-assumption 0 CNY, difference -79 CNY; evaluation end Jan 6 10:00,
valuation observation Jan 3. These are separate fields, with prior daily mark
explicitly not presented as an intraday price. Infeasible alternatives remain
infeasible. No copied-counterparty portfolio scenario is invented.

## Agent and disclosure limits

Six native function tools expose owned/authorized derived facts. Successful SDK
receipts, both support and contradiction retrieval, self-history and registered
comparison lookup are required; comparison runs additionally require the actual
same-stock tool. References must have been retrieved and must support the bounded
hypothesis kind. Valid IDs alone are not enough. Financial numbers are rendered
from deterministic facts, not authored by the model.

This is a real model-directed tool loop with deliberately bounded interpretation
vocabulary, not an unrestricted financial essay generator. Scripted-model tests
do not establish real model reasoning quality. New retrospective user notes are
dated now and invalidate old interpretations without changing canonical facts,
Evidence, or past Twin state. Live correction of an actual model response is
still unverified.

Ed25519 share v2 signs exact recipient, expiry and independent model permission.
Only the public key/fingerprint travels; the signing private key is not exported
or persisted. Old symmetric HMAC packages require re-export. This repairs the
recipient's ability to re-sign altered permission fields, but is not a claim of
verified human identity. Derived time/quantity/price facts are still sensitive.

## Acceptance environment

Browser: fixed strict-port `http://127.0.0.1:1420`, explicit offline state with
analysis disabled; no fake browser model answer. A fresh reload had no blocking
console errors. Earlier edit-time HMR errors are not counted as a clean session.

Native: separate `com.personal-investment-twin.analysis-qa` application; empty
real-account state and dedicated synthetic comparison inspected. Actual review
button attempt, after synthetic-only permission, reported:
`Set DEEPSEEK_API_KEY in the environment for the DeepSeek provider.` No successful
external model request occurred. Need the existing key-injection/launch path,
not a key pasted into chat or committed to the repository.

The first automation launch returned unusually slowly; cause was not established.
Subsequent native accessibility reads succeeded. This is not a performance or
physical-gesture certification. No actual personal brokerage account was used.

## Final automated results

Full Python: 657 passed in 498.88 seconds (baseline 611). Desktop Node: 158 passed
(baseline 148). TypeScript check/build passed. Cargo check and 10 Rust
tests passed. Vite retains the large-chunk warning; no dependency upgrade or
unrelated bundling redesign was attempted.

Two complete deterministic exports produced the identical SHA-256:
`9efbd28f6f8991f98b7c1f001f4c243eac370d84a314daee135102918b9cb8d7`.
The generated artifact stays entirely Synthetic.

The actual frozen sidecar initially failed because the newly imported Agents
SDK's dependency metadata and bundled Markdown prompt resources were absent.
`scripts/build_python_sidecar.py` now collects `openai-agents` recursive metadata
and `agents` data files. This does not enable an application Memory feature.
After rebuilding, an isolated temporary-database NDJSON smoke passed handshake,
`review.context` (39 Synthetic records, own PnL -354.9999999999991), and shutdown,
with process exit 0. No external model request was involved. The isolated native
debug application also built successfully. `git diff --check` passed.

## Local implementation checkpoints

- `8a14a4d` — deterministic same-stock comparison.
- `143fa9f` — same-stock desktop comparison.
- `94cb9bc` — evidence-grounded review, scoped runtime and sharing integration.
- `04272fa` — sender signatures instead of recipient-editable symmetric permissions.
- `cf9169a` — analysis workspace, evidence links, retrospective notes and self-history.
- `8410bfa` — frozen runtime SDK metadata and resource packaging.

No push or amend. The acceptance report is a separate documentation checkpoint.
Live-model acceptance must remain open until the existing DeepSeek startup
configuration is available; this report is not full end-to-end certification.
