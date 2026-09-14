"""Gate real-user Episode construction on replay and exact market coverage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import pandas as pd

from src.behavior.replay_state import BehaviorReplayError
from src.core.canonical_execution import canonical_executions_to_frame, replay_eligibility
from src.episodes.position_episode import PositionEpisodeError, PositionEpisodeLifecycle, build_position_episode_lifecycle
from src.ingestion.contracts import CanonicalImportBundle
from src.market_data.models import HistoricalPriceFact, facts_to_market_data_frame, resolve_market_data_requirements


@dataclass(frozen=True, slots=True)
class EpisodeBuildGateResult:
    status: Literal["available", "unavailable_pending_market_data", "unavailable_replay_ineligible"]
    reason: str | None
    lifecycle: PositionEpisodeLifecycle | None


# Only price-panel coverage failures may be downgraded to
# ``unavailable_pending_market_data``; anything else (contract violations,
# replay state errors, data bugs) must propagate untouched.
_PENDING_MARKET_DATA_MARKERS = (
    "Market price panel is incomplete",
    "Missing market prices for execution dates",
    "Missing market prices for execution symbols",
    "No market prices are available at or before as_of",
)


def build_episode_when_market_ready(
    bundle: CanonicalImportBundle,
    facts: Sequence[HistoricalPriceFact],
    *,
    as_of: pd.Timestamp,
    init_cash: float,
    calculation_code_version: str,
) -> EpisodeBuildGateResult:
    """Call the existing Episode builder only when immutable facts are sufficient."""

    eligibility = replay_eligibility(bundle.accepted_canonical_executions)
    if not eligibility.eligible:
        return EpisodeBuildGateResult(
            "unavailable_replay_ineligible",
            ",".join(eligibility.block_reasons),
            None,
        )
    availability = resolve_market_data_requirements(bundle, facts, as_of=as_of)
    if availability.status != "complete":
        return EpisodeBuildGateResult(
            "unavailable_pending_market_data",
            "exact required daily market observations are incomplete",
            None,
        )
    try:
        lifecycle = build_position_episode_lifecycle(
            canonical_executions_to_frame(bundle.accepted_canonical_executions),
            facts_to_market_data_frame(facts),
            subject_id=bundle.subject_id,
            account_id=bundle.account_id,
            as_of=as_of,
            init_cash=init_cash,
            data_tier="authorized_beta",
            calculation_code_version=calculation_code_version,
        )
    except (PositionEpisodeError, BehaviorReplayError) as exc:
        message = str(exc)
        if not any(marker in message for marker in _PENDING_MARKET_DATA_MARKERS):
            raise
        # Defense in depth: a residual price-panel gap is pending market data,
        # never a crash and never a different failure class.
        return EpisodeBuildGateResult("unavailable_pending_market_data", message, None)
    return EpisodeBuildGateResult("available", None, lifecycle)
