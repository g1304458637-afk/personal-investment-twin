"""Canonical execution facts and replay eligibility for contract v2.

The objects in this module describe broker facts.  They do not calculate any
portfolio state.  A canonical fact may be valid even when the current exact,
net vectorbt replay cannot consume it (for example, when fees are unknown).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Integral
from typing import Final, Literal, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


CANONICAL_EXECUTION_SCHEMA_VERSION: Final = "2"

TimePrecision = Literal["date", "minute", "second", "millisecond", "microsecond"]
FeeStatus = Literal["known_nonzero", "explicit_zero", "unknown"]
ReplayBlockReason = Literal[
    "blocked_unknown_fee",
    "blocked_ambiguous_order",
    "blocked_unresolved_instrument",
    "blocked_unsupported_direction",
]


class CanonicalExecutionError(ValueError):
    """A source fact cannot be represented without inventing information."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalExecutionError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip()
    return normalized or None


def _canonical_hash(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Qualified listing identity plus non-identifying display metadata.

    Currency is listing metadata rather than an identity component: a currency
    correction must not silently create a different security.  Corporate-action
    and symbol-history identity remain outside v2.
    """

    instrument_id: str | None
    local_symbol: str
    market: str | None
    security_type: str | None
    currency: str | None = None
    display_symbol: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        _text(self.local_symbol, "local_symbol")
        if self.instrument_id is not None:
            _text(self.instrument_id, "instrument_id")
            if self.market is None or self.security_type is None:
                raise CanonicalExecutionError(
                    "resolved instrument requires market and security_type"
                )
            expected = _canonical_hash(
                "inst_v2",
                {
                    "local_symbol": self.local_symbol,
                    "market": self.market,
                    "security_type": self.security_type,
                },
            )
            if self.instrument_id != expected:
                raise CanonicalExecutionError(
                    "instrument_id does not match the qualified instrument key"
                )


def instrument_ref(
    *,
    local_symbol: str,
    market: str | None,
    security_type: str | None,
    currency: str | None = None,
    display_symbol: str | None = None,
    display_name: str | None = None,
) -> InstrumentRef:
    """Build an opaque identity when the minimum qualified key is known."""

    symbol = _text(local_symbol, "local_symbol").upper()
    normalized_market = _optional_text(market)
    normalized_type = _optional_text(security_type)
    if normalized_market is not None:
        normalized_market = normalized_market.upper()
    if normalized_type is not None:
        normalized_type = normalized_type.lower()
    identifier = None
    if normalized_market is not None and normalized_type is not None:
        identifier = _canonical_hash(
            "inst_v2",
            {
                "local_symbol": symbol,
                "market": normalized_market,
                "security_type": normalized_type,
            },
        )
    return InstrumentRef(
        instrument_id=identifier,
        local_symbol=symbol,
        market=normalized_market,
        security_type=normalized_type,
        currency=_optional_text(currency),
        display_symbol=_optional_text(display_symbol) or symbol,
        display_name=_optional_text(display_name),
    )


def legacy_demo_instrument(symbol: str) -> InstrumentRef:
    """Qualify an existing demo symbol without claiming a real-world venue."""

    return instrument_ref(
        local_symbol=symbol,
        market="LEGACY_DEMO",
        security_type="synthetic_listing",
        display_symbol=symbol,
    )


@dataclass(frozen=True, slots=True)
class ExecutionTime:
    """Source time without conflating a calendar date with an instant.

    ``instant_utc`` is absent for date-only facts.  ``replay_key`` is merely the
    deterministic daily-axis key needed by vectorbt and is not an asserted
    midnight execution time.
    """

    source_value: str
    precision: TimePrecision
    source_timezone: str | None
    instant_utc: pd.Timestamp | None
    calendar_date: date

    def __post_init__(self) -> None:
        if self.precision not in {
            "date",
            "minute",
            "second",
            "millisecond",
            "microsecond",
        }:
            raise CanonicalExecutionError("time precision is unsupported")
        if self.precision == "date" and self.instant_utc is not None:
            raise CanonicalExecutionError("date precision cannot assert an instant")
        if self.precision != "date" and self.instant_utc is None:
            raise CanonicalExecutionError("timed precision requires a UTC instant")
        if self.instant_utc is not None and (
            self.instant_utc.tzinfo is None
            or str(self.instant_utc.tzinfo).upper() != "UTC"
        ):
            raise CanonicalExecutionError("instant_utc must be timezone-aware UTC")

    @property
    def replay_key(self) -> pd.Timestamp:
        if self.instant_utc is not None:
            return self.instant_utc
        return pd.Timestamp(self.calendar_date)

    @property
    def ordering_key(self) -> str:
        if self.instant_utc is not None:
            return self.instant_utc.isoformat()
        return f"date:{self.calendar_date.isoformat()}"


def execution_time(
    value: str | date | datetime | pd.Timestamp,
    *,
    precision: TimePrecision,
    source_timezone: str | None = None,
) -> ExecutionTime:
    """Normalize timed facts to UTC and fail closed on DST ambiguity.

    An offset carried by the source value wins over ``source_timezone``.  A
    naive timed value requires an explicit IANA timezone.
    """

    if precision not in {"date", "minute", "second", "millisecond", "microsecond"}:
        raise CanonicalExecutionError("time precision is unsupported")

    if precision == "date":
        if isinstance(value, datetime) or (
            isinstance(value, pd.Timestamp) and not pd.isna(value)
        ):
            parsed = pd.Timestamp(value)
            if parsed.time() != datetime.min.time():
                raise CanonicalExecutionError("date precision cannot contain a clock time")
            calendar = parsed.date()
        else:
            raw = str(value).strip()
            try:
                parsed = pd.Timestamp(raw)
            except (TypeError, ValueError) as exc:
                raise CanonicalExecutionError("event date is invalid") from exc
            if pd.isna(parsed) or parsed.time() != datetime.min.time():
                raise CanonicalExecutionError("date precision requires a calendar date only")
            calendar = parsed.date()
        return ExecutionTime(
            source_value=str(value),
            precision="date",
            source_timezone=None,
            instant_utc=None,
            calendar_date=calendar,
        )

    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalExecutionError("event time is invalid") from exc
    if pd.isna(timestamp):
        raise CanonicalExecutionError("event time cannot be NaT")
    if precision == "minute" and (
        timestamp.second != 0 or timestamp.microsecond != 0 or timestamp.nanosecond != 0
    ):
        raise CanonicalExecutionError("event time contains finer precision than minute")
    if precision == "second" and (
        timestamp.microsecond != 0 or timestamp.nanosecond != 0
    ):
        raise CanonicalExecutionError("event time contains finer precision than second")
    if precision == "millisecond" and (
        timestamp.microsecond % 1_000 != 0 or timestamp.nanosecond != 0
    ):
        raise CanonicalExecutionError("event time contains finer precision than millisecond")
    if precision == "microsecond" and timestamp.nanosecond != 0:
        raise CanonicalExecutionError("event time contains finer precision than microsecond")
    normalized_timezone: str | None
    if timestamp.tzinfo is not None:
        normalized_timezone = str(timestamp.tzinfo)
        instant = timestamp.tz_convert("UTC")
    else:
        normalized_timezone = _optional_text(source_timezone)
        if normalized_timezone is None:
            raise CanonicalExecutionError(
                "naive timed event requires an explicit IANA source_timezone"
            )
        try:
            ZoneInfo(normalized_timezone)
        except ZoneInfoNotFoundError as exc:
            raise CanonicalExecutionError("source_timezone must be a valid IANA timezone") from exc
        try:
            instant = timestamp.tz_localize(
                normalized_timezone,
                ambiguous="raise",
                nonexistent="raise",
            ).tz_convert("UTC")
        except (TypeError, ValueError) as exc:
            raise CanonicalExecutionError(
                "local event time is ambiguous or nonexistent; provide an explicit offset"
            ) from exc
    return ExecutionTime(
        source_value=str(value),
        precision=precision,
        source_timezone=normalized_timezone,
        instant_utc=instant,
        calendar_date=timestamp.date(),
    )


@dataclass(frozen=True, slots=True)
class FeeFact:
    status: FeeStatus
    amount: float | None
    currency: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"known_nonzero", "explicit_zero", "unknown"}:
            raise CanonicalExecutionError("fee status is unsupported")
        if self.status == "unknown":
            if self.amount is not None:
                raise CanonicalExecutionError("unknown fee cannot have an amount")
            return
        if self.amount is None or not math.isfinite(self.amount) or self.amount < 0:
            raise CanonicalExecutionError("known fee must be finite and non-negative")
        if self.status == "explicit_zero" and self.amount != 0:
            raise CanonicalExecutionError("explicit_zero fee must have amount zero")
        if self.status == "known_nonzero" and self.amount <= 0:
            raise CanonicalExecutionError("known_nonzero fee must be positive")


def fee_fact(amount: object | None, *, currency: str | None = None) -> FeeFact:
    """Keep explicit zero separate from unknown fee availability."""

    if amount is None or pd.isna(amount):
        return FeeFact("unknown", None, _optional_text(currency))
    try:
        value = float(amount)
    except (TypeError, ValueError) as exc:
        raise CanonicalExecutionError("fee amount must be numeric or unknown") from exc
    if not math.isfinite(value) or value < 0:
        raise CanonicalExecutionError("known fee amount must be finite and non-negative")
    return FeeFact(
        "explicit_zero" if value == 0 else "known_nonzero",
        value,
        _optional_text(currency),
    )


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    source: str
    source_record_ref: str
    sequence_source: str | None

    def __post_init__(self) -> None:
        _text(self.source, "source")
        _text(self.source_record_ref, "source_record_ref")


@dataclass(frozen=True, slots=True)
class CanonicalExecutionV2:
    """One independent fill fact; identity and replay ordering are separate."""

    subject_id: str
    account_id: str
    execution_id: str
    source_execution_id: str | None
    source_order_id: str | None
    instrument: InstrumentRef
    event_time: ExecutionTime
    execution_sequence: int | None
    side: str
    executed_quantity: float
    executed_price: float
    fee: FeeFact
    provenance: ExecutionProvenance
    schema_version: str = CANONICAL_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CANONICAL_EXECUTION_SCHEMA_VERSION:
            raise CanonicalExecutionError("CanonicalExecutionV2 schema_version must be 2")
        for value, field in (
            (self.subject_id, "subject_id"),
            (self.account_id, "account_id"),
            (self.execution_id, "execution_id"),
            (self.side, "side"),
        ):
            _text(value, field)
        if not math.isfinite(self.executed_quantity) or self.executed_quantity <= 0:
            raise CanonicalExecutionError("executed_quantity must be finite and positive")
        if not math.isfinite(self.executed_price) or self.executed_price <= 0:
            raise CanonicalExecutionError("executed_price must be finite and positive")
        if self.execution_sequence is not None and (
            isinstance(self.execution_sequence, bool)
            or not isinstance(self.execution_sequence, Integral)
            or self.execution_sequence < 0
        ):
            raise CanonicalExecutionError(
                "execution_sequence must be a non-negative integer"
            )
        if (
            self.execution_sequence is not None
            and self.provenance.sequence_source is None
        ):
            raise CanonicalExecutionError(
                "sequence_source is required when execution_sequence is supplied"
            )

    def result_payload(self) -> dict[str, object]:
        """Deterministic serialization of identity and result-affecting facts."""

        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "account_id": self.account_id,
            "execution_id": self.execution_id,
            "source_execution_id": self.source_execution_id,
            "source_order_id": self.source_order_id,
            "instrument_id": self.instrument.instrument_id,
            "event_time": self.event_time.ordering_key,
            "time_precision": self.event_time.precision,
            "execution_sequence": self.execution_sequence,
            "side": self.side,
            "executed_quantity": self.executed_quantity,
            "executed_price": self.executed_price,
            "fee_status": self.fee.status,
            "fee_amount": self.fee.amount,
            "source": self.provenance.source,
            "source_record_ref": self.provenance.source_record_ref,
            "sequence_source": self.provenance.sequence_source,
        }


def canonical_execution(
    *,
    subject_id: str,
    account_id: str,
    instrument: InstrumentRef,
    event_time: ExecutionTime,
    side: str,
    executed_quantity: object,
    executed_price: object,
    fee: FeeFact,
    source: str,
    source_record_ref: str,
    execution_sequence: int | None = None,
    sequence_source: str | None = None,
    execution_id: str | None = None,
    source_execution_id: str | None = None,
    source_order_id: str | None = None,
) -> CanonicalExecutionV2:
    """Validate one fill and assign an opaque ID when the caller has none."""

    subject = _text(subject_id, "subject_id")
    account = _text(account_id, "account_id")
    normalized_source = _text(source, "source")
    record_ref = _text(source_record_ref, "source_record_ref")
    normalized_side = _text(side, "side").upper()
    try:
        quantity = float(executed_quantity)
        price = float(executed_price)
    except (TypeError, ValueError) as exc:
        raise CanonicalExecutionError("quantity and price must be numeric") from exc
    if not math.isfinite(quantity) or quantity <= 0:
        raise CanonicalExecutionError("executed_quantity must be finite and positive")
    if not math.isfinite(price) or price <= 0:
        raise CanonicalExecutionError("executed_price must be finite and positive")
    normalized_sequence: int | None = None
    if execution_sequence is not None:
        if isinstance(execution_sequence, bool) or not isinstance(
            execution_sequence, Integral
        ):
            raise CanonicalExecutionError("execution_sequence must be an integer")
        if execution_sequence < 0:
            raise CanonicalExecutionError("execution_sequence cannot be negative")
        normalized_sequence = int(execution_sequence)

    source_execution = _optional_text(source_execution_id)
    source_order = _optional_text(source_order_id)
    normalized_sequence_source = _optional_text(sequence_source)
    if normalized_sequence is not None and normalized_sequence_source is None:
        raise CanonicalExecutionError(
            "sequence_source is required when execution_sequence is supplied"
        )
    identity = _optional_text(execution_id)
    if identity is None:
        # Sequence is deliberately excluded: a source fill keeps its identity if
        # later reconciliation corrects its ordering.
        source_identity: dict[str, str] = (
            {"source_execution_id": source_execution}
            if source_execution is not None
            else {"source_record_ref": record_ref}
        )
        identity = _canonical_hash(
            "exe_v2",
            {
                "schema_version": CANONICAL_EXECUTION_SCHEMA_VERSION,
                "subject_id": subject,
                "account_id": account,
                "source": normalized_source,
                **source_identity,
            },
        )
    return CanonicalExecutionV2(
        subject_id=subject,
        account_id=account,
        execution_id=identity,
        source_execution_id=source_execution,
        source_order_id=source_order,
        instrument=instrument,
        event_time=event_time,
        execution_sequence=normalized_sequence,
        side=normalized_side,
        executed_quantity=quantity,
        executed_price=price,
        fee=fee,
        provenance=ExecutionProvenance(
            source=normalized_source,
            source_record_ref=record_ref,
            sequence_source=normalized_sequence_source,
        ),
    )


@dataclass(frozen=True, slots=True)
class ExecutionReplayEligibility:
    eligible: bool
    block_reasons: tuple[ReplayBlockReason, ...]


def replay_eligibility(
    executions: Sequence[CanonicalExecutionV2],
) -> ExecutionReplayEligibility:
    """Evaluate exact/net, long-only replay readiness without mutating facts."""

    reasons: set[ReplayBlockReason] = set()
    groups: dict[tuple[str, str, str], list[CanonicalExecutionV2]] = {}
    ids: set[str] = set()
    for item in executions:
        if item.execution_id in ids:
            raise CanonicalExecutionError("execution_id must be unique")
        ids.add(item.execution_id)
        if item.instrument.instrument_id is None:
            reasons.add("blocked_unresolved_instrument")
        if item.fee.status == "unknown":
            reasons.add("blocked_unknown_fee")
        if item.side not in {"BUY", "SELL"}:
            reasons.add("blocked_unsupported_direction")
        key = (item.subject_id, item.account_id, item.event_time.ordering_key)
        groups.setdefault(key, []).append(item)
    for items in groups.values():
        if len(items) <= 1:
            continue
        sequences = [item.execution_sequence for item in items]
        if any(value is None for value in sequences) or len(set(sequences)) != len(sequences):
            reasons.add("blocked_ambiguous_order")
    ordered = tuple(sorted(reasons))
    return ExecutionReplayEligibility(not ordered, ordered)


def canonical_executions_to_frame(
    executions: Sequence[CanonicalExecutionV2],
) -> pd.DataFrame:
    """Map replay-eligible facts to the existing normalized replay boundary."""

    if not executions:
        raise CanonicalExecutionError("At least one canonical execution is required")
    eligibility = replay_eligibility(executions)
    if not eligibility.eligible:
        raise CanonicalExecutionError(
            "Canonical executions are not replay eligible: "
            + ", ".join(eligibility.block_reasons)
        )
    ownership = {(item.subject_id, item.account_id) for item in executions}
    if len(ownership) != 1:
        raise CanonicalExecutionError("One replay call must contain one subject and account")
    precision_kinds = {item.event_time.precision == "date" for item in executions}
    if len(precision_kinds) != 1:
        raise CanonicalExecutionError(
            "A replay batch cannot mix date-only and instant execution time semantics"
        )
    rows = []
    for item in executions:
        replay_time = item.event_time.replay_key
        canonical_event_time_utc = None
        if item.event_time.instant_utc is not None:
            canonical_event_time_utc = item.event_time.instant_utc.isoformat()
            # Existing pandas/vectorbt consumers use a timezone-naive axis.  The
            # transport value is explicitly UTC and never machine-local time.
            replay_time = item.event_time.instant_utc.tz_localize(None)
        rows.append(
            {
                "event_time": replay_time,
                "canonical_event_time_utc": canonical_event_time_utc,
                "market_date": pd.Timestamp(item.event_time.calendar_date),
                "symbol": item.instrument.instrument_id,
                "side": item.side,
                "executed_quantity": item.executed_quantity,
                "executed_price": item.executed_price,
                "fee": item.fee.amount,
                "order_id": item.source_order_id,
                "execution_id": item.execution_id,
                "subject_id": item.subject_id,
                "account_id": item.account_id,
                "execution_sequence": (
                    item.execution_sequence if item.execution_sequence is not None else 0
                ),
                "sequence_source": item.provenance.sequence_source or "singleton",
                "time_precision": item.event_time.precision,
                "source_timezone": item.event_time.source_timezone,
                "display_symbol": item.instrument.display_symbol,
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["event_time", "execution_sequence"], kind="stable"
    ).reset_index(drop=True)


class LegacyExecutionAdapter:
    """Additive adapter for current demo DataFrames; not a generic CSV parser."""

    @staticmethod
    def adapt(
        executions: pd.DataFrame,
        *,
        subject_id: str,
        account_id: str,
        source: str = "legacy_normalized_demo",
        source_timezone: str = "Asia/Shanghai",
    ) -> tuple[CanonicalExecutionV2, ...]:
        if not isinstance(executions, pd.DataFrame) or executions.empty:
            raise CanonicalExecutionError("At least one legacy execution is required")
        items: list[CanonicalExecutionV2] = []
        timestamps = pd.to_datetime(executions["event_time"], errors="raise")
        group_sizes = timestamps.groupby(timestamps).transform("size")
        group_sequence: dict[pd.Timestamp, int] = {}
        for ordinal, (_, row) in enumerate(executions.iterrows()):
            timestamp = pd.Timestamp(row["event_time"])
            sequence = group_sequence.get(timestamp, 0)
            group_sequence[timestamp] = sequence + 1
            timed = execution_time(
                timestamp,
                precision="second",
                source_timezone=(source_timezone if timestamp.tzinfo is None else None),
            )
            legacy_execution_id = _optional_text(row.get("execution_id"))
            if legacy_execution_id is None:
                raise CanonicalExecutionError(
                    "legacy normalized execution_id is required for identity migration"
                )
            items.append(
                canonical_execution(
                    subject_id=subject_id,
                    account_id=account_id,
                    execution_id=legacy_execution_id,
                    source_execution_id=legacy_execution_id,
                    source_order_id=_optional_text(row.get("order_id")),
                    instrument=legacy_demo_instrument(str(row["symbol"])),
                    event_time=timed,
                    execution_sequence=sequence,
                    sequence_source=(
                        "source_row_order" if int(group_sizes.iloc[ordinal]) > 1 else "singleton"
                    ),
                    side=str(row["side"]),
                    executed_quantity=row["executed_quantity"],
                    executed_price=row["executed_price"],
                    fee=fee_fact(row.get("fee")),
                    source=source,
                    source_record_ref=f"row:{ordinal}",
                )
            )
        return tuple(items)
