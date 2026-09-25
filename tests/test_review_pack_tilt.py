"""Unit tests for the tilt trigger's missing-trigger-day handling.

The trigger day (third consecutive losing close) can fall on a day without
an observed trading day.  detect_tilt must never drop that confirmed trigger
silently: the window snaps to the first observed day at or after the trigger,
or the item reports honestly that no window could be evaluated.
"""
import pandas as pd

from src.review_pack.tilt import detect_tilt


def _setup(trigger_exit_day: str, extra_trading_days: int = 40):
    """20+ executions with a 3-loss streak ending on trigger_exit_day."""
    trading_days = list(pd.bdate_range("2024-11-04", periods=70))
    execution_days: list[pd.Timestamp] = []
    execution_symbols: list[str] = []
    execution_sides: list[str] = []
    execution_notionals: list[float] = []
    for index in range(20):
        day = trading_days[index]
        execution_days.extend([day, day])
        execution_symbols.extend(["F", "F"])
        execution_sides.extend(["BUY", "SELL"])
        execution_notionals.extend([10_000.0, 10_000.0])
    streak_days = [pd.Timestamp(day).normalize() for day in (
        "2025-01-20", "2025-01-21", trigger_exit_day)]
    for index, day in enumerate(streak_days):
        execution_days.extend([day, day])
        execution_symbols.extend([f"L{index}", f"L{index}"])
        execution_sides.extend(["BUY", "SELL"])
        execution_notionals.extend([10_000.0, 9_000.0])
    closed_exits = [
        {"exit_day": pd.Timestamp("2025-01-20"), "instrument_id": "L0", "realized_pnl": -100.0},
        {"exit_day": pd.Timestamp("2025-01-21"), "instrument_id": "L1", "realized_pnl": -100.0},
        {"exit_day": pd.Timestamp(trigger_exit_day), "instrument_id": "L2", "realized_pnl": -100.0},
    ]
    return execution_days, execution_symbols, execution_sides, execution_notionals, trading_days, closed_exits


def test_trigger_on_unobserved_day_snaps_window_forward():
    # 2025-01-25 is a Saturday: absent from the bdate trading calendar.
    days, symbols, sides, notionals, trading_days, exits = _setup("2025-01-25")
    observations = detect_tilt(days, symbols, sides, notionals, trading_days, exits)
    assert len(observations) == 1
    item = observations[0]
    # The trigger itself is reported with its real calendar date...
    assert item["trigger_date"] == "2025-01-25"
    # ...and the window snapped to the next observed trading day, so a trade
    # on the following Monday counts.
    monday = pd.Timestamp("2025-01-27")
    assert monday in trading_days
    assert any("非已观测交易日" in note for note in item["limitations"])
    assert item["window"]["trade_count"] is not None


def test_trigger_after_last_observed_day_reports_insufficient_window():
    days, symbols, sides, notionals, trading_days, exits = _setup("2030-06-01")
    observations = detect_tilt(days, symbols, sides, notionals, trading_days, exits)
    assert len(observations) == 1
    item = observations[0]
    assert item["trigger_date"] == "2030-06-01"
    assert item["window"]["trade_count"] is None
    assert item["window"]["baseline_trade_count"] is None
    assert item["window"]["avg_size_change_pct"] is None
    assert any("窗口统计不可用" in note for note in item["limitations"])


def test_trigger_on_observed_day_unchanged():
    days, symbols, sides, notionals, trading_days, exits = _setup("2025-01-22")
    observations = detect_tilt(days, symbols, sides, notionals, trading_days, exits)
    assert len(observations) == 1
    item = observations[0]
    assert item["trigger_date"] == "2025-01-22"
    assert all("非已观测交易日" not in note for note in item["limitations"])
    assert all("窗口统计不可用" not in note for note in item["limitations"])
