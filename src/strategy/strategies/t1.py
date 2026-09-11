"""T1 v1 "突破趋势": the first complete teaching strategy.

Rule provenance is explicit.  A1/A2/A3 lift the three Decision Lens
conditions into a *tradable* strategy unchanged in meaning; B-rules are the
adaptations needed for full execution (universe, ranking, sizing, stop,
no-add rule, conflict priority, order model, fees) and are documented in
docs/STRATEGY_SIMULATION_V1.md §4.  This is not presented as a classic
published strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.strategy.data import SimulationData
from src.strategy.signals import breakout_strength, prior_extreme, trailing_mean
from src.strategy.spec import StrategySpec

BREAKOUT_WINDOW = 20
EXIT_WINDOW = 10

RULE_TABLE: tuple[dict[str, str], ...] = (
    {"rule_id": "A1_entry_trend_filter", "source": "lens_rule:trend_ma20",
     "statement": "收盘价高于最近20个有效收盘均值（SMA20）才允许入场。"},
    {"rule_id": "A2_entry_breakout", "source": "lens_rule:closing_breakout20",
     "statement": "收盘价严格高于此前20个有效收盘高点才允许入场。"},
    {"rule_id": "A3_signal_exit", "source": "lens_rule:closing_breakout20",
     "statement": "收盘价低于此前10个有效收盘低点时退出。"},
    {"rule_id": "B1_universe", "source": "adaptation",
     "statement": "股票池为点时上市且有效收盘≥21个的全部成员；上市前/退市后不可选。"},
    {"rule_id": "B2_ranking", "source": "adaptation",
     "statement": "候选超过剩余仓位时按突破强度降序，平局按instrument_id升序。"},
    {"rule_id": "B3_sizing", "source": "adaptation",
     "statement": "等权仓位：每仓目标=当日总净值×25%，最多4仓，按100股整手向下取整。"},
    {"rule_id": "B4_no_add", "source": "adaptation",
     "statement": "不加仓：同一标的同时至多一个仓位，退出后可再次入场。"},
    {"rule_id": "B5_stop_loss", "source": "adaptation",
     "statement": "入场价×(1−8%)硬止损，逐日盘中检查；跳空低开按开盘价成交。"},
    {"rule_id": "B6_conflict_priority", "source": "adaptation",
     "statement": "同日先卖出后买入，卖出资金当日可用；退出优先于入场。"},
    {"rule_id": "B7_order_model", "source": "adaptation",
     "statement": "市价单、当日有效、次日开盘成交；未成交必须记录原因。"},
    {"rule_id": "B8_fees", "source": "adaptation",
     "statement": "佣金0.03%（最低5元）双边，印花税0.1%仅卖出（合成参数，非券商报价）。"},
    {"rule_id": "B9_slippage", "source": "adaptation",
     "statement": "V1滑点固定为0，参数保留。"},
)

T1_PARAMS: dict[str, float | int | str] = {
    "min_history": 21,
    "max_positions": 4,
    "position_fraction": 0.25,
    "lot_size": 100,
    "stop_loss_pct": 0.08,
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_duty_rate": 0.001,
    "slippage_rate": 0.0,
    "price_limit_pct": 0.10,
    "initial_cash": 1_000_000.0,
    "currency": "CNY",
}


def build_t1_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="toujing_t1_breakout_trend",
        version="1",
        title="投镜教学策略 T1：突破趋势",
        description="由 Decision Lens 三条核对规则升格而来的完整教学策略；B 类规则为完整执行所需的新增适配，不冒充经典名家策略。",
        rule_table=RULE_TABLE,
        params=dict(T1_PARAMS),
    )


@dataclass(frozen=True, slots=True)
class CloseSignal:
    instrument: str
    kind: str  # "entry_candidate" | "exit"
    strength: float | None  # breakout strength, entry ranking key
    reason_text: str
    conditions: tuple[dict[str, object], ...]


def t1_entry_state(closes: tuple[float, ...]) -> tuple[bool, dict[str, object]]:
    """A1+A2 on split-adjusted closes through the signal day (inclusive)."""
    close = closes[-1]
    sma = trailing_mean(closes, BREAKOUT_WINDOW)
    prior_high = prior_extreme(closes, BREAKOUT_WINDOW, high=True)
    conditions: dict[str, object] = {
        "close": close,
        "sma20": sma,
        "prior_high_20": prior_high,
        "above_sma20": None if sma is None else close > sma,
        "breaks_prior_high_20": None if prior_high is None else close > prior_high,
    }
    entered = sma is not None and prior_high is not None and close > sma and close > prior_high
    return entered, conditions


def t1_exit_state(closes: tuple[float, ...]) -> tuple[bool, dict[str, object]]:
    """A3: close falls below the prior 10 valid closes' low."""
    close = closes[-1]
    prior_low = prior_extreme(closes, EXIT_WINDOW, high=False)
    conditions: dict[str, object] = {
        "close": close,
        "prior_low_10": prior_low,
        "below_prior_low_10": None if prior_low is None else close < prior_low,
    }
    return prior_low is not None and close < prior_low, conditions


def evaluate_close_signals(spec_params: dict[str, float | int | str], data: SimulationData,
                           day: date, held: set[str], pending_buy_instruments: set[str]) \
        -> tuple[list[CloseSignal], list[CloseSignal]]:
    """Compute exit signals and ranked entry candidates from closes through ``day``.

    Returns (exits, entries).  Entries are ranked by breakout strength
    (desc), ties broken by instrument id; the engine applies position slots.
    """
    min_history = int(spec_params["min_history"])
    exits: list[CloseSignal] = []
    entries: list[CloseSignal] = []
    for instrument in sorted(data.listed_on(day)):
        member_series = data.series[instrument]
        bar = member_series.bar_on(day)
        if bar is None:
            continue  # No close observation today: no signal, no order.
        index = member_series.index_on_or_before(day)
        assert index is not None
        closes = member_series.adjusted_close[: index + 1]
        if instrument in held:
            exited, exit_conditions = t1_exit_state(closes)
            if exited:
                exits.append(CloseSignal(
                    instrument=instrument, kind="exit", strength=None,
                    reason_text=(f"收盘{closes[-1]:.2f}低于此前{EXIT_WINDOW}个有效收盘低点"
                                 f"{exit_conditions['prior_low_10']:.2f}，按规则退出。"),
                    conditions=(dict(label="收盘价 vs 此前10个有效收盘低点", actual=closes[-1],
                                     operator="<", threshold=exit_conditions["prior_low_10"],
                                     passed=True),)))
            continue
        if instrument in pending_buy_instruments:
            continue
        if len(closes) < min_history:
            continue  # B1: not enough valid history yet.
        entered, entry_conditions = t1_entry_state(closes)
        if not entered:
            continue
        strength = breakout_strength(closes[-1], float(entry_conditions["prior_high_20"]))
        entries.append(CloseSignal(
            instrument=instrument, kind="entry_candidate", strength=strength,
            reason_text=(f"收盘{closes[-1]:.2f}高于SMA20 {entry_conditions['sma20']:.2f}，"
                         f"并严格突破此前{BREAKOUT_WINDOW}个有效收盘高点"
                         f"{entry_conditions['prior_high_20']:.2f}。"),
            conditions=()))
    entries.sort(key=lambda item: (-(item.strength or 0.0), item.instrument))
    return exits, entries
