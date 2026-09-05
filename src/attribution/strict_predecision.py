"""Versioned strict-availability mapping into the existing vectorbt replay.

The scenario's fixed valuation basis is an actual prior daily observation, not
a new observation at execution time. Execution timestamps/prices remain intact.
No accounting formulas or filled/interpolated market series are created here.
"""
from dataclasses import dataclass, fields, replace

import pandas as pd

from src.attribution import decision_outcome as outcome
from src.attribution.selection_evidence import (
    PriceProvenance, _validated_price_provenance, _EvidenceDataError,
)
from src.core.portfolio_replay import replay_multi_asset_executions_with_links, PortfolioReplayError
from src.evidence.adapters import adapt_price_provenance


@dataclass(frozen=True, slots=True)
class StrictPredecisionResult(outcome.HistoricalCounterfactualResult):
    next_decision_at: pd.Timestamp | None
    valuation_observation_date: pd.Timestamp | None


def evaluate_strict_omit(scope, *, episode, decision, scenario, changed_execution_refs):
    """Canonical prefix excluding the first Episode decision after the omitted set."""
    refs = tuple(changed_execution_refs)
    if not refs or len(set(refs)) != len(refs):
        raise outcome.OutcomeAttributionError("Omit refs must be nonempty and unique")
    if not set(refs).issubset(episode.execution_refs):
        raise outcome.OutcomeAttributionError("Omit refs do not belong to the Episode")
    order = {str(value): index for index, value in enumerate(scope.frame.execution_id)}
    last = max(order[ref] for ref in refs)
    later = next((item for item in scope.decisions
                  if item.episode_id == episode.episode_id and order[item.execution_id] > last), None)
    if later is None and episode.status != "open":
        raise outcome.OutcomeAttributionError("Closed local scenario has no later Decision")
    end = later.occurred_at if later else scope.analysis_as_of
    actual = scope.frame.iloc[:order[later.execution_id]].copy() if later else scope.frame.copy()
    if decision.execution_id not in refs:
        raise outcome.OutcomeAttributionError("Anchor Decision must belong to the intervention")
    alternative = actual.loc[~actual.execution_id.isin(refs)].copy()
    valuation_date = None
    provenance = ()
    actual_result = alternative_result = None
    reason = None
    try:
        # market_date is the existing canonical local exchange calendar mapping.
        boundary_row = scope.frame.iloc[order[later.execution_id]] if later else None
        calendar = pd.Timestamp(boundary_row["market_date"] if boundary_row is not None
                                and "market_date" in boundary_row else end).normalize()
        rows = scope.market_prices.copy()
        rows["date"] = pd.to_datetime(rows.date, errors="raise").dt.normalize()
        rows = rows.loc[rows.date < calendar]
        symbols = tuple(sorted(set(actual.symbol) | {episode.instrument_id}))
        marks = {}
        sources = []
        for symbol in symbols:
            selected = rows.loc[rows.instrument == symbol].sort_values("date")
            if selected.empty or selected.date.isna().any() or selected.date.duplicated().any():
                raise outcome.OutcomeAttributionError("No unique legal prior daily observation")
            values = _validated_price_provenance(selected, f"Strict pre-decision {symbol}")
            date = pd.Timestamp(selected.date.iloc[-1])
            mark = outcome._evaluation_price(selected, instrument_id=symbol, evaluation_end=date)
            marks[symbol] = mark
            sources.append(adapt_price_provenance(PriceProvenance(
                instrument=symbol, as_of=date, **values)))
            if symbol == episode.instrument_id:
                valuation_date = date
        provenance = outcome._canonical_provenance(sources)

        def replay(frame, label):
            replay_id = outcome._scope_id(frame, account_id=scope.account_id, through=end,
                                         provenance=provenance, label=f"{scenario.scenario_id}:{label}")
            def absent(source_kind):
                source = outcome._source_ref(source_kind,
                    replay_scope_id=replay_id, account_id=scope.account_id,
                    instrument_id=episode.instrument_id, record_id="absent", execution_refs=())
                return outcome.OutcomeResult("counterfactual", "net_pnl", 0.0, None,
                    "flat", "absent", 0.0, 0.0, valuation_date, marks[episode.instrument_id], source)
            if frame.empty:
                return absent("registered_counterfactual_position_absent")
            # Explicit scenario marks at replay steps; these are NOT market observations.
            index = pd.DatetimeIndex(frame.event_time.unique()).union(pd.DatetimeIndex([end])).sort_values()
            panel = pd.DataFrame({symbol: marks[symbol] for symbol in sorted(frame.symbol.unique())}, index=index)
            result = replay_multi_asset_executions_with_links(frame, panel, init_cash=scope.init_cash)
            record = outcome._position_record(result.portfolio, episode=episode,
                execution_links={link.execution_id: link for link in result.execution_links})
            if record is None:
                return absent("vectorbt_replay_position_absent")
            mapped = outcome._position_outcome_result(result.portfolio, record,
                account_id=scope.account_id, episode=episode, replay_scope_id=replay_id,
                execution_refs=outcome._execution_refs_for_episode(episode, frame),
                result_kind="counterfactual" if label == "counterfactual" else None)
            return replace(mapped, valuation_at=valuation_date, valuation_price=marks[episode.instrument_id])

        actual_result = replay(actual, "actual")
        alternative_result = replay(alternative, "counterfactual")
    except (outcome.OutcomeAttributionError, PortfolioReplayError, _EvidenceDataError, KeyError, ValueError) as exc:
        reason = str(exc)
        actual_result = alternative_result = None
    base = outcome._result_record(
        scope=scope, episode=episode, decision=decision, scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version, relation_type="historical_counterfactual",
        evaluation_end=end, intervention=outcome.CounterfactualIntervention(scenario.changed_action, refs),
        held_constant=("canonical execution order, timestamps, prices, quantities and unomitted fees",
                       "same strict prior daily valuation basis for actual and counterfactual"),
        downstream_order_policy=scenario.downstream_order_policy, price_basis=scenario.price_basis,
        friction_basis=scenario.friction_basis,
        feasibility_status="insufficient_counterfactual_data" if reason else "complete",
        infeasible_reason=reason, first_conflicting_execution_id=None,
        actual_result=actual_result, counterfactual_result=alternative_result,
        comparison=outcome._not_applicable_comparison() if reason else outcome.compare_outcome_results(actual_result, alternative_result),
        baseline_evidence_ref=None, provenance=provenance, limitations=scenario.feasibility_conditions,
    )
    return StrictPredecisionResult(**{field.name: getattr(base, field.name) for field in fields(base)},
        next_decision_at=later.occurred_at if later else None,
        valuation_observation_date=valuation_date)
