"""Schema-tolerant normalisation of public financial statement frames."""
from __future__ import annotations

import math
import re
from datetime import date


_FIELDS = {
    "income_statement": {"revenue": ("营业收入", "营业总收入", "REVENUE", "TOTAL_OPERATE_INCOME"), "net_income": ("净利润", "净利润(含少数股东损益)", "NETPROFIT"), "net_income_attributable_to_parent": ("归属于母公司所有者的净利润", "归属于母公司股东的净利润", "PARENT_NETPROFIT")},
    "balance_sheet": {"total_assets": ("资产总计", "资产总额", "TOTAL_ASSETS"), "total_liabilities": ("负债合计", "负债总计", "TOTAL_LIABILITIES"), "total_equity": ("所有者权益(或股东权益)合计", "股东权益合计", "所有者权益合计", "TOTAL_EQUITY")},
    "cash_flow_statement": {"operating_cash_flow": ("经营活动产生的现金流量净额", "经营活动现金流量净额", "NETCASH_OPERATE")},
    "key_indicators": {"return_on_equity": ("净资产收益率", "净资产收益率(%)", "ROE", "ROEJQ"), "gross_margin": ("销售毛利率", "毛利率", "GROSS_PROFIT_RATIO"), "net_profit_margin": ("销售净利率", "净利率", "NETPROFIT_MARGIN")},
}


def _finite(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _percent_display(ratio):
    return f"{float(ratio) * 100:.2f}%"


def _date_text(value):
    text = str(value)[:10]
    compact = text[:8] if len(text) >= 8 and text[:8].isdigit() else text.replace("-", "")
    if not re.fullmatch(r"\d{8}", compact):
        return None
    try:
        return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8])).isoformat()
    except ValueError:
        return None


def _latest_row(frame, *, as_of=None):
    if frame is None or getattr(frame, "empty", True):
        return None
    columns = {str(column): column for column in frame.columns}
    date_column = next((columns[name] for name in ("报告日", "REPORT_DATE", "报告期", "日期") if name in columns), None)
    if date_column is None:
        return None
    rows = []
    cutoff = str(as_of)[:10] if as_of is not None else None
    for _, row in frame.iterrows():
        raw_date = row.get(date_column)
        if raw_date is not None and len(str(raw_date)) >= 8:
            report_period = _date_text(raw_date)
            if report_period is not None and (cutoff is None or report_period <= cutoff):
                rows.append((report_period, row))
    return max(rows, key=lambda item: item[0])[1] if rows else None


def _period(row):
    if row is not None:
        for field in ("报告日", "REPORT_DATE", "报告期", "日期"):
            if field in row:
                return _date_text(row[field])
    return None


def _statement_currency(row):
    if row is not None:
        for name in ("币种", "CURRENCY", "币别"):
            if name in row and isinstance(row[name], str) and row[name].strip():
                return row[name].strip()[:12]
    return None


def _field(row, candidates, *, kind):
    if row is not None:
        for name in candidates:
            if name in row:
                value = _finite(row[name])
                if value is not None:
                    result = {"status": "available", "value": value, "source_field": name}
                    if kind == "amount":
                        currency = _statement_currency(row)
                        result["unit"] = currency or "provider_currency_not_stated"
                        result["scale"] = "provider_reported_amount_not_normalized"
                    elif kind == "percent":
                        # Preserve the established provider contract: values are
                        # provider percentage points (16.75 means 16.75%).
                        result["scale"] = "provider_reported_percent"
                        result["unit"] = "percent"
                        result["display_value"] = f"{value:.2f}%"
                    return result
    return {"status": "unavailable", "reason": "field_not_provided"}


def normalize_financials(statements, *, as_of=None):
    """Return small, stable statements/key indicators with field-level status."""
    statements = statements if isinstance(statements, dict) else {}
    aliases = {"income_statement": "income", "balance_sheet": "balance", "cash_flow_statement": "cash_flow", "key_indicators": "indicators"}
    output = {}
    for section, names in _FIELDS.items():
        frame = statements.get(section)
        if frame is None:
            frame = statements.get(aliases[section])
        row = _latest_row(frame, as_of=as_of)
        provider_error = statements.get(section + "_error") or statements.get(aliases[section] + "_error")
        kind = "percent" if section == "key_indicators" else "amount"
        item = {"report_period": _period(row), "statement_currency": _statement_currency(row),
                "status": "available" if row is not None else "unavailable",
                "fields": {key: _field(row, candidates, kind=kind) for key, candidates in names.items()}}
        if row is None:
            item["reason"] = str(provider_error or ("no_report_period_on_or_before_fetch" if frame is not None and not getattr(frame, "empty", True) else "statement_not_provided"))[:80]
        output[section] = item
    assets = output["balance_sheet"]["fields"]["total_assets"]
    liabilities = output["balance_sheet"]["fields"]["total_liabilities"]
    if assets.get("status") == liabilities.get("status") == "available" and assets["value"] > 0:
        output["key_indicators"]["fields"]["debt_to_assets"] = {
            "status": "available", "value": liabilities["value"] / assets["value"], "unit": "ratio",
            "display_value": _percent_display(liabilities["value"] / assets["value"]),
            "derived_from": ["total_liabilities", "total_assets"],
            "report_period": output["balance_sheet"]["report_period"],
            "source_section": "balance_sheet",
        }
        if output["key_indicators"]["status"] == "unavailable":
            output["key_indicators"]["status"] = "partial"
    else:
        output["key_indicators"]["fields"]["debt_to_assets"] = {"status": "unavailable", "reason": "required_balance_fields_unavailable"}
    return output
