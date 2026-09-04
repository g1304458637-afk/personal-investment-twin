"""Analytical Decision Phase grouping. Never merges or VWAP-normalizes executions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.evidence.contracts import canonical_json_bytes
from src.episodes.position_episode import DecisionEvent, PositionEpisode, ReplayPositionState
from src.path.market_path import PATH_METHOD_VERSION


PHASE_TAXONOMY_VERSION: Final = "1"
PhaseType = Literal["entry", "scaling_in", "scaling_out", "exit"]

_TYPE_TO_PHASE: Final[dict[str, PhaseType]] = {
    "open_position": "entry",
    "add_position": "scaling_in",
    "reduce_position": "scaling_out",
    "close_position": "exit",
}


@dataclass(frozen=True, slots=True)
class DecisionPhase:
    phase_id: str
    episode_id: str
    phase_type: PhaseType
    taxonomy_version: str
    started_at: pd.Timestamp
    ended_at: pd.Timestamp
    decision_event_ids: tuple[str, ...]
    execution_ids: tuple[str, ...]
    quantity_before: float
    quantity_after: float
    average_cost_before: float | None
    average_cost_after: float | None
    state_before_ref: str
    state_after_ref: str
    method_version: str


def _phase_id(episode_id: str, phase_type: PhaseType, decision_ids: Sequence[str]) -> str:
    return "phase_" + hashlib.sha256(
        canonical_json_bytes(
            {
                "episode_id": episode_id,
                "taxonomy_version": PHASE_TAXONOMY_VERSION,
                "phase_type": phase_type,
                "decision_event_ids": list(decision_ids),
            }
        )
    ).hexdigest()


def group_decision_phases(
    episode: PositionEpisode,
    decisions: Sequence[DecisionEvent],
    states: Mapping[str, ReplayPositionState],
) -> tuple[DecisionPhase, ...]:
    ordered = tuple(item for item in decisions if item.episode_id == episode.episode_id)
    phases: list[DecisionPhase] = []
    index = 0
    while index < len(ordered):
        current = ordered[index]
        phase_type = _TYPE_TO_PHASE[current.decision_type]
        run = [current]
        if phase_type in {"scaling_in", "scaling_out"}:
            while index + len(run) < len(ordered):
                nxt = ordered[index + len(run)]
                if _TYPE_TO_PHASE[nxt.decision_type] != phase_type:
                    break
                run.append(nxt)
        first, last = run[0], run[-1]
        before = states[first.state_before_ref]
        after = states[last.state_after_ref]
        phases.append(
            DecisionPhase(
                phase_id=_phase_id(episode.episode_id, phase_type, [item.decision_id for item in run]),
                episode_id=episode.episode_id,
                phase_type=phase_type,
                taxonomy_version=PHASE_TAXONOMY_VERSION,
                started_at=first.occurred_at,
                ended_at=last.occurred_at,
                decision_event_ids=tuple(item.decision_id for item in run),
                execution_ids=tuple(item.execution_id for item in run),
                quantity_before=before.quantity,
                quantity_after=after.quantity,
                average_cost_before=before.average_cost,
                average_cost_after=after.average_cost,
                state_before_ref=before.state_id,
                state_after_ref=after.state_id,
                method_version=PATH_METHOD_VERSION,
            )
        )
        index += len(run)
    return tuple(phases)
