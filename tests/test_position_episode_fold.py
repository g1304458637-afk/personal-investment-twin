"""The lifecycle position fold must agree with a full vectorbt prefix replay.

The fold (src/episodes/position_episode.py) replaces per-fill full replays
with one incremental pass.  These tests reconstruct the authoritative path —
replay_multi_asset_executions over each prefix, reading assets and the open
trade record — and compare quantity/average_cost bit for bit on a scenario
with adds, partial exits, full exits and re-entries.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.portfolio_replay import replay_multi_asset_executions
from src.episodes.position_episode import _fold_positions


def _frame_and_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = {
        "SYN_A": [10.0, 11.0, 12.0, 11.5, 9.0, 12.0, 13.0, 14.0],
        "SYN_B": [20.0, 21.0, 19.0, 20.0, 22.0, 21.0, 23.0, 24.0],
    }
    dates = pd.bdate_range("2025-01-06", periods=8)
    rows = [
        ("2025-01-06", "SYN_A", "BUY", 100.0, 10.0),
        ("2025-01-06", "SYN_B", "BUY", 50.0, 20.0),
        ("2025-01-07", "SYN_A", "BUY", 100.0, 11.0),
        ("2025-01-08", "SYN_A", "SELL", 120.0, 12.0),   # partial exit
        ("2025-01-09", "SYN_A", "BUY", 60.0, 11.5),     # add after partial
        ("2025-01-10", "SYN_A", "SELL", 140.0, 12.0),   # full exit
        ("2025-01-10", "SYN_B", "SELL", 20.0, 23.0),    # partial exit
        ("2025-01-15", "SYN_A", "BUY", 80.0, 14.0),     # re-entry
    ]
    frame = pd.DataFrame(
        [{"event_time": pd.Timestamp(t), "symbol": s, "side": side,
          "executed_quantity": q, "executed_price": p, "fee": 1.0,
          "order_id": f"O{i}", "execution_id": f"E{i}", "_source_ordinal": i}
         for i, (t, s, side, q, p) in enumerate(rows)])
    panel = pd.DataFrame(prices, index=dates)
    return frame, panel


def test_fold_matches_prefix_replay_bit_for_bit():
    frame, panel = _frame_and_panel()
    context = type("Ctx", (), {"valuation_prices": panel, "init_cash": 100_000.0})()
    for prefix in range(len(frame) + 1):
        states = _fold_positions(context, frame, prefix)
        if prefix == 0:
            assert states == {}
            continue
        portfolio = replay_multi_asset_executions(
            frame.iloc[:prefix].drop(columns="_source_ordinal"),
            panel, init_cash=100_000.0)
        assets = portfolio.assets().iloc[-1]
        for symbol in ("SYN_A", "SYN_B"):
            fold_qty, fold_size, fold_gross = states.get(symbol, (0.0, 0.0, 0.0))
            # vectorbt's assets index only carries symbols that have traded;
            # an untraded symbol takes the all-None state branch on both sides.
            if symbol not in assets.index:
                assert fold_qty == 0.0
                continue
            replay_qty = float(assets.loc[symbol])
            assert fold_qty == replay_qty, (prefix, symbol, fold_qty, replay_qty)
            if replay_qty > 1e-12:
                records = portfolio.exit_trades.open.records_readable
                records = records[records["Column"] == symbol]
                replay_avg = float(records.iloc[0]["Avg Entry Price"])
                fold_avg = fold_gross / fold_size
                assert repr(fold_avg) == repr(replay_avg), (prefix, symbol, fold_avg, replay_avg)
