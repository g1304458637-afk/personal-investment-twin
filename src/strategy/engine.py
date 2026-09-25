"""The deterministic daily simulation loop.

Declared execution model (docs/STRATEGY_SIMULATION_V1.md §5), per trading day:

  0. corporate actions at the open (split adjusts positions; pending orders reset)
  1. delisting liquidation at the open (last available raw close)
  2. pending signal SELL orders fill at the open (GFD: cancel if suspended)
  3. stop-loss checks on remaining positions (gap → open price, else stop price;
     runs before buys, so a stop can fire at the earliest on the day after entry,
     which structurally satisfies T+1)
  4. pending signal BUY orders fill at the open in rank order (limit-up reject,
     lot-cash affordability scaling or reject)
  5. T+1 settlement (shares bought today become available)
  6. mark-to-market at the close, equity and drawdown
  7. close signals → new orders for tomorrow (skipped on the final day)

Nothing in this loop reads user account facts, and every value is produced by
sorted, deterministic iteration (no RNG, no wall clock, no dict-order luck).
"""
from __future__ import annotations

from datetime import date

from src.strategy.account import StrategyAccount
from src.strategy.data import SimulationData
from src.strategy.execution import ExecutionModel
from src.strategy.records import (
    DayRecord,
    FillRecord,
    OrderRecord,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    TRIGGER_DELISTING_LIQUIDATION,
    TRIGGER_SIGNAL_ORDER,
    TRIGGER_STOP_LOSS,
)
from src.strategy.spec import StrategySpec
from src.strategy.strategies.registry import resolve_signals
from src.strategy.strategies.t1 import evaluate_close_signals as _t1_signals  # noqa: F401 (default provider)


class SimulationResult:
    __slots__ = ("spec", "data_fingerprint", "days", "orders", "fills", "summary")

    def __init__(self, spec: StrategySpec, data_fingerprint: str,
                 days: list[DayRecord], orders: list[OrderRecord], fills: list[FillRecord],
                 summary: dict[str, object]):
        self.spec = spec
        self.data_fingerprint = data_fingerprint
        self.days = days
        self.orders = orders
        self.fills = fills
        self.summary = summary


def _marks_for(account: StrategyAccount, data: SimulationData, day: date) -> dict[str, float]:
    marks: dict[str, float] = {}
    for instrument in account.positions:
        mark = data.series[instrument].raw_close_on_or_before(day)
        if mark is None:
            raise ValueError(f"position {instrument} has no valuation close on or before {day}")
        marks[instrument] = mark
    return marks


def run_simulation(spec: StrategySpec, data: SimulationData,
                   signal_provider=None) -> SimulationResult:
    """Run one strategy spec over the dataset.

    ``signal_provider`` defaults to the registered close-signal provider for
    the spec's strategy_id; strategies with no registered provider fall back
    to T1's breakout-trend signals.
    """
    if signal_provider is None:
        signal_provider = resolve_signals(spec.strategy_id, _t1_signals)
    params = spec.params
    execution = ExecutionModel(
        commission_rate=float(params["commission_rate"]),
        min_commission=float(params["min_commission"]),
        stamp_duty_rate=float(params["stamp_duty_rate"]),
        slippage_rate=float(params["slippage_rate"]),
        price_limit_pct=float(params["price_limit_pct"]),
        lot_size=int(params["lot_size"]),
    )
    initial_cash = float(params["initial_cash"])
    max_positions = int(params["max_positions"])
    position_fraction = float(params["position_fraction"])
    stop_loss_pct = float(params["stop_loss_pct"])

    account = StrategyAccount.opening(initial_cash)
    orders: list[OrderRecord] = []
    fills: list[FillRecord] = []
    days: list[DayRecord] = []
    order_seq = 0
    fill_seq = 0
    peak_equity = initial_cash
    round_trips: list[dict[str, object]] = []
    # Per-instrument risk at the opening fill, frozen for the whole trade:
    # {"entry_price", "initial_stop"} (both in raw price terms).  Used for the
    # R-multiple of the round trip that eventually closes the position.
    open_risk: dict[str, dict[str, float | None]] = {}

    def next_order_id() -> str:
        nonlocal order_seq
        order_seq += 1
        return f"ORD-{order_seq:06d}"

    def next_fill_id() -> str:
        nonlocal fill_seq
        fill_seq += 1
        return f"FIL-{fill_seq:06d}"

    def create_order(day: date, instrument: str, side: str, intended_quantity: float,
                     reason_code: str, reason_text: str, rank: int | None) -> OrderRecord:
        order = OrderRecord(order_id=next_order_id(), signal_date=day, instrument=instrument,
                            side=side, intended_quantity=intended_quantity,
                            reason_code=reason_code, reason_text=reason_text, rank=rank)
        orders.append(order)
        return order

    def record_fill(day: date, order: OrderRecord | None, trigger: str, instrument: str,
                    side: str, quantity: float, price: float, fee: float,
                    fee_detail: dict[str, float | bool], note: str | None) -> FillRecord:
        fill = FillRecord(fill_id=next_fill_id(), order_id=order.order_id if order else None,
                          trigger=trigger, instrument=instrument, side=side, quantity=quantity,
                          price=price, fee=fee, fee_detail=fee_detail, day=day, note=note)
        fills.append(fill)
        return fill

    def cancel(order: OrderRecord, day: date, reason: str) -> dict[str, object]:
        order.status = ORDER_STATUS_CANCELLED
        order.resolution_date = day
        order.resolution_reason = reason
        return {"kind": "order_cancelled", "order_id": order.order_id,
                "instrument": order.instrument, "side": order.side, "reason": reason}

    def close_round_trip(instrument: str, day: date, pnl: float, reason: str) -> None:
        """Record one closed round trip plus its R-multiple.

        R = pnl ÷ initial_risk, initial_risk = |opening entry price − opening
        stop price| × opening quantity: the position-level cash actually at
        risk when the trade opened.  A trade opened without a stop (or with a
        zero stop) has no defined risk unit: its R stays null and it counts as
        skipped.
        """
        risk = open_risk.pop(instrument, None)
        r_multiple: float | None = None
        if risk is not None:
            initial_stop = risk["initial_stop"]
            if initial_stop is not None and float(initial_stop) > 0:
                per_share_risk = abs(float(risk["entry_price"]) - float(initial_stop))
                initial_risk = per_share_risk * float(risk["quantity"])
                if initial_risk > 0:
                    r_multiple = pnl / initial_risk
        round_trips.append({"instrument": instrument, "closed_on": day.isoformat(),
                            "pnl": pnl, "reason": reason, "r_multiple": r_multiple})

    def reject(order: OrderRecord, day: date, reason: str, detail: dict[str, object] | None = None) -> dict[str, object]:
        order.status = ORDER_STATUS_REJECTED
        order.resolution_date = day
        order.resolution_reason = reason
        event = {"kind": "order_rejected", "order_id": order.order_id,
                 "instrument": order.instrument, "side": order.side, "reason": reason}
        if detail:
            event.update(detail)
        return event

    actions_by_day: dict[date, list] = {}
    for action in data.actions:
        actions_by_day.setdefault(action.ex_date, []).append(action)

    pending: list[OrderRecord] = []
    last_day = data.dates[-1]

    for day in data.dates:
        day_record = DayRecord(day=day, universe_count=len(data.listed_on(day)))
        events = day_record.events

        # 0. Corporate actions at the open.
        for action in actions_by_day.get(day, []):
            if action.instrument in account.positions:
                account.apply_split(action.instrument, action.ratio)
                # Keep the frozen opening risk in the same (post-split) price
                # terms as the position, so the R-multiple stays comparable.
                risk = open_risk.get(action.instrument)
                if risk is not None:
                    risk["entry_price"] = float(risk["entry_price"]) / action.ratio
                    risk["quantity"] = float(risk["quantity"]) * action.ratio
                    if risk["initial_stop"] is not None:
                        risk["initial_stop"] = float(risk["initial_stop"]) / action.ratio
                events.append({"kind": "split_applied", "instrument": action.instrument,
                               "ratio": action.ratio})
            for order in [item for item in pending if item.instrument == action.instrument]:
                pending.remove(order)
                events.append(cancel(order, day, "corporate_action_reset"))

        # 1. Delisting day: cancel every pending order of delisted instruments,
        # then force-liquidate any held position at the last available close.
        for instrument, member in sorted(data.members.items()):
            if member.delist_date != day:
                continue
            for order in [item for item in pending if item.instrument == instrument]:
                pending.remove(order)
                events.append(cancel(order, day, "delisted"))
            if instrument not in account.positions:
                continue
            position = account.positions[instrument]
            price = data.series[instrument].raw_close_on_or_before(day)
            if price is None:  # No bar at all: impossible by dataset contract, fail loudly.
                raise ValueError(f"delisted {instrument} has no historical close")
            amount = position.available_quantity * price
            fee, fee_detail = execution.sell_fee(amount)
            fill = record_fill(day, None, TRIGGER_DELISTING_LIQUIDATION, instrument, "SELL",
                               position.available_quantity, price, fee, fee_detail,
                               note="delisting_forced_liquidation")
            cost_basis = position.average_cost * position.available_quantity
            close_round_trip(instrument, day, amount - fee - cost_basis,
                             "delisting_forced_liquidation")
            account.apply_sell(instrument, position.available_quantity, price, fee)
            events.append({"kind": "fill", "fill_id": fill.fill_id, "order_id": None,
                           "trigger": fill.trigger, "instrument": instrument, "side": "SELL",
                           "quantity": fill.quantity, "price": fill.price, "fee": fill.fee})

        # 2. Pending signal SELL orders at the open.
        for order in sorted((item for item in pending if item.side == "SELL"),
                            key=lambda item: item.instrument):
            pending.remove(order)
            bar = data.series[order.instrument].bar_on(day)
            if bar is None:
                events.append(cancel(order, day, "suspended_expired"))
                continue
            position = account.positions.get(order.instrument)
            if position is None:
                # A duplicate or stale exit (provider bug, or two exit signals
                # racing in one day) must cancel cleanly, never KeyError out of
                # the whole simulation.
                events.append(cancel(order, day, "position_already_closed"))
                continue
            price = execution.sell_fill_price(bar.open)
            quantity = position.available_quantity
            amount = quantity * price
            fee, fee_detail = execution.sell_fee(amount)
            fill = record_fill(day, order, TRIGGER_SIGNAL_ORDER, order.instrument, "SELL",
                               quantity, price, fee, fee_detail, note=None)
            order.status = ORDER_STATUS_FILLED
            order.resolution_date = day
            cost_basis = position.average_cost * quantity
            close_round_trip(order.instrument, day, amount - fee - cost_basis,
                             order.reason_code)
            account.apply_sell(order.instrument, quantity, price, fee)
            order.resolution_reason = fill.fill_id
            events.append({"kind": "fill", "fill_id": fill.fill_id, "order_id": order.order_id,
                           "trigger": fill.trigger, "instrument": order.instrument, "side": "SELL",
                           "quantity": fill.quantity, "price": fill.price, "fee": fill.fee})

        # 3. Stop-loss checks on remaining positions.  Runs before buys, so a
        # position is always at least one day old here: T+1 is structural.
        for instrument in sorted(account.positions):
            position = account.positions[instrument]
            if position.available_quantity != position.quantity:
                raise ValueError(f"stop check requires settled availability: {instrument}")
            bar = data.series[instrument].bar_on(day)
            if bar is None:
                events.append({"kind": "stop_deferred", "instrument": instrument,
                               "reason": "no_session"})
                continue
            if position.stop_price is None:
                continue  # Strategy declares no price stop; exit rules only.
            if bar.open <= position.stop_price:
                price = execution.sell_fill_price(bar.open)
                note = "stop_gap_open_below_stop"
            elif bar.low <= position.stop_price:
                price = execution.sell_fill_price(position.stop_price)
                note = "stop_intraday"
            else:
                continue
            quantity = position.available_quantity
            amount = quantity * price
            fee, fee_detail = execution.sell_fee(amount)
            fill = record_fill(day, None, TRIGGER_STOP_LOSS, instrument, "SELL", quantity,
                               price, fee, fee_detail, note=note)
            cost_basis = position.average_cost * quantity
            close_round_trip(instrument, day, amount - fee - cost_basis, "stop_loss")
            account.apply_sell(instrument, quantity, price, fee)
            events.append({"kind": "fill", "fill_id": fill.fill_id, "order_id": None,
                           "trigger": fill.trigger, "instrument": instrument, "side": "SELL",
                           "quantity": fill.quantity, "price": fill.price, "fee": fill.fee,
                           "note": note})

        # 4. Pending signal BUY orders at the open, in rank order.
        for order in sorted((item for item in pending if item.side == "BUY"),
                            key=lambda item: (item.rank if item.rank is not None else 1 << 30,
                                              item.instrument)):
            pending.remove(order)
            series = data.series[order.instrument]
            bar = series.bar_on(day)
            if bar is None:
                events.append(cancel(order, day, "suspended_expired"))
                continue
            index = series.index_on_or_before(day)
            assert index is not None and index > 0, "entry requires prior closes"
            prior_close = series.bars[index - 1].close
            if bar.open >= execution.limit_up_price(prior_close):
                events.append(reject(order, day, "limit_up_open", {
                    "open": bar.open, "limit_up_price": execution.limit_up_price(prior_close)}))
                continue
            price = execution.buy_fill_price(bar.open)
            affordable = execution.affordable_quantity(account.cash, price)
            quantity = min(order.intended_quantity, affordable)
            if quantity < execution.lot_size:
                events.append(reject(order, day, "insufficient_cash", {
                    "intended_quantity": order.intended_quantity,
                    "affordable_quantity": affordable, "cash": account.cash}))
                continue
            amount = quantity * price
            fee, fee_detail = execution.buy_fee(amount)
            fill = record_fill(day, order, TRIGGER_SIGNAL_ORDER, order.instrument, "BUY",
                               quantity, price, fee, fee_detail,
                               note=None if quantity == order.intended_quantity else "quantity_scaled_by_cash")
            order.status = ORDER_STATUS_FILLED
            order.resolution_date = day
            order.resolution_reason = fill.fill_id
            existing = account.positions.get(order.instrument)
            # Fixed-stop strategies re-arm the stop from every fill; strategies
            # without a fixed stop pass None so an add-on never wipes the
            # trailing stop a provider already ratcheted onto the position.
            fill_stop = price * (1.0 - stop_loss_pct) if stop_loss_pct > 0 else None
            account.apply_buy(order.instrument, quantity, price, fee, day=day,
                              stop_price=fill_stop)
            if existing is not None:
                existing.entry_count += 1
                existing.entry_price = price  # last entry price (adds refresh it)
            else:
                open_risk[order.instrument] = {"entry_price": price,
                                               "initial_stop": fill_stop,
                                               "quantity": quantity}
            events.append({"kind": "fill", "fill_id": fill.fill_id, "order_id": order.order_id,
                           "trigger": fill.trigger, "instrument": order.instrument, "side": "BUY",
                           "quantity": fill.quantity, "price": fill.price, "fee": fill.fee,
                           **({"note": fill.note} if fill.note else {})})

        # 5. T+1 settlement.
        account.settle_day()

        # 6. Mark-to-market, equity, drawdown.
        marks = _marks_for(account, data, day)
        equity = account.equity(marks)
        peak_equity = max(peak_equity, equity)
        market_value = equity - account.cash
        day_record.cash = account.cash
        day_record.equity = equity
        day_record.invested_fraction = 0.0 if equity <= 0 else market_value / equity
        day_record.drawdown_from_peak = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
        day_record.holdings = [
            {"instrument": instrument, "quantity": position.quantity,
             "available_quantity": position.available_quantity,
             "average_cost": position.average_cost, "mark_price": marks[instrument],
             "market_value": position.quantity * marks[instrument],
             "stop_price": position.stop_price}
            for instrument, position in sorted(account.positions.items())
        ]

        # 7. Close signals → orders for the next open.
        if day != last_day:
            held = set(account.positions)
            pending_buys = {item.instrument for item in pending if item.side == "BUY"}
            position_view = {
                instrument: {"quantity": position.quantity,
                             "available_quantity": position.available_quantity,
                             "last_entry_price": position.entry_price,
                             "entry_count": position.entry_count,
                             "stop_price": position.stop_price}
                for instrument, position in account.positions.items()
            }
            exits, candidates = signal_provider(params, data, day, held, pending_buys,
                                                account_view={"equity": equity, "cash": account.cash,
                                                              "positions": position_view})
            adds = [item for item in candidates if item.kind == "add_candidate"]
            entries = [item for item in candidates if item.kind == "entry_candidate"]
            stop_updates = [item for item in candidates if item.kind == "stop_update"]
            for update in stop_updates:
                # Contract: a stop_update condition dict carries the new stop
                # price in "actual"; "threshold" is only the comparison operand
                # and may be unrelated (e.g. 0.0 for a ratchet check).
                conditions = update.conditions[0] if update.conditions else {}
                new_stop = conditions.get("actual", conditions.get("threshold"))
                if new_stop is not None and update.instrument in account.positions:
                    account.positions[update.instrument].stop_price = float(new_stop)
                    events.append({"kind": "stop_updated", "instrument": update.instrument,
                                   "day": day.isoformat(), "reason_code": update.reason_code,
                                   "stop_price": float(new_stop)})
            for signal in exits:
                if signal.instrument not in account.positions:
                    # Exit for a position already fully sold today: nothing to
                    # exit, skip instead of crashing on the missing key.
                    continue
                order = create_order(day, signal.instrument, "SELL",
                                     account.positions[signal.instrument].quantity,
                                     getattr(signal, "reason_code", "signal_exit"),
                                     signal.reason_text, None)
                pending.append(order)
                day_record.orders_created.append(order.order_id)
                day_record.signals.append({"instrument": signal.instrument, "kind": "exit",
                                           "reason": signal.reason_text,
                                           "conditions": [dict(item) for item in signal.conditions]})
            add_rank_base = 0
            for signal in adds:
                if signal.instrument in pending_buys:
                    continue
                close_raw = data.series[signal.instrument].raw_close_on_or_before(day)
                assert close_raw is not None
                intended = getattr(signal, "intended_quantity", None)
                if intended is None:
                    intended_notional = min(equity * position_fraction, account.cash)
                    intended = float(int(intended_notional / close_raw / execution.lot_size) * execution.lot_size)
                if intended < execution.lot_size:
                    continue
                add_rank_base += 1
                order = create_order(day, signal.instrument, "BUY", float(intended),
                                     getattr(signal, "reason_code", "strategy_add"), signal.reason_text,
                                     add_rank_base)
                pending.append(order)
                day_record.orders_created.append(order.order_id)
                day_record.signals.append({"instrument": signal.instrument, "kind": "add",
                                           "reason": signal.reason_text, "rank": add_rank_base})
            slots = max_positions - len(account.positions) - len(pending_buys)
            for rank, signal in enumerate(entries[: slots] if slots > 0 else [], start=1):
                close_raw = data.series[signal.instrument].raw_close_on_or_before(day)
                assert close_raw is not None
                intended = getattr(signal, "intended_quantity", None)
                if intended is None:
                    intended_notional = min(equity * position_fraction, account.cash)
                    intended = float(int(intended_notional / close_raw / execution.lot_size) * execution.lot_size)
                if intended < execution.lot_size:
                    day_record.signals.append({
                        "instrument": signal.instrument, "kind": "entry_skipped",
                        "reason": "lot_size_unaffordable",
                        "detail": {"intended_notional": equity * position_fraction, "close": close_raw}})
                    continue
                order = create_order(day, signal.instrument, "BUY", float(intended),
                                     getattr(signal, "reason_code", "strategy_entry"),
                                     signal.reason_text, rank)
                pending.append(order)
                day_record.orders_created.append(order.order_id)
                day_record.signals.append({"instrument": signal.instrument, "kind": "entry",
                                           "reason": signal.reason_text, "rank": rank,
                                           "strength": signal.strength})
            day_record.candidates = [
                {"instrument": item.instrument, "strength": item.strength,
                 "selected": index < slots and slots > 0}
                for index, item in enumerate(entries)
            ]

        days.append(day_record)

    if any(order.status == ORDER_STATUS_PENDING for order in orders):
        raise ValueError("simulation ended with pending orders")

    summary = _build_summary(spec, initial_cash, days, orders, fills, round_trips)
    return SimulationResult(spec=spec, data_fingerprint=data.fingerprint, days=days,
                            orders=orders, fills=fills, summary=summary)


def _build_summary(spec: StrategySpec, initial_cash: float, days: list[DayRecord],
                   orders: list[OrderRecord], fills: list[FillRecord],
                   round_trips: list[dict[str, object]]) -> dict[str, object]:
    if not days:
        raise ValueError("simulation produced no days")
    final_day = days[-1]
    trough_index = min(range(len(days)), key=lambda index: days[index].drawdown_from_peak)
    # Peak of the max drawdown: highest equity strictly before the trough (the
    # running peak that drawdown_from_peak at the trough is measured against),
    # not the all-time equity high, which can sit after the trough.
    peak_index = max(range(trough_index + 1), key=lambda index: days[index].equity)
    wins = sum(1 for item in round_trips if float(item["pnl"]) > 0)
    r_values = [float(item["r_multiple"]) for item in round_trips if item.get("r_multiple") is not None]
    r_sorted = sorted(r_values)
    if r_sorted:
        mid = len(r_sorted) // 2
        r_median = r_sorted[mid] if len(r_sorted) % 2 else (r_sorted[mid - 1] + r_sorted[mid]) / 2.0
    else:
        r_median = None
    total_fees = sum(fill.fee for fill in fills)
    return {
        "initial_cash": initial_cash,
        "final_equity": final_day.equity,
        "total_return": final_day.equity / initial_cash - 1.0 if initial_cash > 0 else None,
        "max_drawdown": min((day.drawdown_from_peak for day in days), default=0.0),
        "max_drawdown_peak_date": days[peak_index].day.isoformat(),
        "max_drawdown_trough_date": days[trough_index].day.isoformat(),
        "trading_days": len(days),
        "order_count": len(orders),
        "fill_count": len(fills),
        "rejected_order_count": sum(1 for item in orders if item.status == ORDER_STATUS_REJECTED),
        "cancelled_order_count": sum(1 for item in orders if item.status == ORDER_STATUS_CANCELLED),
        "total_fees": total_fees,
        "round_trip_count": len(round_trips),
        "win_rate": (wins / len(round_trips)) if round_trips else None,
        "r_multiple_stats": {
            "count": len(r_values),
            "avg_r": (sum(r_values) / len(r_values)) if r_values else None,
            "median_r": r_median if r_values else None,
            "max_r": max(r_values) if r_values else None,
            "min_r": min(r_values) if r_values else None,
            "skipped_no_stop": sum(1 for item in round_trips if item.get("r_multiple") is None),
            "definition": "R = 单轮回合盈亏 ÷（|建仓成交价 − 建仓止损价| × 建仓数量），"
                          "即建仓时该笔仓位承担的风险金额；无正止损开仓的回合没有确定风险单位，"
                          "计入 skipped_no_stop 且 r_multiple 为 null。",
        },
        "average_invested_fraction": sum(day.invested_fraction for day in days) / len(days),
        "round_trips": round_trips,
    }
