"""Exit-quality episode rows: MFE/MAE over the daily close mark-to-market path.

Method (deterministic, no network, no clock).  For every CLOSED episode the
episode-level long position is marked day by day over its holding window using
the Market Data Contract's daily closes:

    cum_pnl(day) = realized_exit_pnl_so_far(day)
                 + quantity(day) * (close(day) - average_cost(day))
                 - unallocated_entry_fees(day)

where ``realized_exit_pnl_so_far`` sums the canonical SELL exit-trade net PnL
(fees included, same source as the investments endpoint), ``average_cost`` is
the volume-weighted average entry price of the shares still held, and
``unallocated_entry_fees`` spreads the entry fees paid so far pro rata over
the quantity still held.  This decomposition reproduces the vectorbt position
record exactly at both ends: open marks equal the open-position PnL (verified
against ``portfolio.positions``) and the final window day equals the closed
position net PnL, which is asserted per episode; any mismatch fail-closes the
derived fields to null with an explicit limitation instead of guessing.

- mfe_amount / mae_amount: max/min of cum_pnl over the window (daily close
  granularity; intraday extremes are invisible).
- mfe_pct / mae_pct: fractions of the window's maximum invested notional
  (max end-of-day position market value), NOT percentages.
- exit_efficiency = realized_pnl / mfe_amount, only when mfe_amount > 0 and
  realized_pnl > 0.
- giveback_ratio = (mfe_amount - realized_pnl) / mfe_amount, only when
  mfe_amount > 0, capped above at 1.0 (a loss round trip gives exactly 1).
- Missing price days are skipped, never forward filled.  If a window has no
  usable close, all derived fields are null with an explicit limitation.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BASE_LIMITATIONS: tuple[str, ...] = (
    "MFE/MAE 用持仓窗口内日线收盘价对 episode 层仓位逐日 mark-to-market，盘中极值不可见。",
    "盈亏金额为 canonical 成交口径的净额，费用按 canonical 事实含入。",
    "价格缺失日直接跳过，不做前向填充（遵循仓库既有市场数据原则）。",
    "mfe_pct/mae_pct 是相对窗口内最大持仓市值（收盘口径）的小数比例，不是百分数。",
    "exit_efficiency 仅在 MFE>0 且已实现盈亏>0 时给出；giveback_ratio 上限为 1。",
)

_SECTION_LIMITATIONS: tuple[str, ...] = (
    *BASE_LIMITATIONS,
    "仅分析已闭合 episode；未平仓持仓不参与出场质量统计。",
    "realized_pnl 为 vectorbt 仓位级净已实现盈亏（含费），与 investments 端口同源。",
    "连续多日并列峰值/谷值时取最早一天。",
)


@dataclass(frozen=True, slots=True)
class _EpisodeInputs:
    """One closed episode plus the canonical facts needed for its path."""

    episode_id: str
    instrument_id: str
    realized_pnl: float
    hold_days: int | None
    decisions: tuple  # lifecycle DecisionEvent, replay order
    exit_pnl_by_decision: dict[str, float]  # decision_event_id -> SELL net pnl
    closes: dict[pd.Timestamp, float]  # window calendar date -> observed close
    missing_days: int  # account panel days inside the window lacking a close


def _empty_row(inputs: _EpisodeInputs, limitations: list[str]) -> dict:
    return {
        "episode_id": inputs.episode_id,
        "instrument": inputs.instrument_id,
        "mfe_amount": None,
        "mae_amount": None,
        "mfe_pct": None,
        "mae_pct": None,
        "realized_pnl": inputs.realized_pnl,
        "status": "closed",
        "exit_efficiency": None,
        "giveback_ratio": None,
        "facts": {"peak_date": None, "trough_date": None, "hold_days": inputs.hold_days},
        "limitations": [*limitations, *BASE_LIMITATIONS],
    }


def _window_path(inputs: _EpisodeInputs) -> tuple[list[pd.Timestamp], list[float], list[float], int]:
    """Replay the episode decisions day by day and mark with daily closes.

    Returns (marked dates, cum_pnl values, position notional values).  Decisions
    on days without closes still update the position state; only marks are
    skipped.
    """

    state_days = sorted(
        {pd.Timestamp(decision.occurred_at).normalize() for decision in inputs.decisions}
        | set(inputs.closes)
    )
    quantity = 0.0
    average_cost = 0.0
    # Entry-fee pool for shares still held: buys add their fees, sells remove
    # the sold fraction proportionally.  This matches average-cost fee
    # attribution exactly at every step (a uniform share of lifetime fees is
    # wrong once fee-per-share differs between buys, which the 5 CNY minimum
    # commission makes the norm for small adds).  A full exit empties the
    # pool, so the final-day value equals the authoritative realized PnL.
    entry_fee_pool = 0.0
    realized_so_far = 0.0
    exit_pnl_by_day: dict[pd.Timestamp, float] = {}
    for decision in inputs.decisions:
        pnl = inputs.exit_pnl_by_decision.get(decision.decision_id)
        if pnl is not None:
            day = pd.Timestamp(decision.occurred_at).normalize()
            exit_pnl_by_day[day] = exit_pnl_by_day.get(day, 0.0) + float(pnl)

    dates: list[pd.Timestamp] = []
    cum_values: list[float] = []
    notional_values: list[float] = []
    for day in state_days:
        for decision in (item for item in inputs.decisions
                         if pd.Timestamp(item.occurred_at).normalize() == day):
            side = str(decision.side)
            size = float(decision.executed_quantity)
            if side == "BUY":
                total = quantity + size
                if total <= 0:
                    continue
                average_cost = (average_cost * quantity + float(decision.execution_price) * size) / total
                quantity = total
                entry_fee_pool += float(decision.fees)
            elif side == "SELL":
                if quantity > 0:
                    sold = min(size, quantity)
                    entry_fee_pool *= 1.0 - sold / quantity
                quantity = max(0.0, quantity - size)
                if quantity <= 1e-12:
                    quantity = 0.0
                    average_cost = 0.0
                    entry_fee_pool = 0.0
        realized_so_far += exit_pnl_by_day.get(day, 0.0)
        close = inputs.closes.get(day)
        if close is None:
            continue
        unallocated = entry_fee_pool
        unrealized = quantity * (close - average_cost) if quantity > 0 else 0.0
        dates.append(day)
        cum_values.append(realized_so_far + unrealized - unallocated)
        notional_values.append(quantity * close)
    return dates, cum_values, notional_values


def build_exit_quality_rows(closed_episodes: list[dict]) -> tuple[list[dict], list[str]]:
    """Build one exit-quality row per closed episode plus section limitations.

    Every ``closed_episodes`` item carries: episode_id, instrument_id,
    realized_pnl, hold_days, decisions (lifecycle order), exit_pnl_by_decision,
    closes (observed daily closes inside THIS episode's window; no filling)
    and missing_days (account panel days inside the window without a close).
    Derived fields fail closed to null whenever the window has no usable close
    or the path contradicts the authoritative realized result.
    """

    rows: list[dict] = []
    for item in closed_episodes:
        inputs = _EpisodeInputs(
            episode_id=item["episode_id"],
            instrument_id=item["instrument_id"],
            realized_pnl=float(item["realized_pnl"]),
            hold_days=item["hold_days"],
            decisions=item["decisions"],
            exit_pnl_by_decision=item["exit_pnl_by_decision"],
            closes=item["closes"],
            missing_days=int(item["missing_days"]),
        )
        dates, cum_values, notional_values = _window_path(inputs)
        limitations: list[str] = []
        if not cum_values:
            limitations.append("持仓窗口内无可用日线收盘价，MFE/MAE 及派生指标置 null。")
            rows.append(_empty_row(inputs, limitations))
            continue
        if inputs.missing_days:
            limitations.append(f"窗口内缺少 {inputs.missing_days} 个价格观测日，这些日未计入路径。")
        peak_index = max(range(len(cum_values)), key=cum_values.__getitem__)
        trough_index = min(range(len(cum_values)), key=cum_values.__getitem__)
        mfe = float(cum_values[peak_index])
        mae = float(cum_values[trough_index])
        notional_max = max(notional_values) if notional_values else 0.0
        # Fail-closed consistency gate: the path's final value must reproduce
        # the authoritative vectorbt realized result for this episode.
        final_gap = abs(cum_values[-1] - inputs.realized_pnl)
        if final_gap > 1e-6 * max(1.0, abs(inputs.realized_pnl)):
            limitations.append(
                "逐日路径与权威已实现结果不一致（差 "
                f"{final_gap:.6f}），派生指标置 null，不作猜测。"
            )
            rows.append(_empty_row(inputs, limitations))
            continue
        mfe_pct = mfe / notional_max if notional_max > 0 else None
        mae_pct = mae / notional_max if notional_max > 0 else None
        efficiency = (
            inputs.realized_pnl / mfe
            if mfe > 0 and inputs.realized_pnl > 0
            else None
        )
        giveback = min(1.0, (mfe - inputs.realized_pnl) / mfe) if mfe > 0 else None
        rows.append({
            "episode_id": inputs.episode_id,
            "instrument": inputs.instrument_id,
            "mfe_amount": mfe,
            "mae_amount": mae,
            "mfe_pct": mfe_pct,
            "mae_pct": mae_pct,
            "realized_pnl": inputs.realized_pnl,
            "status": "closed",
            "exit_efficiency": efficiency,
            "giveback_ratio": giveback,
            "facts": {
                "peak_date": dates[peak_index].date().isoformat(),
                "trough_date": dates[trough_index].date().isoformat(),
                "hold_days": inputs.hold_days,
            },
            "limitations": [*limitations, *BASE_LIMITATIONS],
        })
    return rows, list(_SECTION_LIMITATIONS)
