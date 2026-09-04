"""Position quantity and average-cost paths copied from ReplayPositionState."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd

from src.episodes.position_episode import DecisionEvent, PositionEpisode, ReplayPositionState
from src.path.market_path import (
    DailyMarketObservation,
    DailyPricePeakDrawdown,
    QuantityAtObservationStatus,
    _calendar,
)


@dataclass(frozen=True, slots=True)
class PositionPathPoint:
    as_of: pd.Timestamp
    boundary: Literal["before_execution", "after_execution", "as_of_valuation"]
    state_id: str
    quantity: float
    average_cost: float | None
    execution_id: str | None
    decision_event_id: str | None


@dataclass(frozen=True, slots=True)
class QuantityAtObservation:
    observed_at: pd.Timestamp
    status: QuantityAtObservationStatus
    quantity: float | None
    state_id: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class EpisodePositionPath:
    episode_id: str
    points: tuple[PositionPathPoint, ...]
    max_quantity: float
    max_quantity_as_of: pd.Timestamp
    max_quantity_state_id: str
    quantity_at_drawdown: QuantityAtObservation | None


def _state_map(states: Sequence[ReplayPositionState]) -> dict[str, ReplayPositionState]:
    return {item.state_id: item for item in states}


def quantity_at_observation(
    observation: DailyMarketObservation,
    *,
    decisions: Sequence[DecisionEvent],
    states: Mapping[str, ReplayPositionState],
) -> QuantityAtObservation:
    """Lookup quantity only when the daily observation is not an execution date.

    Same-day close has no available_at, so a date that also contains an
    execution cannot prove whether the observation is before or after the fill.
    """

    observed = _calendar(observation.observed_at)
    execution_dates = {_calendar(item.occurred_at) for item in decisions}
    if observed in execution_dates:
        return QuantityAtObservation(
            observed_at=observed,
            status="ambiguous",
            quantity=None,
            state_id=None,
            reason="observation_date_contains_execution",
        )
    prior = [item for item in decisions if _calendar(item.occurred_at) < observed]
    if not prior:
        return QuantityAtObservation(
            observed_at=observed,
            status="unavailable",
            quantity=None,
            state_id=None,
            reason="no_prior_decision_with_unambiguous_quantity",
        )
    last = prior[-1]
    state = states[last.state_after_ref]
    return QuantityAtObservation(
        observed_at=observed,
        status="available",
        quantity=state.quantity,
        state_id=state.state_id,
        reason=None,
    )


def attach_drawdown_quantity(
    drawdown: DailyPricePeakDrawdown | None,
    *,
    decisions: Sequence[DecisionEvent],
    states: Mapping[str, ReplayPositionState],
) -> DailyPricePeakDrawdown | None:
    if drawdown is None:
        return None
    lookup = quantity_at_observation(
        drawdown.trough_observation,
        decisions=decisions,
        states=states,
    )
    return replace(
        drawdown,
        quantity_at_trough_status=lookup.status,
        quantity_at_trough=lookup.quantity,
        quantity_status_reason=lookup.reason,
    )


def build_episode_position_path(
    episode: PositionEpisode,
    decisions: Sequence[DecisionEvent],
    states: Sequence[ReplayPositionState],
    *,
    drawdown: DailyPricePeakDrawdown | None,
) -> EpisodePositionPath:
    by_id = _state_map(states)
    ordered = tuple(item for item in decisions if item.episode_id == episode.episode_id)
    points: list[PositionPathPoint] = []
    if ordered:
        before = by_id[ordered[0].state_before_ref]
        points.append(
            PositionPathPoint(
                as_of=before.as_of,
                boundary=before.boundary,
                state_id=before.state_id,
                quantity=before.quantity,
                average_cost=before.average_cost,
                execution_id=before.execution_id,
                decision_event_id=ordered[0].decision_id,
            )
        )
        for decision in ordered:
            after = by_id[decision.state_after_ref]
            points.append(
                PositionPathPoint(
                    as_of=after.as_of,
                    boundary=after.boundary,
                    state_id=after.state_id,
                    quantity=after.quantity,
                    average_cost=after.average_cost,
                    execution_id=after.execution_id,
                    decision_event_id=decision.decision_id,
                )
            )
    if not points:
        raise ValueError("Episode has no replay position states")
    peak = max(points, key=lambda item: (item.quantity, item.as_of.isoformat()))
    annotated = attach_drawdown_quantity(drawdown, decisions=ordered, states=by_id)
    quantity_at_drawdown = None
    if annotated is not None:
        quantity_at_drawdown = QuantityAtObservation(
            observed_at=annotated.trough_observation.observed_at,
            status=annotated.quantity_at_trough_status,
            quantity=annotated.quantity_at_trough,
            state_id=None,
            reason=annotated.quantity_status_reason,
        )
    return EpisodePositionPath(
        episode_id=episode.episode_id,
        points=tuple(points),
        max_quantity=peak.quantity,
        max_quantity_as_of=peak.as_of,
        max_quantity_state_id=peak.state_id,
        quantity_at_drawdown=quantity_at_drawdown,
    )
