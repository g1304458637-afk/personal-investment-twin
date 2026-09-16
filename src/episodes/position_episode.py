"""Position lifecycle read models over the existing vectorbt replay.

This module only segments replayed long-only position states into product
episodes and classifies the normalized executions that connect those states.
It does not implement position accounting, average-cost, PnL, or valuation
formulas.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.behavior.replay_state import (
    BehaviorReplayContext,
    BehaviorReplayError,
    prepare_behavior_replay,
)
from src.core.portfolio_replay import (
    PortfolioReplayError,
    _validated_executions,
)
from src.evidence.adapters import adapt_price_provenance
from src.evidence.contracts import (
    DataTier,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceStatus,
    canonical_json_bytes,
)
from src.twin.state import evidence_available_at


POSITION_EPISODE_SCHEMA_VERSION: Final = "1"
REPLAY_METHOD_ID: Final = "vectorbt_portfolio_replay_v1"
POSITION_EPISODE_LIMITATIONS: Final[tuple[str, ...]] = (
    "Position Episode v1 supports only normalized long-only BUY/SELL executions.",
    "Corporate actions and transfers are unsupported and must not be encoded as executions.",
    "Open-position valuation is a replay mark at its stated valuation time, not an exit.",
)

DecisionType = Literal[
    "open_position",
    "add_position",
    "reduce_position",
    "close_position",
]
EpisodeStatus = Literal["open", "closed"]
StateBoundary = Literal["before_execution", "after_execution", "as_of_valuation"]


class PositionEpisodeError(ValueError):
    """The supplied facts cannot form a supported position lifecycle."""


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Small resolvable reference to an existing EvidenceRecord."""

    evidence_id: str
    metric_id: str
    method_id: str
    method_version: str
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    available_at: pd.Timestamp


@dataclass(frozen=True, slots=True)
class ReplayPositionState:
    """Materialized read model whose financial fields come from vectorbt."""

    state_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    as_of: pd.Timestamp
    boundary: StateBoundary
    execution_id: str | None
    quantity: float
    average_cost: float | None
    valuation_at: pd.Timestamp | None
    valuation_price: float | None
    market_value: float | None
    replay_method_id: str


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    """One actual execution classified from its replayed pre/post position state."""

    decision_id: str
    episode_id: str
    execution_id: str
    occurred_at: pd.Timestamp
    decision_type: DecisionType
    side: Literal["BUY", "SELL"]
    executed_quantity: float
    execution_price: float
    fees: float
    state_before_ref: str
    state_after_ref: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PositionEpisode:
    """One account-and-instrument lifecycle from zero holdings back to zero."""

    episode_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    opened_at: pd.Timestamp
    closed_at: pd.Timestamp | None
    status: EpisodeStatus
    opening_execution_id: str
    closing_execution_id: str | None
    execution_refs: tuple[str, ...]
    decision_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    duration_days: int
    duration_kind: Literal["so_far", "final"]
    replay_method_id: str
    calculation_code_version: str
    provenance: tuple[EvidenceProvenance, ...]
    data_tier: DataTier
    limitations: tuple[str, ...]
    vectorbt_position_record_id: int | None = None


@dataclass(frozen=True, slots=True)
class EpisodeSnapshot:
    """Reference to an Open Episode's latest legal as-of replay state."""

    episode_id: str
    as_of: pd.Timestamp
    position_state_ref: str


@dataclass(frozen=True, slots=True)
class PositionEpisodeLifecycle:
    """Deterministic, ordered lifecycle view for one or more separate accounts."""

    subject_id: str
    as_of: pd.Timestamp
    episodes: tuple[PositionEpisode, ...]
    decisions: tuple[DecisionEvent, ...]
    states: tuple[ReplayPositionState, ...]
    snapshots: tuple[EpisodeSnapshot, ...]
    evidence_references: tuple[EvidenceReference, ...]
    data_tier: DataTier
    limitations: tuple[str, ...]


@dataclass
class _EpisodeDraft:
    episode_id: str
    subject_id: str
    account_id: str
    instrument_id: str
    opened_at: pd.Timestamp
    opening_execution_id: str
    opening_ordinal: int
    execution_refs: list[str]
    decision_refs: list[str]
    closed_at: pd.Timestamp | None = None
    closing_execution_id: str | None = None


def _required_text(value: object, field_name: str) -> str:
    if pd.isna(value) or not isinstance(value, str) or not value.strip():
        raise PositionEpisodeError(f"{field_name} must be a non-empty string")
    return value.strip()


def _required_timestamp(value: object, field_name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise PositionEpisodeError(f"{field_name} must be a timestamp") from exc
    if pd.isna(timestamp):
        raise PositionEpisodeError(f"{field_name} cannot be NaT")
    return timestamp


def _stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"{prefix}_{digest}"


def _account_cash(init_cash: float | Mapping[str, float], account_id: str) -> float:
    raw = init_cash.get(account_id) if isinstance(init_cash, Mapping) else init_cash
    if raw is None:
        raise PositionEpisodeError(f"Missing init_cash for account {account_id}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise PositionEpisodeError("init_cash must be numeric") from exc
    if not math.isfinite(value) or value <= 0:
        raise PositionEpisodeError("init_cash must be finite and positive")
    return value


def _account_frames(
    executions: pd.DataFrame,
    *,
    account_id: str | None,
    as_of: pd.Timestamp,
) -> tuple[tuple[str, pd.DataFrame], ...]:
    if not isinstance(executions, pd.DataFrame) or executions.empty:
        raise PositionEpisodeError("At least one execution is required")

    rows = executions.copy(deep=True)
    rows["_source_ordinal"] = np.arange(len(rows), dtype=int)
    try:
        times = pd.to_datetime(rows["event_time"], errors="raise")
    except (KeyError, TypeError, ValueError) as exc:
        raise PositionEpisodeError(
            "executions.event_time must contain timestamps"
        ) from exc
    if times.dt.tz is not None:
        # The replay axes are timezone-naive UTC instants; align tz-aware
        # source facts to them so mixed naive/aware comparisons fail closed
        # here instead of raising bare TypeErrors at filter time.
        times = times.dt.tz_convert("UTC").dt.tz_localize(None)
    if times.isna().any():
        raise PositionEpisodeError("executions.event_time cannot contain NaT")
    rows["event_time"] = times
    rows = rows.loc[times <= as_of].copy()
    if rows.empty:
        raise PositionEpisodeError("No executions are available at or before as_of")

    if "event_type" in rows.columns:
        normalized_types = rows["event_type"].map(
            lambda value: "" if pd.isna(value) else str(value).strip().lower()
        )
        if not normalized_types.eq("execution").all():
            raise PositionEpisodeError(
                "Corporate actions, transfers, and non-execution events are unsupported"
            )

    if account_id is not None:
        normalized_account = _required_text(account_id, "account_id")
        if "account_id" in rows.columns:
            actual = rows["account_id"].map(
                lambda value: _required_text(value, "account_id")
            )
            if not actual.eq(normalized_account).all():
                raise PositionEpisodeError(
                    "Explicit account_id does not match every execution row"
                )
        rows["account_id"] = normalized_account
    elif "account_id" not in rows.columns:
        raise PositionEpisodeError(
            "account_id is required because Position Episode v1 never consolidates accounts"
        )
    else:
        rows["account_id"] = rows["account_id"].map(
            lambda value: _required_text(value, "account_id")
        )

    grouped: list[tuple[str, pd.DataFrame]] = []
    for current_account in sorted(rows["account_id"].unique()):
        account_rows = rows[rows["account_id"] == current_account].copy()
        for index in account_rows.index:
            account_rows.at[index, "execution_id"] = _required_text(
                account_rows.at[index, "execution_id"],
                "execution_id",
            )
        grouped.append((str(current_account), account_rows))
    return tuple(grouped)


def _window_prices(market_prices: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if not isinstance(market_prices, pd.DataFrame) or "date" not in market_prices:
        raise PositionEpisodeError("market_prices.date is required")
    try:
        dates = pd.to_datetime(market_prices["date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise PositionEpisodeError("market_prices.date must contain timestamps") from exc
    timezone_aware = dates.dt.tz is not None
    if timezone_aware:
        # The contract's price ``date`` is a calendar date, so a tz-aware
        # observation keeps its stated wall-clock calendar date (naive) instead
        # of being shifted by a UTC conversion; this stays comparable with the
        # naive replay axes.
        dates = dates.dt.tz_localize(None)
    if dates.isna().any():
        raise PositionEpisodeError("market_prices.date cannot contain NaT")
    # The current Market Data Contract is daily.  Keep only observations whose
    # stated calendar date is at or before the requested as-of date; never fill.
    selected = market_prices.loc[dates.dt.normalize() <= as_of.normalize()].copy()
    if selected.empty:
        raise PositionEpisodeError("No market prices are available at or before as_of")
    if timezone_aware:
        # Hand the replay a naive date column so panel assembly never mixes
        # tz-aware and tz-naive axes.
        selected["date"] = dates.loc[selected.index]
    return selected


def _validated_account_executions(
    rows: pd.DataFrame,
) -> pd.DataFrame:
    ordinal_by_execution = {
        str(row["execution_id"]): int(row["_source_ordinal"])
        for _, row in rows.iterrows()
    }
    try:
        frame = _validated_executions(rows)
    except (KeyError, PortfolioReplayError) as exc:
        raise PositionEpisodeError(str(exc)) from exc
    if "execution_sequence" in frame.columns:
        # v2 order is a contract fact and must not inherit physical input order.
        frame["_source_ordinal"] = np.arange(len(frame), dtype=int)
    else:
        frame["_source_ordinal"] = frame["execution_id"].map(ordinal_by_execution)
    return frame.reset_index(drop=True)


_FOLD_CACHE: "OrderedDict[int, tuple[BehaviorReplayContext, dict[str, object]]]" = OrderedDict()
_FOLD_CACHE_MAX_CONTEXTS = 8
_FOLD_SNAPSHOTS_KEPT = 4


def clear_fold_cache() -> None:
    """Drops cached fold state (each entry pins a full replay context)."""
    _FOLD_CACHE.clear()


def _fold_positions(context: BehaviorReplayContext, frame: pd.DataFrame, prefix_count: int) -> dict[str, tuple[float, float | None]]:
    """Position fold after the first ``prefix_count`` fills.

    Applies vectorbt's own position semantics (update_pos_record_nb):
    opening sets average cost to the price, adds blend it by size, sells
    leave it untouched, and a full exit resets it.  Each step is the same
    float operation in the same order as the engine, so the fold state is
    bit-identical to a full prefix replay — one O(n) pass instead of O(n²)
    total.  The context is the natural cache unit: it is immutable per
    lifecycle build and held strongly while cached.
    """
    key = id(context)
    entry = _FOLD_CACHE.get(key)
    if entry is None or entry[0] is not context:
        entry = (context, {"max": 0, "positions": {}, "snapshots": OrderedDict()})
        _FOLD_CACHE[key] = entry
        while len(_FOLD_CACHE) > _FOLD_CACHE_MAX_CONTEXTS:
            _FOLD_CACHE.popitem(last=False)
    cache = entry[1]
    snapshots: OrderedDict = cache["snapshots"]
    if prefix_count in snapshots:
        return snapshots[prefix_count]
    if prefix_count < cache["max"]:
        cache["max"] = 0
        cache["positions"] = {}
        snapshots.clear()
    # Average cost mirrors get_exit_trades_nb exactly: the open trade's
    # Avg Entry Price is (entry_gross_sum / entry_size_sum) where buys append
    # size*price and PARTIAL SELLS rescale both sums by the remaining
    # fraction ((entry_size_sum - sold) / entry_size_sum) — a sequential
    # blend would differ in the last ulp, and so would skipping the rescale.
    positions: dict[str, tuple[float, float, float]] = cache["positions"]
    for i in range(cache["max"], prefix_count):
        row = frame.iloc[i]
        symbol = str(row["symbol"])
        size = float(row["executed_quantity"])
        price = float(row["executed_price"])
        quantity, entry_size_sum, entry_gross_sum = positions.get(symbol, (0.0, 0.0, 0.0))
        if str(row["side"]) == "BUY":
            positions[symbol] = (quantity + size, entry_size_sum + size, entry_gross_sum + size * price)
        else:
            remaining = quantity - size
            if remaining <= 1e-12:
                positions[symbol] = (0.0, 0.0, 0.0)
            else:
                fraction = (entry_size_sum - size) / entry_size_sum
                positions[symbol] = (remaining, entry_size_sum * fraction, entry_gross_sum * fraction)
    cache["max"] = prefix_count
    snapshot = dict(positions)
    snapshots[prefix_count] = snapshot
    while len(snapshots) > _FOLD_SNAPSHOTS_KEPT:
        snapshots.popitem(last=False)
    return snapshot


def _state_from_replay(
    context: BehaviorReplayContext,
    frame: pd.DataFrame,
    *,
    prefix_count: int,
    subject_id: str,
    account_id: str,
    instrument_id: str,
    as_of: pd.Timestamp,
    boundary: StateBoundary,
    execution_id: str | None,
) -> ReplayPositionState:
    state_id = _stable_id(
        "ps",
        {
            "schema_version": POSITION_EPISODE_SCHEMA_VERSION,
            "subject_id": subject_id,
            "account_id": account_id,
            "instrument_id": instrument_id,
            "as_of": as_of.isoformat(),
            "boundary": boundary,
            "execution_id": execution_id,
        },
    )
    if prefix_count == 0:
        return ReplayPositionState(
            state_id=state_id,
            subject_id=subject_id,
            account_id=account_id,
            instrument_id=instrument_id,
            as_of=as_of,
            boundary=boundary,
            execution_id=execution_id,
            quantity=0.0,
            average_cost=None,
            valuation_at=None,
            valuation_price=None,
            market_value=None,
            replay_method_id=REPLAY_METHOD_ID,
        )

    # O(n) fold instead of a full vectorbt prefix replay per call: the fold
    # applies the engine's own position formulas in the engine's order, so
    # quantity/average_cost are bit-identical (verified against golden
    # lifecycle builds).  Valuation still reads the validated panel verbatim.
    valuation_prices = context.valuation_prices.loc[:as_of]
    if valuation_prices.empty:
        raise PositionEpisodeError("No replay valuation is available at state as_of")
    positions = _fold_positions(context, frame, prefix_count)
    valuation_at = pd.Timestamp(valuation_prices.index[-1])
    if instrument_id not in positions or instrument_id not in valuation_prices.columns:
        quantity = 0.0
        average_cost = None
        valuation_price = None
        market_value = None
    else:
        quantity, entry_size_sum, entry_gross_sum = positions[instrument_id]
        valuation_price = float(valuation_prices[instrument_id].iloc[-1])
        market_value = quantity * valuation_price
        if quantity <= 1e-12:
            quantity = 0.0
            average_cost = None
        else:
            average_cost = entry_gross_sum / entry_size_sum

    numeric = [quantity]
    numeric.extend(
        value
        for value in (average_cost, valuation_price, market_value)
        if value is not None
    )
    if not np.isfinite(np.asarray(numeric, dtype=float)).all() or quantity < -1e-9:
        raise PositionEpisodeError("Short or invalid replay position state is unsupported")
    if average_cost is not None and average_cost <= 0:
        raise PositionEpisodeError("vectorbt average cost must be positive")
    if valuation_price is not None and valuation_price <= 0:
        raise PositionEpisodeError("vectorbt valuation price must be positive")

    return ReplayPositionState(
        state_id=state_id,
        subject_id=subject_id,
        account_id=account_id,
        instrument_id=instrument_id,
        as_of=as_of,
        boundary=boundary,
        execution_id=execution_id,
        quantity=quantity,
        average_cost=average_cost,
        valuation_at=valuation_at,
        valuation_price=valuation_price,
        market_value=market_value,
        replay_method_id=REPLAY_METHOD_ID,
    )


def _decision_type(side: str, before: float, after: float) -> DecisionType:
    before_zero = math.isclose(before, 0.0, rel_tol=0.0, abs_tol=1e-9)
    after_zero = math.isclose(after, 0.0, rel_tol=0.0, abs_tol=1e-9)
    if side == "BUY" and before_zero and after > 0:
        return "open_position"
    if side == "BUY" and before > 0 and after > before:
        return "add_position"
    if side == "SELL" and before > 0 and after_zero:
        return "close_position"
    if side == "SELL" and before > 0 and 0 < after < before:
        return "reduce_position"
    raise PositionEpisodeError(
        f"Unsupported {side} state transition for long-only lifecycle: {before} -> {after}"
    )


def _eligible_references(
    records: Sequence[EvidenceRecord],
    *,
    as_of: pd.Timestamp,
    registry: dict[str, EvidenceReference],
) -> tuple[str, ...]:
    ids: list[str] = []
    for record in records:
        available_at = evidence_available_at(record)
        if available_at is None or available_at > as_of:
            continue
        registry[record.evidence_id] = EvidenceReference(
            evidence_id=record.evidence_id,
            metric_id=record.metric_id,
            method_id=record.method_id,
            method_version=record.method_version,
            evidence_status=record.evidence_status,
            evidence_reason=record.evidence_reason,
            available_at=available_at,
        )
        ids.append(record.evidence_id)
    return tuple(sorted(dict.fromkeys(ids)))


def _mapped_records(
    mapping: Mapping[str, Sequence[EvidenceRecord]] | None,
    *keys: str,
) -> tuple[EvidenceRecord, ...]:
    if mapping is None:
        return ()
    records: list[EvidenceRecord] = []
    for key in keys:
        records.extend(mapping.get(key, ()))
    return tuple(records)


def _final_episode(
    draft: _EpisodeDraft,
    *,
    as_of: pd.Timestamp,
    provenance: tuple[EvidenceProvenance, ...],
    data_tier: DataTier,
    calculation_code_version: str,
    evidence_refs: tuple[str, ...],
    vectorbt_position_record_id: int,
) -> PositionEpisode:
    status: EpisodeStatus = "closed" if draft.closed_at is not None else "open"
    duration_end = draft.closed_at if draft.closed_at is not None else as_of
    duration_days = int((duration_end.normalize() - draft.opened_at.normalize()).days)
    return PositionEpisode(
        episode_id=draft.episode_id,
        subject_id=draft.subject_id,
        account_id=draft.account_id,
        instrument_id=draft.instrument_id,
        opened_at=draft.opened_at,
        closed_at=draft.closed_at,
        status=status,
        opening_execution_id=draft.opening_execution_id,
        closing_execution_id=draft.closing_execution_id,
        execution_refs=tuple(draft.execution_refs),
        decision_refs=tuple(draft.decision_refs),
        evidence_refs=evidence_refs,
        duration_days=duration_days,
        duration_kind="final" if status == "closed" else "so_far",
        replay_method_id=REPLAY_METHOD_ID,
        calculation_code_version=calculation_code_version,
        provenance=provenance,
        data_tier=data_tier,
        limitations=POSITION_EPISODE_LIMITATIONS,
        vectorbt_position_record_id=vectorbt_position_record_id,
    )


def build_position_episode_lifecycle(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    subject_id: str,
    as_of: pd.Timestamp,
    init_cash: float | Mapping[str, float],
    data_tier: DataTier,
    calculation_code_version: str,
    account_id: str | None = None,
    decision_evidence: Mapping[str, Sequence[EvidenceRecord]] | None = None,
    episode_evidence: Mapping[str, Sequence[EvidenceRecord]] | None = None,
) -> PositionEpisodeLifecycle:
    """Build ordered Episode/Decision refs solely from vectorbt replayed states.

    If ``executions`` contains multiple accounts, each is replayed independently.
    If it has no ``account_id`` column, callers must provide the one account ID.
    Evidence linkage is explicit by execution ID or opening execution/Episode ID;
    this module never infers evidence from a timestamp or trade side.
    """

    normalized_subject = _required_text(subject_id, "subject_id")
    normalized_version = _required_text(
        calculation_code_version,
        "calculation_code_version",
    )
    normalized_as_of = _required_timestamp(as_of, "as_of")
    if normalized_as_of.tzinfo is not None:
        # The replay axes are timezone-naive UTC instants; keep a tz-aware
        # as_of comparable with them instead of raising bare TypeErrors.
        normalized_as_of = normalized_as_of.tz_convert("UTC").tz_localize(None)
    if data_tier not in {"synthetic", "demo", "authorized_beta", "production"}:
        raise PositionEpisodeError("data_tier is unsupported")
    window_prices = _window_prices(market_prices, normalized_as_of)

    episode_items: list[tuple[int, PositionEpisode]] = []
    decision_items: list[tuple[int, DecisionEvent]] = []
    states: list[ReplayPositionState] = []
    snapshots: list[EpisodeSnapshot] = []
    reference_registry: dict[str, EvidenceReference] = {}

    for current_account, account_rows in _account_frames(
        executions,
        account_id=account_id,
        as_of=normalized_as_of,
    ):
        frame = _validated_account_executions(account_rows)
        cash = _account_cash(init_cash, current_account)
        try:
            context = prepare_behavior_replay(frame, window_prices, init_cash=cash)
        except BehaviorReplayError as exc:
            raise PositionEpisodeError(str(exc)) from exc
        provenance = tuple(adapt_price_provenance(item) for item in context.provenance)

        drafts: list[_EpisodeDraft] = []
        active_by_symbol: dict[str, _EpisodeDraft] = {}
        for index, row in frame.iterrows():
            event_time = pd.Timestamp(row["event_time"])
            instrument_id = str(row["symbol"])
            execution_id = str(row["execution_id"])
            ordinal = int(row["_source_ordinal"])
            before = _state_from_replay(
                context,
                frame,
                prefix_count=index,
                subject_id=normalized_subject,
                account_id=current_account,
                instrument_id=instrument_id,
                as_of=event_time,
                boundary="before_execution",
                execution_id=execution_id,
            )
            after = _state_from_replay(
                context,
                frame,
                prefix_count=index + 1,
                subject_id=normalized_subject,
                account_id=current_account,
                instrument_id=instrument_id,
                as_of=event_time,
                boundary="after_execution",
                execution_id=execution_id,
            )
            states.extend((before, after))
            decision_type = _decision_type(str(row["side"]), before.quantity, after.quantity)

            if decision_type == "open_position":
                if instrument_id in active_by_symbol:
                    raise PositionEpisodeError("Cannot open a second active Episode")
                episode_id = _stable_id(
                    "pe",
                    {
                        "schema_version": POSITION_EPISODE_SCHEMA_VERSION,
                        "account_id": current_account,
                        "instrument_id": instrument_id,
                        "opening_execution_id": execution_id,
                    },
                )
                draft = _EpisodeDraft(
                    episode_id=episode_id,
                    subject_id=normalized_subject,
                    account_id=current_account,
                    instrument_id=instrument_id,
                    opened_at=event_time,
                    opening_execution_id=execution_id,
                    opening_ordinal=ordinal,
                    execution_refs=[],
                    decision_refs=[],
                )
                drafts.append(draft)
                active_by_symbol[instrument_id] = draft
            else:
                draft = active_by_symbol.get(instrument_id)
                if draft is None:
                    raise PositionEpisodeError("Execution has no active Position Episode")

            decision_id = _stable_id(
                "de",
                {
                    "schema_version": POSITION_EPISODE_SCHEMA_VERSION,
                    "episode_id": draft.episode_id,
                    "execution_id": execution_id,
                    "decision_type": decision_type,
                },
            )
            evidence_refs = _eligible_references(
                _mapped_records(decision_evidence, execution_id),
                as_of=normalized_as_of,
                registry=reference_registry,
            )
            decision = DecisionEvent(
                decision_id=decision_id,
                episode_id=draft.episode_id,
                execution_id=execution_id,
                occurred_at=event_time,
                decision_type=decision_type,
                side=str(row["side"]),  # type: ignore[arg-type]
                executed_quantity=float(row["executed_quantity"]),
                execution_price=float(row["executed_price"]),
                fees=float(row["fee"]),
                state_before_ref=before.state_id,
                state_after_ref=after.state_id,
                evidence_refs=evidence_refs,
            )
            decision_items.append((ordinal, decision))
            draft.execution_refs.append(execution_id)
            draft.decision_refs.append(decision_id)
            if decision_type == "close_position":
                draft.closed_at = event_time
                draft.closing_execution_id = execution_id
                del active_by_symbol[instrument_id]

        for instrument_id, draft in sorted(active_by_symbol.items()):
            current_state = _state_from_replay(
                context,
                frame,
                prefix_count=len(frame),
                subject_id=normalized_subject,
                account_id=current_account,
                instrument_id=instrument_id,
                as_of=normalized_as_of,
                boundary="as_of_valuation",
                execution_id=None,
            )
            if current_state.quantity <= 0:
                raise PositionEpisodeError("Open Episode has no positive as-of position")
            states.append(current_state)
            snapshots.append(
                EpisodeSnapshot(
                    episode_id=draft.episode_id,
                    as_of=normalized_as_of,
                    position_state_ref=current_state.state_id,
                )
            )

        for draft in drafts:
            episode_id_records = _mapped_records(
                episode_evidence,
                draft.opening_execution_id,
                draft.episode_id,
            )
            evidence_refs = _eligible_references(
                episode_id_records,
                as_of=normalized_as_of,
                registry=reference_registry,
            )
            if draft.closing_execution_id is not None:
                closing_links = [
                    item
                    for item in context.execution_links
                    if item.execution_id == draft.closing_execution_id
                ]
                if (
                    len(closing_links) != 1
                    or closing_links[0].vectorbt_position_record_id is None
                ):
                    raise PositionEpisodeError(
                        f"Closed Episode {draft.episode_id} has no verified vectorbt Position link"
                    )
                position_record_id = int(
                    closing_links[0].vectorbt_position_record_id
                )
            else:
                open_records = context.portfolio.positions.open.records_readable
                matched = open_records[
                    open_records["Column"].astype(str) == draft.instrument_id
                ]
                if len(matched) != 1:
                    raise PositionEpisodeError(
                        f"Open Episode {draft.episode_id} has no unique vectorbt Position link"
                    )
                position_record_id = int(matched.iloc[0]["Position Id"])
            episode_items.append(
                (
                    draft.opening_ordinal,
                    _final_episode(
                        draft,
                        as_of=normalized_as_of,
                        provenance=provenance,
                        data_tier=data_tier,
                        calculation_code_version=normalized_version,
                        evidence_refs=evidence_refs,
                        vectorbt_position_record_id=position_record_id,
                    ),
                )
            )

    episode_items.sort(key=lambda item: (item[0], item[1].account_id, item[1].episode_id))
    decision_items.sort(key=lambda item: (item[0], item[1].decision_id))
    states.sort(key=lambda state: (state.as_of, state.account_id, state.state_id))
    snapshots.sort(key=lambda snapshot: (snapshot.as_of, snapshot.episode_id))
    return PositionEpisodeLifecycle(
        subject_id=normalized_subject,
        as_of=normalized_as_of,
        episodes=tuple(item[1] for item in episode_items),
        decisions=tuple(item[1] for item in decision_items),
        states=tuple(states),
        snapshots=tuple(snapshots),
        evidence_references=tuple(
            reference_registry[key] for key in sorted(reference_registry)
        ),
        data_tier=data_tier,
        limitations=POSITION_EPISODE_LIMITATIONS,
    )
