"""海龟 (Turtle, System-2 long-only variant) — v1.

Richard Dennis & William Eckhardt's publicly documented trading system.
Provenance: the turtle rules were famously taught to the "Turtles" and later
published (Curtis Faith, "Way of the Turtle"); the core mechanics below are
public common knowledge.  Our version is an explicit System-2 long-only
adaptation and is NOT presented as the complete original system.

Declared model: enter when the close breaks above the prior 55-day high
(System 2 entry); N = ATR(20) on adjusted bars; unit shares = (1% × equity)/N
lot-rounded; add one unit whenever the close reaches last entry price +
0.5N, up to 4 units; after each fill the stop moves to (last fill price −
2N); exit when the close breaks below the prior 20-day low.  Long-only,
single-pool, no correlation caps: declared adaptations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.strategy.data import SimulationData
from src.strategy.spec import StrategySpec

ENTRY_WINDOW = 55
EXIT_WINDOW = 20
ATR_WINDOW = 20
MAX_UNITS = 4
UNIT_RISK_FRACTION = 0.01
NOTIONAL_CAP_FRACTION = 0.25
UNIT_STEP_ATR = 0.5
STOP_ATR_MULT = 2.0


def atr20(dates: tuple[date, ...], bars: tuple, factors: tuple[float, ...], index: int) -> float | None:
    """Average true range on split-adjusted bars over ATR_WINDOW ending at index."""
    start = index - ATR_WINDOW + 1
    if start < 1:
        return None
    trs: list[float] = []
    for i in range(start, index + 1):
        factor = factors[i]
        factor_prev = factors[i - 1]
        close_prev = bars[i - 1].close / factor_prev
        high = bars[i].high / factor
        low = bars[i].low / factor
        trs.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))
    return sum(trs) / len(trs)


RULE_TABLE: tuple[dict[str, str], ...] = (
    {"rule_id": "T1_entry_s2_breakout", "source": "public_rule:turtle_system2",
     "statement": "收盘价突破此前 55 个有效收盘高点（System 2 入场）时买入 1 个单元。"},
    {"rule_id": "T2_unit_sizing", "source": "public_rule:turtle",
     "statement": "N = ATR(20)；单元股数 = (1% × 账户净值) ÷ N，按 100 股整手向下取整。"},
    {"rule_id": "T2_adapt_notional_cap", "source": "adaptation",
     "statement": "适配：单元名义敞口上限为净值×25%（与其他策略等权一致）——原版靠大资金跨多市场分散，单池小额账户下 1%风险/N 会超过全部净值，故加名义上限。"},
    {"rule_id": "T3_pyramid_adds", "source": "public_rule:turtle",
     "statement": "收盘价达到上次成交价 + 0.5N 时追加 1 个单元，同一标的最多 4 个单元。"},
    {"rule_id": "T4_trailing_stop", "source": "public_rule:turtle",
     "statement": "每次成交后，该标的止损设为最近成交价 − 2N（2N 移动止损）。"},
    {"rule_id": "T5_exit_s2", "source": "public_rule:turtle_system2",
     "statement": "收盘价跌破此前 20 个有效收盘低点时全部退出。"},
    {"rule_id": "T_adapt_long_only", "source": "adaptation",
     "statement": "适配：仅实现多头；原版为多空双向。"},
    {"rule_id": "T_adapt_single_pool", "source": "adaptation",
     "statement": "适配：原版跨多市场组合并限制相关单元数；本版为单一股票池，不做相关性限制。"},
    {"rule_id": "T_adapt_exit_window", "source": "adaptation",
     "statement": "适配：原版 System 2 退出为 20 日突破的反向；本版按 20 个有效收盘低点执行。"},
    {"rule_id": "B1_universe", "source": "adaptation",
     "statement": "股票池为点时上市且有效收盘≥56个的全部成员。"},
    {"rule_id": "B6_conflict_priority", "source": "adaptation",
     "statement": "同日先卖出后加仓/买入，卖出资金当日可用。"},
    {"rule_id": "B7_order_model", "source": "adaptation",
     "statement": "市价单、当日有效、次日开盘成交；未成交必须记录原因。"},
    {"rule_id": "B8_fees", "source": "adaptation",
     "statement": "佣金0.03%（最低5元）双边，印花税0.1%仅卖出（合成参数，非券商报价）。"},
    {"rule_id": "B9_slippage", "source": "adaptation",
     "statement": "滑点固定为0，参数保留。"},
)

TURTLE_PARAMS: dict[str, float | int | str] = {
    "min_history": 56,
    "max_positions": 4,
    "position_fraction": 0.25,  # Unused by turtle sizing; kept for engine defaults.
    "lot_size": 100,
    "stop_loss_pct": 0.0,  # Turtle uses its own 2N trailing stop (T4).
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
    kind: str  # entry_candidate | add_candidate | stop_update | exit
    strength: float | None
    reason_text: str
    conditions: tuple[dict[str, object], ...]
    reason_code: str = "turtle_entry_s2"
    intended_quantity: float | None = None


def evaluate_close_signals(spec_params: dict[str, float | int | str], data: SimulationData,
                           day: date, held: set[str], pending_buy_instruments: set[str],
                           account_view: dict | None = None) \
        -> tuple[list[CloseSignal], list[CloseSignal]]:
    account_view = account_view or {}
    equity = float(account_view.get("equity") or 0.0)
    positions = account_view.get("positions") or {}
    exits: list[CloseSignal] = []
    candidates: list[CloseSignal] = []
    min_history = int(spec_params["min_history"])
    lot = int(spec_params["lot_size"])
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
        n = atr20(member_series.dates, member_series.bars, member_series.split_factors, index)
        if n is None or n <= 0:
            continue
        prior_high = max(closes[-(ENTRY_WINDOW + 1):-1])
        prior_low = min(closes[-(EXIT_WINDOW + 1):-1])
        close_now = closes[-1]
        if instrument in held:
            view = positions.get(instrument) or {}
            units = int(view.get("entry_count") or 1)
            last_entry = float(view.get("last_entry_price") or 0.0)
            if close_now < prior_low:
                exits.append(CloseSignal(
                    instrument=instrument, kind="exit", strength=None,
                    reason_text=(f"收盘{close_now:.2f}跌破此前{EXIT_WINDOW}个有效收盘低点{prior_low:.2f}，全部退出。"),
                    conditions=(dict(label="收盘价 vs 此前20个有效收盘低点", actual=close_now,
                                     operator="<", threshold=prior_low, passed=True),),
                    reason_code="turtle_exit_s2"))
                continue
            add_trigger = last_entry + UNIT_STEP_ATR * n
            if units < MAX_UNITS and close_now >= add_trigger:
                unit_shares = min((UNIT_RISK_FRACTION * equity) / n,
                                  (NOTIONAL_CAP_FRACTION * equity) / close_now)
                intended = float(int(unit_shares / lot) * lot)
                if intended >= lot:
                    candidates.append(CloseSignal(
                        instrument=instrument, kind="add_candidate", strength=None,
                        reason_text=(f"收盘{close_now:.2f}达到上次成交价+0.5N（{add_trigger:.2f}，N={n:.2f}），"
                                     f"追加第 {units + 1} 单元 {intended:.0f} 股。"),
                        conditions=(dict(label="收盘价 vs 上次成交价+0.5N", actual=close_now,
                                         operator=">=", threshold=add_trigger, passed=True),),
                        reason_code="turtle_unit_add", intended_quantity=intended))
            new_stop = last_entry - STOP_ATR_MULT * n
            stop_view = float(view.get("stop_price") or 0.0)
            if new_stop > stop_view:
                candidates.append(CloseSignal(
                    instrument=instrument, kind="stop_update", strength=None,
                    reason_text=f"2N 移动止损设为/上移至 {new_stop:.2f}（N={n:.2f}）。",
                    conditions=(dict(label="2N 移动止损", actual=new_stop, operator=">",
                                     threshold=0.0, passed=True),),
                    reason_code="turtle_stop_update"))
            continue
        if instrument in pending_buy_instruments:
            continue
        if close_now > prior_high:
            price_ref = close_now
            unit_shares = min((UNIT_RISK_FRACTION * equity) / n,
                              (NOTIONAL_CAP_FRACTION * equity) / price_ref)
            intended = float(int(unit_shares / lot) * lot)
            if intended >= lot:
                candidates.append(CloseSignal(
                    instrument=instrument, kind="entry_candidate", strength=close_now / prior_high - 1.0,
                    reason_text=(f"收盘{close_now:.2f}突破此前{ENTRY_WINDOW}个有效收盘高点{prior_high:.2f}"
                                 f"（N={n:.2f}），买入 1 单元 {intended:.0f} 股。"),
                    conditions=(), reason_code="turtle_entry_s2", intended_quantity=intended))
    return exits, candidates


def build_turtle_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="toujing_turtle_s2_long",
        version="1",
        title="海龟 System 2（55日突破，ATR 单元加仓，多头）",
        description="公开广为人知的海龟系统要点之多头适配版：55日突破入场、ATR(20) 定单元、0.5N 逐级加仓至多 4 单元、2N 移动止损、20日低点退出；仅多头、单股票池为显式适配，不冒充完整原版。",
        rule_table=RULE_TABLE,
        params=dict(TURTLE_PARAMS),
    )
