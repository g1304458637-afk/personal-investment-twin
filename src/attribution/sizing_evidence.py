"""Deterministic cross-asset sizing evidence against an equal-weight baseline.

The output compares two historical vectorbt portfolios.  It is not sizing
skill, alpha, causal attribution, or a recommendation about future weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from src.core.portfolio_replay import (
    PortfolioReplayError,
    replay_multi_asset_executions,
    simulate_target_weight_interval,
)


Comparison = Literal[
    "outperformed_baseline",
    "underperformed_baseline",
    "matched_baseline",
]
EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class SizingDecisionEvidence:
    """Observed allocation evidence for one completed decision interval.

    ``interval_end_time`` is valued immediately before any executions at that
    next decision point.  Weights are fractions of total portfolio value and
    therefore sum to ``risky_exposure`` rather than necessarily to one.
    """

    decision_time: pd.Timestamp
    interval_end_time: pd.Timestamp | None
    active_assets: tuple[str, ...]
    actual_weights: dict[str, float]
    baseline_weights: dict[str, float]
    risky_exposure: float | None
    actual_start_value: float | None
    baseline_start_value: float | None
    actual_end_value: float | None
    baseline_end_value: float | None
    comparison: Comparison | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None


def _insufficient(
    decision_time: pd.Timestamp,
    interval_end_time: pd.Timestamp | None,
    reason: str,
) -> SizingDecisionEvidence:
    return SizingDecisionEvidence(
        decision_time=decision_time,
        interval_end_time=interval_end_time,
        active_assets=(),
        actual_weights={},
        baseline_weights={},
        risky_exposure=None,
        actual_start_value=None,
        baseline_start_value=None,
        actual_end_value=None,
        baseline_end_value=None,
        comparison=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
    )


def _decision_times(executions: pd.DataFrame) -> tuple[pd.Timestamp, ...]:
    if not isinstance(executions, pd.DataFrame) or "event_time" not in executions:
        raise PortfolioReplayError("executions must contain event_time")
    if executions.empty:
        raise PortfolioReplayError("At least one execution is required")
    try:
        times = pd.to_datetime(executions["event_time"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("execution event_time must contain timestamps") from exc
    if times.isna().any():
        raise PortfolioReplayError("execution event_time cannot be null")
    return tuple(pd.Timestamp(value) for value in sorted(times.unique()))


def _comparison(actual_end: float, baseline_end: float) -> Comparison:
    if math.isclose(actual_end, baseline_end, rel_tol=1e-9, abs_tol=1e-8):
        return "matched_baseline"
    if actual_end > baseline_end:
        return "outperformed_baseline"
    return "underperformed_baseline"


def _complete_interval(
    actual_portfolio: object,
    prices: pd.DataFrame,
    decision_time: pd.Timestamp,
    interval_end_time: pd.Timestamp,
) -> SizingDecisionEvidence:
    holdings = actual_portfolio.assets().loc[decision_time]
    if not np.isfinite(holdings.to_numpy(dtype=float)).all():
        raise PortfolioReplayError("Actual asset holdings are invalid")
    if (holdings < 0).any():
        raise PortfolioReplayError("Short positions are unsupported in Sizing Evidence v1")

    active_assets = tuple(sorted(holdings.index[holdings > 0].astype(str)))
    if len(active_assets) < 2:
        raise PortfolioReplayError("Fewer than two active assets at the decision point")

    actual_start_value = float(actual_portfolio.value().loc[decision_time])
    actual_cash = float(actual_portfolio.cash().loc[decision_time])
    risky_exposure = float(actual_portfolio.gross_exposure().loc[decision_time])
    asset_values = actual_portfolio.asset_value(group_by=False).loc[
        decision_time, list(active_assets)
    ]
    state_values = np.array(
        [actual_start_value, actual_cash, risky_exposure, *asset_values.to_numpy()],
        dtype=float,
    )
    if not np.isfinite(state_values).all() or actual_start_value <= 0:
        raise PortfolioReplayError("Actual portfolio state is invalid")
    if actual_cash < -1e-8 or risky_exposure < 0 or risky_exposure > 1.0 + 1e-9:
        raise PortfolioReplayError("Margin exposure is unsupported in Sizing Evidence v1")

    actual_weights = {
        asset: float(asset_values.loc[asset] / actual_start_value)
        for asset in active_assets
    }
    baseline_weight = risky_exposure / len(active_assets)
    baseline_weights = {asset: baseline_weight for asset in active_assets}

    interval_prices = prices.loc[
        (prices.index >= decision_time) & (prices.index <= interval_end_time),
        list(active_assets),
    ]
    if decision_time not in interval_prices.index:
        raise PortfolioReplayError("Missing interval start valuation price")
    if interval_end_time not in interval_prices.index:
        raise PortfolioReplayError("Missing interval end valuation price")

    actual_interval = simulate_target_weight_interval(
        interval_prices,
        init_value=actual_start_value,
        target_weights=actual_weights,
    )
    baseline_interval = simulate_target_weight_interval(
        interval_prices,
        init_value=actual_start_value,
        target_weights=baseline_weights,
    )

    simulated_actual_start = float(actual_interval.value().iloc[0])
    baseline_start_value = float(baseline_interval.value().iloc[0])
    simulated_actual_cash = float(actual_interval.cash().iloc[0])
    baseline_cash = float(baseline_interval.cash().iloc[0])
    simulated_actual_exposure = float(actual_interval.gross_exposure().iloc[0])
    baseline_exposure = float(baseline_interval.gross_exposure().iloc[0])
    invariant_values = np.array(
        [
            simulated_actual_start,
            baseline_start_value,
            simulated_actual_cash,
            baseline_cash,
            simulated_actual_exposure,
            baseline_exposure,
        ],
        dtype=float,
    )
    if not np.isfinite(invariant_values).all():
        raise PortfolioReplayError("vectorbt returned invalid interval start state")
    if not math.isclose(
        simulated_actual_start, baseline_start_value, rel_tol=1e-9, abs_tol=1e-8
    ):
        raise PortfolioReplayError("Actual and baseline start values do not match")
    if not math.isclose(
        simulated_actual_cash, baseline_cash, rel_tol=1e-9, abs_tol=1e-8
    ) or not math.isclose(
        simulated_actual_cash, actual_cash, rel_tol=1e-9, abs_tol=1e-8
    ):
        raise PortfolioReplayError("Actual and baseline cash exposure does not match")
    if not math.isclose(
        simulated_actual_exposure, baseline_exposure, rel_tol=1e-9, abs_tol=1e-12
    ) or not math.isclose(
        simulated_actual_exposure, risky_exposure, rel_tol=1e-9, abs_tol=1e-12
    ):
        raise PortfolioReplayError("Actual and baseline risky exposure does not match")

    actual_end_value = float(actual_interval.value().iloc[-1])
    baseline_end_value = float(baseline_interval.value().iloc[-1])
    if not np.isfinite([actual_end_value, baseline_end_value]).all():
        raise PortfolioReplayError("vectorbt returned invalid interval end value")

    return SizingDecisionEvidence(
        decision_time=decision_time,
        interval_end_time=interval_end_time,
        active_assets=active_assets,
        actual_weights=actual_weights,
        baseline_weights=baseline_weights,
        risky_exposure=risky_exposure,
        actual_start_value=simulated_actual_start,
        baseline_start_value=baseline_start_value,
        actual_end_value=actual_end_value,
        baseline_end_value=baseline_end_value,
        comparison=_comparison(actual_end_value, baseline_end_value),
        evidence_status="complete",
        evidence_reason=None,
    )


def build_sizing_evidence(
    executions: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> tuple[SizingDecisionEvidence, ...]:
    """Build one evidence item per distinct execution timestamp.

    The item for the last decision is always insufficient because no following
    decision point exists to close its interval.  Replay and both interval
    portfolios are delegated to vectorbt.
    """

    decision_times = _decision_times(executions)
    interval_ends = (*decision_times[1:], None)

    try:
        actual_portfolio = replay_multi_asset_executions(
            executions,
            valuation_prices,
            init_cash=init_cash,
        )
    except PortfolioReplayError as exc:
        return tuple(
            _insufficient(decision_time, interval_end, str(exc))
            for decision_time, interval_end in zip(decision_times, interval_ends)
        )

    prices = valuation_prices.copy()
    prices.index = pd.to_datetime(prices.index)
    prices.columns = [str(column).strip() for column in prices.columns]
    prices = prices.sort_index(kind="stable")

    evidence: list[SizingDecisionEvidence] = []
    for decision_time, interval_end in zip(decision_times, interval_ends):
        if interval_end is None:
            evidence.append(
                _insufficient(
                    decision_time,
                    None,
                    "No next distinct decision point exists",
                )
            )
            continue
        try:
            evidence.append(
                _complete_interval(
                    actual_portfolio,
                    prices,
                    decision_time,
                    interval_end,
                )
            )
        except PortfolioReplayError as exc:
            evidence.append(_insufficient(decision_time, interval_end, str(exc)))
    return tuple(evidence)
