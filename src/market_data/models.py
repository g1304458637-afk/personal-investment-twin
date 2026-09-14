"""Immutable facts and coverage views for historical daily market data."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

import pandas as pd

from src.core.canonical_execution import InstrumentRef
from src.ingestion.contracts import CanonicalImportBundle

PriceType = Literal["adjusted_close", "total_return", "synthetic"]
PriceSourceTier = Literal["user_provided", "licensed_provider", "synthetic_demo"]
MarketDataRowStatus = Literal["new_observation", "exact_duplicate", "conflict", "invalid"]
MarketDataCoverageStatus = Literal["complete", "partial", "missing"]


@dataclass(frozen=True, slots=True)
class HistoricalPriceFact:
    observation_id: str
    instrument: InstrumentRef
    date: date
    close: float
    price_type: PriceType
    currency: str | None
    source_id: str
    source_tier: PriceSourceTier
    source_version: str
    imported_at: str
    source_file_sha256: str
    source_row_identity: str
    source_label: str | None = None

    def __post_init__(self) -> None:
        if self.instrument.instrument_id is None:
            raise ValueError("historical price requires a qualified instrument")
        if not math.isfinite(self.close) or self.close <= 0:
            raise ValueError("historical price close must be finite and positive")
        if self.price_type not in {"adjusted_close", "total_return", "synthetic"}:
            raise ValueError("unsupported Market Data Contract price_type")
        if self.source_tier == "synthetic_demo" and self.price_type != "synthetic":
            raise ValueError("synthetic_demo source requires synthetic price_type")
        if self.source_tier != "synthetic_demo" and self.price_type == "synthetic":
            raise ValueError("real market source cannot use synthetic price_type")
        for value, name in (
            (self.observation_id, "observation_id"),
            (self.source_id, "source_id"),
            (self.source_version, "source_version"),
            (self.imported_at, "imported_at"),
            (self.source_file_sha256, "source_file_sha256"),
            (self.source_row_identity, "source_row_identity"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

    @property
    def identity_key(self) -> tuple[str, date, str, str, str]:
        return (
            str(self.instrument.instrument_id),
            self.date,
            self.price_type,
            self.source_id,
            self.source_version,
        )

    def market_contract_payload(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "instrument": self.instrument.instrument_id,
            "close": self.close,
            "price_type": self.price_type,
            "data_source": self.source_id,
            "data_version": self.source_version,
            "is_synthetic": self.source_tier == "synthetic_demo",
        }


@dataclass(frozen=True, slots=True)
class MarketDataImportIssue:
    code: str
    row_number: int | None
    field: str | None


@dataclass(frozen=True, slots=True)
class MarketDataPreviewRow:
    row_number: int
    status: MarketDataRowStatus
    candidate: HistoricalPriceFact | None
    issues: tuple[MarketDataImportIssue, ...]
    existing_observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class MarketDataImportPreview:
    batch_id: str
    file_sha256: str
    rows: tuple[MarketDataPreviewRow, ...]
    total_observations: int
    new_observations: int
    existing_observations: int
    duplicate_rows: int
    conflicts: int
    invalid_rows: int
    instruments: tuple[str, ...]
    date_range: tuple[str, str] | None
    missing_required_dates: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class MarketDataAvailability:
    status: MarketDataCoverageStatus
    required_observation_count: int
    available_observation_count: int
    missing: tuple[tuple[str, tuple[str, ...]], ...]
    limitations: tuple[str, ...]


def facts_to_market_data_frame(facts: Sequence[HistoricalPriceFact]) -> pd.DataFrame:
    """Project canonical facts into the frozen Market Data Contract."""

    rows = [item.market_contract_payload() for item in sorted(facts, key=lambda value: value.identity_key)]
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "instrument",
            "close",
            "price_type",
            "data_source",
            "data_version",
            "is_synthetic",
        ],
    )


def resolve_market_data_requirements(
    bundle: CanonicalImportBundle,
    facts: Sequence[HistoricalPriceFact],
    *,
    as_of: pd.Timestamp | None = None,
) -> MarketDataAvailability:
    """Resolve exact replay-panel coverage without filling or interpolation.

    The Behavior replay pivot builds one daily panel over every traded symbol
    from the globally earliest execution date onward, so a calendar date that
    is observed for any traded symbol requires *all* traded symbols to have a
    price on that date.  The required set therefore includes those cross-symbol
    panel dates in addition to each instrument's own execution dates; otherwise
    a "complete" verdict would still fail the later pivot with an unhandled
    panel-gap error.
    """

    executions = [
        execution
        for execution in bundle.accepted_canonical_executions
        if execution.instrument.instrument_id is not None
    ]
    required: dict[str, set[str]] = {}
    panel_start: date | None = None
    for execution in executions:
        instrument_id = str(execution.instrument.instrument_id)
        required.setdefault(instrument_id, set()).add(
            execution.event_time.calendar_date.isoformat()
        )
        if panel_start is None or execution.event_time.calendar_date < panel_start:
            panel_start = execution.event_time.calendar_date
    as_of_date: date | None = None
    if as_of is not None:
        as_of_date = pd.Timestamp(as_of).normalize().date()
    # Dates actually present in the panel: every non-synthetic observation of
    # a traded symbol at or after the first execution date (and, when the
    # caller supplies one, at or before ``as_of`` because the replay windows
    # price observations to that boundary).
    panel_dates: set[str] = set()
    for item in facts:
        instrument_id = str(item.instrument.instrument_id)
        if item.source_tier == "synthetic_demo" or instrument_id not in required:
            continue
        if panel_start is not None and item.date < panel_start:
            continue
        if as_of_date is not None and item.date > as_of_date:
            continue
        panel_dates.add(item.date.isoformat())
    for instrument_id in required:
        required[instrument_id] |= panel_dates
    available = {
        (str(item.instrument.instrument_id), item.date.isoformat())
        for item in facts
        if item.source_tier != "synthetic_demo"
    }
    missing = tuple(
        (instrument_id, tuple(sorted(date_value for date_value in dates if (instrument_id, date_value) not in available)))
        for instrument_id, dates in sorted(required.items())
    )
    missing = tuple(item for item in missing if item[1])
    required_count = sum(len(dates) for dates in required.values())
    missing_count = sum(len(dates) for _, dates in missing)
    available_count = required_count - missing_count
    if required_count == 0 or available_count == 0:
        status: MarketDataCoverageStatus = "missing"
    elif missing_count:
        status = "partial"
    else:
        status = "complete"
    limitations = (
        "exact_daily_observations_only_no_forward_fill",
        "corporate_actions_are_not_calculated_by_market_import",
    )
    return MarketDataAvailability(status, required_count, available_count, missing, limitations)
