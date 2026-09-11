"""Account ledger tests: golden cash/position/fee reconciliation, T+1, splits."""
from __future__ import annotations

from datetime import date

from src.strategy.account import StrategyAccount
from src.strategy.execution import ExecutionModel

EXECUTION = ExecutionModel(commission_rate=0.0003, min_commission=5.0, stamp_duty_rate=0.001,
                           slippage_rate=0.0, price_limit_pct=0.10, lot_size=100)
D1 = date(2025, 1, 6)
D2 = date(2025, 1, 7)


def test_buy_sell_golden_reconciliation_with_minimum_commission_and_stamp_duty():
    account = StrategyAccount.opening(100_000.0)
    # Buy 1,000 @ 10: amount 10,000, commission max(3, 5) = 5 (minimum binds).
    amount = 1_000 * 10.0
    fee, detail = EXECUTION.buy_fee(amount)
    assert fee == 5.0 and detail["min_commission_applied"] is True and detail["stamp_duty"] == 0.0
    account.apply_buy("X", 1_000, 10.0, fee, day=D1, stop_price=9.2)
    assert account.cash == 100_000.0 - amount - fee == pytest_money(89_995.0)
    position = account.positions["X"]
    assert position.quantity == 1_000 and position.available_quantity == 0.0
    assert position.average_cost == pytest_money((amount + fee) / 1_000)

    account.settle_day()
    # Sell 600 @ 11: amount 6,600, commission max(1.98, 5)=5 (minimum binds), stamp 6.6.
    sell_amount = 600 * 11.0
    sell_fee, sell_detail = EXECUTION.sell_fee(sell_amount)
    assert round(sell_fee, 6) == 11.6 and round(sell_detail["stamp_duty"], 6) == 6.6
    account.apply_sell("X", 600, 11.0, sell_fee)
    assert account.cash == pytest_money(89_995.0 + sell_amount - sell_fee)
    assert account.positions["X"].quantity == 400
    # Equity marks the remaining 400 at 11.
    assert account.equity({"X": 11.0}) == pytest_money(account.cash + 4_400.0)
    # Cash reconciles: initial - outflows + inflows.
    assert account.cash == pytest_money(100_000.0 - (amount + fee) + (sell_amount - sell_fee))


def pytest_money(value: float) -> float:
    return round(value, 6)


def test_proportional_commission_replaces_minimum_on_large_amounts():
    fee, detail = EXECUTION.buy_fee(100_000.0)
    assert round(fee, 6) == 30.0 and detail["min_commission_applied"] is False
    fee, detail = EXECUTION.sell_fee(100_000.0)
    assert round(fee, 6) == 130.0


def test_t_plus_one_buys_are_unsellable_until_settlement():
    account = StrategyAccount.opening(50_000.0)
    fee, _ = EXECUTION.buy_fee(10_000.0)
    account.apply_buy("X", 1_000, 10.0, fee, day=D1, stop_price=9.2)
    try:
        account.apply_sell("X", 1_000, 10.0, 0.0)
        raise AssertionError("same-day sell must fail")
    except ValueError:
        pass
    account.settle_day()
    account.apply_sell("X", 1_000, 10.0, 0.0)
    assert "X" not in account.positions


def test_multiple_instruments_share_one_cash_ledger():
    account = StrategyAccount.opening(100_000.0)
    fee_a, _ = EXECUTION.buy_fee(10_000.0)
    fee_b, _ = EXECUTION.buy_fee(20_000.0)
    assert (fee_a, round(fee_b, 6)) == (5.0, 6.0)  # A hits the minimum, B pays proportionally.
    account.apply_buy("A", 1_000, 10.0, fee_a, day=D1, stop_price=9.2)
    account.apply_buy("B", 2_000, 10.0, fee_b, day=D1, stop_price=9.2)
    assert account.cash == pytest_money(100_000.0 - 10_005.0 - 20_006.0)
    assert set(account.positions) == {"A", "B"}
    assert account.market_value({"A": 10.0, "B": 10.0}) == pytest_money(30_000.0)
    account.settle_day()
    fee_a_out, _ = EXECUTION.sell_fee(11_000.0)
    assert round(fee_a_out, 6) == 16.0  # commission minimum 5 + stamp 11
    account.apply_sell("A", 1_000, 11.0, fee_a_out)
    assert "A" not in account.positions and "B" in account.positions
    assert round(account.cash, 6) == pytest_money(69_989.0 + 11_000.0 - 16.0)


def test_split_adjusts_position_without_touching_cash():
    account = StrategyAccount.opening(100_000.0)
    fee, _ = EXECUTION.buy_fee(20_000.0)
    account.apply_buy("X", 1_000, 20.0, fee, day=D1, stop_price=18.4)
    cash_before = account.cash
    account.settle_day()
    account.apply_split("X", 2.0)
    position = account.positions["X"]
    assert position.quantity == 2_000 and position.available_quantity == 2_000
    assert position.average_cost == pytest_money((20_000.0 + fee) / 2_000)
    assert position.entry_price == 10.0 and position.stop_price == pytest_money(9.2)
    assert account.cash == cash_before


def test_sell_beyond_position_or_availability_fails_closed():
    account = StrategyAccount.opening(100_000.0)
    fee, _ = EXECUTION.buy_fee(10_000.0)
    account.apply_buy("X", 1_000, 10.0, fee, day=D1, stop_price=9.2)
    for quantity in (1_001.0, -1.0):
        try:
            account.apply_sell("X", quantity, 10.0, 0.0)
            raise AssertionError("invalid sell must fail")
        except ValueError:
            pass
