# Canonical Execution Contract v2

Status: implemented compatibility contract for deterministic long-only replay.  It is an additive boundary over the existing normalized demo DataFrame; it is not a generic broker CSV importer or a security master.

## Why v2 exists

The v1 normalized table was sufficient for the synthetic fixture, but it treated a naked symbol as the portfolio column, required a known numeric fee, had no source-timezone contract, and rejected more than one fill for the same symbol and timestamp.  Historical broker data can contain partial fills with equal timestamps, identical economic fields, and independent execution IDs.  Identity, ordering, and analytics eligibility therefore need separate contracts.

The canonical path is:

`source fill → CanonicalExecutionV2 → replay eligibility → normalized replay frame → vectorbt Order → Decision Event → Position Episode → Outcome`

No v2 object calculates cash, holdings, average cost, return, or PnL.

## Source and implementation review

| Reference | Source actually reviewed | Contract observed | Borrowed | Deliberately not borrowed | v2 consequence |
| --- | --- | --- | --- | --- | --- |
| vectorbt 1.1.0 | installed `vectorbt/portfolio/base.py`, `Portfolio.from_order_func`; `vectorbt/portfolio/nb.py`, `flex_simulate_nb`, `process_order_nb`, `get_exit_trades_nb`; upstream `tests/test_portfolio.py` flexible callback tests | `flexible=True` repeatedly calls a flexible order function and explicitly lifts the one-order-per-element limit. `close` remains the end-of-bar valuation series. `get_exit_trades_nb` scans Order IDs in ascending per-column order and emits one closed exit trade for each reducing order in a long position. | Flexible multiple-order emission, long-only Amount orders, fixed recorded fees, authoritative Order/Trade/Position records | Signal generation, custom accounting, partial acceptance, short/margin, tick pricing | One vectorbt replay core now emits every execution and verifies record links. `update_value=False` and bar `close` preserve frozen end-of-bar valuation behavior. |
| QuantConnect Lean | `Common/Symbol.cs`; `Common/Orders/OrderEvent.cs`; `Common/Statistics/TradeBuilder.cs` | A `Symbol` has a security identifier distinct from its display ticker. Fills are independent order events; TradeBuilder processes fill events and order IDs rather than treating timestamp as identity. | Qualified identity and independent execution/order identity | Lean accounting, brokerage, security master, corporate actions | `instrument_id`, `execution_id`, and `source_order_id` are separate. Timestamp never identifies a fill. |
| Rotki | `rotkehlchen/api/v1/fields.py::TimezoneField`; `serialization/deserialize.py::deserialize_timestamp_from_date_with_timezone`; `tests/api/test_data_import.py::test_data_import_cryptocom_with_timezone` | Import timezone is an IANA name; aware values keep their offset; naive values are interpreted in the supplied zone then converted to UTC. Tests prove an Asia/Shanghai shift. | Explicit source timezone, UTC normalization, invalid-zone rejection | Defaulting a missing source timezone to UTC; importer-specific behavior | Naive timed facts require an IANA timezone. Aware offsets win. Ambiguous/nonexistent DST local times fail closed. |
| Portfolio Performance | `model/Security.java`; `datatransfer/SecurityCache.java`; `datatransfer/csv/BaseCSVExtractor.java`; `CSVSecurityExtractor.java` | Security has a stable UUID separate from name, ticker, ISIN/WKN, currency and quote-feed settings. CSV resolution considers multiple identifiers and detects duplicates. | Opaque internal identity; display/provider identifiers as metadata/resolution inputs | Its matching heuristics, Java model, quote providers, FIFO/accounting | v2 qualifies local symbol with market and security type; display name and currency are not the identity. Missing market/type stays unresolved. |

## CanonicalExecutionV2

The immutable v2 fact contains:

- `schema_version = "2"`
- `subject_id`, `account_id`
- opaque `execution_id`
- optional source `source_execution_id`, `source_order_id`
- `InstrumentRef`
- `ExecutionTime`
- optional `execution_sequence` plus provenance `sequence_source`
- `side`, `executed_quantity`, `executed_price`
- `FeeFact`
- source and stable source-record reference

`result_payload()` is deterministic and contains both identity and result-affecting facts. It is not itself the definition of execution identity.

## Identity versus ordering

`execution_id` identifies one fill. Event time is not an identifier. When a source execution ID is available, the generated opaque ID is derived from subject, account, source namespace, source execution ID and stable source-record reference. Execution sequence is intentionally excluded: reconciliation may correct ordering without changing which fill it is.

`execution_sequence` affects replay results but not identity. Its scope is one `subject_id + account_id + event-time key`, across instruments, because shared cash makes `SELL B → BUY A` observably different from `BUY A → SELL B`. Multiple fills in that scope require unique explicit sequences. Unknown or duplicate sequence produces `blocked_ambiguous_order`; symbol, side, price, hash, or incidental Python row order is never used to invent v2 order.

A singleton may omit sequence and maps to the technical value zero. A legacy DataFrame retains its historical stable row order only when it has no same-symbol/timestamp collision. `LegacyExecutionAdapter` can explicitly record legacy source row order as evidence; row order is never an execution identity.

## Qualified instrument identity

`InstrumentRef` separates:

- opaque deterministic `instrument_id`
- normalized `local_symbol`
- `market`
- `security_type`
- non-identifying `currency`, `display_symbol`, and `display_name`

The v2 identity key is normalized `(local_symbol, market, security_type)`. Thus `ABC @ MARKET_A` and `ABC @ MARKET_B` cannot collide in replay or market-data lookup. Currency is metadata: changing a mistaken currency annotation must not silently create a different security. A missing market or security type leaves `instrument_id=None` and blocks replay rather than guessing a venue. `LEGACY_DEMO` is an explicit synthetic namespace for old fixtures; it makes no real-exchange claim.

Corporate actions, symbol changes, mergers, ISIN history, and a durable security-master migration remain limitations.

## Execution time, precision, and timezone

`ExecutionTime` preserves source text, precision (`date`, `minute`, `second`, `millisecond`, or `microsecond`), source timezone, UTC instant when one exists, and source calendar date.

- A naive timed value requires an explicit IANA `source_timezone`.
- An offset-aware value keeps its own offset; importer configuration does not override it.
- Timed values normalize deterministically to UTC, independent of the machine timezone.
- Ambiguous and nonexistent DST local times fail closed and require an explicit offset.
- A date-only fact has no `instant_utc`. It is not asserted to have happened at midnight.

The vectorbt adapter needs an index value. For timed facts it transports a timezone-naive UTC value alongside the explicit `canonical_event_time_utc`; for date-only facts it uses the calendar date as a technical daily-axis key alongside `time_precision=date`. Neither transport convention changes the canonical business fact. Daily market data remains daily: `market_date` selects the exact source calendar date and no intraday quote availability is invented.

## FeeFact and replay eligibility

Fee availability has three states:

- `known_nonzero`: finite positive recorded fee
- `explicit_zero`: known, explicitly zero fee
- `unknown`: amount absent

Unknown fee is a valid canonical broker fact but is never converted to zero. The current exact/net replay blocks it. No gross replay or cost estimate is introduced.

`ExecutionReplayEligibility` currently fails closed for:

- `blocked_unknown_fee`
- `blocked_ambiguous_order`
- `blocked_unresolved_instrument`
- `blocked_unsupported_direction`

This establishes the permanent distinction `canonical fact ≠ replay-ready fact`.

## Flexible vectorbt replay

All existing and v2 callers use one adapter in `portfolio_replay.py`. For each valuation bar the adapter prepares an ordered list of independent fills. A Numba flexible order function emits each as a separate vectorbt Amount order with:

- explicit execution price
- fixed recorded fee and zero proportional fee
- zero slippage and rejection probability
- no partial acceptance
- long-only direction and rejection on illegal cash/position state
- shared account cash

There is no aggregation, weighted fill synthesis, dropped fill, custom cash ledger, or custom PnL code. `max_orders` is the accepted execution count.

The prior `from_orders` implementation used current order price as its decision-time valuation input and the supplied `close` as end-of-bar valuation. Amount orders do not use portfolio value for sizing. The flexible adapter explicitly keeps `update_value=False`; vectorbt resets each column to supplied `close` after the segment. Parity tests compare Orders, cash, holdings, asset flow, value, Positions, Exit Trades, PnL and return against a frozen v1 `from_orders` fixture. Existing Decision, Behavior, Twin, Episode and Outcome regressions provide broader parity coverage.

## ReplayExecutionLink and mapping proof

After vectorbt returns, the adapter fails closed unless accepted Order count equals execution count. In emission order it verifies every link using:

- vectorbt Order ID
- column / canonical instrument ID
- index timestamp
- side
- size
- execution price
- fee

`ReplayExecutionLink` then records:

- `execution_id → vectorbt_order_record_id`
- for SELLs, `execution_id → vectorbt_exit_trade_record_id`
- `execution_id → vectorbt_position_record_id`

The SELL mapping is not a timestamp lookup. It relies on the reviewed vectorbt 1.1.0 algorithm: per column, `get_exit_trades_nb` consumes ascending Order IDs and emits one closed Exit Trade for every long-position SELL. The adapter zips those proven sequences and revalidates timestamp, size, price and fee. Any count or field mismatch returns `outcome_mapping_unavailable`.

Position links use vectorbt Position IDs and the verified final SELL per closed position to delimit order-record membership. This only links records; it does not calculate quantity, average cost, return or PnL.

## Episode and Outcome consumption

Position Episode prefix replay retains `execution_sequence`. A lifecycle can therefore process, at one timestamp, `BUY → SELL → BUY` as `open → close → reopen`, producing two Positions and two Episodes. Decision Events are preserved individually and ordered by canonical sequence.

Each Episode stores its verified `vectorbt_position_record_id`. Actual Outcome order, exit-trade, and position lookup now uses replay links and record IDs. It no longer selects a record by symbol plus timestamp. Two economically identical same-time SELL fills remain separate, each with its own execution ID, Order ID, Exit Trade ID, and authoritative vectorbt PnL.

Counterfactual scopes use links from their own replay. If an actual execution is absent from that scope, the existing fail-closed/structural-absence rules remain unchanged. No PnL formula was added.

## Market-data identity adapter

For v2, the vectorbt column and Market Data Contract `instrument` value are the same opaque canonical `instrument_id`. Market prices retain the frozen exact daily-date, complete-panel, no-forward-fill rules. Execution price remains a fill fact; daily close remains a market valuation fact. Exact timed executions do not create intraday market observations.

## Legacy migration

Existing normalized synthetic frames continue through the same replay function and keep their public financial results. `LegacyExecutionAdapter` can qualify their symbols under `LEGACY_DEMO`, attach subject/account ownership, normalize a declared source timezone, and turn source row order into explicit sequence provenance. This is additive: there is no ReplayV1 calculator beside a ReplayV2 calculator.

The next real-user ingestion phase can map a reviewed source file to `CanonicalExecutionV2`, present unresolved/unknown facts, evaluate eligibility, and only then call `replay_canonical_executions` with market data keyed by canonical instrument ID.

## Current limitations

- Long-only, known absolute quantity, known positive execution price, and no margin.
- Exact/net replay requires known recorded fee.
- Timed and date-only facts cannot be mixed in one replay batch.
- Daily market data only; no tick/minute availability or forward fill.
- v2 does not implement broker-file reconciliation, duplicate import resolution, persistence, corporate actions, transfers, FX accounting, security-master history, gross replay, or generic CSV mapping.
- `LegacyExecutionAdapter` source row references are migration aids, not production reconciliation identities.
