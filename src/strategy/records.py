"""Journal record types: signals, orders, fills, and daily accounting.

Signal → order → fill are deliberately separate records.  An order that never
fills keeps its pending/cancelled/rejected status and reason so "why nothing
happened" is always answerable from the journal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_FILLED = "filled"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REJECTED = "rejected"

TRIGGER_SIGNAL_ORDER = "signal_order"
TRIGGER_STOP_LOSS = "stop_loss"
TRIGGER_DELISTING_LIQUIDATION = "delisting_liquidation"


@dataclass(slots=True)
class OrderRecord:
    order_id: str
    signal_date: date
    instrument: str
    side: str  # BUY | SELL
    intended_quantity: float
    reason_code: str
    reason_text: str
    rank: int | None  # Priority among same-morning buys (1 = first).
    status: str = ORDER_STATUS_PENDING
    resolution_date: date | None = None
    resolution_reason: str | None = None


@dataclass(slots=True)
class FillRecord:
    fill_id: str
    order_id: str | None
    trigger: str
    instrument: str
    side: str
    quantity: float
    price: float
    fee: float
    fee_detail: dict[str, float | bool]
    day: date
    note: str | None = None


@dataclass(slots=True)
class DayRecord:
    day: date
    universe_count: int
    candidates: list[dict[str, object]] = field(default_factory=list)
    signals: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    orders_created: list[str] = field(default_factory=list)
    cash: float = 0.0
    holdings: list[dict[str, object]] = field(default_factory=list)
    equity: float = 0.0
    invested_fraction: float = 0.0
    drawdown_from_peak: float = 0.0
