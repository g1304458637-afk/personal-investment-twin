# Independent account chat and chart guides v1

`/ask` is the independent Ask Toujing workspace. Its default scope is the
currently selected **whole account**. An investment Episode is optional
drilldown, not a required or fabricated account container.

## Existing capabilities reused

- Current account cash/value/holdings: existing vectorbt replay.
- Account performance: registered AccountPerformanceSeries (TWR and drawdown).
- Concentration and turnover: existing behavior Evidence builders.
- Change over time: existing owned self-history builders.
- Investment index and operation drilldown: existing Position Episode lifecycle.

There are no new financial formulas, portfolio engines, peer sources, knowledge
corpora, stock forecasts, exams, or skill scores.

## Runtime boundary

`AgentWorkspace → agentChatService → existing review.context/start/poll RPCs`

An account request adds `scope_kind: "account"` and does not send `episode_id`.
Only `real_user` and `synthetic_showcase` are supported for this scope. Shares,
pair comparisons, other accounts and arbitrary navigation/tool names are not
implicitly authorized. The same existing desktop model configuration and
DeepSeek runtime are used; the UI never reads the credential.

The account analysis loop executes five read-only, scope-bound tools. A separate
tool-free StructuredFinalizer selects registered finding IDs. The backend
validates completed receipts, ownership and selection, then composes displayed
words/numbers from existing deterministic results. Model prose never becomes a
financial fact or the rendered final answer.

## Follow-ups

The frontend sends only `previous_inference_id`, not assistant text. The runtime
resolves the latest owned result with matching source and conversation scope.
At most three previous validated turns help resolve follow-up references; they
do not enter the Evidence allowlist. New tools and validation still run.

Account history lives in the current runtime process. Episode continuation uses
the existing review-inference store, without a schema migration. Frontend
transcripts are session-only, bounded and keyed by exact scope. A refresh or app
restart clears the frontend conversation. This is not a durable chat archive.

Source fingerprints are checked before/after context building and at delivery.
Account configuration, executions and market prices participate. Stale jobs are
terminal, deletion cancels/forgets account work, and old branches cannot become
the current conversation head.

Stopping the UI means **stop waiting**, not a claim that an already submitted
remote request was cancelled. Late results cannot overwrite another scope or
request. Explicit consent is required for every new scoped session.

## Chart guidance

The registered `episode-process`, `pretrade-allocation` and `same-stock` guides
use fixed routes and page-owned anchors. They highlight existing chart areas;
they cannot execute trades, submit simulations, retrieve another account or
accept model-generated CSS selectors/URLs. Chart/decision IDs are checked
against the loaded scope before navigation. Guidance is clearly product help,
not a model-generated financial assessment.

## Browser and desktop

Browser development keeps the independent page and chart guides available and
explicitly labels AI conversation as a desktop capability. It never opens a
Python HTTP service or invents a model reply. The release app packages the new
runtime; an already-running older app must be quit and reopened to load it.

## Verification boundary

Tests use the real deterministic builders and real SDK orchestration with an
offline scripted model. Browser interaction tests use isolated QA-only IPC data.
Packaged-runtime smoke tests use a temporary database and the registered
Synthetic account only. These checks are not paid/live DeepSeek acceptance and
must not be reported as such.


## Annualized volatility delivery (2026-09-09)

The registered synthetic showcase now passes its declared complete weekday
schedule and annualization factor 252 into the existing AccountPerformanceSeries
builder. The same computed volatility, observation count, annualization factor
and schedule provenance reach both the performance summary and daily-path Agent
tools. No financial formula, model-side calculation or fixed output was added.
The existing exact-date and minimum-sample checks still apply. Sharpe remains
unavailable without aligned risk-free returns.

Real accounts still omit DailyRiskPolicy until an authoritative complete daily
schedule can be established. Observed rows alone are not evidence of calendar
completeness, and the synthetic schedule is never applied to real accounts.

Regression coverage verifies actual tool payload delivery through the DSA loop
with an offline scripted model, including number/reference validation. It does
not claim paid/live model quality acceptance. A packaged desktop must load the
rebuilt sidecar; an already saved answer is historical and is not regenerated.
