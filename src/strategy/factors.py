"""User-facing factor library (v1) for composite strategy building.

Design references: qlib's expression operator semantics (features are
strictly backward-looking; every value at index uses bars up to and
including index), and NextTrade's condition model (factor + operator +
threshold).  Each factor ships metadata: label, category, default params,
a plain statement, and a known-misreading warning — the workshop UI renders
these verbatim.

Every compute returns ``None`` when the window is incomplete: insufficient
history means "not satisfied", never a guess.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

from src.strategy.data import InstrumentSeries
from src.strategy.signals import prior_extreme, trailing_mean


def _rsi(closes: tuple[float, ...], window: int) -> float | None:
    if len(closes) < window + 1:
        return None
    gains = losses = 0.0
    for i in range(1, window + 1):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / window, losses / window
    for i in range(window + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (window - 1) + max(change, 0.0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-change, 0.0)) / window
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr_ratio(series: InstrumentSeries, index: int, window: int) -> float | None:
    start = index - window + 1
    if start < 1:
        return None
    trs: list[float] = []
    for i in range(start, index + 1):
        factor, factor_prev = series.split_factors[i], series.split_factors[i - 1]
        close_prev = series.bars[i - 1].close / factor_prev
        high = series.bars[i].high / factor
        low = series.bars[i].low / factor
        trs.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))
    atr = sum(trs) / len(trs)
    close = series.bars[index].close / series.split_factors[index]
    return atr / close if close > 0 else None


def _compute_sma_gap(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
    closes = series.adjusted_close[: index + 1]
    window = int(params["window"])
    mean = trailing_mean(closes, window)
    if mean is None or mean <= 0:
        return None
    return closes[-1] / mean - 1.0


def _make_breakout(high: bool):
    def compute(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
        closes = series.adjusted_close[: index + 1]
        window = int(params["window"])
        extreme = prior_extreme(closes, window, high=high)
        if extreme is None or extreme <= 0:
            return None
        close = closes[-1]
        if high:
            return close / extreme - 1.0 if close > extreme else None
        return extreme / close - 1.0 if close < extreme else None
    return compute


def _compute_rsi(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
    closes = series.adjusted_close[: index + 1]
    return _rsi(closes, int(params["window"]))


def _compute_roc(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
    closes = series.adjusted_close[: index + 1]
    window = int(params["window"])
    if len(closes) < window + 1 or closes[-window - 1] <= 0:
        return None
    return closes[-1] / closes[-window - 1] - 1.0


def _compute_atr_ratio(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
    return _atr_ratio(series, index, int(params["window"]))


def _make_cross(up: bool):
    def compute(series: InstrumentSeries, index: int, params: dict[str, float]) -> float | None:
        closes = series.adjusted_close[: index + 1]
        short_n, long_n = int(params["short"]), int(params["long"])
        short_now = trailing_mean(closes, short_n)
        long_now = trailing_mean(closes, long_n)
        short_prev = trailing_mean(closes[:-1], short_n)
        long_prev = trailing_mean(closes[:-1], long_n)
        if None in (short_now, long_now, short_prev, long_prev):
            return None
        if up:
            return short_now / long_now - 1.0 if short_prev <= long_prev and short_now > long_now else None
        return long_now / short_now - 1.0 if short_prev >= long_prev and short_now < long_now else None
    return compute


def _p(name: str, default: float, minimum: float, maximum: float) -> dict[str, float]:
    return {"name": name, "default": default, "min": minimum, "max": maximum}


FACTOR_LIBRARY: Final[dict[str, dict]] = {
    "rsi": {
        "label": "RSI 相对强弱", "category": "momentum",
        "params": [_p("window", 14, 2, 60)],
        "output": "0~100 的数值，越低越弱势",
        "statement": "Wilder RSI：衡量最近 {window} 个交易日里涨跌力量的相对强弱。",
        "misread": "趋势市里 RSI 可以连续数周低于 30——超卖不等于会反弹（本产品内置的均值回归策略在合成历史上亏损超五成就是这个原因）。",
        "compute": _compute_rsi,
    },
    "sma_gap": {
        "label": "价格相对均线", "category": "trend",
        "params": [_p("window", 20, 2, 250)],
        "output": "偏离度：0.05 表示高于均线 5%",
        "statement": "收盘价相对 {window} 日简单均线的偏离比例。",
        "misread": "均线的滞后性天然存在：偏离度刚转正时，行情往往已经走了一段。",
        "compute": _compute_sma_gap,
    },
    "breakout_high": {
        "label": "创 N 日新高", "category": "breakout",
        "params": [_p("window", 20, 2, 250)],
        "output": "突破幅度（0.03 表示超过前高 3%）；未突破时条件不满足",
        "statement": "收盘价严格高于此前 {window} 个有效收盘的最高点。",
        "misread": "突破有假信号：突破后回落是最常见的亏损来源之一。",
        "compute": _make_breakout(high=True),
    },
    "breakdown_low": {
        "label": "跌破 N 日新低", "category": "breakout",
        "params": [_p("window", 10, 2, 250)],
        "output": "跌破深度；未跌破时条件不满足",
        "statement": "收盘价严格低于此前 {window} 个有效收盘的最低点。",
        "misread": "破位常被当作买点（抄底）也被当作卖点（止损）——同一条信息，方向取决于你的体系，工坊不会替你选。",
        "compute": _make_breakout(high=False),
    },
    "roc": {
        "label": "动量（N 日涨跌幅）", "category": "momentum",
        "params": [_p("window", 20, 2, 250)],
        "output": "区间涨跌幅：0.10 表示上涨 10%",
        "statement": "收盘价相对 {window} 个交易日前的涨跌幅。",
        "misread": "追动量买在高点、杀动量卖在低点，是动量因子最常见的误用。",
        "compute": _compute_roc,
    },
    "atr_ratio": {
        "label": "波动率（ATR 占价比）", "category": "volatility",
        "params": [_p("window", 14, 2, 60)],
        "output": "日均真实波幅 ÷ 收盘价：0.03 表示日均波动约 3%",
        "statement": "衡量当前波动水平；常用于过滤“太震荡”的行情或定仓位。",
        "misread": "高波动不等于机会，它同时放大盈利和亏损。",
        "compute": _compute_atr_ratio,
    },
    "ma_cross_up": {
        "label": "均线金叉", "category": "trend",
        "params": [_p("short", 5, 2, 60), _p("long", 20, 3, 250)],
        "output": "金叉当日的离散度；非金叉日条件不满足",
        "statement": "{short} 日均线上穿 {long} 日均线。",
        "misread": "金叉信号在震荡市里会反复出现和消失（骗线）。",
        "compute": _make_cross(up=True),
    },
    "ma_cross_down": {
        "label": "均线死叉", "category": "trend",
        "params": [_p("short", 5, 2, 60), _p("long", 20, 3, 250)],
        "output": "死叉当日的离散度；非死叉日条件不满足",
        "statement": "{short} 日均线下穿 {long} 日均线。",
        "misread": "死叉确认时价格通常已经低于交叉点，把它当卖点会系统性卖低。",
        "compute": _make_cross(up=False),
    },
}

NUMERIC_OPS: Final[dict[str, Callable[[float, float], bool]]] = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def factor_min_history(factor_id: str, params: dict[str, float]) -> int:
    """Smallest observation count so the factor's windows are defined."""
    spec = FACTOR_LIBRARY[factor_id]
    windows = [int(p["default"]) for p in spec["params"] if p["name"] in ("window", "long")]
    extra = 2 if factor_id in ("ma_cross_up", "ma_cross_down") else 1
    return max(windows, default=1) + extra


def evaluate_factor(factor_id: str, params: dict[str, float], series: InstrumentSeries,
                    index: int) -> float | None:
    """One factor value at one index; None = insufficient history."""
    spec = FACTOR_LIBRARY.get(factor_id)
    if spec is None:
        raise KeyError(factor_id)
    value = spec["compute"](series, index, params)
    if value is None or not math.isfinite(value):
        return None
    return value


def evaluate_condition(condition: dict, series: InstrumentSeries, index: int) -> tuple[bool, float | None]:
    """One condition: satisfied / not (insufficient history counts as not)."""
    value = evaluate_factor(condition["factor"], condition["params"], series, index)
    if value is None:
        return False, None
    op = condition["op"]
    if op == "true":
        return value > 0, value
    threshold = float(condition["threshold"])
    return NUMERIC_OPS[op](value, threshold), value
