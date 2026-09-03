"""Pure, one-account-one-vote descriptive statistics for a fixed cohort."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from scipy.stats import percentileofscore

from src.cohort.models import (
    CohortDefinition,
    CohortMember,
    PeerBenchmarkResult,
    PeerMetricValue,
)


QUANTILE_METHOD = "numpy_quantile_linear_v1"
PERCENTILE_METHOD = "scipy_percentileofscore_rank_v1"
SUPPORTED_PEER_METRICS = frozenset(
    {
        "portfolio_concentration_hhi",
        "mean_daily_turnover",
        "closed_episode_count",
    }
)


def exact_cohort_members(
    definition: CohortDefinition,
    members: Iterable[CohortMember],
) -> tuple[CohortMember, ...]:
    """Return only members matching every declared cohort dimension exactly."""

    if definition.data_tier != "synthetic":
        raise ValueError("Cohort v1 supports only the synthetic data tier")
    all_members = tuple(members)
    if definition.data_tier == "synthetic" and any(
        member.data_tier != "synthetic" for member in all_members
    ):
        raise ValueError("A synthetic cohort cannot mix non-synthetic members")

    exact = tuple(
        member
        for member in all_members
        if member.market == definition.market
        and member.asset_types == definition.asset_types
        and member.direction == definition.direction
        and member.observation_start == definition.observation_start
        and member.observation_end == definition.observation_end
        and member.leverage == definition.leverage_allowed
        and member.data_tier == definition.data_tier
        and member.data_quality_status == "complete"
    )
    ids = [member.subject_id for member in exact]
    if len(ids) != len(set(ids)):
        raise ValueError("Exact cohort members must have unique subject_id values")
    return exact


def _eligible_values(
    metric_id: str,
    peer_metric_values: tuple[PeerMetricValue, ...],
    *,
    member_ids: frozenset[str],
    observation_end: object,
) -> tuple[float, ...]:
    seen: set[str] = set()
    values: list[float] = []
    for item in peer_metric_values:
        if item.metric_id != metric_id or item.subject_id not in member_ids:
            continue
        if item.subject_id in seen:
            raise ValueError("A cohort account may contribute one value per metric")
        seen.add(item.subject_id)
        if (
            item.evidence_status == "complete"
            and item.value is not None
            and math.isfinite(item.value)
            and item.as_of == observation_end
        ):
            values.append(float(item.value))
    return tuple(values)


def _subject_value(
    metric: PeerMetricValue,
    *,
    subject_id: str,
    observation_end: object,
) -> tuple[float | None, str | None]:
    if metric.subject_id != subject_id:
        raise ValueError("subject_metric_values must belong to subject_id")
    if metric.evidence_status != "complete" or metric.value is None:
        return None, metric.evidence_reason or "Subject metric evidence is insufficient"
    if metric.as_of != observation_end:
        return None, "Subject metric is not aligned to the cohort observation window"
    return float(metric.value), None


def build_peer_benchmark_results(
    definition: CohortDefinition,
    members: Iterable[CohortMember],
    peer_metric_values: Iterable[PeerMetricValue],
    subject_metric_values: Iterable[PeerMetricValue],
    *,
    subject_id: str,
) -> tuple[PeerBenchmarkResult, ...]:
    """Benchmark supplied subject metrics against a fixed, exact cohort.

    The function deliberately receives already-computed metric values: it does
    not calculate a financial metric and each peer contributes at most one value
    for a metric.
    """

    exact = exact_cohort_members(definition, members)
    exact_ids = frozenset(member.subject_id for member in exact)
    if subject_id in exact_ids:
        raise ValueError("The subject must not be included in peer cohort members")
    peer_values = tuple(peer_metric_values)
    subjects = tuple(subject_metric_values)
    unsupported = {
        item.metric_id
        for item in (*peer_values, *subjects)
        if item.metric_id not in SUPPORTED_PEER_METRICS
    }
    if unsupported:
        raise ValueError(f"Peer benchmark v1 does not support metrics: {sorted(unsupported)}")
    metric_ids = [item.metric_id for item in subjects]
    if len(metric_ids) != len(set(metric_ids)):
        raise ValueError("subject_metric_values must contain one value per metric")

    results: list[PeerBenchmarkResult] = []
    for subject_metric in subjects:
        subject_value, subject_reason = _subject_value(
            subject_metric,
            subject_id=subject_id,
            observation_end=definition.observation_end,
        )
        values = _eligible_values(
            subject_metric.metric_id,
            peer_values,
            member_ids=exact_ids,
            observation_end=definition.observation_end,
        )
        status = "complete"
        reason: str | None = None
        p25 = median = p75 = percentile = None
        if subject_reason is not None:
            status, reason = "insufficient_evidence", subject_reason
        elif len(values) < definition.min_descriptive_n:
            status = "insufficient_cohort"
            reason = (
                f"Metric has {len(values)} eligible peer values; at least "
                f"{definition.min_descriptive_n} are required"
            )
        else:
            quantiles = np.quantile(np.asarray(values, dtype=float), [0.25, 0.5, 0.75], method="linear")
            p25, median, p75 = (float(value) for value in quantiles)
            percentile = float(percentileofscore(values, subject_value, kind="rank"))
        results.append(
            PeerBenchmarkResult(
                subject_id=subject_id,
                cohort_id=definition.cohort_id,
                metric_id=subject_metric.metric_id,
                subject_value=subject_value,
                cohort_n=len(exact),
                metric_n=len(values),
                p25=p25,
                median=median,
                p75=p75,
                percentile=percentile,
                benchmark_status=status,
                benchmark_reason=reason,
                quantile_method=QUANTILE_METHOD,
                percentile_method=PERCENTILE_METHOD,
                data_tier=definition.data_tier,
                observation_start=definition.observation_start,
                observation_end=definition.observation_end,
                limitations=definition.limitations,
            )
        )
    return tuple(results)
