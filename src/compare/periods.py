"""Calendar-bounded behavior summaries assembled from the existing evidence builders.

The period is ``(start_date, end_date]`` by calendar day.  Replays always keep
the complete account prefix through ``end_date``: the start boundary filters
reported observations and additive counts, never the state used to interpret a
later execution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.behavior import disposition_effect as disposition_module
from src.behavior import loss_averaging as loss_module
from src.behavior.disposition_effect import DispositionEffectEvidence, build_disposition_effect_evidence
from src.behavior.loss_averaging import LossAveragingEvidence, build_loss_averaging_evidence
from src.behavior.portfolio_concentration import (
    PortfolioConcentrationEvidence,
    build_portfolio_concentration_evidence,
)
from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay
from src.behavior.turnover_intensity import (
    DailyTurnoverObservation,
    build_turnover_intensity_evidence,
)


METHOD_ID = "calendar_period_behavior_v1"
METHOD_VERSION = "1"


class PeriodBehaviorUnavailable(ValueError):
    """The requested bounded period cannot be supported by exact source facts."""


@dataclass(frozen=True, slots=True)
class PeriodBehaviorSummary:
    method_id: str
    method_version: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    observation_count: int
    daily_turnover: tuple[DailyTurnoverObservation, ...]
    mean_daily_turnover: float | None
    total_traded_value: float | None
    recorded_fee_total: float
    action_count: int
    hhi_end: float | None
    top1_weight: float | None
    top3_weight: float | None
    concentration: PortfolioConcentrationEvidence
    disposition: DispositionEffectEvidence
    loss_averaging: LossAveragingEvidence


def _calendar_date(value: object, field: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tz is not None:
        raise PeriodBehaviorUnavailable(f"{field} must be a timezone-free calendar date")
    if stamp != stamp.normalize():
        raise PeriodBehaviorUnavailable(f"{field} must be midnight; period boundaries are date-only")
    return stamp.normalize()


def _known_count_result(evidence: object) -> bool:
    """Zero denominator is a valid count result, unlike a replay/data failure."""
    if evidence.evidence_status == "complete":
        return True
    allowed = {
        "No sale decision events are available",
        "PGR denominator is zero",
        "PLR denominator is zero",
        "No existing-position BUY events are available",
    }
    reason = evidence.evidence_reason
    return isinstance(reason, str) and bool(reason) and set(reason.split("; ")).issubset(allowed)


def _bounded_inputs(
    executions: pd.DataFrame, market_prices: pd.DataFrame, end_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(executions, pd.DataFrame) or "event_time" not in executions:
        raise PeriodBehaviorUnavailable("executions must include event_time")
    if not isinstance(market_prices, pd.DataFrame) or "date" not in market_prices:
        raise PeriodBehaviorUnavailable("market_prices must include date")
    try:
        event_days = pd.to_datetime(
            executions["event_time"], errors="raise", format="mixed",
        ).dt.normalize()
        price_days = pd.to_datetime(
            market_prices["date"], errors="raise", format="mixed",
        ).dt.normalize()
    except (TypeError, ValueError) as exc:
        raise PeriodBehaviorUnavailable("execution and market dates must be valid") from exc
    prefix_executions = executions.loc[event_days <= end_date].copy()
    prefix_prices = market_prices.loc[price_days <= end_date].copy()
    if prefix_executions.empty:
        raise PeriodBehaviorUnavailable("no executions are available through end_date")
    if prefix_prices.empty:
        raise PeriodBehaviorUnavailable("no market prices are available through end_date")
    return prefix_executions, prefix_prices


def _prices_through(market_prices: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    days = pd.to_datetime(market_prices["date"], errors="raise", format="mixed").dt.normalize()
    return market_prices.loc[days <= date].copy()


def _period_disposition(
    executions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    init_cash: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> DispositionEffectEvidence:
    """Subtract only additive full-prefix counts; never subtract PGR/PLR ratios."""
    through_end = build_disposition_effect_evidence(executions, prices, init_cash=init_cash)
    if not _known_count_result(through_end):
        raise PeriodBehaviorUnavailable(
            f"disposition evidence unavailable: {through_end.evidence_reason}"
        )
    before_or_on_start = executions[
        executions["event_time"].dt.normalize() <= start_date
    ].copy()
    if before_or_on_start.empty:
        through_start = disposition_module._result(provenance=through_end.provenance)
    else:
        start_prices = _prices_through(prices, start_date)
        through_start = build_disposition_effect_evidence(
            before_or_on_start, start_prices, init_cash=init_cash,
        )
    if not _known_count_result(through_start):
        raise PeriodBehaviorUnavailable(
            f"start-prefix disposition evidence unavailable: {through_start.evidence_reason}"
        )
    fields = (
        "realized_gains", "paper_gains", "realized_losses", "paper_losses",
        "neutral_observations", "eligible_sale_events",
    )
    counts = {field: getattr(through_end, field) - getattr(through_start, field) for field in fields}
    if any(value < 0 for value in counts.values()):
        raise PeriodBehaviorUnavailable("period disposition counts are not monotonic")
    return disposition_module._result(provenance=through_end.provenance, **counts)


def _period_loss_averaging(
    executions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    init_cash: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> LossAveragingEvidence:
    through_end = build_loss_averaging_evidence(executions, prices, init_cash=init_cash)
    if not _known_count_result(through_end):
        raise PeriodBehaviorUnavailable(
            f"loss-averaging evidence unavailable: {through_end.evidence_reason}"
        )
    events = tuple(
        item for item in through_end.events
        if start_date < item.event_time.normalize() <= end_date
    )
    return loss_module._result(events=events, provenance=through_end.provenance)


def build_period_behavior(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
    start_date: object,
    end_date: object,
) -> PeriodBehaviorSummary:
    """Summarize behavior in one exact calendar interval from a full account prefix.

    Both endpoints must be recorded daily price observations.  The adapter does
    not forward-fill them, infer a prior valuation, or read executions/prices
    after ``end_date``.  A missing or invalid fact raises instead of producing
    an apparently precise period result.
    """
    start = _calendar_date(start_date, "start_date")
    end = _calendar_date(end_date, "end_date")
    if start >= end:
        raise PeriodBehaviorUnavailable("start_date must be before end_date")
    prefix_executions, prefix_prices = _bounded_inputs(executions, market_prices, end)
    prefix_price_days = pd.to_datetime(
        prefix_prices["date"], errors="raise", format="mixed",
    ).dt.normalize()
    prefix_symbols = set(prefix_executions["symbol"].astype(str).str.strip())
    for boundary in (start, end):
        symbols_at_boundary = set(prefix_prices.loc[
            prefix_price_days == boundary, "instrument"
        ].astype(str).str.strip())
        if not prefix_symbols.issubset(symbols_at_boundary):
            raise PeriodBehaviorUnavailable(
                "exact start_date and end_date price observations are required"
            )
    try:
        context = prepare_behavior_replay(prefix_executions, prefix_prices, init_cash=init_cash)
    except (BehaviorReplayError, KeyError, TypeError, ValueError) as exc:
        raise PeriodBehaviorUnavailable(f"full account prefix is unavailable: {exc}") from exc
    if start not in context.daily_prices.index or end not in context.daily_prices.index:
        raise PeriodBehaviorUnavailable("exact start_date and end_date price observations are required")

    # Use normalized, canonically ordered rows validated by the existing replay.
    frame = context.executions
    turnover = build_turnover_intensity_evidence(frame, prefix_prices, init_cash=init_cash)
    if turnover.evidence_status != "complete":
        raise PeriodBehaviorUnavailable(f"turnover evidence unavailable: {turnover.evidence_reason}")
    daily = tuple(item for item in turnover.daily_turnover if start < item.observation_date <= end)
    if not daily:
        raise PeriodBehaviorUnavailable("no daily turnover observations exist in the requested period")
    mean_turnover = float(sum(item.turnover for item in daily) / len(daily))
    total_traded_value = float(sum(item.traded_value for item in daily))
    if not math.isfinite(mean_turnover) or not math.isfinite(total_traded_value):
        raise PeriodBehaviorUnavailable("period turnover summary is not finite")

    concentration = build_portfolio_concentration_evidence(frame, prefix_prices, init_cash=init_cash)
    if concentration.as_of_time is not None and concentration.as_of_time.normalize() != end:
        raise PeriodBehaviorUnavailable("end-date concentration was not evaluated at end_date")
    if concentration.evidence_status != "complete" and concentration.evidence_reason != (
        "No risky asset holdings are available at the observation time"
    ):
        raise PeriodBehaviorUnavailable(f"concentration evidence unavailable: {concentration.evidence_reason}")

    period_rows = frame[(frame["event_time"].dt.normalize() > start)
                        & (frame["event_time"].dt.normalize() <= end)]
    fee_total = float(period_rows["fee"].sum())
    if not math.isfinite(fee_total):
        raise PeriodBehaviorUnavailable("recorded fee total is not finite")
    disposition = _period_disposition(
        frame, prefix_prices, init_cash=init_cash, start_date=start, end_date=end,
    )
    loss_averaging = _period_loss_averaging(
        frame, prefix_prices, init_cash=init_cash, start_date=start, end_date=end,
    )
    return PeriodBehaviorSummary(
        METHOD_ID, METHOD_VERSION, start, end, len(daily), daily, mean_turnover,
        total_traded_value, fee_total, len(period_rows), concentration.hhi,
        concentration.top1_weight, concentration.top3_weight, concentration,
        disposition, loss_averaging,
    )
