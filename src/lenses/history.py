"""Small deterministic decision lenses, deliberately separate from replay math.

The lenses inspect the recorded replay state and a *strictly earlier* daily
market prefix.  They do not estimate returns, recommend trades, or reconstruct
position accounting.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

import pandas as pd


_COMMON_LIMITATIONS = [
    "本结果只核对已记录操作与固定规则的一致性，不构成预测、收益评价或投资建议。",
    "行情只按决策对应交易日之前的日收盘价截断；不会使用当日或之后的数据。",
    "导入的复权历史不能保证公司行为在当时已知；日期截断并不等同于公司行为的时点可得性保证。",
]
_MARKET_COLUMNS = ("date", "instrument", "close", "price_type", "data_source", "data_version", "is_synthetic")


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: object) -> pd.Timestamp | None:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    # This is only applied to the canonical market_date field, never event_time.
    # Keep its declared local calendar component while making DataFrame compares
    # timezone-neutral daily dates.
    if parsed.tzinfo is not None:
        parsed = parsed.tz_localize(None)
    return parsed.normalize()


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _condition(label: str, actual: float | None, operator: str,
               threshold: float | None, passed: bool | None, unit: str) -> dict[str, object]:
    return dict(label=label, actual=actual, operator=operator, threshold=threshold,
                passed=passed, unit=unit)


def _method(method_id: str, title: str, description: str, rule: str,
            parameters: dict[str, float], checks: list[dict[str, object]]) -> dict[str, object]:
    return dict(id=method_id, version="1", title=title, description=description,
                rule=rule, parameters=parameters, checks=checks)


def _actual(decision: Mapping[str, object], state: Mapping[str, object] | None,
            row: Mapping[str, object] | None) -> tuple[dict[str, object], list[str]]:
    """Return displayed recorded facts; never synthesize replay state."""
    problems: list[str] = []
    def choose(*values: object) -> object:
        return next((item for item in values if item is not None), None)
    # The projection is the displayed actual.  A canonical row may corroborate
    # it, but can never silently substitute different transaction facts.
    side = _text(decision.get("side"))
    quantity = _number(choose(decision.get("executed_quantity"), decision.get("quantity")))
    price = _number(decision.get("execution_price"))
    before_quantity = _number(state.get("quantity") if state else None)
    average_cost = _number(state.get("average_cost") if state else None)
    if side not in {"BUY", "SELL"}:
        problems.append("缺少或不支持的买卖方向")
    if quantity is None or quantity <= 0:
        problems.append("成交数量必须是正的有限数值")
    if price is None or price <= 0:
        problems.append("成交价格必须是正的有限数值")
    if before_quantity is None or before_quantity < 0:
        problems.append("缺少有效的操作前持仓状态")
    if before_quantity is not None and before_quantity > 0 and (average_cost is None or average_cost <= 0):
        problems.append("持仓状态缺少有效平均成本")
    if row is not None:
        row_side = _text(row.get("side"))
        row_quantity = _number(choose(row.get("executed_quantity"), row.get("quantity")))
        row_price = _number(choose(row.get("executed_price"), row.get("execution_price"), row.get("price")))
        if row_side not in {"BUY", "SELL"}:
            problems.append("规范成交记录缺少有效方向")
        elif row_side != side:
            problems.append("规范成交记录的方向与决策记录不一致")
        if row_quantity is None or row_quantity <= 0:
            problems.append("规范成交记录缺少有效数量")
        elif quantity is not None and row_quantity != quantity:
            problems.append("规范成交记录的数量与决策记录不一致")
        if row_price is None or row_price <= 0:
            problems.append("规范成交记录缺少有效价格")
        elif price is not None and row_price != price:
            problems.append("规范成交记录的价格与决策记录不一致")
    return (dict(side=side, quantity=quantity, price=price, quantity_before=before_quantity,
                 average_cost_before=average_cost), problems)


def _market_prefix(market_prices: pd.DataFrame, instrument_id: str,
                   market_date: pd.Timestamp | None, expected_synthetic: bool | None) -> tuple[pd.DataFrame | None, list[str]]:
    if market_date is None:
        return None, ["规范成交记录缺少交易所市场日期"]
    if not isinstance(market_prices, pd.DataFrame):
        return None, ["行情输入不是表格"]
    missing = [column for column in _MARKET_COLUMNS if column not in market_prices.columns]
    if missing:
        return None, ["行情缺少必填列：" + ", ".join(missing)]
    # Work on a new frame so the caller's data and order stay untouched.
    scoped = market_prices.loc[market_prices["instrument"] == instrument_id, list(_MARKET_COLUMNS)].copy()
    if scoped.empty:
        return None, ["该标的没有精确匹配的行情"]
    # Parse each value independently.  Pandas' vectorized mixed-timezone path
    # may retain timezone-aware values; _date deliberately drops the offset
    # without shifting the declared exchange-calendar date.
    dates = scoped["date"].map(_date)
    # An unparseable date cannot safely be classified as future, so fail closed.
    if dates.isna().any():
        return None, ["行情日期无效，无法安全确定其是否在决策前"]
    scoped["date"] = pd.to_datetime(dates, errors="coerce")
    prefix = scoped.loc[scoped["date"] < market_date].copy()
    if prefix.empty:
        return None, ["决策前没有可用日收盘价"]
    closes = pd.to_numeric(prefix["close"], errors="coerce")
    if (closes.isna().any() or (closes <= 0).any()
            or not pd.Series(closes).map(math.isfinite).all()):
        return None, ["决策前行情收盘价无效"]
    prefix["close"] = closes.astype(float)
    if prefix["date"].duplicated().any():
        return None, ["决策前行情存在重复日期，无法确定唯一收盘价"]
    allowed_price_types = {"close", "unadjusted_close", "adjusted_close", "total_return", "synthetic", "synthetic_unadjusted"}
    if (not prefix["price_type"].map(_text).isin(allowed_price_types).all()
            or not prefix["data_source"].map(_text).notna().all()
            or not prefix["data_version"].map(_text).notna().all()
            or not prefix["is_synthetic"].map(lambda item: isinstance(item, bool)).all()):
        return None, ["决策前行情价格口径、来源或合成标记无效"]
    if expected_synthetic is not None and not (prefix["is_synthetic"] == expected_synthetic).all():
        return None, ["决策前行情的合成标记与持仓数据层级不一致"]
    basis = prefix[["price_type", "data_source", "data_version", "is_synthetic"]].drop_duplicates()
    if len(basis) != 1 or basis.isna().any(axis=None):
        return None, ["决策前行情价格口径或来源版本冲突"]
    return prefix.sort_values("date", kind="mergesort").reset_index(drop=True), []


def _market_date_by_execution(executions: pd.DataFrame | None) -> tuple[dict[str, pd.Timestamp], set[str]]:
    if executions is None or not isinstance(executions, pd.DataFrame):
        return {}, set()
    if "execution_id" not in executions.columns or "market_date" not in executions.columns:
        return {}, set()
    result: dict[str, pd.Timestamp] = {}
    bad: set[str] = set()
    for _, item in executions.iterrows():
        key = _text(item.get("execution_id"))
        value = _date(item.get("market_date"))
        if key is None or value is None or key in result:
            if key is not None:
                bad.add(key)
            continue
        result[key] = value
    return result, bad


def _base_check(decision: Mapping[str, object], actual: dict[str, object], market_date: pd.Timestamp | None,
                observation_count: int, observed_through: str | None, fingerprint: str,
                verdict: str, expected: str, explanation: str, conditions: list[dict[str, object]],
                limitations: list[str]) -> dict[str, object]:
    return dict(decision_id=_text(decision.get("decision_id")) or "unavailable",
                execution_id=_text(decision.get("execution_id")) or "unavailable",
                state_before_ref=_text(decision.get("state_before_ref")) or "unavailable",
                occurred_at=_text(decision.get("occurred_at")) or "unavailable",
                market_date=market_date.date().isoformat() if market_date is not None else None,
                actual=actual, verdict=verdict, expected_action=expected, explanation=explanation,
                observed_through=observed_through, observation_count=observation_count,
                conditions=conditions, input_fingerprint=fingerprint, limitations=limitations)


def _trend_check(decision: Mapping[str, object], actual: dict[str, object], prefix: pd.DataFrame | None,
                 common: dict[str, object], issues: list[str]) -> dict[str, object]:
    if issues or prefix is None or len(prefix) < 20:
        why = issues or ["需要至少20个决策前有效日收盘价"]
        return _base_check(decision, actual, **common, verdict="insufficient", expected="无法判断",
            explanation="趋势均线条件缺少可靠输入。", conditions=[], limitations=why)
    close = float(prefix.iloc[-1].close); average = float(prefix.iloc[-20:].close.mean())
    above = close > average
    below = close < average
    held = (actual["quantity_before"] or 0) > 0
    side = actual["side"]
    if held and above: expected, aligned = "持有或加仓", side == "BUY"
    elif held and below: expected, aligned = "减仓或退出", side == "SELL"
    elif above: expected, aligned = "允许开仓", side == "BUY"
    elif below: expected, aligned = "等待", False
    else: expected, aligned = ("持有不变" if held else "等待"), False
    relation = "高于" if above else "低于" if below else "等于"
    action_note = "操作与趋势条件相容。" if aligned else "记录的操作与趋势条件不相容。"
    return _base_check(decision, actual, **common, verdict="aligned" if aligned else "different",
        expected=expected, explanation=f"前一有效收盘价为{close:g}，20日简单移动平均线（SMA20）为{average:g}；前者{relation}SMA20，{action_note}",
        conditions=[_condition("减仓／退出条件：前一收盘价 vs SMA20" if side == "SELL" else "开仓／加仓条件：前一收盘价 vs SMA20",
            close, "<" if side == "SELL" else ">", average, below if side == "SELL" else above, "price")], limitations=[])


def _breakout_check(decision: Mapping[str, object], actual: dict[str, object], prefix: pd.DataFrame | None,
                    common: dict[str, object], issues: list[str]) -> dict[str, object]:
    if issues or prefix is None or len(prefix) < 21:
        why = issues or ["突破规则需要至少21个决策前有效日收盘价"]
        return _base_check(decision, actual, **common, verdict="insufficient", expected="无法判断",
            explanation="突破条件缺少可靠输入。", conditions=[], limitations=why)
    close = float(prefix.iloc[-1].close)
    breakout = close > float(prefix.iloc[-21:-1].close.max())
    held = (actual["quantity_before"] or 0) > 0
    # The exit part independently needs ten preceding closes; 21 bars already supplies them.
    exit_rule = close < float(prefix.iloc[-11:-1].close.min())
    side = actual["side"]
    if not held:
        expected, aligned = ("突破后开仓", side == "BUY" and breakout) if breakout else ("等待", False)
    elif breakout:
        expected, aligned = "突破后加仓", side == "BUY"
    elif exit_rule:
        expected, aligned = "跌破10日低点后减仓或退出", side == "SELL"
    else:
        expected, aligned = "持有不变", False
    return _base_check(decision, actual, **common, verdict="aligned" if aligned else "different",
        expected=expected, explanation=("记录的操作符合突破／退出条件。" if aligned else "记录的操作不符合突破／退出条件。"),
        conditions=[_condition("前一有效收盘价 vs 此前20日最高收盘价", close, ">", float(prefix.iloc[-21:-1].close.max()), breakout, "price"),
                    _condition("前一有效收盘价 vs 此前10日最低收盘价", close, "<", float(prefix.iloc[-11:-1].close.min()), exit_rule, "price")], limitations=[])


def _cost_check(decision: Mapping[str, object], actual: dict[str, object], common: dict[str, object],
                issues: list[str]) -> dict[str, object]:
    if issues:
        return _base_check(decision, actual, **common, verdict="insufficient", expected="无法判断",
            explanation="成本加仓条件缺少可靠的已记录成交或状态。", conditions=[], limitations=issues)
    if actual["side"] != "BUY" or not (actual["quantity_before"] or 0) > 0:
        return _base_check(decision, actual, **common, verdict="not_applicable", expected="仅检查已有持仓后的买入",
            explanation="该规则只适用于已有持仓后的买入操作。", conditions=[], limitations=[])
    price = actual["price"]; cost = actual["average_cost_before"]
    assert isinstance(price, float) and isinstance(cost, float)
    passed = price >= cost
    return _base_check(decision, actual, **common, verdict="aligned" if passed else "different",
        expected="成交价不低于操作前平均成本的加仓", explanation=("成交价不低于操作前平均成本。" if passed else "成交价低于操作前平均成本。"),
        conditions=[_condition("成交价", price, ">=", cost, passed, "price")], limitations=["本规则只比较已记录成交价与未复算的回放平均成本；不使用行情价格。"])


def _state_issues(state: Mapping[str, object] | None, state_ref: str | None, execution_id: str | None,
                  subject: str, account: str, instrument: str | None) -> list[str]:
    if state is None:
        return ["未找到操作前回放状态"]
    issues: list[str] = []
    if _text(state.get("state_id")) != state_ref:
        issues.append("操作前状态标识与引用不一致")
    if _text(state.get("boundary")) != "before_execution":
        issues.append("状态不是操作前边界")
    if _text(state.get("execution_id")) != execution_id:
        issues.append("操作前状态对应的执行编号不一致")
    for key, expected in (("subject_id", subject), ("account_id", account), ("instrument_id", instrument)):
        if _text(state.get(key)) != expected:
            issues.append("操作前状态归属与当前持仓阶段不一致")
            break
    return issues


def _action_input(decision: Mapping[str, object], actual: dict[str, object], state_ref: str | None) -> dict[str, object]:
    """Only recorded decision facts and pre-state values belong in a fingerprint."""
    return dict(decision_id=_text(decision.get("decision_id")), execution_id=_text(decision.get("execution_id")),
                state_before_ref=state_ref, occurred_at=decision.get("occurred_at"), actual=actual)


def evaluate_episode_lenses(entry: dict[str, object], market_prices: pd.DataFrame,
                            executions: pd.DataFrame | None = None) -> dict[str, object]:
    """Evaluate the three Decision Lens v1 templates without mutating inputs."""
    entry = entry if isinstance(entry, Mapping) else {}
    episode = entry.get("episode") if isinstance(entry.get("episode"), Mapping) else {}
    instrument_meta = entry.get("instrument") if isinstance(entry.get("instrument"), Mapping) else {}
    instrument = _text(episode.get("instrument_id")) or _text(instrument_meta.get("instrument_id"))
    subject = _text(episode.get("subject_id")) or "unavailable"
    account = _text(episode.get("account_id")) or "unavailable"
    episode_id = _text(episode.get("episode_id")) or "unavailable"
    data_tier = _text(episode.get("data_tier")) or _text(instrument_meta.get("data_tier")) or "unavailable"
    states = entry.get("states_by_ref") if isinstance(entry.get("states_by_ref"), Mapping) else {}
    decisions = entry.get("decisions") if isinstance(entry.get("decisions"), (list, tuple)) else []
    dates, bad_ids = _market_date_by_execution(executions)
    decision_id_counts: dict[str, int] = {}
    execution_id_counts: dict[str, int] = {}
    for item in decisions:
        if isinstance(item, Mapping):
            for value, counts in ((_text(item.get("decision_id")), decision_id_counts),
                                  (_text(item.get("execution_id")), execution_id_counts)):
                if value is not None:
                    counts[value] = counts.get(value, 0) + 1
    expected_synthetic = True if data_tier == "synthetic" else (False if data_tier != "unavailable" else None)
    trend_checks: list[dict[str, object]] = []; breakout_checks: list[dict[str, object]] = []; cost_checks: list[dict[str, object]] = []
    for raw in decisions:
        decision = raw if isinstance(raw, Mapping) else {}
        execution_id = _text(decision.get("execution_id"))
        state_ref = _text(decision.get("state_before_ref"))
        state = states.get(state_ref) if state_ref is not None and isinstance(states.get(state_ref), Mapping) else None
        row = None
        if executions is not None and isinstance(executions, pd.DataFrame) and execution_id and "execution_id" in executions:
            matches = executions.loc[executions["execution_id"] == execution_id]
            if len(matches) == 1: row = matches.iloc[0].to_dict()
        actual, issues = _actual(decision, state, row)
        issues.extend(_state_issues(state, state_ref, execution_id, subject, account, instrument))
        if _text(decision.get("episode_id")) != episode_id: issues.append("决策不属于当前持仓阶段")
        decision_id = _text(decision.get("decision_id"))
        if decision_id is None: issues.append("决策缺少决策编号")
        elif decision_id_counts.get(decision_id, 0) != 1: issues.append("持仓阶段内决策编号不唯一")
        if execution_id is None: issues.append("决策缺少执行编号")
        elif execution_id_counts.get(execution_id, 0) != 1: issues.append("持仓阶段内执行编号不唯一")
        for key, expected in (("subject_id", subject), ("account_id", account), ("instrument_id", instrument)):
            supplied = _text(decision.get(key))
            if supplied is not None and supplied != expected:
                issues.append("决策归属与当前持仓阶段不一致")
            if row is not None and key in row and _text(row.get(key)) not in {None, expected}:
                issues.append("规范成交记录归属与当前持仓阶段不一致")
        if row is not None:
            row_instrument = next((_text(row.get(key)) for key in ("instrument_id", "instrument", "symbol", "security_id")
                                   if _text(row.get(key)) is not None), None)
            if row_instrument is not None and row_instrument != instrument:
                issues.append("规范成交记录标的与当前持仓阶段不一致")
        if not instrument: issues.append("持仓阶段缺少标的标识")
        market_date = dates.get(execution_id) if execution_id else None
        if execution_id in bad_ids: issues.append("规范成交记录的执行编号或市场日期不唯一")
        if executions is not None and row is None: issues.append("未找到唯一的规范成交记录")
        prefix, market_issues = _market_prefix(market_prices, instrument or "", market_date, expected_synthetic)
        observed = prefix.iloc[-1].date.date().isoformat() if prefix is not None else None
        count = len(prefix) if prefix is not None else 0
        action = _action_input(decision, actual, state_ref)
        market_input = dict(action=action, market_date=market_date,
                            prefix=(prefix.to_dict("records") if prefix is not None else []))
        trend_common = dict(market_date=market_date, observation_count=count, observed_through=observed,
                            fingerprint=_fingerprint(dict(method_id="trend_ma20", method_version="1", **market_input)))
        breakout_common = dict(market_date=market_date, observation_count=count, observed_through=observed,
                               fingerprint=_fingerprint(dict(method_id="closing_breakout20", method_version="1", **market_input)))
        cost_common = dict(market_date=market_date, observation_count=0, observed_through=None,
                           fingerprint=_fingerprint(dict(method_id="cost_addition", method_version="1", action=action)))
        trend_checks.append(_trend_check(decision, actual, prefix, trend_common, issues + market_issues))
        breakout_checks.append(_breakout_check(decision, actual, prefix, breakout_common, issues + market_issues))
        cost_checks.append(_cost_check(decision, actual, cost_common, issues))
    return dict(schema_version="decision_lens.v1", episode_id=episode_id, subject_id=subject,
        account_id=account, instrument_id=instrument or "unavailable", data_tier=data_tier,
        temporal_policy="prior_daily_close_only", limitations=list(_COMMON_LIMITATIONS), methods=[
            _method("trend_ma20", "20日均线趋势", "以决策前最近有效收盘价和20日均线核对操作方向。", "前一有效收盘价高于20日均线时允许开仓／加仓；持仓跌破时应减仓或退出。", {"window": 20.0}, trend_checks),
            _method("closing_breakout20", "20日收盘突破", "以决策前日收盘价核对20日突破和10日低点退出条件。", "突破严格高于此前20个收盘价；持仓时跌破此前10日低点才允许卖出。", {"breakout_window": 20.0, "exit_window": 10.0}, breakout_checks),
            _method("cost_addition", "成本加仓", "仅核对已有持仓后的买入成交价是否不低于操作前平均成本。", "仅当已有持仓且为买入时，成交价应大于或等于回放操作前平均成本。", {"minimum_cost_ratio": 1.0}, cost_checks),
        ])
