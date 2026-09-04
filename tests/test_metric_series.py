import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_desktop_demo_evidence import _json_value, build_export
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.data.csv_importer import load_normalized_csv
from src.evidence.adapters import adapt_evidence
from src.history.metric_series import (
    build_portfolio_hhi_history,
    build_turnover_history,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTIONS_PATH = PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
PRICES_PATH = PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
INITIAL_CASH = 100_000.0
SUBJECT_ID = "test:synthetic-behavior"
CODE_VERSION = "metric-series-test-v1"


@pytest.fixture
def executions() -> pd.DataFrame:
    return load_normalized_csv(EXECUTIONS_PATH)


@pytest.fixture
def prices() -> pd.DataFrame:
    return pd.read_csv(PRICES_PATH)


def _hhi(executions: pd.DataFrame, prices: pd.DataFrame):
    return build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=INITIAL_CASH,
        subject_id=SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )


def test_hhi_history_is_deterministic_and_chronological(executions, prices):
    first = _hhi(executions, prices)
    second = _hhi(executions, prices)

    assert first == second
    assert [point.as_of for point in first.points] == sorted(
        point.as_of for point in first.points
    )
    assert len(first.points) == 5


def test_future_execution_does_not_change_past_hhi_points(executions, prices):
    future = executions.iloc[[0]].copy()
    future.loc[:, "event_time"] = pd.Timestamp("2025-01-09")
    future.loc[:, "executed_quantity"] = 1
    future.loc[:, "executed_price"] = 14.0
    future.loc[:, "order_id"] = "FUTURE-ORDER"
    future.loc[:, "execution_id"] = "FUTURE-EXECUTION"

    assert _hhi(pd.concat([executions, future], ignore_index=True), prices) == _hhi(
        executions, prices
    )


def test_future_price_does_not_change_past_hhi_points(executions, prices):
    future = prices.loc[prices["date"] == "2025-01-08"].copy()
    future.loc[:, "date"] = "2025-01-09"
    future.loc[:, "close"] = future["close"] * 50

    original = _hhi(executions, prices)
    extended = _hhi(executions, pd.concat([prices, future], ignore_index=True))

    assert extended.points[: len(original.points)] == original.points


def test_missing_required_price_is_an_insufficient_gap_without_fill(executions, prices):
    missing = prices.loc[
        ~(
            (prices["date"] == "2025-01-08")
            & (prices["instrument"] == "SYN_PAPER_WIN")
        )
    ]

    series = _hhi(executions, missing)
    point = next(item for item in series.points if item.as_of == pd.Timestamp("2025-01-08"))

    assert point.value is None
    assert point.evidence_status == "insufficient_evidence"
    assert "forward fill is not allowed" in str(point.attributes["evidence_reason"])


def test_hhi_history_preserves_existing_method_identity(executions, prices):
    series = _hhi(executions, prices)

    assert series.metric_id == "portfolio_concentration_hhi"
    assert series.method_id == "hhi_security_weights_v1"
    assert series.method_version == "1"


def test_turnover_history_exactly_reuses_daily_turnover(executions, prices):
    evidence = build_turnover_intensity_evidence(
        executions,
        prices,
        init_cash=INITIAL_CASH,
    )
    parent = adapt_evidence(
        evidence,
        subject_id=SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )

    series = build_turnover_history(evidence, parent_record=parent)

    assert [(point.as_of, point.value) for point in series.points] == [
        (item.observation_date, item.turnover) for item in evidence.daily_turnover
    ]
    assert {point.source_evidence_id for point in series.points} == {
        parent.evidence_id
    }


def test_desktop_export_is_byte_deterministic_and_contains_real_dates():
    def rendered() -> bytes:
        payload = _json_value(build_export())
        return (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    first = rendered()
    second = rendered()
    payload = json.loads(first)

    assert first == second
    assert payload["data_tier"] == "synthetic"
    assert list(payload["historical_series"]) == ["portfolio_hhi", "turnover"]
    assert payload["historical_series"]["portfolio_hhi"]["points"][0]["as_of"].startswith(
        "2025-01-02"
    )
    episode_demo = payload["position_episode_demo"]
    assert episode_demo["data_tier"] == "synthetic"
    assert {entry["episode"]["status"] for entry in episode_demo["entries"]} == {
        "open",
        "closed",
    }
    exported_episode_ids = {
        entry["episode"]["episode_id"] for entry in episode_demo["entries"]
    }
    current_twin = payload["twin"]["current_snapshot"]
    assert {
        reference["episode_id"]
        for status in ("open", "closed")
        for reference in current_twin["episode_refs"][status]
    } <= exported_episode_ids
