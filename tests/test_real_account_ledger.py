from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
import sqlite3

import pytest

from src.core.canonical_execution import instrument_ref
from src.ledger.contracts import event, opening
from src.ledger.engine import project
from src.market_data.models import HistoricalPriceFact
from toujing_core_runtime.product import ProductRuntime

SCOPE = {"subject_id": "owner", "account_id": "account"}
OPEN = {"opening_date": "2025-01-01", "currency": "CNY", "initial_cash": "10000", "display_name": "账户", "source_ref": "statement-opening"}
SEC = {"symbol": "600000", "market": "XSHG", "security_type": "equity", "currency": "CNY"}


def row(kind, identifier, day="2025-01-01", **values):
    return {**SEC, "event_id": identifier, "event_type": kind, "effective_date": day, "source_ref": "broker:"+identifier, **values}


def quote(day, value, symbol="600000", basis="unadjusted_close"):
    return HistoricalPriceFact(observation_id=f"{symbol}:{day}:{basis}", instrument=instrument_ref(local_symbol=symbol,
        market="XSHG", security_type="equity", currency="CNY"), date=date.fromisoformat(day), close=value,
        price_type=basis, currency="CNY", source_id="fixture", source_tier="user_provided", source_version="1",
        imported_at="2025-02-01T00:00:00Z", source_file_sha256="fixture", source_row_identity=day)


def fold(rows, prices=(), **kw):
    return project({**opening(OPEN), **SCOPE}, [event(x, "CNY") for x in rows], (), prices, **kw)


def commit(runtime, mode, **values):
    params = {**SCOPE, "mode": mode, **values}
    preview = runtime.ledger_runtime().preview(params)
    assert not preview["issues"], preview
    return runtime.ledger_runtime().commit({**params, "expected_preview_fingerprint": preview["preview_fingerprint"],
        "expected_file_sha256": preview["file_sha256"]})


INITIAL = row("opening_position", "open", quantity="100", cost_basis="1000", opening_price="12")


def test_opening_position_does_not_consume_cash_and_keeps_two_pnl_bases():
    result = fold([INITIAL], [quote("2025-01-02", 13)])
    assert result["cash"] == "10000" and result["opening_equity"] == "11200"
    assert result["positions"][0]["unrealized_pnl"] == "300"
    assert result["period_pnl"] == "100"
    assert result["episodes"][0]["origin"] == "opening_position"


def test_cash_flows_and_corporate_actions_conserve_capital():
    rows = [INITIAL, row("split", "split", "2025-01-02", ratio="2"),
        row("cash_dividend", "div", "2025-01-05", ex_date="2025-01-03", amount="100", tax="10"),
        row("deposit", "in", "2025-01-04", amount="5000"),
        row("withdrawal", "out", "2025-01-05", amount="1000")]
    prices = [quote("2025-01-02", 6), quote("2025-01-03", 5.5), quote("2025-01-05", 5.5)]
    before_pay = fold(rows, prices, as_of="2025-01-04")
    assert before_pay["cash"] == "15000" and before_pay["receivables"] == "100"
    after = fold(rows, prices, as_of="2025-01-05")
    assert after["cash"] == "14090" and after["receivables"] == "0"
    assert after["equity"] == "15190" and after["net_contributions"] == "4000"
    assert after["period_pnl"] == "-10" and after["positions"][0]["quantity"] == "200"
    assert after["positions"][0]["cost_basis"] == "1000"


def test_rights_payment_is_pending_asset_until_delivery():
    rows = [INITIAL, row("rights_subscription", "pay", "2025-01-02", amount="200"),
        row("rights_delivery", "credit", "2025-01-04", quantity="40", subscription_id="pay")]
    result = fold(rows, [quote("2025-01-02", 12)], as_of="2025-01-03")
    assert result["cash"] == "9800" and result["receivables"] == "200"
    assert result["equity"] == "11200"
    result = fold(rows, [quote("2025-01-04", 10)], as_of="2025-01-04")
    assert result["receivables"] == "0" and result["positions"][0]["cost_basis"] == "1200"
    assert result["positions"][0]["quantity"] == "140" and result["equity"] == "11200"


def test_split_requires_post_action_raw_mark_never_reuses_pre_split_price():
    result = fold([INITIAL, row("split", "split", "2025-01-02", ratio="2")], [quote("2025-01-01", 12)])
    assert result["equity"] is None and result["market_value"] is None
    adjusted_only = fold([INITIAL], [quote("2025-01-02", 999, basis="adjusted_close")])
    assert adjusted_only["positions"][0]["price"] == "12"
    assert adjusted_only["positions"][0]["price_date"] == "2025-01-01"


@pytest.mark.parametrize("bad", [True, "NaN", "Infinity", "-1", "1e100"])
def test_invalid_amounts_fail_closed(bad):
    with pytest.raises(ValueError):
        event(row("deposit", "bad", amount=bad), "CNY")


def test_exchange_carries_cost_and_cash_settlement_without_fake_sell():
    exchange = row("security_exchange", "merge", "2025-01-02", quantity="50", amount="100", cash_cost_basis="80",
        new_symbol="600001", new_market="XSHG", new_security_type="equity")
    result = fold([INITIAL, exchange], [quote("2025-01-02", 22, symbol="600001")])
    assert result["cash"] == "10100" and result["positions"][0]["cost_basis"] == "920"
    assert result["realized_trading_pnl"] == "20" and len(result["episodes"]) == 2
    assert result["episodes"][1]["origin"] == "security_exchange"


def test_delisting_uses_actual_settlement_and_capital_return_reduces_basis():
    result = fold([INITIAL, row("return_of_capital", "capital", "2025-01-02", amount="100"),
        row("delisting", "delist", "2025-01-03", amount="700")])
    assert result["positions"] == [] and result["cash"] == "10800"
    assert result["realized_trading_pnl"] == "-200"
    assert result["period_pnl"] == "-400"


def test_runtime_preview_immutable_events_stale_binding_reconciliation_and_restart(tmp_path):
    db = tmp_path / "accounts.sqlite3"
    runtime = ProductRuntime(db)
    commit(runtime, "opening", opening=OPEN, records=[INITIAL])
    commit(runtime, "events", records=[row("deposit", "deposit", "2025-01-02", amount="500")])
    state = runtime.ledger_runtime().get(SCOPE)
    assert state["snapshot"]["cash"] == "10500"
    duplicate = runtime.ledger_runtime().preview({**SCOPE, "mode": "events", "records": [row("deposit", "deposit", "2025-01-02", amount="500")]})
    assert duplicate["duplicates"] == 1 and not duplicate["new_events"]
    conflict = runtime.ledger_runtime().preview({**SCOPE, "mode": "events", "records": [row("deposit", "deposit", "2025-01-02", amount="600")]})
    assert conflict["issues"]
    params = {**SCOPE, "mode": "events", "records": [row("withdrawal", "withdraw", "2025-01-03", amount="100")]}
    preview = runtime.ledger_runtime().preview(params)
    commit(runtime, "events", records=[row("interest", "interest", "2025-01-03", amount="10")])
    with pytest.raises(ValueError, match="失效"):
        runtime.ledger_runtime().commit({**params, "expected_preview_fingerprint": preview["preview_fingerprint"]})
    statement = {"statement_id": "stmt", "source_ref": "broker-statement", "as_of": "2025-01-03", "currency": "CNY",
        "positions_complete": True, "cash": "10510", "positions": [{**SEC, "quantity": "100", "cost_basis": "1000"}]}
    commit(runtime, "statement", statement=statement)
    assert runtime.ledger_runtime().get(SCOPE)["reconciliations"][0]["report"]["status"] == "matched"
    commit(runtime, "void", target_event_id="deposit", reason="券商确认重复")
    assert runtime.ledger_runtime().get(SCOPE)["snapshot"]["cash"] == "10010"
    assert runtime.ledger_runtime().get(SCOPE)["reconciliations"][0]["stale"] is True
    expected = runtime.ledger_runtime().get(SCOPE)
    runtime.close()
    runtime = ProductRuntime(db)
    assert runtime.ledger_runtime().get(SCOPE) == expected
    assert not runtime.ledger_runtime().get({"subject_id": "other", "account_id": "account"})["enabled"]
    runtime.close()


def test_v2_migration_backs_up_wal_and_keeps_account(tmp_path):
    from src.persistence.repository import LocalRepository, _MIGRATION_1, _MIGRATION_2
    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(_MIGRATION_1 + _MIGRATION_2 + "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT); PRAGMA user_version=2;")
    db.execute("INSERT INTO accounts VALUES('owner','account','before',100,'then','then')")
    db.commit()
    repo = LocalRepository(path)
    assert repo.connection.execute("PRAGMA user_version").fetchone()[0] == 3
    assert repo.list_accounts()[0]["display_name"] == "before"
    backups = list((tmp_path/"backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 2
        assert backup.execute("SELECT display_name FROM accounts").fetchone()[0] == "before"
    repo.close()
    db.close()
