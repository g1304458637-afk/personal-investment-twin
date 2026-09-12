"""双均线交叉 (Dual Moving-Average Crossover) — v1.

A widely known trend-following template: enter on a golden cross (short MA
crosses above long MA), exit on the death cross.  Provenance is explicit:
the crossover concept is public common knowledge (no single canonical text);
our parameter choice and all execution machinery are declared adaptations.
This is not presented as any single published strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.strategy.data import SimulationData
from src.strategy.signals import trailing_mean
from src.strategy.spec import StrategySpec

SHORT_WINDOW = 5
LONG_WINDOW = 20

RULE_TABLE: tuple[dict[str, str], ...] = (
    {"rule_id": "D1_entry_golden_cross", "source": "public_rule:ma_crossover",
     "statement": "短期均线（5）自下而上穿越长期均线（20）（金叉）时产生入场信号。"},
    {"rule_id": "D2_exit_death_cross", "source": "public_rule:ma_crossover",
     "statement": "短期均线自上而下穿越长期均线（死叉）时退出。"},
    {"rule_id": "D3_no_stop", "source": "public_rule:ma_crossover",
     "statement": "原模板不含价格止损——死叉本身就是退出机制。"},
    {"rule_id": "MA_adapt_params", "source": "adaptation",
     "statement": "适配：经典模板存在 5/20、50/200 等多种参数；本版固定采用 5/20（日频）。"},
    {"rule_id": "MA_adapt_long_only", "source": "adaptation",
     "statement": "适配：仅实现多头一侧，不做做空与反向持仓。"},
    {"rule_id": "B1_universe", "source": "adaptation",
     "statement": "股票池为点时上市且有效收盘≥21个的全部成员。"},
    {"rule_id": "B2_ranking", "source": "adaptation",
     "statement": "候选超过剩余仓位时按均线离散度（短均线/长均线−1）降序，平局按 instrument_id 升序。"},
    {"rule_id": "B3_sizing", "source": "adaptation",
     "statement": "等权仓位：每仓目标=当日总净值×25%，最多4仓，按100股整手向下取整。"},
    {"rule_id": "B4_no_add", "source": "adaptation",
     "statement": "不加仓：同一标的同时至多一个仓位，退出后可再次入场。"},
    {"rule_id": "B6_conflict_priority", "source": "adaptation",
     "statement": "同日先卖出后买入，卖出资金当日可用。"},
    {"rule_id": "B7_order_model", "source": "adaptation",
     "statement": "市价单、当日有效、次日开盘成交；未成交必须记录原因。"},
    {"rule_id": "B8_fees", "source": "adaptation",
     "statement": "佣金0.03%（最低5元）双边，印花税0.1%仅卖出（合成参数，非券商报价）。"},
    {"rule_id": "B9_slippage", "source": "adaptation",
     "statement": "滑点固定为0，参数保留。"},
)

DUAL_MA_PARAMS: dict[str, float | int | str] = {
    "min_history": 21,
    "max_positions": 4,
    "position_fraction": 0.25,
    "lot_size": 100,
    "stop_loss_pct": 0.0,  # D3: no price stop; the death cross is the exit.
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_duty_rate": 0.001,
    "slippage_rate": 0.0,
    "price_limit_pct": 0.10,
    "initial_cash": 1_000_000.0,
    "currency": "CNY",
}


@dataclass(frozen=True, slots=True)
class CloseSignal:
    instrument: str
    kind: str
    strength: float | None
    reason_text: str
    conditions: tuple[dict[str, object], ...]


def _moving_averages(closes: tuple[float, ...]) -> tuple[float | None, float | None, float | None, float | None]:
    short_now = trailing_mean(closes, SHORT_WINDOW)
    long_now = trailing_mean(closes, LONG_WINDOW)
    short_prev = trailing_mean(closes[:-1], SHORT_WINDOW)
    long_prev = trailing_mean(closes[:-1], LONG_WINDOW)
    return short_now, long_now, short_prev, long_prev


def evaluate_close_signals(spec_params: dict[str, float | int | str], data: SimulationData,
                           day: date, held: set[str], pending_buy_instruments: set[str]) \
        -> tuple[list[CloseSignal], list[CloseSignal]]:
    exits: list[CloseSignal] = []
    entries: list[CloseSignal] = []
    min_history = int(spec_params["min_history"])
    for instrument in sorted(data.listed_on(day)):
        member_series = data.series[instrument]
        bar = member_series.bar_on(day)
        if bar is None:
            continue
        index = member_series.index_on_or_before(day)
        assert index is not None
        closes = member_series.adjusted_close[: index + 1]
        if len(closes) < min_history:
            continue
        short_now, long_now, short_prev, long_prev = _moving_averages(closes)
        if short_now is None or long_now is None or short_prev is None or long_prev is None:
            continue
        cross_up = short_prev <= long_prev and short_now > long_now
        cross_down = short_prev >= long_prev and short_now < long_now
        if instrument in held:
            if cross_down:
                exits.append(CloseSignal(
                    instrument=instrument, kind="exit", strength=None,
                    reason_text=(f"短均线{short_now:.2f}下穿长均线{long_now:.2f}（死叉），按规则退出。"),
                    conditions=(dict(label="短均线 vs 长均线（交叉向下）", actual=short_now,
                                     operator="<", threshold=long_now, passed=True),)))
            continue
        if instrument in pending_buy_instruments:
            continue
        if cross_up:
            strength = short_now / long_now - 1.0 if long_now > 0 else None
            entries.append(CloseSignal(
                instrument=instrument, kind="entry_candidate", strength=strength,
                reason_text=(f"短均线{short_now:.2f}上穿长均线{long_now:.2f}（金叉），产生入场信号。"),
                conditions=()))
    entries.sort(key=lambda item: (-(item.strength or 0.0), item.instrument))
    return exits, entries


def build_dual_ma_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="toujing_dual_ma",
        version="1",
        title="双均线交叉（5/20，多头）",
        description="公开广为人知的均线交叉模板：金叉入场、死叉退出；参数与全部执行细节为显式声明的适配，不冒充任何单一文献版本。",
        rule_table=RULE_TABLE,
        params=dict(DUAL_MA_PARAMS),
    )
