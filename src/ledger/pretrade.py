"""Deterministic hypothetical order check and owned, already-closed history."""
from decimal import Decimal
from datetime import date

from src.core.canonical_execution import canonical_execution, execution_time, fee_fact, instrument_ref
from src.market_data.models import HistoricalPriceFact
from .contracts import day, fingerprint, money, number, security
from .engine import project


def check(profile, events, executions, prices, raw, as_of):
    instrument = security({**raw, "currency": profile["currency"]})
    side = raw.get("side")
    if side not in {"BUY", "SELL"}:
        raise ValueError("proposed side must be BUY or SELL")
    quantity, price, fee = (number(raw.get(key), key, positive=key != "fee", nonnegative=True) for key in ("quantity", "price", "fee"))
    boundary = day(as_of, "as_of")
    ref = instrument_ref(local_symbol=instrument["symbol"], market=instrument["market"], security_type=instrument["security_type"], currency=profile["currency"])
    basis_prices = [p for p in prices if not (p.instrument.instrument_id == ref.instrument_id and p.date.isoformat() == boundary)]
    basis_prices.append(HistoricalPriceFact(observation_id="hypothetical-price", instrument=ref, date=date.fromisoformat(boundary),
        close=float(price), price_type="unadjusted_close", currency=profile["currency"], source_id="user_hypothetical_price",
        source_tier="user_provided", source_version="1", imported_at=boundary, source_file_sha256="not-persisted",
        source_row_identity="hypothetical"))
    before = project(profile, events, executions, basis_prices, as_of=boundary)
    reasons = []
    if before["cash"] is None or before["equity"] is None or before["errors"]:
        reasons.append("账户估值或费用不完整，无法完成资金检查。")
    if side == "BUY" and before["cash"] is not None and Decimal(before["cash"]) < quantity*price+fee:
        reasons.append("现金不足，不能按这组假设完成买入。")
    holding = next((p for p in before["positions"] if p["instrument_id"] == ref.instrument_id), None)
    if side == "SELL" and (holding is None or Decimal(holding["quantity"]) < quantity):
        reasons.append("可观察持仓数量不足；不支持卖空。")
    after = None
    if not reasons:
        hypothetical = canonical_execution(subject_id=profile["subject_id"], account_id=profile["account_id"],
            instrument=ref, event_time=execution_time(boundary, precision="date", source_timezone="Asia/Shanghai"),
            side=side, executed_quantity=float(quantity), executed_price=float(price), fee=fee_fact(float(fee), currency=profile["currency"]),
            source="hypothetical", source_record_ref="hypothetical", execution_id="hypothetical:"+fingerprint(raw),
            execution_sequence=1_000_000, sequence_source="hypothetical_after_existing_trades")
        after = project(profile, events, (*executions, hypothetical), basis_prices, as_of=boundary)
        if after["errors"]:
            reasons.append("仿真账本未通过一致性检查。")
            after = None
    history = [ep for ep in before["episodes"] if ep["instrument_id"] == ref.instrument_id and ep["closed_at"] and ep["closed_at"] <= boundary]
    history.sort(key=lambda ep: (ep["closed_at"], ep["episode_id"]), reverse=True)
    return {"schema_version": "ledger_pretrade.v1", "subject_id": profile["subject_id"], "account_id": profile["account_id"],
        "as_of": boundary, "status": "blocked" if reasons else "simulated", "reasons": reasons,
        "assumptions": {"instrument": instrument, "side": side, "quantity": money(quantity), "price": money(price), "fee": money(fee)},
        "before": before, "after": after, "similar_history": history[:10],
        "limitations": ["此价格及费用由用户明确假设，不是实时行情；检查不会提交订单或改写账户。",
            "资金和持仓只反映已记账记录，不确认券商冻结资金、T+1可卖数量、停牌、涨跌停或实际成交可能性。",
            "历史参照仅按同一标的、截止日之前已结束的投资经历筛选并按结束日期排序，不是预测模型或收益推荐。",
            "模拟前后使用同一假设价格；结果不代表真实账户已经发生变化。"]}
