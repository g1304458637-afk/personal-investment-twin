"""Execution reality model: fees, slippage, price limits, affordability.

All models are declared simplifications (see docs/STRATEGY_SIMULATION_V1.md §5)
and every value is a versioned spec parameter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    slippage_rate: float
    price_limit_pct: float
    lot_size: int

    def _commission(self, amount: float) -> tuple[float, bool]:
        raw = amount * self.commission_rate
        if raw <= self.min_commission:
            return self.min_commission, True
        return raw, False

    def buy_fee(self, amount: float) -> tuple[float, dict[str, float | bool]]:
        commission, min_applied = self._commission(amount)
        return commission, {"commission": commission, "min_commission_applied": min_applied,
                            "stamp_duty": 0.0}

    def sell_fee(self, amount: float) -> tuple[float, dict[str, float | bool]]:
        commission, min_applied = self._commission(amount)
        stamp_duty = amount * self.stamp_duty_rate
        return commission + stamp_duty, {"commission": commission, "min_commission_applied": min_applied,
                                         "stamp_duty": stamp_duty}

    def buy_fill_price(self, raw_price: float) -> float:
        return raw_price * (1.0 + self.slippage_rate)

    def sell_fill_price(self, raw_price: float) -> float:
        return raw_price * (1.0 - self.slippage_rate)

    def limit_up_price(self, prior_close: float) -> float:
        """Exchange-style limit price: prior close × (1+limit), rounded half-up to 0.01."""
        return math.floor(prior_close * (1.0 + self.price_limit_pct) * 100.0 + 0.5) / 100.0

    def buy_cost(self, quantity: float, fill_price: float) -> float:
        """Total cash needed for a buy, including its fee."""
        amount = quantity * fill_price
        fee, _ = self.buy_fee(amount)
        return amount + fee

    def affordable_quantity(self, cash: float, fill_price: float) -> float:
        """Largest lot-multiple quantity whose total buy cost fits in cash."""
        if fill_price <= 0 or cash <= 0:
            return 0.0
        lots = int(cash / (fill_price * self.lot_size))
        while lots > 0 and self.buy_cost(lots * self.lot_size, fill_price) > cash:
            lots -= 1
        return float(lots * self.lot_size)
