"""Known-answer tests for the episode hold-baseline counterfactual.

Definition under test: hold the FIRST buy's quantity to the last usable
close inside the decision window; baseline = qty x (end_close - first_price)
- first fee; delta = realized_pnl - baseline.  Closes after the last
decision day are excluded — the baseline horizon ends with the episode.
"""
from types import SimpleNamespace

import pandas as pd

from src.review_pack.exit_quality import _EpisodeInputs, _hold_baseline


def _decision(decision_id, day, side, size, price, fees):
    return SimpleNamespace(
        decision_id=decision_id, occurred_at=f"{day} 09:31:00", side=side,
        executed_quantity=size, execution_price=price, fees=fees)


def test_hold_baseline_known_answer_and_horizon():
    inputs = _EpisodeInputs(
        episode_id="ep", instrument_id="X", realized_pnl=198.0, hold_days=6,
        decisions=(
            _decision("d1", "2025-01-02", "BUY", 100, 10.0, 1.0),
            _decision("d2", "2025-01-08", "SELL", 100, 12.0, 1.0),
        ),
        exit_pnl_by_decision={"d2": 198.0},
        closes={
            pd.Timestamp("2025-01-02"): 10.5,
            pd.Timestamp("2025-01-08"): 12.0,
            pd.Timestamp("2025-01-09"): 99.0,  # after the episode: excluded
        },
        missing_days=0,
    )
    baseline, delta, block = _hold_baseline(inputs)
    assert block is None
    assert baseline == (100.0 * (12.0 - 10.0) - 1.0)
    assert baseline == 199.0
    assert delta == -1.0


def test_hold_baseline_fail_closed_reasons():
    no_buy = _EpisodeInputs(
        episode_id="ep", instrument_id="X", realized_pnl=0.0, hold_days=0,
        decisions=(_decision("d1", "2025-01-02", "SELL", 10, 10.0, 0.0),),
        exit_pnl_by_decision={}, closes={}, missing_days=0)
    baseline, delta, block = _hold_baseline(no_buy)
    assert baseline is None and delta is None and block

    no_close = _EpisodeInputs(
        episode_id="ep", instrument_id="X", realized_pnl=0.0, hold_days=0,
        decisions=(_decision("d1", "2025-01-02", "BUY", 10, 10.0, 0.0),),
        exit_pnl_by_decision={}, closes={}, missing_days=1)
    baseline, delta, block = _hold_baseline(no_close)
    assert baseline is None and delta is None and block

    close_after_episode = _EpisodeInputs(
        episode_id="ep", instrument_id="X", realized_pnl=0.0, hold_days=0,
        decisions=(_decision("d1", "2025-01-02", "BUY", 10, 10.0, 0.0),),
        exit_pnl_by_decision={}, closes={pd.Timestamp("2025-02-01"): 12.0},
        missing_days=0)
    baseline, delta, block = _hold_baseline(close_after_episode)
    assert baseline is None and delta is None and "对齐" in block
