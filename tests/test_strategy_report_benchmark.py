"""Hand-calculated buy-and-hold cash and corporate-action examples."""
from __future__ import annotations

from src.strategy.data import load_simulation_data, truncate_simulation_data
from src.strategy.report import BUY_HOLD_POLICY, buy_and_hold_curve, enrich_summary
from tests.strategy_fixtures import dataset_writer, day, flat_bar


def _member(name: str, listed: str, delisted: str = "") -> dict[str, str]:
    return {"instrument": name, "display_name": name,
            "list_date": listed, "delist_date": delisted}


def test_two_for_one_split_preserves_value_then_tracks_post_split_gain(dataset_writer):
    name = "SYN_POOL_B01"
    dates = ["2025-01-02", "2025-01-03", "2025-01-06"]
    data = load_simulation_data(dataset_writer(
        [_member(name, dates[0])],
        [flat_bar(dates[0], name, 100), flat_bar(dates[1], name, 50),
         flat_bar(dates[2], name, 55)],
        [{"instrument": name, "ex_date": dates[1], "action": "split", "ratio": 2}],
    ))
    assert buy_and_hold_curve(data, 100) == [
        {"date": dates[0], "equity": 100.0},
        {"date": dates[1], "equity": 100.0},
        {"date": dates[2], "equity": 110.0},
    ]
    # Future split information cannot alter a curve that stops before ex-date.
    assert buy_and_hold_curve(truncate_simulation_data(data, day(dates[1])), 100) == [
        {"date": dates[0], "equity": 100.0}]


def test_late_listing_sleeve_remains_cash_until_first_observed_close(dataset_writer):
    early, late = "SYN_POOL_B01", "SYN_POOL_B02"
    d1, d2, d3 = "2025-01-02", "2025-01-03", "2025-01-06"
    data = load_simulation_data(dataset_writer(
        [_member(early, d1), _member(late, d2)],
        [flat_bar(d1, early, 10), flat_bar(d2, early, 12),
         flat_bar(d3, early, 12), flat_bar(d3, late, 20)],
    ))
    # B02 has a list date on d2 but no bar until d3. Its CNY 50 sleeve is
    # still cash on d1/d2; B01 owns five shares throughout.
    assert buy_and_hold_curve(data, 100) == [
        {"date": d1, "equity": 100.0},
        {"date": d2, "equity": 110.0},
        {"date": d3, "equity": 110.0},
    ]
    # The roster is predefined. Removing later observations does not change
    # the earlier sleeve allocation or equity path.
    prefix = truncate_simulation_data(data, day(d3))
    assert buy_and_hold_curve(prefix, 100) == buy_and_hold_curve(data, 100)[:2]


def test_suspension_uses_last_close_and_delisting_turns_value_into_cash(dataset_writer):
    held, clock = "SYN_POOL_B01", "SYN_POOL_B02"
    d1, d2, d3, d4 = "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"
    data = load_simulation_data(dataset_writer(
        [_member(held, d1, d3), _member(clock, d1)],
        [flat_bar(d1, held, 10), flat_bar(d1, clock, 10),
         flat_bar(d2, held, 12), flat_bar(d2, clock, 10),
         flat_bar(d3, clock, 10), flat_bar(d4, clock, 10)],
    ))
    # Held sleeve: 50/10 = 5 shares, then liquidation at last CNY 12 close.
    assert buy_and_hold_curve(data, 100) == [
        {"date": d1, "equity": 100.0},
        {"date": d2, "equity": 110.0},
        {"date": d3, "equity": 110.0},
        {"date": d4, "equity": 110.0},
    ]


def test_member_without_any_bar_never_spends_its_sleeve(dataset_writer):
    traded, never_traded = "SYN_POOL_B01", "SYN_POOL_B02"
    d1, d2 = "2025-01-02", "2025-01-03"
    data = load_simulation_data(dataset_writer(
        [_member(traded, d1), _member(never_traded, d1, d2)],
        [flat_bar(d1, traded, 10), flat_bar(d2, traded, 12)],
    ))
    # Empty B02 series and its later delist event cannot make the reserved
    # CNY 50 disappear or invent a price for liquidation.
    assert buy_and_hold_curve(data, 100) == [
        {"date": d1, "equity": 100.0},
        {"date": d2, "equity": 110.0},
    ]


def test_benchmark_policy_is_published_with_summary(dataset_writer):
    name, d1 = "SYN_POOL_B01", "2025-01-02"
    data = load_simulation_data(dataset_writer(
        [_member(name, d1)], [flat_bar(d1, name, 10)],
    ))
    payload = {"summary": {"initial_cash": 100.0, "final_equity": 100.0,
                           "max_drawdown": 0.0, "round_trips": []}, "days": []}
    enrich_summary(payload, data)
    assert payload["summary"]["benchmark_buy_hold_policy"] == BUY_HOLD_POLICY
    assert payload["summary"]["benchmark_buy_hold"] == [{"date": d1, "equity": 100.0}]
