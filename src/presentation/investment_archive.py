"""Small archive result projection. All financial values belong to Outcome."""

from src.attribution.decision_outcome import build_actual_outcomes
from src.presentation.runtime_episode import json_value


def outcome_summaries(lifecycle, executions, market_prices, *, subject_id, account_id, init_cash):
    """One account-level Outcome build; never build a Path for each list row."""
    try:
        actual = build_actual_outcomes(
            lifecycle, executions, market_prices, subject_id=subject_id,
            account_id=account_id, analysis_as_of=lifecycle.as_of, init_cash=init_cash,
        )
    except ValueError as error:
        return {episode.episode_id: {
            "result_kind": "unavailable", "pnl": None, "return_value": None,
            "result_at": None, "availability": "unavailable",
            "reason": f"outcome_unavailable: {error}", "outcome_id": None,
            "source": None,
        } for episode in lifecycle.episodes}
    episodes = {episode.episode_id: episode for episode in lifecycle.episodes}
    return {outcome.episode_id: json_value({
        "result_kind": outcome.actual_result.result_kind,
        "pnl": outcome.actual_result.pnl,
        "return_value": outcome.actual_result.return_value,
        "result_at": outcome.actual_result.valuation_at if outcome.episode_status == "open"
        else episodes[outcome.episode_id].closed_at,
        "availability": "available", "reason": None,
        "outcome_id": outcome.outcome_id, "source": outcome.actual_result.source,
    }) for outcome in actual.episode_outcomes}
