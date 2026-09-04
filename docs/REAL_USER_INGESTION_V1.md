# Real User Ingestion & Data Quality Core v1

Status: implemented core contract. This phase stops at an immutable in-memory
preview and `CanonicalImportBundle`; it has no Desktop UI, persistence, broker
API, market-data provider, or financial calculator.

## Product purpose and minimum-data principle

The purpose is to turn one user-authorized trade CSV into facts the existing
financial core can trust:

`Raw File → Parse → Column Mapping → Raw Row Validation → Normalization → Instrument Resolution → CanonicalExecutionV2 Candidate → Reconciliation → Replay Eligibility / DQ → Import Preview → CanonicalImportBundle`

The adapter imports only what is needed to establish what was bought or sold,
when, in which account, in what quantity and at what execution price, whether
the recorded fee is known, which qualified instrument was involved, and which
ordering evidence exists. It does not mirror every broker field.

Names, phone numbers, full broker account numbers, identity numbers, marketing
fields, and free-form broker notes are not copied to Canonical Execution,
Evidence, Twin, Episode, Outcome, or Agent domains. The in-memory `RawImportRow`
can retain original values for an isolated audit/preview boundary, while its
default serialization omits them.

## Raw versus canonical

`RawImportBatch` identifies the exact input bytes by SHA-256 and records source
type, schema/mapping versions, configured IANA timezone, target subject/account,
row count, and traceable raw rows. File hash and physical row number are raw
audit references; neither alone is a durable financial identity.

`CanonicalExecutionV2` is the financial fact. The importer calls the existing
constructors for instrument, time, fee, execution identity, and replay
eligibility. It knows nothing about vectorbt Orders, Trades, Positions, cash,
PnL, return, cost basis, HHI, or any attribution formula.

## `generic_csv_v1`

This release claims support only for a reviewed generic schema, not for any
named Chinese or international broker export. UTF-8 and UTF-8 BOM are accepted.
Parsing uses standard CSV quoting, commas inside quoted values, empty cells,
LF/CRLF, and normalized headers. GBK/GB18030 is not claimed without a lawful,
de-identified real sample.

Required mapped fields:

- `symbol`
- `event_time`
- `side`
- `quantity`
- `price`

Optional fields:

- source account (must agree with the explicit target account)
- `market`, `security_type`, `currency`
- `fee`
- source execution ID and source order ID
- execution sequence and time precision

Market and security type may be absent so the row remains a canonical
unresolved fact, but it is then blocked from replay. Missing fee similarly
remains an unknown FeeFact. Required means “required to describe a candidate,”
not “required for exact replay.”

## Column mapping

`ColumnMapping` is versioned. The built-in aliases are finite and exact after
case/whitespace/separator normalization. Examples include `symbol/ticker/code/证券代码`,
`quantity/qty/shares/成交数量`, and `price/unit_price/executed_price/成交价格`.
There is no fuzzy, substring, or LLM mapping.

If two headers are aliases for one canonical field, the adapter returns
`ambiguous_column_mapping`. An explicit mapping can resolve it. Unknown columns
are ignored by canonical normalization and remain only in the isolated raw row.

Raw side aliases are limited to `BUY/buy/买入` and `SELL/sell/卖出`. “加仓”、
“减仓”、“建仓”、and “清仓” are replay-derived decision semantics, not source
execution facts. Quantity and execution price must be finite and positive;
negative quantity never encodes SELL.

## Instrument resolution

Identity follows Canonical v2: normalized `local_symbol + market +
security_type`. Currency is non-identifying metadata. Generic CSV never turns a
naked `000001` into SZSE. Missing qualifiers produce `unresolved_instrument`.
Multiple explicitly supplied resolution candidates produce
`ambiguous_instrument`. Both remain visible in preview and in an accepted
canonical bundle, but exact replay is blocked.

The small `confirmed_instruments` input is an explicit resolution result, not a
security-master heuristic. Corporate actions, symbol history, mergers, and
durable security-master persistence remain deferred.

## Timezone and precision

The importer delegates to the Canonical v2 time contract:

- offset-aware timestamps retain their source offset and normalize to UTC;
- naive timed values require an explicit IANA `source_timezone`;
- ambiguous/nonexistent DST local values fail closed;
- date-only values carry `precision=date`, `instant_utc=None`, and never invent
  midnight or market-close time.

The generic configuration or an explicit time-precision column establishes
precision. Machine-local timezone is never consulted.

## Ordering and same-time fills

Execution identity and result-affecting order are separate. An explicit source
sequence is preserved with `sequence_source=source_execution_sequence`. Source
row order is used only when the caller explicitly declares it to be source
ordering evidence. It is never silently inferred.

More than one execution in an account at the same Canonical v2 time key must
have unique sequences. Otherwise every affected candidate remains visible but
gets `ambiguous_execution_order` and exact replay is blocked. Fills are never
merged, averaged, overwritten, or dropped.

Two source rows can describe genuinely different fills even when time,
instrument, side, quantity, price, and fee are identical. Without a source
execution ID, the importer assigns deterministic occurrence identities within
the exact content-fingerprint group. A stable source order ID, or otherwise an
explicit source execution sequence, disambiguates identical occurrences from
physical CSV order; truly indistinguishable occurrences retain multiplicity by
count. It preserves fills instead of deduplicating by economic fields.

## FeeFact

CSV fee semantics map without repair:

- positive finite amount → `known_nonzero`
- literal zero → `explicit_zero`
- blank cell or absent fee column → `unknown`

An unknown fee is accepted into preview and bundle, and reported as a warning.
It is never changed to zero and never enters exact/net replay. Negative or
non-numeric nonblank fees are invalid.

## Execution identity and reconciliation

A stable source execution/trade ID has highest confidence. Canonical execution
identity uses source namespace, subject/account ownership, and source execution
ID. A changed result-affecting fact under the same ID is
`conflicting_revision`; it is never overwritten.

Without a source ID, the deterministic fingerprint includes subject/account,
qualified instrument, normalized source-local time semantics, side, quantity,
price, FeeFact, and source adapter/schema version. Presentation metadata and
file SHA/row number are excluded. Execution sequence is an ordering fact, not
the base content identity. A deterministic occurrence suffix preserves
field-identical fills.

## Targeted reference review

- Ghostfolio's client importer uses finite header alias lists and maps external
  rows to a smaller activity DTO; its server performs validation and dry-run
  import separately. We borrow the external-schema-to-canonical boundary, not
  Angular, NestJS, Prisma, provider lookup, or its portfolio accounting.
- Actual Budget separates `addTransactions` from `importTransactions`, exposes
  `dryRun/isPreview`, gives stable `imported_id` stronger matching semantics,
  and returns reconciliation previews. We borrow preview plus stable-ID
  reconciliation, not its database mutations or fuzzy bank-transaction rules.
- Rotki validates IANA timezone names and applies a configured zone to naive
  timestamps while respecting aware offsets and normalizing to UTC. We reuse
  this contract through Canonical v2 and deliberately do not inherit any
  default-to-UTC behavior.
- Portfolio Performance keeps security identity separate from display fields,
  resolves across several identifiers, and surfaces duplicate/ambiguous
  security conditions. We borrow fail-closed resolution and row-level import
  errors, not Java models, automatic security creation, quote feeds, or FIFO.

Reconciliation states are:

- `new_execution`: candidate can enter the bundle;
- `exact_duplicate`: proven existing fact, informational and not re-added;
- `possible_duplicate`: similar but not proven, held for user confirmation;
- `conflicting_revision`: same stable source ID with changed facts, blocked;
- `invalid`: no canonical candidate.

The same byte-identical file is recognized by file SHA and independently by
row-level reconciliation. Overlapping exports reconcile their old source IDs
and add only the unseen tail. Similarity alone never deletes a fill.

## Import Preview and data quality

`ImportPreview.as_dict()` is a stable, JSON-safe boundary for future Desktop
work. It exposes total rows; accepted/new, duplicate, possible-duplicate,
conflict, invalid, blocking and warning counts; replay eligible/blocked counts;
instrument and fee issue counts; date range; accounts; instruments; structured
batch issues; and every row's status, normalized candidate, issues, and matched
existing execution ID.

Issues store code, severity, row reference, field, and structured message
parameters. Frozen v1 codes include:

- `missing_required_field`, `invalid_side`, `invalid_quantity`,
  `invalid_price`, `invalid_fee`, `invalid_timestamp`, `timezone_required`
- `ambiguous_execution_order`, `unknown_fee`, `unresolved_instrument`,
  `ambiguous_instrument`
- `exact_duplicate`, `possible_duplicate`, `conflicting_revision`
- `unsupported_short_or_margin`, `replay_ineligible`,
  `missing_market_data`, `ambiguous_column_mapping`, `account_mismatch`

Severity is `error`, `warning`, or `info`; there is deliberately no aggregate
data-quality score. Invalid quantities/prices are errors. Unknown fee is a
warning with analytics blocked. Exact duplicate is info. Missing market data
does not invalidate the execution fact.

## CanonicalImportBundle

The immutable bundle contains:

- deterministic bundle ID and schema version;
- subject/account ownership;
- stable source adapter/schema/mapping reference;
- only accepted `new_execution` CanonicalExecutionV2 facts;
- qualified or unresolved instrument refs;
- DQ, duplicate, and replay eligibility summaries;
- daily `MarketDataRequirement` values;
- explicit limitations.

Invalid, conflicting, possible-duplicate, and already-imported rows are not
replay input. Unknown-fee and unresolved-instrument facts remain in the bundle
as accepted facts but are counted as replay blocked. The bundle sorts facts by
canonical time, explicit sequence, and execution identity. Its canonical JSON
is byte deterministic for the same fact set and contract versions when
ordering evidence is unchanged.

## Replay and market-data boundary

Import never calls replay directly. A caller may take a fully eligible bundle,
obtain daily prices under the existing exact-date/no-forward-fill Market Data
Contract, and pass the CanonicalExecutionV2 facts to the existing flexible
vectorbt replay. The regression fixture proves:

`CSV → Preview → Bundle → canonical_executions_to_frame → existing flexible replay → Position Episode`

`MarketDataRequirement` identifies instrument and required date range, daily
frequency, exact dates, and `forward_fill_allowed=false`. No price provider is
introduced. A missing price leaves the transaction import intact and makes the
dependent analytics unavailable.

## Privacy, persistence, and future adapters

This phase is in-memory only. There is no SQLite, import history, delete,
restore, or mutation of an existing fact store. `imported_at` belongs to a
future operation/audit record and is deliberately excluded from financial
identity.

Future `broker_x_csv_v1` adapters must produce the same raw/preview/canonical
boundary. A source-specific adapter may provide versioned market or ordering
semantics only after lawful sample review and explicit tests. It must never call
replay, calculate finance, or bypass reconciliation.

## Known limitations

- Generic CSV only; no named broker support claim.
- UTF-8/UTF-8 BOM only.
- Long-only execution facts; no margin, short, transfer, corporate action, or
  FX accounting.
- Exact replay requires known fee, qualified instrument, unambiguous order, and
  caller-supplied compatible daily prices.
- No persistence or user-confirmation workflow for possible duplicates.
- A source without stable execution IDs cannot prove identity beyond the
  deterministic content-and-occurrence evidence available in its export.
- No market-data download, intraday quote availability, or forward fill.
