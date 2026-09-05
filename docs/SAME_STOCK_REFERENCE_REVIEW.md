# Deep Decision Analysis: reference review

Research baseline: repository `53dc598`; installed vectorbt 1.1.0 and
openai-agents 0.22.0. References inspected before implementation. No reference
source or visual assets are copied; no new financial engine is introduced.

Local backend references live under `~/Projects/backend-references/`; ECharts
lives under `~/Projects/ui-references/echarts/`.

| Reference / exact inspected source | Useful pattern | Incompatible semantics / not borrowed | Toujing implication | Required adversarial test |
| --- | --- | --- | --- | --- |
| vectorbt, installed `portfolio/base.py::from_order_func/get_exit_trades/get_positions`, `portfolio/orders.py`, `portfolio/trades.py` | Filled orders, exit trades and aggregated Positions are separate authoritative records; flexible replay preserves multiple orders per tick | Backtest signals are not broker executions; open records are not closed results | Independently replay A and B using existing core and map existing outcome records | Same-time sequence; open/closed; result equality to Outcome |
| [Ghostfolio portfolio service](https://github.com/ghostfolio/ghostfolio/blob/main/apps/api/src/app/portfolio/portfolio.service.ts), `getHolding`; local holding-detail template | Scope by user and dataSource/symbol before joining activities, quantity and daily history | FX/performance accounting and first-activity synthetic price fallback; no code reuse | Qualified instrument AND account scope; absent prices fail closed | Same display symbol/different market; currency mismatch; missing price |
| pyfolio `pyfolio/round_trips.py::_groupby_consecutive/extract_round_trips/add_closing_transactions`, `tears.py::create_round_trip_tear_sheet`, `utils.py::check_intraday`, `txn.py::make_transaction_frame` | Separate execution input, lifecycle reporting and chart presentation | Consecutive execution merging/VWAP, inferred intraday state and fabricated closing transaction | Preserve one canonical row per execution; never force-close Open Episodes | Multiple same-time fills; open marked result remains open |
| Wealthfolio `apps/frontend/src/pages/holdings/components/holdings-table.tsx` | Explicit open/disposed display and dense security-oriented detail | Frontend cost/quantity arithmetic and FX fallback; AGPL code not copied | UI consumes replay-derived quantity/cost/result, never computes accounting | Different account sizes must not imply risk ranking |
| Portfolio Performance `name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/panes/TradesPane.java::setInput/createViewControl` | Single-security detail, configurable detail columns, clear stale rows when input changes | TradeCollector grouping and currency conversion; no lifecycle replacement | Selection-scoped detail, clear previous account content on selection/failure | A/B swap; invalid next selection cannot retain old results |
| rotki `frontend/app/src/modules/history/events/HistoryEventsTableActions.vue` | Distinguish exact-event filtering from whole-group filtering and surface scope | Transaction group expansion and unrelated editing/redecode workflows | A fact highlights its actual decisions, not every nearby execution | Fact reference resolves to exact canonical decision |
| ECharts `test/connect-manually.html` | Shared time domain and coordinated pointer events | Random example series and unlimited coupled actions | Existing ECharts runtime; one observed market path, two ordered decision lanes | Equal timestamps, missing daily observations and linked highlight |
| [Anthropic tool-use workflow](https://github.com/anthropics/courses/blob/master/tool_use/06_chatbot_with_multiple_tools.ipynb), `simple_chat`, `process_tool_call` | Model selects tools; application executes; tool_use_id binds returned facts into subsequent iterations | Example prints tool payloads and uses a different provider/runtime; not suitable authorization | Retain OpenAI Agents SDK and existing DeepSeek Responses provider; audit successful scoped calls | Prompt-injection note; missing required tool result; contradictory facts |
| [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling), tool calling flow; installed SDK | Multi-step native tool loop with call IDs and structured outputs | A schema-valid claim is not proof that its cited evidence supports it | Separate tool execution audit, factual value validation and inference grounding | Fabricated numeric claim/ref and outcome-framing invariance |

## Toujing-specific contract decisions

No inspected reference establishes Toujing's cross-subject comparison contract.
Identity, common-window eligibility, normalized position shape and authorization
are **Toujing-specific contracts**, not an industry standard.

Proposed conservative scope: full Episode results stay on their own periods;
the common window aligns observed prices and already-replayed position/decision
facts. It does not create common-window PnL or transplant B's orders into A.
Normalized quantity is only a within-Episode shape view, not portfolio risk.

Current runtime has local subject/account filtering but no authenticated remote
principal or counterpart consent record. Presence of another account in SQLite
must not be treated as authorization. Synthetic pair access and real counterpart
derived-data authorization must remain distinct. The transport and trusted
issuer of real counterpart consent require an explicit boundary before enabling
that product path.
