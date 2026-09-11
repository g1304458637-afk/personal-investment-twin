# Standard investment chart sample v1

Scope: one new, explicitly selected offline example. Existing Demo Security H,
Same-Stock Compare, financial methods, Evidence and Market Data contracts remain
unchanged. This is not an iFinD integration or a live market feed.

## Data path

Pinned Plotly AAPL historical CSV (252 sessions in 2016)
→ source-adjusted OHLC display coordinates + identical replay closes
→ separate six-trade simulated ledger
→ existing replay / Position Episode / Outcome builders
→ `scripts/export_standard_chart_demo.py`
→ `apps/desktop/src/generated/standard-chart-demo.json`
→ thin `standardChart` adapter → existing Episode page.

Source checksum, license, revision and explicit simulated ledger live in
`data/reference/standard_chart`. The source-adjusted coordinates are not nominal
historical execution prices or a reconstructed corporate-action ledger. No real
user data is included. Currency is USD; legacy examples retain their CNY fallback.

## UI

My Investments → “打开标准 K 线示例”. Explicit selection switches to the separate
example account; a direct URL never silently switches a real-user context.

The sample uses KLineCharts 10.0.3. Daily / weekly / monthly candles and close-line
share one price/quantity/optional-volume canvas and one range navigator. MA(5,10,20)
is an optional price indicator, distinct from replay-supplied average cost.
Weekly/monthly OHLCV aggregates only supplied daily bars. Missing volume remains
unavailable. Quantity/cost are period-end snapshots, not interpolated holdings or
invented intraday prices. Trade markers retain exact simulated execution times.
Focus includes seven actual source sessions on either side of the requested span.

The range and crosshair are shared across panes. Horizontal wheel and mouse drag
pan; Ctrl/Meta-wheel and WebKit pinch zoom. Vertical wheel is forwarded to the
enclosing scrollable page. Focus mode escapes glass stacking contexts through a
portal and closes with Escape. Chart asset loading requires no API credentials.

## Verification

- Backend provenance, matched replay price basis, existing-builder result and
  deterministic export tests: 4 passed; full Python suite: 875 passed.
- New adapter/model tests cover malformed bars, owner/instrument/currency mismatch,
  date ordering, aggregation, same-session operations, cost after closing, and
  source-session focus context.
- Browser at 1440×900: actual plotted candles/cost/quantity, operation marker click,
  weekly + MA + volume, full-history/reset, horizontal wheel, mouse drag, zoom
  buttons, and vertical page scrolling verified. No native device pinch claim:
  physical trackpad and the Tauri WebKit build still need user acceptance.
- This sample is not yet a migration of every existing line chart.
