# Strict pre-decision scenarios v2

This versioned migration leaves the registered v1 scenarios and existing
Evidence unchanged. Exit fixed-window start remains the exit-session market
price, never the average exit execution price.

| Scenario | Valuation basis |
| --- | --- |
| omit_event_until_next_decision_v1 | next-decision-session daily market mark |
| omit_decision_phase_until_next_decision_v1 | next-decision-session daily market mark |
| omit_event_until_next_decision_v2 | strict pre-decision prior daily market mark |
| omit_decision_phase_until_next_decision_v2 | strict pre-decision prior daily market mark |

For a next Decision on calendar date D, executions are a prefix of the existing
canonical replay ordering, excluding that Decision. Same timestamps retain
canonical sequence. Market observations must have date strictly less than D;
the actual last legal observed date is retained across weekends and holidays.
Canonical execution `market_date`, where present, supplies the exchange calendar
date rather than interpreting UTC midnight as an exchange date.

Actual and alternative use the same observed prior mark as their explicit
scenario valuation basis. The existing vectorbt adapter executes unchanged
timestamps, ordering, prices and quantities, omitting only selected fills and
their recorded fees. Mapping this fixed scenario basis to replay steps does not
create daily/intraday observations, fill missing prices or predict prices.
No legal prior observation means insufficient counterfactual data. Conflicting
or invalid prior provenance is not silently repaired.

Results retain `next_decision_at`, `valuation_observation_date`, `scenario_id`,
`scenario_version`, and the existing method identity. A prior-session mark is
not a quote observed intraday on the next-decision date. For an Open Episode
without a next Decision, v2 uses strict availability before the analysis-as-of
calendar date and leaves `next_decision_at` null.

New local product paths select v2. v1 remains explicitly callable. Versions
must never be pooled into a statistical observation series, N, CI or historical
rate. This migration adds no statistical aggregation or migration of stored
Evidence. Serialization of the v1 result shape remains unchanged.

Independent point-in-time correction: Market Context, Market Path and post-exit
display observations are bounded by analysis-as-of calendar date. This is not
a change to the registered Exit fixed-window calculation.
