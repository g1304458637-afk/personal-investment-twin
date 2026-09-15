"""Generic historical-price CSV adapter; parsing only, never market fetching."""

from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Protocol, Sequence

from src.core.canonical_execution import InstrumentRef, instrument_ref
from src.ingestion.contracts import CanonicalImportBundle, stable_id
from src.market_data.models import (
    HistoricalPriceFact,
    MarketDataImportIssue,
    MarketDataImportPreview,
    MarketDataPreviewRow,
    resolve_market_data_requirements,
)

GENERIC_HISTORICAL_PRICE_CSV_V1 = "generic_historical_price_csv_v1"
REAL_PRICE_TYPES = frozenset({"adjusted_close", "total_return"})
ALIASES = {
    "instrument_id": ("instrument_id",),
    "local_symbol": ("local_symbol", "symbol", "ticker"),
    "market": ("market", "exchange"),
    "security_type": ("security_type", "asset_type"),
    "date": ("date", "observation_date"),
    "price": ("price", "close"),
    "price_type": ("price_type", "price_basis"),
    "currency": ("currency", "ccy"),
    "source_label": ("source_label",),
}


class MarketDataSourceAdapter(Protocol):
    source_type: str

    def preview(
        self,
        content: bytes | str,
        config: "GenericPriceCsvConfig",
        *,
        existing: Sequence[HistoricalPriceFact] = (),
        requirement_bundle: CanonicalImportBundle | None = None,
    ) -> MarketDataImportPreview: ...


@dataclass(frozen=True, slots=True)
class GenericPriceCsvConfig:
    source_id: str
    source_version: str
    imported_at: str
    known_instruments: tuple[InstrumentRef, ...] = ()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing_{field}")
    return value.strip()


def _mapping(headers: Sequence[str]) -> dict[str, str]:
    lowered = {header.strip().lower(): header for header in headers}
    result: dict[str, str] = {}
    for field, aliases in ALIASES.items():
        matches = [lowered[value] for value in aliases if value in lowered]
        if len(matches) > 1:
            raise ValueError(f"ambiguous_{field}_column")
        if matches:
            result[field] = matches[0]
    for required in ("date", "price", "price_type"):
        if required not in result:
            raise ValueError(f"missing_{required}_column")
    if "instrument_id" not in result and not all(
        item in result for item in ("local_symbol", "market", "security_type")
    ):
        raise ValueError("missing_qualified_instrument_columns")
    return result


def _instrument(
    row: Mapping[str, str],
    mapping: Mapping[str, str],
    known: Mapping[str, InstrumentRef],
) -> InstrumentRef:
    # DictReader yields None (not "") for truncated rows: `or ""` keeps a
    # short row a per-row validation error instead of an AttributeError that
    # aborts the whole preview.
    raw_id = (row.get(mapping.get("instrument_id", "")) or "").strip()
    has_parts = all((row.get(mapping.get(name, "")) or "").strip() for name in ("local_symbol", "market", "security_type"))
    if has_parts:
        resolved = instrument_ref(
            local_symbol=row[mapping["local_symbol"]],
            market=row[mapping["market"]],
            security_type=row[mapping["security_type"]],
            currency=row.get(mapping.get("currency", "")) or None,
        )
        if raw_id and raw_id != resolved.instrument_id:
            raise ValueError("instrument_id_mismatch")
        return resolved
    if not raw_id or raw_id not in known:
        raise ValueError("unresolved_instrument")
    return known[raw_id]


class GenericHistoricalPriceCsvAdapter:
    source_type = GENERIC_HISTORICAL_PRICE_CSV_V1

    def preview(
        self,
        content: bytes | str,
        config: GenericPriceCsvConfig,
        *,
        existing: Sequence[HistoricalPriceFact] = (),
        requirement_bundle: CanonicalImportBundle | None = None,
    ) -> MarketDataImportPreview:
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("market CSV must be UTF-8") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames is None:
            raise ValueError("market CSV header is required")
        mapping = _mapping(reader.fieldnames)
        source_id = _text(config.source_id, "source_id")
        source_version = _text(config.source_version, "source_version")
        imported_at = _text(config.imported_at, "imported_at")
        file_hash = hashlib.sha256(raw).hexdigest()
        batch_id = stable_id(
            "market_batch",
            {
                "source_type": self.source_type,
                "file_sha256": file_hash,
                "source_id": source_id,
                "source_version": source_version,
            },
        )
        known = {
            str(item.instrument_id): item
            for item in config.known_instruments
            if item.instrument_id is not None
        }
        existing_by_key = {item.identity_key: item for item in existing}
        observed_by_key: dict[tuple[str, date, str, str, str], HistoricalPriceFact] = {}
        preview_rows: list[MarketDataPreviewRow] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                instrument = _instrument(row, mapping, known)
                observation_date = date.fromisoformat(_text(row[mapping["date"]], "date"))
                price = float(_text(row[mapping["price"]], "price"))
                if not math.isfinite(price) or price <= 0:
                    raise ValueError("invalid_price")
                price_type = _text(row[mapping["price_type"]], "price_type").lower()
                if price_type not in REAL_PRICE_TYPES:
                    raise ValueError("unsupported_price_type")
                identity = (
                    str(instrument.instrument_id),
                    observation_date,
                    price_type,
                    source_id,
                    source_version,
                )
                fact = HistoricalPriceFact(
                    observation_id=stable_id(
                        "price",
                        (
                            identity[0],
                            observation_date.isoformat(),
                            *identity[2:],
                        ),
                    ),
                    instrument=instrument,
                    date=observation_date,
                    close=price,
                    price_type=price_type,  # type: ignore[arg-type]
                    currency=(row.get(mapping.get("currency", "")) or None),
                    source_id=source_id,
                    source_tier="user_provided",
                    source_version=source_version,
                    imported_at=imported_at,
                    source_file_sha256=file_hash,
                    source_row_identity=stable_id("market_row", {"file": file_hash, "row": row_number}),
                    source_label=(row.get(mapping.get("source_label", "")) or None),
                )
                persisted = existing_by_key.get(identity)
                prior = observed_by_key.get(identity) or persisted
                if prior is None:
                    status = "new_observation"
                    observed_by_key[identity] = fact
                elif prior.close == fact.close:
                    status = "exact_duplicate"
                else:
                    status = "conflict"
                issue = () if status == "new_observation" else (MarketDataImportIssue(status, row_number, "price"),)
                preview_rows.append(
                    MarketDataPreviewRow(
                        row_number,
                        status,  # type: ignore[arg-type]
                        fact,
                        issue,
                        persisted.observation_id if persisted else None,
                    )
                )
            except (TypeError, ValueError) as exc:
                preview_rows.append(
                    MarketDataPreviewRow(
                        row_number,
                        "invalid",
                        None,
                        (MarketDataImportIssue(str(exc), row_number, None),),
                    )
                )

        candidates = tuple(
            row.candidate
            for row in preview_rows
            if row.status == "new_observation" and row.candidate is not None
        )
        all_facts = (*existing, *candidates)
        missing = ()
        if requirement_bundle is not None:
            missing = resolve_market_data_requirements(requirement_bundle, all_facts).missing
        dates = sorted(item.date.isoformat() for item in candidates)
        instruments = tuple(sorted({str(item.instrument.instrument_id) for item in candidates}))
        return MarketDataImportPreview(
            batch_id=batch_id,
            file_sha256=file_hash,
            rows=tuple(preview_rows),
            total_observations=len(preview_rows),
            new_observations=sum(row.status == "new_observation" for row in preview_rows),
            existing_observations=sum(row.status == "exact_duplicate" and row.existing_observation_id is not None for row in preview_rows),
            duplicate_rows=sum(row.status == "exact_duplicate" for row in preview_rows),
            conflicts=sum(row.status == "conflict" for row in preview_rows),
            invalid_rows=sum(row.status == "invalid" for row in preview_rows),
            instruments=instruments,
            date_range=((dates[0], dates[-1]) if dates else None),
            missing_required_dates=missing,
        )
