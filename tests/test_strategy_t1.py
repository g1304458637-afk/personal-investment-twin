"""T1 rule tests: strict conditions, split-adjusted signals, journal reasons."""
from __future__ import annotations

import pandas as pd

from src.strategy.strategies.t1 import t1_entry_state, t1_exit_state
from tests.strategy_fixtures import bar, dataset_writer, day, flat_bar, run


def bdays(start: str, count: int) -> list[str]:
    return [value.date().isoformat() for value in pd.bdate_range(start, periods=count)]


def test_entry_requires_strict_breakout_and_strict_sma_dominance():
    closes = tuple(10.0 for _ in range(20))
    # Newest close equals the SMA and the prior high: nothing strictly breaks.
    entered, conditions = t1_entry_state(closes + (10.0,))
    assert entered is False
    assert conditions["above_sma20"] is False and conditions["breaks_prior_high_20"] is False
    # One tick above both: entry.
    entered, conditions = t1_entry_state(closes + (10.001,))
    assert entered is True and conditions["prior_high_20"] == 10.0


def test_exit_requires_a_strict_break_of_the_prior_ten_low():
    closes = tuple(10.0 for _ in range(10))
    exited, conditions = t1_exit_state(closes + (10.0,))
    assert exited is False and conditions["below_prior_low_10"] is False
    exited, _ = t1_exit_state(closes + (9.999,))
    assert exited is True


def test_split_adjusted_series_stays_continuous(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B01", 20.0) for text in days[:26]]
    bars.append(bar(days[26], "SYN_POOL_B01", 10.0, 10.0, 10.0, 10.0))
    bars.append(bar(days[27], "SYN_POOL_B01", 10.0, 10.0, 10.0, 10.0))
    bars.append(bar(days[28], "SYN_POOL_B01", 10.0, 10.0, 10.0, 10.0))
    bars.append(bar(days[29], "SYN_POOL_B01", 10.0, 10.0, 10.0, 10.0))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    actions = [{"instrument": "SYN_POOL_B01", "ex_date": days[26], "action": "split", "ratio": 2.0}]
    data, result, payload = run(dataset_writer(universe, bars, actions))
    series = data.series["SYN_POOL_B01"]
    # Raw closes halve at the ex-date; adjusted closes do not move.
    assert series.bars[25].close == 20.0 and series.bars[26].close == 10.0
    assert series.split_factors[:26] == (2.0,) * 26 and series.split_factors[26:] == (1.0,) * 4
    assert series.adjusted_close[25] == series.adjusted_close[26] == 10.0
    # A flat adjusted series never signals: no orders, no fills.
    assert result.orders == [] and result.fills == []


def test_position_crossing_a_split_keeps_ledger_and_signals_consistent(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B01", 20.0) for text in days[:24]]
    # Day 25 (index 24): raw close 23 = adjusted 11.5, a strict breakout.
    bars.append(bar(days[24], "SYN_POOL_B01", 20.0, 23.0, 20.0, 23.0))
    # Day 26 (index 25): entry fills at the raw open 23 (factor still 2).
    bars.append(bar(days[25], "SYN_POOL_B01", 23.0, 23.0, 23.0, 23.0))
    # Ex-date 27 (index 26): raw prices halve; adjusted series is unchanged.
    bars.extend(flat_bar(text, "SYN_POOL_B01", 11.5) for text in days[26:])
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    actions = [{"instrument": "SYN_POOL_B01", "ex_date": days[26], "action": "split", "ratio": 2.0}]
    data, result, payload = run(dataset_writer(universe, bars, actions))
    fill = next(item for item in result.fills if item.side == "BUY")
    assert (fill.quantity, fill.price, fill.fee) == (10800.0, 23.0, 74.52)
    split_day = next(item for item in payload["days"] if item["date"] == days[26])
    events = [item["kind"] for item in split_day["events"]]
    assert "split_applied" in events
    holding = split_day["holdings"][0]
    assert holding["quantity"] == 21600.0
    assert round(holding["average_cost"], 6) == 11.50345
    assert holding["stop_price"] == 10.58 and holding["mark_price"] == 11.5
    # Cash is untouched by the split; no sell ever happens (raw prices would
    # have fabricated an exit: 11.5 < the prior raw 10-session lows of 20).
    assert result.days[-1].cash == split_day["cash"]
    assert not [item for item in result.orders if item.side == "SELL"]
    assert payload["summary"]["round_trip_count"] == 0


def test_signal_journal_keeps_reasons_and_conditions(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:25]]
    bars.append(bar(days[25], "SYN_POOL_B01", 10.0, 11.5, 10.0, 11.5))
    bars.append(bar(days[26], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5))
    bars.append(bar(days[27], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    _, result, payload = run(dataset_writer(universe, bars))
    signal_day = next(item for item in payload["days"] if item["date"] == days[25])
    assert signal_day["signals"][0]["kind"] == "entry"
    assert "突破" in signal_day["signals"][0]["reason"]
    order = result.orders[0]
    assert order.reason_code == "signal_entry_breakout_trend" and order.rank == 1
    assert order.reason_text
