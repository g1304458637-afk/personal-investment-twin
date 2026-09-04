"""Ordered historical views over existing deterministic evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from src.behavior.portfolio_concentration import (
    build_portfolio_concentration_evidence,
)
from src.behavior.turnover_intensity import TurnoverIntensityEvidence
from src.evidence.adapters import adapt_portfolio_concentration_evidence
from src.evidence.contracts import (
    DataTier,
    EvidenceRecord,
    EvidenceStatus,
    freeze_json_mapping,
)


@dataclass(frozen=True, slots=True)
class HistoricalMetricPoint:
    """One dated view of an existing deterministic evidence result."""

    as_of: pd.Timestamp
    value: float | None
    evidence_status: EvidenceStatus
    source_evidence_id: str
    observation_count: int | None
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamp = pd.Timestamp(self.as_of)
        if pd.isna(timestamp):
            raise ValueError("as_of cannot be NaT")
        object.__setattr__(self, "as_of", timestamp)
        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise TypeError("value must be a finite number or None")
            if not math.isfinite(self.value):
                raise ValueError("value must be finite or None")
        if self.evidence_status not in {
            "complete",
            "partial",
            "insufficient_evidence",
            "experimental",
        }:
            raise ValueError("evidence_status is unsupported")
        if not isinstance(self.source_evidence_id, str) or not self.source_evidence_id.strip():
            raise ValueError("source_evidence_id must be non-empty")
        if self.observation_count is not None and self.observation_count < 0:
            raise ValueError("observation_count must be non-negative or None")
        object.__setattr__(self, "attributes", freeze_json_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class HistoricalMetricSeries:
    """Chronological product view; it is not a new financial Evidence type."""

    subject_id: str
    metric_id: str
    method_id: str
    method_version: str
    points: tuple[HistoricalMetricPoint, ...]
    data_tier: DataTier
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("subject_id", "metric_id", "method_id", "method_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, value.strip())
        if self.data_tier not in {
            "synthetic",
            "demo",
            "authorized_beta",
            "production",
        }:
            raise ValueError("data_tier is unsupported")
        points = tuple(self.points)
        if any(left.as_of >= right.as_of for left, right in zip(points, points[1:])):
            raise ValueError("points must be strictly chronological")
        object.__setattr__(self, "points", points)
        object.__setattr__(
            self,
            "limitations",
            tuple(item.strip() for item in self.limitations if item.strip()),
        )


def _point_from_record(record: EvidenceRecord, *, as_of: pd.Timestamp) -> HistoricalMetricPoint:
    value = float(record.value) if isinstance(record.value, (int, float)) else None
    return HistoricalMetricPoint(
        as_of=as_of,
        value=value,
        evidence_status=record.evidence_status,
        source_evidence_id=record.evidence_id,
        observation_count=record.observation_count,
        attributes={
            **record.attributes,
            "evidence_reason": record.evidence_reason,
        },
    )


def build_portfolio_hhi_history_with_records(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> tuple[HistoricalMetricSeries, tuple[EvidenceRecord, ...]]:
    """Build dated HHI snapshots and retain their source Evidence records.

    Each point uses executions on or before that calendar date and market-price
    rows on or before that date.  No price is filled and no later row is exposed
    to the underlying replay.
    """

    if "event_time" not in executions.columns or "date" not in market_prices.columns:
        raise ValueError("executions.event_time and market_prices.date are required")
    execution_dates = pd.to_datetime(executions["event_time"], errors="raise").dt.normalize()
    price_dates = pd.to_datetime(market_prices["date"], errors="raise").dt.normalize()
    if execution_dates.empty or price_dates.empty:
        raise ValueError("executions and market_prices must be non-empty")

    dates = tuple(
        sorted(
            pd.Timestamp(value)
            for value in price_dates.unique()
            if value >= execution_dates.min()
        )
    )
    points: list[HistoricalMetricPoint] = []
    records: list[EvidenceRecord] = []
    for as_of in dates:
        execution_prefix = executions.loc[execution_dates <= as_of].copy()
        if execution_prefix.empty:
            continue
        price_prefix = market_prices.loc[price_dates <= as_of].copy()
        evidence = build_portfolio_concentration_evidence(
            execution_prefix,
            price_prefix,
            init_cash=init_cash,
        )
        # A date represented only by irrelevant instruments is not a portfolio
        # snapshot date.  Do not relabel the builder's earlier snapshot as new.
        if (
            evidence.evidence_status == "complete"
            and evidence.as_of_time != as_of
        ):
            continue
        record = adapt_portfolio_concentration_evidence(
            evidence,
            subject_id=subject_id,
            data_tier=data_tier,
            calculation_code_version=calculation_code_version,
        )
        records.append(record)
        points.append(_point_from_record(record, as_of=as_of))

    if not records:
        raise ValueError("no historical HHI observation dates are available")
    latest = records[-1]
    series = HistoricalMetricSeries(
        subject_id=subject_id,
        metric_id=latest.metric_id,
        method_id=latest.method_id,
        method_version=latest.method_version,
        points=tuple(points),
        data_tier=data_tier,
        limitations=latest.limitations,
    )
    return series, tuple(records)


def build_portfolio_hhi_history(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> HistoricalMetricSeries:
    """Build dated HHI snapshots solely through the existing HHI evidence path."""

    series, _ = build_portfolio_hhi_history_with_records(
        executions,
        market_prices,
        init_cash=init_cash,
        subject_id=subject_id,
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
    )
    return series


def build_turnover_history(
    evidence: TurnoverIntensityEvidence,
    *,
    parent_record: EvidenceRecord,
) -> HistoricalMetricSeries:
    """Expose the existing daily_turnover observations without recalculation."""

    if parent_record.method_id != evidence.method_id:
        raise ValueError("parent_record does not describe the supplied turnover evidence")
    points = tuple(
        HistoricalMetricPoint(
            as_of=item.observation_date,
            value=item.turnover,
            evidence_status=parent_record.evidence_status,
            source_evidence_id=parent_record.evidence_id,
            observation_count=1,
            attributes={
                "traded_value": item.traded_value,
                "portfolio_value": item.portfolio_value,
            },
        )
        for item in evidence.daily_turnover
    )
    return HistoricalMetricSeries(
        subject_id=parent_record.subject_id,
        metric_id=parent_record.metric_id,
        method_id=parent_record.method_id,
        method_version=parent_record.method_version,
        points=points,
        data_tier=parent_record.data_tier,
        limitations=parent_record.limitations,
    )
