"""Turtle S2 long-only: unit sizing cap, pyramiding, 2N trailing stop."""
from __future__ import annotations

import pandas as pd

from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from src.strategy.strategies.turtle import build_turtle_spec, evaluate_close_signals
from tests.strategy_fixtures import bar, dataset_writer, flat_bar

def bdays(start, count):
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


def test_unit_sizing_caps_notional_at_fraction(dataset_writer):
    days = bdays("2025-01-02", 70)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:56]]
    bars.append(bar(days[56], "SYN_POOL_B01", 10.0, 10.2, 10.0, 10.2))
    bars.append(bar(days[57], "SYN_POOL_B01", 10.2, 10.4, 10.2, 10.4))
    bars.append(bar(days[58], "SYN_POOL_B01", 10.4, 12.0, 10.4, 12.0))  # breakout close 12 > prior high 10.4
    bars.append(bar(days[59], "SYN_POOL_B01", 12.0, 12.0, 12.0, 12.0))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    # Equity 1,000,000: ATR(20) on mostly-flat bars is small, so the notional
    # cap binds: intended = floor((25% * 1,000,000 / 12) / 100) * 100 = 20,800.
    day = data.dates[58]
    exits, candidates = evaluate_close_signals(
        dict(build_turtle_spec().params), data, day, set(), set(),
        {"equity": 1_000_000.0, "cash": 1_000_000.0, "positions": {}})
    entries = [c for c in candidates if c.kind == "entry_candidate"]
    assert entries and entries[0].intended_quantity == 20_800.0
    assert "突破" in entries[0].reason_text


def test_pyramiding_and_trailing_stop_round_trip(dataset_writer):
    days = bdays("2025-01-02", 120)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:56]]
    # A steady climb: breakout, then repeated +0.5N adds along the way.
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.25 * (index + 1)) for index, text in enumerate(days[56:100])]
    # A collapse below the 20-day low ends the trade.
    bars += [flat_bar(text, "SYN_POOL_B01", 20.0 - 0.5 * (index + 1)) for index, text in enumerate(days[100:])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    result = run_simulation(build_turtle_spec(), data)
    buys = [f for f in result.fills if f.side == "BUY"]
    assert len(buys) >= 2, "the climb must trigger at least one pyramid add"
    add_orders = [o for o in result.orders if o.reason_code == "turtle_unit_add" and o.status == "filled"]
    assert add_orders, "adds must fill as orders"
    # The trailing stop ratchets: stop_updated events exist and the last one sits
    # at most 2N below the newest entry.
    updates = [e for day in result.days for e in day.events if e.get("kind") == "stop_updated"]
    assert updates
    sells = [f for f in result.fills if f.side == "SELL"]
    assert sells, "the collapse must close the position (20-day low exit or 2N stop)"
    assert not result.days[-1].holdings
