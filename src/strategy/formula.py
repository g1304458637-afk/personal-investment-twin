"""Formula DSL (L4): a restricted expression language for strategy rules.

Users write one-line formulas for entry and exit:

    entry: rsi(14) < 30 or close > highest(20)
    exit:  close < lowest(10)

Design (per docs/STRATEGY_LADDER.md L4, referencing qlib's operator
semantics and the freqtrade anti-lookahead checklist):

- Parsed with Python's ``ast`` under a strict node whitelist — no
  attribute access, no subscripts, no calls except whitelisted factor
  functions, no names except whitelisted fields, numeric constants only.
  Arbitrarily clever code is grammatically impossible.
- All factor functions are strictly backward-looking (they read bars up to
  and including the signal day) — the point-in-time discipline is
  guaranteed by the function library, not by user discipline.
- The parsed AST is serializable data; evaluation is deterministic.
- ``entry_price`` is allowed only in exit formulas (it exists only while
  holding); the interpreter passes it from the position view.
"""
from __future__ import annotations

import ast
from typing import Any, Mapping

from src.strategy.signals import prior_extreme, trailing_mean
from src.strategy.rsi_state import wilder_rsi_at
from src.strategy.factors import _rsi

FORMULA_SCHEMA_VERSION = "user_strategy_formula.v1"


class FormulaError(ValueError):
    """The formula text is not a valid expression in the restricted DSL."""


def _mean(closes: tuple[float, ...]) -> float | None:
    return sum(closes) / len(closes) if closes else None


def _ema(closes: tuple[float, ...]) -> float | None:
    if not closes:
        return None
    n = len(closes)
    alpha = 2.0 / (n + 1)
    ema = closes[0]
    for close in closes[1:]:
        ema = alpha * close + (1 - alpha) * ema
    return ema


def _closes(series, index: int, count: int, *, include_current: bool) -> tuple[float, ...] | None:
    end = index + 1 if include_current else index
    start = end - count
    if start < 0 or end > len(series.adjusted_close) or count <= 0:
        return None
    return series.adjusted_close[start:end]


def _f_sma(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]), include_current=True)
    return _mean(closes) if closes else None


def _f_ema(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]), include_current=True)
    return _ema(closes) if closes else None


def _f_highest(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]), include_current=False)
    return max(closes) if closes else None


def _f_lowest(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]), include_current=False)
    return min(closes) if closes else None


def _f_rsi(series, index, args) -> float | None:
    # Same Wilder recursion as the v2 factor library (factors._rsi): the same
    # indicator name must produce the same value in both user modes. The
    # previous local copy sliced exactly window+1 closes, so its smoothing
    # loop never ran and formula mode silently computed a simple-average RSI.
    # The incremental fold below is bit-identical to factors._rsi.
    return wilder_rsi_at(series, index, int(args[0]))


def _f_roc(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]) + 1, include_current=True)
    if not closes or closes[0] <= 0:
        return None
    return closes[-1] / closes[0] - 1.0


def _f_atr_ratio(series, index, args) -> float | None:
    window = int(args[0])
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
    close = series.bars[index].close / series.split_factors[index]
    atr = sum(trs) / len(trs)
    return atr / close if close > 0 else None


def _f_volume_ratio(series, index, args) -> float | None:
    window = int(args[0])
    start = index - window
    if start < 0 or index >= len(series.bars):
        return None
    vols = [series.bars[i].volume for i in range(start, index + 1)]
    if any(v is None or v <= 0 for v in vols):
        return None
    base = vols[:-1]
    avg = sum(base) / len(base) if base else 0.0
    if avg <= 0:
        return None
    return vols[-1] / avg


def _f_range_pos(series, index, args) -> float | None:
    closes = _closes(series, index, int(args[0]), include_current=True)
    if not closes:
        return None
    hi, lo = max(closes), min(closes)
    return 0.5 if hi <= lo else (closes[-1] - lo) / (hi - lo)


def _f_streak_down(series, index, args) -> float | None:
    count = 0
    i = index
    while i > 0 and series.adjusted_close[i] < series.adjusted_close[i - 1]:
        count += 1
        i -= 1
    return float(count)


def _f_cross(series, index, args, up: bool) -> float | None:
    short_n, long_n = int(args[0]), int(args[1])
    closes = series.adjusted_close[: index + 1]
    # Complete trailing windows only (same semantics as the factor library's
    # trailing_mean): a partial window must yield "unknown", not a partial mean.
    if len(closes) < max(short_n, long_n) + 1:
        return None
    prev = closes[:-1]
    short_now, long_now = _mean(closes[-short_n:]), _mean(closes[-long_n:])
    short_prev, long_prev = _mean(prev[-short_n:]), _mean(prev[-long_n:])
    if None in (short_now, long_now, short_prev, long_prev):
        return None
    if up and short_prev <= long_prev and short_now > long_now:
        return short_now / long_now - 1.0
    if not up and short_prev >= long_prev and short_now < long_now:
        return long_now / short_now - 1.0
    return None


def _f_atr(series, index, args) -> float | None:
    window = int(args[0])
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
    return sum(trs) / len(trs)


# name → (min_args, max_args, compute, description)
FORMULA_FUNCTIONS: dict[str, dict] = {
    "sma": {"args": 1, "compute": _f_sma, "desc": "sma(20)：最近 20 个收盘的简单均线"},
    "ema": {"args": 1, "compute": _f_ema, "desc": "ema(20)：最近 20 个收盘的指数均线"},
    "highest": {"args": 1, "compute": _f_highest, "desc": "highest(20)：此前 20 个收盘的最高价（不含当日）"},
    "lowest": {"args": 1, "compute": _f_lowest, "desc": "lowest(10)：此前 10 个收盘的最低价（不含当日）"},
    "rsi": {"args": 1, "compute": _f_rsi, "desc": "rsi(14)：相对强弱指标"},
    "roc": {"args": 1, "compute": _f_roc, "desc": "roc(20)：20 日涨跌幅（小数）"},
    "atr_ratio": {"args": 1, "compute": _f_atr_ratio, "desc": "atr_ratio(14)：ATR 占收盘价比"},
    "atr": {"args": 1, "compute": _f_atr, "desc": "atr(14)：ATR 绝对值"},
    "volume_ratio": {"args": 1, "compute": _f_volume_ratio, "desc": "volume_ratio(20)：量比（真实行情有效）"},
    "range_pos": {"args": 1, "compute": _f_range_pos, "desc": "range_pos(20)：N 日区间位置 0~1"},
    "streak_down": {"args": 0, "compute": _f_streak_down, "desc": "streak_down()：连续收跌天数"},
    "cross_up": {"args": 2, "compute": lambda s, i, a: _f_cross(s, i, a, up=True),
                 "desc": "cross_up(5, 20)：短均线上穿长均线（返回离散度，非交叉日为空）"},
    "cross_down": {"args": 2, "compute": lambda s, i, a: _f_cross(s, i, a, up=False),
                   "desc": "cross_down(5, 20)：短均线下穿长均线"},
}

_ALLOWED_NAMES = {"close", "entry_price"}
_ALLOWED_COMPARE = {ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq}
_ALLOWED_BIN = {ast.Add, ast.Sub, ast.Mult, ast.Div}


def parse_formula(text: str) -> ast.Expression:
    """Parse and whitelist-check one formula; raise FormulaError otherwise."""
    if not isinstance(text, str) or not (1 <= len(text.strip()) <= 300):
        raise FormulaError("公式长度需要 1~300 字符")
    if "__" in text or "import" in text or "lambda" in text or "eval" in text or "exec" in text:
        raise FormulaError("公式含被禁止的内容")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"公式语法错误：{exc.msg}") from exc
    _check_node(tree.body)
    return tree


def _check_node(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _check_node(node.body)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise FormulaError("公式只允许数字常量")
    elif isinstance(node, ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise FormulaError(f"不允许的名称：{node.id}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FORMULA_FUNCTIONS:
            raise FormulaError("只允许调用内置因子函数")
        spec = FORMULA_FUNCTIONS[node.func.id]
        if len(node.args) != spec["args"] or node.keywords:
            raise FormulaError(f"{node.func.id} 需要 {spec['args']} 个参数")
        for arg in node.args:
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, (int, float)) \
                    or isinstance(arg.value, bool) or arg.value <= 0:
                raise FormulaError(f"{node.func.id} 的参数必须是正数")
    elif isinstance(node, ast.Compare):
        _check_node(node.left)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaError("一次只允许一个比较")
        if not isinstance(node.ops[0], tuple(_ALLOWED_COMPARE)):
            raise FormulaError("不支持的比较符")
        _check_node(node.comparators[0])
    elif isinstance(node, ast.BinOp):
        _check_node(node.left)
        if not isinstance(node.op, tuple(_ALLOWED_BIN)):
            raise FormulaError("不支持的运算符")
        _check_node(node.right)
    elif isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise FormulaError("不支持的逻辑符")
        for value in node.values:
            _check_node(value)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.Not)):
            raise FormulaError("不支持的一元运算符")
        _check_node(node.operand)
    else:
        raise FormulaError(f"公式中不允许 {type(node).__name__} 元素")


def formula_windows(text: str) -> int:
    """Max numeric argument across calls (+2 warm-up), min 21."""
    tree = ast.parse(text.strip(), mode="eval")
    numbers: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                    numbers.append(int(arg.value))
    return max(numbers, default=0) + 2


def formula_factor_names(text: str) -> set[str]:
    tree = ast.parse(text.strip(), mode="eval")
    return {node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def eval_node(node: ast.AST, series, index: int, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "close":
            return series.adjusted_close[index]
        if node.id == "entry_price":
            return context.get("entry_price")
        raise FormulaError(f"不允许的名称：{node.id}")
    if isinstance(node, ast.Call):
        spec = FORMULA_FUNCTIONS[node.func.id]
        args = [float(arg.value) for arg in node.args]
        return spec["compute"](series, index, args)
    if isinstance(node, ast.Compare):
        left = eval_node(node.left, series, index, context)
        right = eval_node(node.comparators[0], series, index, context)
        # A missing operand (insufficient history / unavailable data) makes the
        # comparison unknown — never False, otherwise `not` would flip it to a
        # confirmed entry signal.
        if left is None or right is None:
            return None
        op = node.ops[0]
        return {ast.Gt: lambda: left > right, ast.GtE: lambda: left >= right,
                ast.Lt: lambda: left < right, ast.LtE: lambda: left <= right,
                ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right,
                }[type(op)]()
    if isinstance(node, ast.BoolOp):
        # Three-state logic: unknown (None) operands propagate instead of being
        # coerced. AND is False once any operand is known-false; OR is True
        # once any operand is known-true; otherwise any unknown keeps the
        # result unknown ("insufficient data" is never counted as satisfied).
        values = [eval_node(v, series, index, context) for v in node.values]
        known_count = sum(1 for v in values if v is not None)
        if isinstance(node.op, ast.And):
            if any(v is not None and not v for v in values):
                return False
            return True if known_count == len(values) else None
        if any(v is not None and v for v in values):
            return True
        return False if known_count == len(values) else None
    if isinstance(node, ast.UnaryOp):
        value = eval_node(node.operand, series, index, context)
        if isinstance(node.op, ast.Not):
            return None if value is None else not value
        return -value if value is not None else None
    if isinstance(node, ast.BinOp):
        left = eval_node(node.left, series, index, context)
        right = eval_node(node.right, series, index, context)
        if left is None or right is None:
            return None
        return {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right, ast.Div: lambda: left / right if right != 0 else None,
                }[type(node.op)]()
    raise FormulaError(f"公式中不允许 {type(node).__name__} 元素")


def eval_formula(tree: ast.Expression, series, index: int,
                 context: Mapping[str, Any] | None = None) -> bool:
    """Evaluate one entry/exit formula for the given bar.

    Returns True only when the formula is demonstrably satisfied. Unknown
    sub-results (insufficient history, unavailable data such as volume on a
    synthetic universe) propagate as None and count as not satisfied — the
    "never guess" rule also holds under negation.
    """
    result = eval_node(tree.body, series, index, context or {})
    return result is not None and bool(result)
