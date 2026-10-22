"""Shared EMA convention: SMA seed at period observations, then recursive fold.

No partial-window value is published.  For period N, the first EMA is the
arithmetic mean of closes 0..N-1 at index N-1; subsequent values use
alpha=2/(N+1).  This is also the seed convention used for public MACD.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence


def ema_series(values: Sequence[float], period: int) -> list[float]:
    """Return EMA values beginning at source index ``period - 1``."""
    if period <= 0:
        raise ValueError("EMA period must be positive")
    if len(values) < period:
        return []
    current = sum(values[:period]) / period
    output = [current]
    alpha = 2.0 / (period + 1)
    for value in values[period:]:
        current = (value - current) * alpha + current
        output.append(current)
    return output


# Keep just the latest state per (immutable series, period), bounded across
# simulations and formula parameters.  The strong reference prevents id reuse.
_MAX_SERIES = 64
_MAX_PERIODS = 32
_state: OrderedDict[int, tuple[object, OrderedDict[int, tuple[int, float]]]] = OrderedDict()


def ema_at(series: object, index: int, period: int) -> float | None:
    """EMA of ``series.adjusted_close`` at index, amortized O(1) in day order."""
    if period <= 0:
        raise ValueError("EMA period must be positive")
    closes = series.adjusted_close
    if index < period - 1 or index >= len(closes):
        return None
    key = id(series)
    entry = _state.get(key)
    if entry is None or entry[0] is not series:
        entry = (series, OrderedDict())
        _state[key] = entry
    _state.move_to_end(key)
    while len(_state) > _MAX_SERIES:
        _state.popitem(last=False)
    periods = entry[1]
    cached = periods.get(period)
    if cached is None or index < cached[0]:
        current = sum(closes[:period]) / period
        start = period
    else:
        start, current = cached[0] + 1, cached[1]
    alpha = 2.0 / (period + 1)
    for value in closes[start:index + 1]:
        current = (value - current) * alpha + current
    periods[period] = (index, current)
    periods.move_to_end(period)
    while len(periods) > _MAX_PERIODS:
        periods.popitem(last=False)
    return current


def clear_cache() -> None:
    _state.clear()
