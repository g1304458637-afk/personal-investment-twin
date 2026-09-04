from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from src.evidence.contracts import EvidenceProvenance, create_evidence_record
from src.episodes.position_episode import build_position_episode_lifecycle
from src.history.metric_series import HistoricalMetricPoint, HistoricalMetricSeries
from src.twin.state import (
    TWIN_PROJECTION_METHOD_ID,
    TWIN_SNAPSHOT_SCHEMA_VERSION,
    TwinInputVersionRef,
    build_twin_snapshot,
    build_twin_snapshot_from_facts,
    twin_snapshot_json_bytes,
)


SUBJECT = "personal-twin:test-subject"
ACCOUNT = "test-account"
CODE_VERSION = "personal-twin-core-test-v1"
INIT_CASH = 100_000.0
T0 = pd.Timestamp("2025-01-01 23:59")
T1 = pd.Timestamp("2025-01-02 09:30")
T2 = pd.Timestamp("2025-01-03 09:30")
T3 = pd.Timestamp("2025-01-04 09:30")
T4 = pd.Timestamp("2025-01-05 09:30")
T5 = pd.Timestamp("2025-01-06 09:30")


def _executions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 100.0, "O1", "E1"),
            ("2025-01-03 09:30", "A", "BUY", 50.0, 110.0, "O2", "E2"),
            ("2025-01-04 09:30", "A", "SELL", 30.0, 120.0, "O3", "E3"),
            ("2025-01-05 09:30", "A", "SELL", 120.0, 130.0, "O4", "E4"),
            ("2025-01-06 09:30", "A", "BUY", 40.0, 140.0, "O5", "E5"),
        ],
        columns=(
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
            "order_id",
            "execution_id",
        ),
    ).assign(
        event_time=lambda frame: pd.to_datetime(frame["event_time"]),
        fee=0.0,
        account_id=ACCOUNT,
    )


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("2025-01-02", "A", 100.0),
            ("2025-01-03", "A", 110.0),
            ("2025-01-04", "A", 180.0),
            ("2025-01-05", "A", 130.0),
            ("2025-01-06", "A", 140.0),
        ],
        columns=("date", "instrument", "close"),
    ).assign(
        price_type="synthetic",
        data_source="personal_twin_core_test",
        data_version="v1",
        is_synthetic=True,
    )


def _record(
    *,
    available_at: pd.Timestamp,
    status: str = "complete",
    metric_id: str = "disposition_effect",
    observation_end: pd.Timestamp | None = None,
    provenance_as_of: pd.Timestamp | None = None,
    subject_id: str = SUBJECT,
):
    provenance = EvidenceProvenance(
        source_type="synthetic_fixture",
        source_name="personal_twin_core_test",
        data_version=f"version-{available_at.isoformat()}",
        as_of=provenance_as_of or available_at,
        price_type="synthetic",
        is_synthetic=True,
        source_id="fixture",
        instrument="A",
    )
    return create_evidence_record(
        subject_id=subject_id,
        metric_id=metric_id,
        evidence_kind="behavior",
        method_id=f"{metric_id}_test_v1",
        method_version="1",
        observation_start=T1,
        observation_end=observation_end or available_at,
        as_of=available_at,
        value=None if status == "insufficient_evidence" else 0.25,
        numerator=None,
        denominator=None,
        observation_count=0 if status == "insufficient_evidence" else 3,
        ci_lower=None,
        ci_upper=None,
        evidence_status=status,
        evidence_reason="Window incomplete" if status == "insufficient_evidence" else None,
        provenance=(provenance,),
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        limitations=("Synthetic fixture only",),
        attributes={},
        identity_attributes={"fixture_status": status},
    )


def _history(point: HistoricalMetricPoint) -> HistoricalMetricSeries:
    return HistoricalMetricSeries(
        subject_id=SUBJECT,
        metric_id="portfolio_concentration_hhi",
        method_id="hhi_security_weights_v1",
        method_version="1",
        points=(point,),
        data_tier="synthetic",
        limitations=("Synthetic fixture only",),
    )


def _snapshot(
    as_of: pd.Timestamp,
    *,
    executions: pd.DataFrame | None = None,
    prices: pd.DataFrame | None = None,
    records=(),
    histories=(),
):
    return build_twin_snapshot_from_facts(
        _executions() if executions is None else executions,
        _prices() if prices is None else prices,
        records,
        histories,
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        as_of=as_of,
        init_cash=INIT_CASH,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )


@pytest.mark.parametrize(
    (
        "as_of",
        "position",
        "open_count",
        "closed_count",
        "decision_count",
    ),
    [
        (T0, None, 0, 0, 0),
        (T1, (100.0, 100.0, 100.0, 10_000.0), 1, 0, 1),
        (T2, (150.0, 103.3333333333, 110.0, 16_500.0), 1, 0, 2),
        (T3, (120.0, 103.3333333333, 180.0, 21_600.0), 1, 0, 3),
        (T4, None, 0, 1, 4),
        (T5, (40.0, 140.0, 140.0, 5_600.0), 1, 1, 5),
    ],
)
def test_hand_checked_lifecycle_projection(
    as_of,
    position,
    open_count,
    closed_count,
    decision_count,
):
    snapshot = _snapshot(as_of)

    assert snapshot.schema_version == TWIN_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.projection_method_id == TWIN_PROJECTION_METHOD_ID
    assert len(snapshot.episode_refs.open) == open_count
    assert len(snapshot.episode_refs.closed) == closed_count
    assert len(snapshot.decision_event_refs) == decision_count
    assert snapshot.data_quality_summary.open_episode_count == open_count
    assert snapshot.data_quality_summary.closed_episode_count == closed_count
    if position is None:
        assert snapshot.portfolio_state.positions == ()
    else:
        actual = snapshot.portfolio_state.positions[0]
        quantity, average_cost, valuation_price, market_value = position
        assert actual.quantity == pytest.approx(quantity)
        assert actual.average_cost == pytest.approx(average_cost)
        assert actual.valuation_price == pytest.approx(valuation_price)
        assert actual.market_value == pytest.approx(market_value)


def test_partial_reduction_remains_open_before_future_close():
    snapshot = _snapshot(T3)

    assert snapshot.episode_refs.open[0].status == "open"
    assert snapshot.episode_refs.open[0].closed_at is None
    assert snapshot.episode_refs.open[0].closing_execution_id is None
    assert snapshot.portfolio_state.positions[0].quantity == pytest.approx(120.0)


def test_close_then_reopen_creates_second_episode():
    snapshot = _snapshot(T5)

    closed = snapshot.episode_refs.closed[0]
    opened = snapshot.episode_refs.open[0]
    assert closed.episode_id != opened.episode_id
    assert closed.execution_refs == ("E1", "E2", "E3", "E4")
    assert opened.execution_refs == ("E5",)


def test_future_execution_and_close_do_not_change_historical_twin():
    prefix = _executions().iloc[:3].copy()

    before_future = _snapshot(T3, executions=prefix, prices=_prices().iloc[:3].copy())
    after_future = _snapshot(T3)

    assert twin_snapshot_json_bytes(before_future) == twin_snapshot_json_bytes(after_future)
    assert after_future.episode_refs.open[0].status == "open"


def test_future_market_prices_do_not_change_historical_mark_or_snapshot():
    prefix_prices = _prices().iloc[:1].copy()
    before_future = _snapshot(T1, executions=_executions().iloc[:1].copy(), prices=prefix_prices)
    after_future = _snapshot(T1)

    assert twin_snapshot_json_bytes(before_future) == twin_snapshot_json_bytes(after_future)
    position = after_future.portfolio_state.positions[0]
    assert position.valuation_at == pd.Timestamp("2025-01-02 09:30")
    assert position.valuation_price == pytest.approx(100.0)
    assert position.market_value == pytest.approx(10_000.0)


def test_future_evidence_and_later_provenance_cannot_leak_backward():
    future = _record(available_at=T3)
    observed_early_but_available_late = _record(
        available_at=T1,
        metric_id="loss_averaging_event_rate",
        observation_end=T1,
        provenance_as_of=T3,
    )

    snapshot = _snapshot(T1, records=(future, observed_early_but_available_late))

    assert snapshot.behavior_evidence_refs == ()
    assert set(snapshot.evidence_summary.unavailable_metric_ids) >= {
        "disposition_effect",
        "loss_averaging_event_rate",
    }


def test_insufficient_evidence_is_retained_and_later_completion_does_not_rewrite_it():
    insufficient = _record(available_at=T1, status="insufficient_evidence")
    completed_later = _record(available_at=T3, status="complete")

    snapshot = _snapshot(T1, records=(insufficient, completed_later))

    assert snapshot.behavior_evidence_refs[0].evidence_id == insufficient.evidence_id
    assert snapshot.behavior_evidence_refs[0].evidence_status == "insufficient_evidence"
    assert snapshot.evidence_summary.insufficient == 1
    assert snapshot.evidence_summary.complete == 0


def test_historical_point_with_later_source_evidence_is_not_available():
    source = _record(
        available_at=T3,
        metric_id="portfolio_concentration_hhi",
    )
    series = _history(
        HistoricalMetricPoint(
            as_of=T1,
            value=1.0,
            evidence_status="complete",
            source_evidence_id=source.evidence_id,
            observation_count=1,
        )
    )

    snapshot = _snapshot(T1, records=(source,), histories=(series,))

    assert snapshot.behavior_state == ()


def test_same_inputs_have_stable_id_and_canonical_bytes():
    first = _snapshot(T3)
    second = _snapshot(T3)

    assert first.snapshot_id == second.snapshot_id
    assert twin_snapshot_json_bytes(first) == twin_snapshot_json_bytes(second)
    assert first.snapshot_id.startswith("tw_")
    assert len(first.snapshot_id) == 67


def test_unordered_inputs_are_canonicalized_before_snapshot_identity():
    hhi_record = _record(
        available_at=T1,
        metric_id="portfolio_concentration_hhi",
    )
    turnover_record = _record(
        available_at=T1,
        metric_id="mean_daily_turnover",
    )
    hhi_history = _history(
        HistoricalMetricPoint(
            as_of=T1,
            value=0.4,
            evidence_status="complete",
            source_evidence_id=hhi_record.evidence_id,
            observation_count=1,
        )
    )
    turnover_history = HistoricalMetricSeries(
        subject_id=SUBJECT,
        metric_id="mean_daily_turnover",
        method_id="pyfolio_portfolio_value_turnover_v1",
        method_version="1",
        points=(
            HistoricalMetricPoint(
                as_of=T1,
                value=0.1,
                evidence_status="complete",
                source_evidence_id=turnover_record.evidence_id,
                observation_count=1,
            ),
        ),
        data_tier="synthetic",
        limitations=("Synthetic fixture only",),
    )
    input_refs = (
        TwinInputVersionRef("prices", "fixture-b", "v2", T1, "synthetic", True),
        TwinInputVersionRef("prices", "fixture-a", "v1", T1, "synthetic", True),
    )

    first = build_twin_snapshot(
        (hhi_record, turnover_record),
        (hhi_history, turnover_history),
        subject_id=SUBJECT,
        snapshot_at=T1,
        data_tier="synthetic",
        input_version_refs=input_refs,
        data_quality_issues=("issue-b", "issue-a"),
    )
    reordered = build_twin_snapshot(
        (turnover_record, hhi_record),
        (turnover_history, hhi_history),
        subject_id=SUBJECT,
        snapshot_at=T1,
        data_tier="synthetic",
        input_version_refs=tuple(reversed(input_refs)),
        data_quality_issues=("issue-a", "issue-b"),
    )

    assert reordered.snapshot_id == first.snapshot_id
    assert twin_snapshot_json_bytes(reordered) == twin_snapshot_json_bytes(first)


def test_cross_subject_evidence_fails_closed_even_when_episode_linked():
    foreign = _record(
        available_at=T1,
        metric_id="selection_episode_asset_return",
        subject_id="another-subject",
    )
    lifecycle = build_position_episode_lifecycle(
        _executions().iloc[:1].copy(),
        _prices().iloc[:1].copy(),
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        as_of=T1,
        init_cash=INIT_CASH,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        episode_evidence={"E1": (foreign,)},
    )

    with pytest.raises(ValueError, match="owned by the Twin subject"):
        build_twin_snapshot(
            (foreign,),
            (),
            subject_id=SUBJECT,
            snapshot_at=T1,
            data_tier="synthetic",
            position_lifecycle=lifecycle,
        )
    with pytest.raises(ValueError, match="must resolve to Evidence owned"):
        build_twin_snapshot(
            (),
            (),
            subject_id=SUBJECT,
            snapshot_at=T1,
            data_tier="synthetic",
            position_lifecycle=lifecycle,
        )


def test_same_timestamp_execution_order_comes_from_existing_replay_contract():
    executions = pd.DataFrame(
        [
            (T1, "B", "BUY", 10.0, 20.0, 0.0, "OB", "EB", ACCOUNT),
            (T1, "A", "BUY", 10.0, 10.0, 0.0, "OA", "EA", ACCOUNT),
        ],
        columns=(
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
            "fee",
            "order_id",
            "execution_id",
            "account_id",
        ),
    )
    prices = pd.DataFrame(
        [
            ("2025-01-02", "A", 10.0),
            ("2025-01-02", "B", 20.0),
        ],
        columns=("date", "instrument", "close"),
    ).assign(
        price_type="synthetic",
        data_source="personal_twin_core_test",
        data_version="same-timestamp-v1",
        is_synthetic=True,
    )
    lifecycle = build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        as_of=T1,
        init_cash=INIT_CASH,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )
    snapshot = build_twin_snapshot(
        (),
        (),
        subject_id=SUBJECT,
        snapshot_at=T1,
        data_tier="synthetic",
        position_lifecycle=lifecycle,
    )

    assert tuple(item.execution_id for item in lifecycle.decisions) == ("EB", "EA")
    assert snapshot.decision_event_refs == tuple(
        item.decision_id for item in lifecycle.decisions
    )
    assert snapshot.snapshot_id == build_twin_snapshot(
        (),
        (),
        subject_id=SUBJECT,
        snapshot_at=T1,
        data_tier="synthetic",
        position_lifecycle=lifecycle,
    ).snapshot_id


def test_different_as_of_has_different_identity_and_no_future_serialized_facts():
    at_open = _snapshot(T1)
    after_add = _snapshot(T2)
    serialized = twin_snapshot_json_bytes(at_open)

    assert at_open.snapshot_id != after_add.snapshot_id
    assert b'"valuation_price":100.0' in serialized
    assert b'"closing_execution_id":null' in serialized
    assert b'"E2"' not in serialized
    assert b'"E3"' not in serialized
    assert b'"E4"' not in serialized
    assert b'"E5"' not in serialized
    assert b"180.0" not in serialized


def test_future_rows_do_not_change_execution_prefix_version():
    prefix = _snapshot(T2, executions=_executions().iloc[:2].copy(), prices=_prices().iloc[:2].copy())
    full = _snapshot(T2)

    prefix_ref = next(item for item in prefix.input_version_refs if item.source_type == "normalized_executions")
    full_ref = next(item for item in full.input_version_refs if item.source_type == "normalized_executions")
    assert prefix_ref.data_version == full_ref.data_version


def test_unimplemented_twin_capabilities_are_explicitly_empty():
    snapshot = _snapshot(T1)

    assert snapshot.self_baseline_refs == ()
    assert snapshot.peer_context_refs == ()
    assert snapshot.notable_change_refs == ()
    assert snapshot.intervention_history_ref is None


def test_snapshot_rejects_lifecycle_built_for_another_as_of():
    lifecycle = build_position_episode_lifecycle(
        _executions(),
        _prices(),
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        as_of=T2,
        init_cash=INIT_CASH,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )

    with pytest.raises(ValueError, match="exactly at snapshot_at"):
        build_twin_snapshot(
            (),
            (),
            subject_id=SUBJECT,
            snapshot_at=T1,
            data_tier="synthetic",
            position_lifecycle=lifecycle,
        )


def test_data_quality_reports_missing_evidence_without_a_score():
    snapshot = _snapshot(T0, records=(), histories=())

    assert snapshot.portfolio_state.status == "not_started"
    assert snapshot.data_quality_summary.referenced_evidence_count == 0
    assert snapshot.data_quality_summary.issue_count == 0
    assert len(snapshot.data_quality_summary.missing_evidence_metrics) == 8
    assert "score" not in {field.name for field in dataclasses.fields(snapshot.data_quality_summary)}
