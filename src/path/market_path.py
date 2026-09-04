"""Daily market-path context derived from existing Market Data Contract rows.

This module never forward-fills, interpolates, or treats same-day close as
known at a Decision time.  It does not store a second market-data catalog.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

import pandas as pd

from src.episodes.position_episode import DecisionEvent, PositionEpisode


PATH_METHOD_ID: Final = "episode_path_analysis_v1"
PATH_METHOD_VERSION: Final = "1"
PRE_DECISION_MOVE_METHOD_VERSION: Final = "1"
CONTEXT_REQUESTED_OBSERVATIONS: Final = 20
SEGMENT_PROMINENCE_FRACTION: Final = 0.12

ContextStatus = Literal["complete", "partial", "insufficient"]
QuantityAtObservationStatus = Literal["available", "ambiguous", "unavailable"]
MarketPathSegmentKind = Literal["rise", "drawdown", "recovery", "range"]


class EpisodePathError(ValueError):
    """Path facts cannot be derived without inventing market or position state."""


@dataclass(frozen=True, slots=True)
class DailyMarketObservation:
    observed_at: pd.Timestamp
    price: float
    instrument_id: str
    price_type: str | None
    data_source: str | None
    data_version: str | None


@dataclass(frozen=True, slots=True)
class PreEntryMarketContext:
    status: ContextStatus
    observations: tuple[DailyMarketObservation, ...]
    valid_observation_count: int
    requested_observation_count: int
    start_observation: DailyMarketObservation | None
    end_observation: DailyMarketObservation | None
    price_change: float | None
    price_return: float | None
    method_version: str


@dataclass(frozen=True, slots=True)
class MarketContextWindow:
    segment: Literal["pre_entry", "episode", "post_exit"]
    status: ContextStatus
    observations: tuple[DailyMarketObservation, ...]
    valid_observation_count: int
    requested_observation_count: int | None
    daily_path_max: DailyMarketObservation | None
    daily_path_min: DailyMarketObservation | None


@dataclass(frozen=True, slots=True)
class DailyPricePeakDrawdown:
    peak_observation: DailyMarketObservation
    trough_observation: DailyMarketObservation
    daily_price_peak_drawdown: float
    quantity_at_trough_status: QuantityAtObservationStatus
    quantity_at_trough: float | None
    quantity_status_reason: str | None


@dataclass(frozen=True, slots=True)
class PreDecisionMarketMove:
    decision_event_id: str
    previous_decision_event_id: str
    window_start: pd.Timestamp | None
    window_end: pd.Timestamp | None
    start_observation: DailyMarketObservation | None
    end_observation: DailyMarketObservation | None
    valid_observation_count: int
    price_change: float | None
    price_return: float | None
    highest_observation: DailyMarketObservation | None
    lowest_observation: DailyMarketObservation | None
    gap_status: Literal["preserved_as_observed", "insufficient"]
    status: ContextStatus
    method_version: str


@dataclass(frozen=True, slots=True)
class DecisionIntervalObservation:
    interval_id: str
    previous_decision_event_id: str
    next_decision_event_id: str
    move: PreDecisionMarketMove


@dataclass(frozen=True, slots=True)
class TrailingHoldObservation:
    interval_id: str
    previous_decision_event_id: str
    as_of: pd.Timestamp
    window_start: pd.Timestamp | None
    window_end: pd.Timestamp | None
    start_observation: DailyMarketObservation | None
    end_observation: DailyMarketObservation | None
    valid_observation_count: int
    price_change: float | None
    price_return: float | None
    highest_observation: DailyMarketObservation | None
    lowest_observation: DailyMarketObservation | None
    gap_status: Literal["preserved_as_observed", "insufficient"]
    status: ContextStatus


@dataclass(frozen=True, slots=True)
class MarketPathSegment:
    segment_id: str
    kind: MarketPathSegmentKind
    start_observation: DailyMarketObservation
    end_observation: DailyMarketObservation
    valid_observation_count: int
    price_change: float
    price_return: float | None


@dataclass(frozen=True, slots=True)
class EpisodeMarketPath:
    episode_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    pre_entry_context_status: ContextStatus
    episode_context_status: ContextStatus
    post_exit_context_status: ContextStatus
    pre_entry_context: PreEntryMarketContext
    episode_market_path: MarketContextWindow
    post_exit_context: MarketContextWindow
    decision_interval_moves: tuple[DecisionIntervalObservation, ...]
    trailing_hold_observation: TrailingHoldObservation | None
    market_path_segments: tuple[MarketPathSegment, ...]
    daily_price_peak_drawdown: DailyPricePeakDrawdown | None
    method_id: str
    method_version: str
    limitations: tuple[str, ...]


def context_status(count: int, *, requested: int | None) -> ContextStatus:
    """Frozen window completeness: 0–1 insufficient; 2–requested-1 partial; requested complete."""

    if count <= 1:
        return "insufficient"
    if requested is None:
        return "complete"
    if count >= requested:
        return "complete"
    return "partial"


def _calendar(value: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def instrument_observations(
    market_prices: pd.DataFrame,
    *,
    instrument_id: str,
) -> tuple[DailyMarketObservation, ...]:
    if not isinstance(market_prices, pd.DataFrame) or market_prices.empty:
        return ()
    if "date" not in market_prices.columns or "instrument" not in market_prices.columns:
        raise EpisodePathError("market_prices must include date and instrument")
    rows = market_prices.loc[market_prices["instrument"].astype(str) == instrument_id].copy()
    if rows.empty:
        return ()
    rows = rows.assign(_date=pd.to_datetime(rows["date"], errors="raise").dt.normalize())
    rows = rows.sort_values(["_date"], kind="stable")
    observations: list[DailyMarketObservation] = []
    for _, row in rows.iterrows():
        try:
            price = float(row["close"])
        except (TypeError, ValueError) as exc:
            raise EpisodePathError("market close must be numeric") from exc
        if not math.isfinite(price) or price <= 0:
            raise EpisodePathError("market close must be finite and positive")
        observations.append(
            DailyMarketObservation(
                observed_at=pd.Timestamp(row["_date"]),
                price=price,
                instrument_id=instrument_id,
                price_type=str(row["price_type"]) if "price_type" in row and pd.notna(row["price_type"]) else None,
                data_source=str(row["data_source"]) if "data_source" in row and pd.notna(row["data_source"]) else None,
                data_version=str(row["data_version"]) if "data_version" in row and pd.notna(row["data_version"]) else None,
            )
        )
    return tuple(observations)


def _select(
    observations: Sequence[DailyMarketObservation],
    *,
    start_exclusive: pd.Timestamp | None = None,
    end_exclusive: pd.Timestamp | None = None,
    start_inclusive: pd.Timestamp | None = None,
    end_inclusive: pd.Timestamp | None = None,
) -> tuple[DailyMarketObservation, ...]:
    selected: list[DailyMarketObservation] = []
    for item in observations:
        date = item.observed_at
        if start_exclusive is not None and date <= start_exclusive:
            continue
        if start_inclusive is not None and date < start_inclusive:
            continue
        if end_exclusive is not None and date >= end_exclusive:
            continue
        if end_inclusive is not None and date > end_inclusive:
            continue
        selected.append(item)
    return tuple(selected)


def _extrema(
    observations: Sequence[DailyMarketObservation],
) -> tuple[DailyMarketObservation | None, DailyMarketObservation | None]:
    if not observations:
        return None, None
    highest = max(observations, key=lambda item: (item.price, item.observed_at.isoformat()))
    lowest = min(observations, key=lambda item: (item.price, item.observed_at.isoformat()))
    return highest, lowest


def _move_stats(
    observations: Sequence[DailyMarketObservation],
) -> tuple[float | None, float | None, DailyMarketObservation | None, DailyMarketObservation | None]:
    if len(observations) < 2:
        start = observations[0] if observations else None
        return None, None, start, start
    start = observations[0]
    end = observations[-1]
    change = end.price - start.price
    return change, change / start.price, start, end


def _window(
    segment: Literal["pre_entry", "episode", "post_exit"],
    observations: Sequence[DailyMarketObservation],
    *,
    requested: int | None,
) -> MarketContextWindow:
    highest, lowest = _extrema(observations)
    return MarketContextWindow(
        segment=segment,
        status=context_status(len(observations), requested=requested),
        observations=tuple(observations),
        valid_observation_count=len(observations),
        requested_observation_count=requested,
        daily_path_max=highest,
        daily_path_min=lowest,
    )


def build_pre_entry_context(
    observations: Sequence[DailyMarketObservation],
) -> PreEntryMarketContext:
    change, ret, start, end = _move_stats(observations)
    return PreEntryMarketContext(
        status=context_status(len(observations), requested=CONTEXT_REQUESTED_OBSERVATIONS),
        observations=tuple(observations),
        valid_observation_count=len(observations),
        requested_observation_count=CONTEXT_REQUESTED_OBSERVATIONS,
        start_observation=start,
        end_observation=end,
        price_change=change,
        price_return=ret,
        method_version=PATH_METHOD_VERSION,
    )


def build_pre_decision_move(
    *,
    decision: DecisionEvent,
    previous: DecisionEvent,
    observations: Sequence[DailyMarketObservation],
) -> PreDecisionMarketMove:
    previous_date = _calendar(previous.occurred_at)
    current_date = _calendar(decision.occurred_at)
    window = _select(
        observations,
        start_exclusive=previous_date,
        end_exclusive=current_date,
    )
    change, ret, start, end = _move_stats(window)
    highest, lowest = _extrema(window)
    status = context_status(len(window), requested=None)
    if len(window) <= 1:
        status = "insufficient"
    return PreDecisionMarketMove(
        decision_event_id=decision.decision_id,
        previous_decision_event_id=previous.decision_id,
        window_start=start.observed_at if start is not None else None,
        window_end=end.observed_at if end is not None else None,
        start_observation=start,
        end_observation=end,
        valid_observation_count=len(window),
        price_change=change,
        price_return=ret,
        highest_observation=highest,
        lowest_observation=lowest,
        gap_status="preserved_as_observed" if window else "insufficient",
        status=status,
        method_version=PRE_DECISION_MOVE_METHOD_VERSION,
    )


def calendar_days_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Same formula as PositionEpisode.duration_days: normalized calendar dates."""

    return int((_calendar(end) - _calendar(start)).days)


def recovered_prior_high(observations: Sequence[DailyMarketObservation]) -> bool | None:
    drawdown = daily_price_peak_drawdown(observations)
    if drawdown is None:
        return None
    later = [
        item.price
        for item in observations
        if item.observed_at > drawdown.trough_observation.observed_at
    ]
    if not later:
        return False
    return max(later) >= drawdown.peak_observation.price


def build_market_path_segments(
    observations: Sequence[DailyMarketObservation],
    *,
    episode_id: str,
) -> tuple[MarketPathSegment, ...]:
    if len(observations) < 3:
        return ()
    prices = [item.price for item in observations]
    span = max(prices) - min(prices)
    if span <= 0:
        return ()
    prominence = SEGMENT_PROMINENCE_FRACTION * span
    anchors: list[DailyMarketObservation] = [observations[0]]
    direction = 0
    candidate = observations[0]
    for item in observations[1:]:
        if direction == 0:
            if item.price == candidate.price:
                continue
            direction = 1 if item.price > candidate.price else -1
            candidate = item
            continue
        if direction > 0:
            if item.price >= candidate.price:
                candidate = item
            elif candidate.price - item.price >= prominence:
                if candidate.observed_at != anchors[-1].observed_at:
                    anchors.append(candidate)
                direction = -1
                candidate = item
        else:
            if item.price <= candidate.price:
                candidate = item
            elif item.price - candidate.price >= prominence:
                if candidate.observed_at != anchors[-1].observed_at:
                    anchors.append(candidate)
                direction = 1
                candidate = item
    if candidate.observed_at != anchors[-1].observed_at:
        anchors.append(candidate)
    if observations[-1].observed_at != anchors[-1].observed_at:
        anchors.append(observations[-1])
    segments: list[MarketPathSegment] = []
    saw_drawdown = False
    for index, (start, end) in enumerate(zip(anchors, anchors[1:])):
        change = end.price - start.price
        ret = change / start.price if start.price else None
        count = sum(1 for item in observations if start.observed_at <= item.observed_at <= end.observed_at)
        if change < 0:
            kind: MarketPathSegmentKind = "drawdown"
            saw_drawdown = True
        elif saw_drawdown:
            kind = "recovery"
            if end.price >= max(item.price for item in anchors[: index + 1]):
                saw_drawdown = False
        elif change > 0:
            kind = "rise"
        else:
            kind = "range"
        segments.append(
            MarketPathSegment(
                segment_id=f"segment_{episode_id}_{index}_{kind}",
                kind=kind,
                start_observation=start,
                end_observation=end,
                valid_observation_count=count,
                price_change=change,
                price_return=ret,
            )
        )
    return tuple(segments)


def build_trailing_hold_observation(
    *,
    episode: PositionEpisode,
    last_decision: DecisionEvent,
    observations: Sequence[DailyMarketObservation],
    as_of: pd.Timestamp,
) -> TrailingHoldObservation | None:
    if episode.status != "open":
        return None
    window = _select(
        observations,
        start_exclusive=_calendar(last_decision.occurred_at),
        end_inclusive=_calendar(as_of),
    )
    change, ret, start, end = _move_stats(window)
    highest, lowest = _extrema(window)
    status = context_status(len(window), requested=None)
    if len(window) <= 1:
        status = "insufficient"
    return TrailingHoldObservation(
        interval_id=f"trailing_{last_decision.decision_id}",
        previous_decision_event_id=last_decision.decision_id,
        as_of=pd.Timestamp(as_of),
        window_start=start.observed_at if start is not None else None,
        window_end=end.observed_at if end is not None else None,
        start_observation=start,
        end_observation=end,
        valid_observation_count=len(window),
        price_change=change,
        price_return=ret,
        highest_observation=highest,
        lowest_observation=lowest,
        gap_status="preserved_as_observed" if window else "insufficient",
        status=status,
    )


def daily_price_peak_drawdown(
    observations: Sequence[DailyMarketObservation],
) -> DailyPricePeakDrawdown | None:
    if len(observations) < 2:
        return None
    peak = observations[0]
    trough = observations[0]
    worst = 0.0
    running_peak = observations[0]
    for item in observations:
        if item.price >= running_peak.price:
            running_peak = item
            continue
        drawdown = (item.price - running_peak.price) / running_peak.price
        if drawdown < worst:
            worst = drawdown
            peak = running_peak
            trough = item
    if worst >= 0:
        return None
    return DailyPricePeakDrawdown(
        peak_observation=peak,
        trough_observation=trough,
        daily_price_peak_drawdown=worst,
        quantity_at_trough_status="unavailable",
        quantity_at_trough=None,
        quantity_status_reason="quantity_not_attached",
    )


def build_episode_market_path(
    episode: PositionEpisode,
    decisions: Sequence[DecisionEvent],
    market_prices: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
) -> EpisodeMarketPath:
    all_obs = instrument_observations(market_prices, instrument_id=episode.instrument_id)
    opened = _calendar(episode.opened_at)
    end = _calendar(episode.closed_at if episode.closed_at is not None else as_of)
    pre = _select(all_obs, end_exclusive=opened)[-CONTEXT_REQUESTED_OBSERVATIONS:]
    holding = _select(all_obs, start_inclusive=opened, end_inclusive=end)
    post: tuple[DailyMarketObservation, ...] = ()
    if episode.status == "closed" and episode.closed_at is not None:
        post = _select(all_obs, start_exclusive=_calendar(episode.closed_at))[:CONTEXT_REQUESTED_OBSERVATIONS]
    pre_context = build_pre_entry_context(pre)
    episode_window = _window("episode", holding, requested=None)
    post_window = _window("post_exit", post, requested=CONTEXT_REQUESTED_OBSERVATIONS)
    ordered = tuple(item for item in decisions if item.episode_id == episode.episode_id)
    intervals: list[DecisionIntervalObservation] = []
    for previous, current in zip(ordered, ordered[1:]):
        move = build_pre_decision_move(
            decision=current,
            previous=previous,
            observations=all_obs,
        )
        intervals.append(
            DecisionIntervalObservation(
                interval_id=f"interval_{previous.decision_id}_{current.decision_id}",
                previous_decision_event_id=previous.decision_id,
                next_decision_event_id=current.decision_id,
                move=move,
            )
        )
    trailing = (
        build_trailing_hold_observation(
            episode=episode,
            last_decision=ordered[-1],
            observations=all_obs,
            as_of=as_of,
        )
        if ordered
        else None
    )
    return EpisodeMarketPath(
        episode_id=episode.episode_id,
        subject_id=episode.subject_id,
        account_id=episode.account_id,
        instrument_id=episode.instrument_id,
        pre_entry_context_status=pre_context.status,
        episode_context_status=episode_window.status,
        post_exit_context_status=post_window.status if episode.status == "closed" else "insufficient",
        pre_entry_context=pre_context,
        episode_market_path=episode_window,
        post_exit_context=post_window,
        decision_interval_moves=tuple(intervals),
        trailing_hold_observation=trailing,
        market_path_segments=build_market_path_segments(holding, episode_id=episode.episode_id),
        daily_price_peak_drawdown=daily_price_peak_drawdown(holding),
        method_id=PATH_METHOD_ID,
        method_version=PATH_METHOD_VERSION,
        limitations=(
            "Daily observations have no intraday available_at; same-day close is never pre-decision information.",
            "Missing pre-entry or post-exit context does not invalidate the Position Episode lifecycle.",
            "Path statistics describe the asset market-price path, not a second position PnL.",
            "Duration uses calendar days between normalized timestamps, not a trading calendar.",
            "Valid daily market observations are counted as observed rows, not trading days.",
            "Intervals without new executions are market-path facts, not user Decisions.",
            "No corporate-action, FX, short, margin, Journal, or Agent layer is applied.",
        ),
    )
