"""The strategy's own account state: cash, positions, T+1 availability.

This ledger is entirely independent of the user's replayed account; nothing
here reads or writes recorded executions.  Every mutation goes through
explicit apply methods so tests can reconcile cash and holdings fill by fill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class Position:
    instrument: str
    quantity: float
    available_quantity: float  # T+1: shares bought today are not sellable today.
    average_cost: float        # Per-share cost including buy fees.
    entry_price: float         # Raw fill price of the opening buy.
    entry_date: date
    entry_count: int = 1
    stop_price: float | None = None  # None = the strategy declares no price stop.


@dataclass(slots=True)
class StrategyAccount:
    initial_cash: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    @classmethod
    def opening(cls, initial_cash: float) -> "StrategyAccount":
        return cls(initial_cash=initial_cash, cash=initial_cash)

    def apply_buy(self, instrument: str, quantity: float, price: float, fee: float, *, day: date,
                  stop_price: float | None) -> None:
        amount = quantity * price
        self.cash -= amount + fee
        existing = self.positions.get(instrument)
        if existing is None:
            self.positions[instrument] = Position(
                instrument=instrument, quantity=quantity, available_quantity=0.0,
                average_cost=(amount + fee) / quantity, entry_price=price,
                entry_date=day, stop_price=stop_price)
            return
        total_quantity = existing.quantity + quantity
        total_cost = existing.average_cost * existing.quantity + amount + fee
        existing.quantity = total_quantity
        existing.average_cost = total_cost / total_quantity
        # Adds refresh the stop from the newest fill when the strategy uses one.
        existing.stop_price = stop_price

    def apply_sell(self, instrument: str, quantity: float, price: float, fee: float) -> None:
        position = self.positions.get(instrument)
        if position is None or quantity <= 0 or quantity > position.quantity + 1e-9:
            raise ValueError(f"sell without sufficient position: {instrument}")
        if quantity > position.available_quantity + 1e-9:
            raise ValueError(f"sell exceeds T+1 available quantity: {instrument}")
        self.cash += quantity * price - fee
        position.quantity -= quantity
        position.available_quantity -= quantity
        if position.quantity <= 1e-9:
            del self.positions[instrument]

    def apply_split(self, instrument: str, ratio: float) -> None:
        """Split adjustment at ex-date open: quantity ×ratio, per-share cost ÷ratio."""
        position = self.positions.get(instrument)
        if position is None or ratio <= 0:
            return
        position.quantity *= ratio
        position.available_quantity *= ratio
        position.average_cost /= ratio
        position.entry_price /= ratio
        if position.stop_price is not None:
            position.stop_price /= ratio

    def settle_day(self) -> None:
        """End of day: shares bought today become sellable tomorrow."""
        for position in self.positions.values():
            position.available_quantity = position.quantity

    def market_value(self, marks: dict[str, float]) -> float:
        return sum(
            position.quantity * marks[position.instrument]
            for position in self.positions.values()
            if position.instrument in marks
        )

    def equity(self, marks: dict[str, float]) -> float:
        return self.cash + self.market_value(marks)
