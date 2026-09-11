"""Pure window computations over trailing valid closes.

All windows count *valid observations* (the Decision Lens convention), never
calendar days.  Every function returns None instead of guessing when the
window is incomplete.
"""
from __future__ import annotations

import math


def trailing_mean(values: tuple[float, ...] | list[float], window: int) -> float | None:
    """Mean of the last ``window`` observations (newest included)."""
    if window <= 0 or len(values) < window:
        return None
    segment = values[-window:]
    return sum(segment) / len(segment)


def prior_extreme(values: tuple[float, ...] | list[float], window: int, *,
                  high: bool) -> float | None:
    """Extreme of the ``window`` observations strictly before the newest one."""
    if window <= 0 or len(values) < window + 1:
        return None
    segment = values[-(window + 1):-1]
    return max(segment) if high else min(segment)


def breakout_strength(close: float, prior_high: float) -> float | None:
    """Distance of the close above the prior window high; None when invalid."""
    if prior_high <= 0 or not math.isfinite(close):
        return None
    return close / prior_high - 1.0
