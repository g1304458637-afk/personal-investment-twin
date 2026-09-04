from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest

from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.data.csv_importer import load_normalized_csv
from src.evidence.contracts import EvidenceProvenance, EvidenceRecord, create_evidence_record
from src.history.metric_series import (
    HistoricalMetricPoint,
    HistoricalMetricSeries,
    build_portfolio_hhi_history,
)
from src.self_baseline.core import (
    DEFAULT_WINDOW,
    PERCENTILE_METHOD,
    QUANTILE_METHOD,
    build_self_baseline_comparison,
    build_self_baseline_summary,
    get_self_baseline_metric,
    list_self_baseline_metrics,
    self_baseline_json_bytes,
)
from src.twin.state import (
    TwinInputVersionRef,
    TwinSnapshot,
    build_twin_snapshot,
    build_twin_snapshot_from_facts,
)


SUBJECT = "self-baseline:test-subject"
OTHER_SUBJECT = "self-baseline:other-subject"
AS_OF = pd.Timestamp("2026-06-15 12:00:00")
CODE_VERSION = "self-baseline-test-v1"
HHI_METHOD = "hhi_security_weights_v1"
TURNOVER_METHOD = "pyfolio_portfolio_value_turnover_v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(
    *,
    timestamp: pd.Timestamp,
    value: float | None,
    metric_id: str = "portfolio_concentration_hhi",
    method_id: str = HHI_METHOD,
    subject_id: str = SUBJECT,
    status: str = "complete",
    data_version: str = "v1",
    available_at: pd.Timestamp | None = None,
) -> EvidenceRecord:
    available = available_at or timestamp
    provenance = EvidenceProvenance(
        source_type="synthetic_fixture",
        source_name="self_baseline_test",
        data_version=data_version,
        as_of=available,
        price_type="synthetic",
        is_synthetic=True,
        source_id="self-baseline-fixture",
    )
    return create_evidence_record(
        subject_id=subject_id,
        metric_id=metric_id,
        evidence_kind="behavior_evidence",
        method_id=method_id,
        method_version="1",
        observation_start=timestamp,
        observation_end=timestamp,
        as_of=timestamp,
        value=value,
        numerator=None,
        denominator=None,
        observation_count=1 if status == "complete" else 0,
        ci_lower=None,
        ci_upper=None,
        evidence_status=status,
        evidence_reason=None if status == "complete" else "Fixture observation is insufficient",
        provenance=(provenance,),
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        limitations=("Synthetic fixture only",),
        attributes={},
        identity_attributes={
            "fixture_timestamp": timestamp.isoformat(),
            "fixture_value": value,
            "fixture_status": status,
            "fixture_data_version": data_version,
            "fixture_available_at": available.isoformat(),
        },
    )


def _fixture(
    history: tuple[tuple[pd.Timestamp, float | None, str], ...],
    *,
    current: float = 0.6,
    current_at: pd.Timestamp = AS_OF,
    metric_id: str = "portfolio_concentration_hhi",
    method_id: str = HHI_METHOD,
    subject_id: str = SUBJECT,
    data_version: str = "v1",
    input_refs: tuple[TwinInputVersionRef, ...] = (),
) -> tuple[TwinSnapshot, HistoricalMetricSeries, tuple[EvidenceRecord, ...]]:
    records: list[EvidenceRecord] = []
    points: list[HistoricalMetricPoint] = []
    for timestamp, value, status in history:
        record = _record(
            timestamp=timestamp,
            value=value,
            metric_id=metric_id,
            method_id=method_id,
            subject_id=subject_id,
            status=status,
            data_version=data_version,
        )
        records.append(record)
        points.append(
            HistoricalMetricPoint(
                as_of=timestamp,
                value=value,
                evidence_status=record.evidence_status,
                source_evidence_id=record.evidence_id,
                observation_count=record.observation_count,
            )
        )
    current_record = _record(
        timestamp=current_at,
        value=current,
        metric_id=metric_id,
        method_id=method_id,
        subject_id=subject_id,
        data_version=data_version,
    )
    records.append(current_record)
    points.append(
        HistoricalMetricPoint(
            as_of=current_at,
            value=current,
            evidence_status="complete",
            source_evidence_id=current_record.evidence_id,
            observation_count=1,
        )
    )
    series = HistoricalMetricSeries(
        subject_id=subject_id,
        metric_id=metric_id,
        method_id=method_id,
        method_version="1",
        points=tuple(sorted(points, key=lambda item: item.as_of)),
        data_tier="synthetic",
        limitations=("Synthetic fixture only",),
    )
    snapshot = build_twin_snapshot(
        tuple(records),
        (series,),
        subject_id=subject_id,
        snapshot_at=AS_OF,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        input_version_refs=input_refs,
    )
    return snapshot, series, tuple(records)


def _hand_fixture(*, current: float = 0.6):
    return _fixture(
        (
            (pd.Timestamp("2026-01-01"), 0.2, "complete"),
            (pd.Timestamp("2026-02-01"), 0.3, "complete"),
            (pd.Timestamp("2026-03-01"), 0.4, "complete"),
            (pd.Timestamp("2026-04-01"), 0.5, "complete"),
        ),
        current=current,
    )


def _replay_facts(*, future_execution: bool = False, future_price: bool = False):
    execution_rows = [
        ("2026-01-01 09:30", "A", "BUY", 10.0, 10.0, 0.0, "O1", "E1", "self-account"),
    ]
    if future_execution:
        execution_rows.append(
            ("2026-06-16 09:30", "A", "BUY", 5.0, 99.0, 0.0, "O2", "E2", "self-account")
        )
    executions = pd.DataFrame(
        execution_rows,
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
    ).assign(event_time=lambda frame: pd.to_datetime(frame["event_time"]))
    price_rows = [
        ("2026-01-01", "A", 10.0),
        ("2026-06-14", "A", 12.0),
    ]
    if future_price:
        price_rows.append(("2026-06-16", "A", 999.0))
    prices = pd.DataFrame(price_rows, columns=("date", "instrument", "close")).assign(
        price_type="synthetic",
        data_source="self_baseline_test",
        data_version="replay-v1",
        is_synthetic=True,
    )
    return executions, prices


def test_registry_is_explicit_and_freezes_observation_semantics():
    definitions = {item.metric_id: item for item in list_self_baseline_metrics()}

    assert set(definitions) == {"portfolio_concentration_hhi", "mean_daily_turnover"}
    assert definitions["portfolio_concentration_hhi"].observation_kind == "state_snapshot"
    assert definitions["portfolio_concentration_hhi"].observation_cadence == (
        "supplied_complete_market_price_observation_dates"
    )
    assert any(
        "not a time-weighted distribution" in item
        for item in definitions["portfolio_concentration_hhi"].limitations
    )
    assert definitions["portfolio_concentration_hhi"].minimum_observations["rolling_12m"] == 3
    assert definitions["mean_daily_turnover"].observation_kind == "window_statistic"
    assert definitions["mean_daily_turnover"].observation_unit == "calendar_day_portfolio_value_turnover_ratio"
    assert definitions["mean_daily_turnover"].minimum_observations["rolling_12m"] == 5
    assert get_self_baseline_metric("selection_episode_asset_return") is None


def test_hhi_timestamps_follow_actual_irregular_source_price_cadence():
    executions = load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
    )
    prices = pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )
    prices = prices[prices["date"].isin(("2025-01-02", "2025-01-06", "2025-01-08"))]

    series = build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=100_000.0,
        subject_id=SUBJECT,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )

    assert tuple(point.as_of for point in series.points) == tuple(
        pd.to_datetime(("2025-01-02", "2025-01-06", "2025-01-08"))
    )


def test_turnover_distinguishes_recorded_no_trade_date_from_absent_date():
    executions = load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
    )
    prices = pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )
    full = build_turnover_intensity_evidence(executions, prices, init_cash=100_000.0)
    by_date = {item.observation_date: item for item in full.daily_turnover}
    assert by_date[pd.Timestamp("2025-01-06")].turnover == pytest.approx(0.0)

    without_date = prices[prices["date"] != "2025-01-06"]
    sparse = build_turnover_intensity_evidence(
        executions,
        without_date,
        init_cash=100_000.0,
    )
    assert sparse.evidence_status == "complete"
    assert pd.Timestamp("2025-01-06") not in {
        item.observation_date for item in sparse.daily_turnover
    }

    incomplete_date = prices[
        ~(
            (prices["date"] == "2025-01-06")
            & (prices["instrument"] == "SYN_NEUTRAL")
        )
    ]
    incomplete = build_turnover_intensity_evidence(
        executions,
        incomplete_date,
        init_cash=100_000.0,
    )
    assert incomplete.evidence_status == "insufficient_evidence"
    assert incomplete.daily_turnover == ()


def test_hand_calculated_linear_quantiles_and_above_iqr_result():
    snapshot, series, records = _hand_fixture(current=0.6)

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.status == "complete"
    assert result.valid_n == 4
    assert result.p25 == pytest.approx(0.275)
    assert result.median == pytest.approx(0.35)
    assert result.p75 == pytest.approx(0.425)
    assert result.self_historical_percentile == pytest.approx(100.0)
    assert result.delta_from_median == pytest.approx(0.25)
    assert result.comparison_band == "above_historical_iqr"
    assert result.provenance.quantile_method == QUANTILE_METHOD
    assert result.provenance.percentile_method == PERCENTILE_METHOD
    assert result.provenance.observation_kind == "state_snapshot"
    assert result.provenance.observation_unit == "portfolio_state_snapshot"
    assert result.provenance.observation_cadence == (
        "supplied_complete_market_price_observation_dates"
    )


@pytest.mark.parametrize(
    ("current", "percentile", "band"),
    [
        (0.35, 50.0, "within_historical_iqr"),
        (0.1, 0.0, "below_historical_iqr"),
    ],
)
def test_hand_calculated_within_and_below_iqr(current, percentile, band):
    snapshot, series, records = _hand_fixture(current=current)

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.self_historical_percentile == pytest.approx(percentile)
    assert result.comparison_band == band


def test_midrank_ties_are_deterministic():
    snapshot, series, records = _fixture(
        tuple(
            (pd.Timestamp(f"2026-0{month}-01"), 0.2, "complete")
            for month in range(1, 5)
        ),
        current=0.2,
    )

    result = build_self_baseline_comparison(snapshot, series, records)

    assert (result.p25, result.median, result.p75) == pytest.approx((0.2, 0.2, 0.2))
    assert result.self_historical_percentile == pytest.approx(50.0)
    assert result.delta_from_median == pytest.approx(0.0)
    assert result.comparison_band == "within_historical_iqr"


def test_large_outlier_does_not_move_the_hand_checked_median():
    snapshot, series, records = _fixture(
        (
            (pd.Timestamp("2026-01-01"), 0.2, "complete"),
            (pd.Timestamp("2026-02-01"), 0.3, "complete"),
            (pd.Timestamp("2026-03-01"), 0.4, "complete"),
            (pd.Timestamp("2026-04-01"), 0.5, "complete"),
            (pd.Timestamp("2026-05-01"), 100.0, "complete"),
        ),
        current=0.6,
    )

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.median == pytest.approx(0.4)


def test_calendar_month_boundaries_are_inclusive_below_exclusive_above():
    just_before_12m = AS_OF - pd.DateOffset(months=12) - pd.Timedelta(microseconds=1)
    exactly_12m = AS_OF - pd.DateOffset(months=12)
    just_before_3m = AS_OF - pd.DateOffset(months=3) - pd.Timedelta(microseconds=1)
    exactly_3m = AS_OF - pd.DateOffset(months=3)
    snapshot, series, records = _fixture(
        (
            (just_before_12m, 0.1, "complete"),
            (exactly_12m, 0.2, "complete"),
            (pd.Timestamp("2025-09-15 12:00"), 0.3, "complete"),
            (pd.Timestamp("2025-12-15 12:00"), 0.4, "complete"),
            (just_before_3m, 0.5, "complete"),
            (exactly_3m, 0.6, "complete"),
            (pd.Timestamp("2026-04-15 12:00"), 0.7, "complete"),
            (pd.Timestamp("2026-05-15 12:00"), 0.8, "complete"),
        ),
        current=0.9,
    )

    recent = build_self_baseline_comparison(snapshot, series, records, window="rolling_3m")
    annual = build_self_baseline_comparison(snapshot, series, records, window="rolling_12m")
    lifetime = build_self_baseline_comparison(snapshot, series, records, window="lifetime")

    assert recent.valid_n == 3
    assert recent.observation_start == exactly_3m
    assert annual.valid_n == 7
    assert annual.observation_start == exactly_12m
    assert lifetime.valid_n == 8
    assert lifetime.observation_start == just_before_12m
    assert all(item.observation_end < AS_OF for item in (recent, annual, lifetime))


def test_current_observation_is_excluded_even_when_it_predates_snapshot_cutoff():
    current_at = AS_OF - pd.Timedelta(days=1)
    snapshot, series, records = _fixture(
        (
            (pd.Timestamp("2026-01-01"), 0.2, "complete"),
            (pd.Timestamp("2026-02-01"), 0.3, "complete"),
            (pd.Timestamp("2026-03-01"), 0.4, "complete"),
        ),
        current=0.9,
        current_at=current_at,
    )

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.valid_n == 3
    assert result.observation_end == pd.Timestamp("2026-03-01")
    assert result.self_historical_percentile == pytest.approx(100.0)


def test_future_observation_and_future_only_source_do_not_change_self_at_t():
    snapshot, series, records = _hand_fixture()
    original = build_self_baseline_comparison(snapshot, series, records)
    future_at = AS_OF + pd.Timedelta(days=1)
    future_record = _record(timestamp=future_at, value=999.0)
    future_point = HistoricalMetricPoint(
        as_of=future_at,
        value=999.0,
        evidence_status="complete",
        source_evidence_id=future_record.evidence_id,
        observation_count=1,
    )
    extended = dataclasses.replace(series, points=(*series.points, future_point))

    rebuilt = build_self_baseline_comparison(snapshot, extended, (*records, future_record))

    assert self_baseline_json_bytes(rebuilt) == self_baseline_json_bytes(original)
    assert rebuilt.comparison_id == original.comparison_id


def test_later_evidence_does_not_become_available_early():
    snapshot, series, records = _hand_fixture()
    early_time = pd.Timestamp("2025-12-01")
    later_source = _record(
        timestamp=early_time,
        value=0.99,
        available_at=AS_OF + pd.Timedelta(days=1),
    )
    early_point = HistoricalMetricPoint(
        as_of=early_time,
        value=0.99,
        evidence_status="complete",
        source_evidence_id=later_source.evidence_id,
        observation_count=1,
    )
    extended = dataclasses.replace(
        series,
        points=tuple(sorted((*series.points, early_point), key=lambda item: item.as_of)),
    )

    original = build_self_baseline_comparison(snapshot, series, records)
    rebuilt = build_self_baseline_comparison(snapshot, extended, (*records, later_source))

    assert self_baseline_json_bytes(rebuilt) == self_baseline_json_bytes(original)


def test_later_completed_fixed_window_evidence_cannot_rewrite_old_self_comparison():
    snapshot, series, records = _hand_fixture()
    original = build_self_baseline_comparison(snapshot, series, records)
    later_exit = _record(
        timestamp=pd.Timestamp("2026-02-01"),
        value=0.25,
        metric_id="exit_timing_post_exit_asset_return",
        method_id="hold_20_sessions_v1",
        available_at=AS_OF + pd.Timedelta(days=20),
    )

    rebuilt = build_self_baseline_comparison(snapshot, series, (*records, later_exit))

    assert self_baseline_json_bytes(rebuilt) == self_baseline_json_bytes(original)


@pytest.mark.parametrize(
    ("future_execution", "future_price"),
    [(True, False), (False, True)],
)
def test_future_replay_facts_cannot_contaminate_self_at_t(future_execution, future_price):
    _, series, records = _hand_fixture()
    base_executions, base_prices = _replay_facts()
    extended_executions, extended_prices = _replay_facts(
        future_execution=future_execution,
        future_price=future_price,
    )
    base_snapshot = build_twin_snapshot_from_facts(
        base_executions,
        base_prices,
        records,
        (series,),
        subject_id=SUBJECT,
        account_id="self-account",
        as_of=AS_OF,
        init_cash=100_000.0,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )
    extended_snapshot = build_twin_snapshot_from_facts(
        extended_executions,
        extended_prices,
        records,
        (series,),
        subject_id=SUBJECT,
        account_id="self-account",
        as_of=AS_OF,
        init_cash=100_000.0,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )

    base = build_self_baseline_comparison(base_snapshot, series, records)
    extended = build_self_baseline_comparison(extended_snapshot, series, records)

    assert self_baseline_json_bytes(extended) == self_baseline_json_bytes(base)


def test_lifetime_uses_only_complete_available_historical_points():
    snapshot, series, records = _fixture(
        (
            (pd.Timestamp("2024-01-01"), 0.1, "complete"),
            (pd.Timestamp("2025-01-01"), None, "insufficient_evidence"),
            (pd.Timestamp("2026-01-01"), 0.3, "complete"),
            (pd.Timestamp("2026-03-01"), 0.5, "complete"),
        ),
        current=0.6,
    )

    result = build_self_baseline_comparison(snapshot, series, records, window="lifetime")

    assert result.status == "complete"
    assert result.valid_n == 3
    assert result.observation_start == pd.Timestamp("2024-01-01")
    assert result.observation_end == pd.Timestamp("2026-03-01")
    assert result.median == pytest.approx(0.3)


def test_insufficient_observations_are_excluded_and_below_minimum_abstains():
    snapshot, series, records = _fixture(
        (
            (pd.Timestamp("2026-01-01"), 0.2, "complete"),
            (pd.Timestamp("2026-02-01"), None, "insufficient_evidence"),
            (pd.Timestamp("2026-03-01"), 0.4, "complete"),
        ),
        current=0.6,
    )

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.status == "insufficient_self_history"
    assert result.valid_n == 2
    assert "3 are required" in result.insufficient_reason
    assert result.median is None
    assert result.self_historical_percentile is None
    assert result.comparison_band is None


def test_turnover_reuses_daily_observations_with_metric_specific_minimum():
    history = tuple(
        (pd.Timestamp(f"2026-0{month}-01"), value, "complete")
        for month, value in enumerate((0.01, 0.02, 0.03, 0.04, 0.05), start=1)
    )
    snapshot, series, records = _fixture(
        history,
        current=0.06,
        metric_id="mean_daily_turnover",
        method_id=TURNOVER_METHOD,
    )

    result = build_self_baseline_comparison(snapshot, series, records)

    assert result.status == "complete"
    assert result.valid_n == 5
    assert result.observation_kind == "window_statistic"
    assert result.median == pytest.approx(0.03)


def test_unregistered_event_metric_is_unsupported_without_statistics():
    snapshot, _, _ = _hand_fixture()
    source = _record(
        timestamp=pd.Timestamp("2026-01-01"),
        value=0.5,
        metric_id="loss_averaging_event_rate",
        method_id="loss_state_add_v1",
    )
    series = HistoricalMetricSeries(
        subject_id=SUBJECT,
        metric_id="loss_averaging_event_rate",
        method_id="loss_state_add_v1",
        method_version="1",
        points=(
            HistoricalMetricPoint(
                as_of=pd.Timestamp("2026-01-01"),
                value=0.5,
                evidence_status="complete",
                source_evidence_id=source.evidence_id,
                observation_count=1,
            ),
        ),
        data_tier="synthetic",
        limitations=("Synthetic fixture only",),
    )

    result = build_self_baseline_comparison(snapshot, series, (source,))

    assert result.status == "unsupported_for_self_baseline"
    assert result.observation_kind == "unknown"
    assert result.median is None
    assert result.comparison_band is None


def test_wrong_method_cannot_silently_change_observation_unit():
    snapshot, series, records = _hand_fixture()
    malformed = dataclasses.replace(series, method_id=TURNOVER_METHOD)

    with pytest.raises(ValueError, match="method binding"):
        build_self_baseline_comparison(snapshot, malformed, records)


def test_cross_subject_and_missing_source_evidence_fail_closed():
    snapshot, series, records = _hand_fixture()

    with pytest.raises(ValueError, match="subject_id does not match"):
        build_self_baseline_comparison(
            snapshot,
            dataclasses.replace(series, subject_id=OTHER_SUBJECT),
            records,
        )
    with pytest.raises(ValueError, match="source Evidence is missing"):
        build_self_baseline_comparison(snapshot, series, records[1:])

    foreign_source = dataclasses.replace(records[0], subject_id=OTHER_SUBJECT)
    with pytest.raises(ValueError, match="belong to the Twin subject"):
        build_self_baseline_comparison(snapshot, series, (foreign_source, *records[1:]))


def test_malformed_series_status_fails_closed():
    snapshot, series, records = _hand_fixture()
    malformed_first = dataclasses.replace(
        series.points[0],
        evidence_status="insufficient_evidence",
        value=None,
    )
    malformed = dataclasses.replace(series, points=(malformed_first, *series.points[1:]))

    with pytest.raises(ValueError, match="status does not match"):
        build_self_baseline_comparison(snapshot, malformed, records)


def test_input_order_is_canonical_and_correction_version_changes_identity():
    snapshot, series, records = _hand_fixture()
    first = build_self_baseline_comparison(snapshot, series, records)
    reordered = build_self_baseline_comparison(snapshot, series, tuple(reversed(records)))
    assert self_baseline_json_bytes(reordered) == self_baseline_json_bytes(first)

    corrected_snapshot, corrected_series, corrected_records = _fixture(
        (
            (pd.Timestamp("2026-01-01"), 0.2, "complete"),
            (pd.Timestamp("2026-02-01"), 0.3, "complete"),
            (pd.Timestamp("2026-03-01"), 0.4, "complete"),
            (pd.Timestamp("2026-04-01"), 0.5, "complete"),
        ),
        current=0.6,
        data_version="v2-correction",
    )
    corrected = build_self_baseline_comparison(
        corrected_snapshot,
        corrected_series,
        corrected_records,
    )

    assert corrected.median == first.median
    assert corrected.comparison_id != first.comparison_id


def test_summary_uses_rolling_12m_as_default_and_is_deterministic():
    hhi_snapshot, hhi_series, hhi_records = _hand_fixture()
    turnover_history = tuple(
        (pd.Timestamp(f"2026-0{month}-05"), value, "complete")
        for month, value in enumerate((0.01, 0.02, 0.03, 0.04, 0.05), start=1)
    )
    _, turnover_series, turnover_records = _fixture(
        turnover_history,
        current=0.06,
        metric_id="mean_daily_turnover",
        method_id=TURNOVER_METHOD,
    )
    snapshot = build_twin_snapshot(
        (*hhi_records, *turnover_records),
        (hhi_series, turnover_series),
        subject_id=SUBJECT,
        snapshot_at=AS_OF,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )

    first = build_self_baseline_summary(
        snapshot,
        (turnover_series, hhi_series),
        (*turnover_records, *hhi_records),
    )
    second = build_self_baseline_summary(
        snapshot,
        (hhi_series, turnover_series),
        (*hhi_records, *turnover_records),
    )

    assert first.default_window == DEFAULT_WINDOW == "rolling_12m"
    assert first.available_metric_count == 2
    assert first.insufficient_metric_count == 0
    assert [item.metric_id for item in first.metrics] == sorted(item.metric_id for item in first.metrics)
    assert self_baseline_json_bytes(second) == self_baseline_json_bytes(first)
