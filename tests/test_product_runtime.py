from pathlib import Path

from toujing_core_runtime.product import ProductRuntime


ROOT = Path(__file__).parents[1]


def trade_params():
    return {"file_path": str(ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"),
            "subject_id": "local-user", "account_id": "ACC-1", "display_name": "Local Account",
            "source_timezone": "Asia/Shanghai", "use_source_row_order_as_sequence": True,
            "initial_cash": 100000, "imported_at": "2026-09-04T12:00:00Z"}


def prices_file(tmp_path: Path) -> Path:
    return ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv"


def test_product_runtime_preview_commit_restart_reimport_and_delete(tmp_path):
    db = tmp_path / "runtime.sqlite3"
    runtime = ProductRuntime(db)
    trade = trade_params()
    preview = runtime.preview_trade(trade)
    assert preview["summary"]["new_executions"] == 5
    trade["expected_file_sha256"] = preview["batch"]["file_sha256"]
    trade["duplicate_choices"] = {}
    assert runtime.commit_trade(trade)["inserted_executions"] == 5
    assert runtime.commit_trade(trade)["inserted_executions"] == 0
    assert runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})["portfolio_state_reason"] == "unavailable_pending_market_data"
    market = {"file_path": str(prices_file(tmp_path)), "subject_id": "local-user", "account_id": "ACC-1",
              "source_id": "user_csv", "source_version": "v1", "imported_at": "2026-09-04T12:01:00Z"}
    market_preview = runtime.preview_market(market)
    assert market_preview["summary"]["new_observations"] == 5
    market["expected_file_sha256"] = market_preview["file_sha256"]
    assert runtime.commit_market(market)["inserted_observations"] == 5
    assert runtime.commit_market(market)["inserted_observations"] == 0
    investments = runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})
    assert investments["portfolio_state_status"] == "available"
    episode_id = investments["episodes"][0]["episode_id"]
    episode = runtime.episode({"subject_id": "local-user", "account_id": "ACC-1", "episode_id": episode_id})
    assert episode["status"] == "available"
    assert episode["entry"]["instrument"]["is_synthetic"] is False
    runtime.close()
    reopened = ProductRuntime(db)
    assert reopened.investments({"subject_id": "local-user", "account_id": "ACC-1"}) == investments
    assert reopened.delete_account({"subject_id": "local-user", "account_id": "ACC-1"}) == {"deleted": True}
    assert reopened.accounts({})["accounts"] == []


def test_runtime_never_persists_raw_csv_or_absolute_path(tmp_path):
    runtime = ProductRuntime(tmp_path / "db")
    trade = trade_params()
    preview = runtime.preview_trade(trade)
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"], duplicate_choices={})
    runtime.commit_trade(trade)
    history = runtime.data_status({"subject_id": "local-user", "account_id": "ACC-1"})["import_history"]
    assert history[0]["filename"] == "fixture_a_lifecycle.csv"
    assert str(ROOT) not in str(history)
    tables = {row[0] for row in runtime.repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "raw_csv" not in tables
    assert not {"pnl", "returns", "average_cost"}.intersection(tables)


def test_existing_account_initial_cash_cannot_be_rewritten(tmp_path):
    runtime = ProductRuntime(tmp_path / "db")
    trade = trade_params()
    preview = runtime.preview_trade(trade)
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"], duplicate_choices={})
    runtime.commit_trade(trade)
    trade["initial_cash"] = 200000
    import pytest
    with pytest.raises(ValueError, match="initial_cash cannot change"):
        runtime.commit_trade(trade)
    assert runtime.accounts({})["accounts"][0]["initial_cash"] == 100000
