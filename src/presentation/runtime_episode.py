"""Runtime projection for Position Episode; contains no financial formulas."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from src.attribution.decision_outcome import build_actual_outcomes, evaluate_historical_counterfactual
from src.episodes.position_episode import PositionEpisodeLifecycle


def json_value(value: Any) -> Any:
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def episode_entry(lifecycle: PositionEpisodeLifecycle, executions: pd.DataFrame,
                  market_prices: pd.DataFrame, *, episode_id: str, init_cash: float,
                  display_name: str) -> dict[str, object]:
    episode = next(item for item in lifecycle.episodes if item.episode_id == episode_id)
    decisions = tuple(item for item in lifecycle.decisions if item.episode_id == episode_id)
    state_ids = {ref for decision in decisions for ref in (decision.state_before_ref, decision.state_after_ref)}
    snapshot = next((item for item in lifecycle.snapshots if item.episode_id == episode_id), None)
    if snapshot:
        state_ids.add(snapshot.position_state_ref)
    states = {item.state_id: item for item in lifecycle.states if item.state_id in state_ids}
    evidence_ids = {*episode.evidence_refs, *(ref for item in decisions for ref in item.evidence_refs)}
    refs = tuple(item for item in lifecycle.evidence_references if item.evidence_id in evidence_ids)
    dates = pd.to_datetime(market_prices["date"], errors="raise")
    end = episode.closed_at or lifecycle.as_of
    points = tuple(
        {"observed_at": pd.Timestamp(row["date"]), "price": float(row["close"])}
        for _, row in market_prices.loc[
            (market_prices["instrument"] == episode.instrument_id)
            & (dates.dt.normalize() >= episode.opened_at.normalize())
            & (dates.dt.normalize() <= end.normalize())
        ].sort_values("date", kind="stable").iterrows()
    )
    actual = build_actual_outcomes(lifecycle, executions, market_prices,
        subject_id=episode.subject_id, account_id=episode.account_id,
        analysis_as_of=lifecycle.as_of, init_cash=init_cash)
    episode_outcome = next(item for item in actual.episode_outcomes if item.episode_id == episode_id)
    outcomes = tuple(item for item in actual.decision_outcomes if item.episode_id == episode_id)
    counterfactuals = []
    for decision in outcomes:
        scenarios = ["omit_event_until_next_decision_v1"]
        if decision.event_type in {"add_position", "reduce_position"}:
            scenarios.append("omit_event_preserve_later_executions_v1")
        for scenario in scenarios:
            result = evaluate_historical_counterfactual(lifecycle, executions, market_prices,
                subject_id=episode.subject_id, account_id=episode.account_id,
                decision_event_id=decision.decision_event_id, scenario_id=scenario,
                analysis_as_of=lifecycle.as_of, init_cash=init_cash)
            counterfactuals.append(result)
    payload = {
        "instrument": {"instrument_id": episode.instrument_id, "display_name": display_name,
                       "is_synthetic": False, "data_tier": "authorized_beta"},
        "episode": episode, "snapshot": snapshot, "decisions": decisions,
        "states_by_ref": states, "evidence_references": refs, "price_points": points,
        "outcome_story": {"episode_outcome": episode_outcome, "decision_outcomes": outcomes,
                          "counterfactuals": tuple(counterfactuals), "exit_followup": None},
    }
    return json_value(payload)
