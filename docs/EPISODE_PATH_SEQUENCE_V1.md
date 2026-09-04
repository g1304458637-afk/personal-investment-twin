# Episode Path & Sequence Intelligence v1

Path Intelligence sits above frozen Replay and Outcome. It does not store a
second market catalog, invent a second PnL calculator, or rewrite Episode
lifecycle. Frontend adapters display backend facts; they do not group phases,
detect market moves, or compute drawdown.

## Lifecycle vs display

The **Episode lifecycle window** is unchanged: `opened_at` through `closed_at`
or `analysis_as_of`. It is defined by `PositionEpisode`.

The **market-context display window** is derived: pre-entry observations, the
holding-period path, and optional post-exit observations. Completeness of those
windows never invalidates a valid Episode.

Default windows count **valid daily observations**, not trading-calendar days:

- Pre-entry: up to 20 rows with `date < opened_at.normalize()`
- Episode: observations on the holding path
- Closed post-exit: up to 20 rows with `date > closed_at.normalize()`

Status is separate for each window (`pre_entry_context_status`,
`episode_context_status`, `post_exit_context_status`):

- 0–1 observations: `insufficient`
- 2 through requested−1, when a requested count exists: `partial`
- requested count reached: `complete`
- Episode window uses `requested=None`, so 2+ observations are `complete`

Post-exit is labelled **退出后市场路径**. It is display-only. It does not enter
`PreDecisionMarketMove`, Pattern detection, or phase counterfactuals.

## No-lookahead

Daily close has no `available_at`. Same-day close is not treated as known at a
Decision time. Timed fills and date-only fills use the same rule:

- observations used for a decision D satisfy `observation.date < D.calendar_date`
- the move between previous decision P and D uses
  `P.calendar_date < date < D.calendar_date`

Gaps stay gaps. There is no forward-fill or interpolation.

OPEN has no chase or bottom-fishing label. Pre-entry is a neutral
`PreEntryMarketContext` (start, end, count, change, return) for visualization.

## Decision phases

Grouping is analytical over already-sorted Decision events
(`event_time` + `execution_sequence`):

- `entry`: one `open_position`
- `scaling_in`: consecutive `add_position`
- `scaling_out`: consecutive `reduce_position`
- `exit`: one `close_position`, never merged into `scaling_out`

Executions are not merged or VWAP-normalized. Inter-decision market movement is
a `DecisionIntervalObservation` on the path, not a user Decision.

## Patterns

Versioned observations with facts, no psychological enum, and no score:

- `consecutive_scaling_in` / `consecutive_scaling_out`
- `add_after_positive_market_move` / `reduce_after_negative_market_move` /
  `exit_after_negative_market_move`
- `loss_state_addition_reused` (existing Evidence, not recalculated)
- `high_quantity_during_daily_price_drawdown`
- `price_following_scale_sequence`

v1 does not invent a 3% / 5% / 10% chase threshold. UI language stays at
“after the previous decision, the recorded market path rose X%, then an add
occurred.”

Quantity at a daily observation is taken from `ReplayPositionState` only when
the observation date is **not** an execution date. Same-day extremes are
`ambiguous` / `unavailable`, not guessed.

## Phase counterfactual

Primary scenario: `omit_decision_phase_until_next_decision_v1`.

The Path layer omits every execution in a `scaling_in` or `scaling_out` phase
and calls the generic Outcome helper `evaluate_omit_executions_counterfactual`.
`decision_outcome.py` does not import `src.path`. The alternative is one
vectorbt replay of the whole phase, not the sum of single-event differences.

Local horizon is the next Decision after the last phase event, or
`analysis_as_of` when the Episode is still open. Entry is not a primary UI
counterfactual. Full-episode `omit_phase_preserve_later_executions_v1` is
research-only.

## Presentation

Backend `presentation_items` ranks 3–6 items. There is no good/bad score and no
materiality threshold. Desktop `selectPrimaryPathItems` only reads that list.

Long no-execution intervals are `DecisionIntervalObservation` or a trailing
open-hold observation, plus an optional `long_no_execution_interval` pattern.
They are never a Decision Phase and never a user “hold decision.”

## Duration

`PositionEpisode.duration_days` is calendar duration:

`(end.normalize() - opened_at.normalize()).days`

with `duration_kind` `final` (closed) or `so_far` (open). Path does not invent
trading-day counts. Observation counts are labelled **valid daily market
observations**.

## Daily chart zoom

Minimum zoom is derived from daily observations: at least 5 distinct daily
observation timestamps when the series has that many points. ECharts
`minValueSpan` uses the densest 5-observation calendar span, and a clamp expands
sparse/holiday windows so a single isolated observation is not treated as
enough. The axis `minInterval` is one calendar day, so the domain cannot enter
an hour-level view. Price and quantity charts share the same daily domain.
Zoom never changes Path, Pattern, or Counterfactual inputs.

## Long-horizon limitations

v1 Path analysis is bounded as follows:

- daily market observations only; no intraday path
- no official trading calendar
- no corporate-actions engine
- no FX accounting
- no short/margin
- no Decision Journal
- no Agent
- no stop-loss historical scenario
- no user-selected historical exit-date scenario
- PyInstaller cold-start maturity debt remains
- current online market provider is not yet implemented

## Journal / Agent roadmap

Not implemented in v1.

Next: a Decision Journal for what the user believed at the time (why, evidence
used, worry, expectation, planned exit, notes).

Later: an evidence-grounded Agent that reads Path, Phases, Patterns, Outcomes,
Counterfactuals, Evidence, and Journal. The Agent must not calculate financial
facts, draw phases, invent patterns, search for a best historical point, or
give future buy/sell advice.
