"""Compare a complete broker closing snapshot without manufacturing corrections."""
from decimal import Decimal

from .contracts import day, money, number, security, text


def statement(raw, currency):
    if not isinstance(raw, dict) or raw.get("positions_complete") is not True:
        raise ValueError("statement requires positions_complete=true, including an explicitly empty positions list")
    if raw.get("currency") != currency:
        raise ValueError("mixed_currency_without_fx")
    positions, seen = [], set()
    if not isinstance(raw.get("positions"), list):
        raise ValueError("statement positions must be a list")
    for row in raw["positions"]:
        instrument = security({**row, "currency": currency})
        if instrument["instrument_id"] in seen:
            raise ValueError("duplicate statement instrument")
        seen.add(instrument["instrument_id"])
        result = {**instrument, "quantity": money(number(row.get("quantity"), "quantity", nonnegative=True))}
        for field in ("cost_basis", "market_value"):
            result[field] = money(number(row[field], field, nonnegative=True)) if row.get(field) not in (None, "") else None
        positions.append(result)
    ids = raw.get("execution_refs")
    if ids is not None and (not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids)):
        raise ValueError("execution_refs must be a unique list of source execution IDs")
    if ids is not None and day(raw.get("executions_from"), "executions_from") > day(raw.get("as_of"), "as_of"):
        raise ValueError("execution window starts after statement date")
    return {"statement_id": text(raw.get("statement_id"), "statement_id"),
        "as_of": day(raw.get("as_of"), "as_of"), "source_ref": text(raw.get("source_ref"), "source_ref"),
        "currency": currency, "positions_complete": True, "positions": sorted(positions, key=lambda x: x["instrument_id"]),
        "cash": money(number(raw.get("cash"), "cash")),
        "equity": money(number(raw["equity"], "equity")) if raw.get("equity") not in (None, "") else None,
        "execution_refs": ids, "executions_from": day(raw.get("executions_from"), "executions_from") if ids is not None else None,
        "money_tolerance": money(number(raw.get("money_tolerance", "0.01"), "money_tolerance", nonnegative=True)),
        "quantity_tolerance": money(number(raw.get("quantity_tolerance", "0.00000001"), "quantity_tolerance", nonnegative=True))}


def reconcile(snapshot, expected, *, execution_refs=None):
    differences, unavailable = [], []
    comparisons = []
    def compare(field, actual, recorded, tolerance, instrument=None):
        if recorded is None:
            return
        if actual is None:
            unavailable.append({"field": field, "instrument_id": instrument, "reason": "ledger_value_unavailable"})
            return
        delta = Decimal(actual) - Decimal(recorded)
        item = {"field": field, "instrument_id": instrument, "ledger": actual, "statement": recorded, "difference": money(delta)}
        comparisons.append(item)
        if abs(delta) > Decimal(tolerance):
            differences.append(item)
    compare("cash", snapshot["cash"], expected["cash"], expected["money_tolerance"])
    actual = {x["instrument_id"]: x for x in snapshot["positions"]}
    recorded = {x["instrument_id"]: x for x in expected["positions"]}
    for identifier in sorted(actual.keys() | recorded.keys()):
        a, b = actual.get(identifier), recorded.get(identifier)
        compare("quantity", a["quantity"] if a else "0", b["quantity"] if b else "0", expected["quantity_tolerance"], identifier)
        for field in ("cost_basis", "market_value"):
            if b and b[field] is not None:
                value = a[field] if a else "0"
                if field == "market_value" and a and a["price_date"] != expected["as_of"]:
                    value = None
                compare(field, value, b[field], expected["money_tolerance"], identifier)
    equity = snapshot["equity"]
    if any(p["price_date"] != expected["as_of"] for p in snapshot["positions"]):
        equity = None
    compare("equity", equity, expected["equity"], expected["money_tolerance"])
    if expected["execution_refs"] is not None:
        observed, supplied = set(execution_refs or []), set(expected["execution_refs"])
        for kind, values in (("missing_execution", supplied-observed), ("unexpected_execution", observed-supplied)):
            differences.extend({"field": kind, "source_execution_id": ref} for ref in sorted(values))
    if snapshot["errors"]:
        unavailable.append({"field": "ledger", "reason": "invalid_ledger_events"})
    return {"schema_version": "account_reconciliation.v1", "subject_id": snapshot["subject_id"], "account_id": snapshot["account_id"],
        "statement_id": expected["statement_id"], "as_of": expected["as_of"], "currency": expected["currency"],
        "status": "mismatch" if differences else "incomplete" if unavailable else "matched",
        "comparisons": comparisons, "differences": differences, "unavailable": unavailable,
        "tolerances": {"money": expected["money_tolerance"], "quantity": expected["quantity_tolerance"]},
        "checked_fields": sorted({x["field"] for x in comparisons}),
        "limitations": ["只对明确提供的字段判定；未提供成本、市值或总资产不代表这些字段一致。",
            "交易核对仅在明确提供完整时间窗口与source_execution_id时执行，不用日期金额猜测成交身份。",
            "报告不会自动改写余额、成本或成交；修正须单独预览并确认，保留原件。"]}
