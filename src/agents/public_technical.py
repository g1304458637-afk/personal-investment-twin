"""Pure, closed-bar technical calculations for public OHLCV records."""
from __future__ import annotations

import math
from typing import Iterable


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _unavailable(reason, *, window=None):
    result = {"status": "unavailable", "reason": reason}
    if window is not None:
        result["window"] = window
    return result


def _display_value(value):
    """Stable plain-number rendering; indicators here are not percentages."""
    rounded = round(float(value), 2)
    return f"{0.0 if rounded == 0 else rounded:.2f}"


def _available(value, *, window=None):
    result = {"status": "available", "value": float(value),
              "display_value": _display_value(value)}
    if window is not None:
        result["window"] = window
    return result


def _ema(values: list[float], period: int):
    if len(values) < period:
        return None
    current = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1.0)
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def _ema_series(values: list[float], period: int):
    if len(values) < period:
        return []
    current = sum(values[:period]) / period
    output = [current]
    multiplier = 2.0 / (period + 1.0)
    for value in values[period:]:
        current = (value - current) * multiplier + current
        output.append(current)
    return output


def _rsi_wilder(closes: list[float], period=14):
    if len(closes) < period + 1:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains, losses = [max(change, 0.0) for change in changes], [max(-change, 0.0) for change in changes]
    avg_gain, avg_loss = sum(gains[:period]) / period, sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr_wilder(bars: list[dict], period=14):
    if len(bars) < period:
        return None
    ranges, previous_close = [], None
    for bar in bars:
        high, low = float(bar["high"]), float(bar["low"])
        ranges.append(high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = float(bar["close"])
    value = sum(ranges[:period]) / period
    for true_range in ranges[period:]:
        value = ((period - 1) * value + true_range) / period
    return value


def closed_bars(bars: Iterable[dict], *, latest_bar_may_be_in_progress: bool):
    """Validate, order, deduplicate and exclude the explicitly unfinished bar."""
    rows = []
    for item in bars:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str):
            continue
        names = ("open", "high", "low", "close", "volume")
        if not all(_finite(item.get(name)) for name in names):
            continue
        open_px, high, low, close, volume = (float(item[name]) for name in names)
        if high < low or high < max(open_px, close) or low > min(open_px, close) or volume < 0:
            continue
        rows.append({"date": item["date"][:10], "open": open_px, "high": high, "low": low, "close": close, "volume": volume})
    by_date = {row["date"]: row for row in rows}
    ordered = [by_date[key] for key in sorted(by_date)]
    return ordered[:-1] if latest_bar_may_be_in_progress and ordered else ordered


def calculate_technical_indicators(bars: Iterable[dict], *, latest_bar_may_be_in_progress: bool):
    """Calculate a disclosed subset of indicators from completed daily bars only."""
    rows = closed_bars(bars, latest_bar_may_be_in_progress=latest_bar_may_be_in_progress)
    closes, volumes = [row["close"] for row in rows], [row["volume"] for row in rows]
    metrics = {}
    for window in (5, 20, 50):
        metrics[f"sma_{window}"] = _available(sum(closes[-window:]) / window, window=window) if len(closes) >= window else _unavailable("insufficient_closed_bars", window=window)
    for window in (12, 26):
        value = _ema(closes, window)
        metrics[f"ema_{window}"] = _available(value, window=window) if value is not None else _unavailable("insufficient_closed_bars", window=window)
    fast, slow = _ema_series(closes, 12), _ema_series(closes, 26)
    lines = [fast[index + 14] - slow[index] for index in range(len(slow))] if slow else []
    signal = _ema(lines, 9)
    metrics["macd_12_26_9"] = ({"status": "available", "line": float(lines[-1]), "signal": float(signal), "histogram": float(lines[-1] - signal),
        "display_value": {"line": _display_value(lines[-1]), "signal": _display_value(signal),
                          "histogram": _display_value(lines[-1] - signal)},
        "fast_period": 12, "slow_period": 26, "signal_period": 9} if signal is not None else _unavailable("insufficient_closed_bars", window=34))
    rsi, atr = _rsi_wilder(closes), _atr_wilder(rows)
    metrics["rsi_14"] = _available(rsi, window=14) if rsi is not None else _unavailable("insufficient_closed_bars", window=14)
    metrics["atr_14"] = _available(atr, window=14) if atr is not None else _unavailable("insufficient_closed_bars", window=14)
    if len(volumes) < 6:
        metrics["volume_ratio_5"] = _unavailable("insufficient_closed_bars", window=5)
    else:
        baseline = sum(volumes[-6:-1]) / 5
        metrics["volume_ratio_5"] = _available(volumes[-1] / baseline, window=5) if baseline > 0 else _unavailable("zero_prior_volume_baseline", window=5)
    return {"closed_bar_count": len(rows), "last_closed_bar_date": rows[-1]["date"] if rows else None, "metrics": metrics}
