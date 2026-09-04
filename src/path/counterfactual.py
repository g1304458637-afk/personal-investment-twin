"""Phase-level historical counterfactuals. Path depends on Outcome; Outcome does not import Path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from src.attribution.decision_outcome import (
    CounterfactualScenarioDefinition,
    HistoricalCounterfactualResult,
    evaluate_omit_executions_counterfactual,
)
from src.episodes.position_episode import DecisionEvent, PositionEpisode, PositionEpisodeLifecycle
from src.path.phases import DecisionPhase


PHASE_LOCAL_SCENARIO = CounterfactualScenarioDefinition(
    scenario_id="omit_decision_phase_until_next_decision_v1",
    scenario_version="1",
    applicable_event_types=("add_position", "reduce_position"),
    changed_action="omit_selected_executions",
    evaluation_horizon="strictly_before_next_episode_decision_or_analysis_as_of_for_open_episode",
    downstream_order_policy="exclude_next_and_later_episode_decisions",
    price_basis="recorded_execution_prices_and_market_mark_at_evaluation_end",
    friction_basis="remove_selected_recorded_fees_and_preserve_included_recorded_fees",
    feasibility_conditions=(
        "A legal market mark must exist on the evaluation date.",
        "Every omitted execution must belong to the existing Episode lifecycle.",
        "The alternative path is one replay with the entire phase omitted, not a sum of single-event effects.",
    ),
)

PHASE_FULL_SCENARIO = CounterfactualScenarioDefinition(
    scenario_id="omit_phase_preserve_later_executions_v1",
    scenario_version="1",
    applicable_event_types=("add_position", "reduce_position"),
    changed_action="omit_selected_executions",
    evaluation_horizon="actual_episode_close_or_analysis_as_of_for_open_episode",
    downstream_order_policy="preserve_later_execution_time_side_absolute_quantity_price_and_fee",
    price_basis="recorded_execution_prices_and_market_mark_at_evaluation_end",
    friction_basis="remove_selected_recorded_fees_and_preserve_all_other_recorded_fees",
    feasibility_conditions=(
        "Every preserved downstream execution must remain legal without rewriting.",
        "A legal market mark must exist on the evaluation date.",
    ),
)


def _next_after_phase(
    decisions: Sequence[DecisionEvent],
    phase: DecisionPhase,
) -> DecisionEvent | None:
    ordered = tuple(item for item in decisions if item.episode_id == phase.episode_id)
    last_id = phase.decision_event_ids[-1]
    for index, item in enumerate(ordered):
        if item.decision_id == last_id:
            return ordered[index + 1] if index + 1 < len(ordered) else None
    return None


def evaluate_phase_local_counterfactual(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    episode: PositionEpisode,
    phase: DecisionPhase,
    analysis_as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
) -> HistoricalCounterfactualResult | None:
    if phase.phase_type not in {"scaling_in", "scaling_out"}:
        return None
    next_decision = _next_after_phase(lifecycle.decisions, phase)
    if next_decision is not None:
        evaluation_end = next_decision.occurred_at
        include = False
    elif episode.status == "open":
        evaluation_end = analysis_as_of
        include = True
    else:
        return None
    return evaluate_omit_executions_counterfactual(
        lifecycle,
        executions,
        market_prices,
        subject_id=episode.subject_id,
        account_id=episode.account_id,
        analysis_as_of=analysis_as_of,
        init_cash=init_cash,
        episode_id=episode.episode_id,
        anchor_decision_event_id=phase.decision_event_ids[0],
        changed_execution_refs=phase.execution_ids,
        scenario=PHASE_LOCAL_SCENARIO,
        evaluation_end=evaluation_end,
        include_evaluation_end_executions=include,
    )


def evaluate_phase_full_counterfactual(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    episode: PositionEpisode,
    phase: DecisionPhase,
    analysis_as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
) -> HistoricalCounterfactualResult | None:
    if phase.phase_type not in {"scaling_in", "scaling_out"}:
        return None
    evaluation_end = episode.closed_at or analysis_as_of
    return evaluate_omit_executions_counterfactual(
        lifecycle,
        executions,
        market_prices,
        subject_id=episode.subject_id,
        account_id=episode.account_id,
        analysis_as_of=analysis_as_of,
        init_cash=init_cash,
        episode_id=episode.episode_id,
        anchor_decision_event_id=phase.decision_event_ids[0],
        changed_execution_refs=phase.execution_ids,
        scenario=PHASE_FULL_SCENARIO,
        evaluation_end=evaluation_end,
        include_evaluation_end_executions=True,
    )
