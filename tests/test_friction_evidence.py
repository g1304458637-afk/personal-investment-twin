from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.attribution import friction_evidence as friction_module
from src.attribution.friction_evidence import build_friction_evidence
from src.core.portfolio_replay import (
    PortfolioReplayError,
    replay_multi_asset_executions,
)
from src.data.csv_importer import load_normalized_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "synthetic_executions.csv"
INITIAL_CASH = 100_000.0
ORDER_FACT_COLUMNS = ["Timestamp", "Column", "Side", "Size", "Price"]


def _execution_prices(executions: pd.DataFrame) -> pd.DataFrame:
    return executions.pivot(
        index="event_time",
        columns="symbol",
        values="executed_price",
    )


@pytest.fixture
def sample_executions() -> pd.DataFrame:
    return load_normalized_csv(SAMPLE_CSV)


@pytest.fixture
def sample_prices(sample_executions) -> pd.DataFrame:
    return _execution_prices(sample_executions)


@pytest.fixture
def sample_evidence(sample_executions, sample_prices):
    return build_friction_evidence(
        sample_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )


@pytest.fixture
def multi_asset_case() -> tuple[pd.DataFrame, pd.DataFrame]:
    times = pd.to_datetime(["2025-01-06", "2025-02-10"])
    executions = pd.DataFrame(
        {
            "event_time": [times[0], times[0], times[1], times[1]],
            "symbol": ["SYN_B", "SYN_A", "SYN_A", "SYN_B"],
            "side": ["BUY", "BUY", "SELL", "SELL"],
            "executed_quantity": [100.0, 100.0, 100.0, 100.0],
            "executed_price": [20.0, 10.0, 11.0, 18.0],
            "fee": [7.0, 5.0, 6.0, 8.0],
            "order_id": ["ORD-B1", "ORD-A1", "ORD-A2", "ORD-B2"],
            "execution_id": ["EXE-B1", "EXE-A1", "EXE-A2", "EXE-B2"],
        }
    )
    prices = pd.DataFrame(
        {"SYN_A": [10.0, 11.0], "SYN_B": [20.0, 18.0]},
        index=times,
    )
    return executions, prices


def test_sample_recorded_fee_evidence_matches_vectorbt(
    sample_executions,
    sample_prices,
    sample_evidence,
):
    actual = replay_multi_asset_executions(
        sample_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert sample_evidence.start_time == pd.Timestamp("2025-01-06 09:35:00")
    assert sample_evidence.end_time == pd.Timestamp("2025-05-20 10:05:00")
    assert sample_evidence.execution_count == 4
    assert sample_evidence.recorded_fee_total == pytest.approx(30.9)
    assert sample_evidence.recorded_fee_total == pytest.approx(
        actual.orders.records_readable["Fees"].sum()
    )
    assert sample_evidence.actual_end_value == pytest.approx(103_369.1)
    assert sample_evidence.zero_recorded_fee_end_value == pytest.approx(103_400.0)
    assert (
        sample_evidence.actual_end_value
        <= sample_evidence.zero_recorded_fee_end_value
    )
    assert sample_evidence.comparison == "lower_than_zero_fee_baseline"
    assert sample_evidence.evidence_status == "complete"
    assert sample_evidence.evidence_reason is None


def test_counterfactual_changes_only_fee_and_preserves_input_order(
    monkeypatch,
    sample_executions,
    sample_prices,
):
    replay_inputs: list[pd.DataFrame] = []
    real_replay = friction_module.replay_multi_asset_executions

    def capture_replay(executions, valuation_prices, *, init_cash):
        replay_inputs.append(executions.copy(deep=True))
        return real_replay(executions, valuation_prices, init_cash=init_cash)

    monkeypatch.setattr(
        friction_module,
        "replay_multi_asset_executions",
        capture_replay,
    )
    original = sample_executions.copy(deep=True)

    evidence = build_friction_evidence(
        sample_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "complete"
    assert len(replay_inputs) == 2
    pd.testing.assert_frame_equal(sample_executions, original)
    pd.testing.assert_frame_equal(
        replay_inputs[0].drop(columns="fee"),
        replay_inputs[1].drop(columns="fee"),
    )
    pd.testing.assert_series_equal(replay_inputs[0]["fee"], original["fee"])
    assert (replay_inputs[1]["fee"] == 0.0).all()


def test_zero_recorded_fee_case_is_valid_and_matched(
    sample_executions,
    sample_prices,
):
    zero_fee_executions = sample_executions.copy()
    zero_fee_executions["fee"] = 0.0

    evidence = build_friction_evidence(
        zero_fee_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.recorded_fee_total == pytest.approx(0.0)
    assert evidence.actual_end_value == pytest.approx(
        evidence.zero_recorded_fee_end_value
    )
    assert evidence.comparison == "matched_zero_fee_baseline"
    assert evidence.evidence_status == "complete"


def test_multi_asset_replay_and_execution_order_are_preserved(multi_asset_case):
    executions, prices = multi_asset_case
    zero_fee_executions = executions.assign(fee=0.0)
    actual = replay_multi_asset_executions(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )
    zero_fee = replay_multi_asset_executions(
        zero_fee_executions,
        prices,
        init_cash=INITIAL_CASH,
    )
    actual_orders = actual.orders.records_readable.reset_index(drop=True)
    zero_fee_orders = zero_fee.orders.records_readable.reset_index(drop=True)

    assert actual_orders["Column"].tolist() == ["SYN_B", "SYN_A", "SYN_A", "SYN_B"]
    pd.testing.assert_frame_equal(
        actual_orders[ORDER_FACT_COLUMNS],
        zero_fee_orders[ORDER_FACT_COLUMNS],
    )
    assert actual_orders["Fees"].tolist() == pytest.approx([7.0, 5.0, 6.0, 8.0])
    assert (zero_fee_orders["Fees"] == 0.0).all()

    evidence = build_friction_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )
    assert evidence.execution_count == 4
    assert evidence.recorded_fee_total == pytest.approx(26.0)
    assert evidence.actual_end_value == pytest.approx(99_874.0)
    assert evidence.zero_recorded_fee_end_value == pytest.approx(99_900.0)
    assert evidence.comparison == "lower_than_zero_fee_baseline"
    assert evidence.evidence_status == "complete"


def test_cost_scope_does_not_estimate_unrecorded_friction(sample_evidence):
    assert sample_evidence.included_costs == ("recorded_fee",)
    assert sample_evidence.excluded_costs == (
        "unrecorded_tax",
        "slippage",
        "bid_ask_spread",
        "market_impact",
        "opportunity_cost",
    )
    assert not hasattr(sample_evidence, "slippage_cost")
    assert not hasattr(sample_evidence, "market_impact_cost")
    assert not hasattr(sample_evidence, "friction_skill")


def test_empty_executions_are_insufficient(sample_executions, sample_prices):
    evidence = build_friction_evidence(
        sample_executions.iloc[0:0],
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.execution_count == 0
    assert evidence.recorded_fee_total is None
    assert evidence.comparison is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "At least one execution" in evidence.evidence_reason


@pytest.mark.parametrize("invalid_fee", [np.nan, -0.01])
def test_invalid_recorded_fee_is_insufficient(
    sample_executions,
    sample_prices,
    invalid_fee,
):
    invalid_executions = sample_executions.copy()
    invalid_executions.loc[0, "fee"] = invalid_fee

    evidence = build_friction_evidence(
        invalid_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.recorded_fee_total is None
    assert evidence.comparison is None
    assert evidence.evidence_status == "insufficient_evidence"


@pytest.mark.parametrize("invalid_case", ["short", "margin"])
def test_unsupported_short_or_margin_is_insufficient(
    sample_executions,
    sample_prices,
    invalid_case,
):
    invalid_executions = sample_executions.copy()
    if invalid_case == "short":
        invalid_executions.loc[0, "side"] = "SELL"
    else:
        invalid_executions.loc[0, "executed_quantity"] = 1_000_000.0

    evidence = build_friction_evidence(
        invalid_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.comparison is None
    assert evidence.evidence_status == "insufficient_evidence"
    assert "Actual replay unavailable" in evidence.evidence_reason


def test_replay_failure_is_insufficient(monkeypatch, sample_executions, sample_prices):
    def fail_replay(*args, **kwargs):
        raise PortfolioReplayError("forced replay failure")

    monkeypatch.setattr(
        friction_module,
        "replay_multi_asset_executions",
        fail_replay,
    )

    evidence = build_friction_evidence(
        sample_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert "forced replay failure" in evidence.evidence_reason


def test_actual_above_zero_fee_baseline_is_anomaly(
    monkeypatch,
    sample_executions,
    sample_prices,
):
    order_facts = pd.DataFrame(
        {
            "Timestamp": sample_executions["event_time"],
            "Column": sample_executions["symbol"],
            "Side": sample_executions["side"].str.title(),
            "Size": sample_executions["executed_quantity"],
            "Price": sample_executions["executed_price"],
            "Fees": sample_executions["fee"],
        }
    )

    class FakeOrders:
        def __init__(self, records):
            self.records_readable = records

    class FakePortfolio:
        def __init__(self, records, end_value):
            self.orders = FakeOrders(records)
            self._value = pd.Series(
                [INITIAL_CASH, end_value],
                index=pd.to_datetime(["2025-01-06", "2025-05-20"]),
            )

        def value(self):
            return self._value

    actual = FakePortfolio(order_facts, 100_010.0)
    zero_records = order_facts.assign(Fees=0.0)
    zero_fee = FakePortfolio(zero_records, 100_000.0)
    results = iter([actual, zero_fee])
    monkeypatch.setattr(
        friction_module,
        "replay_multi_asset_executions",
        lambda *args, **kwargs: next(results),
    )

    evidence = build_friction_evidence(
        sample_executions,
        sample_prices,
        init_cash=INITIAL_CASH,
    )

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.comparison is None
    assert "exceeds" in evidence.evidence_reason
