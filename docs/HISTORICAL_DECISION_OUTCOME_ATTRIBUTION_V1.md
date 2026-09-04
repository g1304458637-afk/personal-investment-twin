# Historical Decision Outcome Attribution Core v1

## 1. Purpose and boundary

Historical Decision Outcome Attribution organizes already-observed facts into an
auditable answer to two retrospective questions:

1. What accounting or marked result is associated with an existing Position
   Episode and each of its actual executions?
2. Under one explicitly registered historical alternative, how does the result
   change when both paths are replayed by the existing vectorbt engine?

It is not a recommendation engine, forecast, optimizer, target-position model,
tax-lot engine, or psychological explanation. It does not search for a best
entry, exit, quantity, or subset of trades.

The product lifecycle remains `PositionEpisodeLifecycle`. The Outcome layer adds
no second `RoundTrip` or position lifecycle.

## 2. Research and implementation review

| Reference | Implementation reviewed | What it solves | What 投镜 borrows | What 投镜 rejects | Contract impact |
|---|---|---|---|---|---|
| vectorbt 1.1.0 | Installed `vectorbt/portfolio/trades.py`, `portfolio/nb.py`, `portfolio/enums.py`; `Portfolio.orders`, `entry_trades`, `exit_trades`, `positions`; official Trades API documentation and partial-exit examples | Deterministic order replay and authoritative trade/position accounting | PnL, Return, Entry Fees, Exit Fees, Open/Closed status, trade-to-position parent relation | Exposing internal records as the product contract; treating Open exit-like fields as actual exits | Product results carry a stable `AuthoritativeSourceRef`; no PnL formula exists here |
| current 投镜 replay | `src/core/portfolio_replay.py`, `src/behavior/replay_state.py`, replay and average-cost tests | Long-only normalized executions, fixed recorded fees, same-timestamp call sequence, strict prefix state | The only actual and counterfactual replay path | A second cash ledger, cost basis, fee compounding, or ordering policy | Both historical paths preserve the existing replay semantics |
| pyfolio | `pyfolio/round_trips.py`, its extraction tests and round-trip tear-sheet call path | FIFO round-trip grouping and completed-trade summaries | The semantic expectation that a completed lifecycle has PnL, return, duration, and transaction traceability | Its FIFO transaction matcher and PnL calculation | Existing Position Episode remains the only product lifecycle; vectorbt remains the accounting source |
| Portfolio Performance | `Trade.java`, `TradeCollector.java`, `TradeDetailsView.java`, `TradesTableViewer.java` | Closed-trade reporting tied back to original transactions | Results must retain execution and decision references | Its accounting-specific trade reconstruction and UI model | Episode Outcome retains all contributing execution and decision refs |
| Essentia Decision-Based Attribution | Published decision-attribution taxonomy | Separates selection, entry, sizing, scaling, adjusting, and exit decisions | Decision results should attach to actual decision types | Skill scores, behavioral alpha, predictive ranking, and recommendations | Relation types distinguish mechanical, accounting, follow-up, baseline, counterfactual, and statistical claims |
| existing 投镜 Sizing / Exit | `src/attribution/sizing_evidence.py`, `exit_timing_evidence.py`, adapters and tests | Frozen equal-weight sizing comparison and fixed-window post-exit evidence | Registered evidence is referenced when its method already answers the question | Recalculating either baseline inside Outcome | v1 reuses Exit Evidence by `evidence_id`; it does not turn post-exit asset return into user PnL |

Source references used during the audit:

- vectorbt Trades API: <https://vectorbt.dev/api/portfolio/trades/>
- Essentia decision-based analysis overview:
  <https://www.essentia-analytics.com/performance-attribution-decision-based-analysis/>

## 3. PnL truth source and record mapping

The fixed project adapter accepts at most one execution per `(event_time,
symbol)`. It preserves DataFrame row order among different symbols sharing a
timestamp. Under that bounded contract, a SELL execution can be mapped without
ambiguity to one closed vectorbt Exit Trade by:

`Column == symbol` and `Exit Timestamp == event_time`, followed by exact checks
of Size, Avg Exit Price, and Exit Fees.

| 投镜 object | vectorbt authoritative record | Mapping key and validation | Cardinality in the current contract | Safe product use |
|---|---|---|---|---|
| Execution | Order | symbol + timestamp; side, size, price, fee must match | 1:1 | Executed facts and recorded fee |
| BUY Decision Event | Order; it also contributes to Entry Trade and Position aggregation | Order mapping above | Order is 1:1; the execution can also participate in later aggregate records | State transition only; no invented realized PnL |
| Partial SELL Decision Event | closed Exit Trade | symbol + exit timestamp; size, exit price, exit fee must match | 1:1 under the current unique symbol/timestamp replay contract | Realized PnL, Return, allocated Entry Fees, Exit Fees |
| Final SELL / `close_position` | closed Exit Trade, and closes the containing Position | same Exit Trade mapping plus existing Episode lifecycle boundary | SELL→Exit Trade is 1:1; multiple Exit Trades→one Position | Event realized result from Exit Trade; Episode result from Position |
| Open Episode | Open Position | symbol + Episode opening timestamp | one Position per Episode; Position aggregates all entry/exit trades so far | Marked PnL/Return only, never final realized PnL |
| Closed Episode | Closed Position | symbol + Episode opening timestamp; status must match lifecycle | one Position per Episode; many Exit Trades may aggregate into it | Final Episode PnL, Return, entry/exit fees |

A single execution therefore may participate in several representations: its
Order, an Entry or Exit Trade, and the aggregate Position. Those are not
duplicate product results. The Outcome record identifies the exact authoritative
record used for each claim.

### Authoritative fields

- Execution facts and per-order recorded fee: Order `Size`, `Price`, `Fees`,
  `Side`, and `Timestamp`.
- SELL realized result: closed Exit Trade `PnL`, `Return`, `Entry Fees`, and
  `Exit Fees`.
- Episode result: Position `PnL`, `Return`, `Entry Fees`, `Exit Fees`, and
  `Status`.
- Open valuation time and price: the replay's final legal close index and close
  value, passed into the existing `InvestmentEpisode` adapter explicitly.

For an Open Trade or Open Position, vectorbt's readable `Exit Timestamp` and
`Avg Exit Price` are mark-to-market fields. They are not evidence that a real
exit occurred. The product maps them only through explicit `valuation_at` and
`valuation_price`; the Episode remains Open. Exit Fees on an Open aggregate can
include fees from actual partial sells already completed, but it is not a fee
for the current mark.

If a SELL ever maps to zero or more than one matching closed Exit Trade, or its
size/price/fee differs, the mapping raises `OutcomeAttributionError`. The module
does not fall back to `(price - cost) * quantity` or any other handcrafted PnL.

## 4. Relationship semantics

The internal relation taxonomy controls future narrative verbs:

- `deterministic_state_transition`: an execution mechanically changes existing
  replay state.
- `accounting_realized_result`: a completed SELL/Position has an authoritative
  realized accounting result.
- `marked_position_result`: an Open Position has an authoritative as-of mark,
  not a realized result.
- `historical_market_followup`: a later observed market path; temporal sequence
  alone is not causality.
- `registered_baseline_comparison`: an existing frozen Evidence method is
  referenced.
- `historical_counterfactual`: two replay paths differ only by the registered
  intervention and stated assumptions.
- `statistical_association`: a behavioral statistic, not mechanical causality.

These identifiers are system semantics, not mandatory headline copy.

## 5. Actual outcome contracts

### EpisodeOutcome

An Episode Outcome contains stable IDs, subject/account/instrument ownership,
Open/Closed status, `analysis_as_of`, the authoritative `OutcomeResult`, all
Decision Event refs, all contributing execution refs, duration and duration
kind, method/code versions, provenance, and limitations.

For a Closed Episode its result is `realized` and comes from a closed vectorbt
Position. For an Open Episode it is `marked` and comes from an open vectorbt
Position with an explicit legal valuation time and price.

### DecisionImmediateOutcome

Each actual Decision contains:

`before replay state → authoritative Order execution → after replay state`

It embeds only the small immutable state view needed for stable product use:
quantity, average cost, and flat/open status. Each state also retains the
original `ReplayPositionState.state_id`.

A SELL additionally references one authoritative closed Exit Trade and copies
its realized PnL/Return/fees. A BUY has `immediate_result = None`; it never
creates immediate realized profit or loss. `episode_result_ref` points to the
corresponding `EpisodeOutcome`, which in turn points to its Position record.

## 6. Result kind, basis, and comparison

`OutcomeResult.result_kind` is one of:

- `realized`: completed accounting result;
- `marked`: current/historical valuation of an Open Position;
- `counterfactual`: result from a registered alternative replay path.

Actual and counterfactual values are compared only if `result_basis` is equal.
v1 replay scenarios use `net_pnl`, including the fixed recorded fees present in
each replayed path. `gross_pnl_before_incremental_friction` is reserved as an
explicit distinct basis; it cannot be compared to net PnL.

The direction is frozen as:

`pnl_difference = counterfactual_pnl - actual_pnl`

A positive difference means the registered historical alternative has a higher
PnL than actual history. Objective transitions such as `loss_reduced`,
`loss_to_flat`, or `loss_to_profit` are arithmetic classifications, not grades
of investor skill.

Only equal-basis net results with actual PnL below zero and counterfactual PnL
at or above zero can support a future phrase such as “this registered historical
alternative would not have remained a loss.” That wording must retain the
counterfactual method and assumptions; it must never become “would surely
profit.”

## 7. Counterfactual scenario registry

Only versioned scenarios in `COUNTERFACTUAL_SCENARIOS` can run. Natural-language
requests cannot directly rewrite an execution sequence.

### 7.1 `omit_event_until_next_decision_v1`

Applicable to Open, Add, and Reduce events. It removes the selected execution
and evaluates actual and alternative paths strictly before the next Decision
Event. Later Episode decisions are outside the replay. If an Open Episode has no
later decision, the horizon is `analysis_as_of` and an exact legal mark must
exist.

The current Market Data Contract is daily. The historical mark is the legal
observation on the evaluation calendar date; it must not be described as a
provably available intraday quote. Missing evaluation-date data returns
`insufficient_counterfactual_data`; no forward fill or interpolation is used.

This is the primary fallback when preserving all later executions is infeasible.

If omitting an opening event leaves no execution at all to replay, the existing
portfolio adapter cannot construct an empty Portfolio. In that one structural
case the counterfactual explicitly records `position_status = absent`, PnL zero,
and Return unavailable, with source kind
`registered_counterfactual_position_absent`. It does not claim that an
authoritative vectorbt Position exists. Every non-empty actual or alternative
path still uses the same vectorbt replay.

### 7.2 `omit_event_preserve_later_executions_v1`

Applicable to Add and Reduce events. It removes only the selected execution and
preserves every later actual execution's timestamp, symbol, side, absolute
quantity, execution price, fee, and ordering. The horizon is the actual Episode
close, or `analysis_as_of` while the Episode remains Open.

If any preserved downstream execution becomes illegal, the result is:

- `feasibility_status = infeasible_downstream_execution`;
- `first_conflicting_execution_id` identifies the earliest rejected order;
- both numerical comparison results are withheld.

No quantity is clamped or proportionally scaled. No later order is deleted. No
remainder is auto-closed, and no replacement behavior is inferred.

### 7.3 `existing_exit_evidence_reuse_v1`

Applicable to `close_position`. It requires same-subject, same-Episode frozen
Exit Evidence available by `analysis_as_of`. The Outcome layer records the exact
`evidence_id`, method horizon, provenance, limitations, and the separate price
basis.

Existing Exit Evidence begins at the exit-session market price, not the average
execution price. Its value is a later asset return. Outcome v1 intentionally
does not transform that return into a hypothetical user PnL, so
`counterfactual_result` and PnL comparison remain unavailable.

## 8. Counterfactual scope decision

Implemented:

- local omit until the next Decision: bounded historical marked comparison;
- full omit while preserving all later absolute orders, only when feasible;
- exact reuse of existing frozen Exit Evidence.

Deferred:

- `close_all_instead_of_reduce_v1`: altered quantity has no frozen execution
  price/liquidity guarantee or deterministic incremental-fee basis;
- proportional downstream resizing: would rewrite actual user behavior;
- clamp/delete/auto-close policies: would silently repair an invalid scenario;
- any optimizer or historical best-action search: incompatible with an auditable
  finite registry and would create hindsight optimization.

## 9. Time, prices, fees, and no-lookahead

The three times are separate:

- `decision_at`: when the actual execution occurred;
- `evaluation_end`: the registered historical comparison horizon;
- `analysis_as_of`: when the retrospective analysis is built.

Executions and market rows after `analysis_as_of` are filtered before replay.
Each scenario additionally truncates market data at `evaluation_end`. A required
mark must exist exactly on the evaluation calendar date. Missing data produces
an insufficient result; it is never filled, interpolated, or replaced by a
current price.

The actual and alternative paths both use recorded execution prices. Omit
scenarios remove the selected execution and its recorded fee; all included
orders keep their recorded fees. Because v1 never changes an order quantity, it
does not need to invent an incremental fee model.

Counterfactual IDs hash subject/account/Episode/event, scenario and method
versions, calculation code version, all times, intervention, held constants,
downstream policy, price and friction bases, and canonical provenance/data
versions. Repeating the same facts produces the same ID.

## 10. Ownership and provenance

Lifecycle subject and account must match the explicit analysis context.
Execution `subject_id`, when supplied, must match. The account's Episode and
Decision execution refs must exactly match authoritative executions through
`analysis_as_of`. Exit Evidence must have the same subject and Episode and must
already be available by the analysis time. Any mismatch fails closed.

Market price rows are reference data governed by the existing Market Data
Contract; they do not claim user/account ownership. Their validated source,
version, price type, synthetic flag, instrument, and as-of are retained as
provenance.

## 11. Hand-calculated regression fixtures

Tests freeze simple expected values independently of the Outcome implementation:

- Buy 100 at 10 with fee 1; sell 40 at 12 with fee 2: the mapped Exit Trade PnL
  is 77.6, including 0.4 allocated entry fee and 2.0 exit fee.
- Buy 100 at 10; sell 50 at 8: the SELL realizes -100 while the Episode remains
  Open.
- Buy 100 at 10; add 50 at 12; mark at 9 before the next Decision: actual marked
  PnL is -250, omit-add PnL is -100, difference is +150.
- Buy 100 at 10; reduce 40 at 9; mark at 8 before the next Decision: actual
  marked PnL is -160, omit-reduce PnL is -200, difference is -40.
- Buy 100 at 10; add 20 at 12; later sell 40 at 15 and 60 at 14; final mark at
  13: actual marked PnL is 460; omit-add closes at PnL 440; difference is -20.
- Buy 100, add 50, then sell 120: omitting the add rejects the unchanged sell
  and reports that sell as the first conflict.

The “full feasible” fixture intentionally leaves 20 actual shares open while the
omit path closes 100 shares. This is the unavoidable consequence of preserving
later absolute quantities. The commonly stated sequence `BUY 100, ADD 20, SELL
40, SELL 60` cannot make both paths end flat; v1 reports the actual states rather
than silently changing the fixture or orders.

## 12. Known limitations and future narrative principles

- Long-only normalized executions only; no short, margin, corporate-action, or
  transfer outcome attribution.
- At most one execution per symbol and timestamp, inherited from the replay
  contract.
- Daily market marks cannot establish intraday price availability.
- No tax-lot explanation beyond vectorbt's authoritative aggregate/exit records.
- Exit Evidence provides later asset performance, not a comparable user PnL.
- No psychological label, skill score, peer rank, forecast, or recommended next
  action.

Future Episode Decision Story UI may state objective accounting facts directly,
for example “this sell realized a loss of X” or “the Open Episode currently has
a marked loss of X.” Counterfactual language must remain conditional on its
scenario, horizon, basis, and held-constant assumptions. The detailed method and
source refs should be inspectable without forcing all caveats into every primary
headline.
