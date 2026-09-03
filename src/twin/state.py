"""Deterministic point-in-time views over registered evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.evidence.contracts import DataTier, EvidenceRecord, EvidenceStatus
from src.history.metric_series import HistoricalMetricPoint, HistoricalMetricSeries


DECISION_METRICS = (
    "selection_episode_asset_return",
    "sizing_equal_weight_comparison",
    "exit_timing_post_exit_asset_return",
    "recorded_trading_friction_comparison",
)
BEHAVIOR_METRICS = (
    "portfolio_concentration_hhi",
    "mean_daily_turnover",
    "disposition_effect",
    "loss_averaging_event_rate",
)
HISTORICAL_METRICS = (
    "portfolio_concentration_hhi",
    "mean_daily_turnover",
)


@dataclass(frozen=True, slots=True)
class TwinEvidenceRef:
    evidence_id: str
    metric_id: str
    evidence_status: EvidenceStatus
    available_at: pd.Timestamp


@dataclass(frozen=True, slots=True)
class TwinMetricState:
    metric_id: str
    as_of: pd.Timestamp
    value: float | None
    evidence_status: EvidenceStatus
    source_evidence_id: str
    observation_count: int | None


@dataclass(frozen=True, slots=True)
class TwinDataQualitySummary:
    expected_evidence_count: int
    referenced_evidence_count: int
    complete_evidence_count: int
    insufficient_evidence_count: int
    available_behavior_metric_count: int
    missing_behavior_metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TwinSnapshot:
    """A rebuildable point-in-time product view, not a financial calculation."""

    subject_id: str
    snapshot_at: pd.Timestamp
    decision_evidence_refs: tuple[TwinEvidenceRef, ...]
    behavior_evidence_refs: tuple[TwinEvidenceRef, ...]
    behavior_state: tuple[TwinMetricState, ...]
    data_quality_summary: TwinDataQualitySummary
    data_tier: DataTier
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TwinMetricComparison:
    metric_id: str
    method_id: str
    method_version: str
    reference_date: pd.Timestamp | None
    current_date: pd.Timestamp | None
    past_value: float | None
    current_value: float | None
    absolute_change: float | None
    relative_change: float | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    reference_evidence_id: str | None
    current_evidence_id: str | None


def _required_timestamp(value: object, field_name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError(f"{field_name} cannot be NaT")
    return timestamp


def evidence_available_at(record: EvidenceRecord) -> pd.Timestamp | None:
    """Return when every dated input represented by an EvidenceRecord was available."""

    candidates = [record.as_of, record.observation_end]
    candidates.extend(item.as_of for item in record.provenance)
    dated = [pd.Timestamp(item) for item in candidates if item is not None]
    return max(dated) if dated else None


def latest_twin_snapshot_at(
    records: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
    historical_series: tuple[HistoricalMetricSeries, ...] | list[HistoricalMetricSeries],
) -> pd.Timestamp:
    dates = [
        available
        for record in records
        if (available := evidence_available_at(record)) is not None
    ]
    dates.extend(point.as_of for series in historical_series for point in series.points)
    if not dates:
        raise ValueError("No dated evidence or historical points are available")
    return max(dates)


def _latest_records(
    records: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
    *,
    snapshot_at: pd.Timestamp,
) -> dict[str, tuple[EvidenceRecord, pd.Timestamp]]:
    eligible: dict[str, tuple[EvidenceRecord, pd.Timestamp]] = {}
    for record in records:
        available_at = evidence_available_at(record)
        if available_at is None or available_at > snapshot_at:
            continue
        current = eligible.get(record.metric_id)
        candidate_key = (available_at, record.evidence_id)
        current_key = (current[1], current[0].evidence_id) if current else None
        if current_key is None or candidate_key > current_key:
            eligible[record.metric_id] = (record, available_at)
    return eligible


def _reference(
    record: EvidenceRecord,
    available_at: pd.Timestamp,
) -> TwinEvidenceRef:
    return TwinEvidenceRef(
        evidence_id=record.evidence_id,
        metric_id=record.metric_id,
        evidence_status=record.evidence_status,
        available_at=available_at,
    )


def _latest_point(
    series: HistoricalMetricSeries,
    snapshot_at: pd.Timestamp,
) -> HistoricalMetricPoint | None:
    eligible = [point for point in series.points if point.as_of <= snapshot_at]
    return eligible[-1] if eligible else None


def build_twin_snapshot(
    records: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
    historical_series: tuple[HistoricalMetricSeries, ...] | list[HistoricalMetricSeries],
    *,
    subject_id: str,
    snapshot_at: pd.Timestamp,
    data_tier: DataTier,
) -> TwinSnapshot:
    """Build a snapshot without admitting evidence or history after ``snapshot_at``."""

    snapshot_at = _required_timestamp(snapshot_at, "snapshot_at")
    series_by_metric = {series.metric_id: series for series in historical_series}
    latest_records = _latest_records(records, snapshot_at=snapshot_at)

    decision_refs = tuple(
        _reference(*latest_records[metric_id])
        for metric_id in DECISION_METRICS
        if metric_id in latest_records
    )
    behavior_refs = tuple(
        _reference(*latest_records[metric_id])
        for metric_id in BEHAVIOR_METRICS
        if metric_id in latest_records
    )

    behavior_state: list[TwinMetricState] = []
    for metric_id in HISTORICAL_METRICS:
        series = series_by_metric.get(metric_id)
        point = _latest_point(series, snapshot_at) if series else None
        if point is not None:
            behavior_state.append(
                TwinMetricState(
                    metric_id=metric_id,
                    as_of=point.as_of,
                    value=point.value,
                    evidence_status=point.evidence_status,
                    source_evidence_id=point.source_evidence_id,
                    observation_count=point.observation_count,
                )
            )
    for metric_id in BEHAVIOR_METRICS[2:]:
        item = latest_records.get(metric_id)
        if item is None:
            continue
        record, available_at = item
        value = float(record.value) if isinstance(record.value, (int, float)) else None
        behavior_state.append(
            TwinMetricState(
                metric_id=metric_id,
                as_of=available_at,
                value=value,
                evidence_status=record.evidence_status,
                source_evidence_id=record.evidence_id,
                observation_count=record.observation_count,
            )
        )

    refs = (*decision_refs, *behavior_refs)
    limitations = tuple(
        sorted(
            {
                limitation
                for reference in refs
                for limitation in latest_records[reference.metric_id][0].limitations
            }
            | {
                limitation
                for series in historical_series
                if _latest_point(series, snapshot_at) is not None
                for limitation in series.limitations
            }
        )
    )
    missing_behavior = tuple(
        metric_id
        for metric_id in BEHAVIOR_METRICS
        if metric_id not in {item.metric_id for item in behavior_state}
    )
    quality = TwinDataQualitySummary(
        expected_evidence_count=len(DECISION_METRICS) + len(BEHAVIOR_METRICS),
        referenced_evidence_count=len(refs),
        complete_evidence_count=sum(
            reference.evidence_status == "complete" for reference in refs
        ),
        insufficient_evidence_count=sum(
            reference.evidence_status == "insufficient_evidence" for reference in refs
        ),
        available_behavior_metric_count=len(behavior_state),
        missing_behavior_metrics=missing_behavior,
    )
    return TwinSnapshot(
        subject_id=subject_id,
        snapshot_at=snapshot_at,
        decision_evidence_refs=decision_refs,
        behavior_evidence_refs=behavior_refs,
        behavior_state=tuple(behavior_state),
        data_quality_summary=quality,
        data_tier=data_tier,
        limitations=limitations,
    )


def build_historical_twin_snapshots(
    records: tuple[EvidenceRecord, ...] | list[EvidenceRecord],
    historical_series: tuple[HistoricalMetricSeries, ...] | list[HistoricalMetricSeries],
    *,
    subject_id: str,
    snapshot_at: pd.Timestamp,
    data_tier: DataTier,
) -> tuple[TwinSnapshot, ...]:
    """Rebuild Twin snapshots only at real registered historical dates."""

    cutoff = _required_timestamp(snapshot_at, "snapshot_at")
    dates = sorted(
        {
            point.as_of
            for series in historical_series
            for point in series.points
            if point.as_of <= cutoff
        }
    )
    return tuple(
        build_twin_snapshot(
            records,
            historical_series,
            subject_id=subject_id,
            snapshot_at=date,
            data_tier=data_tier,
        )
        for date in dates
    )


def build_twin_metric_comparison(
    series: HistoricalMetricSeries,
) -> TwinMetricComparison:
    """Compare the earliest and latest valid registered points in one series."""

    valid = [
        point
        for point in series.points
        if point.value is not None
        and point.evidence_status != "insufficient_evidence"
    ]
    if not valid:
        return TwinMetricComparison(
            metric_id=series.metric_id,
            method_id=series.method_id,
            method_version=series.method_version,
            reference_date=None,
            current_date=None,
            past_value=None,
            current_value=None,
            absolute_change=None,
            relative_change=None,
            evidence_status="insufficient_evidence",
            evidence_reason="No valid historical evidence points are available",
            reference_evidence_id=None,
            current_evidence_id=None,
        )
    current = valid[-1]
    if len(valid) == 1:
        return TwinMetricComparison(
            metric_id=series.metric_id,
            method_id=series.method_id,
            method_version=series.method_version,
            reference_date=None,
            current_date=current.as_of,
            past_value=None,
            current_value=current.value,
            absolute_change=None,
            relative_change=None,
            evidence_status="insufficient_evidence",
            evidence_reason="At least two valid historical evidence points are required",
            reference_evidence_id=None,
            current_evidence_id=current.source_evidence_id,
        )

    reference = valid[0]
    absolute_change = current.value - reference.value
    relative_change = (
        absolute_change / reference.value if reference.value != 0 else None
    )
    if not math.isfinite(absolute_change):  # pragma: no cover - point invariant
        raise ValueError("absolute_change must be finite")
    return TwinMetricComparison(
        metric_id=series.metric_id,
        method_id=series.method_id,
        method_version=series.method_version,
        reference_date=reference.as_of,
        current_date=current.as_of,
        past_value=reference.value,
        current_value=current.value,
        absolute_change=absolute_change,
        relative_change=relative_change,
        evidence_status="complete",
        evidence_reason=(
            "Relative change is unavailable because the reference value is zero"
            if reference.value == 0
            else None
        ),
        reference_evidence_id=reference.source_evidence_id,
        current_evidence_id=current.source_evidence_id,
    )
