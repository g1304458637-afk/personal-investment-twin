"""Parameter sensitivity runs (schema strategy_sensitivity.v1).

One strategy, one parameter, a small set of values: run each variant on the
same dataset and line the outcomes up — in the order the caller provided,
never ranked, never marked best/worst.  This is deterministic anti-self-
deception education (how fragile is this result?), not parameter
optimization: there is deliberately no "best value" anywhere in the output.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Sequence

from src.strategy.data import SimulationData
from src.strategy.engine import run_simulation
from src.strategy.spec import StrategySpec

SCHEMA_VERSION = "strategy_sensitivity.v1"

# Parameters a sensitivity run may vary, with safe ranges.  Deliberately
# excludes entry/exit windows (those change what the strategy *is*, not how
# it is executed or risked) — that belongs to the workshop/L3 discussion.
ALLOWED_SENSITIVITY_PARAMS: dict[str, dict[str, float | int]] = {
    "stop_loss_pct": {"min": 0.0, "max": 0.5},
    "position_fraction": {"min": 0.05, "max": 1.0},
    "max_positions": {"min": 1, "max": 8},
    "commission_rate": {"min": 0.0, "max": 0.01},
    "slippage_rate": {"min": 0.0, "max": 0.02},
    "min_history": {"min": 10, "max": 250},
}


class SensitivityError(ValueError):
    """The requested parameter/values are out of the allowed sandbox."""


def _validate(parameter: str, values: Sequence[float]) -> list[float]:
    bounds = ALLOWED_SENSITIVITY_PARAMS.get(parameter)
    if bounds is None:
        raise SensitivityError(f"parameter_not_allowed: {parameter}")
    if not isinstance(values, (list, tuple)) or not 2 <= len(values) <= 6:
        raise SensitivityError("values 需要 2~6 个取值")
    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math_isfinite(value):
            raise SensitivityError("values 必须是有限数值")
        number = float(value)
        if not bounds["min"] <= number <= bounds["max"]:
            raise SensitivityError(f"{parameter} 取值超出允许范围 {bounds['min']}~{bounds['max']}")
        normalized.append(number)
    return normalized


def math_isfinite(value: object) -> bool:
    from math import isfinite
    return isfinite(value) if isinstance(value, (int, float)) else False


def _with_parameter(spec: StrategySpec, parameter: str, value: float) -> StrategySpec:
    params = dict(spec.params)
    if parameter == "max_positions" or parameter == "min_history":
        params[parameter] = int(value)
    else:
        params[parameter] = value
    return replace(spec, params=params)


def sensitivity_report(spec: StrategySpec, data: SimulationData, *, parameter: str,
                       values: Sequence[float], signal_provider: Callable | None = None) -> dict:
    """Run one variant per value; rows keep the caller's order (no ranking)."""
    normalized_values = _validate(parameter, values)
    rows = []
    for value in normalized_values:
        variant = _with_parameter(spec, parameter, value)
        result = run_simulation(variant, data, signal_provider=signal_provider)
        summary = result.summary
        trigger_counts: dict[str, int] = {}
        for fill in result.fills:
            trigger_counts[fill.trigger] = trigger_counts.get(fill.trigger, 0) + 1
        rows.append({
            "value": value,
            "final_equity": summary["final_equity"],
            "total_return": summary["total_return"],
            "max_drawdown": summary["max_drawdown"],
            "fill_count": summary["fill_count"],
            "round_trip_count": summary["round_trip_count"],
            "win_rate": summary["win_rate"],
            "total_fees": summary["total_fees"],
            "average_invested_fraction": summary["average_invested_fraction"],
            "trigger_counts": trigger_counts,
            "equity": [{"date": day.day.isoformat(), "equity": day.equity,
                        "drawdown_from_peak": day.drawdown_from_peak}
                       for day in result.days],
        })
    signature = {(row["final_equity"], row["fill_count"], row["total_fees"]) for row in rows}
    all_identical = len(signature) == 1
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": spec.strategy_id,
        "strategy_version": spec.version,
        "parameter": parameter,
        "rows": rows,
        "all_variants_identical": all_identical,
        "note": "各行顺序即输入顺序；本报告刻意不排序、不标注最优值——它展示的是结论对假设的敏感程度。",
        "limitations": (["各变体结果完全相同：该参数在这段历史中未起作用（未绑定任何成交）。"]
                        if all_identical else []) + [
            "全部运行发生在合成行情上，仅用于教学，不代表真实市场业绩。",
            "参数敏感不等于参数错误；敏感度高的策略，其历史结论本来就脆弱。",
            "本报告不做任何形式的参数推荐或优化。",
        ],
    }
