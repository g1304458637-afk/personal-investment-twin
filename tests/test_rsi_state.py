"""The incremental Wilder-RSI cache must reproduce the reference fold bit
for bit — same operations, same order — across forward, out-of-order and
multi-window query patterns (simulations walk days forward; candidate
screening may query older indices)."""
from pathlib import Path

from src.strategy.data import load_simulation_data
from src.strategy.factors import _rsi
from src.strategy.rsi_state import clear_cache, wilder_rsi_at

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _assert_equal(series, index: int, window: int) -> None:
    reference = _rsi(series.adjusted_close[: index + 1], window)
    incremental = wilder_rsi_at(series, index, window)
    assert repr(reference) == repr(incremental), (index, window, reference, incremental)


def test_incremental_rsi_matches_reference_bit_for_bit():
    data = load_simulation_data(PROJECT_ROOT / "data" / "sample" / "strategy_universe")
    clear_cache()
    for series in data.series.values():
        for index in range(len(series.dates)):
            _assert_equal(series, index, 14)
            _assert_equal(series, index, 5)


def test_out_of_order_and_interleaved_windows():
    data = load_simulation_data(PROJECT_ROOT / "data" / "sample" / "strategy_universe")
    clear_cache()
    series = next(iter(data.series.values()))
    for index in (200, 100, 300, 150, 500, 500, 30, 14, 13, 0):
        _assert_equal(series, index, 14)
    for index in range(0, 400, 7):
        for window in (5, 14, 60):
            _assert_equal(series, index, window)


def test_insufficient_history_is_none():
    data = load_simulation_data(PROJECT_ROOT / "data" / "sample" / "strategy_universe")
    clear_cache()
    series = next(iter(data.series.values()))
    for index in (-1, 0, 5, 13):
        assert wilder_rsi_at(series, index, 14) is None
