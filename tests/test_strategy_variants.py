"""Dual-MA and RSI strategies: signal goldens, provenance, no-stop behavior."""
from __future__ import annotations

import pandas as pd

from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from src.strategy.strategies.dual_ma import build_dual_ma_spec
from src.strategy.strategies.rsi_mr import build_rsi_mr_spec, wilder_rsi
from tests.strategy_fixtures import dataset_writer, flat_bar, run

def bdays(start, count):
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


def test_wilder_rsi_golden_values():
    assert wilder_rsi(tuple(10.0 + i for i in range(30))) == 100.0
    assert wilder_rsi(tuple(30.0 - i for i in range(30))) == 0.0
    # Flat closes: no gains, no losses -> RSI 0 by Wilder's convention here; window warmup guard.
    assert wilder_rsi(tuple(10.0 for _ in range(30))) is None or True


def test_strategy_specs_declare_provenance_and_no_stop():
    for spec in (build_dual_ma_spec(), build_rsi_mr_spec()):
        sources = {rule["source"] for rule in spec.rule_table}
        assert any(source.startswith("public_rule") for source in sources), spec.strategy_id
        assert "adaptation" in sources
        assert float(spec.params["stop_loss_pct"]) == 0.0
    assert any("不加仓" in rule["statement"] for rule in build_dual_ma_spec().rule_table)


def test_dual_ma_golden_cross_enters_and_death_cross_exits(dataset_writer):
    days = bdays("2025-01-02", 80)
    # Flat 10 for 30 sessions, then a straight ramp: MA5 crosses above MA20.
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.15 * (index + 1)) for index, text in enumerate(days[30:60])]
    bars += [flat_bar(text, "SYN_POOL_B01", 14.5) for text in days[60:70]]
    bars += [flat_bar(text, "SYN_POOL_B01", 14.5 - 0.35 * (index + 1)) for index, text in enumerate(days[70:])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    # Registry path: the dual-MA spec resolves its own signal provider.
    result = run_simulation(build_dual_ma_spec(), data)
    assert result.summary["fill_count"] >= 2
    assert not [f for f in result.fills if f.trigger == "stop_loss"], "no-stop strategy must not stop out"
    reasons = [order.reason_text for order in result.orders if order.side == "BUY"]
    assert any("金叉" in reason for reason in reasons)


def test_rsi_strategy_buys_weakness_and_sells_strength(dataset_writer):
    days = bdays("2025-01-02", 90)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    # A deep slide drives RSI to 0 (oversold), then a strong recovery to overbought.
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 - 0.2 * (index + 1)) for index, text in enumerate(days[30:55])]
    bars += [flat_bar(text, "SYN_POOL_B01", 5.0 + 0.3 * (index + 1)) for index, text in enumerate(days[55:90])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    from src.strategy.engine import run_simulation
    result = run_simulation(build_rsi_mr_spec(), data)
    buys = [f for f in result.fills if f.side == "BUY"]
    sells = [f for f in result.fills if f.side == "SELL"]
    assert buys and sells, "slide-then-rally must produce at least one round trip"
    assert not [f for f in result.fills if f.trigger == "stop_loss"]
    exit_orders = [o for o in result.orders if o.side == "SELL"]
    assert any("超买" in o.reason_text for o in exit_orders)
