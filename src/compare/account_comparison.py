"""Factual account-period differences over already-built comparison projections.

This module has no replay, accounting, ranking, or causal interpretation.  The
caller is responsible for binding each performance series to an authorized
account before constructing this descriptive view.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.compare.lookthrough import LookthroughResult
from src.compare.periods import PeriodBehaviorSummary
from src.evidence.contracts import canonical_json_bytes
from src.performance.account_series import AccountPerformanceSeries


METHOD_ID = "account_period_factual_comparison_v1"
METHOD_VERSION = "1"
ComparisonKind = Literal["self_periods", "professional"]


class AccountComparisonError(ValueError):
    """The supplied evidence does not establish one comparable pair."""


@dataclass(frozen=True, slots=True)
class MethodReference:
    source: str
    method_id: str
    method_version: str


@dataclass(frozen=True, slots=True)
class MetricDifference:
    metric_id: str
    left_value: float | None
    right_value: float | None
    right_minus_left: float | None
    unit: str


@dataclass(frozen=True, slots=True)
class UnderlyingOverlap:
    asset_id: str
    left_weight: float
    right_weight: float
    overlap_weight: float


@dataclass(frozen=True, slots=True)
class AccountPeriodComparison:
    comparison_id: str
    method_id: str
    method_version: str
    kind: ComparisonKind
    currency: str
    data_tier: str
    left_account_id: str
    right_account_id: str
    left_period_start: str
    left_period_end: str
    right_period_start: str
    right_period_end: str
    method_references: tuple[MethodReference, ...]
    differences: tuple[MetricDifference, ...]
    shared_underlying: tuple[UnderlyingOverlap, ...]
    limitations: tuple[str, ...]


def _date(value: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _same_calendar_date(left: pd.Timestamp, right: pd.Timestamp) -> bool:
    return _date(left) == _date(right)


def _performance_dates(series: AccountPerformanceSeries) -> tuple[pd.Timestamp, ...]:
    return tuple(_date(point.observed_at) for point in series.points)


def _validate_behavior(
    series: AccountPerformanceSeries, behavior: PeriodBehaviorSummary, side: str,
) -> None:
    if not _same_calendar_date(series.period_start, behavior.start_date):
        raise AccountComparisonError(f"{side} behavior start_date does not match performance period")
    if not _same_calendar_date(series.period_end, behavior.end_date):
        raise AccountComparisonError(f"{side} behavior end_date does not match performance period")


def _difference(metric_id: str, left: float | None, right: float | None, unit: str) -> MetricDifference:
    values = (left, right)
    if any(value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                  or not math.isfinite(float(value))) for value in values):
        raise AccountComparisonError(f"{metric_id} is not a finite numeric result")
    normalized_left = None if left is None else float(left)
    normalized_right = None if right is None else float(right)
    return MetricDifference(
        metric_id, normalized_left, normalized_right,
        None if normalized_left is None or normalized_right is None else normalized_right - normalized_left,
        unit,
    )


def _overlap(left: LookthroughResult, right: LookthroughResult) -> tuple[UnderlyingOverlap, ...]:
    left_weights = {item.asset_id: item.weight for item in left.security_exposures}
    right_weights = {item.asset_id: item.weight for item in right.security_exposures}
    return tuple(
        UnderlyingOverlap(asset_id, float(left_weights[asset_id]), float(right_weights[asset_id]),
                          min(float(left_weights[asset_id]), float(right_weights[asset_id])))
        for asset_id in sorted(left_weights.keys() & right_weights.keys())
    )


def _method_refs(
    left: AccountPerformanceSeries, right: AccountPerformanceSeries,
    left_behavior: PeriodBehaviorSummary, right_behavior: PeriodBehaviorSummary,
    left_lookthrough: LookthroughResult | None, right_lookthrough: LookthroughResult | None,
) -> tuple[MethodReference, ...]:
    refs = [
        MethodReference("left_performance", left.method_id, left.method_version),
        MethodReference("right_performance", right.method_id, right.method_version),
        MethodReference("left_behavior", left_behavior.method_id, left_behavior.method_version),
        MethodReference("right_behavior", right_behavior.method_id, right_behavior.method_version),
    ]
    if left_lookthrough is not None:
        refs.append(MethodReference("left_lookthrough", left_lookthrough.method_id, left_lookthrough.method_version))
    if right_lookthrough is not None:
        refs.append(MethodReference("right_lookthrough", right_lookthrough.method_id, right_lookthrough.method_version))
    return tuple(refs)


def compare_account_periods(
    left: AccountPerformanceSeries,
    right: AccountPerformanceSeries,
    *,
    kind: ComparisonKind,
    left_behavior: PeriodBehaviorSummary,
    right_behavior: PeriodBehaviorSummary,
    left_lookthrough: LookthroughResult | None = None,
    right_lookthrough: LookthroughResult | None = None,
) -> AccountPeriodComparison:
    """Return simple right-minus-left differences for a validated account pair.

    Professional periods must use the same observed calendar-date schedule.
    Self periods must belong to one account and be chronological/non-overlapping;
    a shared end/start date is allowed as the normal rebasing boundary.  The
    differences are descriptions, not a score, ranking, or causal attribution.
    """
    if kind not in ("self_periods", "professional"):
        raise AccountComparisonError("unsupported comparison kind")
    if left.method_id != right.method_id:
        raise AccountComparisonError("performance method ids must match")
    if left.method_version != right.method_version:
        raise AccountComparisonError("performance method versions must match")
    if left.base_currency != right.base_currency:
        raise AccountComparisonError("performance currencies must match")
    if left.data_tier != right.data_tier:
        raise AccountComparisonError("performance data tiers must match")
    _validate_behavior(left, left_behavior, "left")
    _validate_behavior(right, right_behavior, "right")
    if left_behavior.method_id != right_behavior.method_id:
        raise AccountComparisonError("behavior method ids must match")
    if left_behavior.method_version != right_behavior.method_version:
        raise AccountComparisonError("behavior method versions must match")

    if kind == "professional":
        if _performance_dates(left) != _performance_dates(right):
            raise AccountComparisonError("professional comparison requires exact matching observation dates")

    else:
        if left.account_id != right.account_id:
            raise AccountComparisonError("self-period comparison requires the same account_id")
        if left.period_end > right.period_start:
            raise AccountComparisonError("self-period comparison requires chronological non-overlapping periods")

    if (left_lookthrough is None) != (right_lookthrough is None):
        raise AccountComparisonError("lookthrough must be supplied for both accounts or neither")
    overlap: tuple[UnderlyingOverlap, ...] = ()
    if left_lookthrough is not None and right_lookthrough is not None:
        if left_lookthrough.method_id != right_lookthrough.method_id:
            raise AccountComparisonError("lookthrough method ids must match")
        if left_lookthrough.method_version != right_lookthrough.method_version:
            raise AccountComparisonError("lookthrough method versions must match")
        if left_lookthrough.max_depth != right_lookthrough.max_depth:
            raise AccountComparisonError("lookthrough max_depth must match")
        if not _same_calendar_date(left_lookthrough.as_of, left.period_end):
            raise AccountComparisonError("left lookthrough as_of does not match performance period end")
        if not _same_calendar_date(right_lookthrough.as_of, right.period_end):
            raise AccountComparisonError("right lookthrough as_of does not match performance period end")
        overlap = _overlap(left_lookthrough, right_lookthrough)

    differences = (
        _difference("period_return", 100.0 * left.period_return, 100.0 * right.period_return, "percentage_points"),
        _difference("max_drawdown_magnitude", 100.0 * left.max_drawdown_magnitude,
                    100.0 * right.max_drawdown_magnitude, "percentage_points"),
        _difference("mean_daily_turnover", None if left_behavior.mean_daily_turnover is None else 100.0 * left_behavior.mean_daily_turnover,
                    None if right_behavior.mean_daily_turnover is None else 100.0 * right_behavior.mean_daily_turnover,
                    "percentage_points"),
        _difference("portfolio_hhi", left_behavior.hhi_end, right_behavior.hhi_end, "index"),
        _difference("recorded_fee_total", left_behavior.recorded_fee_total,
                    right_behavior.recorded_fee_total, left.base_currency),
    )
    references = _method_refs(left, right, left_behavior, right_behavior, left_lookthrough, right_lookthrough)
    payload = {
        "method_id": METHOD_ID, "method_version": METHOD_VERSION, "kind": kind,
        "currency": left.base_currency, "data_tier": left.data_tier,
        "left": [left.account_id, left.period_start.isoformat(), left.period_end.isoformat()],
        "right": [right.account_id, right.period_start.isoformat(), right.period_end.isoformat()],
        "method_references": [(item.source, item.method_id, item.method_version) for item in references],
        "lookthrough_ids": [
            None if left_lookthrough is None else left_lookthrough.lookthrough_id,
            None if right_lookthrough is None else right_lookthrough.lookthrough_id,
        ],
        "differences": [item.__dict__ if hasattr(item, "__dict__") else
                        (item.metric_id, item.left_value, item.right_value, item.right_minus_left, item.unit)
                        for item in differences],
        "overlap": [(item.asset_id, item.left_weight, item.right_weight, item.overlap_weight) for item in overlap],
    }
    comparison_id = "account_compare_" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return AccountPeriodComparison(
        comparison_id, METHOD_ID, METHOD_VERSION, kind, left.base_currency, left.data_tier,
        left.account_id, right.account_id, left.period_start.isoformat(), left.period_end.isoformat(),
        right.period_start.isoformat(), right.period_end.isoformat(), references, differences, overlap,
        (
            "Differences are factual right-minus-left values, not a capability score, ranking, or causal attribution.",
            "Account ownership and authorization must be bound by the caller before comparison.",
            "Self-period samples may have different observation counts; turnover is shown as a daily mean, not a frequency verdict.",
        ),
    )
