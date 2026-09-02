"""Retrospective fixed-horizon evidence after a completed investment exit.

The counterfactual is fixed in advance and never searches for a favorable
future price.  It is evidence for review, not exit skill, advice, prediction,
or a claim that subsequent prices were knowable at the actual exit time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.attribution.selection_evidence import (
    PriceProvenance,
    _empyrical_total_return,
    _EvidenceDataError,
    _price_window,
)
from src.data.local_market_data_provider import LocalMarketDataProvider
from src.episodes.investment_episode import InvestmentEpisode


PRIMARY_EXIT_POLICY: Final = "hold_20_sessions_v1"
POLICY_SESSIONS: Final = 20
COUNTERFACTUAL_NOTICE: Final = (
    "This is a retrospective fixed-horizon counterfactual. The 20-session "
    "horizon is a fixed project policy, not an optimal or industry-standard "
    "horizon, and does not imply that subsequent price changes were knowable "
    "at the actual exit time."
)
_LATEST_PROVIDER_DATE: Final = pd.Timestamp.max.normalize()

Comparison = Literal[
    "actual_exit_outperformed_hold_baseline",
    "actual_exit_underperformed_hold_baseline",
    "matched_hold_baseline",
]
EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class ExitTimingEvidence:
    """Fixed-policy post-exit market evidence for one InvestmentEpisode.

    ``actual_exit_price`` is copied from the Episode.  The return uses the
    separate, internally consistent market-price series beginning at
    ``exit_session_market_price``; the two price bases are never mixed.
    """

    episode_id: str
    symbol: str
    actual_exit_time: pd.Timestamp | None
    actual_exit_price: float | None
    policy_id: str
    policy_sessions: int
    counterfactual_exit_time: pd.Timestamp | None
    exit_session_market_price: float | None
    counterfactual_exit_price: float | None
    post_exit_asset_return: float | None
    comparison: Comparison | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: PriceProvenance | None
    counterfactual_notice: str


def _insufficient(
    episode: InvestmentEpisode,
    reason: str,
    *,
    actual_exit_time: pd.Timestamp | None = None,
    actual_exit_price: float | None = None,
    provenance: PriceProvenance | None = None,
) -> ExitTimingEvidence:
    return ExitTimingEvidence(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        actual_exit_time=actual_exit_time,
        actual_exit_price=actual_exit_price,
        policy_id=PRIMARY_EXIT_POLICY,
        policy_sessions=POLICY_SESSIONS,
        counterfactual_exit_time=None,
        exit_session_market_price=None,
        counterfactual_exit_price=None,
        post_exit_asset_return=None,
        comparison=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
        provenance=provenance,
        counterfactual_notice=COUNTERFACTUAL_NOTICE,
    )


def _fixed_session_price_window(
    provider: LocalMarketDataProvider,
    symbol: str,
    exit_date: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame, PriceProvenance]:
    candidates = provider.get_prices(
        [symbol],
        exit_date,
        _LATEST_PROVIDER_DATE,
    )
    context = f"Post-exit price data for {symbol}"
    if candidates.empty:
        raise _EvidenceDataError(f"{context} is unavailable")
    if candidates["date"].isna().any():
        raise _EvidenceDataError(f"{context} contains a null date")

    candidates = candidates.sort_values("date", kind="stable").reset_index(drop=True)
    session_dates = candidates["date"].dt.normalize()
    exit_session = session_dates == exit_date
    if exit_session.sum() != 1:
        raise _EvidenceDataError(f"{context} has no unique actual exit session")

    post_exit = candidates.loc[session_dates > exit_date]
    if len(post_exit) < POLICY_SESSIONS:
        raise _EvidenceDataError(
            f"{context} has fewer than {POLICY_SESSIONS} subsequent sessions"
        )
    policy_session_dates = pd.concat(
        [
            session_dates.loc[exit_session],
            post_exit["date"].iloc[:POLICY_SESSIONS].dt.normalize(),
        ]
    )
    if policy_session_dates.duplicated().any():
        raise _EvidenceDataError(
            f"{context} contains duplicate sessions inside the policy window"
        )
    counterfactual_exit_date = pd.Timestamp(
        post_exit.iloc[POLICY_SESSIONS - 1]["date"]
    ).normalize()
    return _price_window(provider, symbol, exit_date, counterfactual_exit_date)


def _comparison(post_exit_asset_return: float) -> Comparison:
    if math.isclose(post_exit_asset_return, 0.0, rel_tol=1e-9, abs_tol=1e-12):
        return "matched_hold_baseline"
    if post_exit_asset_return > 0:
        return "actual_exit_underperformed_hold_baseline"
    return "actual_exit_outperformed_hold_baseline"


def build_exit_timing_evidence(
    episode: InvestmentEpisode,
    provider: LocalMarketDataProvider,
) -> ExitTimingEvidence:
    """Evaluate the fixed 20-session hold policy using validated market data."""

    if episode.status == "Open":
        return _insufficient(
            episode,
            "Open Episode has no completed final exit to evaluate",
        )
    if episode.status != "Closed":
        return _insufficient(episode, f"Unsupported Episode status: {episode.status}")
    if episode.direction != "Long":
        return _insufficient(
            episode,
            "Exit Timing Evidence v1 supports Long Episodes only",
        )
    if episode.exit_time is None or pd.isna(episode.exit_time):
        return _insufficient(episode, "Closed Episode has no actual exit_time")
    if episode.avg_exit_price is None or pd.isna(episode.avg_exit_price):
        return _insufficient(episode, "Closed Episode has no actual avg_exit_price")

    try:
        actual_exit_time = pd.Timestamp(episode.exit_time)
        actual_exit_price = float(episode.avg_exit_price)
    except (TypeError, ValueError) as exc:
        return _insufficient(episode, f"Invalid actual exit facts: {exc}")
    if not math.isfinite(actual_exit_price) or actual_exit_price <= 0:
        return _insufficient(episode, "Actual exit price must be finite and positive")

    provenance: PriceProvenance | None = None
    try:
        prices, price_rows, provenance = _fixed_session_price_window(
            provider,
            episode.symbol,
            actual_exit_time.normalize(),
        )
        post_exit_asset_return = _empyrical_total_return(prices, episode.symbol)
    except (KeyError, LookupError, TypeError, ValueError, _EvidenceDataError) as exc:
        return _insufficient(
            episode,
            str(exc),
            actual_exit_time=actual_exit_time,
            actual_exit_price=actual_exit_price,
            provenance=provenance,
        )

    return ExitTimingEvidence(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        actual_exit_time=actual_exit_time,
        actual_exit_price=actual_exit_price,
        policy_id=PRIMARY_EXIT_POLICY,
        policy_sessions=POLICY_SESSIONS,
        counterfactual_exit_time=pd.Timestamp(price_rows["date"].iloc[-1]),
        exit_session_market_price=float(prices.iloc[0]),
        counterfactual_exit_price=float(prices.iloc[-1]),
        post_exit_asset_return=post_exit_asset_return,
        comparison=_comparison(post_exit_asset_return),
        evidence_status="complete",
        evidence_reason=None,
        provenance=provenance,
        counterfactual_notice=COUNTERFACTUAL_NOTICE,
    )
