"""Safe ``generic_csv_v1`` adapter for CanonicalExecutionV2.

The adapter stops at preview and an in-memory canonical bundle.  It does not
persist data, fetch market prices, call vectorbt, or calculate financial
results.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from src.core.canonical_execution import (
    CanonicalExecutionError,
    CanonicalExecutionV2,
    InstrumentRef,
    TimePrecision,
    canonical_execution,
    execution_time,
    fee_fact,
    instrument_ref,
    replay_eligibility,
)
from src.evidence.contracts import canonical_json_bytes
from src.ingestion.contracts import (
    CanonicalImportBundle,
    ColumnMapping,
    ImportIssue,
    ImportPreview,
    ImportPreviewRow,
    ImportPreviewSummary,
    ImportSourceDefinition,
    MarketDataRequirement,
    RawImportBatch,
    RawImportRow,
    sorted_instruments,
    stable_id,
)


GENERIC_CSV_V1 = ImportSourceDefinition(
    source_type="generic_csv_v1",
    schema_version="1",
    mapping_version="generic_csv_mapping_v1",
)

IMPORT_ISSUE_CODES = frozenset(
    {
        "missing_required_field",
        "invalid_side",
        "invalid_quantity",
        "invalid_price",
        "invalid_fee",
        "invalid_timestamp",
        "timezone_required",
        "ambiguous_execution_order",
        "unknown_fee",
        "unresolved_instrument",
        "ambiguous_instrument",
        "exact_duplicate",
        "possible_duplicate",
        "conflicting_revision",
        "unsupported_short_or_margin",
        "replay_ineligible",
        "missing_market_data",
        "ambiguous_column_mapping",
        "unknown_canonical_field",
        "missing_explicit_source_column",
        "source_column_reused",
        "account_mismatch",
    }
)

_REQUIRED_FIELDS = frozenset({"event_time", "symbol", "side", "quantity", "price"})
_ALIASES: Mapping[str, tuple[str, ...]] = {
    "account": ("account", "account_id", "账户"),
    "symbol": ("symbol", "ticker", "code", "证券代码"),
    "market": ("market", "exchange", "市场", "交易所"),
    "security_type": ("security_type", "asset_type", "证券类型"),
    "event_time": ("event_time", "execution_time", "trade_time", "date", "成交时间", "成交日期"),
    "time_precision": ("time_precision", "时间精度"),
    "side": ("side", "type", "buy_sell", "买卖方向"),
    "quantity": ("quantity", "qty", "shares", "成交数量"),
    "price": ("price", "unit_price", "executed_price", "成交价格"),
    "fee": ("fee", "commission", "手续费"),
    "currency": ("currency", "ccy", "币种"),
    "source_execution_id": ("source_execution_id", "execution_id", "trade_id", "成交编号"),
    "source_order_id": ("source_order_id", "order_id", "委托编号"),
    "execution_sequence": ("execution_sequence", "sequence", "fill_sequence", "成交序号"),
}
_LIMITATIONS = (
    "generic_csv_v1_only_no_broker_specific_claim",
    "preview_and_in_memory_bundle_only_no_persistence",
    "long_only_exact_replay_requires_resolved_instrument_known_fee_and_order",
    "market_data_not_fetched_exact_daily_prices_required_downstream",
    "no_fx_conversion_or_multi_currency_accounting",
    "utf8_and_utf8_bom_only",
)


class ImportMappingError(ValueError):
    def __init__(self, code: str, field: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class GenericCsvImportConfig:
    subject_id: str
    account_id: str
    source_timezone: str | None = None
    default_time_precision: TimePrecision = "second"
    use_source_row_order_as_sequence: bool = False
    confirmed_instruments: Mapping[str, tuple[InstrumentRef, ...]] | None = None


def _header_key(value: str) -> str:
    return re.sub(r"[\s\-/]+", "_", value.strip().lstrip("\ufeff").casefold())


def _issue(
    code: str,
    severity: str,
    row_ref: str | None,
    field: str | None = None,
    **params: object,
) -> ImportIssue:
    return ImportIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        row_ref=row_ref,
        field=field,
        message_params=tuple(sorted((key, str(value)) for key, value in params.items())),
    )


def resolve_column_mapping(
    headers: Sequence[str],
    *,
    explicit_mapping: Mapping[str, str] | None = None,
) -> ColumnMapping:
    """Resolve only exact, versioned aliases; never fuzzy-match substrings."""

    header_lookup: dict[str, list[str]] = defaultdict(list)
    for header in headers:
        header_lookup[_header_key(header)].append(header)
    fields: dict[str, str] = {}
    used_sources: set[str] = set()
    explicit = dict(explicit_mapping or {})
    unknown_fields = set(explicit).difference(_ALIASES)
    if unknown_fields:
        raise ImportMappingError("unknown_canonical_field", sorted(unknown_fields)[0])
    for canonical_field, source_header in explicit.items():
        if source_header not in headers:
            raise ImportMappingError("missing_explicit_source_column", canonical_field)
        if headers.count(source_header) != 1:
            raise ImportMappingError("ambiguous_column_mapping", canonical_field)
        if source_header in used_sources:
            raise ImportMappingError("source_column_reused", canonical_field)
        fields[canonical_field] = source_header
        used_sources.add(source_header)

    for canonical_field, aliases in _ALIASES.items():
        if canonical_field in fields:
            continue
        matches: list[str] = []
        for alias in aliases:
            matches.extend(header_lookup.get(_header_key(alias), ()))
        matches = sorted(matches)
        if len(matches) > 1:
            raise ImportMappingError("ambiguous_column_mapping", canonical_field)
        if matches:
            fields[canonical_field] = matches[0]

    missing = sorted(_REQUIRED_FIELDS.difference(fields))
    if missing:
        raise ImportMappingError("missing_required_field", missing[0])
    return ColumnMapping(
        schema_version=GENERIC_CSV_V1.schema_version,
        mapping_version=GENERIC_CSV_V1.mapping_version,
        fields=tuple(sorted(fields.items())),
    )


def _decode(content: bytes | str) -> tuple[bytes, str]:
    if isinstance(content, str):
        encoded = content.encode("utf-8")
        return encoded, content.lstrip("\ufeff")
    try:
        return content, content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("unsupported_csv_encoding") from exc


def _parse_rows(text: str) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("missing_csv_header")
    headers = tuple(str(value).lstrip("\ufeff") for value in reader.fieldnames)
    rows: list[dict[str, str]] = []
    for source in reader:
        if source.get(None):
            raise ValueError("csv_row_has_extra_columns")
        normalized = {
            str(key).lstrip("\ufeff"): "" if value is None else str(value).strip()
            for key, value in source.items()
            if key is not None
        }
        if any(value != "" for value in normalized.values()):
            rows.append(normalized)
    return headers, rows


def _value(row: Mapping[str, str], mapping: ColumnMapping, field: str) -> str | None:
    source = mapping.source_column(field)
    if source is None:
        return None
    value = row.get(source, "").strip()
    return value or None


def _number(value: str | None, *, field: str, positive: bool) -> float:
    if value is None:
        raise ValueError("missing_required_field")
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"invalid_{field}")
    return result


def _sequence(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("ambiguous_execution_order") from exc
    if parsed < 0 or str(parsed) != value.strip():
        raise ValueError("ambiguous_execution_order")
    return parsed


def _precision(value: str | None, default: TimePrecision) -> TimePrecision:
    selected = (value or default).strip().lower()
    if selected not in {"date", "minute", "second", "millisecond", "microsecond"}:
        raise ValueError("invalid_timestamp")
    return selected  # type: ignore[return-value]


def _resolve_instrument(
    row: Mapping[str, str],
    mapping: ColumnMapping,
    config: GenericCsvImportConfig,
) -> tuple[InstrumentRef, tuple[ImportIssue, ...]]:
    symbol = _value(row, mapping, "symbol")
    if symbol is None:
        raise ValueError("missing_required_field")
    market = _value(row, mapping, "market")
    security_type = _value(row, mapping, "security_type")
    currency = _value(row, mapping, "currency")
    if market is not None and security_type is not None:
        return instrument_ref(
            local_symbol=symbol,
            market=market,
            security_type=security_type,
            currency=currency,
        ), ()

    candidates = tuple((config.confirmed_instruments or {}).get(symbol.upper(), ()))
    if len(candidates) > 1:
        unresolved = instrument_ref(
            local_symbol=symbol,
            market=market,
            security_type=security_type,
            currency=currency,
        )
        return unresolved, (_issue("ambiguous_instrument", "error", None, "symbol"),)
    if len(candidates) == 1:
        return candidates[0], ()
    unresolved = instrument_ref(
        local_symbol=symbol,
        market=market,
        security_type=security_type,
        currency=currency,
    )
    return unresolved, (_issue("unresolved_instrument", "error", None, "symbol"),)


def _fact_fingerprint_payload(item: CanonicalExecutionV2) -> dict[str, object]:
    return {
        "schema_version": item.schema_version,
        "subject_id": item.subject_id,
        "account_id": item.account_id,
        "instrument_id": item.instrument.instrument_id,
        "local_symbol": item.instrument.local_symbol,
        "market": item.instrument.market,
        "security_type": item.instrument.security_type,
        "currency": item.instrument.currency,
        "event_time": item.event_time.ordering_key,
        "time_precision": item.event_time.precision,
        "source_timezone": item.event_time.source_timezone,
        "side": item.side,
        "executed_quantity": item.executed_quantity,
        "executed_price": item.executed_price,
        "fee_status": item.fee.status,
        "fee_amount": item.fee.amount,
        "source_adapter": GENERIC_CSV_V1.source_type,
        "source_schema_version": GENERIC_CSV_V1.schema_version,
    }


def _fingerprint(item: CanonicalExecutionV2) -> str:
    return hashlib.sha256(canonical_json_bytes(_fact_fingerprint_payload(item))).hexdigest()


def _similarity_key(item: CanonicalExecutionV2) -> tuple[object, ...]:
    return (
        item.subject_id,
        item.account_id,
        item.instrument.instrument_id,
        item.instrument.local_symbol,
        item.event_time.ordering_key,
        item.side,
        item.executed_quantity,
        item.executed_price,
    )


def _result_equal(left: CanonicalExecutionV2, right: CanonicalExecutionV2) -> bool:
    return left.result_payload() == right.result_payload()


def _raw_batch(
    content_bytes: bytes,
    headers: Sequence[str],
    source_rows: Sequence[Mapping[str, str]],
    config: GenericCsvImportConfig,
) -> RawImportBatch:
    file_sha = hashlib.sha256(content_bytes).hexdigest()
    rows = tuple(
        RawImportRow(
            source_file_sha256=file_sha,
            source_row_identity=f"sha256:{file_sha}:row:{index}",
            row_number=index,
            original_values=tuple((header, row.get(header, "")) for header in headers),
            mapping_version=GENERIC_CSV_V1.mapping_version,
        )
        for index, row in enumerate(source_rows, start=2)
    )
    payload = {
        "source_type": GENERIC_CSV_V1.source_type,
        "file_sha256": file_sha,
        "schema_version": GENERIC_CSV_V1.schema_version,
        "mapping_version": GENERIC_CSV_V1.mapping_version,
        "source_timezone": config.source_timezone,
        "subject_id": config.subject_id,
        "account_id": config.account_id,
    }
    return RawImportBatch(
        batch_id=stable_id("batch", payload),
        source_type=GENERIC_CSV_V1.source_type,
        file_sha256=file_sha,
        schema_version=GENERIC_CSV_V1.schema_version,
        mapping_version=GENERIC_CSV_V1.mapping_version,
        source_timezone=config.source_timezone,
        subject_id=config.subject_id,
        account_id=config.account_id,
        row_count=len(rows),
        rows=rows,
    )


def _candidate(
    row: Mapping[str, str],
    raw: RawImportRow,
    mapping: ColumnMapping,
    config: GenericCsvImportConfig,
    occurrence_by_fingerprint: Counter[str],
) -> tuple[CanonicalExecutionV2, tuple[ImportIssue, ...]]:
    source_account = _value(row, mapping, "account")
    if source_account is not None and source_account != config.account_id:
        raise ValueError("account_mismatch")
    side = (_value(row, mapping, "side") or "").upper()
    side = {"买入": "BUY", "卖出": "SELL"}.get(side, side)
    if side not in {"BUY", "SELL"}:
        if side in {"SHORT", "SELL_SHORT", "MARGIN"}:
            raise ValueError("unsupported_short_or_margin")
        raise ValueError("invalid_side")
    quantity = _number(_value(row, mapping, "quantity"), field="quantity", positive=True)
    price = _number(_value(row, mapping, "price"), field="price", positive=True)
    raw_fee = _value(row, mapping, "fee")
    try:
        fees = fee_fact(raw_fee, currency=_value(row, mapping, "currency"))
    except CanonicalExecutionError as exc:
        raise ValueError("invalid_fee") from exc
    precision = _precision(_value(row, mapping, "time_precision"), config.default_time_precision)
    raw_time = _value(row, mapping, "event_time")
    if raw_time is None:
        raise ValueError("missing_required_field")
    try:
        when = execution_time(
            raw_time,
            precision=precision,
            source_timezone=config.source_timezone,
        )
    except CanonicalExecutionError as exc:
        if "source_timezone" in str(exc):
            raise ValueError("timezone_required") from exc
        raise ValueError("invalid_timestamp") from exc
    instrument, instrument_issues = _resolve_instrument(row, mapping, config)
    source_execution_id = _value(row, mapping, "source_execution_id")
    sequence = _sequence(_value(row, mapping, "execution_sequence"))
    sequence_source = "source_execution_sequence" if sequence is not None else None
    if sequence is None and config.use_source_row_order_as_sequence:
        sequence = raw.row_number
        sequence_source = "source_row_order"

    provisional = canonical_execution(
        subject_id=config.subject_id,
        account_id=config.account_id,
        source_execution_id=source_execution_id,
        source_order_id=_value(row, mapping, "source_order_id"),
        instrument=instrument,
        event_time=when,
        execution_sequence=sequence,
        sequence_source=sequence_source,
        side=side,
        executed_quantity=quantity,
        executed_price=price,
        fee=fees,
        source=GENERIC_CSV_V1.source_type,
        source_record_ref=(
            f"source_execution_id:{source_execution_id}"
            if source_execution_id is not None
            else raw.source_row_identity
        ),
    )
    if source_execution_id is None:
        fingerprint = _fingerprint(provisional)
        if provisional.source_order_id is not None:
            occurrence_evidence = f"source_order_id:{provisional.source_order_id}"
        elif sequence_source == "source_execution_sequence":
            # The sequence is not part of the content fingerprint.  With no
            # stable fill ID it is, however, the only source evidence that can
            # distinguish otherwise identical rows independently of physical
            # CSV order.
            occurrence_evidence = f"source_sequence:{sequence}"
        else:
            occurrence_evidence = "content_occurrence"
        occurrence_key = f"{fingerprint}:{occurrence_evidence}"
        occurrence = occurrence_by_fingerprint[occurrence_key]
        occurrence_by_fingerprint[occurrence_key] += 1
        stable_ref = (
            f"fingerprint:{fingerprint}:{occurrence_evidence}:occurrence:{occurrence}"
        )
        provisional = canonical_execution(
            subject_id=config.subject_id,
            account_id=config.account_id,
            source_order_id=provisional.source_order_id,
            instrument=instrument,
            event_time=when,
            execution_sequence=sequence,
            sequence_source=sequence_source,
            side=side,
            executed_quantity=quantity,
            executed_price=price,
            fee=fees,
            source=GENERIC_CSV_V1.source_type,
            source_record_ref=stable_ref,
        )
    issues = list(instrument_issues)
    if fees.status == "unknown":
        issues.append(_issue("unknown_fee", "warning", None, "fee"))
    return provisional, tuple(issues)


def _annotate_group_eligibility(rows: list[ImportPreviewRow]) -> list[ImportPreviewRow]:
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.status == "new_execution" and row.candidate is not None:
            item = row.candidate
            groups[(item.subject_id, item.account_id, item.event_time.ordering_key)].append(index)
    for indices in groups.values():
        if len(indices) <= 1:
            continue
        sequences = [rows[index].candidate.execution_sequence for index in indices]  # type: ignore[union-attr]
        if any(value is None for value in sequences) or len(set(sequences)) != len(sequences):
            for index in indices:
                row = rows[index]
                issue = _issue("ambiguous_execution_order", "error", row.row_ref, "execution_sequence")
                rows[index] = ImportPreviewRow(
                    row_ref=row.row_ref,
                    status=row.status,
                    candidate=row.candidate,
                    issues=tuple((*row.issues, issue)),
                    existing_execution_id=row.existing_execution_id,
                )
    return rows


def preview_generic_csv(
    content: bytes | str,
    *,
    config: GenericCsvImportConfig,
    explicit_mapping: Mapping[str, str] | None = None,
    existing_executions: Sequence[CanonicalExecutionV2] = (),
    existing_file_hashes: Sequence[str] = (),
) -> ImportPreview:
    """Parse, normalize, reconcile, and preview without persistence or replay."""

    content_bytes, text = _decode(content)
    headers, source_rows = _parse_rows(text)
    batch = _raw_batch(content_bytes, headers, source_rows, config)
    try:
        mapping = resolve_column_mapping(headers, explicit_mapping=explicit_mapping)
    except ImportMappingError as exc:
        issue = _issue(exc.code, "error", None, exc.field)
        rows = tuple(
            ImportPreviewRow(raw.source_row_identity, "invalid", None, (issue,))
            for raw in batch.rows
        )
        summary = _summary(rows)
        return ImportPreview(
            batch=batch,
            column_mapping=None,
            rows=rows,
            batch_issues=(issue,),
            summary=summary,
            date_range=None,
            accounts=(),
            instruments=(),
            duplicate_file=batch.file_sha256 in set(existing_file_hashes),
        )

    by_source_id = {
        (item.subject_id, item.account_id, item.provenance.source, item.source_execution_id): item
        for item in existing_executions
        if item.source_execution_id is not None
    }
    by_execution_id = {item.execution_id: item for item in existing_executions}
    by_similarity: dict[tuple[object, ...], list[CanonicalExecutionV2]] = defaultdict(list)
    for item in existing_executions:
        by_similarity[_similarity_key(item)].append(item)
    occurrence_by_fingerprint: Counter[str] = Counter()
    preview_rows: list[ImportPreviewRow] = []

    for source_row, raw in zip(source_rows, batch.rows):
        row_ref = raw.source_row_identity
        try:
            candidate, candidate_issues = _candidate(
                source_row,
                raw,
                mapping,
                config,
                occurrence_by_fingerprint,
            )
        except (CanonicalExecutionError, ValueError) as exc:
            code = str(exc)
            if code not in {
                "account_mismatch",
                "ambiguous_execution_order",
                "invalid_price",
                "invalid_quantity",
                "invalid_fee",
                "invalid_side",
                "invalid_timestamp",
                "missing_required_field",
                "timezone_required",
                "unsupported_short_or_margin",
            }:
                code = "invalid"
            preview_rows.append(
                ImportPreviewRow(
                    row_ref=row_ref,
                    status="invalid",
                    candidate=None,
                    issues=(_issue(code, "error", row_ref),),
                )
            )
            continue

        issues = tuple(
            ImportIssue(item.code, item.severity, row_ref, item.field, item.message_params)
            for item in candidate_issues
        )
        existing: CanonicalExecutionV2 | None = None
        status = "new_execution"
        if candidate.source_execution_id is not None:
            source_key = (
                candidate.subject_id,
                candidate.account_id,
                candidate.provenance.source,
                candidate.source_execution_id,
            )
            existing = by_source_id.get(source_key)
            if existing is not None:
                status = "exact_duplicate" if _result_equal(candidate, existing) else "conflicting_revision"
        else:
            existing = by_execution_id.get(candidate.execution_id)
            if existing is not None:
                status = "exact_duplicate" if _result_equal(candidate, existing) else "possible_duplicate"
            elif by_similarity.get(_similarity_key(candidate)):
                existing = by_similarity[_similarity_key(candidate)][0]
                status = "possible_duplicate"

        if status == "exact_duplicate":
            issues = (*issues, _issue("exact_duplicate", "info", row_ref))
        elif status == "possible_duplicate":
            issues = (*issues, _issue("possible_duplicate", "warning", row_ref))
        elif status == "conflicting_revision":
            issues = (*issues, _issue("conflicting_revision", "error", row_ref))
        preview_rows.append(
            ImportPreviewRow(
                row_ref=row_ref,
                status=status,  # type: ignore[arg-type]
                candidate=candidate,
                issues=issues,
                existing_execution_id=(existing.execution_id if existing else None),
            )
        )
        if status == "new_execution":
            by_execution_id[candidate.execution_id] = candidate
            if candidate.source_execution_id is not None:
                by_source_id[source_key] = candidate

    preview_rows = _annotate_group_eligibility(preview_rows)
    summary = _summary(preview_rows)
    candidates = [row.candidate for row in preview_rows if row.candidate is not None]
    dates = sorted(item.event_time.calendar_date.isoformat() for item in candidates)
    instruments = sorted(
        {
            item.instrument.instrument_id or f"unresolved:{item.instrument.local_symbol}"
            for item in candidates
        }
    )
    return ImportPreview(
        batch=batch,
        column_mapping=mapping,
        rows=tuple(preview_rows),
        batch_issues=(),
        summary=summary,
        date_range=((dates[0], dates[-1]) if dates else None),
        accounts=tuple(sorted({item.account_id for item in candidates})),
        instruments=tuple(instruments),
        duplicate_file=batch.file_sha256 in set(existing_file_hashes),
    )


def _summary(rows: Sequence[ImportPreviewRow]) -> ImportPreviewSummary:
    statuses = Counter(row.status for row in rows)
    accepted = [
        row.candidate
        for row in rows
        if row.status == "new_execution" and row.candidate is not None
    ]
    eligible = 0
    blocked = 0
    for item in accepted:
        if replay_eligibility((item,)).eligible:
            eligible += 1
        else:
            blocked += 1
    # Account-level order ambiguity is only observable across a group.
    order_blocked_ids = {
        row.candidate.execution_id
        for row in rows
        if row.status == "new_execution"
        and row.candidate is not None
        and any(issue.code == "ambiguous_execution_order" for issue in row.issues)
    }
    newly_order_blocked = sum(
        item.execution_id in order_blocked_ids and replay_eligibility((item,)).eligible
        for item in accepted
    )
    eligible -= newly_order_blocked
    blocked += newly_order_blocked
    return ImportPreviewSummary(
        total_rows=len(rows),
        accepted_canonical_facts=len(accepted),
        new_executions=statuses["new_execution"],
        exact_duplicates=statuses["exact_duplicate"],
        possible_duplicates=statuses["possible_duplicate"],
        conflicts=statuses["conflicting_revision"],
        invalid_rows=statuses["invalid"],
        blocking_rows=sum(any(issue.severity == "error" for issue in row.issues) for row in rows),
        warning_rows=sum(any(issue.severity == "warning" for issue in row.issues) for row in rows),
        replay_eligible_count=eligible,
        replay_blocked_count=blocked,
        instrument_issue_count=sum(
            issue.code in {"unresolved_instrument", "ambiguous_instrument"}
            for row in rows
            for issue in row.issues
        ),
        fee_issue_count=sum(
            issue.code == "unknown_fee" for row in rows for issue in row.issues
        ),
    )


def build_canonical_import_bundle(preview: ImportPreview) -> CanonicalImportBundle:
    """Build the accepted in-memory fact set; unresolved/unknown facts remain."""

    accepted = tuple(
        sorted(
            (
                row.candidate
                for row in preview.rows
                if row.status == "new_execution" and row.candidate is not None
            ),
            key=lambda item: (
                item.event_time.ordering_key,
                item.execution_sequence if item.execution_sequence is not None else -1,
                item.execution_id,
            ),
        )
    )
    instruments = sorted_instruments(accepted)
    dates_by_instrument: dict[tuple[object, ...], list[str]] = defaultdict(list)
    for item in accepted:
        key = (
            item.instrument.instrument_id,
            item.instrument.local_symbol,
            item.instrument.market,
            item.instrument.security_type,
        )
        dates_by_instrument[key].append(item.event_time.calendar_date.isoformat())
    requirements = tuple(
        MarketDataRequirement(
            instrument_id=key[0],
            local_symbol=str(key[1]),
            market=key[2],  # type: ignore[arg-type]
            security_type=key[3],  # type: ignore[arg-type]
            start_date=min(dates),
            end_date=max(dates),
        )
        for key, dates in sorted(dates_by_instrument.items(), key=lambda item: repr(item[0]))
    )
    per_item = [replay_eligibility((item,)).eligible for item in accepted]
    ambiguous_ids = {
        row.candidate.execution_id
        for row in preview.rows
        if row.candidate is not None
        and any(issue.code == "ambiguous_execution_order" for issue in row.issues)
    }
    eligible_count = sum(
        eligible and item.execution_id not in ambiguous_ids
        for item, eligible in zip(accepted, per_item)
    )
    replay_summary = (
        ("eligible", eligible_count),
        ("blocked", len(accepted) - eligible_count),
    )
    duplicate_summary = (
        ("exact_duplicate", preview.summary.exact_duplicates),
        ("possible_duplicate", preview.summary.possible_duplicates),
        ("conflicting_revision", preview.summary.conflicts),
    )
    identity_payload = {
        "schema_version": "canonical_import_bundle_v1",
        "subject_id": preview.batch.subject_id,
        "account_id": preview.batch.account_id,
        "source_metadata_refs": [GENERIC_CSV_V1.ref],
        "executions": [item.result_payload() for item in accepted],
    }
    return CanonicalImportBundle(
        bundle_id=stable_id("bundle", identity_payload),
        schema_version="canonical_import_bundle_v1",
        subject_id=preview.batch.subject_id,
        account_id=preview.batch.account_id,
        source_metadata_refs=(GENERIC_CSV_V1.ref,),
        accepted_canonical_executions=accepted,
        instrument_refs=instruments,
        data_quality_summary=preview.summary,
        duplicate_summary=duplicate_summary,
        replay_eligibility_summary=replay_summary,
        market_data_requirements=requirements,
        limitations=_LIMITATIONS,
    )
