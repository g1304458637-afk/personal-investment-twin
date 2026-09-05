# Same-Stock Compare v1 — Toujing-specific contract

Method: `same_stock_descriptive_comparison_v1`, version `1`.

## Source and identity

Each side is rebuilt independently using the existing Position Episode,
Decision Outcome and Path builders. The complete account execution prefix is
passed to those builders. Compare adds no accounting, cost, return, phase,
daily-price inference or historical counterfactual formula.

The canonical `InstrumentRef` validates instrument ID against local symbol,
market and security type. Currency must also be present and equal for Compare;
this does not change Canonical v2's rule that currency is listing metadata.
Explicit execution subject/account columns must match the requested owner.

## Three windows and result kinds

A and B retain their complete Episode periods, authoritative net result,
return, recorded entry/exit fees, result kind and source references.
Closed means realized; Open means marked at the recorded valuation point.

The common execution interval is the intersection of Episode timestamps, with
both endpoints included. The shared daily market path uses matching observations
on calendar dates touched by this interval. Daily timestamps remain date labels,
not intraday availability claims. No common-window PnL is created. Position paths
retain their full authoritative state history, including state before the first
execution; a UI crop must never rebuild a flat account at the common start.

## Eligibility

`unavailable`: qualified identity/currency/source tier/as-of mismatch; invalid
ownership/result linkage; nonoverlapping periods; no common market observation;
or conflicting price/provenance on a common date. No shared chart or differences
are emitted in this state. Own full-period facts are not a permission grant to
retrieve or disclose a counterpart.

`partially_comparable`: at least one common observation but only a single point,
different observed date sets, different full periods, or marked/realized mismatch.
Reasons remain explicit. A single observation is never rendered as a trend.

`comparable`: these restrictions do not apply. This status does not mean equal
account size, equal risk, comparable skill or causal explanation.

No exchange calendar is inferred. Identically absent weekend dates are not
invented; differing observation sets are retained as a limitation. Required
execution-day price failures are raised by the existing financial builders.

## Descriptive differences and normalization

Common-window counts use existing DecisionImmediateOutcome event types in
canonical replay order. Difference references include both full Episode outcome
scopes, actual matching decisions and shared market observations. A zero count
is checked absence within that scope, not missing data. Existing Path facts
provide cost paths, legal pre-decision moves and drawdown quantity availability.

Normalized quantity = existing replay quantity / existing Episode maximum
quantity, solely a display shape. The denominator uses the same as-of-limited
Episode path. No portfolio-risk comparison or score is inferred from shares.

## Synthetic hand-check

Dedicated subjects `SYN_COMPARE_A` and `SYN_COMPARE_B`, separate accounts, one
qualified synthetic listing in CNY, daily rise/drawdown/partial-recovery series.
Source: `src/compare/demo.py::pair_inputs`; explicit synthetic tier.

A buys 100×10 + 100×12 + 100×13 = 3500; sells 100×9.5 + 200×11 = 3150;
five recorded fees of 1: net result **−355 CNY**.

B buys 100×10 + 40×11 = 1440; sells 40×13 + 40×11.5 + 60×11 = 1640;
five recorded fees of 1: net result **195 CNY**.

These equations are test expectations, not production calculation. B does not
exit at a hindsight optimum: it continues holding through drawdown and adds
after the trough. Both results are copied from authoritative replay records.

## Permission boundary

Own-account access, specific counterpart sharing and cohort contribution are
different permissions. Compare is a pure backend projection, not an access
control API. Never pass frontend-selected arbitrary counterpart account IDs to
a repository reader.

User-approved transport: counterpart explicitly exports a limited Episode's
derived-fact share package, recipient imports that package; no original CSV or
account-wide execution access. Package authorization must bind the selected
Episode and permitted derived facts. Local file presence alone is not consent.
No production cohort or authenticated online-user service is introduced.
