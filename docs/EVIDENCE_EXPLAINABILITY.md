# Evidence Explainability Core v1

Evidence Explainability v1 is a deterministic read layer over the existing
financial calculators and Evidence Contract. It does not calculate portfolio
facts and does not produce investment advice.

## Four separate layers

| Layer | Responsibility | Not responsible for |
| --- | --- | --- |
| Concept | Stable definition, method/version, unit, mathematical direction, methodology references, and interpretation policy | A result for one investor |
| Calculation Trace | Structured inputs, operations, source references, window, provenance, limitations, and the result already produced by the calculator | Replaying data or evaluating the formula again |
| Evidence | Frozen result, status, numerator/denominator, N, CI, provenance, and deterministic Evidence ID | Natural-language conclusions |
| Interpretation | A future UI or Agent can describe a result only within the Concept policy and only from the Evidence and Trace | Recomputing facts, advice, psychological diagnosis, or unsupported causal claims |

`ConceptDefinition`, `CalculationTrace`, and `EvidenceRecord` therefore remain
different contracts. A single description string cannot replace any of them.

## Trace construction

Calculators expose only the deterministic intermediate components they already
used. Adapters retain those components in the immutable EvidenceRecord. Trace
builders validate the record against its source result and serialize the same
components. A mismatch fails closed.

Current end-to-end trace builders cover:

- Portfolio HHI, including the risky-security values and weights used by the
  existing HHI builder.
- Mean daily Turnover, including each existing daily traded-value,
  portfolio-value, and turnover observation.
- Loss-state Addition, including the replayed pre-trade average cost and the
  actual BUY execution price.
- Sizing actual-versus-equal-weight comparison.
- Fixed-window post-exit market return, including its full validated market
  price window. The Position Episode average exit price is retained as context
  and explicitly excluded from the return formula when the method uses the
  exit-session market series.
- Pre-trade HHI impact, including the existing before/after HHI Evidence IDs.
  The hypothetical execution price and vectorbt valuation mark are separate
  inputs.
- Existing decision statistics, including the already-computed Wilson interval;
  Explainability does not calculate the interval.

An Open Position valuation is a mark, not an exit. A partial SELL is a reduce
decision, not a completed exit. The corresponding source-fact trace helpers
enforce both boundaries.

## Determinism and provenance

Trace IDs are SHA-256 IDs over the canonical trace payload. The identity binds
the Evidence ID (when present), concept and method versions, calculation code
version, inputs, operations, window, source references, provenance,
limitations, status, and result. The same source facts produce the same Trace
content and ID.

Inputs use stable references such as `execution:<execution_id>`,
`evidence:<evidence_id>`, `position_state:<state_id>`, and market observation
references. Raw brokerage account numbers and local filesystem paths are not
part of the user-facing trace contract.

## Insufficient evidence

An insufficient Trace has no invented result and no completed calculation
operation. It retains the existing Evidence reason, a structured required
condition, and the observations that are currently available. The layer never
shortens a policy window, forward-fills a missing price, or uses a future
observation to make an incomplete result look complete.

## Interpretation boundary

Every Concept has machine-readable `allowed_claims` and `prohibited_claims`.
The common prohibited claims include investment advice, buy/sell
recommendations, future-return predictions, and durable skill conclusions.
Behavior concepts additionally prohibit psychological diagnosis and motive
inference. Mathematical directionality may be described—for example, a higher
HHI is mathematically more concentrated—but it is not a judgment that the
portfolio is better or worse.

Explaining a method is not financial advice.

## Market-data limitation

The existing Market Data Contract uses daily dates and does not include an
intraday availability timestamp. The system can exclude future dates, but it
cannot prove that a trading day's final close was already available at an
intraday decision time. Explainability preserves this limitation in applicable
Concept metadata and does not change the Market Data Contract.
