import numpy as np
import pandas as pd
import pytest

from src.attribution.sizing_evidence import build_sizing_evidence
from src.core.portfolio_replay import (
    replay_multi_asset_executions,
    simulate_target_weight_interval,
)


INITIAL_CASH = 100_000.0
DATES = pd.DatetimeIndex(
    ["2025-01-06", "2025-02-10", "2025-03-18", "2025-05-20"],
    name="event_time",
)


@pytest.fixture
def valuation_prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SYN_A": [10.0, 11.0, 12.0, 13.0],
            "SYN_B": [20.0, 18.0, 22.0, 24.0],
        },
        index=DATES,
    )


@pytest.fixture
def executions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_time": [
                DATES[0],
                DATES[0],
                DATES[1],
                DATES[2],
                DATES[2],
                DATES[3],
            ],
            "symbol": ["SYN_A", "SYN_B", "SYN_A", "SYN_A", "SYN_B", "SYN_B"],
            "side": ["BUY", "BUY", "BUY", "SELL", "BUY", "SELL"],
            "executed_quantity": [3000.0, 2000.0, 1000.0, 1000.0, 500.0, 500.0],
            "executed_price": [10.0, 20.0, 11.0, 12.0, 22.0, 24.0],
            "fee": 0.0,
            "order_id": [f"ORD-{number}" for number in range(1, 7)],
            "execution_id": [f"EXE-{number}" for number in range(1, 7)],
        }
    )


@pytest.fixture
def sizing_evidence(executions, valuation_prices):
    return build_sizing_evidence(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )


def test_multi_asset_replay_state_comes_from_vectorbt(executions, valuation_prices):
    portfolio = replay_multi_asset_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    np.testing.assert_allclose(
        portfolio.assets().to_numpy(),
        [[3000.0, 2000.0], [4000.0, 2000.0], [3000.0, 2500.0], [3000.0, 2000.0]],
    )
    np.testing.assert_allclose(
        portfolio.asset_value(group_by=False).to_numpy(),
        [
            [30_000.0, 40_000.0],
            [44_000.0, 36_000.0],
            [36_000.0, 55_000.0],
            [39_000.0, 48_000.0],
        ],
    )
    np.testing.assert_allclose(
        portfolio.cash().to_numpy(),
        [30_000.0, 19_000.0, 20_000.0, 32_000.0],
    )
    np.testing.assert_allclose(
        portfolio.value().to_numpy(),
        [100_000.0, 99_000.0, 111_000.0, 119_000.0],
    )


def test_same_timestamp_executions_form_one_decision_point(sizing_evidence):
    assert [item.decision_time for item in sizing_evidence] == list(DATES)
    assert len(sizing_evidence) == 4
    assert sizing_evidence[0].active_assets == ("SYN_A", "SYN_B")
    assert sizing_evidence[-1].interval_end_time is None
    assert sizing_evidence[-1].evidence_status == "insufficient_evidence"
    assert "No next distinct decision point" in sizing_evidence[-1].evidence_reason


def test_three_complete_intervals_match_vectorbt_counterfactuals(sizing_evidence):
    first, second, third = sizing_evidence[:3]

    assert [item.evidence_status for item in (first, second, third)] == [
        "complete",
        "complete",
        "complete",
    ]
    assert [item.interval_end_time for item in (first, second, third)] == list(DATES[1:])

    assert first.actual_end_value == pytest.approx(99_000.0)
    assert first.baseline_end_value == pytest.approx(100_000.0)
    assert first.comparison == "underperformed_baseline"

    assert second.actual_end_value == pytest.approx(111_000.0)
    assert second.baseline_end_value == pytest.approx(111_525.25252525252)
    assert second.comparison == "underperformed_baseline"

    assert third.actual_end_value == pytest.approx(119_000.0)
    assert third.baseline_end_value == pytest.approx(118_928.0303030303)
    assert third.comparison == "outperformed_baseline"


def test_equal_weight_baseline_preserves_start_value_risk_and_cash(
    sizing_evidence,
    valuation_prices,
):
    for item in sizing_evidence[:3]:
        assert item.actual_start_value == pytest.approx(item.baseline_start_value)
        assert sum(item.actual_weights.values()) == pytest.approx(item.risky_exposure)
        assert sum(item.baseline_weights.values()) == pytest.approx(item.risky_exposure)
        assert len(set(item.baseline_weights.values())) == 1

        interval_prices = valuation_prices.loc[
            item.decision_time : item.interval_end_time,
            list(item.active_assets),
        ]
        actual = simulate_target_weight_interval(
            interval_prices,
            init_value=item.actual_start_value,
            target_weights=item.actual_weights,
        )
        baseline = simulate_target_weight_interval(
            interval_prices,
            init_value=item.baseline_start_value,
            target_weights=item.baseline_weights,
        )
        assert actual.cash().iloc[0] == pytest.approx(baseline.cash().iloc[0])
        assert actual.gross_exposure().iloc[0] == pytest.approx(
            baseline.gross_exposure().iloc[0]
        )


def test_first_interval_allocations_are_actual_and_same_exposure_equal_weight(
    sizing_evidence,
):
    first = sizing_evidence[0]

    assert first.actual_weights == pytest.approx({"SYN_A": 0.30, "SYN_B": 0.40})
    assert first.baseline_weights == pytest.approx({"SYN_A": 0.35, "SYN_B": 0.35})
    assert first.risky_exposure == pytest.approx(0.70)
    assert first.actual_start_value == pytest.approx(100_000.0)
    assert first.baseline_start_value == pytest.approx(100_000.0)


def test_equal_actual_allocation_matches_equal_weight_baseline(
    executions,
    valuation_prices,
):
    equal_executions = executions.copy()
    equal_executions.loc[
        (equal_executions["event_time"] == DATES[0])
        & (equal_executions["symbol"] == "SYN_A"),
        "executed_quantity",
    ] = 3_500.0
    equal_executions.loc[
        (equal_executions["event_time"] == DATES[0])
        & (equal_executions["symbol"] == "SYN_B"),
        "executed_quantity",
    ] = 1_750.0

    evidence = build_sizing_evidence(
        equal_executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence[0].actual_weights == pytest.approx(
        {"SYN_A": 0.35, "SYN_B": 0.35}
    )
    assert evidence[0].actual_end_value == pytest.approx(
        evidence[0].baseline_end_value
    )
    assert evidence[0].comparison == "matched_baseline"


def test_next_decision_trade_and_fee_do_not_pollute_previous_interval(
    executions,
    valuation_prices,
):
    executions = executions.copy()
    executions.loc[
        (executions["event_time"] == DATES[1]) & (executions["symbol"] == "SYN_A"),
        "fee",
    ] = 1_000.0

    evidence = build_sizing_evidence(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence[0].actual_end_value == pytest.approx(99_000.0)
    assert evidence[0].baseline_end_value == pytest.approx(100_000.0)
    assert evidence[1].actual_start_value == pytest.approx(98_000.0)


def test_single_active_asset_is_insufficient(executions, valuation_prices):
    one_asset_executions = executions[executions["symbol"] == "SYN_A"].copy()

    evidence = build_sizing_evidence(
        one_asset_executions,
        valuation_prices[["SYN_A"]],
        init_cash=INITIAL_CASH,
    )

    assert evidence[0].evidence_status == "insufficient_evidence"
    assert "Fewer than two active assets" in evidence[0].evidence_reason
    assert evidence[0].comparison is None


def test_missing_endpoint_price_is_insufficient(executions, valuation_prices):
    missing_endpoint = valuation_prices.drop(index=DATES[1])

    evidence = build_sizing_evidence(
        executions,
        missing_endpoint,
        init_cash=INITIAL_CASH,
    )

    assert evidence[0].evidence_status == "insufficient_evidence"
    assert "Missing valuation timestamps" in evidence[0].evidence_reason
    assert evidence[0].actual_end_value is None
    assert evidence[0].baseline_end_value is None


def test_same_symbol_partial_fills_at_one_timestamp_are_explicitly_insufficient(
    executions,
    valuation_prices,
):
    duplicate_fill = executions.iloc[[0]].copy()
    duplicate_fill["executed_quantity"] = 100.0
    duplicate_fill["order_id"] = "ORD-PARTIAL"
    duplicate_fill["execution_id"] = "EXE-PARTIAL"
    partial_fills = pd.concat([executions, duplicate_fill], ignore_index=True)

    evidence = build_sizing_evidence(
        partial_fills,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    assert all(item.evidence_status == "insufficient_evidence" for item in evidence)
    assert "at most one execution per symbol" in evidence[0].evidence_reason


@pytest.mark.parametrize("invalid_price", [0.0, -1.0, np.nan, np.inf])
def test_invalid_price_is_insufficient(executions, valuation_prices, invalid_price):
    invalid_prices = valuation_prices.copy()
    invalid_prices.iloc[1, 0] = invalid_price

    evidence = build_sizing_evidence(
        executions,
        invalid_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence[0].evidence_status == "insufficient_evidence"
    assert evidence[0].comparison is None


def test_short_or_margin_replay_is_insufficient(executions, valuation_prices):
    short_executions = executions.copy()
    short_executions.loc[0, "side"] = "SELL"

    evidence = build_sizing_evidence(
        short_executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    assert all(item.evidence_status == "insufficient_evidence" for item in evidence)
    assert all(item.comparison is None for item in evidence)
