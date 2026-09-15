"""Tilt observation: a deterministic rule over observable execution facts.

Trigger (fixed rule, descriptive only): three consecutive CLOSED episodes with
strictly negative net realized PnL.  After each trigger the following 10
trading days are observed and compared with whole-history baselines:

- trade_count vs baseline_trade_count (executions per trading day averaged
  over the entire data boundary);
- avg_size_change_pct: average BUY notional in the window vs the average BUY
  notional of the 30 trading days before the trigger date (null when either
  side has no BUY observations; never guessed);
- same_instrument_rebuy_count: window BUYs whose instrument is one of the
  three instruments closed at a loss in the trigger streak.

Everything is a descriptive statistic of observable facts; no psychological
motive is inferred.  With fewer than MIN_TOTAL_EXECUTIONS executions in the
whole history no observation is produced (insufficient evidence).  Windows of
overlapping triggers do not stack: scanning resumes after a trigger window.
"""

from __future__ import annotations

import bisect

import pandas as pd

MIN_TOTAL_EXECUTIONS = 20
WINDOW_TRADING_DAYS = 10
STREAK_LENGTH = 3
BASELINE_TRADING_DAYS = 30

SECTION_LIMITATIONS: tuple[str, ...] = (
    "tilt 为确定性规则下的描述性观察，只描述可观测事实，不推断心理动机，不构成诊断。",
    "触发规则：连续 3 个已闭合 episode 净已实现盈亏 < 0（含费净额口径）。",
    "全历史成交不足 20 笔时样本不足，不输出任何观察。",
    "交易日轴来自可用日线价格观测日并集，不是交易所官方日历。",
    "观察窗口与基线均按交易日计数；触发后窗口与下一触发不重叠。",
)

ITEM_LIMITATIONS: tuple[str, ...] = (
    "描述性统计，不推断心理动机",
    "交易日轴来自可用日线价格日历，非交易所官方日历。",
)


def detect_tilt(
    execution_days: list[pd.Timestamp],
    execution_symbols: list[str],
    execution_sides: list[str],
    execution_notionals: list[float],
    trading_days: list[pd.Timestamp],
    closed_exits: list[dict],
) -> list[dict]:
    """Detect non-overlapping three-consecutive-loss triggers.

    ``execution_days/symbols/sides/notionals`` are parallel lists over all
    canonical executions in replay order.  ``trading_days`` is the sorted
    union of observed market dates.  ``closed_exits`` items carry exit_day
    (normalized Timestamp), instrument_id and realized_pnl, in chronological
    episode order.
    """

    if len(execution_days) < MIN_TOTAL_EXECUTIONS:
        return []
    if not trading_days:
        return []
    day_index = {day: index for index, day in enumerate(trading_days)}
    observations: list[dict] = []
    suppressed: set[int] = set()
    streak = 0
    for position, exit_item in enumerate(closed_exits):
        if position in suppressed:
            streak = 0
            continue
        if float(exit_item["realized_pnl"]) < 0:
            streak += 1
        else:
            streak = 0
        if streak < STREAK_LENGTH:
            continue
        trigger_day = pd.Timestamp(exit_item["exit_day"]).normalize()
        trigger_index = day_index.get(trigger_day)
        snapped_limitation: str | None = None
        if trigger_index is None:
            # The trigger day itself may carry no price observation (holidays
            # in the observed calendar, stale vendor rows).  Dropping the
            # confirmed trigger silently violates the never-drop convention:
            # snap the window to the first observed day at or after the
            # trigger, or report honestly when none exists.
            position_of_next = bisect.bisect_left(trading_days, trigger_day)
            if position_of_next >= len(trading_days):
                observations.append({
                    "trigger": "three_consecutive_losses",
                    "trigger_date": trigger_day.date().isoformat(),
                    "window": {
                        "days": WINDOW_TRADING_DAYS,
                        "trade_count": None,
                        "baseline_trade_count": None,
                        "avg_size_change_pct": None,
                        "same_instrument_rebuy_count": None,
                    },
                    "note": (
                        f"在 {trigger_day.date().isoformat()} 出现连续 {STREAK_LENGTH} 笔亏损平仓；"
                        "但其后没有已观测的交易日，行为窗口未能评估。"
                    ),
                    "limitations": (*ITEM_LIMITATIONS,
                                    "触发日之后无已观测交易日，窗口统计不可用"),
                })
                streak = 0
                continue
            trigger_index = position_of_next
            snapped_limitation = (
                f"触发日 {trigger_day.date().isoformat()} 非已观测交易日，"
                f"窗口自其后首个观测交易日 "
                f"{trading_days[trigger_index].date().isoformat()} 起计。")
        window_end_index = min(trigger_index + WINDOW_TRADING_DAYS, len(trading_days) - 1)
        window_days = set(trading_days[trigger_index + 1:window_end_index + 1])
        streak_instruments = {
            str(closed_exits[position - offset]["instrument_id"])
            for offset in range(STREAK_LENGTH)
        }
        window_counts = _window_stats(
            execution_days, execution_symbols, execution_sides, execution_notionals,
            window_days, streak_instruments)
        baseline_trade_count = len(execution_days) / len(trading_days)
        avg_size_change_pct = _avg_size_change_pct(
            execution_days, execution_sides, execution_notionals,
            trading_days, trigger_index, window_days)
        observations.append({
            "trigger": "three_consecutive_losses",
            "trigger_date": trigger_day.date().isoformat(),
            "window": {
                "days": WINDOW_TRADING_DAYS,
                "trade_count": window_counts["trade_count"],
                "baseline_trade_count": baseline_trade_count,
                "avg_size_change_pct": avg_size_change_pct,
                "same_instrument_rebuy_count": window_counts["same_instrument_rebuy_count"],
            },
            "note": (
                f"在 {trigger_day.date().isoformat()} 出现连续 {STREAK_LENGTH} 笔亏损平仓；"
                f"其后 {WINDOW_TRADING_DAYS} 个交易日内共成交 {window_counts['trade_count']} 笔，"
                f"对照全历史日均 {baseline_trade_count:.2f} 笔/交易日；"
                f"其中回买触发亏损序列标的 {window_counts['same_instrument_rebuy_count']} 笔。"
                "以上为可观测成交事实的描述性统计。"
            ),
            "limitations": (*ITEM_LIMITATIONS,
                            *((snapped_limitation,) if snapped_limitation else ())),
        })
        streak = 0
        # Suppress later exits whose third loss would fall inside this
        # observation window so windows never stack.
        for later_position in range(position + 1, len(closed_exits)):
            if pd.Timestamp(closed_exits[later_position]["exit_day"]).normalize() in window_days:
                suppressed.add(later_position)
    return observations


def _window_stats(
    execution_days, execution_symbols, execution_sides, execution_notionals,
    window_days: set[pd.Timestamp], streak_instruments: set[str],
) -> dict[str, int]:
    trade_count = 0
    same_instrument_rebuy_count = 0
    for day, symbol, side in zip(execution_days, execution_symbols, execution_sides):
        if day not in window_days:
            continue
        trade_count += 1
        if side == "BUY" and str(symbol) in streak_instruments:
            same_instrument_rebuy_count += 1
    return {"trade_count": trade_count, "same_instrument_rebuy_count": same_instrument_rebuy_count}


def _avg_size_change_pct(
    execution_days, execution_sides, execution_notionals,
    trading_days, trigger_index: int, window_days: set[pd.Timestamp],
) -> float | None:
    baseline_start = max(0, trigger_index - BASELINE_TRADING_DAYS)
    baseline_days = set(trading_days[baseline_start:trigger_index])
    window_buy_notionals = [
        notional for day, side, notional
        in zip(execution_days, execution_sides, execution_notionals)
        if side == "BUY" and day in window_days]
    baseline_buy_notionals = [
        notional for day, side, notional
        in zip(execution_days, execution_sides, execution_notionals)
        if side == "BUY" and day in baseline_days]
    if not window_buy_notionals or not baseline_buy_notionals:
        return None
    window_avg = sum(window_buy_notionals) / len(window_buy_notionals)
    baseline_avg = sum(baseline_buy_notionals) / len(baseline_buy_notionals)
    if baseline_avg <= 0:
        return None
    return (window_avg - baseline_avg) / baseline_avg
