"""Server-dated plans and append-only notes; hindsight never becomes foresight."""
from datetime import datetime, timezone

from .contracts import money, number, security, text


def prepare(params, repo, subject, account, now=None):
    now = now or datetime.now(timezone.utc)
    profile = repo.ledger_profile(subject, account)
    if profile is None:
        raise ValueError("ledger profile required")
    kind = params["mode"]
    raw = params.get("entry")
    if not isinstance(raw, dict):
        raise ValueError("entry object required")
    result = {"entry_id": text(raw.get("entry_id"), "entry_id"), "entry_type": kind,
        "text": text(raw.get("text"), "text"), "subject_id": subject, "account_id": account}
    existing = repo.journal_entries(subject, account)
    if any(x["entry_id"] == result["entry_id"] for x in existing):
        raise ValueError("journal ID exists; original entries are immutable, add a follow-up note")
    if kind == "plan":
        trade = raw.get("proposed_trade")
        if not isinstance(trade, dict):
            raise ValueError("proposed_trade object required")
        instrument = security({**trade, "currency": profile["currency"]})
        side = trade.get("side")
        if side not in {"BUY", "SELL"}:
            raise ValueError("plan side must be BUY or SELL")
        result.update({"proposed_trade": {**instrument, "side": side,
            "quantity": money(number(trade.get("quantity"), "quantity", positive=True)),
            "price": money(number(trade.get("price"), "price", positive=True)),
            "fee": money(number(trade.get("fee"), "fee", nonnegative=True))},
            "invalidation": text(raw.get("invalidation"), "invalidation"),
            "source_fingerprint": params.get("source_fingerprint"), "timing": "recorded_now_not_backdated"})
    elif kind == "note":
        result["retrospective"] = True
        if raw.get("plan_id"):
            if not any(x["entry_id"] == raw["plan_id"] and x["entry_type"] == "plan" for x in existing):
                raise ValueError("note plan is missing or foreign")
            result["plan_id"] = raw["plan_id"]
    elif kind == "link":
        plan = next((x for x in existing if x["entry_id"] == raw.get("plan_id") and x["entry_type"] == "plan"), None)
        trade = next((x for x in repo.executions(subject, account) if x.execution_id == raw.get("execution_id")), None)
        if plan is None or trade is None:
            raise ValueError("plan or execution is missing or foreign")
        if any(x.get("execution_id") == trade.execution_id and x["entry_type"] == "link" for x in existing):
            raise ValueError("execution already linked; add a follow-up note for corrections")
        recorded = datetime.fromisoformat(plan["recorded_at"])
        instant = trade.event_time.instant_utc
        timing = "unverifiable_date_only" if instant is None else "before_execution" if recorded < instant.to_pydatetime() else "retrospective"
        result.update({"plan_id": plan["entry_id"], "execution_id": trade.execution_id, "timing": timing,
            "same_instrument": trade.instrument.instrument_id == plan["proposed_trade"]["instrument_id"],
            "same_side": trade.side == plan["proposed_trade"]["side"],
            "planned_quantity": plan["proposed_trade"]["quantity"], "filled_quantity": str(trade.executed_quantity)})
    else:
        raise ValueError("unsupported journal type")
    return result
