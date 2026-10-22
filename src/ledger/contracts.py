"""Strict, decimal-valued ledger inputs. No inferred entitlements or tax rates."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

EVENT_TYPES = frozenset({"deposit", "withdrawal", "opening_position", "opening_cash_adjustment", "split", "stock_dividend",
    "cash_dividend", "withholding_tax", "rights_subscription", "rights_delivery", "security_exchange",
    "delisting", "return_of_capital", "interest", "fee", "transfer_in", "transfer_out"})
ZERO = Decimal(0)


def number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name}: required decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: invalid decimal number") from None
    if not result.is_finite() or abs(result) > Decimal("1e18") or result.as_tuple().exponent < -10:
        raise ValueError(f"{name}: finite decimal with at most 10 decimal places required")
    if positive and result <= 0 or nonnegative and result < 0:
        raise ValueError(f"{name}: invalid sign")
    return result


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ValueError(f"{name}: non-empty text required (max 1000)")
    return value.strip()


def day(value, name="effective_date"):
    try:
        return date.fromisoformat(text(value, name)).isoformat()
    except ValueError:
        raise ValueError(f"{name}: ISO calendar date required") from None


def money(value):
    return None if value is None else format(value.normalize(), "f") if value else "0"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def security(raw, prefix=""):
    from src.core.canonical_execution import instrument_ref
    item = instrument_ref(local_symbol=text(raw.get(prefix + "symbol"), prefix + "symbol"),
        market=text(raw.get(prefix + "market"), prefix + "market"),
        security_type=text(raw.get(prefix + "security_type", "equity"), prefix + "security_type"),
        currency=text(raw.get("currency"), "currency").upper())
    if item.security_type not in {"equity", "etf", "fund"}:
        raise ValueError("unsupported_security_type_without_contract_multiplier")
    if not item.instrument_id:
        raise ValueError("qualified instrument required")
    return {"instrument_id": item.instrument_id, "symbol": item.local_symbol, "market": item.market,
        "security_type": item.security_type, "currency": item.currency}


def opening(raw):
    if not isinstance(raw, dict):
        raise ValueError("opening must be an object")
    currency = text(raw.get("currency"), "currency").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency: three-letter code required")
    result = {"schema_version": "account_opening.v1", "opening_date": day(raw.get("opening_date")),
        "currency": currency, "initial_cash": money(number(raw.get("initial_cash"), "initial_cash", nonnegative=True)),
        "source_ref": text(raw.get("source_ref"), "source_ref"), "display_name": text(raw.get("display_name"), "display_name")}
    return result


def event(raw, currency):
    if not isinstance(raw, dict):
        raise ValueError("event must be an object")
    kind = text(raw.get("event_type"), "event_type")
    if kind not in EVENT_TYPES:
        raise ValueError("unsupported ledger event_type")
    result = {"event_id": text(raw.get("event_id"), "event_id"), "event_type": kind,
        "effective_date": day(raw.get("effective_date")), "currency": text(raw.get("currency"), "currency").upper(),
        "source_ref": text(raw.get("source_ref"), "source_ref"), "note": str(raw.get("note") or "")[:2000]}
    if result["currency"] != currency:
        raise ValueError("mixed_currency_without_fx")
    sequence = raw.get("sequence", 0)
    if isinstance(sequence, str) and sequence.isdigit():
        sequence = int(sequence)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not 0 <= sequence <= 1_000_000:
        raise ValueError("sequence: nonnegative integer required")
    result["sequence"] = sequence
    if kind in {"opening_position", "split", "stock_dividend", "cash_dividend", "withholding_tax",
                "rights_subscription", "rights_delivery", "security_exchange", "delisting",
                "return_of_capital", "transfer_in", "transfer_out"}:
        result["instrument"] = security(raw)
    for name in {
        "opening_cash_adjustment": ("amount",),
        "deposit": ("amount",), "withdrawal": ("amount",), "interest": ("amount",), "fee": ("amount",),
        "withholding_tax": ("amount",), "cash_dividend": ("amount", "tax"),
        "rights_subscription": ("amount",), "delisting": ("amount",), "return_of_capital": ("amount",),
        "opening_position": ("quantity", "cost_basis", "opening_price"),
        "transfer_in": ("quantity", "cost_basis", "transfer_value"),
        "transfer_out": ("quantity", "transfer_value"), "rights_delivery": ("quantity",),
        "security_exchange": ("quantity", "amount", "cash_cost_basis"),
        "split": ("ratio",), "stock_dividend": ("quantity",),
    }.get(kind, ()):
        default = "0" if name in {"tax", "amount", "cash_cost_basis"} and kind in {"cash_dividend", "security_exchange", "delisting"} else None
        result[name] = money(number(raw.get(name, default), name,
            positive=name in {"quantity", "opening_price", "ratio", "transfer_value"}, nonnegative=kind != "opening_cash_adjustment"))
    if kind in {"deposit", "withdrawal", "interest", "fee", "withholding_tax", "rights_subscription", "return_of_capital", "cash_dividend"}:
        number(result["amount"], "amount", positive=True)
    if kind == "opening_cash_adjustment":
        result["note"] = text(raw.get("reason") or raw.get("note"), "reason")
        if Decimal(result["amount"]) == 0: raise ValueError("cash adjustment must be nonzero")
    if kind == "cash_dividend":
        result["ex_date"] = day(raw.get("ex_date"), "ex_date")
        if result["ex_date"] > result["effective_date"]:
            raise ValueError("dividend ex_date must not follow payment date")
        if Decimal(result["tax"]) > Decimal(result["amount"]):
            raise ValueError("dividend tax exceeds gross amount")
    if kind == "rights_delivery":
        result["subscription_id"] = text(raw.get("subscription_id"), "subscription_id")
    if kind == "security_exchange":
        result["new_instrument"] = security(raw, "new_")
        if result["new_instrument"]["instrument_id"] == result["instrument"]["instrument_id"]:
            raise ValueError("security exchange requires a different destination instrument")
    return result
