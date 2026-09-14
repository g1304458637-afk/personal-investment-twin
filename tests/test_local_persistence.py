from pathlib import Path

import pytest

from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv
from src.market_data.generic_csv import GenericHistoricalPriceCsvAdapter, GenericPriceCsvConfig
from src.persistence import LocalRepository, RepositoryError


ROOT = Path(__file__).parents[1]
TRADES = ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"
PRICES = ROOT / "tests/fixtures/market_data/historical_prices_65.csv"


def trade_preview(repo: LocalRepository):
    return preview_generic_csv(
        TRADES.read_bytes(), config=GenericCsvImportConfig("subject", "ACC-1", "Asia/Shanghai"),
        existing_executions=repo.executions("subject", "ACC-1"),
        existing_file_hashes=repo.file_hashes("subject", "ACC-1", "trade"),
    )


def commit_trades(repo: LocalRepository):
    preview = trade_preview(repo)
    items = [row.candidate for row in preview.rows if row.status == "new_execution" and row.candidate]
    count = repo.commit_trade_import(subject_id="subject", account_id="ACC-1", display_name="我的账户",
        initial_cash=100000, batch_id=preview.batch.batch_id, file_sha256=preview.batch.file_sha256,
        filename="trades.csv", imported_at="2026-09-04T10:00:00+08:00", summary=preview.summary.as_dict(), executions=items)
    return preview, count


def test_fresh_migration_reopen_and_execution_round_trip(tmp_path):
    path = tmp_path / "toujing.sqlite3"
    repo = LocalRepository(path)
    preview, inserted = commit_trades(repo)
    expected = tuple(row.candidate for row in preview.rows if row.status == "new_execution" and row.candidate)
    assert inserted == len(expected)
    repo.close()
    reopened = LocalRepository(path)
    assert reopened.executions("subject", "ACC-1") == expected
    assert reopened.executions("subject", "ACC-1")[0].fee == expected[0].fee
    assert len(reopened.list_accounts()) == 1


def test_same_time_sequence_and_date_precision_round_trip(tmp_path):
    repo = LocalRepository(tmp_path / "db")
    preview = preview_generic_csv((ROOT / "tests/fixtures/ingestion/fixture_b_same_time.csv").read_bytes(),
        config=GenericCsvImportConfig("subject", "account", "Asia/Shanghai"))
    items = [row.candidate for row in preview.rows if row.candidate]
    repo.commit_trade_import(subject_id="subject", account_id="account", display_name="A", initial_cash=1e6,
        batch_id=preview.batch.batch_id, file_sha256=preview.batch.file_sha256, filename="same.csv",
        imported_at="2026-01-01T00:00:00Z", summary=preview.summary.as_dict(), executions=items)
    loaded = repo.executions("subject", "account")
    expected = sorted(items, key=lambda x: (x.event_time.ordering_key, x.execution_sequence or -1, x.execution_id))
    assert [(x.event_time.precision, x.execution_sequence) for x in loaded] == [(x.event_time.precision, x.execution_sequence) for x in expected]


def test_market_round_trip_duplicate_and_delete_cascade(tmp_path):
    repo = LocalRepository(tmp_path / "db")
    preview, _ = commit_trades(repo)
    known = tuple(row.candidate.instrument for row in preview.rows if row.candidate)
    market = GenericHistoricalPriceCsvAdapter().preview(PRICES.read_bytes(), GenericPriceCsvConfig(
        source_id="user_csv", source_version="v1", imported_at="2026-09-04T10:01:00Z", known_instruments=known))
    facts = [row.candidate for row in market.rows if row.status == "new_observation" and row.candidate]
    assert repo.commit_market_import(subject_id="subject", account_id="ACC-1", batch_id=market.batch_id,
        file_sha256=market.file_sha256, filename="prices.csv", imported_at="2026-09-04T10:01:00Z",
        summary={"new_observations": market.new_observations}, facts=facts) == len(facts)
    assert repo.prices("subject", "ACC-1") == tuple(facts)
    assert repo.delete_account("subject", "ACC-1")
    assert repo.executions("subject", "ACC-1") == ()
    assert repo.prices("subject", "ACC-1") == ()


def test_identical_market_file_is_account_owned(tmp_path):
    repo = LocalRepository(tmp_path / "db")
    preview, _ = commit_trades(repo)
    known = tuple(row.candidate.instrument for row in preview.rows if row.candidate)
    market = GenericHistoricalPriceCsvAdapter().preview(PRICES.read_bytes(), GenericPriceCsvConfig(
        source_id="user_csv", source_version="v1", imported_at="2026-09-04T10:01:00Z", known_instruments=known))
    facts = [row.candidate for row in market.rows if row.status == "new_observation" and row.candidate]
    repo.upsert_account("subject", "ACC-2", display_name="第二账户", initial_cash=200000, now="2026-09-04T10:00:00Z")
    repo.connection.commit()
    for account in ("ACC-1", "ACC-2"):
        assert repo.commit_market_import(
            subject_id="subject", account_id=account, batch_id=market.batch_id,
            file_sha256=market.file_sha256, filename="prices.csv",
            imported_at="2026-09-04T10:01:00Z", summary={}, facts=facts,
        ) == len(facts)
    assert repo.prices("subject", "ACC-1") == repo.prices("subject", "ACC-2")


def test_import_transaction_rolls_back(tmp_path):
    repo = LocalRepository(tmp_path / "db")
    preview = trade_preview(repo)
    with pytest.raises(RepositoryError):
        repo.commit_trade_import(subject_id="subject", account_id="account", display_name="A", initial_cash=1,
            batch_id=preview.batch.batch_id, file_sha256=preview.batch.file_sha256, filename="x.csv",
            imported_at="now", summary={}, executions=(), decisions=[("same", "keep", None), ("same", "skip", None)])
    assert repo.list_accounts() == []


def test_mixed_precision_order_is_documented_not_chronological(tmp_path):
    """Characterization: executions() order is not a cross-precision contract.

    event_order_key stores date-precision facts as "date:YYYY-MM-DD" and timed
    facts as ISO UTC instants; lexicographic SQL order across the two formats
    is not chronological.  The format is deliberately kept stable (rewriting
    stored keys would change persisted payload identity for existing rows);
    consumers needing chronology re-sort on timestamps, as
    canonical_executions_to_frame does.
    """
    from src.core.canonical_execution import (
        canonical_execution,
        execution_time,
        fee_fact,
        instrument_ref,
    )

    instrument = instrument_ref(local_symbol="A", market="X", security_type="equity")
    date_fact = canonical_execution(
        subject_id="subject", account_id="ACC-1", execution_id="EXE-DATE",
        source_execution_id="SRC-DATE", instrument=instrument,
        event_time=execution_time("2025-01-05", precision="date"),
        side="BUY", executed_quantity=1, executed_price=10, fee=fee_fact(0),
        source="test", source_record_ref="row-1",
    )
    timed_fact = canonical_execution(
        subject_id="subject", account_id="ACC-1", execution_id="EXE-TIMED",
        source_execution_id="SRC-TIMED", instrument=instrument,
        event_time=execution_time("2025-02-01 10:30+00:00", precision="minute"),
        side="BUY", executed_quantity=1, executed_price=10, fee=fee_fact(0),
        source="test", source_record_ref="row-2",
    )
    repo = LocalRepository(tmp_path / "db")
    try:
        repo.commit_trade_import(subject_id="subject", account_id="ACC-1", display_name="A",
            initial_cash=100000, batch_id="b-mixed", file_sha256="sha-mixed", filename="mixed.csv",
            imported_at="2026-09-04T10:00:00Z", summary={}, executions=(date_fact, timed_fact))
        loaded = repo.executions("subject", "ACC-1")
    finally:
        repo.close()

    assert {item.execution_id for item in loaded} == {"EXE-DATE", "EXE-TIMED"}
    # Lexicographic event_order_key order puts the timed February fact first
    # even though the date-precision January fact is earlier in time — the
    # documented, non-chronological ordering behavior.
    assert [item.execution_id for item in loaded] == ["EXE-TIMED", "EXE-DATE"]


def test_future_schema_fails_closed(tmp_path):
    import sqlite3
    path = tmp_path / "future.db"
    db = sqlite3.connect(path)
    db.execute("PRAGMA user_version=99")
    db.close()
    with pytest.raises(RepositoryError, match="future schema"):
        LocalRepository(path)


def test_schema_one_upgrade_preserves_original_facts(tmp_path):
    import sqlite3
    from src.persistence.repository import _MIGRATION_1
    path = tmp_path / "existing.db"
    with sqlite3.connect(path) as db:
        db.executescript(_MIGRATION_1 + "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
            "INSERT INTO schema_migrations VALUES(1,'original'); PRAGMA user_version=1;")
        db.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?)", ("s", "a", "existing", 100, "old", "old"))
    with sqlite3.connect(path) as db:
        before = db.execute("SELECT * FROM accounts").fetchall()
    repo = LocalRepository(path)
    try:
        assert [tuple(x) for x in repo.connection.execute("SELECT * FROM accounts")] == before
        assert repo.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert repo.connection.execute("SELECT applied_at FROM schema_migrations WHERE version=1").fetchone()[0] == "original"
        assert repo.connection.execute("SELECT COUNT(*) FROM execution_instrument_resolutions").fetchone()[0] == 0
    finally:
        repo.close()
