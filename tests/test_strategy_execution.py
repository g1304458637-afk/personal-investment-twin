"""Engine execution-model tests with crafted datasets: every rejection and
fill path keeps an explainable reason and hand-checked money."""
from __future__ import annotations

import pandas as pd

from tests.strategy_fixtures import bar, dataset_writer, day, flat_bar, run, run_params


def bdays(start: str, count: int) -> list[str]:
    return [value.date().isoformat() for value in pd.bdate_range(start, periods=count)]


UNIVERSE = lambda instrument, list_date="2025-01-01", delist=None: [
    {"instrument": instrument, "display_name": instrument, "list_date": list_date,
     "delist_date": delist or ""}]


def breakout_dataset(instrument: str, *, base: float = 10.0, breakout: float = 11.5,
                     extra_days: list[dict[str, object]] | None = None,
                     list_date: str = "2025-01-01") -> tuple[list[dict], list[dict]]:
    """25 flat closes then one breakout close: an entry signal on day 26."""
    days = bdays("2025-01-02", 26)
    prices = [flat_bar(text, instrument, base) for text in days[:25]]
    prices.append(bar(days[25], instrument, base, breakout, base, breakout))
    prices.extend(extra_days or [])
    return UNIVERSE(instrument, list_date), prices


def test_limit_up_open_rejects_the_buy_and_keeps_cash_intact(dataset_writer):
    universe, prices = breakout_dataset("SYN_POOL_B01")
    # Day 27 opens exactly at the limit price of the day-26 close: unfillable.
    # Its own close stays below the prior high so no follow-up order appears.
    days = bdays("2025-01-02", 28)
    prices.append(bar(days[26], "SYN_POOL_B01", 12.65, 12.8, 11.2, 11.2))
    prices.append(bar(days[27], "SYN_POOL_B01", 11.2, 11.2, 11.2, 11.2))
    _, result, payload = run(dataset_writer(universe, prices))
    rejected = [item for item in result.orders if item.status == "rejected"]
    assert len(rejected) == 1
    assert rejected[0].resolution_reason == "limit_up_open"
    assert rejected[0].resolution_date == day(days[26])
    event = next(item for item in payload["days"][26]["events"] if item["kind"] == "order_rejected")
    assert event["open"] == 12.65 and event["limit_up_price"] == 12.65
    assert result.fills == []
    assert result.days[26].cash == 1_000_000.0 and not result.days[26].holdings


def test_order_into_suspension_expires_with_reason(dataset_writer):
    # B02 keeps trading through the window so the suspended session still
    # exists in the simulation calendar; B01 has no bar on that session.
    days = bdays("2025-01-02", 29)
    universe = [*UNIVERSE("SYN_POOL_B01"), *UNIVERSE("SYN_POOL_B02")]
    u1, prices_b01 = breakout_dataset("SYN_POOL_B01")
    prices_b02 = [flat_bar(text, "SYN_POOL_B02", 10.0) for text in days]
    _, result, payload = run(dataset_writer(universe, prices_b01 + prices_b02))
    cancelled = [item for item in result.orders if item.status == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].resolution_reason == "suspended_expired"
    assert cancelled[0].resolution_date == day(days[26])
    event = next(item for item in payload["days"][26]["events"] if item["kind"] == "order_cancelled")
    assert event["reason"] == "suspended_expired"
    assert not [item for item in result.fills if item.instrument == "SYN_POOL_B01"]


def test_insufficient_cash_rejects_the_second_same_morning_buy(dataset_writer):
    universe = [*UNIVERSE("SYN_POOL_B01"), *UNIVERSE("SYN_POOL_B02")]
    u1, p1 = breakout_dataset("SYN_POOL_B01")
    u2, p2 = breakout_dataset("SYN_POOL_B02")
    days = bdays("2025-01-02", 28)
    tail = [bar(days[26], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5),
            bar(days[27], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5),
            bar(days[26], "SYN_POOL_B02", 11.5, 11.5, 11.5, 11.5),
            bar(days[27], "SYN_POOL_B02", 11.5, 11.5, 11.5, 11.5)]
    _, result, payload = run(dataset_writer(universe, p1 + p2 + tail),
                             params=run_params(position_fraction=1.0, initial_cash=100_000.0))
    fills = [(item.instrument, item.quantity, item.price, round(item.fee, 6)) for item in result.fills]
    assert fills == [("SYN_POOL_B01", 8600.0, 11.5, 29.67)]
    rejected = [item for item in result.orders if item.status == "rejected"]
    assert [item.resolution_reason for item in rejected] == ["insufficient_cash"]
    event = next(item for item in payload["days"][26]["events"] if item["kind"] == "order_rejected")
    assert event["intended_quantity"] == 8600.0 and event["affordable_quantity"] == 0.0
    assert round(event["cash"], 6) == 1070.33


def test_stop_loss_is_deferred_on_entry_day_then_fills_at_gap_open(dataset_writer):
    universe, prices = breakout_dataset("SYN_POOL_B01", breakout=12.0)
    days = bdays("2025-01-02", 28)
    # Entry day 27 itself dips below the stop: stops run before buys, so the
    # earliest possible stop is the day after entry (structural T+1).
    prices.append(bar(days[26], "SYN_POOL_B01", 12.0, 12.1, 11.0, 11.1))
    # Day 28 opens below the stop: the declared gap model fills at the open.
    prices.append(bar(days[27], "SYN_POOL_B01", 11.0, 11.2, 10.9, 11.1))
    _, result, payload = run(dataset_writer(universe, prices))
    # The entry fill happens that morning; no stop-loss execution may exist on
    # the entry day itself (stops run before buys, so T+1 is structural).
    assert [item for item in payload["days"][26]["events"]
            if item["kind"] == "fill" and item.get("trigger") == "stop_loss"] == []
    stop_fills = [item for item in result.fills if item.trigger == "stop_loss"]
    assert len(stop_fills) == 1
    fill = stop_fills[0]
    assert fill.day == day(days[27]) and fill.note == "stop_gap_open_below_stop"
    assert (fill.quantity, fill.price, round(fill.fee, 6)) == (20800.0, 11.0, 297.44)
    # Golden round trip: proceeds - buy cost including fees.
    assert round(payload["summary"]["round_trips"][0]["pnl"], 6) == -21172.32
    assert not result.days[-1].holdings


def test_intraday_stop_fills_at_the_stop_price(dataset_writer):
    universe, prices = breakout_dataset("SYN_POOL_B01", breakout=12.0)
    days = bdays("2025-01-02", 28)
    prices.append(bar(days[26], "SYN_POOL_B01", 12.0, 12.0, 12.0, 12.0))
    # Day 28: open above the stop, low touches it -> declared intraday fill at stop.
    prices.append(bar(days[27], "SYN_POOL_B01", 11.5, 11.6, 11.0, 11.1))
    _, result, _ = run(dataset_writer(universe, prices))
    fill = next(item for item in result.fills if item.trigger == "stop_loss")
    assert (fill.quantity, round(fill.price, 6), round(fill.fee, 6)) == (20800.0, 11.04, 298.5216)
    assert fill.note == "stop_intraday"


def test_delisting_liquidates_at_last_close_and_cancels_pending_orders(dataset_writer):
    # Index 25 = 2025-02-06 (breakout signal), 26 = 2025-02-07, 30 = 2025-02-13.
    universe = [*UNIVERSE("SYN_POOL_B01", delist="2025-02-13"),
                *UNIVERSE("SYN_POOL_B02", delist="2025-02-07")]
    u1, p1 = breakout_dataset("SYN_POOL_B01")
    u2, p2 = breakout_dataset("SYN_POOL_B02")
    days = bdays("2025-01-02", 31)
    tail = [bar(days[index], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5) for index in (26, 27, 28, 29)]
    # B02 signals on 2025-02-06 and is delisted on 2025-02-07 with no further bars.
    _, result, _ = run(dataset_writer(universe, p1 + p2 + tail))
    liquidation = next(item for item in result.fills if item.trigger == "delisting_liquidation")
    assert liquidation.instrument == "SYN_POOL_B01"
    assert (liquidation.quantity, liquidation.price) == (21700.0, 11.5)
    assert round(liquidation.fee, 6) == 324.415 and liquidation.note == "delisting_forced_liquidation"
    assert liquidation.day == day(days[30])
    cancelled = [item for item in result.orders if item.status == "cancelled"
                 and item.instrument == "SYN_POOL_B02"]
    assert [item.resolution_reason for item in cancelled] == ["delisted"]
    assert round(result.days[-1].cash, 6) == 999_600.72 and not result.days[-1].holdings


def test_same_morning_sells_settle_before_buys_and_reuse_cash(dataset_writer):
    # C01 climbs from a flat base (prior-10-low 11.3 stays above its 11.04 stop),
    # exits by the A3 signal, and C02 breaks out the same evening.
    c01_days = bdays("2025-01-02", 30)
    c01 = [flat_bar(text, "SYN_POOL_C01", 11.3) for text in c01_days[:25]]
    c01.append(bar(c01_days[25], "SYN_POOL_C01", 11.3, 12.0, 11.3, 12.0))
    c01.append(bar(c01_days[26], "SYN_POOL_C01", 12.0, 12.0, 12.0, 12.0))
    c01.append(bar(c01_days[27], "SYN_POOL_C01", 12.0, 12.0, 11.1, 11.1))
    c01.append(bar(c01_days[28], "SYN_POOL_C01", 11.1, 11.1, 11.1, 11.1))
    c01.append(bar(c01_days[29], "SYN_POOL_C01", 11.1, 11.1, 11.1, 11.1))
    c02 = [flat_bar(text, "SYN_POOL_C02", 20.0) for text in c01_days[:27]]
    c02.append(bar(c01_days[27], "SYN_POOL_C02", 20.0, 23.0, 20.0, 23.0))
    c02.append(bar(c01_days[28], "SYN_POOL_C02", 23.0, 23.0, 23.0, 23.0))
    c02.append(bar(c01_days[29], "SYN_POOL_C02", 23.0, 23.0, 23.0, 23.0))
    universe = [*UNIVERSE("SYN_POOL_C01"), *UNIVERSE("SYN_POOL_C02")]
    _, result, payload = run(dataset_writer(universe, c01 + c02))
    day29 = payload["days"][28]
    fills_that_day = [item for item in day29["events"] if item["kind"] == "fill"]
    assert [(item["instrument"], item["side"]) for item in fills_that_day] == [
        ("SYN_POOL_C01", "SELL"), ("SYN_POOL_C02", "BUY")]
    buy = next(item for item in result.fills if item.instrument == "SYN_POOL_C02")
    assert (buy.quantity, buy.price, round(buy.fee, 6)) == (10600.0, 23.0, 73.14)
    # Hand reconciliation: cash after sell-in then buy-out on the same morning.
    assert round(result.days[28].cash, 6) == 737_031.836
    assert [item["instrument"] for item in day29["holdings"]] == ["SYN_POOL_C02"]


def test_entry_sizing_scales_down_to_affordable_lots(dataset_writer):
    # Three positions absorb ~75% of cash; the fourth entry signals at close 46
    # but fills at an open of 48, so the intended 54 lots no longer fit: the
    # fill scales down to whole lots that the remaining cash covers.
    base = {"SYN_POOL_B01": 10.0, "SYN_POOL_B02": 20.0, "SYN_POOL_B03": 30.0}
    days = bdays("2025-01-02", 49)
    prices: list[dict[str, object]] = []
    universe = []
    for instrument, level in base.items():
        universe.append({"instrument": instrument, "display_name": instrument,
                         "list_date": "2025-01-01", "delist_date": ""})
        prices.extend(flat_bar(text, instrument, level) for text in days[:25])
        prices.append(bar(days[25], instrument, level, level * 1.15, level, level * 1.15))
        prices.extend(flat_bar(text, instrument, level * 1.15) for text in days[26:])
    universe.append({"instrument": "SYN_POOL_B04", "display_name": "SYN_POOL_B04",
                     "list_date": "2025-01-01", "delist_date": ""})
    prices.extend(flat_bar(text, "SYN_POOL_B04", 40.0) for text in days[:47])
    prices.append(bar(days[47], "SYN_POOL_B04", 40.0, 46.0, 40.0, 46.0))
    prices.append(bar(days[48], "SYN_POOL_B04", 48.0, 48.0, 48.0, 48.0))
    _, result, _ = run(dataset_writer(universe, prices))
    scaled = [item for item in result.fills if item.note == "quantity_scaled_by_cash"]
    assert len(scaled) == 1
    fill = scaled[0]
    assert (fill.instrument, fill.quantity, fill.price) == ("SYN_POOL_B04", 5200.0, 48.0)
    assert fill.quantity * fill.price + fill.fee <= result.days[46].cash + 1e-9
    assert all(item.quantity % 100 == 0.0 for item in result.fills)
