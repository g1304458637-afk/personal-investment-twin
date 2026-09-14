import dataclasses
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_desktop_demo_evidence import _json_value, build_export
from src.data.csv_importer import load_normalized_csv
from src.history.metric_series import (
    HistoricalMetricPoint,
    HistoricalMetricSeries,
    build_portfolio_hhi_history,
)
from src.twin.state import (
    build_historical_twin_snapshots,
    build_twin_metric_comparison,
    build_twin_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTIONS_PATH = PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
PRICES_PATH = PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
SUBJECT_ID = "test:synthetic-twin"
SNAPSHOT_AT = pd.Timestamp("2025-01-08")


def _hhi(executions: pd.DataFrame, prices: pd.DataFrame) -> HistoricalMetricSeries:
    return build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=100_000.0,
        subject_id=SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version="twin-state-test-v1",
    )


def _snapshot(series: HistoricalMetricSeries, *, snapshot_at=SNAPSHOT_AT):
    return build_twin_snapshot(
        [],
        [series],
        subject_id=SUBJECT_ID,
        snapshot_at=snapshot_at,
        data_tier="synthetic",
    )


def _series(values: list[float | None]) -> HistoricalMetricSeries:
    return HistoricalMetricSeries(
        subject_id=SUBJECT_ID,
        metric_id="portfolio_concentration_hhi",
        method_id="hhi_security_weights_v1",
        method_version="1",
        points=tuple(
            HistoricalMetricPoint(
                as_of=pd.Timestamp("2025-01-02") + pd.Timedelta(days=index),
                value=value,
                evidence_status="complete" if value is not None else "insufficient_evidence",
                source_evidence_id=f"source-{index}",
                observation_count=1 if value is not None else 0,
            )
            for index, value in enumerate(values)
        ),
        data_tier="synthetic",
        limitations=("test limitation",),
    )


def test_twin_snapshot_is_deterministic_and_historical_snapshots_are_chronological():
    payload = build_export()
    histories = list(payload["historical_series"].values())
    subject_id = histories[0].subject_id
    records = [
        record
        for record in payload["evidence_records"]
        if record.subject_id == subject_id
    ]

    first = build_twin_snapshot(
        records,
        histories,
        subject_id=subject_id,
        snapshot_at=SNAPSHOT_AT,
        data_tier="synthetic",
    )
    second = build_twin_snapshot(
        records,
        histories,
        subject_id=subject_id,
        snapshot_at=SNAPSHOT_AT,
        data_tier="synthetic",
    )
    snapshots = build_historical_twin_snapshots(
        records,
        histories,
        subject_id=subject_id,
        snapshot_at=SNAPSHOT_AT,
        data_tier="synthetic",
    )

    assert first == second
    assert [item.snapshot_at for item in snapshots] == sorted(
        item.snapshot_at for item in snapshots
    )


def test_future_execution_does_not_change_past_twin_snapshot():
    executions = load_normalized_csv(EXECUTIONS_PATH)
    prices = pd.read_csv(PRICES_PATH)
    future = executions.iloc[[0]].copy()
    future.loc[:, "event_time"] = pd.Timestamp("2025-01-09")
    future.loc[:, "executed_quantity"] = 1
    future.loc[:, "order_id"] = "FUTURE-ORDER"
    future.loc[:, "execution_id"] = "FUTURE-EXECUTION"

    original = _snapshot(_hhi(executions, prices))
    extended = _snapshot(_hhi(pd.concat([executions, future], ignore_index=True), prices))

    assert extended == original


def test_future_price_does_not_change_past_twin_snapshot():
    executions = load_normalized_csv(EXECUTIONS_PATH)
    prices = pd.read_csv(PRICES_PATH)
    future = prices.loc[prices["date"] == "2025-01-08"].copy()
    future.loc[:, "date"] = "2025-01-09"
    future.loc[:, "close"] = future["close"] * 50

    original = _snapshot(_hhi(executions, prices))
    extended = _snapshot(_hhi(executions, pd.concat([prices, future], ignore_index=True)))

    assert extended == original


def test_historical_point_after_snapshot_at_is_excluded():
    original = _series([0.3, 0.4])
    future_point = HistoricalMetricPoint(
        as_of=pd.Timestamp("2025-02-01"),
        value=0.9,
        evidence_status="complete",
        source_evidence_id="future-source",
        observation_count=1,
    )
    extended = dataclasses.replace(original, points=(*original.points, future_point))

    assert _snapshot(original, snapshot_at=pd.Timestamp("2025-01-03")) == _snapshot(
        extended,
        snapshot_at=pd.Timestamp("2025-01-03"),
    )


def test_current_and_past_hhi_and_turnover_match_registered_points():
    payload = build_export()

    for series in payload["historical_series"].values():
        comparison = build_twin_metric_comparison(series)
        valid = [point for point in series.points if point.value is not None]
        assert comparison.reference_date == valid[0].as_of
        assert comparison.current_date == valid[-1].as_of
        assert comparison.past_value == valid[0].value
        assert comparison.current_value == valid[-1].value
        assert comparison.absolute_change == pytest.approx(
            valid[-1].value - valid[0].value
        )


def test_relative_change_is_not_fabricated_for_zero_denominator():
    comparison = build_twin_metric_comparison(_series([0.0, 0.2]))

    assert comparison.evidence_status == "complete"
    assert comparison.absolute_change == pytest.approx(0.2)
    assert comparison.relative_change is None
    assert "reference value is zero" in comparison.evidence_reason


def test_relative_change_is_not_infinite_for_tiny_reference():
    comparison = build_twin_metric_comparison(_series([1e-310, 100.0]))

    assert comparison.evidence_status == "complete"
    assert comparison.absolute_change == pytest.approx(100.0)
    assert comparison.relative_change is None
    assert "not finite" in comparison.evidence_reason


def test_no_valid_history_is_insufficient():
    comparison = build_twin_metric_comparison(_series([None]))

    assert comparison.evidence_status == "insufficient_evidence"
    assert comparison.past_value is None
    assert comparison.current_value is None
    assert comparison.absolute_change is None
    assert comparison.relative_change is None


def test_past_twin_excludes_evidence_not_yet_available():
    payload = build_export()
    histories = list(payload["historical_series"].values())
    subject_id = histories[0].subject_id
    records = [
        record
        for record in payload["evidence_records"]
        if record.subject_id == subject_id
    ]
    snapshot = build_twin_snapshot(
        records,
        histories,
        subject_id=subject_id,
        snapshot_at=SNAPSHOT_AT,
        data_tier="synthetic",
    )

    assert {item.metric_id for item in snapshot.decision_evidence_refs} == {
        "sizing_equal_weight_comparison"
    }
    assert all(item.available_at <= SNAPSHOT_AT for item in snapshot.decision_evidence_refs)
    assert all(item.available_at <= SNAPSHOT_AT for item in snapshot.behavior_evidence_refs)


def test_twin_export_is_byte_deterministic():
    def rendered() -> bytes:
        return (
            json.dumps(
                _json_value(build_export()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

    first = rendered()
    second = rendered()
    exported = json.loads(first)

    assert first == second
    assert exported["twin"]["data_tier"] == "synthetic"
    assert len(exported["twin"]["historical_snapshots"]) == 5


def test_desktop_current_twin_is_replay_backed_and_every_episode_is_resolvable():
    exported = _json_value(build_export())
    snapshot = exported["twin"]["current_snapshot"]
    episode_entries = exported["position_episode_demo"]["entries"]
    episodes_by_id = {
        item["episode"]["episode_id"]: item["episode"] for item in episode_entries
    }

    assert snapshot["portfolio_state"]["status"] == "available"
    assert snapshot["portfolio_state"]["replay_method_id"] == "vectorbt_portfolio_replay_v1"
    assert len(snapshot["portfolio_state"]["positions"]) == 5
    assert len(snapshot["episode_refs"]["open"]) == 5
    assert snapshot["episode_refs"]["closed"] == []
    assert all(
        episodes_by_id[item["episode_id"]]["subject_id"] == snapshot["subject_id"]
        for state in ("open", "closed")
        for item in snapshot["episode_refs"][state]
    )
    assert all(
        record["subject_id"] == snapshot["subject_id"]
        for reference in (
            *snapshot["decision_evidence_refs"],
            *snapshot["behavior_evidence_refs"],
        )
        for record in exported["evidence_records"]
        if record["evidence_id"] == reference["evidence_id"]
    )


def test_desktop_investments_projection_copies_twin_refs_and_neutral_names():
    exported = _json_value(build_export())
    snapshot = exported["twin"]["current_snapshot"]
    investments = exported["investments"]
    entries = exported["position_episode_demo"]["entries"]

    assert investments["subject_id"] == snapshot["subject_id"]
    assert investments["as_of"] == snapshot["snapshot_at"]
    assert investments["portfolio_state_status"] == snapshot["portfolio_state"]["status"]
    assert investments["open_episode_ids"] == [
        item["episode_id"] for item in snapshot["episode_refs"]["open"]
    ]
    assert investments["closed_episode_ids"] == [
        item["episode_id"] for item in snapshot["episode_refs"]["closed"]
    ]
    assert investments["summary"]["open_episode_count"] == snapshot[
        "data_quality_summary"
    ]["open_episode_count"]
    assert investments["summary"]["closed_episode_count"] == snapshot[
        "data_quality_summary"
    ]["closed_episode_count"]
    assert all(
        entry["instrument"]["instrument_id"] == entry["episode"]["instrument_id"]
        and entry["instrument"]["display_name"].startswith("Demo Security ")
        and entry["instrument"]["is_synthetic"] is True
        for entry in entries
    )
