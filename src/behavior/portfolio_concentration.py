"""Risky-security concentration using the standard HHI definition."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.attribution.selection_evidence import PriceProvenance
from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay


METHOD_ID: Final = "hhi_security_weights_v1"
METHOD_SOURCE: Final = (
    "Standard Herfindahl-Hirschman Index: HHI = sum(w_i^2), using long risky "
    "security values normalized by total risky asset value."
)
SAMPLE_BASIS: Final = (
    "Latest vectorbt risky-security asset values in the supplied observation window."
)
LIMITATION: Final = (
    "Cash is excluded from security weights. This evidence applies no high/medium/low "
    "threshold, benchmark judgment, behavior score, or claim that concentration is "
    "good or bad."
)

EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class PortfolioConcentrationEvidence:
    method_id: str
    method_source: str
    sample_basis: str
    observation_count: int
    as_of_time: pd.Timestamp | None
    active_asset_count: int
    top1_weight: float | None
    top3_weight: float | None
    hhi: float | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: tuple[PriceProvenance, ...]
    synthetic_provenance_present: bool
    limitation: str


def _insufficient(
    reason: str,
    *,
    as_of_time: pd.Timestamp | None = None,
    provenance: tuple[PriceProvenance, ...] = (),
) -> PortfolioConcentrationEvidence:
    return PortfolioConcentrationEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=0,
        as_of_time=as_of_time,
        active_asset_count=0,
        top1_weight=None,
        top3_weight=None,
        hhi=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
        provenance=provenance,
        synthetic_provenance_present=any(item.is_synthetic for item in provenance),
        limitation=LIMITATION,
    )


def build_portfolio_concentration_evidence(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> PortfolioConcentrationEvidence:
    """Describe the latest risky-asset weights from vectorbt asset values."""

    provenance: tuple[PriceProvenance, ...] = ()
    try:
        context = prepare_behavior_replay(
            executions,
            market_prices,
            init_cash=init_cash,
        )
        provenance = context.provenance
        asset_values = context.portfolio.asset_value(group_by=False)
        as_of_time = pd.Timestamp(asset_values.index[-1])
        latest = asset_values.iloc[-1].astype(float)
        if not np.isfinite(latest.to_numpy()).all() or (latest < -1e-9).any():
            raise BehaviorReplayError("Short or invalid risky asset values are unsupported")
        latest = latest.mask(latest.abs() <= 1e-12, 0.0)
        active = latest[latest > 0]
        risky_total = float(active.sum())
        if not math.isfinite(risky_total) or risky_total <= 0:
            return _insufficient(
                "No risky asset holdings are available at the observation time",
                as_of_time=as_of_time,
                provenance=context.provenance,
            )
        weights = (active / risky_total).sort_values(ascending=False)
        hhi = float((weights**2).sum())
        top1_weight = float(weights.iloc[0])
        top3_weight = float(weights.iloc[:3].sum())
    except (BehaviorReplayError, IndexError, TypeError, ValueError) as exc:
        return _insufficient(str(exc), provenance=provenance)

    return PortfolioConcentrationEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=1,
        as_of_time=as_of_time,
        active_asset_count=len(active),
        top1_weight=top1_weight,
        top3_weight=top3_weight,
        hhi=hhi,
        evidence_status="complete",
        evidence_reason=None,
        provenance=context.provenance,
        synthetic_provenance_present=context.synthetic_provenance_present,
        limitation=LIMITATION,
    )
