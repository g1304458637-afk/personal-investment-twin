"""Orchestrate derived Episode Path analysis above frozen Replay and Outcome."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import pandas as pd

from src.attribution.decision_outcome import HistoricalCounterfactualResult
from src.episodes.position_episode import PositionEpisode, PositionEpisodeLifecycle
from src.path.counterfactual import evaluate_phase_local_counterfactual
from src.path.market_path import (
    PATH_METHOD_ID,
    PATH_METHOD_VERSION,
    EpisodeMarketPath,
    build_episode_market_path,
)
from src.path.patterns import EpisodePatternObservation, build_pattern_observations
from src.path.phases import DecisionPhase, group_decision_phases
from src.path.position_path import (
    EpisodePositionPath,
    attach_drawdown_quantity,
    build_episode_position_path,
)
from src.path.presentation import PathPresentationItem, select_presentation_items


@dataclass(frozen=True, slots=True)
class EpisodePathAnalysis:
    episode_id: str
    method_id: str
    method_version: str
    market_path: EpisodeMarketPath
    position_path: EpisodePositionPath
    phases: tuple[DecisionPhase, ...]
    patterns: tuple[EpisodePatternObservation, ...]
    phase_counterfactuals: tuple[HistoricalCounterfactualResult, ...]
    presentation_items: tuple[PathPresentationItem, ...]
    limitations: tuple[str, ...]


def build_episode_path_analysis(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    episode_id: str,
    init_cash: float | Mapping[str, float],
    include_phase_counterfactuals: bool = True,
) -> EpisodePathAnalysis:
    episode = next(item for item in lifecycle.episodes if item.episode_id == episode_id)
    decisions = tuple(item for item in lifecycle.decisions if item.episode_id == episode_id)
    states = {item.state_id: item for item in lifecycle.states}
    market_path = build_episode_market_path(
        episode,
        decisions,
        market_prices,
        as_of=lifecycle.as_of,
    )
    annotated_drawdown = attach_drawdown_quantity(
        market_path.daily_price_peak_drawdown,
        decisions=decisions,
        states=states,
    )
    market_path = replace(market_path, daily_price_peak_drawdown=annotated_drawdown)
    snapshot = next((item for item in lifecycle.snapshots if item.episode_id == episode_id), None)
    position_path = build_episode_position_path(
        episode,
        decisions,
        lifecycle.states,
        drawdown=annotated_drawdown,
        snapshot_state=states[snapshot.position_state_ref] if snapshot else None,
    )
    phases = group_decision_phases(episode, decisions, states)
    holding = market_path.episode_market_path.observations
    interval_windows: dict[str, tuple] = {}
    ordered = tuple(item for item in decisions if item.episode_id == episode.episode_id)
    for previous, current in zip(ordered, ordered[1:]):
        interval_id = f"interval_{previous.decision_id}_{current.decision_id}"
        interval_windows[interval_id] = tuple(
            item
            for item in holding
            if previous.occurred_at.normalize() < item.observed_at < current.occurred_at.normalize()
        )
    if market_path.trailing_hold_observation is not None and ordered:
        last = ordered[-1]
        interval_windows[market_path.trailing_hold_observation.interval_id] = tuple(
            item
            for item in holding
            if last.occurred_at.normalize() < item.observed_at <= lifecycle.as_of.normalize()
        )
    patterns = build_pattern_observations(
        episode_id=episode.episode_id,
        decisions=decisions,
        phases=phases,
        intervals=market_path.decision_interval_moves,
        position_path=position_path,
        drawdown=market_path.daily_price_peak_drawdown,
        evidence_references=lifecycle.evidence_references,
        states=states,
        trailing_hold=market_path.trailing_hold_observation,
        interval_observation_windows=interval_windows,
    )
    counterfactuals: list[HistoricalCounterfactualResult] = []
    if include_phase_counterfactuals:
        for phase in phases:
            result = evaluate_phase_local_counterfactual(
                lifecycle,
                executions,
                market_prices,
                episode=episode,
                phase=phase,
                analysis_as_of=lifecycle.as_of,
                init_cash=init_cash,
            )
            if result is not None:
                counterfactuals.append(result)
    presentation = select_presentation_items(phases, patterns, counterfactuals)
    return EpisodePathAnalysis(
        episode_id=episode.episode_id,
        method_id=PATH_METHOD_ID,
        method_version=PATH_METHOD_VERSION,
        market_path=market_path,
        position_path=position_path,
        phases=phases,
        patterns=patterns,
        phase_counterfactuals=tuple(counterfactuals),
        presentation_items=presentation,
        limitations=market_path.limitations + (
            "No stop-loss historical scenario or user-selected historical exit-date scenario is provided.",
            "No online market provider is implemented; path uses recorded daily observations only.",
        ),
    )
