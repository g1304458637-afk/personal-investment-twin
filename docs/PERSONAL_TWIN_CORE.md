# Personal Twin Core v1

## Definition

Personal Twin is a versioned, deterministic point-in-time read model. It projects
financial facts already produced by portfolio replay, Position Episode lifecycle,
and Evidence records that were available at the requested `as_of` time.

It is not a broker ledger, portfolio replay engine, second financial calculator,
LLM memory, psychology profile, investment score, or skill score. Deleting every
Twin snapshot must not delete an authoritative financial fact: the snapshot is
rebuildable from canonical inputs and the existing deterministic core.

```text
normalized executions + dated market data
                  |
                  v
        vectorbt portfolio replay
                  |
                  v
       Position Episode lifecycle

registered deterministic Evidence + historical Evidence views
                  |
                  v
       point-in-time Twin projection
                  |
                  v
              TwinSnapshot
```

The dependency direction never reverses. Replay and Evidence do not read Twin
state, and presentation or Agent layers must not calculate replacement financial
numbers from Twin fields.

## Reference implementation study

### Ghostfolio

- Read: `PortfolioCalculator.computeSnapshot()` / `getSnapshot()` in
  `apps/api/src/app/portfolio/calculator/portfolio-calculator.ts`,
  `PortfolioSnapshotProcessor.calculatePortfolioSnapshot()`,
  `ActivitiesService.getActivitiesForPortfolioCalculator()`, the shared
  `PortfolioSnapshot` model, and calculator scenario tests such as
  `portfolio-calculator-msft-buy-with-dividend.spec.ts`.
- Solves: activities and dated market/FX data enter one calculator; positions and
  historical data are derived together; a queue/service may cache the result.
- Borrow: snapshots are disposable calculator output, while activities remain the
  source; orchestration and caching sit above the calculator.
- Reject: tracker-specific broad snapshot fields, Redis lifecycle, and the
  non-deterministic `createdAt` value are not Twin identity inputs.
- Contract impact: Twin stores references and projected facts, not an editable
  second ledger.

### Rotki

- Read: `HistoricalBalancesManager.get_balances()` / `get_balance_series()`,
  `process_historical_balances()`, historical-balance API tests, historical price
  query tests, and issue `rotki/rotki#12277`.
- Solves: ordered historical events generate timestamped balance metrics and
  historical price lookups are a separate dated dependency.
- Borrow: current state and historical state require different price-time
  semantics; missing historical data must remain visible.
- Reject: current-data fallback for a historical display. Issue #12277 documents
  historical USD snapshots being converted with today's FX rate, which changes
  the meaning of old points.
- Contract impact: every execution, mark, Episode state, Evidence availability
  time, historical point, and provenance timestamp serialized into `Twin@T` must
  be at or before `T`. The current daily Market Data Contract cannot prove that a
  day's final close was available at an intraday time, so that limitation remains
  explicit.

### Portfolio Performance

- Read: `ClientSnapshot.create()`, `PortfolioSnapshot.create()`,
  `AccountSnapshot.create()`, `ClientPerformanceSnapshot`, and
  `CurrencyTestCase.testClientSnapshot()`.
- Solves: transactions are filtered at a requested date and valued through the
  existing dated currency/price converter; performance composes start and end
  core snapshots.
- Borrow: an upper layer requests a dated core snapshot and reuses it; it does not
  reproduce accounting formulas for an API, UI, or AI consumer.
- Reject: Portfolio Performance's Java domain objects and tracker-specific
  account/taxonomy model are not copied into Twin.
- Contract impact: Position quantities, average cost, marks, and market values in
  Twin come only from the existing replay-backed Position Episode lifecycle.

No source code from these reference repositories is copied into this project.

## Point-in-time contract

`build_twin_snapshot(..., snapshot_at=T)` accepts an optional Position Episode
lifecycle that must itself have been built exactly at `T`. The projection rejects
a lifecycle from a later or earlier time and defensively rejects any future
episode, decision, state, valuation, snapshot, or linked Evidence reference.

Evidence is eligible only when:

```text
max(record.as_of, record.observation_end, provenance[*].as_of) <= T
```

Every supplied Evidence record must also have `record.subject_id ==
TwinSnapshot.subject_id`. Position Episode currently has no registered ownership
mapping that can prove an Episode-scoped subject belongs to an account/Twin
subject, so an Episode reference never authorizes cross-subject Evidence. A
subject mismatch fails closed.

The Evidence Contract has no separate `produced_at` field. In v1, `as_of`, the
completed observation window, and provenance timestamps are therefore the
available-time boundary. An earlier observation with a later `as_of` or later
provenance timestamp is not visible. `insufficient_evidence` is retained as the
state that was knowable at `T`; a later-completed window cannot rewrite it.

Historical metric points after `T` are excluded. If a point references a supplied
Evidence record whose available time is after `T`, that point is also excluded.
No current price or current state is used as a fallback for a historical point.

Open Episode marks remain valuation facts, never exits. A partial sale keeps an
Episode open. A later full close is visible only in snapshots built at or after
that execution, and reopening from zero creates a new Episode.

## Identity and serialization

`snapshot_id` is `tw_` plus SHA-256 of the project's canonical JSON encoding of
the snapshot payload excluding the ID itself. The identity includes the subject,
`snapshot_at`, schema/projection/code versions, deterministic input version
references, portfolio/Episode/Decision references, eligible Evidence and status,
data quality, data tier, and declared limitations.

Serialization is explicit JSON data with ISO timestamps and stable tuple order;
it never depends on Python object representation or a random UUID. The
from-facts orchestration derives a prefix-scoped normalized-execution data version
from the canonical execution facts and initial-cash input, so appending future
rows does not change `Twin@T`.

## Current boundaries

- Long-only normalized BUY/SELL executions only, inherited from Position Episode.
- Daily market dates have no intraday availability timestamp. A same-day close is
  dated but cannot be proven available at an intraday decision time.
- No new HHI, Turnover, Sizing, Exit, return, PnL, CI, or other financial formula
  exists in Twin.
- Self-baseline, peer context, notable changes, and intervention history are empty
  or unavailable in v1.
- No cohort, percentile, ranking, personality label, advice, prediction, or skill
  conclusion is produced.
