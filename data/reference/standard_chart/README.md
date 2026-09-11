# Standard chart reference data

`finance-charts-apple.csv` is the untouched Plotly datasets source file downloaded
from the immutable commit recorded in `source.json`.  Its SHA-256 is verified by
the exporter before it builds the demo payload.  Plotly datasets is MIT licensed;
the source repository's `LICENSE` is MIT and is retained locally as
`PLOTLY_DATASETS_LICENSE`.  The source URL and commit are retained in the
payload for attribution.

The chart uses only the source's 2016 sessions.  Its `close` is the source
`AAPL.Adjusted`; open, high, and low are transformed by the same daily factor
`AAPL.Adjusted / AAPL.Close`.  This is an explicit display/replay price-basis
adapter, not a new accounting method.  These are fixed adjusted historical
coordinates: they are not nominal fills and they do not reconstruct corporate
actions.

`simulated-executions.csv` is a separate, explicitly simulated six-execution
ledger.  It is mapped to the real source instrument `AAPL` through the replay
instrument `SYN_AAPL_HISTORY`; its synthetic status belongs to the ledger and
demo account, not to the historical market observations.
