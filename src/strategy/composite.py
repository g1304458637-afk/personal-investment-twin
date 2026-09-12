"""Composite user-defined strategies: spec validation + generic interpreter.

A user strategy is *data* (a JSON spec), never code.  This module is the
single interpreter the engine calls; it validates the spec fail-closed and
auto-generates the provenance rule table.  Structural notes:

- No field of the spec can name a security: strategies express conditions
  over the whole point-in-time universe, never specific instruments
  (a hard architectural answer to "sharing = stock tipping").
- Entry conditions are AND-ed (1..3); exits are OR-ed (0..2) plus an
  optional fixed stop.  At least one exit mechanism is required.
- Sizing is equal-weight (engine default) or risk-unit (1%×equity÷ATR,
  notional-capped, computed per candidate via intended_quantity).
- Insufficient history counts as "condition not satisfied", never a guess.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from src.strategy.data import SimulationData
from src.strategy.factors import (
    FACTOR_LIBRARY,
    evaluate_condition,
    factor_min_history,
)
from src.strategy.spec import StrategySpec

SCHEMA_VERSION = "user_strategy.v2"
LEGACY_VERSIONS = {"user_strategy.v1"}
MAX_ENTRY_CONDITIONS = 5
MAX_ANYOF_CONDITIONS = 3
MAX_EXIT_CONDITIONS = 2
MAX_ENTRY_CONDITIONS = 3
MAX_EXIT_CONDITIONS = 2
MAX_POSITIONS_RANGE = (1, 8)
USER_OPS = {"gt", "gte", "lt", "lte", "true"}


class UserStrategyError(ValueError):
    """The spec is malformed, out of range, or tries to escape the sandbox."""


def _condition(raw: Any, where: str) -> dict:
    if not isinstance(raw, Mapping):
        raise UserStrategyError(f"{where}: 条件必须是对象")
    extra = set(raw) - {"factor", "params", "op", "threshold"}
    if extra:
        raise UserStrategyError(f"{where}: 条件含未知字段 {sorted(extra)}")
    factor = raw.get("factor")
    if factor not in FACTOR_LIBRARY:
        raise UserStrategyError(f"{where}: 未知因子 {factor!r}")
    params: dict[str, float] = {}
    raw_params = raw.get("params") or {}
    if not isinstance(raw_params, Mapping):
        raise UserStrategyError(f"{where}: 参数必须是对象")
    known = {entry["name"] for entry in FACTOR_LIBRARY[factor]["params"]}
    unknown = set(raw_params) - known
    if unknown:
        # Blocks, e.g., a "symbol" key: strategies cannot bind securities.
        raise UserStrategyError(f"{where}: 条件含未知参数 {sorted(unknown)}")
    for entry in FACTOR_LIBRARY[factor]["params"]:
        name = entry["name"]
        value = raw_params.get(name, entry["default"])
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise UserStrategyError(f"{where}: 参数 {name} 必须是有限数值")
        if not entry["min"] <= value <= entry["max"]:
            raise UserStrategyError(f"{where}: 参数 {name} 超出允许范围 {entry['min']}~{entry['max']}")
        params[name] = float(value)
    op = raw.get("op", "true")
    if op not in USER_OPS:
        raise UserStrategyError(f"{where}: 不支持的比较 {op!r}")
    threshold: float | None = None
    if op != "true":
        threshold = raw.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold):
            raise UserStrategyError(f"{where}: 阈值必须是有限数值")
        threshold = float(threshold)
    if op == "true" and threshold is not None:
        raise UserStrategyError(f"{where}: 该因子不接受阈值")
    return {"factor": factor, "params": params, "op": op, "threshold": threshold}


def _conditions_list(raw: Any, where: str, maximum: int) -> list[dict]:
    if not isinstance(raw, list) or not (1 <= len(raw) <= maximum):
        raise UserStrategyError(f"{where}: 需要 1~{maximum} 个条件")
    return [_condition(item, f"{where}[{index}]") for index, item in enumerate(raw)]


def validate_user_strategy(raw: Mapping[str, Any]) -> dict:
    """Normalize a raw workshop spec; fail closed on anything unexpected."""
    if not isinstance(raw, Mapping) or raw.get("schema_version") not in LEGACY_VERSIONS | {SCHEMA_VERSION}:
        raise UserStrategyError("schema_version 必须是 " + " 或 ".join(sorted(LEGACY_VERSIONS | {SCHEMA_VERSION})))
    version = raw["schema_version"]
    is_v2 = version == SCHEMA_VERSION
    allowed_top = {"schema_version", "name", "entry", "exit", "sizing", "constraints", "ranking"}
    if is_v2:
        allowed_top |= {"adds"}
    extra = set(raw) - allowed_top
    if extra:
        raise UserStrategyError(f"策略含未知字段 {sorted(extra)}（策略不能绑定具体标的或注入逻辑）")
    name = raw.get("name")
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 60):
        raise UserStrategyError("策略名称需要 1~60 个字符")
    entry_raw = raw.get("entry")
    entry_allowed = {"all_of", "any_of"} if is_v2 else {"all_of"}
    if not isinstance(entry_raw, Mapping) or set(entry_raw) - entry_allowed:
        raise UserStrategyError(f"entry 只允许 {sorted(entry_allowed)} 条件组")
    entry_count_v2 = len(entry_raw.get("all_of") or [])
    any_of_raw = entry_raw.get("any_of") or [] if is_v2 else []
    if is_v2:
        if not isinstance(any_of_raw, list) or len(any_of_raw) > MAX_ANYOF_CONDITIONS:
            raise UserStrategyError(f"entry.any_of 最多 {MAX_ANYOF_CONDITIONS} 个条件")
        if entry_count_v2 + len(any_of_raw) < 1 or entry_count_v2 + len(any_of_raw) > 6:
            raise UserStrategyError("entry 条件总数需要 1~6 个")
    if not is_v2 and entry_count_v2 < 1:
        raise UserStrategyError("entry 至少需要 1 个条件")
    any_of = _conditions_list(any_of_raw, "entry.any_of", MAX_ANYOF_CONDITIONS) if is_v2 and any_of_raw else []
    entry = {"all_of": _conditions_list(entry_raw.get("all_of"), "entry", MAX_ENTRY_CONDITIONS) if entry_count_v2 else [],
             "any_of": any_of}
    exit_raw = raw.get("exit")
    exit_allowed = {"any_of", "stop_loss_pct", "atr_trailing_mult"} if is_v2 else {"any_of", "stop_loss_pct"}
    if not isinstance(exit_raw, Mapping) or set(exit_raw) - exit_allowed:
        raise UserStrategyError(f"exit 只允许 {sorted(exit_allowed)}")
    exit_conditions = _conditions_list(exit_raw.get("any_of", []), "exit", MAX_EXIT_CONDITIONS) \
        if exit_raw.get("any_of") else []
    stop = exit_raw.get("stop_loss_pct")
    stop_pct: float | None = None
    if stop is not None:
        if not isinstance(stop, (int, float)) or isinstance(stop, bool) or not math.isfinite(stop) \
                or not 0.01 <= float(stop) <= 0.5:
            raise UserStrategyError("stop_loss_pct 允许范围 0.01~0.5")
        stop_pct = float(stop)
    atr_mult: float | None = None
    if is_v2 and exit_raw.get("atr_trailing_mult") is not None:
        atr_mult = exit_raw.get("atr_trailing_mult")
        if not isinstance(atr_mult, (int, float)) or isinstance(atr_mult, bool) \
                or not math.isfinite(atr_mult) or not 1.0 <= float(atr_mult) <= 5.0:
            raise UserStrategyError("atr_trailing_mult 允许范围 1.0~5.0")
        atr_mult = float(atr_mult)
    if not exit_conditions and stop_pct is None and atr_mult is None:
        raise UserStrategyError("至少需要一种退出机制（退出条件、止损或跟踪止损）")
    adds: dict[str, Any] | None = None
    if is_v2 and raw.get("adds") is not None:
        adds_raw = raw.get("adds")
        if not isinstance(adds_raw, Mapping) or set(adds_raw) - {"max_units"}:
            raise UserStrategyError("adds 只允许 max_units")
        max_units = adds_raw.get("max_units", 2)
        if not isinstance(max_units, int) or isinstance(max_units, bool) or not 2 <= max_units <= 4:
            raise UserStrategyError("adds.max_units 允许范围 2~4")
        adds = {"max_units": max_units}
    sizing_raw = raw.get("sizing")
    if not isinstance(sizing_raw, Mapping):
        raise UserStrategyError("sizing 缺失")
    mode = sizing_raw.get("mode")
    constraints_raw = raw.get("constraints") or {}
    if not isinstance(constraints_raw, Mapping) or set(constraints_raw) - {"max_positions"}:
        raise UserStrategyError("constraints 只允许 max_positions")
    max_positions = constraints_raw.get("max_positions", 4)
    if not isinstance(max_positions, int) or isinstance(max_positions, bool) \
            or not MAX_POSITIONS_RANGE[0] <= max_positions <= MAX_POSITIONS_RANGE[1]:
        raise UserStrategyError("max_positions 允许范围 1~8")
    sizing: dict[str, Any]
    if mode == "equal_weight":
        if set(sizing_raw) - {"mode", "fraction"}:
            raise UserStrategyError("sizing 含未知字段")
        fraction = sizing_raw.get("fraction", 0.25)
        if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) \
                or not math.isfinite(fraction) or not 0.05 <= float(fraction) <= 1.0:
            raise UserStrategyError("fraction 允许范围 0.05~1.0")
        sizing = {"mode": "equal_weight", "fraction": float(fraction)}
    elif mode == "risk_unit":
        if set(sizing_raw) - {"mode", "risk_fraction", "notional_cap"}:
            raise UserStrategyError("sizing 含未知字段")
        risk = sizing_raw.get("risk_fraction", 0.01)
        cap = sizing_raw.get("notional_cap", 0.25)
        for label, value, lo, hi in (("risk_fraction", risk, 0.001, 0.05), ("notional_cap", cap, 0.05, 1.0)):
            if not isinstance(value, (int, float)) or isinstance(value, bool) \
                    or not math.isfinite(value) or not lo <= float(value) <= hi:
                raise UserStrategyError(f"{label} 允许范围 {lo}~{hi}")
        sizing = {"mode": "risk_unit", "risk_fraction": float(risk), "notional_cap": float(cap)}
    else:
        raise UserStrategyError("sizing.mode 必须是 equal_weight 或 risk_unit")
    ranking_raw = raw.get("ranking")
    ranking: dict[str, Any] | None = None
    if ranking_raw is not None:
        if not isinstance(ranking_raw, Mapping) or set(ranking_raw) - {"factor", "params", "direction"}:
            raise UserStrategyError("ranking 只允许 factor/params/direction")
        direction = ranking_raw.get("direction", "desc")
        if direction not in {"desc", "asc"}:
            raise UserStrategyError("ranking.direction 必须是 desc 或 asc")
        ranking_condition = _condition(
            {"factor": ranking_raw.get("factor"), "params": ranking_raw.get("params") or {},
             "op": "true"}, "ranking")
        ranking = {"factor": ranking_condition["factor"], "params": ranking_condition["params"],
                   "direction": direction}
    windows = [factor_min_history(c["factor"], c["params"]) for c in (*entry["all_of"], *any_of, *exit_conditions)]
    if ranking is not None:
        windows.append(factor_min_history(ranking["factor"], ranking["params"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "name": name.strip(),
        "entry": {"all_of": entry["all_of"], "any_of": any_of},
        "exit": {"any_of": exit_conditions, "stop_loss_pct": stop_pct, "atr_trailing_mult": atr_mult},
        "adds": adds,
        "sizing": sizing,
        "constraints": {"max_positions": max_positions},
        "ranking": ranking,
        "min_history": max(windows, default=21) + 1,
    }


def strategy_id_for(normalized: Mapping[str, Any]) -> str:
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "user_" + hashlib.sha256(canonical.encode()).hexdigest()[:10]


def _condition_statement(where: str, condition: Mapping[str, Any]) -> str:
    factor = FACTOR_LIBRARY[condition["factor"]]
    params_text = "、".join(f"{p['name']}={condition['params'][p['name']]:g}" for p in factor["params"])
    if condition["op"] == "true":
        return f"{where}：{factor['label']}（{params_text}）成立"
    symbols = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
    return (f"{where}：{factor['label']}（{params_text}）{symbols[condition['op']]} "
            f"{condition['threshold']:g}")


def build_user_strategy_spec(raw: Mapping[str, Any]) -> tuple[StrategySpec, dict]:
    """Validate and wrap into the engine's StrategySpec (provenance auto-generated)."""
    normalized = validate_user_strategy(raw)
    strategy_id = strategy_id_for(normalized)
    rules: list[dict[str, str]] = []
    for condition in normalized["entry"]["all_of"]:
        rules.append({"rule_id": f"U_entry_{len(rules) + 1}", "source": "user_defined",
                      "statement": _condition_statement("入场条件", condition)})
    if normalized["ranking"] is not None:
        rules.append({"rule_id": "U_ranking", "source": "user_defined",
                      "statement": "候选超过剩余仓位时，按排序因子的取值排序（" + normalized["ranking"]["direction"] + "）。"})
    for condition in normalized["entry"]["any_of"]:
        rules.append({"rule_id": f"U_entry_any_{len(rules) + 1}", "source": "user_defined",
                      "statement": "任一满足：" + _condition_statement("入场条件", condition)})
    for condition in normalized["exit"]["any_of"]:
        rules.append({"rule_id": f"U_exit_{len(rules) + 1}", "source": "user_defined",
                      "statement": _condition_statement("退出条件", condition)})
    if normalized["adds"] is not None:
        rules.append({"rule_id": "U_adds", "source": "user_defined",
                      "statement": f"加仓规则：入场条件再次满足时追加 1 个单元，同一标的最多 {normalized['adds']['max_units']} 个单元。"})
    if normalized["exit"]["atr_trailing_mult"] is not None:
        rules.append({"rule_id": "U_trailing", "source": "user_defined",
                      "statement": f"ATR 跟踪止损：止损每日上移至 前收 − {normalized['exit']['atr_trailing_mult']}×ATR(14)，只升不降。"})
    if normalized["exit"]["stop_loss_pct"] is not None:
        rules.append({"rule_id": "U_stop", "source": "user_defined",
                      "statement": f"固定止损：低于成交价 {normalized['exit']['stop_loss_pct'] * 100:.0f}%。"})
    rules.append({"rule_id": "U_sizing", "source": "user_defined",
                  "statement": ("等权仓位：每仓目标=当日净值×%.0f%%。"
                                % (normalized["sizing"]["fraction"] * 100))
                  if normalized["sizing"]["mode"] == "equal_weight"
                  else "风险定尺：单元=风险比例×净值÷ATR，名义敞口设上限。"})
    rules.append({"rule_id": "U_no_add", "source": "user_defined",
                  "statement": "不加仓：同一标的同时至多一个仓位，退出后可再次入场。"})
    rules.append({"rule_id": "SYS_execution", "source": "system_execution",
                  "statement": "固定执行模型：市价单次日开盘成交、100股整手、佣金0.03%（最低5元）双边、印花税0.1%卖出、涨停开盘拒买、退市强清。"})
    rules.append({"rule_id": "SYS_provenance", "source": "system_execution",
                  "statement": "本策略为用户在因子库内自建的组合，不是经典策略，也不是任何形式的推荐。"})
    sizing = normalized["sizing"]
    params: dict[str, float | int | str] = {
        "min_history": normalized["min_history"],
        "max_positions": normalized["constraints"]["max_positions"],
        "position_fraction": sizing["fraction"] if sizing["mode"] == "equal_weight" else 0.25,
        "lot_size": 100,
        "stop_loss_pct": normalized["exit"]["stop_loss_pct"] or 0.0,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.001,
        "slippage_rate": 0.0,
        "price_limit_pct": 0.10,
        "initial_cash": 1_000_000.0,
        "currency": "CNY",
    }
    spec = StrategySpec(
        strategy_id=strategy_id, version="1",
        title=f"自建策略：{normalized['name']}",
        description="用户在因子库内自建的规则组合；由确定性解释器执行，与真实账户完全隔离，不是投资建议。",
        rule_table=tuple(rules), params=params,
    )
    return spec, normalized


@dataclass(frozen=True, slots=True)
class Signal:
    instrument: str
    kind: str
    strength: float | None
    reason_text: str
    conditions: tuple[dict, ...]
    reason_code: str = "user_entry"
    intended_quantity: float | None = None


def make_provider(normalized: Mapping[str, Any]):
    """Build the engine signal provider for one validated user strategy."""

    def _entry_signal(instrument: str, series, index: int, equity_value: float, lot: int):
        all_values = [evaluate_condition(c, series, index) for c in normalized["entry"]["all_of"]]
        all_ok = all(satisfied for satisfied, _ in all_values) if normalized["entry"]["all_of"] else True
        any_values = [evaluate_condition(c, series, index) for c in normalized["entry"]["any_of"]]
        any_ok = any(satisfied for satisfied, _ in any_values) if any_values else True
        if not (all_ok and any_ok):
            return None
        statements = [_condition_statement("入场条件", c) for c in normalized["entry"]["all_of"]] + \
                     [_condition_statement("任一满足", c) for c in normalized["entry"]["any_of"]]
        ranking = normalized["ranking"]
        strength = values_value(all_values) if ranking is None else evaluate_factor(
            ranking["factor"], ranking["params"], series, index)
        intended = unit_sizing(series, index, equity_value, lot)
        return Signal(
            instrument=instrument, kind="entry_candidate",
            strength=strength if strength is not None else 0.0,
            reason_text="；".join(statements),
            conditions=(), reason_code="user_entry", intended_quantity=intended)

    def unit_sizing(series, index, equity_value: float, lot: int) -> float | None:
        if normalized["sizing"]["mode"] != "risk_unit" or equity_value <= 0:
            return None
        from src.strategy.factors import _atr_ratio
        n = _atr_ratio(series, index, 14)
        price = series.bars[index].close / series.split_factors[index]
        if not n or n <= 0 or price <= 0:
            return None
        sizing = normalized["sizing"]
        shares = min(sizing["risk_fraction"] * equity_value / (n * price),
                     sizing["notional_cap"] * equity_value / price)
        return float(int(shares / lot) * lot)

    def values_value(values):
        return values[0][1] if values else None

    def provider(spec_params: dict[str, float | int | str], data: SimulationData,
                 day: date, held: set[str], pending_buy_instruments: set[str],
                 account_view: dict | None = None):
        equity = float((account_view or {}).get("equity") or 0.0)
        view = (account_view or {}).get("positions") or {}
        exits: list[Signal] = []
        candidates: list[Signal] = []
        min_history = int(spec_params["min_history"])
        lot = int(spec_params["lot_size"])
        for instrument in sorted(data.listed_on(day)):
            if instrument in pending_buy_instruments:
                continue
            series = data.series[instrument]
            if series.bar_on(day) is None:
                continue
            index = series.index_on_or_before(day)
            assert index is not None
            if index + 1 < min_history:
                continue
            if instrument in held:
                position_view = view.get(instrument) or {}
                for condition in normalized["exit"]["any_of"]:
                    satisfied, value = evaluate_condition(condition, series, index)
                    if satisfied:
                        exits.append(Signal(
                            instrument=instrument, kind="exit", strength=None,
                            reason_text=_condition_statement("退出条件", condition)
                            + f"（当前值 {value:.4g}）",
                            conditions=({"label": _condition_statement("退出条件", condition),
                                         "actual": value, "op": condition["op"],
                                         "threshold": condition.get("threshold"), "passed": True},),
                            reason_code="user_exit"))
                        break
                else:
                    adds = normalized.get("adds")
                    if adds is not None:
                        units = int(position_view.get("entry_count") or 1)
                        if units < adds["max_units"]:
                            add_signal = _entry_signal(instrument, series, index, equity, lot)
                            if add_signal is not None:
                                intended = add_signal.intended_quantity
                                if intended is None:
                                    close = series.bars[index].close / series.split_factors[index]
                                    intended = float(int(min(equity * 0.25, equity) / close / lot) * lot) \
                                        if equity > 0 else 0.0
                                if intended and intended >= lot:
                                    candidates.append(Signal(
                                        instrument=instrument, kind="add_candidate", strength=None,
                                        reason_text=f"入场条件再次满足，追加第 {units + 1} 单元。",
                                        conditions=(), reason_code="user_add",
                                        intended_quantity=float(intended)))
                    atr_mult = normalized["exit"].get("atr_trailing_mult")
                    if atr_mult is not None:
                        from src.strategy.factors import _atr_ratio
                        n = _atr_ratio(series, index, 14)
                        if n and n > 0:
                            close = series.adjusted_close[-1]
                            current_stop = float((view.get(instrument) or {}).get("stop_price") or 0.0)
                            new_stop = close - atr_mult * n
                            if new_stop > current_stop:
                                candidates.append(Signal(
                                    instrument=instrument, kind="stop_update", strength=None,
                                    reason_text=f"ATR 跟踪止损上移至 {new_stop:.2f}（前收−{atr_mult}×ATR）。",
                                    conditions=({"label": "ATR 跟踪止损", "actual": new_stop,
                                                 "op": "gt", "threshold": new_stop, "passed": True},),
                                    reason_code="user_trailing_stop"))
                continue
            entry_signal = _entry_signal(instrument, series, index, equity, lot)
            if entry_signal is not None:
                candidates.append(entry_signal)
        direction = (normalized.get("ranking") or {}).get("direction", "desc")
        candidates.sort(key=lambda item: ((-1 if direction == "desc" else 1) * (item.strength or 0.0),
                                          item.instrument))
        return exits, candidates

    return provider
