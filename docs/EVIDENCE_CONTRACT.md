# Unified Evidence Contract v1

## 1. Fact Layer vs Evidence Layer

The Fact Layer remains the existing frozen deterministic system: normalized
executions, vectorbt portfolios, InvestmentEpisode, and the existing Decision
and Behavior Evidence dataclasses. It owns financial calculation semantics.

The Evidence Layer does not recalculate those facts. It maps an existing frozen
evidence object into one stable `EvidenceRecord` for UI, chart, and Agent
consumers. `DecisionEvidenceStatistics` remains distinguishable through
`evidence_kind="aggregate_statistics"`; it is not treated as one decision.

## 2. EvidenceRecord schema

`EvidenceRecord` is a frozen, slotted dataclass with:

- identity: `evidence_id`, `subject_id`, `metric_id`, `evidence_kind`
- method: `method_id`, `method_version`
- time: `observation_start`, `observation_end`, `as_of`
- result: `value`, `numerator`, `denominator`, `observation_count`
- interval: `ci_lower`, `ci_upper`
- status: `evidence_status`, `evidence_reason`
- lineage: `provenance`, `data_tier`, `calculation_code_version`
- interpretation: `limitations`, `attributes`

Missing facts remain `None`; adapters do not replace absence with zero.
`attributes` and provenance attributes are validated as JSON-safe and deeply
frozen.

The immutable project schema version used by identity generation is
`EVIDENCE_SCHEMA_VERSION = "1"`.

## 3. Evidence ID identity payload

`evidence_id` is `ev_` plus the SHA-256 digest of canonical JSON bytes. The
bounded identity payload contains:

- schema version
- subject, metric, and evidence kind
- method ID and method version
- calculation code version
- observation start/end and as-of time
- stable provenance identity
- value, numerator, denominator, observation count, and status
- adapter-selected identity attributes

Provenance identity includes source type/name, data version, as-of, price type,
synthetic flag, and available source/instrument/benchmark identifiers.
Descriptive provenance attributes, limitations, display names, and arbitrary
future presentation fields are intentionally excluded. Each adapter explicitly
selects identity attributes, so adding a display-only field does not silently
change every ID.

## 4. Canonicalization strategy

The project-local canonicalizer:

- accepts JSON scalars, string-keyed mappings, and sequences only
- rejects dataclasses, pandas timestamps, non-string keys, and non-finite floats
  inside attributes
- recursively sorts mapping keys
- preserves array order
- emits compact UTF-8 JSON with no insignificant whitespace

This borrows the deterministic canonical JSON concept from
[RFC 8785 / JCS](https://www.rfc-editor.org/rfc/rfc8785.html) and the
[Trail of Bits Python implementation](https://github.com/trailofbits/rfc8785.py),
but it is **not** a complete RFC 8785 implementation. In particular, it does not
claim JCS's ECMAScript number serialization or UTF-16 property ordering. No new
canonicalization dependency is installed.

## 5. Method Registry

`MethodDefinition` separates method specification from registry metadata:

- spec: method ID/version, source, sample basis, limitations
- metadata: producer, registry revision, deterministic spec digest, evidence
  kind, module

The registry contains the four Behavior methods and five existing Decision or
aggregate methods. Definitions are queryable by `(method_id, method_version)`.
Behavior modules retain their existing `METHOD_ID`, `METHOD_SOURCE`,
`SAMPLE_BASIS`, and `LIMITATION` constants.

This borrows Feast's central metadata catalog and its separation of
user-specified `spec` from system-populated `meta`; it does not claim Feast
Registry compatibility. See the
[Feast Registry design](https://github.com/feast-dev/feast/blob/master/docs/getting-started/components/registry.md).

## 6. Provenance

`EvidenceProvenance` expresses source type, source name, data version, as-of,
price type, synthetic flag, optional identities, and JSON-safe attributes.
Adapters preserve existing `PriceProvenance`, `BenchmarkProvenance`, and
`IndustryProvenance` without modifying those frozen source types.

The design borrows OpenLineage's explicit producer/provenance and immutable
schema-version concepts, without claiming OpenLineage facet compatibility. See
[OpenLineage Facets](https://openlineage.io/docs/spec/facets/).

It also borrows MLflow Dataset's separation of source, digest, schema, and
profile: evidence identity is a digest, provenance describes the source, and
business detail stays outside the identity core. It does not claim MLflow
Dataset compatibility. See [MLflow Dataset Tracking](https://mlflow.org/docs/latest/dataset/).

Adapters do not invent missing lineage or time facts. Current Sizing,
Friction, and aggregate Statistics objects carry no source provenance, so their
unified provenance tuple is empty. Current Disposition evidence carries no
sale-window timestamps, so its unified observation start/end/as-of remain
`None`.

## 7. Status

Supported unified statuses are:

- `complete`
- `partial`
- `insufficient_evidence`
- `experimental`

Existing Selection statuses pass through unchanged. The aggregate-only
`DecisionEvidenceStatistics.evidence_status="available"` maps to unified
`complete`, while the original `available` value is retained in attributes.
Its `insufficient_evidence` status passes through unchanged.

## 8. Data tier

Supported tiers are:

- `synthetic`
- `demo`
- `authorized_beta`
- `production`

The caller must choose the tier explicitly for every adapter call.

## 9. Synthetic safety

If any provenance has `is_synthetic=True`, only `synthetic` or `demo` is
allowed. `authorized_beta` and `production` raise `ValueError`; the contract
never silently downgrades the requested tier.

## 10. Adapter philosophy

Adapters copy deterministic source fields only. Complex source structure such
as turnover observations, weights, benchmark comparisons, episode IDs,
disposition counts, and loss-averaging events is converted into JSON-safe
attributes. Timestamps inside attributes become ISO 8601 strings. No adapter
replays a portfolio or computes PnL, returns, TWR, comparisons, confidence
intervals, or new financial metrics.
