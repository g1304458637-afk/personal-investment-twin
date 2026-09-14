"""Calendar aggregation of realized results, attributed to exit days.

Deterministic grouping only.  A closed episode's whole net realized PnL is
attributed to the calendar date of its closing execution (the exit day);
month rows aggregate those day attributions.  Months and days with no closed
episode are absent from the lists by design (clients render heatmaps by
filling zeros themselves); nothing here invents a value for an empty period.
"""

from __future__ import annotations

import pandas as pd

SECTION_LIMITATIONS: tuple[str, ...] = (
    "realized P&L 按退出日（平仓成交的日历日）归属，不是开仓日，也不是按月持有期分摊。",
    "仅统计已闭合 episode；未平仓浮动盈亏不出现在日历中。",
    "空月/空日不出现在列表中：前端绘制热力图或日历视图时需自行补零。",
    "金额为 canonical 成交含费净额，保持账户原始币种，不做汇率换算。",
    "同一日多笔平仓合并为一行，closed_count 为该日平仓的 episode 数。",
)


def build_calendar_rows(closed_episodes: list[dict]) -> list[dict]:
    """Aggregate closed episodes into (months, days) calendar rows.

    ``closed_episodes`` items carry episode_id, realized_pnl and closed_at.
    """

    month_rows: dict[str, dict] = {}
    day_rows: dict[str, dict] = {}
    for item in closed_episodes:
        exit_day = pd.Timestamp(item["closed_at"]).normalize()
        month_key = exit_day.date().isoformat()[:7]
        day_key = exit_day.date().isoformat()
        pnl = float(item["realized_pnl"])
        win = pnl > 0
        month = month_rows.setdefault(
            month_key, {"month": month_key, "realized_pnl": 0.0, "closed_count": 0, "win_count": 0})
        month["realized_pnl"] += pnl
        month["closed_count"] += 1
        month["win_count"] += int(win)
        day = day_rows.setdefault(
            day_key, {"date": day_key, "realized_pnl": 0.0, "closed_count": 0})
        day["realized_pnl"] += pnl
        day["closed_count"] += 1
    return {
        "months": [month_rows[key] for key in sorted(month_rows)],
        "days": [day_rows[key] for key in sorted(day_rows)],
        "limitations": list(SECTION_LIMITATIONS),
    }
