"""The shipped synthetic fixture run: full-ledger reconciliation invariants.

These tests run the real T1 v1 demonstration dataset end to end and prove the
account books add up on every single day — cash, holdings, fees, equity,
drawdown, round trips and the no-add rule.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation, SimulationResult
from src.strategy.report import result_to_dict
from src.strategy.strategies.t1 import T1_PARAMS, build_t1_spec

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-6


@lru_cache(maxsize=1)
def _fixture_result() -> SimulationResult:
    data = load_simulation_data(ROOT / "data/sample/strategy_universe")
    return run_simulation(build_t1_spec(), data)


def test_every_day_reconciles_cash_holdings_and_equity():
    result = _fixture_result()
    initial_cash = float(T1_PARAMS["initial_cash"])
    cash = initial_cash
    for day_record in result.days:
        # Cash equals initial plus every fill's cash flow so far.
        for fill in (item for item in result.fills if item.day == day_record.day):
            amount = fill.quantity * fill.price
            cash += (-amount - fill.fee) if fill.side == "BUY" else (amount - fill.fee)
        assert cash == day_record.cash, f"cash mismatch on {day_record.day}"
        recomputed = day_record.cash + sum(
            item["quantity"] * item["mark_price"] for item in day_record.holdings)
        assert abs(recomputed - day_record.equity) < TOLERANCE
        for item in day_record.holdings:
            assert item["quantity"] % 100 == 0.0
            assert item["market_value"] == item["quantity"] * item["mark_price"]
    open_value = sum(item["quantity"] * item["mark_price"] for item in result.days[-1].holdings)
    assert abs(cash - (result.days[-1].equity - open_value)) < TOLERANCE


def test_summary_metrics_agree_with_the_daily_journal():
    result = _fixture_result()
    summary = result.summary
    payload = result_to_dict(result)
    assert summary["total_fees"] == sum(fill.fee for fill in result.fills)
    assert summary["order_count"] == len(result.orders)
    assert summary["fill_count"] == len(result.fills)
    assert summary["rejected_order_count"] + summary["cancelled_order_count"] <= len(result.orders)
    assert summary["max_drawdown"] == min(day.drawdown_from_peak for day in result.days)
    assert summary["final_equity"] == result.days[-1].equity
    assert payload["schema_version"] == "strategy_simulation.v1"
    assert payload["strategy"]["params"] == dict(T1_PARAMS)
    assert all(rule["source"] for rule in payload["strategy"]["rule_table"])
    # Round trips plus open-position PnL explain the whole result.
    closed = sum(float(item["pnl"]) for item in summary["round_trips"])
    open_pnl = sum(item["quantity"] * (item["mark_price"] - item["average_cost"])
                   for item in result.days[-1].holdings)
    assert abs(summary["final_equity"] - float(T1_PARAMS["initial_cash"]) - closed - open_pnl) < TOLERANCE


def test_no_add_rule_holds_across_the_whole_run():
    result = _fixture_result()
    seen: dict[str, str] = {}
    for fill in result.fills:
        if fill.side == "BUY":
            assert fill.instrument not in seen, f"re-entry while holding {fill.instrument}"
            seen[fill.instrument] = fill.fill_id
        else:
            assert seen.pop(fill.instrument, None) is not None, "sell without holding"
    # Whatever remains in `seen` must be exactly the open positions on the last day.
    assert set(seen) == {item["instrument"] for item in result.days[-1].holdings}


def test_fill_and_order_statuses_are_explainable():
    result = _fixture_result()
    for order in result.orders:
        assert order.status in {"pending", "filled", "cancelled", "rejected"}
        if order.status in {"cancelled", "rejected"}:
            assert order.resolution_reason
        if order.status == "filled":
            assert order.resolution_reason and order.resolution_reason.startswith("FIL-")
    for fill in result.fills:
        assert fill.fee >= 0.0 and fill.quantity > 0 and fill.price > 0
        detail_total = float(fill.fee_detail["commission"]) + float(fill.fee_detail["stamp_duty"])
        assert abs(detail_total - fill.fee) < TOLERANCE
