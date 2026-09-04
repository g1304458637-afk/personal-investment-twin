# Minimal Historical Market Data v1

## Purpose and boundary

This layer supplies only the historical daily observations needed by the
existing deterministic replay, Position Episode, Outcome, and registered
historical counterfactual modules. It is not a quote terminal and contains no
network provider, realtime quote, intraday bar, order book, volume, news, money
flow, or security-fundamentals capability.

The architecture is:

`source adapter → immutable HistoricalPriceFact → frozen Market Data Contract → existing financial core`

`MarketDataSourceAdapter` is the source boundary. v1 implements only
`generic_historical_price_csv_v1`. A future commercially licensed source adds
another adapter and must produce the same contract; financial modules do not
depend on its transport.

## Frozen price semantics

The existing Market Data Contract names the numeric observation `close` and
allows `adjusted_close`, `total_return`, or `synthetic`. Generic real-user CSV
requires the user to state `adjusted_close` or `total_return`; it rejects an
unknown basis, `raw_close`, and `synthetic`. The importer does not guess,
convert, adjust, interpolate, or fetch a price.

This means corporate actions remain a known limitation. A file with unknown
adjustment basis is not accepted merely to make an Episode displayable. The
term “close” here follows the frozen contract; it does not assert intraday
availability at the execution timestamp.

## Generic CSV v1

Required fields are:

- `date`
- `price` (alias `close`)
- `price_type` (alias `price_basis`)
- either qualified `local_symbol + market + security_type`, or an
  `instrument_id` resolvable through the caller's canonical instrument registry

Optional fields are `currency` and `source_label`. Import configuration records
`source_id`, `source_version`, and deterministic `imported_at` metadata. The raw
file hash and source-row identity are retained for audit; the adapter does not
persist the raw file.

Canonical v2 identity is mandatory. The same local symbol on two markets maps
to two different opaque instrument IDs. Currency is metadata, not identity.

## Duplicate and conflict rules

Observation identity is:

`instrument_id + date + price_type + source_id + source_version`

An equal value at the same identity is a duplicate. A different value is a
conflict and is never silently overwritten. Preview reports new, existing,
duplicate, conflicting, and invalid rows before any persistence layer exists.

## Daily coverage and Episode gate

The frozen ingestion requirement identifies a date range but does not contain
an exchange trading calendar. v1 can therefore prove exact observations for
the canonical executions' source calendar dates; it must not invent additional
sessions. Coverage is `complete`, `partial`, or `missing`, with explicit missing
instrument/date pairs.

There is no forward fill, backward fill, interpolation, or synthetic fallback.
If a required execution date is absent, trade facts remain valid but
`build_episode_when_market_ready` returns
`unavailable_pending_market_data`. Only replay-eligible executions plus complete
exact-date coverage are projected into the existing Position Episode builder.

The complete price panel supplied by the user remains available for the Episode
path and valuation. Exact exchange-calendar completeness and current-price
freshness require a future licensed provider or reviewed trading-calendar
contract.

## Licensing and provenance

v1 performs no network access and adopts no third-party market-data license.
The user is responsible for supplying data they are authorized to use. Source,
version, price basis, file hash, import timestamp, and synthetic tier are kept
explicit. Real-account facts cannot consume `synthetic_demo` observations.

## Known limitations

- Historical daily observations only.
- No corporate-action calculator or raw-to-adjusted conversion.
- No FX conversion or multi-currency account valuation.
- No exchange calendar, holiday service, or current-price updater.
- No licensed provider is selected in v1.
