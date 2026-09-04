"""Immutable product contracts for real-user import preview and bundles.

These objects describe parsing, reconciliation, and data quality.  They never
calculate portfolio state, PnL, cost basis, returns, or analytics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from src.core.canonical_execution import CanonicalExecutionV2, InstrumentRef
from src.evidence.contracts import canonical_json_bytes


IssueSeverity = Literal["error", "warning", "info"]
ImportRowStatus = Literal[
    "new_execution",
    "exact_duplicate",
    "possible_duplicate",
    "conflicting_revision",
    "invalid",
]


@dataclass(frozen=True, slots=True)
class ImportIssue:
    code: str
    severity: IssueSeverity
    row_ref: str | None
    field: str | None
    message_params: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "row_ref": self.row_ref,
            "field": self.field,
            "message_params": dict(self.message_params),
        }


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    schema_version: str
    mapping_version: str
    fields: tuple[tuple[str, str], ...]

    def source_column(self, canonical_field: str) -> str | None:
        return dict(self.fields).get(canonical_field)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mapping_version": self.mapping_version,
            "fields": dict(self.fields),
        }


@dataclass(frozen=True, slots=True)
class ImportSourceDefinition:
    source_type: str
    schema_version: str
    mapping_version: str

    @property
    def ref(self) -> str:
        return f"{self.source_type}:{self.schema_version}:{self.mapping_version}"


@dataclass(frozen=True, slots=True)
class RawImportRow:
    source_file_sha256: str
    source_row_identity: str
    row_number: int
    original_values: tuple[tuple[str, str], ...]
    mapping_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_file_sha256": self.source_file_sha256,
            "source_row_identity": self.source_row_identity,
            "row_number": self.row_number,
            "original_values": dict(self.original_values),
            "mapping_version": self.mapping_version,
        }


@dataclass(frozen=True, slots=True)
class RawImportBatch:
    batch_id: str
    source_type: str
    file_sha256: str
    schema_version: str
    mapping_version: str
    source_timezone: str | None
    subject_id: str
    account_id: str
    row_count: int
    rows: tuple[RawImportRow, ...]

    def as_dict(self, *, include_raw_values: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "batch_id": self.batch_id,
            "source_type": self.source_type,
            "file_sha256": self.file_sha256,
            "schema_version": self.schema_version,
            "mapping_version": self.mapping_version,
            "source_timezone": self.source_timezone,
            "subject_id": self.subject_id,
            "account_id": self.account_id,
            "row_count": self.row_count,
        }
        if include_raw_values:
            payload["rows"] = [row.as_dict() for row in self.rows]
        return payload


@dataclass(frozen=True, slots=True)
class ImportPreviewRow:
    row_ref: str
    status: ImportRowStatus
    candidate: CanonicalExecutionV2 | None
    issues: tuple[ImportIssue, ...]
    existing_execution_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        candidate: dict[str, object] | None = None
        if self.candidate is not None:
            item = self.candidate
            candidate = {
                **item.result_payload(),
                "instrument": {
                    "instrument_id": item.instrument.instrument_id,
                    "local_symbol": item.instrument.local_symbol,
                    "market": item.instrument.market,
                    "security_type": item.instrument.security_type,
                    "currency": item.instrument.currency,
                    "display_symbol": item.instrument.display_symbol,
                    "display_name": item.instrument.display_name,
                },
                "execution_time": {
                    "source_value": item.event_time.source_value,
                    "precision": item.event_time.precision,
                    "source_timezone": item.event_time.source_timezone,
                    "instant_utc": (
                        item.event_time.instant_utc.isoformat()
                        if item.event_time.instant_utc is not None
                        else None
                    ),
                    "calendar_date": item.event_time.calendar_date.isoformat(),
                },
                "fee": {
                    "status": item.fee.status,
                    "amount": item.fee.amount,
                    "currency": item.fee.currency,
                },
            }
        return {
            "row_ref": self.row_ref,
            "status": self.status,
            "candidate": candidate,
            "issues": [issue.as_dict() for issue in self.issues],
            "existing_execution_id": self.existing_execution_id,
        }


@dataclass(frozen=True, slots=True)
class ImportPreviewSummary:
    total_rows: int
    accepted_canonical_facts: int
    new_executions: int
    exact_duplicates: int
    possible_duplicates: int
    conflicts: int
    invalid_rows: int
    blocking_rows: int
    warning_rows: int
    replay_eligible_count: int
    replay_blocked_count: int
    instrument_issue_count: int
    fee_issue_count: int

    def as_dict(self) -> dict[str, int]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class ImportPreview:
    batch: RawImportBatch
    column_mapping: ColumnMapping | None
    rows: tuple[ImportPreviewRow, ...]
    batch_issues: tuple[ImportIssue, ...]
    summary: ImportPreviewSummary
    date_range: tuple[str, str] | None
    accounts: tuple[str, ...]
    instruments: tuple[str, ...]
    duplicate_file: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "batch": self.batch.as_dict(),
            "column_mapping": (
                self.column_mapping.as_dict() if self.column_mapping is not None else None
            ),
            "rows": [row.as_dict() for row in self.rows],
            "batch_issues": [issue.as_dict() for issue in self.batch_issues],
            "summary": self.summary.as_dict(),
            "date_range": list(self.date_range) if self.date_range is not None else None,
            "accounts": list(self.accounts),
            "instruments": list(self.instruments),
            "duplicate_file": self.duplicate_file,
        }


@dataclass(frozen=True, slots=True)
class MarketDataRequirement:
    instrument_id: str | None
    local_symbol: str
    market: str | None
    security_type: str | None
    start_date: str
    end_date: str
    price_frequency: str = "daily"
    exact_date_required: bool = True
    forward_fill_allowed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "local_symbol": self.local_symbol,
            "market": self.market,
            "security_type": self.security_type,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "price_frequency": self.price_frequency,
            "exact_date_required": self.exact_date_required,
            "forward_fill_allowed": self.forward_fill_allowed,
        }


@dataclass(frozen=True, slots=True)
class CanonicalImportBundle:
    bundle_id: str
    schema_version: str
    subject_id: str
    account_id: str
    source_metadata_refs: tuple[str, ...]
    accepted_canonical_executions: tuple[CanonicalExecutionV2, ...]
    instrument_refs: tuple[InstrumentRef, ...]
    data_quality_summary: ImportPreviewSummary
    duplicate_summary: tuple[tuple[str, int], ...]
    replay_eligibility_summary: tuple[tuple[str, int], ...]
    market_data_requirements: tuple[MarketDataRequirement, ...]
    limitations: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "account_id": self.account_id,
            "source_metadata_refs": list(self.source_metadata_refs),
            "accepted_canonical_executions": [
                item.result_payload() for item in self.accepted_canonical_executions
            ],
            "instrument_refs": [
                {
                    "instrument_id": item.instrument_id,
                    "local_symbol": item.local_symbol,
                    "market": item.market,
                    "security_type": item.security_type,
                    "currency": item.currency,
                    "display_symbol": item.display_symbol,
                    "display_name": item.display_name,
                }
                for item in self.instrument_refs
            ],
            "data_quality_summary": self.data_quality_summary.as_dict(),
            "duplicate_summary": dict(self.duplicate_summary),
            "replay_eligibility_summary": dict(self.replay_eligibility_summary),
            "market_data_requirements": [
                item.as_dict() for item in self.market_data_requirements
            ],
            "limitations": list(self.limitations),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_payload())


def stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"


def sorted_instruments(
    executions: Sequence[CanonicalExecutionV2],
) -> tuple[InstrumentRef, ...]:
    unique: dict[tuple[object, ...], InstrumentRef] = {}
    for item in executions:
        instrument = item.instrument
        key = (
            instrument.instrument_id,
            instrument.local_symbol,
            instrument.market,
            instrument.security_type,
        )
        unique[key] = instrument
    return tuple(unique[key] for key in sorted(unique, key=lambda value: repr(value)))
