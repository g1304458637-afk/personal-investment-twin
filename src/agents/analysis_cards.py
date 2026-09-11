"""Fail-closed, deterministic presentation cards for validated conversation answers.

Cards are projections of one already-read, answer-cited record.  This module
does not call tools, calculate financial values, or accept model-authored card
content. A malformed record produces no card. The sole availability exception
is a guarded, explicitly non-comparable same-stock side-by-side projection.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Final


CARD_KINDS: Final = frozenset((
    "hypothetical_trade_impact", "owned_period_comparison", "owned_same_stock_comparison",
    "public_technical", "public_financials",
))


def _local(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _finite_tree(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _finite_tree(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(item) for item in value)
    return value is None or isinstance(value, (str, int, bool))


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: object, *, digits: int = 2) -> str | None:
    if not _finite(value):
        return None
    # Display rounding is presentation only. It neither derives a metric nor
    # changes units; all values remain direct copies of typed projections.
    rounded = round(float(value), digits)
    return f"{0.0 if rounded == 0 else rounded:.{digits}f}"


def _amount(value: object, currency: object, *, digits: int = 2) -> str | None:
    unit = _text(currency)
    if not _finite(value) or unit is None:
        return None
    rounded = round(float(value), digits)
    return f"{0.0 if rounded == 0 else rounded:,.{digits}f} {unit}"


def _quantity(value: object) -> str | None:
    if not _finite(value):
        return None
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    rounded = round(numeric, 2)
    return f"{0.0 if rounded == 0 else rounded:,.2f}"


def _weight_percent(value: object) -> str | None:
    if not _finite(value):
        return None
    # This is display-unit conversion of the existing account-value fraction,
    # not a newly calculated financial metric.
    return f"{float(value) * 100:.2f}%"


def _card_id(kind: str, source_ref: str) -> str:
    return "analysis_card_" + kind + "_" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:16]


def _row(label_zh: str, label_en: str, cells: Sequence[tuple[str, str]], explanation: tuple[str, str]):
    if not cells or any(not zh or not en for zh, en in cells):
        return None
    return {"label": _local(label_zh, label_en), "cells": [_local(zh, en) for zh, en in cells],
            "explanation": _local(*explanation)}


def _card(kind: str, source_ref: str, title: tuple[str, str], subtitle: tuple[str, str],
          columns: Sequence[tuple[str, str]], rows: Sequence[dict], notes: Sequence[tuple[str, str]]):
    if not (2 <= len(columns) <= 4 and 1 <= len(rows) <= 16 and len(notes) <= 5):
        return None
    if any(len(row.get("cells", ())) != len(columns) for row in rows):
        return None
    return {"id": _card_id(kind, source_ref), "kind": kind, "source_ref": source_ref,
            "title": _local(*title), "subtitle": _local(*subtitle),
            "columns": [_local(*column) for column in columns], "rows": list(rows),
            "notes": [_local(*note) for note in notes]}


def _hypothetical(source_ref: str, record: Mapping):
    value = record.get("value")
    if not isinstance(value, Mapping) or value.get("hypothetical_only") is not True:
        return None
    impact = value.get("impact")
    if not isinstance(impact, Mapping) or impact.get("simulation_status") != "complete":
        return None
    trade, before, after = (impact.get(key) for key in ("proposed_trade", "before", "after"))
    if not all(isinstance(item, Mapping) for item in (trade, before, after)):
        return None
    currency = _text(record.get("currency"))
    symbol, side = _text(trade.get("symbol")), _text(trade.get("side"))
    quantity, price, fees = (_quantity(trade.get("quantity")), _amount(trade.get("execution_price"), currency), _amount(trade.get("fees"), currency))
    if None in (symbol, side, quantity, price, fees, currency):
        return None
    side_zh = {"BUY": "买入", "SELL": "卖出"}.get(side)
    if side_zh is None:
        return None
    rows = []
    metric_specs = (
        ("cash", ("现金", "Cash"), lambda item: _amount(item.get("cash"), currency),
         ("账户现金，币种沿用记录。", "Account cash in the recorded currency.")),
        ("portfolio_value", ("账户总价值", "Total account value"), lambda item: _amount(item.get("portfolio_value"), currency),
         ("当前状态的总账户估值。", "Total account value in the recorded state.")),
        ("symbol_quantity", ("目标证券数量", "Target security quantity"), lambda item: _quantity(item.get("symbol_quantity")),
         ("目标证券的记录数量。", "Recorded quantity of the target security.")),
        ("valuation_price", ("目标证券估值价", "Target security valuation price"), lambda item: _amount(item.get("valuation_price"), currency),
         ("按估值价计算持仓市值；与假设成交价分别记录，二者可以相同。", "Position value uses the valuation price; it is recorded separately from the hypothetical execution price, and the two may match.")),
        ("symbol_weight", ("目标证券账户价值权重", "Target security account-value weight"), lambda item: _weight_percent(item.get("symbol_weight")),
         ("目标证券价值除以账户总价值的记录权重；不含未来预测。", "Recorded target value divided by total account value; no future prediction.")),
        ("hhi", ("集中度 HHI（不含现金）", "Concentration HHI (cash excluded)"), lambda item: _number(item.get("hhi"), digits=4),
         ("非现金风险资产归一化权重的平方和，范围为 0 至 1；数值越大表示越集中。", "Sum of squared normalized non-cash risk-asset weights, from 0 to 1; a larger value is more concentrated.")),
    )
    for _key, label, formatter, explanation in metric_specs:
        before_value, after_value = (formatter(item) for item in (before, after))
        row = _row(*label, ((before_value, before_value), (after_value, after_value)), explanation)
        if row:
            rows.append(row)
    return _card("hypothetical_trade_impact", source_ref,
                 ("假设交易影响", "Hypothetical trade impact"),
                 (f"Synthetic 情景：{side_zh} {quantity} 单位 @ {price}；费用 {fees}。",
                  f"Synthetic scenario: {side} {quantity} units @ {price}; fees {fees}."),
                 (("交易前", "Before trade"), ("交易后", "After trade")), rows[:16],
                 (("现金与估值基于记录中披露的状态；费用为用户明确输入。", "Cash and marks use the recorded state; fees are user-supplied."),))


_PERIOD_LABELS = {
    "period_return": ("期间时间加权回报（TWR）", "Period time-weighted return (TWR)"),
    "max_drawdown_magnitude": ("最大回撤幅度", "Maximum drawdown magnitude"),
    "mean_daily_turnover": ("平均日换手", "Mean daily turnover"),
    "portfolio_hhi": ("期末持仓集中度 HHI", "End-of-period holding concentration HHI"),
    "recorded_fee_total": ("已记录费用", "Recorded fees"),
}

_PERIOD_EXPLANATIONS = {
    "period_return": ("把期间内各段账户收益连续相乘，衡量投资本身的表现；有外部入金、出金时须有对应估值边界，不能把入金算成盈利。", "Links account sub-period returns to measure investment performance. External deposits and withdrawals require corresponding valuation boundaries, so deposits are not counted as gains."),
    "max_drawdown_magnitude": ("该期间账户收益路径从先前高点回落到随后低点的最大百分比，描述期间内曾经历的跌幅，不等于期末亏损。", "The largest percentage decline from an earlier peak to a subsequent trough on this period's account return path; it describes a past decline, not the ending loss."),
    "mean_daily_turnover": ("每天买入与卖出的成交金额合计除以当日账户价值，再对有效日期取平均；包含零成交日。", "Daily buy-plus-sell traded value divided by that day's account value, averaged across effective dates including zero-trade days."),
    "portfolio_hhi": ("期末各项非现金持仓占风险资产的权重平方后相加；越大表示越集中。它是期末状态，不是全期平均。", "Sum of squared period-end holding weights normalized across non-cash risk assets. Larger means more concentrated; this is an ending state, not a period average."),
    "recorded_fee_total": ("有效期间内已记录的费用总额。", "Total recorded fees in the effective period."),
}


def _period_display_local(value: object) -> tuple[str | None, str | None]:
    text = _text(value)
    if text is None:
        return None, None
    # The owned projection's registered display uses a Chinese parenthetical
    # for percentage points. Keep that exact value in zh and make only the
    # unit label bilingual; no numeric value is recalculated.
    return text, text.replace(" pp（个百分点）", " pp")


def _period(source_ref: str, record: Mapping):
    value = record.get("value")
    if not isinstance(value, Mapping):
        return None
    effective = value.get("effective_periods")
    metrics = value.get("display_metrics")
    if not isinstance(effective, Mapping) or not isinstance(metrics, list):
        return None
    earlier, later = effective.get("earlier"), effective.get("later")
    if not isinstance(earlier, Mapping) or not isinstance(later, Mapping):
        return None
    earlier_dates = tuple(_text(earlier.get(key)) for key in ("effective_start", "effective_end"))
    later_dates = tuple(_text(later.get(key)) for key in ("effective_start", "effective_end"))
    if any(item is None for item in (*earlier_dates, *later_dates)):
        return None
    rows = []
    for metric in metrics[:16]:
        if not isinstance(metric, Mapping) or metric.get("metric_id") not in _PERIOD_LABELS:
            continue
        left, right, difference = (_period_display_local(metric.get(key)) for key in ("left", "right", "right_minus_left"))
        row = _row(*_PERIOD_LABELS[metric["metric_id"]], (left, right, difference),
                   _PERIOD_EXPLANATIONS[metric["metric_id"]])
        if row:
            rows.append(row)
    return _card("owned_period_comparison", source_ref,
                 ("账户期间比较", "Owned account period comparison"),
                 (f"前期 {earlier_dates[0]} 至 {earlier_dates[1]}；后期 {later_dates[0]} 至 {later_dates[1]}。",
                  f"Earlier {earlier_dates[0]} to {earlier_dates[1]}; later {later_dates[0]} to {later_dates[1]}."),
                 (("前期", "Earlier"), ("后期", "Later"), ("后期－前期", "Later − earlier")), rows,
                 (("日期是已登记完整估值观察的实际计算边界，不补齐缺失边界；若两段共用边界，该日是后段计算基线。", "Dates are effective registered valuation boundaries; missing boundaries are not filled. When periods share a boundary, that day is the later period's calculation baseline."),
                  ("操作和换手统计从期初估值日之后开始，计至期末估值日（含当日）；期初当日操作已经包含在起点状态中。", "Behavior statistics use (effective_start, effective_end]; executions on the start date belong to the valuation baseline, not in-period actions."),
                  ("差值为后期减前期；pp 表示个百分点，例如 1% 到 2% 的差是 +1 个百分点。", "Differences are later minus earlier; pp means percentage points, e.g. 1% to 2% is +1 percentage point.")))


def _outcome_cell(result: Mapping, currency: object, key: str) -> str | None:
    if key == "result_kind":
        kind = result.get(key)
        return {"realized": "已实现 / realized", "marked": "账面估值 / marked"}.get(kind)
    if key == "pnl":
        return _amount(result.get(key), currency)
    return _amount(result.get(key), currency)


_NONCOMPARABLE_REASONS = {
    "没有重叠的投资期间": ("两轮投资期间没有重叠，因此没有共同市场窗口。", "The two investment periods do not overlap, so there is no shared market window."),
    "一方为已实现结果，另一方为持有中的估值结果": ("一轮为已实现结果，另一轮仍为持有中估值。", "One episode is realized while the other remains marked while open."),
    "完整投资期间不同，结果不能视为同区间绩效": ("完整投资期间不同，不能视为同区间表现。", "Full investment periods differ and are not same-window performance."),
    "没有双方共同可验证的市场观察": ("没有双方共同可验证的市场观察。", "There are no mutually verifiable market observations."),
    "双方记录日期不完整一致；缺失日不补齐": ("双方记录日期不完整一致；缺失日不补齐。", "Recorded dates are incomplete or inconsistent; missing days are not filled."),
    "共同日价格或来源、价格类型、版本冲突": ("共同日的价格或来源、价格类型或版本冲突。", "Shared-day price, provenance, price type, or version conflicts."),
}


def _episode_outcome_is_complete(episode: Mapping) -> bool:
    result = episode.get("actual_result")
    if not isinstance(result, Mapping):
        return False
    if result.get("result_kind") not in {"realized", "marked"} or result.get("position_status") not in {"open", "closed"}:
        return False
    if not all(_finite(result.get(key)) for key in ("pnl", "recorded_entry_fees", "recorded_exit_fees")):
        return False
    if not _text(episode.get("opened_at")) or episode.get("status") not in {"open", "closed"}:
        return False
    if result["result_kind"] == "realized":
        return episode.get("status") == result.get("position_status") == "closed" and bool(_text(episode.get("closed_at")))
    return (episode.get("status") == result.get("position_status") == "open"
            and bool(_text(result.get("valuation_at"))))


def _noncomparable_same_stock(source_ref: str, record: Mapping, comparison: Mapping,
                              earlier: Mapping, later: Mapping, currency: str):
    reasons = comparison.get("reasons")
    if (not isinstance(reasons, list) or not reasons or any(reason not in _NONCOMPARABLE_REASONS for reason in reasons)
            or not _episode_outcome_is_complete(earlier) or not _episode_outcome_is_complete(later)):
        return None
    e_result, l_result = earlier["actual_result"], later["actual_result"]
    earlier_end = _text(earlier.get("closed_at")) or _text(e_result.get("valuation_at"))
    later_end = _text(later.get("closed_at")) or _text(l_result.get("valuation_at"))
    if earlier_end is None or later_end is None:
        return None
    kind_cells = {
        "realized": _local("已实现", "Realized"), "marked": _local("账面估值", "Marked"),
    }
    status_cells = {"closed": _local("已结束", "Closed"), "open": _local("持有中", "Open")}
    rows = [
        {"label": _local("结果类型", "Result type"), "cells": [kind_cells[e_result["result_kind"]], kind_cells[l_result["result_kind"]]],
         "explanation": _local("明确区分已实现结果与持有中估值。", "Realized outcomes and open-position marks remain distinct.")},
        _row("实际结果", "Actual result", ((_amount(e_result.get("pnl"), currency),) * 2, (_amount(l_result.get("pnl"), currency),) * 2),
             ("各轮自己的净结果，不是同一市场窗口的比较。", "Each episode's own net result, not a shared-market-window comparison.")),
        _row("已记录入场费用", "Recorded entry fees", ((_amount(e_result.get("recorded_entry_fees"), currency),) * 2, (_amount(l_result.get("recorded_entry_fees"), currency),) * 2),
             ("各轮结果记录中的入场侧费用。", "Entry-side fees recorded in each outcome.")),
        _row("已记录离场费用", "Recorded exit fees", ((_amount(e_result.get("recorded_exit_fees"), currency),) * 2, (_amount(l_result.get("recorded_exit_fees"), currency),) * 2),
             ("各轮结果记录中的离场侧费用。", "Exit-side fees recorded in each outcome.")),
        {"label": _local("持仓状态", "Position status"), "cells": [status_cells[e_result["position_status"]], status_cells[l_result["position_status"]]],
         "explanation": _local("状态来自各轮自己的结果记录。", "Status comes from each episode's own outcome record.")},
        _row("起始时间", "Opened at", ((_text(earlier.get("opened_at")),) * 2, (_text(later.get("opened_at")),) * 2),
             ("各轮已登记的开始时间。", "Registered opening time of each episode.")),
        _row("结束或估值时间", "Closed or marked at", ((earlier_end, earlier_end), (later_end, later_end)),
             ("已结束轮次显示结束时间；持有中轮次显示估值时间。", "Closed episodes show close time; open episodes show mark time.")),
    ]
    rows = [row for row in rows if row is not None]
    return _card("owned_same_stock_comparison", source_ref,
                 ("两轮记录并排查看（不可直接比较）", "Two episode records side by side (not directly comparable)"),
                 (f"较早轮次 {earlier.get('opened_at')} 至 {earlier_end}；较晚轮次 {later.get('opened_at')} 至 {later_end}；未建立可核验的共同市场对比。",
                  f"Earlier episode {earlier.get('opened_at')} to {earlier_end}; later episode {later.get('opened_at')} to {later_end}; no verifiable shared-market comparison was established."),
                 (("较早轮次", "Earlier episode"), ("较晚轮次", "Later episode")), rows,
                 tuple(_NONCOMPARABLE_REASONS[reason] for reason in reasons))


def _same_stock(source_ref: str, record: Mapping):
    value = record.get("value")
    if not isinstance(value, Mapping) or not isinstance(value.get("comparison"), Mapping):
        return None
    comparison = value["comparison"]
    earlier, later = comparison.get("earlier"), comparison.get("later")
    if not isinstance(earlier, Mapping) or not isinstance(later, Mapping):
        return None
    e_result, l_result = earlier.get("actual_result"), later.get("actual_result")
    if not isinstance(e_result, Mapping) or not isinstance(l_result, Mapping):
        return None
    e_id, l_id = _text(earlier.get("episode_id")), _text(later.get("episode_id"))
    if not e_id or not l_id:
        return None
    currency = _text(record.get("currency"))
    if currency is None:
        return None
    if comparison.get("status") == "unavailable":
        return _noncomparable_same_stock(source_ref, record, comparison, earlier, later, currency)
    if comparison.get("status") not in {"comparable", "partially_comparable"}:
        return None
    rows = []
    for key, label in (("result_kind", ("结果类型", "Result type")), ("pnl", ("实际结果", "Actual result")),
                       ("recorded_entry_fees", ("已记录入场费用", "Recorded entry fees")),
                       ("recorded_exit_fees", ("已记录离场费用", "Recorded exit fees"))):
        left, right = _outcome_cell(e_result, currency, key), _outcome_cell(l_result, currency, key)
        row = _row(*label, ((left, left), (right, right)),
                   ("各轮自己的实际结果；不把不同完整期间当作同一段市场表现。", "Each episode's own actual result; full periods are not treated as one market window."))
        if row:
            rows.append(row)
    for difference in comparison.get("differences", ()):
        if not isinstance(difference, Mapping):
            continue
        dimension = difference.get("dimension")
        left, right = _number(difference.get("a_value")), _number(difference.get("b_value"))
        label = _SAME_STOCK_DIMENSIONS.get(dimension)
        if label is None or left is None or right is None:
            continue
        row = _row(*label,
                   ((left, left), (right, right)),
                   ("仅记录共同时间范围内的已登记操作次数。", "Only registered action counts in the shared time window."))
        if row:
            rows.append(row)
    return _card("owned_same_stock_comparison", source_ref,
                 ("同股两轮投资比较", "Owned same-stock comparison"),
                 (f"较早轮次 {e_id} 与较晚轮次 {l_id}；结果明确区分已实现与账面估值。",
                  f"Earlier {e_id} and later {l_id}; realized and marked results remain distinct."),
                 (("较早轮次", "Earlier episode"), ("较晚轮次", "Later episode")), rows[:16],
                 (("仅比较当前账户的两轮已登记投资，不使用同行或专业账户数据。", "Only two registered episodes in this account; no peer or professional-account data."),))


_TECHNICAL_LABELS = {
    "sma_5": ("SMA(5)", "SMA(5)"), "sma_20": ("SMA(20)", "SMA(20)"), "sma_50": ("SMA(50)", "SMA(50)"),
    "ema_12": ("EMA(12)", "EMA(12)"), "ema_26": ("EMA(26)", "EMA(26)"),
    "macd_12_26_9": ("MACD(12,26,9)", "MACD(12,26,9)"), "rsi_14": ("RSI(14)", "RSI(14)"),
    "atr_14": ("ATR(14)", "ATR(14)"), "volume_ratio_5": ("成交量比(5)", "Volume ratio(5)"),
}

_TECHNICAL_DEFINITIONS = {
    "sma_5": ("最近 5 个已完成日线收盘价的简单移动平均。", "Simple moving average of the last 5 completed daily closes."),
    "sma_20": ("最近 20 个已完成日线收盘价的简单移动平均。", "Simple moving average of the last 20 completed daily closes."),
    "sma_50": ("最近 50 个已完成日线收盘价的简单移动平均。", "Simple moving average of the last 50 completed daily closes."),
    "ema_12": ("EMA(12)，以首个完整周期 SMA 初始化。", "EMA(12), seeded with the first full-period SMA."),
    "ema_26": ("EMA(26)，以首个完整周期 SMA 初始化。", "EMA(26), seeded with the first full-period SMA."),
    "macd_12_26_9": ("MACD 线为 EMA(12)－EMA(26)；信号线为 MACD 的 EMA(9)；柱为两者之差，未额外倍增。", "MACD line is EMA(12) minus EMA(26); signal is its EMA(9); histogram is their difference, not additionally doubled."),
    "rsi_14": ("Wilder RSI(14) 强弱振荡指标，不是预测。", "Wilder RSI(14) strength oscillator, not a forecast."),
    "atr_14": ("Wilder ATR(14) 的价格波动范围。", "Wilder ATR(14) price range."),
    "volume_ratio_5": ("最新完整日成交量除以前 5 个完整日平均成交量。", "Latest completed volume divided by the prior 5 completed-day average."),
}


def _technical(source_ref: str, record: Mapping):
    value = record.get("value")
    if not isinstance(value, Mapping) or not isinstance(value.get("metrics"), Mapping):
        return None
    metrics, definitions = value["metrics"], value.get("definitions")
    if not isinstance(definitions, Mapping):
        return None
    rows = []
    definition_keys = {"volume_ratio_5": "volume_ratio"}
    currency = _text(value.get("currency"))
    if currency is None:
        return None
    for key in _TECHNICAL_LABELS:
        metric = metrics.get(key)
        definition = _text(definitions.get(definition_keys.get(
            key, "macd" if key == "macd_12_26_9" else key.split("_")[0]
        )))
        if (not isinstance(metric, Mapping) or metric.get("status") != "available" or not definition
                or key not in _TECHNICAL_DEFINITIONS):
            continue
        unit = ("0–100", "0–100") if key == "rsi_14" else (
            ("倍", "times") if key == "volume_ratio_5" else (currency, currency)
        )
        display = metric.get("display_value")
        if isinstance(display, str) and _text(display):
            row = _row(*_TECHNICAL_LABELS[key], ((display, display), unit, _TECHNICAL_DEFINITIONS[key]),
                       ("来自已完成的公开日线指标，不是交易结论。", "From completed public daily-bar indicators, not a trading conclusion."))
            if row:
                rows.append(row)
        elif key == "macd_12_26_9" and isinstance(display, Mapping):
            for part, label_zh, label_en in (("line", "线", "line"), ("signal", "信号", "signal"), ("histogram", "柱", "histogram")):
                rendered = _text(display.get(part))
                row = _row(_TECHNICAL_LABELS[key][0] + " " + label_zh, _TECHNICAL_LABELS[key][1] + " " + label_en,
                           ((rendered, rendered), unit, _TECHNICAL_DEFINITIONS[key]),
                           ("来自已完成的公开日线指标，不是交易结论。", "From completed public daily-bar indicators, not a trading conclusion."))
                if row:
                    rows.append(row)
    security_id, date, adjust = (_text(value.get(key)) for key in ("security_id", "last_closed_bar_date", "adjust"))
    if not security_id or not date or not adjust:
        return None
    adjust_label = {
        "none": ("不复权", "Unadjusted"), "qfq": ("前复权", "Forward-adjusted"),
        "hfq": ("后复权", "Backward-adjusted"),
    }.get(adjust)
    if adjust_label is None:
        return None
    return _card("public_technical", source_ref, ("公开技术指标", "Public technical indicators"),
                 (f"公开证券 {security_id}，最后完整日线 {date}，{adjust_label[0]}口径。",
                  f"Public security {security_id}; last completed daily bar {date}, {adjust_label[1]} basis."),
                 (("数值", "Value"), ("单位", "Unit"), ("定义", "Definition")), rows[:16],
                 (("公开研究资料，不是账户持仓事实、交易信号或建议。", "Public research, not an account holding fact, signal, or recommendation."),))


_FINANCIAL_LABELS = {
    "revenue": ("营业收入", "Revenue"), "net_income": ("净利润", "Net income"),
    "net_income_attributable_to_parent": ("归母净利润", "Net income attributable to parent"),
    "total_assets": ("资产总计", "Total assets"), "total_liabilities": ("负债合计", "Total liabilities"),
    "total_equity": ("所有者权益", "Total equity"), "operating_cash_flow": ("经营现金流", "Operating cash flow"),
    "return_on_equity": ("净资产收益率", "Return on equity"), "gross_margin": ("毛利率", "Gross margin"),
    "net_profit_margin": ("净利率", "Net profit margin"), "debt_to_assets": ("资产负债率", "Debt-to-assets"),
}

_SAME_STOCK_DIMENSIONS = {
    "open_position": ("建仓次数", "Open-position actions"),
    "add_position": ("加仓次数", "Add-position actions"),
    "reduce_position": ("减仓次数", "Reduce-position actions"),
    "close_position": ("清仓次数", "Close-position actions"),
    "cost_raising_additions": ("抬高平均成本的加仓次数", "Cost-raising additions"),
    "reductions_before_recorded_trough": ("记录谷值前的减仓次数", "Reductions before recorded trough"),
}


def _financial_value(field: Mapping) -> str | None:
    display = _text(field.get("display_value"))
    if display:
        return display
    value, unit = _number(field.get("value")), _text(field.get("unit"))
    return f"{value} {unit}" if value is not None and unit is not None else None


def _financials(source_ref: str, record: Mapping):
    value = record.get("value")
    if not isinstance(value, Mapping) or not isinstance(value.get("statements"), Mapping):
        return None
    security_id = _text(value.get("security_id"))
    if security_id is None:
        return None
    rows, has_local_derivation = [], False
    for section in ("income_statement", "balance_sheet", "cash_flow_statement", "key_indicators"):
        item = value["statements"].get(section)
        if not isinstance(item, Mapping) or not isinstance(item.get("fields"), Mapping):
            continue
        for key, field in item["fields"].items():
            if key not in _FINANCIAL_LABELS or not isinstance(field, Mapping) or field.get("status") != "available":
                continue
            period = _text(field.get("report_period")) or _text(item.get("report_period"))
            if period is None:
                continue
            rendered = _financial_value(field)
            derived = isinstance(field.get("derived_from"), list) and bool(field["derived_from"])
            if derived:
                has_local_derivation = True
                explanation = (
                    "该字段由记录列出的报表字段在本地派生；保留对应报告期和单位。",
                    "This field is locally derived from the record-listed statement fields; its report period and unit are retained.",
                )
            else:
                explanation = (
                    "保留提供方报告期和单位；不混合不同报表期间。",
                    "Provider report period and unit retained; statement periods are not mixed.",
                )
            row = _row(*_FINANCIAL_LABELS[key], ((rendered, rendered), (period, period)),
                       explanation)
            if row:
                rows.append(row)
    notes = [("除特别标注为本地派生的字段外，金额、币种、规模及百分比沿用提供方披露；不可跨报告期混算。",
              "Except where explicitly marked locally derived, amounts, currency, scale, and percentages retain provider reporting; do not mix report periods.")]
    if has_local_derivation:
        notes.append(("“资产负债率”等本地派生字段不应表述为提供方直接报告。",
                      "Locally derived fields such as debt-to-assets are not provider-directly reported."))
    return _card("public_financials", source_ref, ("公开财务字段", "Public financial fields"),
                 (f"公开证券 {security_id}；最新可取得披露不是历史时点重建。",
                  f"Public security {security_id}; latest retrievable disclosure is not a historical point-in-time reconstruction."),
                 (("数值", "Value"), ("报告期", "Report period")), rows[:16], notes)


_BUILDERS = {
    "hypothetical_trade_impact": _hypothetical,
    "owned_period_comparison": _period,
    "owned_same_stock_comparison": _same_stock,
    "public_technical": _technical,
    "public_financials": _financials,
}


def build_analysis_cards(records: Mapping[str, object], allowed_refs: Sequence[str], cited_refs: Sequence[str]) -> list[dict]:
    """Build at most five cards from the intersection of cited and receipt-allowed refs.

    All inputs are treated as untrusted shapes.  The function is intentionally
    side-effect free, including when a candidate record is malformed.
    """
    if not isinstance(records, Mapping):
        return []
    allowed = {ref for ref in allowed_refs if isinstance(ref, str)}
    cards, seen = [], set()
    for ref in cited_refs:
        if len(cards) >= 5 or not isinstance(ref, str) or ref in seen or ref not in allowed:
            continue
        seen.add(ref)
        record = records.get(ref)
        same_stock_unavailable = (record.get("kind") == "owned_same_stock_comparison"
                                  and record.get("availability") == "insufficient_evidence") if isinstance(record, Mapping) else False
        if (not isinstance(record, Mapping) or record.get("ref") != ref
                or (record.get("availability") != "complete" and not same_stock_unavailable)
                or record.get("kind") not in CARD_KINDS or not _finite_tree(record.get("value"))):
            continue
        try:
            card = _BUILDERS[record["kind"]](ref, record)
        except (AttributeError, KeyError, TypeError, ValueError):
            card = None
        if card is not None:
            try:
                validate_analysis_cards([card])
            except ValueError:
                continue
            cards.append(card)
    return cards


def validate_analysis_cards(value: object) -> None:
    """Validate the archive/transport shape without granting card authoring rights."""
    if value is None:
        return
    if not isinstance(value, list) or len(value) > 5:
        raise ValueError("invalid_analysis_cards")

    def is_local(item: object, maximum: int) -> bool:
        return (isinstance(item, Mapping) and set(item) == {"zh", "en"}
                and all(isinstance(item.get(language), str) and 1 <= len(item[language]) <= maximum
                        for language in ("zh", "en")))

    seen_ids = set()
    for card in value:
        required = {"id", "kind", "source_ref", "title", "subtitle", "columns", "rows", "notes"}
        if not isinstance(card, Mapping) or set(card) != required or card.get("kind") not in CARD_KINDS:
            raise ValueError("invalid_analysis_cards")
        identifier, source_ref = card.get("id"), card.get("source_ref")
        if (not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or identifier in seen_ids
                or not isinstance(source_ref, str) or not 1 <= len(source_ref) <= 1000):
            raise ValueError("invalid_analysis_cards")
        seen_ids.add(identifier)
        if not is_local(card.get("title"), 160) or not is_local(card.get("subtitle"), 1200):
            raise ValueError("invalid_analysis_cards")
        columns, rows, notes = card.get("columns"), card.get("rows"), card.get("notes")
        if not isinstance(columns, list) or not 2 <= len(columns) <= 4 or not isinstance(rows, list) or not 1 <= len(rows) <= 16 or not isinstance(notes, list) or len(notes) > 5:
            raise ValueError("invalid_analysis_cards")
        for item in columns:
            if not is_local(item, 160):
                raise ValueError("invalid_analysis_cards")
        for item in notes:
            if not is_local(item, 1200):
                raise ValueError("invalid_analysis_cards")
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"label", "cells", "explanation"} or not isinstance(row.get("cells"), list) or len(row["cells"]) != len(columns):
                raise ValueError("invalid_analysis_cards")
            if not is_local(row["label"], 160) or not is_local(row["explanation"], 1200):
                raise ValueError("invalid_analysis_cards")
            if any(not is_local(cell, 1200) for cell in row["cells"]):
                raise ValueError("invalid_analysis_cards")
