"""Observable path/behavior relationships. Not personality, motive, or skill."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.episodes.position_episode import DecisionEvent, EvidenceReference, ReplayPositionState
from src.path.market_path import (
    DailyMarketObservation,
    DailyPricePeakDrawdown,
    DecisionIntervalObservation,
    TrailingHoldObservation,
    calendar_days_between,
    recovered_prior_high,
)
from src.path.phases import DecisionPhase
from src.path.position_path import EpisodePositionPath


PATTERN_METHOD_VERSION: Final = "1"
LONG_NO_EXECUTION_MIN_CALENDAR_DAYS: Final = 365
LONG_NO_EXECUTION_MIN_OBSERVATIONS: Final = 200
PatternCode = Literal[
    "consecutive_scaling_in",
    "consecutive_scaling_out",
    "add_after_positive_market_move",
    "reduce_after_negative_market_move",
    "exit_after_negative_market_move",
    "loss_state_addition_reused",
    "high_quantity_during_daily_price_drawdown",
    "price_following_scale_sequence",
    "long_no_execution_interval",
]


@dataclass(frozen=True, slots=True)
class EpisodePatternObservation:
    pattern_id: str
    episode_id: str
    pattern_code: PatternCode
    method_version: str
    decision_event_ids: tuple[str, ...]
    phase_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    facts: Mapping[str, object]


def _decision_map(decisions: Sequence[DecisionEvent]) -> dict[str, DecisionEvent]:
    return {item.decision_id: item for item in decisions}


def _move_by_decision(
    intervals: Sequence[DecisionIntervalObservation],
) -> dict[str, DecisionIntervalObservation]:
    return {item.next_decision_event_id: item for item in intervals}


def _phase_id_for_decision(phases: Sequence[DecisionPhase], decision_id: str) -> str | None:
    for phase in phases:
        if decision_id in phase.decision_event_ids:
            return phase.phase_id
    return None


def _month_span(start: pd.Timestamp, end: pd.Timestamp) -> int:
    left = pd.Timestamp(start).normalize()
    right = pd.Timestamp(end).normalize()
    return (right.year - left.year) * 12 + (right.month - left.month)


def _is_long_interval(calendar_days: int, observation_count: int) -> bool:
    return (
        calendar_days >= LONG_NO_EXECUTION_MIN_CALENDAR_DAYS
        or observation_count >= LONG_NO_EXECUTION_MIN_OBSERVATIONS
    )


def _long_interval_pattern(
    *,
    episode_id: str,
    previous: DecisionEvent,
    next_decision: DecisionEvent | None,
    calendar_start: pd.Timestamp,
    calendar_end: pd.Timestamp,
    valid_observation_count: int,
    price_change: float | None,
    price_return: float | None,
    window_start: pd.Timestamp | None,
    window_end: pd.Timestamp | None,
    highest: DailyMarketObservation | None,
    lowest: DailyMarketObservation | None,
    quantity_held: float,
    recovered: bool | None,
) -> EpisodePatternObservation | None:
    days = calendar_days_between(calendar_start, calendar_end)
    if not _is_long_interval(days, valid_observation_count):
        return None
    suffix = next_decision.decision_id if next_decision is not None else "trailing"
    return EpisodePatternObservation(
        pattern_id=f"pattern_{previous.decision_id}_{suffix}_long_no_execution_interval",
        episode_id=episode_id,
        pattern_code="long_no_execution_interval",
        method_version=PATTERN_METHOD_VERSION,
        decision_event_ids=(previous.decision_id,)
        + ((next_decision.decision_id,) if next_decision is not None else ()),
        phase_ids=(),
        evidence_ids=(),
        facts={
            "calendar_days": days,
            "calendar_month_span": _month_span(calendar_start, calendar_end),
            "duration_unit": "calendar_days",
            "valid_observation_count": valid_observation_count,
            "price_change": price_change,
            "price_return": price_return,
            "window_start": window_start.isoformat() if window_start is not None else None,
            "window_end": window_end.isoformat() if window_end is not None else None,
            "highest_price": highest.price if highest is not None else None,
            "lowest_price": lowest.price if lowest is not None else None,
            "highest_observed_at": highest.observed_at.isoformat() if highest is not None else None,
            "lowest_observed_at": lowest.observed_at.isoformat() if lowest is not None else None,
            "quantity_held": quantity_held,
            "quantity_stable": True,
            "recovered_prior_high": recovered,
            "previous_decision_event_id": previous.decision_id,
            "next_decision_event_id": next_decision.decision_id if next_decision is not None else None,
            "is_trailing_open_hold": next_decision is None,
        },
    )


def build_pattern_observations(
    *,
    episode_id: str,
    decisions: Sequence[DecisionEvent],
    phases: Sequence[DecisionPhase],
    intervals: Sequence[DecisionIntervalObservation],
    position_path: EpisodePositionPath,
    drawdown: DailyPricePeakDrawdown | None,
    evidence_references: Sequence[EvidenceReference],
    states: Mapping[str, ReplayPositionState],
    trailing_hold: TrailingHoldObservation | None = None,
    interval_observation_windows: Mapping[str, Sequence[DailyMarketObservation]] | None = None,
) -> tuple[EpisodePatternObservation, ...]:
    by_decision = _decision_map(decisions)
    moves = _move_by_decision(intervals)
    patterns: list[EpisodePatternObservation] = []

    for phase in phases:
        if phase.phase_type == "scaling_in" and len(phase.decision_event_ids) >= 2:
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{phase.phase_id}_consecutive_scaling_in",
                    episode_id=episode_id,
                    pattern_code="consecutive_scaling_in",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=phase.decision_event_ids,
                    phase_ids=(phase.phase_id,),
                    evidence_ids=(),
                    facts={
                        "decision_count": len(phase.decision_event_ids),
                        "quantity_before": phase.quantity_before,
                        "quantity_after": phase.quantity_after,
                        "started_at": phase.started_at.isoformat(),
                        "ended_at": phase.ended_at.isoformat(),
                    },
                )
            )
        if phase.phase_type == "scaling_out" and len(phase.decision_event_ids) >= 2:
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{phase.phase_id}_consecutive_scaling_out",
                    episode_id=episode_id,
                    pattern_code="consecutive_scaling_out",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=phase.decision_event_ids,
                    phase_ids=(phase.phase_id,),
                    evidence_ids=(),
                    facts={
                        "decision_count": len(phase.decision_event_ids),
                        "quantity_before": phase.quantity_before,
                        "quantity_after": phase.quantity_after,
                        "started_at": phase.started_at.isoformat(),
                        "ended_at": phase.ended_at.isoformat(),
                    },
                )
            )

    positive_adds: list[str] = []
    negative_reduces: list[str] = []
    for decision in decisions:
        if decision.decision_type == "open_position":
            continue
        interval = moves.get(decision.decision_id)
        if interval is None or interval.move.status != "complete" or interval.move.price_return is None:
            continue
        ret = interval.move.price_return
        facts = {
            "price_return": ret,
            "price_change": interval.move.price_change,
            "valid_observation_count": interval.move.valid_observation_count,
            "window_start": interval.move.window_start.isoformat() if interval.move.window_start is not None else None,
            "window_end": interval.move.window_end.isoformat() if interval.move.window_end is not None else None,
            "previous_decision_event_id": interval.previous_decision_event_id,
        }
        phase_id = _phase_id_for_decision(phases, decision.decision_id)
        phase_ids = (phase_id,) if phase_id is not None else ()
        if decision.decision_type == "add_position" and ret > 0:
            positive_adds.append(decision.decision_id)
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{decision.decision_id}_add_after_positive_market_move",
                    episode_id=episode_id,
                    pattern_code="add_after_positive_market_move",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=(decision.decision_id,),
                    phase_ids=phase_ids,
                    evidence_ids=(),
                    facts=facts,
                )
            )
        if decision.decision_type == "reduce_position" and ret < 0:
            negative_reduces.append(decision.decision_id)
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{decision.decision_id}_reduce_after_negative_market_move",
                    episode_id=episode_id,
                    pattern_code="reduce_after_negative_market_move",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=(decision.decision_id,),
                    phase_ids=phase_ids,
                    evidence_ids=(),
                    facts=facts,
                )
            )
        if decision.decision_type == "close_position" and ret < 0:
            negative_reduces.append(decision.decision_id)
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{decision.decision_id}_exit_after_negative_market_move",
                    episode_id=episode_id,
                    pattern_code="exit_after_negative_market_move",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=(decision.decision_id,),
                    phase_ids=phase_ids,
                    evidence_ids=(),
                    facts=facts,
                )
            )

    for interval in intervals:
        previous = by_decision[interval.previous_decision_event_id]
        nxt = by_decision[interval.next_decision_event_id]
        quantity = states[previous.state_after_ref].quantity
        window = (interval_observation_windows or {}).get(interval.interval_id, ())
        recovered = recovered_prior_high(window) if window else None
        long_pattern = _long_interval_pattern(
            episode_id=episode_id,
            previous=previous,
            next_decision=nxt,
            calendar_start=previous.occurred_at,
            calendar_end=nxt.occurred_at,
            valid_observation_count=interval.move.valid_observation_count,
            price_change=interval.move.price_change,
            price_return=interval.move.price_return,
            window_start=interval.move.window_start,
            window_end=interval.move.window_end,
            highest=interval.move.highest_observation,
            lowest=interval.move.lowest_observation,
            quantity_held=quantity,
            recovered=recovered,
        )
        if long_pattern is not None:
            patterns.append(long_pattern)

    if trailing_hold is not None:
        previous = by_decision[trailing_hold.previous_decision_event_id]
        quantity = states[previous.state_after_ref].quantity
        window = (interval_observation_windows or {}).get(trailing_hold.interval_id, ())
        recovered = recovered_prior_high(window) if window else None
        long_pattern = _long_interval_pattern(
            episode_id=episode_id,
            previous=previous,
            next_decision=None,
            calendar_start=previous.occurred_at,
            calendar_end=trailing_hold.as_of,
            valid_observation_count=trailing_hold.valid_observation_count,
            price_change=trailing_hold.price_change,
            price_return=trailing_hold.price_return,
            window_start=trailing_hold.window_start,
            window_end=trailing_hold.window_end,
            highest=trailing_hold.highest_observation,
            lowest=trailing_hold.lowest_observation,
            quantity_held=quantity,
            recovered=recovered,
        )
        if long_pattern is not None:
            patterns.append(long_pattern)

    loss_state_ids = tuple(
        ref.evidence_id
        for ref in evidence_references
        if ref.metric_id == "loss_state_addition"
    )
    if loss_state_ids:
        linked = tuple(
            decision.decision_id
            for decision in decisions
            if any(item in loss_state_ids for item in decision.evidence_refs)
        )
        patterns.append(
            EpisodePatternObservation(
                pattern_id=f"pattern_{episode_id}_loss_state_addition_reused",
                episode_id=episode_id,
                pattern_code="loss_state_addition_reused",
                method_version=PATTERN_METHOD_VERSION,
                decision_event_ids=linked,
                phase_ids=(),
                evidence_ids=loss_state_ids,
                facts={"reused_existing_evidence": True},
            )
        )

    if (
        drawdown is not None
        and position_path.max_quantity > 0
    ):
        ratio = None
        if drawdown.quantity_at_trough is not None:
            ratio = drawdown.quantity_at_trough / position_path.max_quantity
        patterns.append(
            EpisodePatternObservation(
                pattern_id=f"pattern_{episode_id}_high_quantity_during_daily_price_drawdown",
                episode_id=episode_id,
                pattern_code="high_quantity_during_daily_price_drawdown",
                method_version=PATTERN_METHOD_VERSION,
                decision_event_ids=(),
                phase_ids=(),
                evidence_ids=(),
                facts={
                    "episode_max_quantity": position_path.max_quantity,
                    "quantity_at_daily_price_drawdown": drawdown.quantity_at_trough,
                    "quantity_at_trough_status": drawdown.quantity_at_trough_status,
                    "quantity_ratio_to_episode_max": ratio,
                    "daily_price_peak_drawdown": drawdown.daily_price_peak_drawdown,
                    "peak_observed_at": drawdown.peak_observation.observed_at.isoformat(),
                    "trough_observed_at": drawdown.trough_observation.observed_at.isoformat(),
                    "quantity_status_reason": drawdown.quantity_status_reason,
                },
            )
        )

    if positive_adds and negative_reduces:
        first_add = min(positive_adds, key=lambda item: by_decision[item].occurred_at)
        later_reduce = [
            item
            for item in negative_reduces
            if by_decision[item].occurred_at > by_decision[first_add].occurred_at
        ]
        if later_reduce:
            patterns.append(
                EpisodePatternObservation(
                    pattern_id=f"pattern_{episode_id}_price_following_scale_sequence",
                    episode_id=episode_id,
                    pattern_code="price_following_scale_sequence",
                    method_version=PATTERN_METHOD_VERSION,
                    decision_event_ids=(first_add, later_reduce[0]),
                    phase_ids=(),
                    evidence_ids=(),
                    facts={
                        "add_after_positive_decision_event_id": first_add,
                        "reduce_or_exit_after_negative_decision_event_id": later_reduce[0],
                    },
                )
            )
    return tuple(patterns)
