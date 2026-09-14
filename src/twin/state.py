"""Deterministic point-in-time projection over replay, Episodes, and Evidence.

Twin is a rebuildable read model. It references financial facts produced by
the existing deterministic core and never implements portfolio accounting or a
financial metric formula.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import pandas as pd

from src.evidence.contracts import (
    DataTier,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceStatus,
    canonical_json_bytes,
)
from src.history.metric_series import HistoricalMetricPoint, HistoricalMetricSeries

if TYPE_CHECKING:
    from src.episodes.position_episode import PositionEpisodeLifecycle


TWIN_SNAPSHOT_SCHEMA_VERSION: Final = "1"
TWIN_PROJECTION_METHOD_ID: Final = "personal_twin_point_in_time_projection_v1"
TWIN_PROJECTION_METHOD_VERSION: Final = "1"
TWIN_SNAPSHOT_ID_PREFIX: Final = "tw_"
TWIN_LIMITATIONS: Final[tuple[str, ...]] = (
    "Personal Twin is a derived point-in-time read model, not a financial ledger.",
    "Daily market data cannot prove that a final close was available intraday.",
    "Self baseline, peer context, notable changes, and intervention history are unavailable in v1.",
)

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

PortfolioStateStatus = Literal["available", "not_started", "unavailable"]


@dataclass(frozen=True, slots=True)
class TwinInputVersionRef:
    """Stable reference to one canonical input visible at ``snapshot_at``."""

    source_type: str
    source_name: str
    data_version: str
    as_of: pd.Timestamp | None
    price_type: str | None
    is_synthetic: bool
    source_id: str | None = None
    instrument: str | None = None
    benchmark_id: str | None = None


@dataclass(frozen=True, slots=True)
class TwinEvidenceRef:
    """Resolvable Evidence reference with its method and availability boundary."""

    evidence_id: str
    metric_id: str
    evidence_status: EvidenceStatus
    available_at: pd.Timestamp
    evidence_kind: str = "unspecified"
    method_id: str = "unspecified"
    method_version: str = "unspecified"
    evidence_reason: str | None = None
    calculation_code_version: str = "unspecified"
    provenance: tuple[EvidenceProvenance, ...] = ()


@dataclass(frozen=True, slots=True)
class TwinMetricState:
    metric_id: str
    as_of: pd.Timestamp
    value: float | None
    evidence_status: EvidenceStatus
    source_evidence_id: str
    observation_count: int | None


@dataclass(frozen=True, slots=True)
class TwinPositionState:
    """Position projection copied from a replay-backed Position Episode state."""

    state_ref: str
    account_id: str
    instrument_id: str
    quantity: float
    average_cost: float | None
    valuation_at: pd.Timestamp | None
    valuation_price: float | None
    market_value: float | None
    replay_method_id: str


@dataclass(frozen=True, slots=True)
class TwinPortfolioState:
    as_of: pd.Timestamp
    status: PortfolioStateStatus
    reason: str | None
    replay_method_id: str | None
    positions: tuple[TwinPositionState, ...]


@dataclass(frozen=True, slots=True)
class TwinEpisodeRef:
    episode_id: str
    status: Literal["open", "closed"]
    account_id: str
    instrument_id: str
    opened_at: pd.Timestamp
    closed_at: pd.Timestamp | None
    opening_execution_id: str
    closing_execution_id: str | None
    execution_refs: tuple[str, ...]
    decision_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    current_position_state_ref: str | None


@dataclass(frozen=True, slots=True)
class TwinEpisodeRefs:
    open: tuple[TwinEpisodeRef, ...]
    closed: tuple[TwinEpisodeRef, ...]


@dataclass(frozen=True, slots=True)
class TwinEvidenceSummary:
    total: int
    complete: int
    partial: int
    insufficient: int
    experimental: int
    unavailable_metric_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TwinDataQualitySummary:
    expected_evidence_count: int
    referenced_evidence_count: int
    complete_evidence_count: int
    insufficient_evidence_count: int
    available_behavior_metric_count: int
    missing_behavior_metrics: tuple[str, ...]
    partial_evidence_count: int = 0
    experimental_evidence_count: int = 0
    missing_evidence_metrics: tuple[str, ...] = ()
    portfolio_state_status: PortfolioStateStatus = "unavailable"
    open_episode_count: int = 0
    closed_episode_count: int = 0
    issue_count: int = 0
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TwinSnapshot:
    """Versioned, deterministic point-in-time product view."""

    snapshot_id: str
    subject_id: str
    snapshot_at: pd.Timestamp
    schema_version: str
    projection_method_id: str
    projection_method_version: str
    calculation_code_version: str
    input_version_refs: tuple[TwinInputVersionRef, ...]
    portfolio_state: TwinPortfolioState
    episode_refs: TwinEpisodeRefs
    decision_event_refs: tuple[str, ...]
    decision_evidence_refs: tuple[TwinEvidenceRef, ...]
    behavior_evidence_refs: tuple[TwinEvidenceRef, ...]
    behavior_state: tuple[TwinMetricState, ...]
    evidence_summary: TwinEvidenceSummary
    data_quality_summary: TwinDataQualitySummary
    self_baseline_refs: tuple[str, ...]
    peer_context_refs: tuple[str, ...]
    notable_change_refs: tuple[str, ...]
    intervention_history_ref: str | None
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


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def evidence_available_at(record: EvidenceRecord) -> pd.Timestamp | None:
    """Return when all dated inputs represented by an EvidenceRecord were available."""

    candidates = [record.as_of, record.observation_end]
    candidates.extend(item.as_of for item in record.provenance)
    dated = [pd.Timestamp(item) for item in candidates if item is not None]
    return max(dated) if dated else None


def latest_twin_snapshot_at(
    records: Sequence[EvidenceRecord],
    historical_series: Sequence[HistoricalMetricSeries],
    *,
    subject_id: str | None = None,
) -> pd.Timestamp:
    dates = [
        available
        for record in records
        if subject_id is None or record.subject_id == subject_id
        if (available := evidence_available_at(record)) is not None
    ]
    dates.extend(
        point.as_of
        for series in historical_series
        if subject_id is None or series.subject_id == subject_id
        for point in series.points
    )
    if not dates:
        raise ValueError("No dated evidence or historical points are available")
    return max(dates)


def _latest_records(
    records: Sequence[EvidenceRecord],
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


def _provenance_sort_key(item: EvidenceProvenance) -> tuple[str, ...]:
    return (
        item.source_type,
        item.source_name,
        item.data_version,
        item.as_of.isoformat() if item.as_of is not None else "",
        item.price_type or "",
        item.source_id or "",
        item.instrument or "",
        item.benchmark_id or "",
    )


def _reference(record: EvidenceRecord, available_at: pd.Timestamp) -> TwinEvidenceRef:
    return TwinEvidenceRef(
        evidence_id=record.evidence_id,
        metric_id=record.metric_id,
        evidence_status=record.evidence_status,
        available_at=available_at,
        evidence_kind=record.evidence_kind,
        method_id=record.method_id,
        method_version=record.method_version,
        evidence_reason=record.evidence_reason,
        calculation_code_version=record.calculation_code_version,
        provenance=tuple(sorted(record.provenance, key=_provenance_sort_key)),
    )


def _latest_point(
    series: HistoricalMetricSeries,
    snapshot_at: pd.Timestamp,
    evidence_by_id: Mapping[str, EvidenceRecord],
) -> HistoricalMetricPoint | None:
    eligible: list[HistoricalMetricPoint] = []
    for point in series.points:
        if point.as_of > snapshot_at:
            continue
        source = evidence_by_id.get(point.source_evidence_id)
        source_available = evidence_available_at(source) if source is not None else None
        if source is not None and (source_available is None or source_available > snapshot_at):
            continue
        eligible.append(point)
    return eligible[-1] if eligible else None


def _input_ref_from_provenance(item: EvidenceProvenance) -> TwinInputVersionRef:
    return TwinInputVersionRef(
        source_type=item.source_type,
        source_name=item.source_name,
        data_version=item.data_version,
        as_of=item.as_of,
        price_type=item.price_type,
        is_synthetic=item.is_synthetic,
        source_id=item.source_id,
        instrument=item.instrument,
        benchmark_id=item.benchmark_id,
    )


def _input_ref_key(item: TwinInputVersionRef) -> tuple[str, ...]:
    return (
        item.source_type,
        item.source_name,
        item.data_version,
        item.as_of.isoformat() if item.as_of is not None else "",
        item.price_type or "",
        "1" if item.is_synthetic else "0",
        item.source_id or "",
        item.instrument or "",
        item.benchmark_id or "",
    )


def _validate_lifecycle(
    lifecycle: PositionEpisodeLifecycle,
    *,
    subject_id: str,
    snapshot_at: pd.Timestamp,
    data_tier: DataTier,
    evidence_by_id: Mapping[str, EvidenceRecord],
) -> None:
    if lifecycle.subject_id != subject_id:
        raise ValueError("Position Episode lifecycle subject_id does not match Twin")
    if lifecycle.as_of != snapshot_at:
        raise ValueError("Position Episode lifecycle must be built exactly at snapshot_at")
    if lifecycle.data_tier != data_tier:
        raise ValueError("Position Episode lifecycle data_tier does not match Twin")
    if any(item.opened_at > snapshot_at for item in lifecycle.episodes):
        raise ValueError("Position Episode lifecycle contains a future open")
    if any(
        item.closed_at is not None and item.closed_at > snapshot_at
        for item in lifecycle.episodes
    ):
        raise ValueError("Position Episode lifecycle contains a future close")
    if any(item.occurred_at > snapshot_at for item in lifecycle.decisions):
        raise ValueError("Position Episode lifecycle contains a future Decision Event")
    if any(
        item.as_of > snapshot_at
        or (item.valuation_at is not None and item.valuation_at > snapshot_at)
        for item in lifecycle.states
    ):
        raise ValueError("Position Episode lifecycle contains a future replay state")
    if any(item.as_of > snapshot_at for item in lifecycle.snapshots):
        raise ValueError("Position Episode lifecycle contains a future Episode snapshot")
    if any(item.available_at > snapshot_at for item in lifecycle.evidence_references):
        raise ValueError("Position Episode lifecycle contains future Evidence")
    lifecycle_evidence_ids = {
        item.evidence_id for item in lifecycle.evidence_references
    }
    unresolved = sorted(lifecycle_evidence_ids.difference(evidence_by_id))
    if unresolved:
        raise ValueError(
            "Position Episode Evidence must resolve to Evidence owned by the Twin subject: "
            f"{unresolved}"
        )


def _lifecycle_projection(
    lifecycle: PositionEpisodeLifecycle | None,
    *,
    snapshot_at: pd.Timestamp,
    missing_status: PortfolioStateStatus,
) -> tuple[TwinPortfolioState, TwinEpisodeRefs, tuple[str, ...]]:
    if lifecycle is None:
        reason = (
            "No execution had occurred at snapshot_at"
            if missing_status == "not_started"
            else "No replay-backed Position Episode lifecycle was supplied"
        )
        return (
            TwinPortfolioState(snapshot_at, missing_status, reason, None, ()),
            TwinEpisodeRefs(open=(), closed=()),
            (),
        )

    state_by_id = {item.state_id: item for item in lifecycle.states}
    snapshot_by_episode = {item.episode_id: item for item in lifecycle.snapshots}
    projected: list[TwinEpisodeRef] = []
    positions: list[TwinPositionState] = []
    for episode in lifecycle.episodes:
        episode_snapshot = snapshot_by_episode.get(episode.episode_id)
        state_ref = episode_snapshot.position_state_ref if episode_snapshot else None
        if episode.status == "open":
            if state_ref is None or state_ref not in state_by_id:
                raise ValueError("Open Position Episode has no replay-backed as-of state")
            state = state_by_id[state_ref]
            positions.append(
                TwinPositionState(
                    state_ref=state.state_id,
                    account_id=state.account_id,
                    instrument_id=state.instrument_id,
                    quantity=state.quantity,
                    average_cost=state.average_cost,
                    valuation_at=state.valuation_at,
                    valuation_price=state.valuation_price,
                    market_value=state.market_value,
                    replay_method_id=state.replay_method_id,
                )
            )
        elif state_ref is not None:
            raise ValueError("Closed Position Episode cannot have a current position state")
        projected.append(
            TwinEpisodeRef(
                episode_id=episode.episode_id,
                status=episode.status,
                account_id=episode.account_id,
                instrument_id=episode.instrument_id,
                opened_at=episode.opened_at,
                closed_at=episode.closed_at,
                opening_execution_id=episode.opening_execution_id,
                closing_execution_id=episode.closing_execution_id,
                execution_refs=episode.execution_refs,
                decision_refs=episode.decision_refs,
                evidence_refs=episode.evidence_refs,
                current_position_state_ref=state_ref,
            )
        )
    projected.sort(key=lambda item: (item.opened_at, item.account_id, item.episode_id))
    positions.sort(key=lambda item: (item.account_id, item.instrument_id, item.state_ref))
    open_refs = tuple(item for item in projected if item.status == "open")
    closed_refs = tuple(item for item in projected if item.status == "closed")
    replay_methods = {item.replay_method_id for item in positions}
    replay_methods.update(item.replay_method_id for item in lifecycle.episodes)
    replay_method = next(iter(replay_methods)) if len(replay_methods) == 1 else None
    return (
        TwinPortfolioState(snapshot_at, "available", None, replay_method, tuple(positions)),
        TwinEpisodeRefs(open=open_refs, closed=closed_refs),
        tuple(item.decision_id for item in lifecycle.decisions),
    )


def _snapshot_json_value(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _snapshot_json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _snapshot_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_snapshot_json_value(item) for item in value]
    return value


def twin_snapshot_to_dict(snapshot: TwinSnapshot) -> dict[str, object]:
    """Serialize a TwinSnapshot without relying on Python object repr."""

    value = _snapshot_json_value(snapshot)
    if not isinstance(value, dict):  # pragma: no cover - defensive invariant
        raise TypeError("TwinSnapshot serialization must produce an object")
    return value


def twin_snapshot_json_bytes(snapshot: TwinSnapshot) -> bytes:
    """Return canonical deterministic bytes for persistence or transport."""

    return canonical_json_bytes(twin_snapshot_to_dict(snapshot))


def _snapshot_id(payload: Mapping[str, object]) -> str:
    return TWIN_SNAPSHOT_ID_PREFIX + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_twin_snapshot(
    records: Sequence[EvidenceRecord],
    historical_series: Sequence[HistoricalMetricSeries],
    *,
    subject_id: str,
    snapshot_at: pd.Timestamp,
    data_tier: DataTier,
    calculation_code_version: str = "personal-twin-core-v1",
    position_lifecycle: PositionEpisodeLifecycle | None = None,
    input_version_refs: Sequence[TwinInputVersionRef] = (),
    portfolio_state_status_if_missing: PortfolioStateStatus = "unavailable",
    data_quality_issues: Sequence[str] = (),
) -> TwinSnapshot:
    """Project facts, Episode state, and Evidence available at ``snapshot_at``."""

    subject = _required_text(subject_id, "subject_id")
    code_version = _required_text(calculation_code_version, "calculation_code_version")
    cutoff = _required_timestamp(snapshot_at, "snapshot_at")
    if data_tier not in {"synthetic", "demo", "authorized_beta", "production"}:
        raise ValueError("data_tier is unsupported")
    if portfolio_state_status_if_missing not in {"not_started", "unavailable"}:
        raise ValueError("missing portfolio state must be not_started or unavailable")
    mismatched_subjects = sorted(
        {record.subject_id for record in records if record.subject_id != subject}
    )
    if mismatched_subjects:
        raise ValueError(
            "Every EvidenceRecord must be owned by the Twin subject; "
            f"received subject_id values {mismatched_subjects}"
        )
    evidence_by_id = {record.evidence_id: record for record in records}
    if position_lifecycle is not None:
        _validate_lifecycle(
            position_lifecycle,
            subject_id=subject,
            snapshot_at=cutoff,
            data_tier=data_tier,
            evidence_by_id=evidence_by_id,
        )

    portfolio_state, episode_refs, decision_refs = _lifecycle_projection(
        position_lifecycle,
        snapshot_at=cutoff,
        missing_status=portfolio_state_status_if_missing,
    )
    latest_records = _latest_records(
        records,
        snapshot_at=cutoff,
    )
    series_by_metric = {
        series.metric_id: series
        for series in historical_series
        if series.subject_id == subject and series.data_tier == data_tier
    }

    decision_evidence_refs = tuple(
        _reference(*latest_records[metric_id])
        for metric_id in DECISION_METRICS
        if metric_id in latest_records
    )
    behavior_evidence_refs = tuple(
        _reference(*latest_records[metric_id])
        for metric_id in BEHAVIOR_METRICS
        if metric_id in latest_records
    )

    behavior_state: list[TwinMetricState] = []
    selected_points: dict[str, HistoricalMetricPoint] = {}
    for metric_id in HISTORICAL_METRICS:
        series = series_by_metric.get(metric_id)
        point = _latest_point(series, cutoff, evidence_by_id) if series else None
        if point is None:
            continue
        selected_points[metric_id] = point
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
        value = (
            float(record.value)
            if isinstance(record.value, (int, float)) and not isinstance(record.value, bool)
            else None
        )
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

    evidence_refs = (*decision_evidence_refs, *behavior_evidence_refs)
    evidence_records = [latest_records[ref.metric_id][0] for ref in evidence_refs]
    limitations = {
        *TWIN_LIMITATIONS,
        *(position_lifecycle.limitations if position_lifecycle is not None else ()),
        *(limitation for record in evidence_records for limitation in record.limitations),
        *(
            limitation
            for metric_id, series in series_by_metric.items()
            if metric_id in selected_points
            for limitation in series.limitations
        ),
    }
    normalized_input_refs = list(input_version_refs)
    for record in evidence_records:
        normalized_input_refs.extend(_input_ref_from_provenance(item) for item in record.provenance)
    if position_lifecycle is not None:
        for episode in position_lifecycle.episodes:
            normalized_input_refs.extend(
                _input_ref_from_provenance(item) for item in episode.provenance
            )
    deduplicated_inputs = {
        _input_ref_key(item): item
        for item in normalized_input_refs
        if item.as_of is None or item.as_of <= cutoff
    }
    input_refs = tuple(deduplicated_inputs[key] for key in sorted(deduplicated_inputs))

    missing_behavior = tuple(
        metric_id
        for metric_id in BEHAVIOR_METRICS
        if metric_id not in {item.metric_id for item in behavior_state}
    )
    available_metric_ids = {ref.metric_id for ref in evidence_refs}
    missing_evidence = tuple(
        metric_id
        for metric_id in (*DECISION_METRICS, *BEHAVIOR_METRICS)
        if metric_id not in available_metric_ids
    )
    status_counts = {
        status: sum(ref.evidence_status == status for ref in evidence_refs)
        for status in ("complete", "partial", "insufficient_evidence", "experimental")
    }
    evidence_summary = TwinEvidenceSummary(
        total=len(evidence_refs),
        complete=status_counts["complete"],
        partial=status_counts["partial"],
        insufficient=status_counts["insufficient_evidence"],
        experimental=status_counts["experimental"],
        unavailable_metric_ids=missing_evidence,
    )
    issues = tuple(
        sorted({_required_text(item, "data_quality_issue") for item in data_quality_issues})
    )
    quality = TwinDataQualitySummary(
        expected_evidence_count=len(DECISION_METRICS) + len(BEHAVIOR_METRICS),
        referenced_evidence_count=len(evidence_refs),
        complete_evidence_count=status_counts["complete"],
        insufficient_evidence_count=status_counts["insufficient_evidence"],
        available_behavior_metric_count=len(behavior_state),
        missing_behavior_metrics=missing_behavior,
        partial_evidence_count=status_counts["partial"],
        experimental_evidence_count=status_counts["experimental"],
        missing_evidence_metrics=missing_evidence,
        portfolio_state_status=portfolio_state.status,
        open_episode_count=len(episode_refs.open),
        closed_episode_count=len(episode_refs.closed),
        issue_count=len(issues),
        issues=issues,
    )
    payload: dict[str, object] = {
        "subject_id": subject,
        "snapshot_at": cutoff.isoformat(),
        "schema_version": TWIN_SNAPSHOT_SCHEMA_VERSION,
        "projection_method_id": TWIN_PROJECTION_METHOD_ID,
        "projection_method_version": TWIN_PROJECTION_METHOD_VERSION,
        "calculation_code_version": code_version,
        "input_version_refs": _snapshot_json_value(input_refs),
        "portfolio_state": _snapshot_json_value(portfolio_state),
        "episode_refs": _snapshot_json_value(episode_refs),
        "decision_event_refs": list(decision_refs),
        "decision_evidence_refs": _snapshot_json_value(decision_evidence_refs),
        "behavior_evidence_refs": _snapshot_json_value(behavior_evidence_refs),
        "behavior_state": _snapshot_json_value(tuple(behavior_state)),
        "evidence_summary": _snapshot_json_value(evidence_summary),
        "data_quality_summary": _snapshot_json_value(quality),
        "self_baseline_refs": [],
        "peer_context_refs": [],
        "notable_change_refs": [],
        "intervention_history_ref": None,
        "data_tier": data_tier,
        "limitations": sorted(limitations),
    }
    return TwinSnapshot(
        snapshot_id=_snapshot_id(payload),
        subject_id=subject,
        snapshot_at=cutoff,
        schema_version=TWIN_SNAPSHOT_SCHEMA_VERSION,
        projection_method_id=TWIN_PROJECTION_METHOD_ID,
        projection_method_version=TWIN_PROJECTION_METHOD_VERSION,
        calculation_code_version=code_version,
        input_version_refs=input_refs,
        portfolio_state=portfolio_state,
        episode_refs=episode_refs,
        decision_event_refs=decision_refs,
        decision_evidence_refs=decision_evidence_refs,
        behavior_evidence_refs=behavior_evidence_refs,
        behavior_state=tuple(behavior_state),
        evidence_summary=evidence_summary,
        data_quality_summary=quality,
        self_baseline_refs=(),
        peer_context_refs=(),
        notable_change_refs=(),
        intervention_history_ref=None,
        data_tier=data_tier,
        limitations=tuple(sorted(limitations)),
    )


def _normalized_execution_input_ref(
    executions: pd.DataFrame,
    *,
    snapshot_at: pd.Timestamp,
    subject_id: str,
    account_id: str | None,
    init_cash: float | Mapping[str, float],
    data_tier: DataTier,
) -> TwinInputVersionRef | None:
    if not isinstance(executions, pd.DataFrame) or executions.empty:
        return None
    if "event_time" not in executions:
        raise ValueError("executions.event_time is required")
    times = pd.to_datetime(executions["event_time"], errors="raise")
    prefix = executions.loc[times <= snapshot_at].copy()
    if prefix.empty:
        return None
    prefix["event_time"] = pd.to_datetime(prefix["event_time"]).map(pd.Timestamp.isoformat)
    ordered_rows = prefix.reset_index(drop=True).reset_index(names="source_ordinal")
    payload = {
        "subject_id": subject_id,
        "account_id": account_id,
        "init_cash": init_cash,
        "rows": ordered_rows.to_dict("records"),
    }
    version = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return TwinInputVersionRef(
        source_type="normalized_executions",
        source_name="twin_snapshot_execution_prefix",
        data_version=version,
        as_of=max(pd.to_datetime(prefix["event_time"])),
        price_type=None,
        is_synthetic=data_tier in {"synthetic", "demo"},
        source_id=account_id,
    )


def build_twin_snapshot_from_facts(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    records: Sequence[EvidenceRecord],
    historical_series: Sequence[HistoricalMetricSeries],
    *,
    subject_id: str,
    account_id: str | None,
    as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
    data_tier: DataTier,
    calculation_code_version: str,
    decision_evidence: Mapping[str, Sequence[EvidenceRecord]] | None = None,
    episode_evidence: Mapping[str, Sequence[EvidenceRecord]] | None = None,
    data_quality_issues: Sequence[str] = (),
) -> TwinSnapshot:
    """Build an as-of Twin through the existing Position Episode/replay core."""

    cutoff = _required_timestamp(as_of, "as_of")
    if "event_time" not in executions:
        raise ValueError("executions.event_time is required")
    execution_times = pd.to_datetime(executions["event_time"], errors="raise")
    has_started = bool((execution_times <= cutoff).any())
    lifecycle = None
    if has_started:
        # Position Episode imports only evidence_available_at from this module.
        # Keeping this import local avoids a module initialization cycle.
        from src.episodes.position_episode import build_position_episode_lifecycle

        lifecycle = build_position_episode_lifecycle(
            executions,
            market_prices,
            subject_id=subject_id,
            account_id=account_id,
            as_of=cutoff,
            init_cash=init_cash,
            data_tier=data_tier,
            calculation_code_version=calculation_code_version,
            decision_evidence=decision_evidence,
            episode_evidence=episode_evidence,
        )
    execution_ref = _normalized_execution_input_ref(
        executions,
        snapshot_at=cutoff,
        subject_id=subject_id,
        account_id=account_id,
        init_cash=init_cash,
        data_tier=data_tier,
    )
    return build_twin_snapshot(
        records,
        historical_series,
        subject_id=subject_id,
        snapshot_at=cutoff,
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        position_lifecycle=lifecycle,
        input_version_refs=(() if execution_ref is None else (execution_ref,)),
        portfolio_state_status_if_missing="not_started",
        data_quality_issues=data_quality_issues,
    )


def build_historical_twin_snapshots(
    records: Sequence[EvidenceRecord],
    historical_series: Sequence[HistoricalMetricSeries],
    *,
    subject_id: str,
    snapshot_at: pd.Timestamp,
    data_tier: DataTier,
    calculation_code_version: str = "personal-twin-core-v1",
) -> tuple[TwinSnapshot, ...]:
    """Rebuild Evidence-only Twin snapshots at registered history dates."""

    cutoff = _required_timestamp(snapshot_at, "snapshot_at")
    dates = sorted(
        {
            point.as_of
            for series in historical_series
            if series.subject_id == subject_id
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
            calculation_code_version=calculation_code_version,
        )
        for date in dates
    )


def build_twin_metric_comparison(series: HistoricalMetricSeries) -> TwinMetricComparison:
    """Compare the earliest and latest valid registered points in one series."""

    valid = [
        point
        for point in series.points
        if point.value is not None and point.evidence_status != "insufficient_evidence"
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
    if not math.isfinite(absolute_change):  # pragma: no cover - point invariant
        raise ValueError("absolute_change must be finite")
    relative_change: float | None = None
    if reference.value != 0:
        quotient = absolute_change / reference.value
        # A tiny non-zero reference can overflow the quotient to +/-inf (or a
        # NaN from inf/inf-like point values).  The comparison must stay a
        # finite, presentable ratio or be reported as unavailable.
        relative_change = quotient if math.isfinite(quotient) else None
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
            else (
                "Relative change is unavailable because the ratio is not finite"
                if relative_change is None
                else None
            )
        ),
        reference_evidence_id=reference.source_evidence_id,
        current_evidence_id=current.source_evidence_id,
    )
