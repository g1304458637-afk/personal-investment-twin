"""Deterministic 3–6 item presentation ranking. No good/bad score."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.path.patterns import EpisodePatternObservation
from src.path.phases import DecisionPhase
from src.attribution.decision_outcome import HistoricalCounterfactualResult


PresentationKind = Literal["phase", "pattern"]


@dataclass(frozen=True, slots=True)
class PathPresentationItem:
    item_id: str
    kind: PresentationKind
    phase_id: str | None
    pattern_id: str | None
    reason_code: str


_PATTERN_PRIORITY = {
    "consecutive_scaling_in": 0,
    "consecutive_scaling_out": 1,
    "long_no_execution_interval": 2,
    "high_quantity_during_daily_price_drawdown": 3,
    "price_following_scale_sequence": 4,
    "add_after_positive_market_move": 5,
    "reduce_after_negative_market_move": 6,
    "exit_after_negative_market_move": 7,
    "loss_state_addition_reused": 8,
}

_PRIMARY_PATTERNS = {
    "consecutive_scaling_in",
    "consecutive_scaling_out",
    "long_no_execution_interval",
    "high_quantity_during_daily_price_drawdown",
    "price_following_scale_sequence",
}

_SECONDARY_PATTERNS = {
    "add_after_positive_market_move",
    "reduce_after_negative_market_move",
    "exit_after_negative_market_move",
    "loss_state_addition_reused",
}


def _append_pattern(
    selected: list[PathPresentationItem],
    used_patterns: set[str],
    used_phases: set[str],
    pattern: EpisodePatternObservation,
    *,
    limit: int,
) -> None:
    if len(selected) >= limit or pattern.pattern_id in used_patterns:
        return
    selected.append(
        PathPresentationItem(
            item_id=pattern.pattern_id,
            kind="pattern",
            phase_id=pattern.phase_ids[0] if pattern.phase_ids else None,
            pattern_id=pattern.pattern_id,
            reason_code=pattern.pattern_code,
        )
    )
    used_patterns.add(pattern.pattern_id)
    used_phases.update(pattern.phase_ids)


def select_presentation_items(
    phases: Sequence[DecisionPhase],
    patterns: Sequence[EpisodePatternObservation],
    phase_counterfactuals: Sequence[HistoricalCounterfactualResult],
    *,
    limit: int = 6,
) -> tuple[PathPresentationItem, ...]:
    complete_cf_phases = {
        item.decision_event_id
        for item in phase_counterfactuals
        if item.feasibility_status == "complete"
    }
    selected: list[PathPresentationItem] = []
    used_phases: set[str] = set()
    used_patterns: set[str] = set()
    ranked = sorted(
        patterns,
        key=lambda item: (
            _PATTERN_PRIORITY.get(item.pattern_code, 99),
            -(int(item.facts["calendar_days"]) if item.pattern_code == "long_no_execution_interval" and isinstance(item.facts.get("calendar_days"), int) else 0),
            item.pattern_id,
        ),
    )

    for pattern in ranked:
        if pattern.pattern_code in _PRIMARY_PATTERNS:
            _append_pattern(selected, used_patterns, used_phases, pattern, limit=limit)

    for phase in phases:
        if len(selected) >= limit:
            break
        if phase.phase_type != "entry" or phase.phase_id in used_phases:
            continue
        selected.append(
            PathPresentationItem(
                item_id=phase.phase_id,
                kind="phase",
                phase_id=phase.phase_id,
                pattern_id=None,
                reason_code="episode_path_phase",
            )
        )
        used_phases.add(phase.phase_id)

    quantity_ranked = sorted(
        phases,
        key=lambda item: abs(item.quantity_after - item.quantity_before),
        reverse=True,
    )
    for phase in quantity_ranked:
        if len(selected) >= limit:
            break
        if phase.phase_id in used_phases or phase.phase_type == "entry":
            continue
        if abs(phase.quantity_after - phase.quantity_before) <= 0:
            continue
        selected.append(
            PathPresentationItem(
                item_id=phase.phase_id,
                kind="phase",
                phase_id=phase.phase_id,
                pattern_id=None,
                reason_code="large_quantity_change",
            )
        )
        used_phases.add(phase.phase_id)

    for phase in phases:
        if len(selected) >= limit:
            break
        if phase.phase_id in used_phases:
            continue
        if phase.decision_event_ids[0] in complete_cf_phases and phase.phase_type in {
            "scaling_in",
            "scaling_out",
        }:
            selected.append(
                PathPresentationItem(
                    item_id=phase.phase_id,
                    kind="phase",
                    phase_id=phase.phase_id,
                    pattern_id=None,
                    reason_code="valid_phase_counterfactual",
                )
            )
            used_phases.add(phase.phase_id)

    for pattern in ranked:
        if pattern.pattern_code in _SECONDARY_PATTERNS:
            _append_pattern(selected, used_patterns, used_phases, pattern, limit=limit)

    for phase in phases:
        if len(selected) >= limit:
            break
        if phase.phase_id in used_phases or phase.phase_type == "entry":
            continue
        selected.append(
            PathPresentationItem(
                item_id=phase.phase_id,
                kind="phase",
                phase_id=phase.phase_id,
                pattern_id=None,
                reason_code="episode_path_phase",
            )
        )
        used_phases.add(phase.phase_id)

    return tuple(selected[:limit])
