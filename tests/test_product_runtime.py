from pathlib import Path

import pandas as pd
import pytest

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
    trade["expected_preview_fingerprint"] = preview["preview_fingerprint"]
    trade["duplicate_choices"] = {}
    assert runtime.commit_trade(trade)["inserted_executions"] == 5
    assert runtime.commit_trade(trade)["inserted_executions"] == 0
    assert runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})["portfolio_state_reason"] == "unavailable_pending_market_data"
    market = {"file_path": str(prices_file(tmp_path)), "subject_id": "local-user", "account_id": "ACC-1",
              "source_id": "user_csv", "source_version": "v1", "imported_at": "2026-09-04T12:01:00Z"}
    market_preview = runtime.preview_market(market)
    assert market_preview["summary"]["new_observations"] == 5
    market["expected_file_sha256"] = market_preview["file_sha256"]
    market["expected_preview_fingerprint"] = market_preview["preview_fingerprint"]
    assert runtime.commit_market(market)["inserted_observations"] == 5
    assert runtime.commit_market(market)["inserted_observations"] == 0
    investments = runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})
    assert investments["portfolio_state_status"] == "available"
    episode_id = investments["episodes"][0]["episode_id"]
    episode = runtime.episode({"subject_id": "local-user", "account_id": "ACC-1", "episode_id": episode_id})
    assert episode["status"] == "available"
    assert episode["entry"]["instrument"]["is_synthetic"] is False
    analysis = episode["entry"]["path_analysis"]
    assert analysis["episode_id"] == episode_id
    assert analysis["phases"]
    assert analysis["phases"][0]["phase_type"] == "entry"
    runtime.close()
    reopened = ProductRuntime(db)
    assert reopened.investments({"subject_id": "local-user", "account_id": "ACC-1"}) == investments
    assert reopened.delete_account({"subject_id": "local-user", "account_id": "ACC-1"}) == {"deleted": True}
    assert reopened.accounts({})["accounts"] == []


def test_runtime_never_persists_raw_csv_or_absolute_path(tmp_path):
    runtime = ProductRuntime(tmp_path / "db")
    trade = trade_params()
    preview = runtime.preview_trade(trade)
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"], expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
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
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"], expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
    runtime.commit_trade(trade)
    trade["initial_cash"] = 200000
    preview = runtime.preview_trade(trade)
    trade["expected_preview_fingerprint"] = preview["preview_fingerprint"]
    import pytest
    with pytest.raises(ValueError, match="initial_cash cannot change"):
        runtime.commit_trade(trade)
    assert runtime.accounts({})["accounts"][0]["initial_cash"] == 100000


def _import_trades(runtime, params):
    preview = runtime.preview_trade(params)
    params.update(expected_file_sha256=preview["batch"]["file_sha256"], expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
    return runtime.commit_trade(params)


def _market_params():
    return {"file_path": str(ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv"),
            "subject_id": "local-user", "account_id": "ACC-1", "source_id": "user_csv",
            "source_version": "v1", "imported_at": "2026-09-04T12:01:00Z"}


@pytest.mark.parametrize("same_time_executions", [False, True])
def test_latest_daily_observation_includes_intraday_canonical_executions(
    tmp_path, monkeypatch, same_time_executions,
):
    from src.episodes import position_episode

    # Reuse the audited lifecycle, changing only the final fill's time. The
    # optional same-time rows deliberately arrive in reverse sequence order.
    params = trade_params()
    content = Path(params["file_path"]).read_text().replace(
        "2025-01-06 09:30:00", "2025-01-06 15:00:00",
    )
    if same_time_executions:
        content += (
            "ACC-1,600000,XSHG,equity,2025-01-06 15:00:00,SELL,10,12.50,1.00,CNY,A-7,AO-7,3\n"
            "ACC-1,600000,XSHG,equity,2025-01-06 15:00:00,BUY,30,12.50,1.00,CNY,A-6,AO-6,2\n"
        )
    trade_file = tmp_path / "latest_day.csv"
    trade_file.write_text(content)
    params["file_path"] = str(trade_file)
    runtime = ProductRuntime(tmp_path / "runtime.db")
    try:
        expected_count = 7 if same_time_executions else 5
        assert _import_trades(runtime, params)["inserted_executions"] == expected_count
        market = _market_params()
        preview = runtime.preview_market(market)
        market["expected_file_sha256"] = preview["file_sha256"]
        market["expected_preview_fingerprint"] = preview["preview_fingerprint"]
        runtime.commit_market(market)
        stored = runtime.repo.executions("local-user", "ACC-1")
        assert len(stored) == expected_count
        ids = {item.source_execution_id: item.execution_id for item in stored}
        ordered_ids = [ids[f"A-{i}"] for i in range(1, expected_count + 1)]
        last_day = [item for item in stored if item.source_execution_id in {"A-5", "A-6", "A-7"}]
        assert all(item.event_time.source_value == "2025-01-06 15:00:00" for item in last_day)
        assert [item.execution_sequence for item in last_day] == list(range(1, len(last_day) + 1))

        replay_consumed = []
        prepare = position_episode.prepare_behavior_replay

        def capture_replay(*args, **kwargs):
            result = prepare(*args, **kwargs)
            replay_consumed.append([link.execution_id for link in result.execution_links])
            return result

        monkeypatch.setattr(position_episode, "prepare_behavior_replay", capture_replay)
        account = {"subject_id": "local-user", "account_id": "ACC-1"}
        investments = runtime.investments(account)
        assert replay_consumed == [ordered_ids]
        assert investments["summary"] == {
            "open_episode_count": 1, "closed_episode_count": 1, "current_position_count": 1,
        }
        current = next(item for item in investments["episodes"] if item["status"] == "open")
        assert current["quantity"] == (40 if same_time_executions else 20)
        assert current["valuation_price"] == 12.5
        entry = runtime.episode({**account, "episode_id": current["episode_id"]})["entry"]
        assert entry["episode"]["execution_refs"] == ordered_ids[4:]
        assert [item["execution_id"] for item in entry["decisions"]] == ordered_ids[4:]
        quantities = [entry["states_by_ref"][item["state_after_ref"]]["quantity"] for item in entry["decisions"]]
        assert quantities == ([20, 50, 40] if same_time_executions else [20])
        assert runtime.repo.executions("local-user", "ACC-1") == stored
        # Daily observations remain daily facts; no new intraday observation.
        facts = runtime.repo.prices("local-user", "ACC-1")
        assert len(facts) == 5
        assert max(item.date for item in facts).isoformat() == "2025-01-06"
        assert all(pd.Timestamp(item["observed_at"]).hour == 0 for item in entry["price_points"])
    finally:
        runtime.close()


@pytest.mark.parametrize("kind", ["trade", "market"])
def test_commit_rejects_changed_confirmed_file_without_persisting(tmp_path, kind):
    runtime = ProductRuntime(tmp_path / "runtime.db")
    try:
        if kind == "market":
            _import_trades(runtime, trade_params())
        params = trade_params() if kind == "trade" else _market_params()
        original = Path(params["file_path"]).read_bytes()
        changed = original.replace(b"BUY,100,10.00", b"BUY,999,10.00") if kind == "trade" else original.replace(b"equity,10.00", b"equity,99.00")
        assert changed != original
        path = tmp_path / f"{kind}.csv"
        path.write_bytes(original)
        params["file_path"] = str(path)
        preview = getattr(runtime, f"preview_{kind}")(params)
        params["expected_file_sha256"] = preview["batch"]["file_sha256"] if kind == "trade" else preview["file_sha256"]
        params["expected_preview_fingerprint"] = preview["preview_fingerprint"]
        before = list(runtime.repo.connection.iterdump())
        path.write_bytes(changed)
        with pytest.raises(ValueError, match="^file changed after preview$"):
            getattr(runtime, f"commit_{kind}")(params)
        assert list(runtime.repo.connection.iterdump()) == before
    finally:
        runtime.close()


@pytest.mark.parametrize("kind", ["trade", "market"])
def test_commit_hashes_and_parses_one_authoritative_read(tmp_path, monkeypatch, kind):
    from toujing_core_runtime import product

    runtime = ProductRuntime(tmp_path / "runtime.db")
    try:
        if kind == "market":
            _import_trades(runtime, trade_params())
        params = trade_params() if kind == "trade" else _market_params()
        path = Path(params["file_path"])
        original = path.read_bytes()
        changed = original.replace(b"BUY,100,10.00", b"BUY,999,10.00") if kind == "trade" else original.replace(b"equity,10.00", b"equity,99.00")
        preview = getattr(runtime, f"preview_{kind}")(params)
        params["expected_file_sha256"] = preview["batch"]["file_sha256"] if kind == "trade" else preview["file_sha256"]
        params["expected_preview_fingerprint"] = preview["preview_fingerprint"]
        reads = []

        def changing_file(_params):
            reads.append(True)
            return path, original if len(reads) == 1 else changed

        monkeypatch.setattr(product, "_file", changing_file)
        getattr(runtime, f"commit_{kind}")(params)
        if kind == "trade":
            assert runtime.repo.executions("local-user", "ACC-1")[0].executed_quantity == 100
        else:
            assert runtime.repo.prices("local-user", "ACC-1")[0].close == 10
        assert len(reads) == 1
    finally:
        runtime.close()
