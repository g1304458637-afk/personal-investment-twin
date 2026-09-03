"""Observable loss-state additions without motive or quality judgments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.attribution.selection_evidence import PriceProvenance
from src.behavior.replay_state import (
    BehaviorReplayError,
    prefix_portfolio_state,
    prepare_behavior_replay,
)


METHOD_ID: Final = "loss_state_add_v1"
METHOD_SOURCE: Final = (
    "Transparent product rule: an existing Long position is increased while the "
    "BUY execution price is below its strict pre-trade vectorbt average cost."
)
SAMPLE_BASIS: Final = "BUY executions, with event rate measured over existing-position adds."
LIMITATION: Final = (
    "A detected event only means that quantity was added while the position was "
    "below average cost. It is not evidence of revenge trading, irrationality, "
    "greed, fear, FOMO, investment skill, or whether the decision was good or bad."
)

EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class LossAveragingEvent:
    event_time: pd.Timestamp
    symbol: str
    pre_trade_position: float
    pre_trade_avg_cost: float | None
    execution_price: float
    added_quantity: float
    eligible_event: bool
    event_detected: bool
    execution_id: str | None = None


@dataclass(frozen=True, slots=True)
class LossAveragingEvidence:
    method_id: str
    method_source: str
    sample_basis: str
    observation_count: int
    events: tuple[LossAveragingEvent, ...]
    eligible_add_events: int
    loss_averaging_events: int
    event_rate: float | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: tuple[PriceProvenance, ...]
    synthetic_provenance_present: bool
    limitation: str


def _result(
    *,
    events: tuple[LossAveragingEvent, ...] = (),
    provenance: tuple[PriceProvenance, ...] = (),
    reason: str | None = None,
) -> LossAveragingEvidence:
    eligible = sum(event.eligible_event for event in events)
    detected = sum(event.event_detected for event in events)
    event_rate = detected / eligible if eligible else None
    if eligible == 0 and reason is None:
        reason = "No existing-position BUY events are available"
    status: EvidenceStatus = "complete" if reason is None else "insufficient_evidence"
    return LossAveragingEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=len(events),
        events=events,
        eligible_add_events=eligible,
        loss_averaging_events=detected,
        event_rate=event_rate,
        evidence_status=status,
        evidence_reason=reason,
        provenance=provenance,
        synthetic_provenance_present=any(item.is_synthetic for item in provenance),
        limitation=LIMITATION,
    )


def build_loss_averaging_evidence(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> LossAveragingEvidence:
    """Inspect each BUY against vectorbt's deterministic pre-trade state."""

    try:
        context = prepare_behavior_replay(
            executions,
            market_prices,
            init_cash=init_cash,
        )
    except BehaviorReplayError as exc:
        return _result(reason=str(exc))

    buys = context.executions[context.executions["side"] == "BUY"]
    events: list[LossAveragingEvent] = []
    state_by_time = {}
    try:
        for row in buys.itertuples(index=False):
            event_time = pd.Timestamp(row.event_time)
            if event_time not in state_by_time:
                state_by_time[event_time] = prefix_portfolio_state(context, event_time)
            state = state_by_time[event_time]
            symbol = str(row.symbol)
            pre_trade_position = float(state.holdings.get(symbol, 0.0))
            execution_price = float(row.executed_price)
            eligible = pre_trade_position > 0
            average_cost = state.average_costs.get(symbol) if eligible else None
            if eligible and (
                average_cost is None
                or not math.isfinite(average_cost)
                or average_cost <= 0
            ):
                raise BehaviorReplayError(
                    f"Pre-trade average cost is unavailable for {symbol}"
                )
            events.append(
                LossAveragingEvent(
                    event_time=event_time,
                    symbol=symbol,
                    pre_trade_position=pre_trade_position,
                    pre_trade_avg_cost=average_cost,
                    execution_price=execution_price,
                    added_quantity=float(row.executed_quantity),
                    eligible_event=eligible,
                    event_detected=(
                        eligible and execution_price < float(average_cost)
                    ),
                    execution_id=str(row.execution_id),
                )
            )
    except (BehaviorReplayError, TypeError, ValueError) as exc:
        return _result(provenance=context.provenance, reason=str(exc))

    return _result(events=tuple(events), provenance=context.provenance)
