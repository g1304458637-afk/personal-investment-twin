"""Deterministic self-history comparisons over existing Twin and metric facts.

This module does not calculate a financial metric.  It compares the current
metric state already selected by ``TwinSnapshot`` with eligible points already
published by ``HistoricalMetricSeries``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.evidence.contracts import (
    DataTier,
    EvidenceRecord,
    canonical_json_bytes,
)
from src.history.metric_series import HistoricalMetricPoint, HistoricalMetricSeries
from src.twin.state import (
    TwinInputVersionRef,
    TwinMetricState,
    TwinSnapshot,
    evidence_available_at,
)


SELF_BASELINE_METHOD_ID: Final = "self_historical_distribution_v1"
SELF_BASELINE_METHOD_VERSION: Final = "1"
SELF_BASELINE_ID_PREFIX: Final = "sb_"
HISTORICAL_SERIES_ID_PREFIX: Final = "hs_"
QUANTILE_METHOD: Final = "numpy_quantile_linear_v1"
PERCENTILE_METHOD: Final = "empirical_midrank_percentile_v1"
DEFAULT_WINDOW: Final = "rolling_12m"

SelfWindow = Literal["rolling_3m", "rolling_12m", "lifetime"]
ObservationKind = Literal["state_snapshot", "event", "window_statistic", "unknown"]
ComparisonBand = Literal[
    "below_historical_iqr",
    "within_historical_iqr",
    "above_historical_iqr",
]
SelfComparisonStatus = Literal[
    "complete",
    "insufficient_self_history",
    "unsupported_for_self_baseline",
]

WINDOWS: Final[tuple[SelfWindow, ...]] = (
    "rolling_3m",
    "rolling_12m",
    "lifetime",
)
COMMON_LIMITATIONS: Final[tuple[str, ...]] = (
    "Self vs Past is descriptive and does not judge whether a higher or lower value is good.",
    "The comparison uses only registered same-subject historical observations available at as_of.",
    "Self historical percentile is not a peer percentile or an investment skill score.",
)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be NaT")
    return timestamp


def _finite(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number or None")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite or None")
    return result


@dataclass(frozen=True, slots=True)
class SelfBaselineMetricDefinition:
    """Explicit opt-in rule for one comparable historical metric."""

    metric_id: str
    source_method_id: str
    source_method_version: str
    observation_kind: ObservationKind
    observation_unit: str
    observation_cadence: str
    baseline_eligible: bool
    supported_windows: tuple[SelfWindow, ...]
    minimum_observations: Mapping[SelfWindow, int]
    comparison_semantics: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "metric_id",
            "source_method_id",
            "source_method_version",
            "observation_unit",
            "observation_cadence",
            "comparison_semantics",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.observation_kind not in {
            "state_snapshot",
            "event",
            "window_statistic",
            "unknown",
        }:
            raise ValueError("observation_kind is unsupported")
        windows = tuple(self.supported_windows)
        if not windows or len(set(windows)) != len(windows) or any(item not in WINDOWS for item in windows):
            raise ValueError("supported_windows must contain unique known windows")
        minimum = dict(self.minimum_observations)
        if set(minimum) != set(windows):
            raise ValueError("minimum_observations must cover every supported window")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in minimum.values()):
            raise ValueError("minimum_observations values must be positive integers")
        object.__setattr__(self, "supported_windows", windows)
        object.__setattr__(self, "minimum_observations", MappingProxyType(minimum))
        object.__setattr__(self, "limitations", tuple(_text(item, "limitation") for item in self.limitations))


_METRICS: Final = (
    SelfBaselineMetricDefinition(
        metric_id="portfolio_concentration_hhi",
        source_method_id="hhi_security_weights_v1",
        source_method_version="1",
        observation_kind="state_snapshot",
        observation_unit="portfolio_state_snapshot",
        observation_cadence="supplied_complete_market_price_observation_dates",
        baseline_eligible=True,
        supported_windows=WINDOWS,
        minimum_observations={window: 3 for window in WINDOWS},
        comparison_semantics="current_state_relative_to_same_subject_historical_distribution",
        limitations=(
            "HHI comparisons describe concentration position, not risk quality or investment skill.",
            "HHI history is an observation-weighted distribution over supplied market-price dates, not a time-weighted distribution; dates absent from the source receive no weight.",
        ),
    ),
    SelfBaselineMetricDefinition(
        metric_id="mean_daily_turnover",
        source_method_id="pyfolio_portfolio_value_turnover_v1",
        source_method_version="1",
        observation_kind="window_statistic",
        observation_unit="calendar_day_portfolio_value_turnover_ratio",
        observation_cadence="supplied_complete_market_price_observation_dates",
        baseline_eligible=True,
        supported_windows=WINDOWS,
        minimum_observations={window: 5 for window in WINDOWS},
        comparison_semantics="current_daily_observation_relative_to_same_subject_daily_history",
        limitations=(
            "Historical points are existing daily turnover observations, not a recomputed rolling mean.",
            "A supplied complete market-price date with no trade contributes zero turnover; a date absent from the source is not silently inserted as a zero observation.",
            "Turnover comparisons do not label trading activity as excessive or disciplined.",
        ),
    ),
)
_METRIC_REGISTRY: Final = MappingProxyType({item.metric_id: item for item in _METRICS})


def list_self_baseline_metrics() -> tuple[SelfBaselineMetricDefinition, ...]:
    """Return the stable explicit opt-in registry."""

    return _METRICS


def get_self_baseline_metric(metric_id: str) -> SelfBaselineMetricDefinition | None:
    """Return the registered definition, or ``None`` for an unsupported metric."""

    return _METRIC_REGISTRY.get(metric_id)


@dataclass(frozen=True, slots=True)
class SelfBaselineProvenance:
    current_source_ref: str | None
    historical_series_ref: str | None
    historical_point_source_refs: tuple[str, ...]
    input_version_refs: tuple[TwinInputVersionRef, ...]
    source_method_id: str
    source_method_version: str
    observation_kind: ObservationKind
    observation_unit: str
    observation_cadence: str
    quantile_method: str
    percentile_method: str
    data_tier: DataTier


@dataclass(frozen=True, slots=True)
class SelfBaselineComparison:
    comparison_id: str
    subject_id: str
    metric_id: str
    method_id: str
    method_version: str
    source_method_id: str
    source_method_version: str
    as_of: pd.Timestamp
    current_value: float | None
    current_source_ref: str | None
    historical_series_ref: str | None
    window: SelfWindow
    observation_start: pd.Timestamp | None
    observation_end: pd.Timestamp | None
    observation_kind: ObservationKind
    observation_unit: str
    observation_cadence: str
    valid_n: int
    median: float | None
    p25: float | None
    p75: float | None
    self_historical_percentile: float | None
    delta_from_median: float | None
    comparison_band: ComparisonBand | None
    status: SelfComparisonStatus
    insufficient_reason: str | None
    provenance: SelfBaselineProvenance
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.comparison_id.startswith(SELF_BASELINE_ID_PREFIX) or len(self.comparison_id) != 67:
            raise ValueError("comparison_id must be a deterministic SHA-256 Self baseline ID")
        for name in (
            "subject_id",
            "metric_id",
            "method_id",
            "method_version",
            "source_method_id",
            "source_method_version",
            "observation_unit",
            "observation_cadence",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        for name in ("observation_start", "observation_end"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _timestamp(value, name))
        for name in (
            "current_value",
            "median",
            "p25",
            "p75",
            "self_historical_percentile",
            "delta_from_median",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.valid_n < 0:
            raise ValueError("valid_n must be non-negative")
        if self.status not in {
            "complete",
            "insufficient_self_history",
            "unsupported_for_self_baseline",
        }:
            raise ValueError("status is unsupported")
        if self.comparison_band not in {
            None,
            "below_historical_iqr",
            "within_historical_iqr",
            "above_historical_iqr",
        }:
            raise ValueError("comparison_band is unsupported")
        if (self.observation_start is None) != (self.observation_end is None):
            raise ValueError("observation_start and observation_end must be present together")
        if self.observation_start is not None:
            if self.observation_end < self.observation_start:
                raise ValueError("observation_end cannot precede observation_start")
            if self.observation_end >= self.as_of:
                raise ValueError("historical observations must precede as_of")
        statistics = (
            self.median,
            self.p25,
            self.p75,
            self.self_historical_percentile,
            self.delta_from_median,
        )
        if self.status == "complete":
            if any(value is None for value in statistics) or self.comparison_band is None:
                raise ValueError("complete comparison requires all descriptive statistics")
            if self.valid_n == 0:
                raise ValueError("complete comparison requires historical observations")
            if not 0 <= self.self_historical_percentile <= 100:
                raise ValueError("self_historical_percentile must be between 0 and 100")
            if self.insufficient_reason is not None:
                raise ValueError("complete comparison cannot have insufficient_reason")
        elif any(value is not None for value in statistics) or self.comparison_band is not None:
            raise ValueError("non-complete comparison cannot publish descriptive statistics")
        if self.status != "complete" and not self.insufficient_reason:
            raise ValueError("non-complete comparison requires insufficient_reason")
        object.__setattr__(self, "limitations", tuple(_text(item, "limitation") for item in self.limitations))


@dataclass(frozen=True, slots=True)
class SelfBaselineMetricSummary:
    metric_id: str
    observation_kind: ObservationKind
    observation_unit: str
    observation_cadence: str
    windows: tuple[SelfBaselineComparison, ...]


@dataclass(frozen=True, slots=True)
class SelfBaselineSummary:
    subject_id: str
    as_of: pd.Timestamp
    default_window: SelfWindow
    metrics: tuple[SelfBaselineMetricSummary, ...]
    available_metric_count: int
    insufficient_metric_count: int
    data_tier: DataTier
    limitations: tuple[str, ...]


def _json_value(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def self_baseline_json_bytes(value: SelfBaselineComparison | SelfBaselineSummary) -> bytes:
    """Return canonical bytes for persistence, hashing, and regression tests."""

    return canonical_json_bytes(_json_value(value))


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


def _point_payload(point: HistoricalMetricPoint) -> dict[str, object]:
    return {
        "as_of": point.as_of.isoformat(),
        "value": point.value,
        "evidence_status": point.evidence_status,
        "source_evidence_id": point.source_evidence_id,
        "observation_count": point.observation_count,
        "attributes": dict(point.attributes),
    }


def _series_ref(series: HistoricalMetricSeries, points: Sequence[HistoricalMetricPoint]) -> str:
    payload = {
        "subject_id": series.subject_id,
        "metric_id": series.metric_id,
        "method_id": series.method_id,
        "method_version": series.method_version,
        "points": [_point_payload(item) for item in points],
        "data_tier": series.data_tier,
        "limitations": list(series.limitations),
    }
    return HISTORICAL_SERIES_ID_PREFIX + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _window_start(as_of: pd.Timestamp, window: SelfWindow) -> pd.Timestamp | None:
    if window == "rolling_3m":
        return as_of - pd.DateOffset(months=3)
    if window == "rolling_12m":
        return as_of - pd.DateOffset(months=12)
    if window == "lifetime":
        return None
    raise ValueError(f"Unsupported Self baseline window: {window!r}")


def _current_state(snapshot: TwinSnapshot, metric_id: str) -> TwinMetricState | None:
    matches = tuple(item for item in snapshot.behavior_state if item.metric_id == metric_id)
    if len(matches) > 1:
        raise ValueError(f"Twin contains duplicate current states for {metric_id!r}")
    return matches[0] if matches else None


def _evidence_catalog(records: Sequence[EvidenceRecord]) -> dict[str, EvidenceRecord]:
    catalog = {item.evidence_id: item for item in records}
    if len(catalog) != len(records):
        raise ValueError("evidence_records contains duplicate evidence_id values")
    return catalog


def _validate_source_record(
    record: EvidenceRecord,
    *,
    snapshot: TwinSnapshot,
    series: HistoricalMetricSeries,
) -> None:
    if record.subject_id != snapshot.subject_id:
        raise ValueError("Historical point Evidence must belong to the Twin subject")
    if record.metric_id != series.metric_id:
        raise ValueError("Historical point Evidence metric does not match its series")
    if (record.method_id, record.method_version) != (series.method_id, series.method_version):
        raise ValueError("Historical point Evidence method does not match its series")


def _midrank_percentile(history: Sequence[float], current: float) -> float:
    lower = sum(value < current for value in history)
    equal = sum(value == current for value in history)
    return 100.0 * (lower + 0.5 * equal) / len(history)


def _identity(
    payload: Mapping[str, object],
) -> str:
    return SELF_BASELINE_ID_PREFIX + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _comparison(
    *,
    snapshot: TwinSnapshot,
    series: HistoricalMetricSeries,
    definition: SelfBaselineMetricDefinition | None,
    window: SelfWindow,
    current: TwinMetricState | None,
    available_points: tuple[HistoricalMetricPoint, ...],
    selected_points: tuple[HistoricalMetricPoint, ...],
    input_refs: tuple[TwinInputVersionRef, ...],
    status: SelfComparisonStatus,
    reason: str | None,
) -> SelfBaselineComparison:
    valid = tuple(
        item
        for item in selected_points
        if item.evidence_status == "complete" and item.value is not None
    )
    values = tuple(float(item.value) for item in valid if item.value is not None)
    p25 = median = p75 = percentile = delta = None
    band: ComparisonBand | None = None
    current_value = float(current.value) if current is not None and current.value is not None else None
    if status == "complete" and current_value is not None:
        quantiles = np.quantile(np.asarray(values, dtype=float), [0.25, 0.5, 0.75], method="linear")
        p25, median, p75 = (float(value) for value in quantiles)
        percentile = _midrank_percentile(values, current_value)
        delta = current_value - median
        band = (
            "below_historical_iqr"
            if current_value < p25
            else "above_historical_iqr"
            if current_value > p75
            else "within_historical_iqr"
        )

    historical_series_ref = _series_ref(series, available_points)
    source_refs = tuple(sorted({item.source_evidence_id for item in selected_points}))
    provenance = SelfBaselineProvenance(
        current_source_ref=current.source_evidence_id if current is not None else None,
        historical_series_ref=historical_series_ref,
        historical_point_source_refs=source_refs,
        input_version_refs=input_refs,
        source_method_id=series.method_id,
        source_method_version=series.method_version,
        observation_kind=definition.observation_kind if definition else "unknown",
        observation_unit=definition.observation_unit if definition else "unsupported",
        observation_cadence=(
            definition.observation_cadence if definition else "unsupported"
        ),
        quantile_method=QUANTILE_METHOD,
        percentile_method=PERCENTILE_METHOD,
        data_tier=snapshot.data_tier,
    )
    identity_payload = {
        "subject_id": snapshot.subject_id,
        "metric_id": series.metric_id,
        "method_id": SELF_BASELINE_METHOD_ID,
        "method_version": SELF_BASELINE_METHOD_VERSION,
        "source_method_id": series.method_id,
        "source_method_version": series.method_version,
        "observation_kind": definition.observation_kind if definition else "unknown",
        "observation_unit": definition.observation_unit if definition else "unsupported",
        "observation_cadence": (
            definition.observation_cadence if definition else "unsupported"
        ),
        "as_of": snapshot.snapshot_at.isoformat(),
        "window": window,
        "current": _json_value(current),
        "historical_series_ref": historical_series_ref,
        "selected_points": [_point_payload(item) for item in selected_points],
        "input_version_refs": [_json_value(item) for item in input_refs],
        "quantile_method": QUANTILE_METHOD,
        "percentile_method": PERCENTILE_METHOD,
        "status": status,
        "reason": reason,
    }
    limitations = tuple(dict.fromkeys((*COMMON_LIMITATIONS, *(definition.limitations if definition else ()))))
    return SelfBaselineComparison(
        comparison_id=_identity(identity_payload),
        subject_id=snapshot.subject_id,
        metric_id=series.metric_id,
        method_id=SELF_BASELINE_METHOD_ID,
        method_version=SELF_BASELINE_METHOD_VERSION,
        source_method_id=series.method_id,
        source_method_version=series.method_version,
        as_of=snapshot.snapshot_at,
        current_value=current_value,
        current_source_ref=current.source_evidence_id if current is not None else None,
        historical_series_ref=historical_series_ref,
        window=window,
        observation_start=valid[0].as_of if valid else None,
        observation_end=valid[-1].as_of if valid else None,
        observation_kind=definition.observation_kind if definition else "unknown",
        observation_unit=definition.observation_unit if definition else "unsupported",
        observation_cadence=(
            definition.observation_cadence if definition else "unsupported"
        ),
        valid_n=len(valid),
        median=median,
        p25=p25,
        p75=p75,
        self_historical_percentile=percentile,
        delta_from_median=delta,
        comparison_band=band,
        status=status,
        insufficient_reason=reason,
        provenance=provenance,
        limitations=limitations,
    )


def build_self_baseline_comparison(
    snapshot: TwinSnapshot,
    series: HistoricalMetricSeries,
    evidence_records: Sequence[EvidenceRecord],
    *,
    window: SelfWindow = DEFAULT_WINDOW,
) -> SelfBaselineComparison:
    """Compare one Twin current state with its registered historical distribution.

    Historical points and their source Evidence are only inspected when their
    timestamps are not later than ``snapshot.snapshot_at``.  The current point
    is excluded even when the Twin current state predates the snapshot cutoff.
    """

    if series.subject_id != snapshot.subject_id:
        raise ValueError("Historical series subject_id does not match Twin subject_id")
    if series.data_tier != snapshot.data_tier:
        raise ValueError("Historical series data_tier does not match Twin")
    if window not in WINDOWS:
        raise ValueError(f"Unsupported Self baseline window: {window!r}")

    definition = get_self_baseline_metric(series.metric_id)
    current = _current_state(snapshot, series.metric_id)
    input_refs = tuple(sorted(snapshot.input_version_refs, key=_input_ref_key))
    if definition is None or not definition.baseline_eligible:
        return _comparison(
            snapshot=snapshot,
            series=series,
            definition=None,
            window=window,
            current=current,
            available_points=(),
            selected_points=(),
            input_refs=input_refs,
            status="unsupported_for_self_baseline",
            reason="Metric is not registered for Self baseline v1",
        )
    if window not in definition.supported_windows:
        raise ValueError(f"Window {window!r} is not registered for {series.metric_id!r}")
    if (series.method_id, series.method_version) != (
        definition.source_method_id,
        definition.source_method_version,
    ):
        raise ValueError("Historical series method binding is not registered for Self baseline")

    catalog = _evidence_catalog(tuple(evidence_records))
    available: list[HistoricalMetricPoint] = []
    for point in series.points:
        if point.as_of > snapshot.snapshot_at:
            continue
        source = catalog.get(point.source_evidence_id)
        if source is None:
            raise ValueError("Historical point source Evidence is missing")
        _validate_source_record(source, snapshot=snapshot, series=series)
        source_available = evidence_available_at(source)
        if source_available is None or source_available > snapshot.snapshot_at:
            continue
        if point.evidence_status != source.evidence_status:
            raise ValueError("Historical point status does not match its source Evidence")
        available.append(point)

    if current is not None:
        if current.as_of > snapshot.snapshot_at:
            raise ValueError("Twin current state is later than snapshot_at")
        source = catalog.get(current.source_evidence_id)
        if source is None:
            raise ValueError("Twin current state source Evidence is missing")
        _validate_source_record(source, snapshot=snapshot, series=series)
        source_available = evidence_available_at(source)
        if source_available is None or source_available > snapshot.snapshot_at:
            raise ValueError("Twin current state source Evidence was not available at snapshot_at")
        if current.evidence_status != source.evidence_status:
            raise ValueError("Twin current state status does not match its source Evidence")
        if not any(
            point.as_of == current.as_of
            and point.source_evidence_id == current.source_evidence_id
            and point.value == current.value
            and point.evidence_status == current.evidence_status
            for point in available
        ):
            raise ValueError("Twin current state does not resolve to the supplied historical series")

    historical = tuple(
        point
        for point in available
        if point.as_of < snapshot.snapshot_at
        and not (
            current is not None
            and point.as_of == current.as_of
            and point.source_evidence_id == current.source_evidence_id
        )
    )
    lower = _window_start(snapshot.snapshot_at, window)
    selected = tuple(point for point in historical if lower is None or point.as_of >= lower)
    valid_n = sum(
        item.evidence_status == "complete" and item.value is not None
        for item in selected
    )
    reason: str | None = None
    if current is None:
        reason = "Twin has no current state for this registered metric"
    elif current.evidence_status != "complete" or current.value is None:
        reason = "Current metric state is not complete"
    elif valid_n < definition.minimum_observations[window]:
        reason = (
            f"{valid_n} valid historical observations are available; "
            f"{definition.minimum_observations[window]} are required for {window}"
        )
    status: SelfComparisonStatus = "complete" if reason is None else "insufficient_self_history"
    return _comparison(
        snapshot=snapshot,
        series=series,
        definition=definition,
        window=window,
        current=current,
        available_points=historical,
        selected_points=selected,
        input_refs=input_refs,
        status=status,
        reason=reason,
    )


def build_self_baseline_summary(
    snapshot: TwinSnapshot,
    historical_series: Sequence[HistoricalMetricSeries],
    evidence_records: Sequence[EvidenceRecord],
) -> SelfBaselineSummary:
    """Build stable three-window summaries for explicitly supplied series."""

    by_metric: dict[str, HistoricalMetricSeries] = {}
    for series in historical_series:
        if series.metric_id in by_metric:
            raise ValueError("historical_series contains duplicate metric_id values")
        by_metric[series.metric_id] = series

    metric_summaries: list[SelfBaselineMetricSummary] = []
    for metric_id in sorted(by_metric):
        series = by_metric[metric_id]
        definition = get_self_baseline_metric(metric_id)
        comparisons = tuple(
            build_self_baseline_comparison(snapshot, series, evidence_records, window=window)
            for window in (definition.supported_windows if definition else (DEFAULT_WINDOW,))
        )
        metric_summaries.append(
            SelfBaselineMetricSummary(
                metric_id=metric_id,
                observation_kind=definition.observation_kind if definition else "unknown",
                observation_unit=definition.observation_unit if definition else "unsupported",
                observation_cadence=(
                    definition.observation_cadence if definition else "unsupported"
                ),
                windows=comparisons,
            )
        )

    default_results = tuple(
        comparison
        for metric in metric_summaries
        for comparison in metric.windows
        if comparison.window == DEFAULT_WINDOW
    )
    return SelfBaselineSummary(
        subject_id=snapshot.subject_id,
        as_of=snapshot.snapshot_at,
        default_window=DEFAULT_WINDOW,
        metrics=tuple(metric_summaries),
        available_metric_count=sum(item.status == "complete" for item in default_results),
        insufficient_metric_count=sum(item.status != "complete" for item in default_results),
        data_tier=snapshot.data_tier,
        limitations=COMMON_LIMITATIONS,
    )
