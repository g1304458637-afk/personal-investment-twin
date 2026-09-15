"""Known-answer test for mid-path entry-fee allocation in exit quality.

The entry-fee pool must follow average-cost attribution: sells remove their
proportional share of the pool at sell time, buys add theirs.  A lifetime
uniform-rate formula (total fees × held/lifetime-bought) gives a different,
wrong mid-path number once fee-per-share differs between buys.
"""
from types import SimpleNamespace

import pandas as pd

from src.review_pack.exit_quality import _EpisodeInputs, _window_path


def _decision(decision_id, day, side, size, price, fees):
    return SimpleNamespace(
        decision_id=decision_id, occurred_at=f"{day} 09:31:00",
        side=side, executed_quantity=size, execution_price=price, fees=fees)


def test_mid_path_fee_pool_tracks_average_cost_attribution():
    buys_and_sells = [
        _decision("d1", "2025-01-02", "BUY", 100, 10.0, 5.0),   # fee/share 0.05
        _decision("d2", "2025-01-03", "SELL", 50, 12.0, 0.5),   # half the lot exits
        _decision("d3", "2025-01-06", "BUY", 100, 10.0, 1.0),   # cheap fee add
    ]
    inputs = _EpisodeInputs(
        episode_id="ep", instrument_id="X", realized_pnl=497.0,
        hold_days=4, decisions=buys_and_sells,
        exit_pnl_by_decision={"d2": 500.0},
        closes={
            pd.Timestamp("2025-01-02"): 10.0, pd.Timestamp("2025-01-03"): 12.0,
            pd.Timestamp("2025-01-06"): 10.0, pd.Timestamp("2025-01-07"): 10.0,
        },
        missing_days=0,
    )
    dates, cum_values, notional_values = _window_path(inputs)
    cum_by_date = {str(day.date()): value for day, value in zip(dates, cum_values)}

    # After the sell: pool = 5.0 × (1 − 50/100) = 2.5 → cum = 500 + 50×2 − 2.5.
    assert cum_by_date["2025-01-03"] == (500.0 + 100.0 - 2.5)
    # After the cheap add: pool = 2.5 + 1.0 = 3.5, held 150 @ avg cost 10.
    # The old lifetime formula would have charged 6.0 × 150/200 = 4.5 here.
    assert cum_by_date["2025-01-07"] == (500.0 + 0.0 - 3.5)
    assert notional_values[-1] == 1500.0
