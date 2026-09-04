# Self vs Past Core v1

## Purpose

Self vs Past is a deterministic derived comparison layer. At `as_of = T`, it
compares one current, already-proven metric state from `TwinSnapshot@T` with
valid observations from the same subject's existing `HistoricalMetricSeries`.

It answers: “Where is the current value relative to my own recorded history?”

It is not a financial metric engine, peer benchmark, personality assessment,
skill score, recommendation, anomaly score, prediction, or causal attribution.
It never changes Replay, Evidence, Historical Series, Episode, or Twin facts.

## Truth hierarchy

```text
Replay / Evidence / HistoricalMetricSeries
                    ↓
              TwinSnapshot@T
                    ↓
       SelfBaselineComparison / Summary
```

The Self layer receives values; it does not rebuild HHI, Turnover, portfolio
state, returns, PnL, or any Decision Evidence.

## Windows

`rolling_12m` is the default product baseline: the distribution of the user's
eligible recorded observations during the previous twelve calendar months.
It is not a time-weighted description of where the portfolio spent most of its
time.

`rolling_3m` is recent context only. It does not mean “improved,” “worsened,” or
“more predictive.”

`lifetime` is long-run recorded context only. It is not a lifetime skill score.

Window membership is defined against the exact `TwinSnapshot.snapshot_at`:

- `rolling_3m`: `[T - 3 calendar months, T)`
- `rolling_12m`: `[T - 12 calendar months, T)`
- `lifetime`: all eligible observations `< T`

The lower calendar boundary is inclusive. The upper boundary is exclusive.
Three months never means 90 days and twelve months never means 365 days.
`pandas.DateOffset(months=...)` implements the versioned calendar rule.

The observation selected as the Twin's current state is also explicitly
excluded if its timestamp is earlier than `T`; a current observation can never
enter its own historical baseline.

## Explicit metric eligibility

Self baseline metrics are opt-in through `SelfBaselineMetricDefinition`.
Nothing iterates over all Evidence and assumes it is comparable.

| Metric | Source method | Observation kind | Observation unit | Actual cadence | Minimum valid N | Windows |
|---|---|---|---|---|---:|---|
| `portfolio_concentration_hhi` | `hhi_security_weights_v1` | `state_snapshot` | one deterministic portfolio-state snapshot | supplied complete market-price observation dates | 3 | 3m, 12m, lifetime |
| `mean_daily_turnover` | `pyfolio_portfolio_value_turnover_v1` | `window_statistic` | one existing calendar-day portfolio-value turnover ratio | supplied complete market-price observation dates | 5 | 3m, 12m, lifetime |

These N rules are transparent v1 product eligibility thresholds, not claims of
statistical significance. HHI needs at least three states to describe a center
and range. Turnover needs at least five existing daily observations because its
unit is a daily window statistic rather than a state snapshot.

The Turnover series retains the existing metric ID for compatibility, but each
historical point is the already-produced `daily_turnover` observation. Self v1
does not recompute a rolling or period mean.

## Observation cadence correctness

Both eligible series preserve the cadence actually represented by the supplied
Market Data Contract rows. They do not create a daily calendar or business-day
schedule.

HHI history asks the existing HHI Evidence builder for a point-in-time state on
each supplied relevant market-price date after the first execution. A date that
is absent from the source has no HHI point and receives no statistical weight.
A represented date with an incomplete multi-asset price panel produces an
insufficient point; it is not filled from another date. Consequently, HHI Self
baseline is an **observation-weighted sampled-state distribution**, not a
time-weighted distribution and not a claim about where the portfolio spent
most of the period.

Turnover history reuses the existing `daily_turnover` tuple exactly. One point
exists for each supplied date in the complete replay market-price panel. If
that represented date has no trades, the existing deterministic Evidence emits
an explicit zero traded value and zero turnover. A wholly absent date is not
silently inserted as zero. An incomplete represented multi-asset date causes
the source Evidence to fail closed rather than fill prices.

Therefore cadence can be irregular for either metric. Provenance records the
observation kind, unit, and cadence, while limitations state the corresponding
observation-weighted interpretation. Minimum N counts valid observations under
that cadence; it is a product eligibility threshold, not elapsed-day coverage
or statistical significance.

## Unsupported metrics

Loss-state Addition and Disposition are event / eligible-event statistics and
do not yet have a frozen, same-unit `HistoricalMetricSeries`. Selection,
Sizing, Exit, and Friction are Decision Evidence whose numeric values cannot be
treated as state snapshots. They return `unsupported_for_self_baseline` when
explicitly supplied; they are never auto-enrolled.

Supporting any of these later requires a separately versioned event aggregation
method and its own observation-unit contract. Core v1 does not invent one.

## Descriptive statistics

The primary historical description is median, P25, and P75. Arithmetic mean is
not used as the default because personal histories can be skewed, contain
outliers, and have uneven activity.

Quantiles use NumPy's explicitly selected linear method:

```text
quantile_method = numpy_quantile_linear_v1
numpy.quantile(values, [0.25, 0.5, 0.75], method="linear")
```

The explicit `method="linear"` prevents a dependency default change from
silently changing the contract.

Self historical percentile uses a separate empirical mid-rank convention:

```text
(count(history < current) + 0.5 × count(history == current)) / N × 100
percentile_method = empirical_midrank_percentile_v1
```

It is deterministic under ties and is deliberately named differently from the
Peer percentile method.

`delta_from_median = current_value - historical_median` is only a descriptive
difference between supplied values; it does not reconstruct either metric.

## Comparison bands and interpretation

- `below_historical_iqr`: current `< P25`
- `within_historical_iqr`: `P25 <= current <= P75`
- `above_historical_iqr`: current `> P75`

The bands contain no good/bad, safe/risky, rational/irrational, skill, advice,
or behavior diagnosis. They only locate the current value relative to the
subject's own recorded interquartile range.

## Insufficient history and abstention

Only finite, non-null points with `evidence_status == "complete"` contribute to
statistics. Insufficient points remain visible in the historical series
identity/provenance but are excluded from `valid_n`.

If the current state is absent/incomplete or valid history is below the
metric-specific threshold, status is `insufficient_self_history`. The result
retains `valid_n` and a reason, while median, P25, P75, percentile,
delta-from-median, and comparison band remain `None`. Missing history is never
represented as zero or a directional claim.

## Availability and no-future-data

Every selected historical point must resolve to same-subject Evidence with the
same metric and method binding. Its Evidence availability is evaluated with the
existing `evidence_available_at` rule. A point whose source Evidence is only
available after `T` is not visible to `SelfComparison@T`.

The builder ignores observations and Evidence after `T`. Consequently, adding
future executions, market prices, later Episode closes, later-completed fixed
windows, or later historical points cannot alter the value, canonical bytes,
or identity of a previously built `SelfComparison@T`.

Self does not forward-fill, backfill, substitute current prices, or rebuild a
missing historical point.

## Correction and version semantics

Future new data and historical corrections are different:

- Future new data occurred or became available after `T`; it cannot change
  `SelfComparison@T`.
- A formal correction changes data/version identity for facts that were part of
  the historical input. Rebuilding from that corrected version produces a new
  deterministic comparison identity, even when descriptive values happen to be
  numerically equal.

Core v1 freezes this identity behavior but does not add a revision database.

## Provenance and deterministic identity

Every comparison retains:

- current source Evidence reference;
- cutoff-specific Historical Series reference;
- historical point Evidence references considered in the window;
- source metric method/version;
- source observation kind, unit, and actual cadence;
- Self comparison method/version;
- quantile and percentile method IDs;
- Twin input version references;
- exact `as_of`, window, valid N, data tier, and limitations.

`comparison_id` is a SHA-256 identity over canonical JSON containing the
subject, metric, cutoff, window, current source, eligible historical inputs,
method versions, and input versions. Semantically unordered Evidence and series
collections are canonicalized. Future-only facts are excluded before hashing.

## Summary contract and Twin integration

`SelfBaselineSummary` groups each explicitly supplied metric's three window
comparisons, declares `rolling_12m` as the default, and counts complete versus
insufficient default-window metrics. It contains no natural-language diagnosis.

Personal Twin Core v1 keeps `self_baseline_refs = ()`. This task does not mutate
Twin schema, backfill `notable_changes`, or modify any current financial fact.
A later integration can persist accepted Self comparison IDs and reference them
from a newer Twin projection version.

## Current limitations

- Only HHI and daily Turnover historical series are eligible.
- Calendar coverage is represented by observed points; v1 does not infer
  missing-day coverage or statistical confidence.
- Uneven observation cadence is preserved. Each point receives one descriptive
  vote according to its registered observation unit.
- No event aggregation, trend detection, notable-change ranking, Peer context,
  Agent interpretation, or frontend is included.
