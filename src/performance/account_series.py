"""Deterministic account-return series over authoritative account valuations.

This is deliberately a thin performance projection, not another ledger or PnL
engine.  Fixed-cash account values come from the existing vectorbt replay.
Accounts with external cash flows must instead provide authoritative before-
flow and after-flow valuation boundaries, including source ordering evidence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

import empyrical
import empyrical.stats
import numpy as np
import pandas as pd

from src.evidence.contracts import DataTier


ACCOUNT_PERFORMANCE_METHOD_VERSION: Final = "1.0.0"
ACCOUNT_FIXED_CASH_METHOD_ID: Final = "account_fixed_cash_twr_empyrical_v1"
ACCOUNT_FLOW_TWR_METHOD_ID: Final = "account_external_flow_twr_exact_boundary_empyrical_v1"
MINIMUM_DAILY_RISK_RETURN_OBSERVATIONS: Final = 20

BoundaryStage = Literal["after_external_flow", "before_external_flow"]

_DATA_TIERS: Final = frozenset(
    {"synthetic", "demo", "authorized_beta", "production"}
)


class AccountPerformanceSeriesError(ValueError):
    """Inputs do not establish one bounded, flow-neutral account series."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountPerformanceSeriesError(f"{field_name} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, field_name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise AccountPerformanceSeriesError(f"{field_name} must be a timestamp") from exc
    if pd.isna(result):
        raise AccountPerformanceSeriesError(f"{field_name} cannot be NaT")
    return result


def _finite_float(value: object, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise AccountPerformanceSeriesError(f"{field_name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AccountPerformanceSeriesError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise AccountPerformanceSeriesError(f"{field_name} must be finite")
    if positive and result <= 0:
        raise AccountPerformanceSeriesError(f"{field_name} must be positive")
    return result


def _event_key(boundary: AccountValuationBoundary) -> tuple[int, int]:
    return int(boundary.observed_at.value), boundary.event_sequence


def _normalize_source_refs(source_refs: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_required_text(item, "source_ref") for item in source_refs}))


def _calendar_date(value: object, field_name: str) -> date:
    return _timestamp(value, field_name).date()


def _replay_calendar_boundary(value: object, field_name: str) -> pd.Timestamp:
    """Require an unambiguous date-only bound for daily EOD replay windows."""

    result = _timestamp(value, field_name)
    if result.tz is not None or result != result.normalize():
        raise AccountPerformanceSeriesError(
            f"{field_name} must be a timezone-free date-only value for daily EOD replay"
        )
    return result


@dataclass(frozen=True, slots=True)
class AccountValuationBoundary:
    """One sourced valuation immediately before or after an external flow."""

    observed_at: pd.Timestamp
    event_sequence: int
    stage: BoundaryStage
    value: float
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))
        if isinstance(self.event_sequence, bool) or not isinstance(self.event_sequence, int):
            raise AccountPerformanceSeriesError("event_sequence must be an integer")
        if self.event_sequence < 0:
            raise AccountPerformanceSeriesError("event_sequence must be non-negative")
        if self.stage not in {"after_external_flow", "before_external_flow"}:
            raise AccountPerformanceSeriesError("unsupported valuation boundary stage")
        object.__setattr__(self, "value", _finite_float(self.value, "value", positive=True))
        object.__setattr__(self, "source_ref", _required_text(self.source_ref, "source_ref"))


@dataclass(frozen=True, slots=True)
class ExternalCashFlow:
    """One external owner cash movement between authoritative valuations."""

    flow_id: str
    account_id: str
    occurred_at: pd.Timestamp
    event_sequence: int
    amount: float
    currency: str
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _required_text(self.flow_id, "flow_id"))
        object.__setattr__(self, "account_id", _required_text(self.account_id, "account_id"))
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at, "occurred_at"))
        if isinstance(self.event_sequence, bool) or not isinstance(self.event_sequence, int):
            raise AccountPerformanceSeriesError("event_sequence must be an integer")
        if self.event_sequence < 0:
            raise AccountPerformanceSeriesError("event_sequence must be non-negative")
        amount = _finite_float(self.amount, "amount")
        if amount == 0:
            raise AccountPerformanceSeriesError("external flow amount cannot be zero")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", _required_text(self.currency, "currency").upper())
        object.__setattr__(self, "source_ref", _required_text(self.source_ref, "source_ref"))


@dataclass(frozen=True, slots=True)
class FlowNeutralReturnInterval:
    """A return interval containing no external flow in its interior.

    ``preceding_flows`` bridges the preceding interval's end-before-flow
    valuation to this interval's start-after-flow valuation.  The first
    interval cannot own preceding flows: its start is the selected period
    boundary and is already after any earlier flow.
    """

    start_after_flow: AccountValuationBoundary
    end_before_flow: AccountValuationBoundary
    preceding_flows: tuple[ExternalCashFlow, ...] = ()

    def __post_init__(self) -> None:
        if self.start_after_flow.stage != "after_external_flow":
            raise AccountPerformanceSeriesError(
                "interval start must be an after_external_flow valuation"
            )
        if self.end_before_flow.stage != "before_external_flow":
            raise AccountPerformanceSeriesError(
                "interval end must be a before_external_flow valuation"
            )
        if _event_key(self.end_before_flow) <= _event_key(self.start_after_flow):
            raise AccountPerformanceSeriesError("interval end must follow interval start")
        flows = tuple(
            sorted(
                tuple(self.preceding_flows),
                key=lambda item: (int(item.occurred_at.value), item.event_sequence, item.flow_id),
            )
        )
        object.__setattr__(self, "preceding_flows", flows)


@dataclass(frozen=True, slots=True)
class RiskFreeReturnSeries:
    """Exact periodic risk-free returns aligned by ``DailyRiskPolicy``."""

    currency: str
    source_ref: str
    as_of: pd.Timestamp
    period_returns: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required_text(self.currency, "currency").upper())
        object.__setattr__(self, "source_ref", _required_text(self.source_ref, "source_ref"))
        object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        returns = tuple(
            _finite_float(value, "risk_free period return") for value in self.period_returns
        )
        if any(value <= -1 for value in returns):
            raise AccountPerformanceSeriesError("risk-free period returns must exceed -100%")
        object.__setattr__(self, "period_returns", returns)


@dataclass(frozen=True, slots=True)
class DailyRiskPolicy:
    """Caller-owned proof of a complete daily observation schedule."""

    expected_observation_dates: tuple[date, ...]
    annualization_factor: int
    risk_free: RiskFreeReturnSeries | None = None

    def __post_init__(self) -> None:
        dates = tuple(
            _calendar_date(item, "expected_observation_date")
            for item in self.expected_observation_dates
        )
        if len(dates) < 2:
            raise AccountPerformanceSeriesError(
                "daily risk policy requires at least two observation dates"
            )
        if any(left >= right for left, right in zip(dates, dates[1:])):
            raise AccountPerformanceSeriesError(
                "expected daily observation dates must be strictly chronological"
            )
        if isinstance(self.annualization_factor, bool) or not isinstance(
            self.annualization_factor, int
        ):
            raise AccountPerformanceSeriesError("annualization_factor must be an integer")
        if self.annualization_factor <= 0:
            raise AccountPerformanceSeriesError("annualization_factor must be positive")
        if self.risk_free is not None:
            expected_returns = len(dates) - 1
            if len(self.risk_free.period_returns) != expected_returns:
                raise AccountPerformanceSeriesError(
                    "risk-free returns must align one-for-one with daily return intervals"
                )
            if self.risk_free.as_of.date() < dates[-1]:
                raise AccountPerformanceSeriesError(
                    "risk-free series as_of cannot precede its final observation date"
                )
        object.__setattr__(self, "expected_observation_dates", dates)


@dataclass(frozen=True, slots=True)
class AccountPerformancePoint:
    """One immutable account-value and flow-neutral performance observation."""

    observed_at: pd.Timestamp
    event_sequence: int
    account_value: float
    cumulative_nav: float
    period_return: float | None
    drawdown: float
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))
        if isinstance(self.event_sequence, bool) or not isinstance(self.event_sequence, int):
            raise AccountPerformanceSeriesError("event_sequence must be an integer")
        if self.event_sequence < 0:
            raise AccountPerformanceSeriesError("event_sequence must be non-negative")
        object.__setattr__(
            self,
            "account_value",
            _finite_float(self.account_value, "account_value", positive=True),
        )
        object.__setattr__(
            self,
            "cumulative_nav",
            _finite_float(self.cumulative_nav, "cumulative_nav", positive=True),
        )
        if self.period_return is not None:
            period_return = _finite_float(self.period_return, "period_return")
            if period_return <= -1:
                raise AccountPerformanceSeriesError("period_return must exceed -100%")
            object.__setattr__(self, "period_return", period_return)
        drawdown = _finite_float(self.drawdown, "drawdown")
        if drawdown > 1e-12 or drawdown <= -1:
            raise AccountPerformanceSeriesError(
                "drawdown must be non-positive and greater than -100%"
            )
        object.__setattr__(self, "drawdown", min(0.0, drawdown))
        sources = _normalize_source_refs(tuple(self.source_refs))
        if not sources:
            raise AccountPerformanceSeriesError("performance point requires source_refs")
        object.__setattr__(self, "source_refs", sources)

    def as_dict(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "event_sequence": self.event_sequence,
            "account_value": self.account_value,
            "cumulative_nav": self.cumulative_nav,
            "period_return": self.period_return,
            "drawdown": self.drawdown,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class AccountPerformanceSeries:
    """Versioned account TWR, drawdown path, and optional daily risk metrics."""

    account_id: str
    base_currency: str
    method_id: str
    method_version: str
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    as_of: pd.Timestamp
    points: tuple[AccountPerformancePoint, ...]
    period_return: float
    max_drawdown_magnitude: float
    max_drawdown_peak_at: pd.Timestamp | None
    max_drawdown_trough_at: pd.Timestamp | None
    max_drawdown_recovered_at: pd.Timestamp | None
    annualized_volatility: float | None
    sharpe_ratio: float | None
    annualization_factor: int | None
    return_observation_count: int
    data_tier: DataTier
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("account_id", "base_currency", "method_id", "method_version"):
            normalized = _required_text(getattr(self, field_name), field_name)
            if field_name == "base_currency":
                normalized = normalized.upper()
            object.__setattr__(self, field_name, normalized)
        for field_name in ("period_start", "period_end", "as_of"):
            object.__setattr__(
                self,
                field_name,
                _timestamp(getattr(self, field_name), field_name),
            )
        points = tuple(self.points)
        if len(points) < 2:
            raise AccountPerformanceSeriesError("points require at least one return interval")
        if points[0].period_return is not None:
            raise AccountPerformanceSeriesError("the first point period_return must be None")
        if any(point.period_return is None for point in points[1:]):
            raise AccountPerformanceSeriesError(
                "every point after the first requires period_return"
            )
        if any(
            (int(left.observed_at.value), left.event_sequence)
            >= (int(right.observed_at.value), right.event_sequence)
            for left, right in zip(points, points[1:])
        ):
            raise AccountPerformanceSeriesError("points must be strictly chronological")
        if self.period_start != points[0].observed_at:
            raise AccountPerformanceSeriesError("period_start must equal the first point")
        if self.period_end != points[-1].observed_at:
            raise AccountPerformanceSeriesError("period_end must equal the final point")
        if self.as_of.date() < self.period_end.date():
            raise AccountPerformanceSeriesError("as_of cannot precede period_end")
        object.__setattr__(self, "points", points)

        period_return = _finite_float(self.period_return, "period_return")
        if period_return <= -1:
            raise AccountPerformanceSeriesError("period_return must exceed -100%")
        object.__setattr__(self, "period_return", period_return)
        magnitude = _finite_float(
            self.max_drawdown_magnitude, "max_drawdown_magnitude"
        )
        if magnitude < 0 or magnitude >= 1:
            raise AccountPerformanceSeriesError(
                "max_drawdown_magnitude must be in [0, 1) for positive account values"
            )
        object.__setattr__(self, "max_drawdown_magnitude", magnitude)
        for field_name in (
            "max_drawdown_peak_at",
            "max_drawdown_trough_at",
            "max_drawdown_recovered_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _timestamp(value, field_name))
        if magnitude == 0:
            if any(
                value is not None
                for value in (
                    self.max_drawdown_peak_at,
                    self.max_drawdown_trough_at,
                    self.max_drawdown_recovered_at,
                )
            ):
                raise AccountPerformanceSeriesError(
                    "zero drawdown cannot have peak, trough, or recovery dates"
                )
        elif self.max_drawdown_peak_at is None or self.max_drawdown_trough_at is None:
            raise AccountPerformanceSeriesError(
                "a non-zero drawdown requires peak and trough dates"
            )
        if (
            self.max_drawdown_peak_at is not None
            and self.max_drawdown_trough_at is not None
            and self.max_drawdown_peak_at > self.max_drawdown_trough_at
        ):
            raise AccountPerformanceSeriesError("drawdown peak cannot follow its trough")
        if (
            self.max_drawdown_recovered_at is not None
            and self.max_drawdown_trough_at is not None
            and self.max_drawdown_recovered_at <= self.max_drawdown_trough_at
        ):
            raise AccountPerformanceSeriesError("drawdown recovery must follow its trough")

        for field_name in ("annualized_volatility", "sharpe_ratio"):
            value = getattr(self, field_name)
            if value is not None:
                normalized = _finite_float(value, field_name)
                if field_name == "annualized_volatility" and normalized < 0:
                    raise AccountPerformanceSeriesError(
                        "annualized_volatility cannot be negative"
                    )
                object.__setattr__(self, field_name, normalized)
        if self.annualization_factor is not None:
            if isinstance(self.annualization_factor, bool) or not isinstance(
                self.annualization_factor, int
            ):
                raise AccountPerformanceSeriesError(
                    "annualization_factor must be an integer or None"
                )
            if self.annualization_factor <= 0:
                raise AccountPerformanceSeriesError(
                    "annualization_factor must be positive"
                )
        if isinstance(self.return_observation_count, bool) or not isinstance(
            self.return_observation_count, int
        ):
            raise AccountPerformanceSeriesError(
                "return_observation_count must be an integer"
            )
        if self.return_observation_count != len(points) - 1:
            raise AccountPerformanceSeriesError(
                "return_observation_count must equal len(points) - 1"
            )
        if self.data_tier not in _DATA_TIERS:
            raise AccountPerformanceSeriesError("unsupported data_tier")
        sources = _normalize_source_refs(tuple(self.source_refs))
        if not sources:
            raise AccountPerformanceSeriesError("series requires source_refs")
        object.__setattr__(self, "source_refs", sources)
        object.__setattr__(
            self,
            "limitations",
            tuple(
                dict.fromkeys(
                    _required_text(item, "limitation") for item in self.limitations
                )
            ),
        )

    def as_dict(self) -> dict[str, object]:
        def optional_timestamp(value: pd.Timestamp | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "account_id": self.account_id,
            "base_currency": self.base_currency,
            "method_id": self.method_id,
            "method_version": self.method_version,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "as_of": self.as_of.isoformat(),
            "points": [point.as_dict() for point in self.points],
            "period_return": self.period_return,
            "max_drawdown_magnitude": self.max_drawdown_magnitude,
            "max_drawdown_peak_at": optional_timestamp(self.max_drawdown_peak_at),
            "max_drawdown_trough_at": optional_timestamp(self.max_drawdown_trough_at),
            "max_drawdown_recovered_at": optional_timestamp(
                self.max_drawdown_recovered_at
            ),
            "annualized_volatility": self.annualized_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "annualization_factor": self.annualization_factor,
            "return_observation_count": self.return_observation_count,
            "data_tier": self.data_tier,
            "source_refs": list(self.source_refs),
            "limitations": list(self.limitations),
        }


def _validate_common_metadata(
    *,
    account_id: str,
    base_currency: str,
    source_refs: Sequence[str],
    data_tier: DataTier,
    as_of: object,
) -> tuple[str, str, tuple[str, ...], DataTier, pd.Timestamp]:
    normalized_account = _required_text(account_id, "account_id")
    normalized_currency = _required_text(base_currency, "base_currency").upper()
    normalized_sources = _normalize_source_refs(tuple(source_refs))
    if not normalized_sources:
        raise AccountPerformanceSeriesError("at least one source_ref is required")
    if data_tier not in _DATA_TIERS:
        raise AccountPerformanceSeriesError("unsupported data_tier")
    return (
        normalized_account,
        normalized_currency,
        normalized_sources,
        data_tier,
        _timestamp(as_of, "as_of"),
    )


def _risk_statistics(
    points_at: tuple[pd.Timestamp, ...],
    returns: np.ndarray,
    *,
    base_currency: str,
    risk_policy: DailyRiskPolicy | None,
) -> tuple[float | None, float | None, int | None, tuple[str, ...], tuple[str, ...]]:
    if risk_policy is None:
        return (
            None,
            None,
            None,
            ("daily_risk_statistics_require_explicit_complete_cadence",),
            (),
        )

    actual_dates = tuple(item.date() for item in points_at)
    if actual_dates != risk_policy.expected_observation_dates:
        raise AccountPerformanceSeriesError(
            "daily risk policy dates must exactly match account observation dates"
        )
    if len(returns) < MINIMUM_DAILY_RISK_RETURN_OBSERVATIONS:
        return (
            None,
            None,
            risk_policy.annualization_factor,
            (
                "daily_risk_statistics_require_at_least_20_return_observations",
            ),
            (risk_policy.risk_free.source_ref,) if risk_policy.risk_free else (),
        )

    volatility = float(
        empyrical.annual_volatility(
            returns,
            period="daily",
            annualization=risk_policy.annualization_factor,
        )
    )
    if not math.isfinite(volatility):
        volatility = None

    risk_free = risk_policy.risk_free
    if risk_free is None:
        return (
            volatility,
            None,
            risk_policy.annualization_factor,
            ("sharpe_ratio_requires_exact_base_currency_risk_free_returns",),
            (),
        )
    if risk_free.currency != base_currency:
        raise AccountPerformanceSeriesError(
            "risk-free return currency must match the account base currency"
        )
    risk_free_array = np.asarray(risk_free.period_returns, dtype=np.float64)
    excess = returns - risk_free_array
    if np.isclose(np.std(excess, ddof=1), 0.0, rtol=0.0, atol=1e-15):
        return (
            volatility,
            None,
            risk_policy.annualization_factor,
            ("sharpe_ratio_undefined_for_zero_excess_return_volatility",),
            (risk_free.source_ref,),
        )
    sharpe = float(
        empyrical.sharpe_ratio(
            returns,
            risk_free=risk_free_array,
            period="daily",
            annualization=risk_policy.annualization_factor,
        )
    )
    if not math.isfinite(sharpe):
        sharpe = None
    return (
        volatility,
        sharpe,
        risk_policy.annualization_factor,
        (),
        (risk_free.source_ref,),
    )


def _build_series(
    *,
    account_id: str,
    base_currency: str,
    method_id: str,
    observed_at: tuple[pd.Timestamp, ...],
    event_sequences: tuple[int, ...],
    account_values: tuple[float, ...],
    period_returns: tuple[float, ...],
    point_source_refs: tuple[tuple[str, ...], ...],
    source_refs: tuple[str, ...],
    data_tier: DataTier,
    as_of: pd.Timestamp,
    risk_policy: DailyRiskPolicy | None,
    method_limitations: tuple[str, ...],
) -> AccountPerformanceSeries:
    if len(observed_at) < 2 or len(period_returns) != len(observed_at) - 1:
        raise AccountPerformanceSeriesError(
            "account performance requires at least one return interval"
        )
    if not (
        len(observed_at)
        == len(event_sequences)
        == len(account_values)
        == len(point_source_refs)
    ):
        raise AccountPerformanceSeriesError("internal account series lengths disagree")
    if as_of.date() < observed_at[-1].date():
        raise AccountPerformanceSeriesError("as_of cannot precede period_end")

    returns = np.asarray(period_returns, dtype=np.float64)
    nav_tail = np.asarray(
        empyrical.cum_returns(returns, starting_value=100.0), dtype=np.float64
    )
    nav = np.concatenate((np.asarray([100.0]), nav_tail))
    drawdowns = np.asarray(empyrical.stats.drawdown_series(returns), dtype=np.float64)
    if drawdowns.shape != nav.shape:
        raise AccountPerformanceSeriesError("empyrical drawdown output shape is unsupported")
    max_drawdown = float(empyrical.max_drawdown(returns))
    if not np.all(np.isfinite(nav)) or not np.all(np.isfinite(drawdowns)):
        raise AccountPerformanceSeriesError("empyrical produced non-finite performance values")
    if not np.isclose(drawdowns.min(), max_drawdown, rtol=1e-12, atol=1e-12):
        raise AccountPerformanceSeriesError("empyrical drawdown calculations disagree")

    peak_at: pd.Timestamp | None = None
    trough_at: pd.Timestamp | None = None
    recovered_at: pd.Timestamp | None = None
    max_drawdown_magnitude = max(0.0, -max_drawdown)
    if max_drawdown_magnitude > 0:
        trough_index = int(np.argmin(drawdowns))
        running_peak = float(np.max(nav[: trough_index + 1]))
        peak_candidates = np.flatnonzero(
            np.isclose(nav[: trough_index + 1], running_peak, rtol=1e-12, atol=1e-12)
        )
        peak_index = int(peak_candidates[-1])
        recovery_candidates = np.flatnonzero(
            nav[trough_index + 1 :] >= running_peak * (1.0 - 1e-12)
        )
        peak_at = observed_at[peak_index]
        trough_at = observed_at[trough_index]
        if len(recovery_candidates):
            recovered_at = observed_at[trough_index + 1 + int(recovery_candidates[0])]

    volatility, sharpe, annualization, risk_limits, risk_sources = _risk_statistics(
        observed_at,
        returns,
        base_currency=base_currency,
        risk_policy=risk_policy,
    )
    all_source_refs = _normalize_source_refs((*source_refs, *risk_sources))
    points = tuple(
        AccountPerformancePoint(
            observed_at=timestamp,
            event_sequence=event_sequences[index],
            account_value=account_values[index],
            cumulative_nav=float(nav[index]),
            period_return=None if index == 0 else float(returns[index - 1]),
            drawdown=float(drawdowns[index]),
            source_refs=point_source_refs[index],
        )
        for index, timestamp in enumerate(observed_at)
    )
    return AccountPerformanceSeries(
        account_id=account_id,
        base_currency=base_currency,
        method_id=method_id,
        method_version=ACCOUNT_PERFORMANCE_METHOD_VERSION,
        period_start=observed_at[0],
        period_end=observed_at[-1],
        as_of=as_of,
        points=points,
        period_return=float(nav[-1] / 100.0 - 1.0),
        max_drawdown_magnitude=max_drawdown_magnitude,
        max_drawdown_peak_at=peak_at,
        max_drawdown_trough_at=trough_at,
        max_drawdown_recovered_at=recovered_at,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        annualization_factor=annualization,
        return_observation_count=len(returns),
        data_tier=data_tier,
        source_refs=all_source_refs,
        limitations=tuple(dict.fromkeys((*method_limitations, *risk_limits))),
    )


def _portfolio_value_series(portfolio_or_replay: object) -> pd.Series:
    portfolio = getattr(portfolio_or_replay, "portfolio", portfolio_or_replay)
    value_method = getattr(portfolio, "value", None)
    if not callable(value_method):
        raise AccountPerformanceSeriesError(
            "portfolio_or_replay must expose vectorbt portfolio.value()"
        )
    raw_values = value_method()
    if isinstance(raw_values, pd.DataFrame):
        if raw_values.shape[1] != 1:
            raise AccountPerformanceSeriesError(
                "portfolio.value() must be one cash-shared account series"
            )
        raw_values = raw_values.iloc[:, 0]
    if not isinstance(raw_values, pd.Series):
        raise AccountPerformanceSeriesError("portfolio.value() must return a pandas Series")
    values = raw_values.copy(deep=True)
    try:
        values.index = pd.to_datetime(values.index, errors="raise")
        values = pd.to_numeric(values, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise AccountPerformanceSeriesError(
            "portfolio values require valid timestamps and numeric values"
        ) from exc
    if values.empty or values.index.hasnans or values.index.duplicated().any():
        raise AccountPerformanceSeriesError(
            "portfolio values require non-empty, unique, non-NaT timestamps"
        )
    if values.isna().any() or not np.isfinite(values.to_numpy()).all():
        raise AccountPerformanceSeriesError("portfolio values cannot be missing or non-finite")
    if (values <= 0).any():
        raise AccountPerformanceSeriesError("portfolio values must remain positive")
    return values.sort_index(kind="stable")


def build_account_performance_from_replay(
    portfolio_or_replay: object,
    *,
    account_id: str,
    base_currency: str,
    source_refs: Sequence[str],
    data_tier: DataTier,
    as_of: object,
    start_at: object | None = None,
    risk_policy: DailyRiskPolicy | None = None,
) -> AccountPerformanceSeries:
    """Project a fixed-external-cash vectorbt replay into daily account TWR.

    Bounds must be timezone-free date-only values.  Within each selected date,
    the last real replay valuation timestamp is used as EOD; no price or value
    is filled.  Both requested boundary dates must have an actual observation.
    """

    account, currency, sources, tier, normalized_as_of = _validate_common_metadata(
        account_id=account_id,
        base_currency=base_currency,
        source_refs=source_refs,
        data_tier=data_tier,
        as_of=as_of,
    )
    normalized_as_of = _replay_calendar_boundary(normalized_as_of, "as_of")
    values = _portfolio_value_series(portfolio_or_replay)
    start_date = (
        values.index[0].date()
        if start_at is None
        else _replay_calendar_boundary(start_at, "start_at").date()
    )
    end_date = normalized_as_of.date()
    if end_date < start_date:
        raise AccountPerformanceSeriesError("as_of cannot precede start_at")

    observation_dates = pd.Index(timestamp.date() for timestamp in values.index)
    if start_date not in observation_dates:
        raise AccountPerformanceSeriesError("start_at requires an exact valuation date")
    if end_date not in observation_dates:
        raise AccountPerformanceSeriesError("as_of requires an exact valuation date")
    mask = (observation_dates >= start_date) & (observation_dates <= end_date)
    selected = values.loc[mask]
    selected_dates = pd.Index(timestamp.date() for timestamp in selected.index)
    # Sorting above makes groupby-last the actual final observation of each date.
    eod = selected.groupby(selected_dates, sort=True).tail(1)
    if len(eod) < 2:
        raise AccountPerformanceSeriesError(
            "fixed-cash replay window requires at least two daily valuations"
        )

    raw = eod.to_numpy(dtype=np.float64, copy=True)
    returns = tuple(float(value) for value in raw[1:] / raw[:-1] - 1.0)
    point_sources = tuple(sources for _ in range(len(eod)))
    return _build_series(
        account_id=account,
        base_currency=currency,
        method_id=ACCOUNT_FIXED_CASH_METHOD_ID,
        observed_at=tuple(pd.Timestamp(value) for value in eod.index),
        event_sequences=tuple(0 for _ in range(len(eod))),
        account_values=tuple(float(value) for value in raw),
        period_returns=returns,
        point_source_refs=point_sources,
        source_refs=sources,
        data_tier=tier,
        as_of=normalized_as_of,
        risk_policy=risk_policy,
        method_limitations=(
            "fixed_external_cash_only",
            "values_are_authoritative_existing_vectorbt_replay_output",
            "positive_long_only_base_currency_scope",
            "daily_eod_is_last_actual_replay_observation_no_fill",
            "replay_bounds_are_timezone_free_calendar_dates_with_eod_semantics",
            "corporate_actions_and_transfers_are_not_calculated_here",
        ),
    )


def build_account_performance_from_intervals(
    intervals: Sequence[FlowNeutralReturnInterval],
    *,
    account_id: str,
    base_currency: str,
    source_refs: Sequence[str],
    data_tier: DataTier,
    as_of: object,
    risk_policy: DailyRiskPolicy | None = None,
) -> AccountPerformanceSeries:
    """Chain exact no-flow intervals into flow-neutral TWR and NAV.

    The caller supplies authoritative valuations.  This function validates
    external-flow ownership, order, currency, and before/after reconciliation;
    it never derives cash, positions, trades, dividends, or corporate actions.
    """

    account, currency, sources, tier, normalized_as_of = _validate_common_metadata(
        account_id=account_id,
        base_currency=base_currency,
        source_refs=source_refs,
        data_tier=data_tier,
        as_of=as_of,
    )
    ordered = tuple(sorted(tuple(intervals), key=lambda item: _event_key(item.start_after_flow)))
    if not ordered:
        raise AccountPerformanceSeriesError("at least one return interval is required")
    if ordered[0].preceding_flows:
        raise AccountPerformanceSeriesError(
            "the first interval cannot re-own cash flows before the selected period"
        )

    seen_flow_ids: set[str] = set()
    all_sources = set(sources)
    for index, interval in enumerate(ordered):
        all_sources.add(interval.start_after_flow.source_ref)
        all_sources.add(interval.end_before_flow.source_ref)
        if index == 0:
            continue
        previous = ordered[index - 1].end_before_flow
        current = interval.start_after_flow
        if previous.observed_at != current.observed_at:
            raise AccountPerformanceSeriesError(
                "adjacent intervals require exact shared boundary timestamps; no gap is filled"
            )
        flows = interval.preceding_flows
        if not flows:
            if previous.event_sequence != current.event_sequence:
                raise AccountPerformanceSeriesError(
                    "a changed boundary sequence requires explicit intervening external flows"
                )
            if not np.isclose(previous.value, current.value, rtol=1e-12, atol=1e-9):
                raise AccountPerformanceSeriesError(
                    "account value changed between intervals without an external flow"
                )
            continue

        previous_sequence = previous.event_sequence
        for flow in flows:
            if flow.flow_id in seen_flow_ids:
                raise AccountPerformanceSeriesError("external flow_id must be unique")
            seen_flow_ids.add(flow.flow_id)
            if flow.account_id != account:
                raise AccountPerformanceSeriesError(
                    "external flow account ownership does not match account_id"
                )
            if flow.currency != currency:
                raise AccountPerformanceSeriesError(
                    "external flow currency does not match base_currency"
                )
            if flow.occurred_at != previous.observed_at:
                raise AccountPerformanceSeriesError(
                    "external flow must share the exact before/after valuation timestamp"
                )
            if flow.event_sequence <= previous_sequence:
                raise AccountPerformanceSeriesError(
                    "external flows require unique source order after before-flow valuation"
                )
            previous_sequence = flow.event_sequence
            all_sources.add(flow.source_ref)
        if current.event_sequence <= previous_sequence:
            raise AccountPerformanceSeriesError(
                "after-flow valuation must follow every external flow in source order"
            )
        expected_after_value = previous.value + sum(flow.amount for flow in flows)
        if not np.isclose(expected_after_value, current.value, rtol=1e-12, atol=1e-9):
            raise AccountPerformanceSeriesError(
                "external flows do not reconcile before-flow and after-flow account values"
            )

    observed_at = (ordered[0].start_after_flow.observed_at,) + tuple(
        interval.end_before_flow.observed_at for interval in ordered
    )
    event_sequences = (ordered[0].start_after_flow.event_sequence,) + tuple(
        interval.end_before_flow.event_sequence for interval in ordered
    )
    if any(
        (int(left_time.value), left_sequence)
        >= (int(right_time.value), right_sequence)
        for left_time, left_sequence, right_time, right_sequence in zip(
            observed_at,
            event_sequences,
            observed_at[1:],
            event_sequences[1:],
        )
    ):
        raise AccountPerformanceSeriesError("performance points must be strictly chronological")
    account_values = (ordered[0].start_after_flow.value,) + tuple(
        interval.end_before_flow.value for interval in ordered
    )
    returns = tuple(
        interval.end_before_flow.value / interval.start_after_flow.value - 1.0
        for interval in ordered
    )
    point_sources = (
        (ordered[0].start_after_flow.source_ref,),
    ) + tuple((interval.end_before_flow.source_ref,) for interval in ordered)
    return _build_series(
        account_id=account,
        base_currency=currency,
        method_id=ACCOUNT_FLOW_TWR_METHOD_ID,
        observed_at=observed_at,
        event_sequences=event_sequences,
        account_values=account_values,
        period_returns=returns,
        point_source_refs=point_sources,
        source_refs=_normalize_source_refs(tuple(all_sources)),
        data_tier=tier,
        as_of=normalized_as_of,
        risk_policy=risk_policy,
        method_limitations=(
            "authoritative_external_flow_boundaries_required",
            "no_trade_cash_position_or_corporate_action_accounting_is_performed",
            "positive_long_only_base_currency_scope",
            "drawdown_is_observed_only_at_supplied_valuation_boundaries",
        ),
    )
