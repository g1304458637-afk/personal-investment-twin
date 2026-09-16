"""Incremental Wilder-RSI state cache.

The reference implementation (``factors._rsi`` / ``rsi_mr.wilder_rsi``)
re-folds the whole prefix for every queried day: O(days) per call, O(days²)
per simulation on real multi-year histories.  Wilder's recursion is a pure
sequential fold, so continuing from the stored (avg_gain, avg_loss) at index
i reproduces the from-scratch value bit for bit — same operations, same
order, no re-association.

The cache is keyed by ``id(series)`` and holds a strong reference to the
series (preventing id reuse) with a small LRU cap; simulations walk days
forward, so only forward extension is cached — a smaller or repeated index
falls back to the reference fold, which stays correct (just slower).
"""
from __future__ import annotations

from collections import OrderedDict

from src.strategy.data import InstrumentSeries

_CACHE_MAX_SERIES = 64

# id(series) -> (series, window -> [index, avg_gain, avg_loss])
_state: "OrderedDict[int, tuple[InstrumentSeries, dict[int, list[float]]]]" = OrderedDict()


def wilder_rsi_at(series: InstrumentSeries, index: int, window: int) -> float | None:
    """Reference-equal RSI value at ``index``, folding incrementally."""
    closes = series.adjusted_close
    if index < window or index < 0:
        return None
    key = id(series)
    entry = _state.get(key)
    if entry is None or entry[0] is not series:
        entry = (series, {})
        _state[key] = entry
        while len(_state) > _CACHE_MAX_SERIES:
            _state.popitem(last=False)
    _, windows = entry
    state = windows.get(window)
    if state is None or state[0] > index:
        # Seed from scratch (also the path for out-of-order queries).
        gains = losses = 0.0
        for i in range(1, window + 1):
            change = closes[i] - closes[i - 1]
            gains += max(change, 0.0)
            losses += max(-change, 0.0)
        state = [window, gains / window, losses / window]
        windows[window] = state
    start = state[0] + 1
    avg_gain, avg_loss = state[1], state[2]
    for i in range(start, index + 1):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (window - 1) + max(change, 0.0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-change, 0.0)) / window
    state[0], state[1], state[2] = index, avg_gain, avg_loss
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def clear_cache() -> None:
    """Drops all cached fold state (test isolation between simulations)."""
    _state.clear()
