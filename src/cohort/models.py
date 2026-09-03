"""Small, deterministic contracts for synthetic cohort benchmarking.

These records deliberately contain only comparability and descriptive-statistics
metadata.  They do not calculate portfolio, behaviour, or evidence values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


def _timestamp(value: object, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be NaT")
    return timestamp


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class CohortDefinition:
    cohort_id: str
    market: str
    asset_types: tuple[str, ...]
    direction: str
    observation_start: pd.Timestamp
    observation_end: pd.Timestamp
    leverage_allowed: bool
    data_tier: str
    min_descriptive_n: int
    description: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("cohort_id", "market", "direction", "data_tier", "description"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        asset_types = tuple(_non_empty(item, "asset_types item") for item in self.asset_types)
        if not asset_types:
            raise ValueError("asset_types must be non-empty")
        object.__setattr__(self, "asset_types", asset_types)
        start = _timestamp(self.observation_start, "observation_start")
        end = _timestamp(self.observation_end, "observation_end")
        if end < start:
            raise ValueError("observation_end must not precede observation_start")
        object.__setattr__(self, "observation_start", start)
        object.__setattr__(self, "observation_end", end)
        if self.min_descriptive_n < 1:
            raise ValueError("min_descriptive_n must be positive")
        object.__setattr__(
            self,
            "limitations",
            tuple(_non_empty(item, "limitations item") for item in self.limitations),
        )


@dataclass(frozen=True, slots=True)
class CohortMember:
    subject_id: str
    market: str
    asset_types: tuple[str, ...]
    direction: str
    observation_start: pd.Timestamp
    observation_end: pd.Timestamp
    leverage: bool
    data_tier: str
    data_quality_status: str

    def __post_init__(self) -> None:
        for name in ("subject_id", "market", "direction", "data_tier", "data_quality_status"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        asset_types = tuple(_non_empty(item, "asset_types item") for item in self.asset_types)
        if not asset_types:
            raise ValueError("asset_types must be non-empty")
        object.__setattr__(self, "asset_types", asset_types)
        start = _timestamp(self.observation_start, "observation_start")
        end = _timestamp(self.observation_end, "observation_end")
        if end < start:
            raise ValueError("observation_end must not precede observation_start")
        object.__setattr__(self, "observation_start", start)
        object.__setattr__(self, "observation_end", end)


@dataclass(frozen=True, slots=True)
class PeerMetricValue:
    subject_id: str
    metric_id: str
    value: float | None
    evidence_status: str
    source_evidence_id: str
    as_of: pd.Timestamp | None
    evidence_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("subject_id", "metric_id", "evidence_status", "source_evidence_id"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise TypeError("value must be a finite number or None")
            if not math.isfinite(self.value):
                raise ValueError("value must be finite or None")
            object.__setattr__(self, "value", float(self.value))
        if self.as_of is not None:
            object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        if self.evidence_reason is not None:
            object.__setattr__(
                self,
                "evidence_reason",
                _non_empty(self.evidence_reason, "evidence_reason"),
            )


@dataclass(frozen=True, slots=True)
class PeerBenchmarkResult:
    subject_id: str
    cohort_id: str
    metric_id: str
    subject_value: float | None
    cohort_n: int
    metric_n: int
    p25: float | None
    median: float | None
    p75: float | None
    percentile: float | None
    benchmark_status: str
    benchmark_reason: str | None
    quantile_method: str
    percentile_method: str
    data_tier: str
    observation_start: pd.Timestamp
    observation_end: pd.Timestamp
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "subject_id", "cohort_id", "metric_id", "benchmark_status",
            "quantile_method", "percentile_method", "data_tier",
        ):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if self.subject_value is not None:
            object.__setattr__(self, "subject_value", float(self.subject_value))
        for name in ("p25", "median", "p75", "percentile"):
            value = getattr(self, name)
            if value is not None:
                if not math.isfinite(value):
                    raise ValueError(f"{name} must be finite or None")
                object.__setattr__(self, name, float(value))
        if self.cohort_n < 0 or self.metric_n < 0:
            raise ValueError("cohort_n and metric_n must be non-negative")
        start = _timestamp(self.observation_start, "observation_start")
        end = _timestamp(self.observation_end, "observation_end")
        if end < start:
            raise ValueError("observation_end must not precede observation_start")
        object.__setattr__(self, "observation_start", start)
        object.__setattr__(self, "observation_end", end)
        object.__setattr__(
            self, "limitations", tuple(_non_empty(item, "limitations item") for item in self.limitations)
        )
