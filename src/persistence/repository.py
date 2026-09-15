"""Versioned SQLite repository for canonical imports.

Only source facts and audit metadata are authoritative here.  Financial
results remain disposable projections rebuilt by the deterministic core.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from src.core.canonical_execution import (
    CanonicalExecutionV2,
    canonical_execution,
    execution_time,
    fee_fact,
    instrument_ref,
)
from src.market_data.models import HistoricalPriceFact

SCHEMA_VERSION = 2


class RepositoryError(RuntimeError):
    pass


_MIGRATION_1 = """
CREATE TABLE accounts (
  subject_id TEXT NOT NULL, account_id TEXT NOT NULL, display_name TEXT NOT NULL,
  initial_cash REAL NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(subject_id, account_id)
);
CREATE TABLE import_batches (
  batch_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('trade','market')), file_sha256 TEXT NOT NULL,
  filename TEXT NOT NULL, imported_at TEXT NOT NULL, summary_json TEXT NOT NULL,
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
CREATE TABLE canonical_executions (
  execution_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
  event_order_key TEXT NOT NULL, execution_sequence INTEGER, instrument_id TEXT, payload_json TEXT NOT NULL,
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
CREATE INDEX executions_account_order ON canonical_executions(subject_id, account_id, event_order_key, execution_sequence, execution_id);
CREATE TABLE reconciliation_decisions (
  batch_id TEXT NOT NULL, row_ref TEXT NOT NULL, decision TEXT NOT NULL,
  existing_execution_id TEXT, PRIMARY KEY(batch_id, row_ref),
  FOREIGN KEY(batch_id) REFERENCES import_batches(batch_id) ON DELETE CASCADE
);
CREATE TABLE market_data_batches (
  batch_id TEXT NOT NULL, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
  file_sha256 TEXT NOT NULL, filename TEXT NOT NULL, imported_at TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  PRIMARY KEY(subject_id, account_id, batch_id),
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
CREATE TABLE market_price_observations (
  observation_id TEXT NOT NULL, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL, observation_date TEXT NOT NULL, price_type TEXT NOT NULL,
  source_id TEXT NOT NULL, source_version TEXT NOT NULL, close REAL NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(subject_id, account_id, observation_id),
  UNIQUE(subject_id, account_id, instrument_id, observation_date, price_type, source_id, source_version),
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
CREATE TABLE instrument_resolutions (
  subject_id TEXT NOT NULL, account_id TEXT NOT NULL, source_symbol TEXT NOT NULL,
  instrument_id TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(subject_id, account_id, source_symbol),
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
"""


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


_MIGRATION_2 = """
CREATE TABLE execution_instrument_resolutions (
  execution_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL, payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
  source_file_sha256 TEXT NOT NULL, source_row_ref TEXT NOT NULL,
  FOREIGN KEY(execution_id) REFERENCES canonical_executions(execution_id) ON DELETE CASCADE,
  FOREIGN KEY(subject_id, account_id) REFERENCES accounts(subject_id, account_id) ON DELETE CASCADE
);
"""


def _execution_payload(item: CanonicalExecutionV2) -> dict[str, object]:
    return {
        **item.result_payload(),
        "instrument": {
            "local_symbol": item.instrument.local_symbol, "market": item.instrument.market,
            "security_type": item.instrument.security_type, "currency": item.instrument.currency,
            "display_symbol": item.instrument.display_symbol, "display_name": item.instrument.display_name,
        },
        "execution_time": {
            "source_value": item.event_time.source_value, "precision": item.event_time.precision,
            "source_timezone": item.event_time.source_timezone,
        },
        "fee_currency": item.fee.currency,
    }


def _decode_execution(payload: str) -> CanonicalExecutionV2:
    raw = json.loads(payload)
    inst = raw["instrument"]
    instrument = instrument_ref(**inst)
    when = raw["execution_time"]
    return canonical_execution(
        subject_id=raw["subject_id"], account_id=raw["account_id"], execution_id=raw["execution_id"],
        source_execution_id=raw["source_execution_id"], source_order_id=raw["source_order_id"],
        instrument=instrument,
        event_time=execution_time(when["source_value"], precision=when["precision"], source_timezone=when["source_timezone"]),
        execution_sequence=raw["execution_sequence"], sequence_source=raw["sequence_source"],
        side=raw["side"], executed_quantity=raw["executed_quantity"], executed_price=raw["executed_price"],
        fee=fee_fact(raw["fee_amount"], currency=raw["fee_currency"]),
        source=raw["source"], source_record_ref=raw["source_record_ref"],
    )


def _price_payload(item: HistoricalPriceFact) -> dict[str, object]:
    return {
        "observation_id": item.observation_id,
        "instrument": {
            "local_symbol": item.instrument.local_symbol, "market": item.instrument.market,
            "security_type": item.instrument.security_type, "currency": item.instrument.currency,
            "display_symbol": item.instrument.display_symbol, "display_name": item.instrument.display_name,
        },
        "date": item.date.isoformat(), "close": item.close, "price_type": item.price_type,
        "currency": item.currency, "source_id": item.source_id, "source_tier": item.source_tier,
        "source_version": item.source_version, "imported_at": item.imported_at,
        "source_file_sha256": item.source_file_sha256, "source_row_identity": item.source_row_identity,
        "source_label": item.source_label,
    }


def _decode_price(payload: str) -> HistoricalPriceFact:
    raw = json.loads(payload)
    return HistoricalPriceFact(
        observation_id=raw["observation_id"], instrument=instrument_ref(**raw["instrument"]),
        date=date.fromisoformat(raw["date"]), close=raw["close"], price_type=raw["price_type"],
        currency=raw["currency"], source_id=raw["source_id"], source_tier=raw["source_tier"],
        source_version=raw["source_version"], imported_at=raw["imported_at"],
        source_file_sha256=raw["source_file_sha256"], source_row_identity=raw["source_row_identity"],
        source_label=raw["source_label"],
    )


class LocalRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        # WAL + busy_timeout: the sidecar holds a long-lived connection; any
        # second opener (scripts, backup tools) must not hit rollback-journal
        # lock contention where readers block writers and 5s locks fail.
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise RepositoryError(f"unsupported future schema version {current}")
        if current == 0:
            # A pre-versioning database already carries the base tables
            # (created before schema_migrations existed): stamp it at version 1
            # so the recorded migrations apply cleanly on top, instead of
            # failing with "table accounts already exists".
            base_tables = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if base_tables & {"accounts", "executions"}:
                # Base layout exists without version metadata. Stamp the
                # version implied by which migration artifacts are present:
                # the resolutions table is migration 2's product.
                stamped = 2 if "execution_instrument_resolutions" in base_tables else 1
                # Later migration steps INSERT INTO schema_migrations; a
                # pre-versioning database has never created it.
                self.connection.executescript(
                    "BEGIN IMMEDIATE;"
                    + "\nCREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
                    + f"\nINSERT INTO schema_migrations VALUES({stamped}, datetime('now'));"
                    + f"\nPRAGMA user_version={stamped};\nCOMMIT;"
                )
                current = stamped
        if current == 0:
            try:
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + _MIGRATION_1
                    + "\nCREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
                    + "\nINSERT INTO schema_migrations VALUES(1, datetime('now'));"
                    + "\nPRAGMA user_version=1;\nCOMMIT;"
                )
            except sqlite3.Error as exc:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise RepositoryError(f"migration failed: {exc}") from exc
            current = 1
        if current == 1:
            try:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + _MIGRATION_2
                    + "\nINSERT INTO schema_migrations VALUES(2, datetime('now'));"
                    + "\nPRAGMA user_version=2;\nCOMMIT;")
            except sqlite3.Error as exc:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise RepositoryError(f"migration failed: {exc}") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            with self.connection:
                yield self.connection
        except sqlite3.Error as exc:
            raise RepositoryError(str(exc)) from exc

    def upsert_account(self, subject_id: str, account_id: str, *, display_name: str, initial_cash: float, now: str) -> None:
        self.connection.execute(
            "INSERT INTO accounts VALUES(?,?,?,?,?,?) ON CONFLICT(subject_id,account_id) DO UPDATE SET display_name=excluded.display_name, updated_at=excluded.updated_at",
            (subject_id, account_id, display_name, initial_cash, now, now),
        )

    def list_accounts(self) -> list[dict[str, object]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM accounts ORDER BY created_at, subject_id, account_id")]

    def executions(self, subject_id: str, account_id: str, *, resolve_instruments: bool = True) -> tuple[CanonicalExecutionV2, ...]:
        # Ordering is NOT a cross-precision chronology contract.  The stored
        # event_order_key is the fact's ExecutionTime.ordering_key string:
        # date-precision facts use "date:YYYY-MM-DD" while timed facts use ISO
        # UTC instants, and those two forms do not sort chronologically against
        # each other (only within one precision).  The format is kept stable
        # because rewriting stored keys would change persisted payload
        # identity for existing rows without a data migration.  Callers that
        # need chronological order must re-sort on timestamps, as
        # canonical_executions_to_frame does.
        rows = self.connection.execute(
            "SELECT payload_json FROM canonical_executions WHERE subject_id=? AND account_id=? ORDER BY event_order_key, COALESCE(execution_sequence,-1), execution_id",
            (subject_id, account_id),
        )
        facts = tuple(_decode_execution(row[0]) for row in rows)
        if not resolve_instruments:
            return facts
        resolutions = {row[0]: instrument_ref(**json.loads(row[1])["instrument"])
            for row in self.connection.execute(
                "SELECT execution_id,payload_json FROM execution_instrument_resolutions WHERE subject_id=? AND account_id=?",
                (subject_id, account_id))}
        return tuple(replace(item, instrument=resolutions[item.execution_id])
            if item.execution_id in resolutions else item for item in facts)

    def prices(self, subject_id: str, account_id: str) -> tuple[HistoricalPriceFact, ...]:
        rows = self.connection.execute(
            "SELECT payload_json FROM market_price_observations WHERE subject_id=? AND account_id=? ORDER BY observation_date, instrument_id",
            (subject_id, account_id),
        )
        return tuple(_decode_price(row[0]) for row in rows)

    def file_hashes(self, subject_id: str, account_id: str, kind: str) -> tuple[str, ...]:
        table = "import_batches" if kind == "trade" else "market_data_batches"
        return tuple(row[0] for row in self.connection.execute(
            f"SELECT file_sha256 FROM {table} WHERE subject_id=? AND account_id=? ORDER BY imported_at, batch_id",
            (subject_id, account_id),
        ))

    def commit_trade_import(self, *, subject_id: str, account_id: str, display_name: str,
                            initial_cash: float, batch_id: str, file_sha256: str, filename: str,
                            imported_at: str, summary: Mapping[str, object], executions: Sequence[CanonicalExecutionV2],
                            decisions: Sequence[tuple[str, str, str | None]] = (),
                            resolutions: Sequence[tuple[str, str, Mapping[str, object]]] = (),
                            execution_resolutions: Sequence[tuple[str, str, Mapping[str, object]]] = ()) -> int:
        with self.transaction() as db:
            self.upsert_account(subject_id, account_id, display_name=display_name, initial_cash=initial_cash, now=imported_at)
            # A confirmed resolution is independent of import-batch idempotency.
            # The original execution JSON stays immutable; this is a qualified view.
            for execution_id, source_row_ref, payload in execution_resolutions:
                existing = db.execute("SELECT payload_json FROM canonical_executions WHERE execution_id=? AND subject_id=? AND account_id=?",
                    (execution_id, subject_id, account_id)).fetchone()
                if not existing or _decode_execution(existing[0]).instrument.instrument_id is not None:
                    raise RepositoryError("resolution requires an owned unresolved canonical execution")
                instrument = instrument_ref(**payload["instrument"])
                if instrument.instrument_id is None:
                    raise RepositoryError("resolution must identify a qualified instrument")
                previous = db.execute("SELECT payload_json FROM execution_instrument_resolutions WHERE execution_id=?", (execution_id,)).fetchone()
                if previous and instrument_ref(**json.loads(previous[0])["instrument"]) != instrument:
                    raise RepositoryError("conflicting instrument resolution requires explicit reconciliation")
                db.execute("INSERT OR IGNORE INTO execution_instrument_resolutions VALUES(?,?,?,?,?,?,?,?)",
                    (execution_id, subject_id, account_id, instrument.instrument_id, _dump(payload), imported_at, file_sha256, source_row_ref))
            if db.execute("SELECT 1 FROM import_batches WHERE batch_id=?", (batch_id,)).fetchone():
                return 0
            db.execute("INSERT INTO import_batches VALUES(?,?,?,?,?,?,?,?)",
                       (batch_id, subject_id, account_id, "trade", file_sha256, filename, imported_at, _dump(summary)))
            inserted = 0
            for item in executions:
                inserted += db.execute(
                    "INSERT OR IGNORE INTO canonical_executions VALUES(?,?,?,?,?,?,?)",
                    # ordering_key format contract: see executions() below.
                    (item.execution_id, subject_id, account_id, item.event_time.ordering_key, item.execution_sequence,
                     item.instrument.instrument_id, _dump(_execution_payload(item))),
                ).rowcount
            db.executemany("INSERT INTO reconciliation_decisions VALUES(?,?,?,?)",
                           ((batch_id, row, decision, existing) for row, decision, existing in decisions))
            db.executemany(
                "INSERT INTO instrument_resolutions VALUES(?,?,?,?,?) "
                "ON CONFLICT(subject_id,account_id,source_symbol) DO UPDATE SET "
                "instrument_id=excluded.instrument_id,payload_json=excluded.payload_json",
                ((subject_id, account_id, source_symbol, instrument_id, _dump(payload))
                 for source_symbol, instrument_id, payload in resolutions),
            )
        return inserted

    def commit_market_import(self, *, subject_id: str, account_id: str, batch_id: str,
                             file_sha256: str, filename: str, imported_at: str,
                             summary: Mapping[str, object], facts: Sequence[HistoricalPriceFact]) -> int:
        with self.transaction() as db:
            if db.execute(
                "SELECT 1 FROM market_data_batches WHERE subject_id=? AND account_id=? AND batch_id=?",
                (subject_id, account_id, batch_id),
            ).fetchone():
                return 0
            db.execute("INSERT INTO market_data_batches VALUES(?,?,?,?,?,?,?)",
                       (batch_id, subject_id, account_id, file_sha256, filename, imported_at, _dump(summary)))
            inserted = 0
            for item in facts:
                inserted += db.execute(
                    "INSERT OR IGNORE INTO market_price_observations VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (item.observation_id, subject_id, account_id, item.instrument.instrument_id,
                     item.date.isoformat(), item.price_type, item.source_id, item.source_version,
                     item.close, _dump(_price_payload(item))),
                ).rowcount
        return inserted

    def import_history(self, subject_id: str, account_id: str) -> list[dict[str, object]]:
        sql = """SELECT batch_id, kind, filename, imported_at, summary_json FROM import_batches
                 WHERE subject_id=? AND account_id=? UNION ALL
                 SELECT batch_id, 'market', filename, imported_at, summary_json FROM market_data_batches
                 WHERE subject_id=? AND account_id=? ORDER BY imported_at DESC, batch_id DESC"""
        return [dict(row) | {"summary": json.loads(row["summary_json"])} for row in self.connection.execute(sql, (subject_id, account_id, subject_id, account_id))]

    def delete_account(self, subject_id: str, account_id: str) -> bool:
        with self.transaction() as db:
            return bool(db.execute("DELETE FROM accounts WHERE subject_id=? AND account_id=?", (subject_id, account_id)).rowcount)
