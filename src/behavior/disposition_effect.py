"""Odean-style disposition evidence from deterministic vectorbt state."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.attribution.selection_evidence import PriceProvenance
from src.behavior.replay_state import (
    BehaviorReplayError,
    market_price,
    prefix_portfolio_state,
    prepare_behavior_replay,
)


METHOD_ID: Final = "odean_pgr_plr_v1"
METHOD_SOURCE: Final = (
    "Odean-style product implementation v1, following Odean (1998), Are "
    "Investors Reluctant to Realize Their Losses?: "
    "PGR = RG / (RG + PG) and PLR = RL / (RL + PL), with realized outcomes "
    "counted at SELL executions and paper opportunities on sale calendar days."
)
SAMPLE_BASIS: Final = (
    "SELL-execution realized outcomes and stock-level paper opportunities at "
    "distinct sale calendar days."
)
LIMITATION: Final = (
    "This is observable historical evidence, not a psychological diagnosis or "
    "skill score. Realized outcomes use actual SELL execution prices; paper "
    "outcomes use the Market Data Contract's same-day close. Both are compared "
    "with vectorbt open-position average entry price, and neutral observations "
    "are excluded. A sale day symbol counts as a paper opportunity only through "
    "its residual shares (pre-sale quantity minus the day's sold quantity); a "
    "full exit on the day contributes none. This is not a full Odean replication "
    "and does not reproduce tax-lot, commission-adjusted, or daily high/low "
    "research data treatment."
)

EvidenceStatus = Literal["complete", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class DispositionEffectEvidence:
    method_id: str
    method_source: str
    sample_basis: str
    observation_count: int
    realized_gains: int
    paper_gains: int
    realized_losses: int
    paper_losses: int
    neutral_observations: int
    pgr: float | None
    plr: float | None
    disposition_effect: float | None
    eligible_sale_events: int
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: tuple[PriceProvenance, ...]
    synthetic_provenance_present: bool
    limitation: str


def _result(
    *,
    realized_gains: int = 0,
    paper_gains: int = 0,
    realized_losses: int = 0,
    paper_losses: int = 0,
    neutral_observations: int = 0,
    eligible_sale_events: int = 0,
    provenance: tuple[PriceProvenance, ...] = (),
    reason: str | None = None,
) -> DispositionEffectEvidence:
    gain_denominator = realized_gains + paper_gains
    loss_denominator = realized_losses + paper_losses
    pgr = realized_gains / gain_denominator if gain_denominator else None
    plr = realized_losses / loss_denominator if loss_denominator else None
    disposition_effect = pgr - plr if pgr is not None and plr is not None else None

    missing_denominators: list[str] = []
    if gain_denominator == 0:
        missing_denominators.append("PGR denominator is zero")
    if loss_denominator == 0:
        missing_denominators.append("PLR denominator is zero")
    if eligible_sale_events == 0 and reason is None:
        reason = "No sale decision events are available"
    if reason is None and missing_denominators:
        reason = "; ".join(missing_denominators)
    status: EvidenceStatus = "complete" if reason is None else "insufficient_evidence"

    return DispositionEffectEvidence(
        method_id=METHOD_ID,
        method_source=METHOD_SOURCE,
        sample_basis=SAMPLE_BASIS,
        observation_count=(
            realized_gains
            + paper_gains
            + realized_losses
            + paper_losses
            + neutral_observations
        ),
        realized_gains=realized_gains,
        paper_gains=paper_gains,
        realized_losses=realized_losses,
        paper_losses=paper_losses,
        neutral_observations=neutral_observations,
        pgr=pgr,
        plr=plr,
        disposition_effect=disposition_effect,
        eligible_sale_events=eligible_sale_events,
        evidence_status=status,
        evidence_reason=reason,
        provenance=provenance,
        synthetic_provenance_present=any(item.is_synthetic for item in provenance),
        limitation=LIMITATION,
    )


def _classify(price: float, average_cost: float) -> str:
    if math.isclose(price, average_cost, rel_tol=1e-12, abs_tol=1e-12):
        return "neutral"
    return "gain" if price > average_cost else "loss"


def build_disposition_effect_evidence(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> DispositionEffectEvidence:
    """Count sale-decision opportunities without recomputing portfolio state."""

    try:
        context = prepare_behavior_replay(
            executions,
            market_prices,
            init_cash=init_cash,
        )
    except BehaviorReplayError as exc:
        return _result(reason=str(exc))

    sales = context.executions[context.executions["side"] == "SELL"]
    if sales.empty:
        return _result(provenance=context.provenance)

    sales = sales.assign(sale_date=sales["event_time"].dt.normalize())
    realized_gains = paper_gains = realized_losses = paper_losses = 0
    neutral_observations = eligible_sale_events = 0
    try:
        for _, sale_day_rows in sales.groupby("sale_date", sort=True):
            sale_day_rows = sale_day_rows.sort_values("event_time", kind="stable")
            first_sale_time = pd.Timestamp(sale_day_rows["event_time"].iloc[0])
            paper_state = prefix_portfolio_state(context, first_sale_time)

            state_by_time = {}
            for row in sale_day_rows.itertuples(index=False):
                event_time = pd.Timestamp(row.event_time)
                if event_time not in state_by_time:
                    state_by_time[event_time] = prefix_portfolio_state(
                        context,
                        event_time,
                    )
                sale_state = state_by_time[event_time]
                symbol = str(row.symbol)
                quantity = float(sale_state.holdings.get(symbol, 0.0))
                average_cost = sale_state.average_costs.get(symbol)
                if quantity <= 0 or average_cost is None:
                    raise BehaviorReplayError(
                        f"Pre-sale position or average cost is unavailable for {symbol}"
                    )
                outcome = _classify(float(row.executed_price), average_cost)
                if outcome == "gain":
                    realized_gains += 1
                elif outcome == "loss":
                    realized_losses += 1
                else:
                    neutral_observations += 1

            # Symbols fully exited today are not paper opportunities anymore;
            # a PARTIAL exit leaves a residual position that is still one —
            # excluding it would bias PGR/PLR denominators on scale-outs.
            sold_quantity_by_symbol = {}
            for row in sale_day_rows.itertuples(index=False):
                sold_quantity_by_symbol[str(row.symbol)] = (
                    sold_quantity_by_symbol.get(str(row.symbol), 0.0) + float(row.executed_quantity))
            for symbol, quantity in paper_state.holdings.items():
                residual = quantity - sold_quantity_by_symbol.get(symbol, 0.0)
                if quantity <= 0 or residual <= 1e-12:
                    continue
                quantity = residual
                average_cost = paper_state.average_costs.get(symbol)
                if average_cost is None:
                    raise BehaviorReplayError(
                        f"Average cost is unavailable for held symbol {symbol}"
                    )
                outcome = _classify(
                    market_price(context, first_sale_time, str(symbol)),
                    average_cost,
                )
                if outcome == "gain":
                    paper_gains += 1
                elif outcome == "loss":
                    paper_losses += 1
                else:
                    neutral_observations += 1
            eligible_sale_events += 1
    except BehaviorReplayError as exc:
        return _result(provenance=context.provenance, reason=str(exc))

    return _result(
        realized_gains=realized_gains,
        paper_gains=paper_gains,
        realized_losses=realized_losses,
        paper_losses=paper_losses,
        neutral_observations=neutral_observations,
        eligible_sale_events=eligible_sale_events,
        provenance=context.provenance,
    )
