from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbt as vbt
from vectorbt.portfolio.enums import RejectedOrderError, SizeType

from src.behavior import disposition_effect as disposition_module
from src.behavior import loss_averaging as loss_module
from src.behavior import turnover_intensity as turnover_module
from src.behavior.disposition_effect import build_disposition_effect_evidence
from src.behavior.loss_averaging import build_loss_averaging_evidence
from src.behavior.portfolio_concentration import (
    build_portfolio_concentration_evidence,
)
from src.behavior.replay_state import (
    BehaviorReplayError,
    prefix_portfolio_state,
    prepare_behavior_replay,
)
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.data.csv_importer import load_normalized_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTION_FIXTURE = (
    PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
)
PRICE_FIXTURE = PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
INITIAL_CASH = 100_000.0

BUILDERS = (
    build_disposition_effect_evidence,
    build_turnover_intensity_evidence,
    build_portfolio_concentration_evidence,
    build_loss_averaging_evidence,
)


@pytest.fixture(scope="module")
def behavior_executions() -> pd.DataFrame:
    return load_normalized_csv(EXECUTION_FIXTURE)


@pytest.fixture(scope="module")
def behavior_prices() -> pd.DataFrame:
    return pd.read_csv(PRICE_FIXTURE)


@pytest.fixture(scope="module")
def disposition(behavior_executions, behavior_prices):
    return build_disposition_effect_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )


@pytest.fixture(scope="module")
def turnover(behavior_executions, behavior_prices):
    return build_turnover_intensity_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )


@pytest.fixture(scope="module")
def concentration(behavior_executions, behavior_prices):
    return build_portfolio_concentration_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )


@pytest.fixture(scope="module")
def loss_averaging(behavior_executions, behavior_prices):
    return build_loss_averaging_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )


def _executions(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=(
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
        ),
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    frame["fee"] = 0.0
    frame["order_id"] = [f"ORD-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"EXE-{index}" for index in range(len(frame))]
    return frame


def _market_prices(
    prices: dict[str, list[float]],
    dates: list[str],
) -> pd.DataFrame:
    records = []
    for symbol, values in prices.items():
        for date, close in zip(dates, values):
            records.append(
                {
                    "date": date,
                    "instrument": symbol,
                    "close": close,
                    "price_type": "synthetic",
                    "data_source": "behavior_test",
                    "data_version": "v1",
                    "is_synthetic": True,
                }
            )
    return pd.DataFrame(records)


def _balanced_case() -> tuple[pd.DataFrame, pd.DataFrame]:
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 100.0, 10.0),
            ("2025-01-02", "B", "BUY", 50.0, 20.0),
        ]
    )
    prices = _market_prices({"A": [10.0], "B": [20.0]}, ["2025-01-02"])
    return executions, prices


def _closed_then_no_trade_case() -> tuple[pd.DataFrame, pd.DataFrame]:
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 100.0, 10.0),
            ("2025-01-03", "A", "SELL", 100.0, 11.0),
        ]
    )
    prices = _market_prices(
        {"A": [10.0, 11.0, 12.0]},
        ["2025-01-02", "2025-01-03", "2025-01-06"],
    )
    return executions, prices


def test_odean_counts_and_pgr_plr_match_hand_calculation(disposition):
    assert disposition.method_id == "odean_pgr_plr_v1"
    assert disposition.eligible_sale_events == 2
    assert disposition.realized_gains == 1
    # Both sale days are PARTIAL exits (50 of 100): the residual shares stay
    # paper opportunities on their sale day, one extra gain (SYN_WIN_SOLD)
    # and one extra loss (SYN_LOSS_SOLD) versus the old whole-symbol rule.
    assert disposition.paper_gains == 3
    assert disposition.realized_losses == 1
    assert disposition.paper_losses == 4
    assert disposition.neutral_observations == 3
    assert disposition.observation_count == 12
    assert disposition.pgr == pytest.approx(1 / 4)
    assert disposition.plr == pytest.approx(1 / 5)
    assert disposition.disposition_effect == pytest.approx(1 / 20)
    assert disposition.evidence_status == "complete"


def test_neutral_positions_are_excluded_from_gain_and_loss_counts(disposition):
    gain_and_loss_count = (
        disposition.realized_gains
        + disposition.paper_gains
        + disposition.realized_losses
        + disposition.paper_losses
    )

    assert gain_and_loss_count == 9
    assert disposition.neutral_observations == 3
    assert disposition.observation_count == gain_and_loss_count + 3


def test_no_sale_events_make_disposition_insufficient(
    behavior_executions,
    behavior_prices,
):
    buys_only = behavior_executions[behavior_executions["side"] == "BUY"]

    evidence = build_disposition_effect_evidence(
        buys_only,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.eligible_sale_events == 0
    assert evidence.pgr is None
    assert evidence.plr is None
    assert evidence.disposition_effect is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "No sale decision" in evidence.evidence_reason


def test_zero_pgr_denominator_is_not_fabricated(
    behavior_executions,
    behavior_prices,
):
    executions = behavior_executions.copy()
    executions.loc[executions["side"] == "SELL", "executed_price"] = 1.0
    all_loss = behavior_prices.copy()
    sale_dates = pd.to_datetime(all_loss["date"]).isin(
        pd.to_datetime(["2025-01-07", "2025-01-08"])
    )
    all_loss.loc[sale_dates, "close"] = 1.0

    evidence = build_disposition_effect_evidence(
        executions,
        all_loss,
        init_cash=INITIAL_CASH,
    )

    assert evidence.realized_gains + evidence.paper_gains == 0
    assert evidence.pgr is None
    assert evidence.plr is not None
    assert evidence.disposition_effect is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "PGR denominator is zero" in evidence.evidence_reason


def test_zero_plr_denominator_is_not_fabricated(
    behavior_executions,
    behavior_prices,
):
    executions = behavior_executions.copy()
    executions.loc[executions["side"] == "SELL", "executed_price"] = 100.0
    all_gain = behavior_prices.copy()
    sale_dates = pd.to_datetime(all_gain["date"]).isin(
        pd.to_datetime(["2025-01-07", "2025-01-08"])
    )
    all_gain.loc[sale_dates, "close"] = 100.0

    evidence = build_disposition_effect_evidence(
        executions,
        all_gain,
        init_cash=INITIAL_CASH,
    )

    assert evidence.realized_losses + evidence.paper_losses == 0
    assert evidence.plr is None
    assert evidence.pgr is not None
    assert evidence.disposition_effect is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "PLR denominator is zero" in evidence.evidence_reason


def test_disposition_avg_cost_failure_is_insufficient(
    monkeypatch,
    behavior_executions,
    behavior_prices,
):
    def missing_average_cost(*args, **kwargs):
        raise BehaviorReplayError("vectorbt average cost unavailable")

    monkeypatch.setattr(
        disposition_module,
        "prefix_portfolio_state",
        missing_average_cost,
    )

    evidence = build_disposition_effect_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.disposition_effect is None
    assert "average cost unavailable" in evidence.evidence_reason


@pytest.mark.parametrize(
    ("sell_price", "same_day_close", "expected_gains", "expected_losses"),
    [
        (11.0, 9.0, 1, 0),
        (9.0, 11.0, 0, 1),
    ],
)
def test_realized_disposition_uses_sell_execution_price_not_same_day_close(
    sell_price,
    same_day_close,
    expected_gains,
    expected_losses,
):
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 10:00", "A", "SELL", 50.0, sell_price),
        ]
    )
    prices = _market_prices(
        {"A": [10.0, same_day_close]},
        ["2025-01-02", "2025-01-03"],
    )

    evidence = build_disposition_effect_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.realized_gains == expected_gains
    assert evidence.realized_losses == expected_losses


def test_sale_calendar_day_counts_paper_opportunities_once():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-02 09:30", "PAPER", "BUY", 100.0, 10.0),
            ("2025-01-03 10:00", "A", "SELL", 50.0, 11.0),
            ("2025-01-03 12:00", "INTRADAY", "BUY", 100.0, 10.0),
            ("2025-01-03 14:00", "A", "SELL", 50.0, 9.0),
        ]
    )
    prices = _market_prices(
        {
            "A": [10.0, 8.0],
            "PAPER": [10.0, 12.0],
            "INTRADAY": [10.0, 12.0],
        },
        ["2025-01-02", "2025-01-03"],
    )

    evidence = build_disposition_effect_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.eligible_sale_events == 1
    assert evidence.realized_gains == 1
    assert evidence.realized_losses == 1
    assert evidence.paper_gains == 1
    assert evidence.paper_losses == 0
    assert evidence.observation_count == 3
    assert evidence.evidence_status == "complete"


def test_turnover_matches_pyfolio_official_portfolio_value_reference_semantics():
    dates = pd.date_range("2015-01-01", periods=20, freq="D")
    traded_value = pd.Series(20.0, index=dates)
    portfolio_value = pd.Series([50.0, 20.0] * 10, index=dates)

    result = turnover_module._portfolio_value_turnover(
        traded_value,
        portfolio_value,
    )

    expected = pd.Series([0.4, 1.0] * 10, index=dates)
    pd.testing.assert_series_equal(result, expected)


def test_turnover_uses_vectorbt_filled_value_and_portfolio_value(turnover):
    assert turnover.method_id == "pyfolio_portfolio_value_turnover_v1"
    assert turnover.denominator == "portfolio_value"
    assert turnover.observation_days == 5
    assert turnover.observation_count == 5
    assert turnover.total_traded_value == pytest.approx(10_900.0)
    for observation in turnover.daily_turnover:
        assert observation.turnover == pytest.approx(
            observation.traded_value / observation.portfolio_value
        )
    expected_mean = np.mean(
        [observation.turnover for observation in turnover.daily_turnover]
    )
    assert turnover.mean_daily_turnover == pytest.approx(expected_mean)
    assert turnover.evidence_status == "complete"


def test_no_trade_day_turnover_is_zero(turnover):
    by_date = {item.observation_date: item for item in turnover.daily_turnover}

    no_trade_day = by_date[pd.Timestamp("2025-01-06")]
    assert no_trade_day.traded_value == pytest.approx(0.0)
    assert no_trade_day.turnover == pytest.approx(0.0)
    assert no_trade_day.portfolio_value == pytest.approx(100_400.0)


def test_turnover_rejects_non_positive_portfolio_value(
    monkeypatch,
    behavior_executions,
    behavior_prices,
):
    monkeypatch.setattr(
        turnover_module,
        "daily_portfolio_value",
        lambda context: pd.Series([0.0], index=[pd.Timestamp("2025-01-02")]),
    )

    evidence = build_turnover_intensity_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.mean_daily_turnover is None
    assert "finite and positive" in evidence.evidence_reason
    assert evidence.synthetic_provenance_present is True


def test_vectorbt_no_order_cells_support_post_close_no_trade_days():
    executions, prices = _closed_then_no_trade_case()

    evidence = build_turnover_intensity_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "complete"
    assert evidence.daily_turnover[-1].observation_date == pd.Timestamp("2025-01-06")
    assert evidence.daily_turnover[-1].traded_value == pytest.approx(0.0)
    assert evidence.daily_turnover[-1].turnover == pytest.approx(0.0)


def test_vectorbt_longonly_amount_requires_nan_for_post_close_inactive_cells():
    index = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    close = pd.Series([10.0, 11.0, 12.0], index=index, name="A")
    common = {
        "close": close,
        "size_type": SizeType.Amount,
        "direction": "longonly",
        "price": close,
        "fees": 0.0,
        "fixed_fees": 0.0,
        "slippage": 0.0,
        "allow_partial": False,
        "raise_reject": True,
        "init_cash": INITIAL_CASH,
    }

    with pytest.raises(RejectedOrderError, match="No open position"):
        vbt.Portfolio.from_orders(
            size=pd.Series([100.0, -100.0, 0.0], index=index, name="A"),
            **common,
        )

    portfolio = vbt.Portfolio.from_orders(
        size=pd.Series([100.0, -100.0, np.nan], index=index, name="A"),
        **common,
    )

    assert len(portfolio.orders.records_readable) == 2
    assert portfolio.assets().iloc[-1] == pytest.approx(0.0)
    assert portfolio.cash().iloc[-1] == pytest.approx(100_100.0)
    assert portfolio.value().iloc[-1] == pytest.approx(100_100.0)
    assert portfolio.positions.records_readable.iloc[0]["Status"] == "Closed"


def test_balanced_two_asset_concentration_has_hhi_one_half_and_excludes_cash():
    executions, prices = _balanced_case()

    evidence = build_portfolio_concentration_evidence(
        executions,
        prices,
        init_cash=1_000_000.0,
    )

    assert evidence.method_id == "hhi_security_weights_v1"
    assert evidence.active_asset_count == 2
    assert evidence.top1_weight == pytest.approx(0.5)
    assert evidence.top3_weight == pytest.approx(1.0)
    assert evidence.hhi == pytest.approx(0.5)
    assert evidence.evidence_status == "complete"


def test_single_asset_concentration_has_hhi_one():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100.0, 10.0)]
    )
    prices = _market_prices({"A": [10.0]}, ["2025-01-02"])

    evidence = build_portfolio_concentration_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.active_asset_count == 1
    assert evidence.top1_weight == pytest.approx(1.0)
    assert evidence.top3_weight == pytest.approx(1.0)
    assert evidence.hhi == pytest.approx(1.0)


def test_synthetic_fixture_has_auditable_concentration_result(concentration):
    values = np.array([500.0, 800.0, 5_850.0, 1_050.0, 500.0])
    weights = values / values.sum()

    assert concentration.as_of_time == pd.Timestamp("2025-01-08")
    assert concentration.active_asset_count == 5
    assert concentration.top1_weight == pytest.approx(5_850.0 / 8_700.0)
    assert concentration.top3_weight == pytest.approx(7_700.0 / 8_700.0)
    assert concentration.hhi == pytest.approx(np.square(weights).sum())


def test_no_risky_assets_make_concentration_insufficient():
    executions, prices = _closed_then_no_trade_case()

    evidence = build_portfolio_concentration_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.active_asset_count == 0
    assert evidence.hhi is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "No risky asset holdings" in evidence.evidence_reason


def test_loss_state_buy_is_detected_from_vectorbt_pre_trade_state(loss_averaging):
    event = next(
        item
        for item in loss_averaging.events
        if item.symbol == "SYN_PAPER_LOSS" and item.eligible_event
    )

    assert loss_averaging.method_id == "loss_state_add_v1"
    assert event.pre_trade_position == pytest.approx(100.0)
    assert event.pre_trade_avg_cost == pytest.approx(10.0)
    assert event.execution_price == pytest.approx(9.0)
    assert event.added_quantity == pytest.approx(50.0)
    assert event.eligible_event is True
    assert event.event_detected is True


def test_gain_state_buy_is_an_eligible_non_event(loss_averaging):
    event = next(
        item
        for item in loss_averaging.events
        if item.symbol == "SYN_PAPER_WIN" and item.eligible_event
    )

    assert event.pre_trade_position == pytest.approx(400.0)
    assert event.pre_trade_avg_cost == pytest.approx(10.0)
    assert event.execution_price == pytest.approx(11.0)
    assert event.eligible_event is True
    assert event.event_detected is False


def test_new_positions_are_not_loss_averaging_events(loss_averaging):
    opening_events = [
        item
        for item in loss_averaging.events
        if item.event_time == pd.Timestamp("2025-01-02")
    ]

    assert len(opening_events) == 5
    assert all(item.pre_trade_position == 0 for item in opening_events)
    assert all(item.pre_trade_avg_cost is None for item in opening_events)
    assert all(item.eligible_event is False for item in opening_events)
    assert all(item.event_detected is False for item in opening_events)


def test_loss_averaging_summary_uses_only_existing_position_adds(loss_averaging):
    assert loss_averaging.observation_count == 7
    assert loss_averaging.eligible_add_events == 2
    assert loss_averaging.loss_averaging_events == 1
    assert loss_averaging.event_rate == pytest.approx(0.5)
    assert loss_averaging.evidence_status == "complete"


@pytest.mark.parametrize(
    ("buy_price", "same_day_close", "expected_detected"),
    [
        (9.0, 11.0, True),
        (11.0, 9.0, False),
    ],
)
def test_loss_averaging_uses_buy_execution_price_not_same_day_close(
    buy_price,
    same_day_close,
    expected_detected,
):
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 10:00", "A", "BUY", 50.0, buy_price),
        ]
    )
    prices = _market_prices(
        {"A": [10.0, same_day_close]},
        ["2025-01-02", "2025-01-03"],
    )

    evidence = build_loss_averaging_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )
    event = next(item for item in evidence.events if item.eligible_event)

    assert event.pre_trade_avg_cost == pytest.approx(10.0)
    assert event.execution_price == pytest.approx(buy_price)
    assert event.event_detected is expected_detected
    assert evidence.evidence_status == "complete"


def test_prefix_state_uses_vectorbt_open_position_after_partial_sale(
    behavior_executions,
    behavior_prices,
):
    context = prepare_behavior_replay(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    state = prefix_portfolio_state(context, pd.Timestamp("2025-01-08"))

    assert state.holdings["SYN_WIN_SOLD"] == pytest.approx(50.0)
    assert state.average_costs["SYN_WIN_SOLD"] == pytest.approx(10.0)


def test_prefix_state_uses_current_open_inventory_after_reduce_then_add():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 09:30", "A", "SELL", 50.0, 12.0),
            ("2025-01-06 09:30", "A", "BUY", 50.0, 8.0),
            ("2025-01-07 09:30", "A", "SELL", 10.0, 9.0),
        ]
    )
    prices = _market_prices(
        {"A": [10.0, 12.0, 8.0, 9.0]},
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"],
    )
    context = prepare_behavior_replay(executions, prices, init_cash=INITIAL_CASH)

    state = prefix_portfolio_state(context, pd.Timestamp("2025-01-07 09:30"))

    assert state.holdings["A"] == pytest.approx(100.0)
    assert state.average_costs["A"] == pytest.approx(9.0)


def test_no_existing_position_adds_have_no_fabricated_event_rate():
    executions, prices = _balanced_case()

    evidence = build_loss_averaging_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.observation_count == 2
    assert evidence.eligible_add_events == 0
    assert evidence.loss_averaging_events == 0
    assert evidence.event_rate is None
    assert evidence.evidence_status == "insufficient_evidence"


def test_loss_averaging_avg_cost_failure_is_insufficient(
    monkeypatch,
    behavior_executions,
    behavior_prices,
):
    real_prefix = loss_module.prefix_portfolio_state

    def fail_on_add(context, event_time):
        if pd.Timestamp(event_time) == pd.Timestamp("2025-01-03"):
            raise BehaviorReplayError("vectorbt average cost unavailable")
        return real_prefix(context, event_time)

    monkeypatch.setattr(loss_module, "prefix_portfolio_state", fail_on_add)

    evidence = build_loss_averaging_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.event_rate is None
    assert "average cost unavailable" in evidence.evidence_reason


@pytest.mark.parametrize("builder", BUILDERS)
def test_missing_market_price_is_insufficient_without_filling(
    builder,
    behavior_executions,
    behavior_prices,
):
    missing = behavior_prices[
        ~(
            (behavior_prices["instrument"] == "SYN_NEUTRAL")
            & (behavior_prices["date"] == "2025-01-06")
        )
    ]

    evidence = builder(
        behavior_executions,
        missing,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert "forward fill is not allowed" in evidence.evidence_reason


@pytest.mark.parametrize("builder", BUILDERS)
def test_missing_entire_execution_date_is_insufficient(
    builder,
    behavior_executions,
    behavior_prices,
):
    missing = behavior_prices[behavior_prices["date"] != "2025-01-07"]

    evidence = builder(
        behavior_executions,
        missing,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert "Missing market prices for execution dates" in evidence.evidence_reason


@pytest.mark.parametrize("builder", BUILDERS)
def test_invalid_execution_is_insufficient(
    builder,
    behavior_executions,
    behavior_prices,
):
    invalid = behavior_executions.copy()
    invalid.loc[invalid.index[0], "side"] = "HOLD"

    evidence = builder(invalid, behavior_prices, init_cash=INITIAL_CASH)

    assert evidence.evidence_status == "insufficient_evidence"
    assert "side must be BUY or SELL" in evidence.evidence_reason


@pytest.mark.parametrize("builder", BUILDERS)
def test_short_or_margin_replay_is_insufficient(builder):
    executions = _executions(
        [("2025-01-02", "A", "SELL", 100.0, 10.0)]
    )
    prices = _market_prices({"A": [10.0]}, ["2025-01-02"])

    evidence = builder(executions, prices, init_cash=INITIAL_CASH)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.evidence_reason is not None


@pytest.mark.parametrize("builder", BUILDERS)
def test_margin_purchase_is_insufficient(builder):
    executions = _executions(
        [("2025-01-02", "A", "BUY", 20_000.0, 10.0)]
    )
    prices = _market_prices({"A": [10.0]}, ["2025-01-02"])

    evidence = builder(executions, prices, init_cash=INITIAL_CASH)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.evidence_reason is not None


@pytest.mark.parametrize("builder", BUILDERS)
def test_unknown_price_type_is_insufficient(
    builder,
    behavior_executions,
    behavior_prices,
):
    invalid = behavior_prices.copy()
    invalid.loc[invalid["instrument"] == "SYN_WIN_SOLD", "price_type"] = "raw_close"

    evidence = builder(
        behavior_executions,
        invalid,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert "unsupported price_type" in evidence.evidence_reason


def test_synthetic_provenance_and_method_metadata_are_preserved(
    disposition,
    turnover,
    concentration,
    loss_averaging,
):
    evidence_items = (disposition, turnover, concentration, loss_averaging)
    assert [item.method_id for item in evidence_items] == [
        "odean_pgr_plr_v1",
        "pyfolio_portfolio_value_turnover_v1",
        "hhi_security_weights_v1",
        "loss_state_add_v1",
    ]
    for item in evidence_items:
        assert item.method_source
        assert item.sample_basis
        assert item.limitation
        assert item.synthetic_provenance_present is True
        assert len(item.provenance) == 5
        assert all(record.is_synthetic is True for record in item.provenance)
        assert all(record.price_type == "synthetic" for record in item.provenance)
        assert all(
            record.data_source == "local_behavior_fixture"
            for record in item.provenance
        )


def test_outputs_do_not_create_psychological_or_black_box_score_fields(
    disposition,
    turnover,
    concentration,
    loss_averaging,
):
    forbidden_fields = {
        "behavior_score",
        "greed",
        "fear",
        "revenge_trading",
        "overconfidence",
        "fomo",
        "overtrading",
        "skill_score",
    }
    for item in (disposition, turnover, concentration, loss_averaging):
        assert forbidden_fields.isdisjoint(field.name for field in fields(item))
