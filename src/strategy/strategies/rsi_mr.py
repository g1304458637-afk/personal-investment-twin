"""RSI 均值回归 (RSI Mean Reversion) — v1.

Classic contrarian template based on Wilder's RSI(14): buy weakness (RSI
below 30), sell strength (RSI above 70).  Provenance: RSI is J. Welles
Wilder's 1978 indicator (public common knowledge); the 30/70 thresholds are
the widely taught defaults.  Our long-only, next-open, lot-rounded execution
is declared adaptation.  Not presented as any single published strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.strategy.data import SimulationData
from src.strategy.rsi_state import wilder_rsi_at
from src.strategy.spec import StrategySpec

RSI_WINDOW = 14
OVERSOLD = 30.0
OVERBOUGHT = 70.0


def wilder_rsi(closes: tuple[float, ...], window: int = RSI_WINDOW) -> float | None:
    """Wilder's smoothing: first value from simple means, then recursive."""
    if len(closes) < window + 1:
        return None
    gains = losses = 0.0
    for index in range(1, window + 1):
        change = closes[index] - closes[index - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / window, losses / window
    for index in range(window + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        avg_gain = (avg_gain * (window - 1) + max(change, 0.0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-change, 0.0)) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


RULE_TABLE: tuple[dict[str, str], ...] = (
    {"rule_id": "R1_entry_oversold", "source": "public_rule:wilder_rsi",
     "statement": "RSI(14) 低于 30（超卖）时产生入场信号——在弱势中买入。"},
    {"rule_id": "R2_exit_overbought", "source": "public_rule:wilder_rsi",
     "statement": "RSI(14) 高于 70（超买）时退出——在强势中卖出。"},
    {"rule_id": "R3_no_stop", "source": "adaptation",
     "statement": "本模板不含价格止损——退出依赖 RSI 回升到超买区。"},
    {"rule_id": "MR_adapt_thresholds", "source": "adaptation",
     "statement": "适配：30/70 为最常见教学阈值；Wilder 原文未强制该数值。"},
    {"rule_id": "MR_adapt_long_only", "source": "adaptation",
     "statement": "适配：仅实现多头（超卖买入），不做做空一侧。"},
    {"rule_id": "B1_universe", "source": "adaptation",
     "statement": "股票池为点时上市且有效收盘≥30个的全部成员（RSI 平滑需要更长预热）。"},
    {"rule_id": "B2_ranking", "source": "adaptation",
     "statement": "候选超过剩余仓位时按超卖深度（30−RSI）降序，平局按 instrument_id 升序。"},
    {"rule_id": "B3_sizing", "source": "adaptation",
     "statement": "等权仓位：每仓目标=当日总净值×25%，最多4仓，按100股整手向下取整。"},
    {"rule_id": "B4_no_add", "source": "adaptation",
     "statement": "不加仓：同一标的同时至多一个仓位。"},
    {"rule_id": "B6_conflict_priority", "source": "adaptation",
     "statement": "同日先卖出后买入，卖出资金当日可用。"},
    {"rule_id": "B7_order_model", "source": "adaptation",
     "statement": "市价单、当日有效、次日开盘成交（信号收盘确认、次开盘执行）。"},
    {"rule_id": "B8_fees", "source": "adaptation",
     "statement": "佣金0.03%（最低5元）双边，印花税0.1%仅卖出（合成参数，非券商报价）。"},
    {"rule_id": "B9_slippage", "source": "adaptation",
     "statement": "滑点固定为0，参数保留。"},
)

RSI_MR_PARAMS: dict[str, float | int | str] = {
    "min_history": 30,
    "max_positions": 4,
    "position_fraction": 0.25,
    "lot_size": 100,
    "stop_loss_pct": 0.0,  # R3: no price stop; the RSI recovery is the exit.
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
    reason_code: str = "signal_entry_rsi_mr"
    intended_quantity: float | None = None


def evaluate_close_signals(spec_params: dict[str, float | int | str], data: SimulationData,
                           day: date, held: set[str], pending_buy_instruments: set[str],
                           account_view: dict | None = None) \
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
        if index + 1 < min_history:
            continue
        rsi = wilder_rsi_at(member_series, index, RSI_WINDOW)
        if rsi is None:
            continue
        if instrument in held:
            if rsi > OVERBOUGHT:
                exits.append(CloseSignal(
                    instrument=instrument, kind="exit", strength=None,
                    reason_text=(f"RSI(14)={rsi:.1f} 高于 70（超买），按规则退出。"),
                    conditions=(dict(label="RSI(14) vs 70", actual=rsi, operator=">",
                                     threshold=OVERBOUGHT, passed=True),)))
            continue
        if instrument in pending_buy_instruments:
            continue
        if rsi < OVERSOLD:
            entries.append(CloseSignal(
                instrument=instrument, kind="entry_candidate", strength=OVERSOLD - rsi,
                reason_text=(f"RSI(14)={rsi:.1f} 低于 30（超卖），产生入场信号。"),
                conditions=()))
    entries.sort(key=lambda item: (-(item.strength or 0.0), item.instrument))
    return exits, entries


def build_rsi_mr_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="toujing_rsi_mean_reversion",
        version="1",
        title="RSI 均值回归（14，30/70，多头）",
        description="基于 Wilder RSI(14) 的经典反转模板：超卖买入、超买卖出；阈值与全部执行细节为显式声明的适配，与顺势策略（T1、双均线）构成相反的行为参照。",
        rule_table=RULE_TABLE,
        params=dict(RSI_MR_PARAMS),
    )
