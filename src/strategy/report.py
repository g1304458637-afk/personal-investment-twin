"""JSON-safe serialization of simulation results (schema strategy_simulation.v1)."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from src.strategy.engine import SimulationResult

SCHEMA_VERSION = "strategy_simulation.v1"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def result_to_dict(result: SimulationResult) -> dict[str, object]:
    """Full journal: every day keeps candidates, signals, events, ledger and equity."""
    return _safe({
        "schema_version": SCHEMA_VERSION,
        "strategy": result.spec.as_dict(),
        "data_fingerprint": result.data_fingerprint,
        "summary": dict(result.summary),
        "days": [
            {
                "date": day.day,
                "universe_count": day.universe_count,
                "candidates": day.candidates,
                "signals": day.signals,
                "events": day.events,
                "orders_created": day.orders_created,
                "cash": day.cash,
                "holdings": day.holdings,
                "equity": day.equity,
                "invested_fraction": day.invested_fraction,
                "drawdown_from_peak": day.drawdown_from_peak,
            }
            for day in result.days
        ],
        "orders": [
            {
                "order_id": order.order_id, "signal_date": order.signal_date,
                "instrument": order.instrument, "side": order.side,
                "intended_quantity": order.intended_quantity, "reason_code": order.reason_code,
                "reason_text": order.reason_text, "rank": order.rank, "status": order.status,
                "resolution_date": order.resolution_date,
                "resolution_reason": order.resolution_reason,
            }
            for order in result.orders
        ],
        "fills": [
            {
                "fill_id": fill.fill_id, "order_id": fill.order_id, "trigger": fill.trigger,
                "instrument": fill.instrument, "side": fill.side, "quantity": fill.quantity,
                "price": fill.price, "fee": fill.fee, "fee_detail": fill.fee_detail,
                "day": fill.day, "note": fill.note,
            }
            for fill in result.fills
        ],
    })
