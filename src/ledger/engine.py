"""Decimal account fold. Actual trades stay trades; corporate actions never fake fills.

Daily actions occur before that day's trades; cash payments occur afterwards.
Explicit sequence orders actions of the same kind. This is a declared EOD
ledger convention, not an assertion about missing intraday timestamps.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext

from .contracts import ZERO, fingerprint, money


def project(profile, events, executions, prices, *, as_of=None):
    """Fold authoritative facts through a calendar-date cutoff, without network."""
    with localcontext() as context:
        context.prec = 34
        return _project(profile, events, executions, prices, as_of=as_of)


def _project(profile, events, executions, prices, *, as_of):
    opening_date, currency = profile["opening_date"], profile["currency"]
    voids = {e["target_event_id"] for e in events if e["event_type"] == "void"}
    active = [e for e in events if e["event_type"] != "void" and e["event_id"] not in voids]
    rows = []
    for e in active:
        item = deepcopy(e)
        kind = e["event_type"]
        if kind == "cash_dividend":
            rows.append({**item, "effective_date": item["ex_date"], "event_type": "dividend_accrual", "phase": 1})
        rows.append({**item, "phase": 0 if kind in {"opening_position", "opening_cash_adjustment"} else 1
            if kind in {"split", "stock_dividend", "rights_delivery", "security_exchange", "delisting", "return_of_capital"}
            else 3})
    for execution in executions:
        if "execution:" + execution.execution_id in voids:
            continue
        rows.append({"event_id": "execution:" + execution.execution_id, "event_type": execution.side.lower(),
            "effective_date": execution.event_time.calendar_date.isoformat(), "phase": 2,
            "sequence": execution.execution_sequence or 0, "trade_time": execution.event_time.ordering_key,
            "instrument": {"instrument_id": execution.instrument.instrument_id,
                "symbol": execution.instrument.local_symbol, "currency": execution.instrument.currency,
                "market": execution.instrument.market, "security_type": execution.instrument.security_type},
            "quantity": str(execution.executed_quantity), "price": str(execution.executed_price),
            "fee": str(execution.fee.amount) if execution.fee.amount is not None else None,
            "source_execution_id": execution.source_execution_id, "source_ref": execution.execution_id,
            "currency": execution.instrument.currency, "fee_currency": execution.fee.currency})
    all_dates = {opening_date, *(r["effective_date"] for r in rows), *(p.date.isoformat() for p in prices)}
    boundary = as_of or max(all_dates)
    if boundary < opening_date:
        raise ValueError("as_of precedes account opening")
    excluded = sum(r["effective_date"] < opening_date for r in rows if r["event_type"] in {"buy", "sell"})
    rows = [r for r in rows if r["effective_date"] <= boundary and not
        (r["effective_date"] < opening_date and r["event_type"] in {"buy", "sell"})]
    rows.sort(key=lambda r: (r["effective_date"], r["phase"], r.get("trade_time", ""), r.get("sequence", 0), r["event_id"]))
    price_map = {}
    for fact in prices:
        if fact.price_type != "unadjusted_close" or fact.currency != currency or fact.date.isoformat() > boundary:
            continue
        key = (fact.instrument.instrument_id, fact.date.isoformat())
        price_map.setdefault(key, set()).add(Decimal(str(fact.close)))
    prices_by_date = {}
    for (key, observed), values in price_map.items():
        prices_by_date.setdefault(observed, []).append((key, values))
    positions, episodes, current_episode, pending = {}, [], {}, {}
    cash, contributed, income, fees, realized = Decimal(profile["initial_cash"]), ZERO, ZERO, ZERO, ZERO
    cash_known, errors, warnings, used_trades = True, [], set(), []
    marks, daily, processed = {}, [], []
    if excluded:
        warnings.add(f"preopening_trades_excluded: {excluded}")
    opening_value = Decimal(profile["initial_cash"])

    def position(instrument):
        key = instrument["instrument_id"]
        if instrument.get("security_type") not in {"equity", "etf", "fund"}:
            raise ValueError("unsupported_security_type_without_contract_multiplier")
        if not key or instrument.get("currency") != currency:
            raise ValueError("unresolved_instrument_or_mixed_currency")
        if key not in positions:
            positions[key] = {"instrument": instrument, "quantity": ZERO, "cost_basis": ZERO, "action_date": opening_date}
        return key, positions[key]

    def begin(key, row, origin):
        if key not in current_episode:
            episode = {"episode_id": "le_" + fingerprint([profile["subject_id"], profile["account_id"], key, row["event_id"]]),
                "instrument_id": key, "symbol": positions[key]["instrument"]["symbol"], "opened_at": row["effective_date"],
                "closed_at": None, "origin": origin, "realized_pnl": ZERO, "invested_cost": ZERO,
                "source_refs": [], "path": []}
            episodes.append(episode)
            current_episode[key] = episode
        current_episode[key]["source_refs"].append(row["event_id"])

    def remove(key, quantity, proceeds, row, *, realize=True):
        nonlocal realized
        p = positions[key]
        if quantity > p["quantity"] or quantity <= 0:
            raise ValueError("insufficient_position")
        cost = p["cost_basis"] * quantity / p["quantity"] if p["cost_basis"] is not None else None
        gain = proceeds - cost if cost is not None and proceeds is not None else None
        if realize:
            realized = realized + gain if realized is not None and gain is not None else None
            ep = current_episode[key]
            ep["realized_pnl"] = ep["realized_pnl"] + gain if ep["realized_pnl"] is not None and gain is not None else None
        p["quantity"] -= quantity
        p["cost_basis"] = p["cost_basis"] - cost if cost is not None else None
        current_episode[key]["source_refs"].append(row["event_id"])
        if p["quantity"] == 0:
            p["cost_basis"] = ZERO
            current_episode[key]["path"].append({"date": row["effective_date"], "quantity": "0", "market_value": "0", "cost_basis": "0"})
            current_episode[key]["closed_at"] = row["effective_date"]
            del current_episode[key]
        return cost

    days = sorted({opening_date, boundary, *(d for d in all_dates if opening_date <= d <= boundary)})
    cursor = 0
    for current_day in days:
        day_gross = ZERO
        while cursor < len(rows) and rows[cursor]["effective_date"] <= current_day:
            r = rows[cursor]
            cursor += 1
            kind, identifier = r["event_type"], r["event_id"]
            try:
                if r["effective_date"] < opening_date:
                    raise ValueError("event_precedes_opening")
                if r.get("currency") != currency:
                    raise ValueError("mixed_currency_without_fx")
                key, p = position(r["instrument"]) if "instrument" in r else (None, None)
                amount = Decimal(r.get("amount", "0"))
                qty = Decimal(r.get("quantity", "0"))
                if kind == "opening_cash_adjustment":
                    if r["effective_date"] != opening_date or not r["note"].strip():
                        raise ValueError("opening_cash_correction_requires_opening_date_and_reason")
                    cash += amount
                    opening_value += amount
                elif kind in {"deposit", "withdrawal"}:
                    signed = amount if kind == "deposit" else -amount
                    cash += signed
                    contributed += signed
                elif kind in {"interest", "fee", "withholding_tax"}:
                    cash += amount if kind == "interest" else -amount
                    income += amount if kind == "interest" else -amount
                    if kind == "fee":
                        fees += amount
                elif kind == "opening_position":
                    if r["effective_date"] != opening_date or p["quantity"]:
                        raise ValueError("opening_position_requires_unique_instrument_at_opening")
                    begin(key, r, "opening_position")
                    p["quantity"], p["cost_basis"] = qty, Decimal(r["cost_basis"])
                    current_episode[key]["invested_cost"] += p["cost_basis"]
                    marks[key] = (opening_date, Decimal(r["opening_price"]))
                    opening_value += qty * Decimal(r["opening_price"])
                elif kind in {"buy", "sell"}:
                    if r["fee_currency"] and r["fee_currency"] != currency:
                        raise ValueError("mixed_fee_currency_without_fx")
                    fee = Decimal(r["fee"]) if r["fee"] is not None else None
                    gross = qty * Decimal(r["price"])
                    day_gross += gross
                    if fee is None:
                        warnings.add("unknown_fee: " + identifier)
                        cash_known = False
                    else:
                        fees += fee
                    if kind == "buy":
                        begin(key, r, "trade")
                        cost = gross + fee if fee is not None else None
                        cash -= gross + (fee or ZERO)
                        p["quantity"] += qty
                        p["cost_basis"] = p["cost_basis"] + cost if p["cost_basis"] is not None and cost is not None else None
                        ep = current_episode[key]
                        ep["invested_cost"] = ep["invested_cost"] + cost if ep["invested_cost"] is not None and cost is not None else None
                    else:
                        remove(key, qty, gross - fee if fee is not None else None, r)
                        cash += gross - (fee or ZERO)
                    used_trades.append(r.get("source_execution_id") or r["source_ref"])
                elif kind in {"split", "stock_dividend"}:
                    if p["quantity"] <= 0:
                        raise ValueError("corporate_action_requires_position")
                    p["quantity"] = p["quantity"] * Decimal(r["ratio"]) if kind == "split" else p["quantity"] + qty
                    p["action_date"] = r["effective_date"]
                    current_episode[key]["source_refs"].append(identifier)
                elif kind == "dividend_accrual":
                    pending[identifier] = {"kind": "dividend", "amount": amount, "instrument_id": key}
                    income += amount
                elif kind == "cash_dividend":
                    entitlement = pending.pop(identifier, None)
                    if entitlement is None:
                        raise ValueError("dividend_entitlement_missing")
                    tax = Decimal(r["tax"])
                    cash += amount - tax
                    income -= tax
                elif kind == "rights_subscription":
                    cash -= amount
                    pending[identifier] = {"kind": "rights", "amount": amount, "instrument_id": key}
                elif kind == "rights_delivery":
                    subscription = pending.get(r["subscription_id"])
                    if not subscription or subscription["kind"] != "rights" or subscription["instrument_id"] != key:
                        raise ValueError("rights_subscription_missing_or_wrong_instrument")
                    begin(key, r, "rights_delivery")
                    cost = subscription["amount"]
                    p["quantity"] += qty
                    p["cost_basis"] = p["cost_basis"] + cost if p["cost_basis"] is not None else None
                    ep = current_episode[key]
                    ep["invested_cost"] = ep["invested_cost"] + cost if ep["invested_cost"] is not None else None
                    p["action_date"] = r["effective_date"]
                    del pending[r["subscription_id"]]
                elif kind == "delisting":
                    remove(key, p["quantity"], amount, r)
                    cash += amount
                elif kind == "return_of_capital":
                    if p["quantity"] <= 0 or p["cost_basis"] is None:
                        raise ValueError("capital_return_requires_known_position_cost")
                    basis_reduction = min(amount, p["cost_basis"])
                    p["cost_basis"] -= basis_reduction
                    cash += amount
                    excess = amount - basis_reduction
                    realized = realized + excess if realized is not None else None
                    current_episode[key]["realized_pnl"] += excess
                elif kind == "security_exchange":
                    if p["quantity"] <= 0 or p["cost_basis"] is None:
                        raise ValueError("exchange_requires_known_position_cost")
                    cash_basis = Decimal(r["cash_cost_basis"])
                    if cash_basis > p["cost_basis"] or amount == 0 and cash_basis != 0:
                        raise ValueError("invalid_exchange_cash_cost_basis")
                    carry = p["cost_basis"] - cash_basis
                    new_key, target = position(r["new_instrument"])
                    remove(key, p["quantity"], amount + carry, r)
                    begin(new_key, r, "security_exchange")
                    target["quantity"] += qty
                    target["cost_basis"] = target["cost_basis"] + carry if target["cost_basis"] is not None else None
                    ep = current_episode[new_key]
                    ep["invested_cost"] = ep["invested_cost"] + carry if ep["invested_cost"] is not None else None
                    target["action_date"] = r["effective_date"]
                    cash += amount
                elif kind == "transfer_in":
                    begin(key, r, "transfer_in")
                    p["quantity"] += qty
                    cost = Decimal(r["cost_basis"])
                    p["cost_basis"] = p["cost_basis"] + cost if p["cost_basis"] is not None else None
                    current_episode[key]["invested_cost"] += cost
                    contributed += Decimal(r["transfer_value"])
                elif kind == "transfer_out":
                    remove(key, qty, ZERO, r, realize=False)
                    contributed -= Decimal(r["transfer_value"])
                else:
                    raise ValueError("unsupported_ledger_event")
                processed.append(identifier)
            except (ValueError, KeyError) as exc:
                errors.append({"event_id": identifier, "code": str(exc)})
                # Never publish a partially applied invalid event as a balance.
                break
        for key, values in prices_by_date.get(current_day, []):
            if len(values) == 1:
                marks[key] = (current_day, next(iter(values)))
            else:
                marks.pop(key, None)
                warnings.add("conflicting_raw_prices: " + key + ":" + current_day)
        market_value, missing, exposure_values = ZERO, [], []
        for key, p in positions.items():
            if not p["quantity"]:
                continue
            mark = marks.get(key)
            if mark is None or mark[0] < p["action_date"]:
                missing.append(key)
                continue
            value = p["quantity"] * mark[1]
            market_value += value
            exposure_values.append(value)
        receivables = sum((item["amount"] for item in pending.values()), ZERO)
        equity = cash + market_value + receivables if cash_known and not missing and not errors else None
        if cash < 0:
            warnings.add("negative_cash: " + current_day)
        daily.append({"date": current_day, "cash": money(cash) if cash_known and not errors else None,
            "market_value": money(market_value) if not missing and not errors else None,
            "receivables": money(receivables), "equity": money(equity), "net_contributions": money(contributed),
            "period_pnl": money(equity - opening_value - contributed) if equity is not None else None,
            "gross_traded": money(day_gross), "position_count": sum(p["quantity"] > 0 for p in positions.values()),
            "position_hhi": money(sum((x/market_value)**2 for x in exposure_values)) if market_value > 0 and not missing else None,
            "max_position_equity_weight": money(max(exposure_values)/equity) if equity and equity > 0 and exposure_values else None})
        for key, ep in current_episode.items():
            p, mark = positions[key], marks.get(key)
            mark_value = p["quantity"] * mark[1] if mark and mark[0] >= p["action_date"] else None
            ep["path"].append({"date": current_day, "quantity": money(p["quantity"]),
                "market_value": money(mark_value), "cost_basis": money(p["cost_basis"])})
        if errors:
            for field in ("cash","market_value","receivables","equity","net_contributions","period_pnl","gross_traded","position_count","position_hhi","max_position_equity_weight"):
                daily[-1][field] = None
            break
    output_positions = []
    for key, p in sorted(positions.items()):
        if not p["quantity"]:
            continue
        mark = marks.get(key)
        valid = mark and mark[0] >= p["action_date"]
        value = p["quantity"] * mark[1] if valid and not errors else None
        if valid and mark[0] < boundary:
            warnings.add("stale_price: " + key + ":" + mark[0])
        if not valid:
            warnings.add("missing_unadjusted_price: " + key)
        output_positions.append({**p["instrument"], "quantity": money(p["quantity"]),
            "cost_basis": money(p["cost_basis"]), "average_cost": money(p["cost_basis"] / p["quantity"]) if p["cost_basis"] is not None else None,
            "price": money(mark[1]) if valid else None, "price_date": mark[0] if valid else None,
            "market_value": money(value), "unrealized_pnl": money(value - p["cost_basis"]) if value is not None and p["cost_basis"] is not None else None})
    for ep in episodes:
        ep["status"] = "closed" if ep["closed_at"] else "open"
        ep["realized_pnl"] = money(ep["realized_pnl"])
        ep["invested_cost"] = money(ep["invested_cost"])
    last = daily[-1]
    pnl = Decimal(last["equity"]) - opening_value - contributed if last["equity"] is not None else None
    return {"schema_version": "account_ledger.v1", "subject_id": profile["subject_id"], "account_id": profile["account_id"],
        "as_of": boundary, "currency": currency, "opening_date": opening_date,
        "status": "invalid" if errors else "needs_attention" if warnings or last["equity"] is None else "available",
        "cash": last["cash"], "market_value": last["market_value"], "receivables": last["receivables"], "equity": last["equity"],
        "opening_equity": money(opening_value) if not errors else None, "net_contributions": money(contributed) if not errors else None, "period_pnl": money(pnl),
        "realized_trading_pnl": money(realized) if not errors else None, "net_income": money(income) if not errors else None,
        "fees": money(fees) if cash_known and not errors else None, "positions": output_positions if not errors else [], "episodes": episodes if not errors else [],
        "pending_assets": [{"event_id": key, **value, "amount": money(value["amount"])} for key, value in sorted(pending.items())] if not errors else [],
        "daily": daily, "execution_refs": used_trades, "errors": errors, "warnings": sorted(warnings),
        "time_weighted_return": None, "return_limitation": "缺少每次外部资金流前后的独立估值，不计算精确时间加权收益率；期间盈亏已扣除出入金和证券转入转出。",
        "definitions": ["单币种、无融资、只做多；成本使用含已知交易费用的移动平均法。",
            "期初持仓不产生买入或消耗现金；期初市值用于期间盈亏，历史账面成本另行保留。",
            "公司行动在当日成交前处理，现金流水在当日成交后处理；同类事件按显式sequence排序。",
            "分红在除息日确认应收，实付日转现金并扣实际税额；配股缴款先记待到账资产，到账再结转成本。",
            "仅用未复权价格估值，最后已知价格标出日期；缺价或未知费用不补零、不发布精确账户总值。",
            "持仓/交易盈亏包含期初账面成本；期间账户盈亏以期初市值为起点，两种口径分别展示。"]}
