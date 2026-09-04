"""Historical decision outcomes backed by the existing vectorbt replay.

This module maps authoritative vectorbt order, exit-trade, and position
records into stable product facts.  It also evaluates a deliberately small
registry of retrospective counterfactuals by replaying unchanged historical
orders through the same portfolio engine.  It does not implement PnL,
cost-basis, fee, return, or order-resizing formulas.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay
from src.core.portfolio_replay import (
    PortfolioReplayError,
    ReplayExecutionLink,
    _validated_executions,
)
from src.evidence.adapters import adapt_price_provenance
from src.evidence.contracts import (
    DataTier,
    EvidenceProvenance,
    EvidenceRecord,
    canonical_json_bytes,
)
from src.episodes.investment_episode import from_vectorbt_position_record
from src.episodes.position_episode import (
    DecisionEvent,
    PositionEpisode,
    PositionEpisodeLifecycle,
    ReplayPositionState,
)
from src.twin.state import evidence_available_at


OUTCOME_METHOD_ID: Final = "historical_decision_outcome_v1"
OUTCOME_METHOD_VERSION: Final = "1"

RelationType = Literal[
    "deterministic_state_transition",
    "accounting_realized_result",
    "marked_position_result",
    "historical_market_followup",
    "registered_baseline_comparison",
    "historical_counterfactual",
    "statistical_association",
]
ResultKind = Literal["realized", "marked", "counterfactual"]
ResultBasis = Literal["net_pnl", "gross_pnl_before_incremental_friction"]
ResultSign = Literal["profit", "flat", "loss"]
PositionResultStatus = Literal["open", "closed", "absent"]
SourceKind = Literal[
    "vectorbt_order",
    "vectorbt_exit_trade",
    "vectorbt_position",
    "vectorbt_replay_position_absent",
    "registered_counterfactual_position_absent",
    "existing_exit_evidence",
]
FeasibilityStatus = Literal[
    "complete",
    "infeasible_downstream_execution",
    "insufficient_counterfactual_data",
    "unsupported_scenario",
]
ComparisonStatus = Literal[
    "complete",
    "not_applicable",
    "unavailable_result_basis_mismatch",
]
ResultTransition = Literal[
    "matched",
    "loss_reduced",
    "loss_increased",
    "loss_to_flat",
    "loss_to_profit",
    "profit_increased",
    "profit_reduced",
    "profit_to_flat",
    "profit_to_loss",
    "flat_to_profit",
    "flat_to_loss",
]


class OutcomeAttributionError(ValueError):
    """Authoritative records cannot be mapped without ambiguity."""


@dataclass(frozen=True, slots=True)
class AuthoritativeSourceRef:
    """Stable pointer to one authoritative replay or Evidence record."""

    source_kind: SourceKind
    source_record_id: str
    replay_scope_id: str | None
    vectorbt_record_id: int | None
    execution_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutcomeResult:
    """A result copied from one authoritative record.

    ``recorded_entry_fees`` and ``recorded_exit_fees`` are separate fields
    from that record.  This module deliberately does not create a second fee
    total or PnL calculation.
    """

    result_kind: ResultKind
    result_basis: ResultBasis
    pnl: float
    return_value: float | None
    result_sign: ResultSign
    position_status: PositionResultStatus
    recorded_entry_fees: float
    recorded_exit_fees: float
    valuation_at: pd.Timestamp | None
    valuation_price: float | None
    source: AuthoritativeSourceRef


@dataclass(frozen=True, slots=True)
class OutcomePositionState:
    """Small immutable view of an existing ReplayPositionState."""

    state_ref: str
    quantity: float
    average_cost: float | None
    position_status: Literal["flat", "open"]


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    """Authoritative result for one existing PositionEpisode lifecycle."""

    outcome_id: str
    episode_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    episode_status: Literal["open", "closed"]
    analysis_as_of: pd.Timestamp
    relation_type: Literal["accounting_realized_result", "marked_position_result"]
    actual_result: OutcomeResult
    decision_event_refs: tuple[str, ...]
    execution_refs: tuple[str, ...]
    duration_days: int
    duration_kind: Literal["so_far", "final"]
    method_id: str
    method_version: str
    calculation_code_version: str
    provenance: tuple[EvidenceProvenance, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionImmediateOutcome:
    """Execution-backed before/execution/after facts for one DecisionEvent."""

    outcome_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    episode_id: str
    decision_event_id: str
    event_type: str
    event_time: pd.Timestamp
    relation_types: tuple[RelationType, ...]
    before: OutcomePositionState
    execution_id: str
    side: Literal["BUY", "SELL"]
    executed_quantity: float
    execution_price: float
    execution_fee: float
    execution_source: AuthoritativeSourceRef
    after: OutcomePositionState
    immediate_result: OutcomeResult | None
    episode_result_ref: str
    evidence_refs: tuple[str, ...]
    method_id: str
    method_version: str
    calculation_code_version: str
    provenance: tuple[EvidenceProvenance, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutcomeAttributionAnalysis:
    """Ordered actual outcomes for one subject/account as of one instant."""

    subject_id: str
    account_id: str
    analysis_as_of: pd.Timestamp
    episode_outcomes: tuple[EpisodeOutcome, ...]
    decision_outcomes: tuple[DecisionImmediateOutcome, ...]
    method_id: str
    method_version: str
    calculation_code_version: str
    data_tier: DataTier
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CounterfactualScenarioDefinition:
    scenario_id: str
    scenario_version: str
    applicable_event_types: tuple[str, ...]
    changed_action: str
    evaluation_horizon: str
    downstream_order_policy: str
    price_basis: str
    friction_basis: str
    feasibility_conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CounterfactualIntervention:
    changed_action: str
    changed_execution_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutcomeComparison:
    comparison_status: ComparisonStatus
    result_basis: ResultBasis | None
    pnl_difference: float | None
    actual_result_sign: ResultSign | None
    counterfactual_result_sign: ResultSign | None
    result_transition: ResultTransition | None


@dataclass(frozen=True, slots=True)
class HistoricalCounterfactualResult:
    """One versioned retrospective alternative path; never an optimizer."""

    counterfactual_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    episode_id: str
    decision_event_id: str
    scenario_id: str
    scenario_version: str
    method_id: str
    method_version: str
    calculation_code_version: str
    relation_type: Literal[
        "historical_counterfactual", "registered_baseline_comparison"
    ]
    analysis_as_of: pd.Timestamp
    decision_at: pd.Timestamp
    evaluation_end: pd.Timestamp | None
    intervention: CounterfactualIntervention
    held_constant: tuple[str, ...]
    downstream_order_policy: str
    price_basis: str
    friction_basis: str
    feasibility_status: FeasibilityStatus
    infeasible_reason: str | None
    first_conflicting_execution_id: str | None
    actual_result: OutcomeResult | None
    counterfactual_result: OutcomeResult | None
    comparison: OutcomeComparison
    baseline_evidence_ref: str | None
    provenance: tuple[EvidenceProvenance, ...]
    data_tier: DataTier
    limitations: tuple[str, ...]


_COMMON_LIMITATIONS: Final[tuple[str, ...]] = (
    "Outcome Attribution v1 supports normalized long-only executions only.",
    "Results describe recorded history and registered historical alternatives; they are not forecasts or recommendations.",
    "No downstream order is clamped, resized, deleted, synthesized, or optimized.",
)

_LOCAL_SCENARIO = CounterfactualScenarioDefinition(
    scenario_id="omit_event_until_next_decision_v1",
    scenario_version="1",
    applicable_event_types=("open_position", "add_position", "reduce_position"),
    changed_action="omit_selected_execution",
    evaluation_horizon="strictly_before_next_episode_decision_or_analysis_as_of_for_open_episode",
    downstream_order_policy="exclude_next_and_later_episode_decisions",
    price_basis="recorded_execution_prices_and_market_mark_at_evaluation_end",
    friction_basis="remove_selected_recorded_fee_and_preserve_included_recorded_fees",
    feasibility_conditions=(
        "A legal market mark must exist on the evaluation date.",
        "The selected event must belong to the existing Episode lifecycle.",
    ),
)

_FULL_SCENARIO = CounterfactualScenarioDefinition(
    scenario_id="omit_event_preserve_later_executions_v1",
    scenario_version="1",
    applicable_event_types=("add_position", "reduce_position"),
    changed_action="omit_selected_execution",
    evaluation_horizon="actual_episode_close_or_analysis_as_of_for_open_episode",
    downstream_order_policy="preserve_later_execution_time_side_absolute_quantity_price_and_fee",
    price_basis="recorded_execution_prices_and_market_mark_at_evaluation_end",
    friction_basis="remove_selected_recorded_fee_and_preserve_all_other_recorded_fees",
    feasibility_conditions=(
        "Every preserved downstream execution must remain legal without rewriting.",
        "A legal market mark must exist on the evaluation date.",
    ),
)

_EXIT_SCENARIO = CounterfactualScenarioDefinition(
    scenario_id="existing_exit_evidence_reuse_v1",
    scenario_version="1",
    applicable_event_types=("close_position",),
    changed_action="reference_registered_exit_baseline",
    evaluation_horizon="existing_exit_evidence_policy_horizon",
    downstream_order_policy="not_applicable_existing_evidence",
    price_basis="existing_exit_evidence_price_basis",
    friction_basis="not_applicable_existing_evidence",
    feasibility_conditions=(
        "A same-subject, same-Episode registered Exit Evidence record must be supplied.",
    ),
)

COUNTERFACTUAL_SCENARIOS: Final[Mapping[str, CounterfactualScenarioDefinition]] = (
    MappingProxyType(
        {
            item.scenario_id: item
            for item in (_LOCAL_SCENARIO, _FULL_SCENARIO, _EXIT_SCENARIO)
        }
    )
)


@dataclass(slots=True)
class _ScopedReplay:
    lifecycle: PositionEpisodeLifecycle
    account_id: str
    analysis_as_of: pd.Timestamp
    frame: pd.DataFrame
    market_prices: pd.DataFrame
    portfolio: object
    execution_links: dict[str, ReplayExecutionLink]
    episodes: tuple[PositionEpisode, ...]
    decisions: tuple[DecisionEvent, ...]
    states: dict[str, ReplayPositionState]
    provenance: tuple[EvidenceProvenance, ...]
    replay_scope_id: str
    init_cash: float


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeAttributionError(f"{field_name} must be a non-empty string")
    return value.strip()


def _timestamp(value: object, field_name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise OutcomeAttributionError(f"{field_name} must be a timestamp") from exc
    if pd.isna(timestamp):
        raise OutcomeAttributionError(f"{field_name} cannot be NaT")
    return timestamp


def _stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"


def _result_sign(value: float) -> ResultSign:
    if math.isclose(value, 0.0, rel_tol=1e-9, abs_tol=1e-9):
        return "flat"
    return "profit" if value > 0 else "loss"


def _transition(actual: float, counterfactual: float) -> ResultTransition:
    if math.isclose(actual, counterfactual, rel_tol=1e-9, abs_tol=1e-8):
        return "matched"
    actual_sign = _result_sign(actual)
    counterfactual_sign = _result_sign(counterfactual)
    if actual_sign == "loss":
        if counterfactual_sign == "flat":
            return "loss_to_flat"
        if counterfactual_sign == "profit":
            return "loss_to_profit"
        return "loss_reduced" if counterfactual > actual else "loss_increased"
    if actual_sign == "profit":
        if counterfactual_sign == "flat":
            return "profit_to_flat"
        if counterfactual_sign == "loss":
            return "profit_to_loss"
        return "profit_increased" if counterfactual > actual else "profit_reduced"
    return "flat_to_profit" if counterfactual_sign == "profit" else "flat_to_loss"


def compare_outcome_results(
    actual: OutcomeResult,
    counterfactual: OutcomeResult,
) -> OutcomeComparison:
    """Compare only equal bases; difference is always counterfactual minus actual."""

    if actual.result_basis != counterfactual.result_basis:
        return OutcomeComparison(
            comparison_status="unavailable_result_basis_mismatch",
            result_basis=None,
            pnl_difference=None,
            actual_result_sign=actual.result_sign,
            counterfactual_result_sign=counterfactual.result_sign,
            result_transition=None,
        )
    return OutcomeComparison(
        comparison_status="complete",
        result_basis=actual.result_basis,
        pnl_difference=counterfactual.pnl - actual.pnl,
        actual_result_sign=actual.result_sign,
        counterfactual_result_sign=counterfactual.result_sign,
        result_transition=_transition(actual.pnl, counterfactual.pnl),
    )


def _cash_for_account(init_cash: float | Mapping[str, float], account_id: str) -> float:
    raw = init_cash.get(account_id) if isinstance(init_cash, Mapping) else init_cash
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise OutcomeAttributionError("init_cash must provide a numeric account value") from exc
    if not math.isfinite(value) or value <= 0:
        raise OutcomeAttributionError("init_cash must be finite and positive")
    return value


def _account_frame(
    executions: pd.DataFrame,
    *,
    subject_id: str,
    account_id: str,
    through: pd.Timestamp,
) -> pd.DataFrame:
    if not isinstance(executions, pd.DataFrame) or executions.empty:
        raise OutcomeAttributionError("At least one execution is required")
    rows = executions.copy(deep=True)
    if "account_id" in rows:
        if rows["account_id"].isna().any():
            raise OutcomeAttributionError("execution account_id cannot be null")
        normalized = rows["account_id"].astype(str).str.strip()
        rows = rows.loc[normalized == account_id].copy()
    if rows.empty:
        raise OutcomeAttributionError(f"No executions belong to account {account_id}")
    if "subject_id" in rows:
        values = rows["subject_id"].map(
            lambda value: "" if pd.isna(value) else str(value).strip()
        )
        if not values.eq(subject_id).all():
            raise OutcomeAttributionError("execution subject_id does not match analysis subject")
    try:
        rows["event_time"] = pd.to_datetime(rows["event_time"], errors="raise")
    except (KeyError, TypeError, ValueError) as exc:
        raise OutcomeAttributionError("execution event_time must contain timestamps") from exc
    rows = rows.loc[rows["event_time"] <= through].copy()
    if rows.empty:
        raise OutcomeAttributionError("No executions are available by analysis_as_of")
    try:
        return _validated_executions(rows).reset_index(drop=True)
    except (KeyError, PortfolioReplayError) as exc:
        raise OutcomeAttributionError(str(exc)) from exc


def _market_rows_through(
    market_prices: pd.DataFrame,
    through: pd.Timestamp,
) -> pd.DataFrame:
    if not isinstance(market_prices, pd.DataFrame) or "date" not in market_prices:
        raise OutcomeAttributionError("market_prices.date is required")
    rows = market_prices.copy(deep=True)
    try:
        dates = pd.to_datetime(rows["date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise OutcomeAttributionError("market price dates must be valid") from exc
    if dates.isna().any():
        raise OutcomeAttributionError("market price dates cannot be null")
    rows = rows.loc[dates.dt.normalize() <= through.normalize()].copy()
    if rows.empty:
        raise OutcomeAttributionError("No market data is available by the required horizon")
    return rows


def _canonical_provenance(
    provenance: Sequence[EvidenceProvenance],
) -> tuple[EvidenceProvenance, ...]:
    return tuple(sorted(provenance, key=lambda item: canonical_json_bytes(item.identity_payload())))


def _scope_id(
    frame: pd.DataFrame,
    *,
    account_id: str,
    through: pd.Timestamp,
    provenance: Sequence[EvidenceProvenance],
    label: str,
) -> str:
    return _stable_id(
        "replay",
        {
            "method_id": "vectorbt_portfolio_replay_v1",
            "label": label,
            "account_id": account_id,
            "through": through.isoformat(),
            "execution_refs": list(frame["execution_id"].astype(str)),
            "provenance": [item.identity_payload() for item in _canonical_provenance(provenance)],
        },
    )


def _prepare_scope(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    subject_id: str,
    account_id: str,
    analysis_as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
) -> _ScopedReplay:
    subject = _required_text(subject_id, "subject_id")
    account = _required_text(account_id, "account_id")
    as_of = _timestamp(analysis_as_of, "analysis_as_of")
    if lifecycle.subject_id != subject:
        raise OutcomeAttributionError("lifecycle subject_id does not match analysis subject")
    if lifecycle.as_of != as_of:
        raise OutcomeAttributionError("lifecycle.as_of must equal analysis_as_of")

    frame = _account_frame(
        executions,
        subject_id=subject,
        account_id=account,
        through=as_of,
    )
    execution_order = {
        execution_id: index
        for index, execution_id in enumerate(frame["execution_id"].astype(str))
    }
    account_episodes = tuple(
        item for item in lifecycle.episodes if item.account_id == account
    )
    if not account_episodes:
        raise OutcomeAttributionError(f"Lifecycle has no Episodes for account {account}")
    try:
        episodes = tuple(
            sorted(
                account_episodes,
                key=lambda item: execution_order[item.opening_execution_id],
            )
        )
    except KeyError as exc:
        raise OutcomeAttributionError(
            "Episode opening execution is missing from authoritative executions"
        ) from exc
    calculation_versions = {item.calculation_code_version for item in episodes}
    if len(calculation_versions) != 1:
        raise OutcomeAttributionError(
            "Account Episodes must share one calculation_code_version"
        )
    episode_ids = {item.episode_id for item in episodes}
    account_decisions = tuple(
        item for item in lifecycle.decisions if item.episode_id in episode_ids
    )
    try:
        decisions = tuple(
            sorted(
                account_decisions,
                key=lambda item: execution_order[item.execution_id],
            )
        )
    except KeyError as exc:
        raise OutcomeAttributionError(
            "Decision execution is missing from authoritative executions"
        ) from exc
    states = {
        item.state_id: item
        for item in lifecycle.states
        if item.account_id == account
    }
    expected_execution_refs = {
        execution_id for episode in episodes for execution_id in episode.execution_refs
    }
    if set(frame["execution_id"].astype(str)) != expected_execution_refs:
        raise OutcomeAttributionError(
            "Lifecycle execution refs do not match the authoritative account executions"
        )
    price_rows = _market_rows_through(market_prices, as_of)
    cash = _cash_for_account(init_cash, account)
    try:
        context = prepare_behavior_replay(frame, price_rows, init_cash=cash)
    except BehaviorReplayError as exc:
        raise OutcomeAttributionError(str(exc)) from exc
    provenance = _canonical_provenance(
        tuple(adapt_price_provenance(item) for item in context.provenance)
    )
    replay_scope_id = _scope_id(
        frame,
        account_id=account,
        through=as_of,
        provenance=provenance,
        label="actual",
    )
    return _ScopedReplay(
        lifecycle=lifecycle,
        account_id=account,
        analysis_as_of=as_of,
        frame=frame,
        market_prices=price_rows,
        portfolio=context.portfolio,
        execution_links={item.execution_id: item for item in context.execution_links},
        episodes=episodes,
        decisions=decisions,
        states=states,
        provenance=provenance,
        replay_scope_id=replay_scope_id,
        init_cash=cash,
    )


def _unique(records: pd.DataFrame, mask: pd.Series, description: str) -> pd.Series:
    matched = records.loc[mask]
    if len(matched) != 1:
        raise OutcomeAttributionError(
            f"Expected one authoritative {description} record, found {len(matched)}"
        )
    return matched.iloc[0]


def _same_number(left: object, right: object) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-8)
    except (TypeError, ValueError):
        return False


def _source_ref(
    source_kind: SourceKind,
    *,
    replay_scope_id: str | None,
    account_id: str,
    instrument_id: str,
    record_id: int | str,
    execution_refs: Sequence[str],
) -> AuthoritativeSourceRef:
    refs = tuple(str(item) for item in execution_refs)
    source_record_id = (
        f"{source_kind}:{replay_scope_id or 'registered'}:"
        f"{account_id}:{instrument_id}:{record_id}"
    )
    return AuthoritativeSourceRef(
        source_kind=source_kind,
        source_record_id=source_record_id,
        replay_scope_id=replay_scope_id,
        vectorbt_record_id=int(record_id) if isinstance(record_id, (int, np.integer)) else None,
        execution_refs=refs,
    )


def _order_record(scope: _ScopedReplay, decision: DecisionEvent) -> pd.Series:
    records = scope.portfolio.orders.records_readable
    link = scope.execution_links.get(decision.execution_id)
    if link is None:
        raise OutcomeAttributionError(
            f"Execution {decision.execution_id} has no verified replay link"
        )
    record = _unique(
        records,
        records["Order Id"] == link.vectorbt_order_record_id,
        f"order for execution {decision.execution_id}",
    )
    expected_side = "Buy" if decision.side == "BUY" else "Sell"
    if (
        str(record["Side"]) != expected_side
        or not _same_number(record["Size"], decision.executed_quantity)
        or not _same_number(record["Price"], decision.execution_price)
        or not _same_number(record["Fees"], decision.fees)
    ):
        raise OutcomeAttributionError(
            f"vectorbt order does not match execution {decision.execution_id}"
        )
    return record


def _exit_trade_record(scope: _ScopedReplay, decision: DecisionEvent) -> pd.Series:
    records = scope.portfolio.exit_trades.records_readable
    link = scope.execution_links.get(decision.execution_id)
    if link is None or link.vectorbt_exit_trade_record_id is None:
        raise OutcomeAttributionError(
            f"outcome_mapping_unavailable for execution {decision.execution_id}"
        )
    record = _unique(
        records,
        (records["Exit Trade Id"] == link.vectorbt_exit_trade_record_id)
        & (records["Status"].astype(str) == "Closed"),
        f"closed exit trade for execution {decision.execution_id}",
    )
    if (
        not _same_number(record["Size"], decision.executed_quantity)
        or not _same_number(record["Avg Exit Price"], decision.execution_price)
        or not _same_number(record["Exit Fees"], decision.fees)
    ):
        raise OutcomeAttributionError(
            f"vectorbt exit trade does not match execution {decision.execution_id}"
        )
    return record


def _episode(scope: _ScopedReplay, episode_id: str) -> PositionEpisode:
    items = [item for item in scope.episodes if item.episode_id == episode_id]
    if len(items) != 1:
        raise OutcomeAttributionError(f"Unknown or ambiguous Episode: {episode_id}")
    return items[0]


def _position_record(
    portfolio: object,
    *,
    episode: PositionEpisode,
    execution_links: Mapping[str, ReplayExecutionLink] | None = None,
) -> pd.Series | None:
    records = portfolio.positions.records_readable
    if records.empty:
        return None
    position_id: int | None = None
    if execution_links is not None:
        link = execution_links.get(episode.opening_execution_id)
        if link is not None:
            position_id = link.vectorbt_position_record_id
    if position_id is None and execution_links is None:
        position_id = episode.vectorbt_position_record_id
    if position_id is not None:
        matched = records.loc[records["Position Id"] == position_id]
    else:
        # A long-only replay has at most one currently open position per
        # instrument.  This fallback is for counterfactual scopes whose record
        # IDs may differ from the actual Episode.
        matched = records.loc[
            (records["Column"].astype(str) == episode.instrument_id)
            & (records["Status"].astype(str) == "Open")
        ]
    if len(matched) > 1:
        raise OutcomeAttributionError(
            f"Episode {episode.episode_id} maps to multiple vectorbt Position records"
        )
    return None if matched.empty else matched.iloc[0]


def _position_outcome_result(
    portfolio: object,
    record: pd.Series,
    *,
    account_id: str,
    episode: PositionEpisode,
    replay_scope_id: str,
    execution_refs: Sequence[str],
    result_kind: ResultKind | None = None,
) -> OutcomeResult:
    status = str(record["Status"])
    if status not in {"Open", "Closed"}:
        raise OutcomeAttributionError("vectorbt Position status is unsupported")
    valuation_at: pd.Timestamp | None = None
    valuation_price: float | None = None
    if status == "Open":
        valuation_at = pd.Timestamp(portfolio.close.index[-1])
        try:
            valuation_price = float(portfolio.close[episode.instrument_id].iloc[-1])
        except (KeyError, TypeError, ValueError) as exc:
            raise OutcomeAttributionError("Open Position valuation mark is unavailable") from exc
    mapped = from_vectorbt_position_record(
        record,
        valuation_time=valuation_at,
        valuation_price=valuation_price,
    )
    kind: ResultKind = result_kind or ("realized" if status == "Closed" else "marked")
    source = _source_ref(
        "vectorbt_position",
        replay_scope_id=replay_scope_id,
        account_id=account_id,
        instrument_id=episode.instrument_id,
        record_id=int(record["Position Id"]),
        execution_refs=execution_refs,
    )
    return OutcomeResult(
        result_kind=kind,
        result_basis="net_pnl",
        pnl=mapped.pnl,
        return_value=mapped.return_value,
        result_sign=_result_sign(mapped.pnl),
        position_status="closed" if status == "Closed" else "open",
        recorded_entry_fees=mapped.entry_fees,
        recorded_exit_fees=float(record["Exit Fees"]),
        valuation_at=mapped.valuation_time,
        valuation_price=mapped.valuation_price,
        source=source,
    )


def _exit_trade_result(
    record: pd.Series,
    *,
    scope: _ScopedReplay,
    decision: DecisionEvent,
    episode: PositionEpisode,
) -> OutcomeResult:
    pnl = float(record["PnL"])
    return OutcomeResult(
        result_kind="realized",
        result_basis="net_pnl",
        pnl=pnl,
        return_value=float(record["Return"]),
        result_sign=_result_sign(pnl),
        position_status="closed",
        recorded_entry_fees=float(record["Entry Fees"]),
        recorded_exit_fees=float(record["Exit Fees"]),
        valuation_at=None,
        valuation_price=None,
        source=_source_ref(
            "vectorbt_exit_trade",
            replay_scope_id=scope.replay_scope_id,
            account_id=scope.account_id,
            instrument_id=episode.instrument_id,
            record_id=int(record["Exit Trade Id"]),
            execution_refs=(decision.execution_id,),
        ),
    )


def _state_view(
    state: ReplayPositionState,
    *,
    position_status: Literal["flat", "open"],
) -> OutcomePositionState:
    return OutcomePositionState(
        state_ref=state.state_id,
        quantity=state.quantity,
        average_cost=state.average_cost,
        position_status=position_status,
    )


def build_actual_outcomes(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    subject_id: str,
    account_id: str,
    analysis_as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
) -> OutcomeAttributionAnalysis:
    """Map actual Episode and Decision outcomes from authoritative records."""

    scope = _prepare_scope(
        lifecycle,
        executions,
        market_prices,
        subject_id=subject_id,
        account_id=account_id,
        analysis_as_of=analysis_as_of,
        init_cash=init_cash,
    )
    episode_outcomes: list[EpisodeOutcome] = []
    episode_outcome_id_by_id: dict[str, str] = {}
    for episode in scope.episodes:
        record = _position_record(
            scope.portfolio,
            episode=episode,
            execution_links=scope.execution_links,
        )
        if record is None:
            raise OutcomeAttributionError(
                f"Episode {episode.episode_id} has no vectorbt Position record"
            )
        status = str(record["Status"]).lower()
        if status != episode.status:
            raise OutcomeAttributionError(
                f"Episode {episode.episode_id} status does not match vectorbt Position"
            )
        result = _position_outcome_result(
            scope.portfolio,
            record,
            account_id=scope.account_id,
            episode=episode,
            replay_scope_id=scope.replay_scope_id,
            execution_refs=episode.execution_refs,
        )
        relation = (
            "accounting_realized_result"
            if episode.status == "closed"
            else "marked_position_result"
        )
        outcome_id = _stable_id(
            "eo",
            {
                "method_id": OUTCOME_METHOD_ID,
                "method_version": OUTCOME_METHOD_VERSION,
                "episode_id": episode.episode_id,
                "analysis_as_of": scope.analysis_as_of.isoformat(),
                "source_record_id": result.source.source_record_id,
                "calculation_code_version": episode.calculation_code_version,
            },
        )
        episode_outcome_id_by_id[episode.episode_id] = outcome_id
        episode_outcomes.append(
            EpisodeOutcome(
                outcome_id=outcome_id,
                episode_id=episode.episode_id,
                subject_id=lifecycle.subject_id,
                account_id=scope.account_id,
                instrument_id=episode.instrument_id,
                episode_status=episode.status,
                analysis_as_of=scope.analysis_as_of,
                relation_type=relation,
                actual_result=result,
                decision_event_refs=episode.decision_refs,
                execution_refs=episode.execution_refs,
                duration_days=episode.duration_days,
                duration_kind=episode.duration_kind,
                method_id=OUTCOME_METHOD_ID,
                method_version=OUTCOME_METHOD_VERSION,
                calculation_code_version=episode.calculation_code_version,
                provenance=scope.provenance,
                limitations=_COMMON_LIMITATIONS,
            )
        )

    decision_outcomes: list[DecisionImmediateOutcome] = []
    for decision in scope.decisions:
        episode = _episode(scope, decision.episode_id)
        try:
            before = scope.states[decision.state_before_ref]
            after = scope.states[decision.state_after_ref]
        except KeyError as exc:
            raise OutcomeAttributionError("Decision state reference is unresolved") from exc
        order = _order_record(scope, decision)
        order_source = _source_ref(
            "vectorbt_order",
            replay_scope_id=scope.replay_scope_id,
            account_id=scope.account_id,
            instrument_id=episode.instrument_id,
            record_id=int(order["Order Id"]),
            execution_refs=(decision.execution_id,),
        )
        immediate_result: OutcomeResult | None = None
        relations: list[RelationType] = ["deterministic_state_transition"]
        if decision.side == "SELL":
            exit_trade = _exit_trade_record(scope, decision)
            immediate_result = _exit_trade_result(
                exit_trade,
                scope=scope,
                decision=decision,
                episode=episode,
            )
            relations.append("accounting_realized_result")
        outcome_id = _stable_id(
            "do",
            {
                "method_id": OUTCOME_METHOD_ID,
                "method_version": OUTCOME_METHOD_VERSION,
                "decision_event_id": decision.decision_id,
                "order_source": order_source.source_record_id,
                "immediate_source": (
                    immediate_result.source.source_record_id
                    if immediate_result is not None
                    else None
                ),
                "calculation_code_version": episode.calculation_code_version,
            },
        )
        decision_outcomes.append(
            DecisionImmediateOutcome(
                outcome_id=outcome_id,
                subject_id=lifecycle.subject_id,
                account_id=scope.account_id,
                instrument_id=episode.instrument_id,
                episode_id=episode.episode_id,
                decision_event_id=decision.decision_id,
                event_type=decision.decision_type,
                event_time=decision.occurred_at,
                relation_types=tuple(relations),
                before=_state_view(
                    before,
                    position_status="flat" if decision.decision_type == "open_position" else "open",
                ),
                execution_id=decision.execution_id,
                side=decision.side,
                executed_quantity=float(order["Size"]),
                execution_price=float(order["Price"]),
                execution_fee=float(order["Fees"]),
                execution_source=order_source,
                after=_state_view(
                    after,
                    position_status="flat" if decision.decision_type == "close_position" else "open",
                ),
                immediate_result=immediate_result,
                episode_result_ref=episode_outcome_id_by_id[episode.episode_id],
                evidence_refs=tuple(sorted(dict.fromkeys(decision.evidence_refs))),
                method_id=OUTCOME_METHOD_ID,
                method_version=OUTCOME_METHOD_VERSION,
                calculation_code_version=episode.calculation_code_version,
                provenance=scope.provenance,
                limitations=_COMMON_LIMITATIONS,
            )
        )

    return OutcomeAttributionAnalysis(
        subject_id=lifecycle.subject_id,
        account_id=scope.account_id,
        analysis_as_of=scope.analysis_as_of,
        episode_outcomes=tuple(episode_outcomes),
        decision_outcomes=tuple(decision_outcomes),
        method_id=OUTCOME_METHOD_ID,
        method_version=OUTCOME_METHOD_VERSION,
        calculation_code_version=scope.episodes[0].calculation_code_version,
        data_tier=lifecycle.data_tier,
        limitations=_COMMON_LIMITATIONS,
    )


def _evaluation_price(
    price_rows: pd.DataFrame,
    *,
    instrument_id: str,
    evaluation_end: pd.Timestamp,
) -> float:
    try:
        dates = pd.to_datetime(price_rows["date"], errors="raise").dt.normalize()
        instruments = price_rows["instrument"].astype(str)
    except (KeyError, TypeError, ValueError) as exc:
        raise OutcomeAttributionError("Market Data Contract fields are unavailable") from exc
    matched = price_rows.loc[
        (dates == evaluation_end.normalize()) & (instruments == instrument_id)
    ]
    if len(matched) != 1:
        raise OutcomeAttributionError(
            f"No unique market price exists for {instrument_id} at evaluation_end"
        )
    try:
        price = float(matched.iloc[0]["close"])
    except (TypeError, ValueError) as exc:
        raise OutcomeAttributionError("Evaluation price is invalid") from exc
    if not math.isfinite(price) or price <= 0:
        raise OutcomeAttributionError("Evaluation price must be finite and positive")
    return price


def _replayed_result(
    frame: pd.DataFrame,
    price_rows: pd.DataFrame,
    *,
    account_id: str,
    episode: PositionEpisode,
    evaluation_end: pd.Timestamp,
    init_cash: float,
    label: str,
    result_kind: ResultKind | None,
    execution_refs: Sequence[str],
) -> tuple[OutcomeResult, tuple[EvidenceProvenance, ...]]:
    mark = _evaluation_price(
        price_rows,
        instrument_id=episode.instrument_id,
        evaluation_end=evaluation_end,
    )
    if frame.empty:
        replay_scope_id = _stable_id(
            "replay",
            {
                "method_id": "vectorbt_portfolio_replay_v1",
                "label": label,
                "account_id": account_id,
                "through": evaluation_end.isoformat(),
                "execution_refs": [],
            },
        )
        source = _source_ref(
            "registered_counterfactual_position_absent",
            replay_scope_id=replay_scope_id,
            account_id=account_id,
            instrument_id=episode.instrument_id,
            record_id="absent",
            execution_refs=(),
        )
        return (
            OutcomeResult(
                result_kind=result_kind or "marked",
                result_basis="net_pnl",
                pnl=0.0,
                return_value=None,
                result_sign="flat",
                position_status="absent",
                recorded_entry_fees=0.0,
                recorded_exit_fees=0.0,
                valuation_at=evaluation_end.normalize(),
                valuation_price=mark,
                source=source,
            ),
            (),
        )
    try:
        context = prepare_behavior_replay(frame, price_rows, init_cash=init_cash)
    except BehaviorReplayError as exc:
        raise OutcomeAttributionError(str(exc)) from exc
    provenance = _canonical_provenance(
        tuple(adapt_price_provenance(item) for item in context.provenance)
    )
    replay_scope_id = _scope_id(
        frame,
        account_id=account_id,
        through=evaluation_end,
        provenance=provenance,
        label=label,
    )
    record = _position_record(
        context.portfolio,
        episode=episode,
        execution_links={item.execution_id: item for item in context.execution_links},
    )
    if record is None:
        source = _source_ref(
            "vectorbt_replay_position_absent",
            replay_scope_id=replay_scope_id,
            account_id=account_id,
            instrument_id=episode.instrument_id,
            record_id="absent",
            execution_refs=(),
        )
        return (
            OutcomeResult(
                result_kind=result_kind or "marked",
                result_basis="net_pnl",
                pnl=0.0,
                return_value=None,
                result_sign="flat",
                position_status="absent",
                recorded_entry_fees=0.0,
                recorded_exit_fees=0.0,
                valuation_at=pd.Timestamp(context.portfolio.close.index[-1]),
                valuation_price=mark,
                source=source,
            ),
            provenance,
        )
    return (
        _position_outcome_result(
            context.portfolio,
            record,
            account_id=account_id,
            episode=episode,
            replay_scope_id=replay_scope_id,
            execution_refs=execution_refs,
            result_kind=result_kind,
        ),
        provenance,
    )


def _not_applicable_comparison() -> OutcomeComparison:
    return OutcomeComparison(
        comparison_status="not_applicable",
        result_basis=None,
        pnl_difference=None,
        actual_result_sign=None,
        counterfactual_result_sign=None,
        result_transition=None,
    )


def _counterfactual_id_payload(
    *,
    subject_id: str,
    account_id: str,
    episode_id: str,
    decision_event_id: str,
    scenario_id: str,
    scenario_version: str,
    calculation_code_version: str,
    analysis_as_of: pd.Timestamp,
    evaluation_end: pd.Timestamp | None,
    intervention: CounterfactualIntervention,
    held_constant: Sequence[str],
    downstream_order_policy: str,
    price_basis: str,
    friction_basis: str,
    provenance: Sequence[EvidenceProvenance],
) -> dict[str, object]:
    return {
        "method_id": OUTCOME_METHOD_ID,
        "method_version": OUTCOME_METHOD_VERSION,
        "subject_id": subject_id,
        "account_id": account_id,
        "episode_id": episode_id,
        "decision_event_id": decision_event_id,
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "calculation_code_version": calculation_code_version,
        "analysis_as_of": analysis_as_of.isoformat(),
        "evaluation_end": evaluation_end.isoformat() if evaluation_end is not None else None,
        "intervention": {
            "changed_action": intervention.changed_action,
            "changed_execution_refs": sorted(intervention.changed_execution_refs),
        },
        "held_constant": sorted(dict.fromkeys(held_constant)),
        "downstream_order_policy": downstream_order_policy,
        "price_basis": price_basis,
        "friction_basis": friction_basis,
        "provenance": [
            item.identity_payload() for item in _canonical_provenance(provenance)
        ],
    }


def _result_record(
    *,
    scope: _ScopedReplay,
    episode: PositionEpisode,
    decision: DecisionEvent,
    scenario_id: str,
    scenario_version: str,
    relation_type: Literal[
        "historical_counterfactual", "registered_baseline_comparison"
    ],
    evaluation_end: pd.Timestamp | None,
    intervention: CounterfactualIntervention,
    held_constant: Sequence[str],
    downstream_order_policy: str,
    price_basis: str,
    friction_basis: str,
    feasibility_status: FeasibilityStatus,
    infeasible_reason: str | None,
    first_conflicting_execution_id: str | None,
    actual_result: OutcomeResult | None,
    counterfactual_result: OutcomeResult | None,
    comparison: OutcomeComparison,
    baseline_evidence_ref: str | None,
    provenance: Sequence[EvidenceProvenance],
    limitations: Sequence[str],
) -> HistoricalCounterfactualResult:
    canonical_held = tuple(sorted(dict.fromkeys(held_constant)))
    canonical_provenance = _canonical_provenance(provenance)
    counterfactual_id = _stable_id(
        "cf",
        _counterfactual_id_payload(
            subject_id=scope.lifecycle.subject_id,
            account_id=scope.account_id,
            episode_id=episode.episode_id,
            decision_event_id=decision.decision_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            calculation_code_version=episode.calculation_code_version,
            analysis_as_of=scope.analysis_as_of,
            evaluation_end=evaluation_end,
            intervention=intervention,
            held_constant=canonical_held,
            downstream_order_policy=downstream_order_policy,
            price_basis=price_basis,
            friction_basis=friction_basis,
            provenance=canonical_provenance,
        ),
    )
    return HistoricalCounterfactualResult(
        counterfactual_id=counterfactual_id,
        subject_id=scope.lifecycle.subject_id,
        account_id=scope.account_id,
        instrument_id=episode.instrument_id,
        episode_id=episode.episode_id,
        decision_event_id=decision.decision_id,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        method_id=OUTCOME_METHOD_ID,
        method_version=OUTCOME_METHOD_VERSION,
        calculation_code_version=episode.calculation_code_version,
        relation_type=relation_type,
        analysis_as_of=scope.analysis_as_of,
        decision_at=decision.occurred_at,
        evaluation_end=evaluation_end,
        intervention=intervention,
        held_constant=canonical_held,
        downstream_order_policy=downstream_order_policy,
        price_basis=price_basis,
        friction_basis=friction_basis,
        feasibility_status=feasibility_status,
        infeasible_reason=infeasible_reason,
        first_conflicting_execution_id=first_conflicting_execution_id,
        actual_result=actual_result,
        counterfactual_result=counterfactual_result,
        comparison=comparison,
        baseline_evidence_ref=baseline_evidence_ref,
        provenance=canonical_provenance,
        data_tier=scope.lifecycle.data_tier,
        limitations=tuple(dict.fromkeys((*_COMMON_LIMITATIONS, *limitations))),
    )


def _unsupported(
    *,
    scope: _ScopedReplay,
    episode: PositionEpisode,
    decision: DecisionEvent,
    scenario_id: str,
    reason: str,
    scenario: CounterfactualScenarioDefinition | None = None,
) -> HistoricalCounterfactualResult:
    intervention = CounterfactualIntervention(
        changed_action="unsupported",
        changed_execution_refs=(decision.execution_id,),
    )
    return _result_record(
        scope=scope,
        episode=episode,
        decision=decision,
        scenario_id=scenario_id,
        scenario_version=scenario.scenario_version if scenario is not None else "unregistered",
        relation_type="historical_counterfactual",
        evaluation_end=None,
        intervention=intervention,
        held_constant=(),
        downstream_order_policy=(
            scenario.downstream_order_policy if scenario is not None else "none"
        ),
        price_basis=scenario.price_basis if scenario is not None else "none",
        friction_basis=scenario.friction_basis if scenario is not None else "none",
        feasibility_status="unsupported_scenario",
        infeasible_reason=reason,
        first_conflicting_execution_id=None,
        actual_result=None,
        counterfactual_result=None,
        comparison=_not_applicable_comparison(),
        baseline_evidence_ref=None,
        provenance=(),
        limitations=(reason,),
    )


def _episode_decisions(scope: _ScopedReplay, episode_id: str) -> tuple[DecisionEvent, ...]:
    return tuple(item for item in scope.decisions if item.episode_id == episode_id)


def _next_episode_decision(
    scope: _ScopedReplay,
    decision: DecisionEvent,
) -> DecisionEvent | None:
    items = _episode_decisions(scope, decision.episode_id)
    for index, item in enumerate(items):
        if item.decision_id == decision.decision_id:
            return items[index + 1] if index + 1 < len(items) else None
    raise OutcomeAttributionError("Decision is missing from its Episode ordering")


def _execution_refs_for_episode(
    episode: PositionEpisode,
    frame: pd.DataFrame,
) -> tuple[str, ...]:
    included = set(frame["execution_id"].astype(str))
    return tuple(item for item in episode.execution_refs if item in included)


def _first_downstream_conflict(
    scope: _ScopedReplay,
    counterfactual_frame: pd.DataFrame,
    price_rows: pd.DataFrame,
    *,
    decision: DecisionEvent,
) -> str | None:
    actual_order = list(scope.frame["execution_id"].astype(str))
    selected_index = actual_order.index(decision.execution_id)
    downstream = set(actual_order[selected_index + 1 :])
    for index, row in counterfactual_frame.reset_index(drop=True).iterrows():
        execution_id = str(row["execution_id"])
        if execution_id not in downstream:
            continue
        prefix = counterfactual_frame.iloc[: index + 1].copy()
        try:
            prefix_prices = _market_rows_through(price_rows, pd.Timestamp(row["event_time"]))
            prepare_behavior_replay(prefix, prefix_prices, init_cash=scope.init_cash)
        except (BehaviorReplayError, OutcomeAttributionError):
            return execution_id
    return None


def _evaluate_replay_scenario(
    scope: _ScopedReplay,
    *,
    episode: PositionEpisode,
    decision: DecisionEvent,
    scenario: CounterfactualScenarioDefinition,
) -> HistoricalCounterfactualResult:
    next_decision = _next_episode_decision(scope, decision)
    if scenario.scenario_id == _LOCAL_SCENARIO.scenario_id:
        if next_decision is not None:
            evaluation_end = next_decision.occurred_at
            actual_frame = scope.frame.loc[
                scope.frame["event_time"] < evaluation_end
            ].copy()
        elif episode.status == "open":
            evaluation_end = scope.analysis_as_of
            actual_frame = scope.frame.loc[
                scope.frame["event_time"] <= evaluation_end
            ].copy()
        else:
            return _unsupported(
                scope=scope,
                episode=episode,
                decision=decision,
                scenario_id=scenario.scenario_id,
                reason="A closed Episode event has no later Decision horizon",
                scenario=scenario,
            )
    else:
        evaluation_end = episode.closed_at or scope.analysis_as_of
        actual_frame = scope.frame.loc[
            scope.frame["event_time"] <= evaluation_end
        ].copy()

    if evaluation_end > scope.analysis_as_of:
        raise OutcomeAttributionError("evaluation_end cannot exceed analysis_as_of")
    counterfactual_frame = actual_frame.loc[
        actual_frame["execution_id"].astype(str) != decision.execution_id
    ].copy()
    intervention = CounterfactualIntervention(
        changed_action=scenario.changed_action,
        changed_execution_refs=(decision.execution_id,),
    )
    held_constant = (
        "all other execution timestamps",
        "all other symbols",
        "all other sides",
        "all other absolute quantities",
        "all other execution prices",
        "all other recorded fees",
        "historical market observations through evaluation_end",
    )
    try:
        price_rows = _market_rows_through(scope.market_prices, evaluation_end)
        _evaluation_price(
            price_rows,
            instrument_id=episode.instrument_id,
            evaluation_end=evaluation_end,
        )
        actual_result, actual_provenance = _replayed_result(
            actual_frame,
            price_rows,
            account_id=scope.account_id,
            episode=episode,
            evaluation_end=evaluation_end,
            init_cash=scope.init_cash,
            label=f"{scenario.scenario_id}:actual",
            result_kind=None,
            execution_refs=_execution_refs_for_episode(episode, actual_frame),
        )
        counterfactual_result, counterfactual_provenance = _replayed_result(
            counterfactual_frame,
            price_rows,
            account_id=scope.account_id,
            episode=episode,
            evaluation_end=evaluation_end,
            init_cash=scope.init_cash,
            label=f"{scenario.scenario_id}:counterfactual",
            result_kind="counterfactual",
            execution_refs=_execution_refs_for_episode(episode, counterfactual_frame),
        )
    except OutcomeAttributionError as exc:
        conflict = None
        if scenario.scenario_id == _FULL_SCENARIO.scenario_id:
            conflict = _first_downstream_conflict(
                scope,
                counterfactual_frame,
                scope.market_prices,
                decision=decision,
            )
        status: FeasibilityStatus = (
            "infeasible_downstream_execution"
            if conflict is not None
            else "insufficient_counterfactual_data"
        )
        return _result_record(
            scope=scope,
            episode=episode,
            decision=decision,
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            relation_type="historical_counterfactual",
            evaluation_end=evaluation_end,
            intervention=intervention,
            held_constant=held_constant,
            downstream_order_policy=scenario.downstream_order_policy,
            price_basis=scenario.price_basis,
            friction_basis=scenario.friction_basis,
            feasibility_status=status,
            infeasible_reason=str(exc),
            first_conflicting_execution_id=conflict,
            actual_result=None,
            counterfactual_result=None,
            comparison=_not_applicable_comparison(),
            baseline_evidence_ref=None,
            provenance=(),
            limitations=scenario.feasibility_conditions,
        )

    provenance = _canonical_provenance((*actual_provenance, *counterfactual_provenance))
    return _result_record(
        scope=scope,
        episode=episode,
        decision=decision,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        relation_type="historical_counterfactual",
        evaluation_end=evaluation_end,
        intervention=intervention,
        held_constant=held_constant,
        downstream_order_policy=scenario.downstream_order_policy,
        price_basis=scenario.price_basis,
        friction_basis=scenario.friction_basis,
        feasibility_status="complete",
        infeasible_reason=None,
        first_conflicting_execution_id=None,
        actual_result=actual_result,
        counterfactual_result=counterfactual_result,
        comparison=compare_outcome_results(actual_result, counterfactual_result),
        baseline_evidence_ref=None,
        provenance=provenance,
        limitations=scenario.feasibility_conditions,
    )


def _reuse_exit_evidence(
    scope: _ScopedReplay,
    *,
    episode: PositionEpisode,
    decision: DecisionEvent,
    scenario: CounterfactualScenarioDefinition,
    evidence: EvidenceRecord | None,
) -> HistoricalCounterfactualResult:
    intervention = CounterfactualIntervention(
        changed_action=scenario.changed_action,
        changed_execution_refs=(decision.execution_id,),
    )
    if evidence is None:
        return _result_record(
            scope=scope,
            episode=episode,
            decision=decision,
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            relation_type="registered_baseline_comparison",
            evaluation_end=None,
            intervention=intervention,
            held_constant=("existing Exit Evidence method and inputs",),
            downstream_order_policy=scenario.downstream_order_policy,
            price_basis=scenario.price_basis,
            friction_basis=scenario.friction_basis,
            feasibility_status="insufficient_counterfactual_data",
            infeasible_reason="A registered Exit Evidence record is required",
            first_conflicting_execution_id=None,
            actual_result=None,
            counterfactual_result=None,
            comparison=_not_applicable_comparison(),
            baseline_evidence_ref=None,
            provenance=(),
            limitations=scenario.feasibility_conditions,
        )
    if evidence.subject_id != scope.lifecycle.subject_id:
        raise OutcomeAttributionError("Exit Evidence subject_id does not match analysis subject")
    if evidence.metric_id != "exit_timing_post_exit_asset_return":
        raise OutcomeAttributionError("Evidence is not registered Exit Timing Evidence")
    if evidence.attributes.get("episode_id") != episode.episode_id:
        raise OutcomeAttributionError("Exit Evidence does not belong to the selected Episode")
    available_at = evidence_available_at(evidence)
    if available_at is None or available_at > scope.analysis_as_of:
        raise OutcomeAttributionError("Exit Evidence is not available by analysis_as_of")
    actual_analysis = build_actual_outcomes(
        scope.lifecycle,
        scope.frame,
        scope.market_prices,
        subject_id=scope.lifecycle.subject_id,
        account_id=scope.account_id,
        analysis_as_of=scope.analysis_as_of,
        init_cash=scope.init_cash,
    )
    actual_episode = next(
        item for item in actual_analysis.episode_outcomes if item.episode_id == episode.episode_id
    )
    status: FeasibilityStatus = (
        "complete"
        if evidence.evidence_status == "complete"
        else "insufficient_counterfactual_data"
    )
    return _result_record(
        scope=scope,
        episode=episode,
        decision=decision,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        relation_type="registered_baseline_comparison",
        evaluation_end=evidence.observation_end,
        intervention=intervention,
        held_constant=(
            "existing Exit Evidence policy",
            "existing Exit Evidence price observations",
            "existing Exit Evidence method version",
        ),
        downstream_order_policy=scenario.downstream_order_policy,
        price_basis="existing_exit_evidence:exit_session_market_price_to_policy_end",
        friction_basis=scenario.friction_basis,
        feasibility_status=status,
        infeasible_reason=evidence.evidence_reason,
        first_conflicting_execution_id=None,
        actual_result=actual_episode.actual_result,
        counterfactual_result=None,
        comparison=_not_applicable_comparison(),
        baseline_evidence_ref=evidence.evidence_id,
        provenance=evidence.provenance,
        limitations=evidence.limitations,
    )


def evaluate_historical_counterfactual(
    lifecycle: PositionEpisodeLifecycle,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    subject_id: str,
    account_id: str,
    decision_event_id: str,
    scenario_id: str,
    analysis_as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
    exit_evidence: EvidenceRecord | None = None,
) -> HistoricalCounterfactualResult:
    """Evaluate one registered retrospective scenario without rewriting orders."""

    scope = _prepare_scope(
        lifecycle,
        executions,
        market_prices,
        subject_id=subject_id,
        account_id=account_id,
        analysis_as_of=analysis_as_of,
        init_cash=init_cash,
    )
    decision_id = _required_text(decision_event_id, "decision_event_id")
    selected = [item for item in scope.decisions if item.decision_id == decision_id]
    if len(selected) != 1:
        raise OutcomeAttributionError("decision_event_id is unknown or ambiguous")
    decision = selected[0]
    episode = _episode(scope, decision.episode_id)
    scenario_key = _required_text(scenario_id, "scenario_id")
    scenario = COUNTERFACTUAL_SCENARIOS.get(scenario_key)
    if scenario is None:
        return _unsupported(
            scope=scope,
            episode=episode,
            decision=decision,
            scenario_id=scenario_key,
            reason=f"Scenario is not registered: {scenario_key}",
        )
    if decision.decision_type not in scenario.applicable_event_types:
        return _unsupported(
            scope=scope,
            episode=episode,
            decision=decision,
            scenario_id=scenario.scenario_id,
            reason=(
                f"Scenario {scenario.scenario_id} does not support "
                f"{decision.decision_type}"
            ),
            scenario=scenario,
        )
    if scenario.scenario_id == _EXIT_SCENARIO.scenario_id:
        return _reuse_exit_evidence(
            scope,
            episode=episode,
            decision=decision,
            scenario=scenario,
            evidence=exit_evidence,
        )
    return _evaluate_replay_scenario(
        scope,
        episode=episode,
        decision=decision,
        scenario=scenario,
    )
