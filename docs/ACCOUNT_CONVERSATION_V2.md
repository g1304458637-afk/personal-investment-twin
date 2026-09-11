# Question-driven account conversation V2

## What changes

The standalone account chat opts into `account_conversation_answer_v2`. The
original account V1 and Episode ClaimOption / Evidence contracts remain intact.
V2 is a session-only interpretation, never a ledger fact or immutable Evidence.

The analyst chooses relevant tools instead of running all five reads every turn.
Existing account facts are supplemented with read-only projections of the
existing `build_actual_outcomes` and account performance builders: per-investment
results, execution-backed before/after operations, and the actual daily path.
General knowledge about the registered methods and chart reading is a separate
versioned source; it is not a personal account fact or a live market feed.
The first knowledge set covers concentration/denominators, account versus
investment results, chart reading, and turnover—not a complete stock curriculum.
The allocation read returns both denominator contexts together. Operation counts
copy the existing event taxonomy (opening is not adding). Repeated daily-point
provenance arrays use a lossless source table; no observations are sampled away.

## Architecture

Existing DeepSeek runtime / Agents SDK -> analysis tool loop -> exact paired tool
receipts -> tool-free structured natural-language answer -> deterministic scope,
reference and numeric-format checks -> separate model grounding review -> UI.

The answer contains 1–5 bilingual paragraphs (`fact`, `concept`, `interpretation`),
each with read refs, plus up to three allowlisted page guides. No model-generated
URL, selector, arbitrary command or financial calculation is executed.

The grounding review checks relevance, unsupported motives/causes, mixed periods,
wrong denominators and bilingual consistency. It is a probabilistic quality gate,
not a proof of semantic correctness. Numeric token membership is only a formatting
guard, not proof that a number was assigned to the correct security or period.
One bounded answer correction is allowed; the prior candidate and issue codes are
returned to the same model under the original account consent. Analysis/tools do
not rerun during correction. Each strict JSON call has at most one format retry.
Failure returns no unverified prose. Approximate percentages in explanatory
paragraphs are explicitly flagged for semantic review; literal numeric matching
does not decide whether an approximation is financially meaningful.

History comes from backend-owned, fingerprinted session results (latest three
turns), not frontend-submitted assistant text. Account changes invalidate the
conversation. The UI requests cancellation through the existing owned-job poll
endpoint. Runtime phases are real progress, NOT pretend token streaming; candidate
analysis and unchecked final text are never rendered.

## Reuse decisions

- Dexter `src/agent/agent.ts` and `src/tools/registry.ts`: reference for iterative
  question-driven reads, continuation and bounded tool execution.
  <https://github.com/virattt/dexter>
- Rita `src/agent/prompt.ts` and `src/agent/messages.ts`: reference for separating
  conceptual explanation from source retrieval, and workspace-aware follow-ups.
  <https://github.com/OpenBB-finance/agent-rita>
- No upstream source was copied and no LangChain/Bun/second provider runtime was
  added. Actual tool execution/structured parsing use the installed Agents SDK.
  <https://developers.openai.com/api/docs/guides/function-calling>

## Acceptance

## Conversation UX and finalizer repair (2026-09-07)

- Transcript scrolls independently; composer remains visible. Suggested prompts
  fill (not send) input; help is collapsed until requested. Failed/stopped final
  turns can retry in place without deleting questions or earlier answers.
- Context-load failures have distinct copy from answer-validation failures.
- Finalizer uses reversible run-local Rxxx aliases for completed-read refs.
  Output is decoded before unchanged per-paragraph source/number validation.
  Aliases cannot admit unread refs; no answer-wide citation fallback was added.
- Grounding-review findings identify the rejected paragraph and specific issue;
  one authorized correction gets that candidate and the same actual reads.
  Original analysis prose and duplicate receipt outputs are omitted from repair.
- Canonical-to-display Episode navigation reuses the existing Synthetic identity
  mapping and also checks the owned visible Episode catalog. Evidence IDs stay
  canonical. Real-account IDs remain unchanged.
- Phase progress is real; this is not unchecked token-by-token prose streaming.

## Verification scope

Offline tests cover on-demand tools, prose/JSON failure, fake/unread refs, scope,
grounding rejection/correction, exact episode guides, cancellation, and V1 support.
They do not establish live model answer quality.

`scripts/qa_account_conversation.py` runs only the registered Synthetic showcase
through the existing DeepSeek factory. Three turns cover weight denominator,
local loss versus account performance, and an exact chart guide. Optional
`--keychain` uses the existing desktop credential in memory; it does not print or
persist credentials, prompts or full raw responses. Synthetic rendered answers
and bounded Synthetic numeric-binding diagnostics are printed for review.

Not part of this change: new financial formulas, new counterfactual methods,
external market APIs, unrestricted browsing/SQL/shell, additional Agent framework,
long-term learning or unverified token-by-token financial prose.
