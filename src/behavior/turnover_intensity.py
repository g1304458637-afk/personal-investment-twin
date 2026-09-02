"""Pyfolio-compatible portfolio-value turnover from vectorbt facts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.attribution.selection_evidence import PriceProvenance
from src.behavior.replay_state import (
    BehaviorReplayError,
    daily_portfolio_value,
    prepare_behavior_replay,
)


METHOD_ID: Final = "pyfolio_portfolio_value_turnover_v1"
METHOD_SOURCE: Final = (
    'Method semantics follow Quantopian pyfolio get_turnover(denominator="portfolio_value"): '
    "daily turnover is same-day double-sided traded value divided by total "
    "portfolio value, including cash."
)
SAMPLE_BASIS: Final = (
    "Calendar-day vectorbt filled-order value and end-of-day portfolio value."
)
LIMITATION: Final = (
    "Turnover Intensity is descriptive and is not an overtrading label, skill "
    "score, or psychological inference. It uses double-sided filled dollars, "
    "excludes fees from traded value, and is sensitive to low portfolio values."
)

EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class DailyTurnoverObservation:
    observation_date: pd.Timestamp
    traded_value: float
    portfolio_value: float
    turnover: float


@dataclass(frozen=True, slots=True)
class TurnoverIntensityEvidence:
    method_id: str
    method_source: str
    sample_basis: str
    observation_count: int
    daily_turnover: tuple[DailyTurnoverObservation, ...]
    mean_daily_turnover: float | None
    total_traded_value: float | None
    observation_days: int
    denominator: str
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: tuple[PriceProvenance, ...]
    synthetic_provenance_present: bool
    limitation: str


def _insufficient(
    reason: str,
    *,
    provenance: tuple[PriceProvenance, ...] = (),
) -> TurnoverIntensityEvidence:
    return TurnoverIntensityEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=0,
        daily_turnover=(),
        mean_daily_turnover=None,
        total_traded_value=None,
        observation_days=0,
        denominator="portfolio_value",
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
        provenance=provenance,
        synthetic_provenance_present=any(item.is_synthetic for item in provenance),
        limitation=LIMITATION,
    )


def _portfolio_value_turnover(
    traded_value: pd.Series,
    portfolio_value: pd.Series,
) -> pd.Series:
    """Apply the thin pyfolio ``portfolio_value`` denominator semantics."""

    values = portfolio_value.astype(float)
    if values.empty:
        raise BehaviorReplayError("Portfolio value observations are unavailable")
    if not np.isfinite(values.to_numpy()).all() or (values <= 0).any():
        raise BehaviorReplayError("Portfolio value must be finite and positive")
    traded = traded_value.astype(float).reindex(values.index, fill_value=0.0)
    if not np.isfinite(traded.to_numpy()).all() or (traded < 0).any():
        raise BehaviorReplayError("Daily traded value must be finite and non-negative")
    return traded / values


def build_turnover_intensity_evidence(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> TurnoverIntensityEvidence:
    """Measure daily filled dollars relative to vectorbt portfolio value."""

    provenance: tuple[PriceProvenance, ...] = ()
    try:
        context = prepare_behavior_replay(
            executions,
            market_prices,
            init_cash=init_cash,
        )
        provenance = context.provenance
        orders = context.portfolio.orders.records_readable
        timestamps = pd.to_datetime(orders["Timestamp"], errors="raise").dt.normalize()
        filled_values = orders["Size"].abs().astype(float) * orders["Price"].astype(float)
        if not np.isfinite(filled_values.to_numpy()).all():
            raise BehaviorReplayError("vectorbt returned invalid filled-order value")
        traded_value = filled_values.groupby(timestamps, sort=True).sum()
        traded_value.index = pd.DatetimeIndex(traded_value.index)
        portfolio_value = daily_portfolio_value(context)
        turnover = _portfolio_value_turnover(traded_value, portfolio_value)
    except (BehaviorReplayError, KeyError, TypeError, ValueError) as exc:
        return _insufficient(str(exc), provenance=provenance)

    daily = tuple(
        DailyTurnoverObservation(
            observation_date=pd.Timestamp(date),
            traded_value=float(traded_value.get(date, 0.0)),
            portfolio_value=float(portfolio_value.loc[date]),
            turnover=float(turnover.loc[date]),
        )
        for date in portfolio_value.index
    )
    mean_daily_turnover = float(turnover.mean())
    total_traded_value = float(traded_value.sum())
    if not math.isfinite(mean_daily_turnover) or not math.isfinite(total_traded_value):
        return _insufficient(
            "Turnover summary is not finite",
            provenance=context.provenance,
        )

    return TurnoverIntensityEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=len(daily),
        daily_turnover=daily,
        mean_daily_turnover=mean_daily_turnover,
        total_traded_value=total_traded_value,
        observation_days=len(daily),
        denominator="portfolio_value",
        evidence_status="complete",
        evidence_reason=None,
        provenance=context.provenance,
        synthetic_provenance_present=context.synthetic_provenance_present,
        limitation=LIMITATION,
    )
