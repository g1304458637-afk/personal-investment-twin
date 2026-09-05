from pathlib import Path

import pytest

from toujing_core_runtime.product import ProductRuntime
from test_product_runtime import trade_params, _market_params, _import_trades, ROOT


def confirmed(runtime, kind, params):
    preview = getattr(runtime, f"preview_{kind}")(params)
    return {**params,
        "expected_file_sha256": preview["batch"]["file_sha256"] if kind == "trade" else preview["file_sha256"],
        "expected_preview_fingerprint": preview.get("preview_fingerprint", "missing-in-old-runtime")}


@pytest.mark.parametrize("field,value", [
    ("subject_id", "different-subject"), ("source_timezone", "UTC"),
    ("use_source_row_order_as_sequence", False), ("initial_cash", 200000),
    ("resolution_symbol", "ABC"), ("resolution_market", "XNAS"),
    ("column_mapping", {"executed_quantity": "price"}),
])
def test_changed_trade_preview_configuration_fails_closed(tmp_path, field, value):
    runtime = ProductRuntime(tmp_path / "db")
    try:
        params = confirmed(runtime, "trade", trade_params())
        before = list(runtime.repo.connection.iterdump())
        params[field] = value
        with pytest.raises(ValueError, match="preview.*changed|fingerprint"):
            runtime.commit_trade(params)
        assert list(runtime.repo.connection.iterdump()) == before
    finally:
        runtime.close()


@pytest.mark.parametrize("field,value", [("source_id", "different"), ("source_version", "v2"), ("subject_id", "other")])
def test_changed_market_preview_configuration_fails_closed(tmp_path, field, value):
    runtime = ProductRuntime(tmp_path / "db")
    try:
        _import_trades(runtime, trade_params())
        params = confirmed(runtime, "market", _market_params())
        before = list(runtime.repo.connection.iterdump())
        params[field] = value
        with pytest.raises(ValueError, match="preview.*changed|fingerprint"):
            runtime.commit_market(params)
        assert list(runtime.repo.connection.iterdump()) == before
    finally:
        runtime.close()


def test_unresolved_resolution_preserves_original_execution_and_survives_restart(tmp_path):
    db = tmp_path / "db"
    runtime = ProductRuntime(db)
    params = {**trade_params(), "file_path": str(ROOT / "tests/fixtures/ingestion/fixture_f_ambiguous_instrument.csv")}
    try:
        runtime.commit_trade(confirmed(runtime, "trade", params))
        original = runtime.repo.connection.execute("SELECT execution_id,payload_json FROM canonical_executions").fetchone()
        resolved = {**params, "resolution_symbol": "ABC", "resolution_market": "XNAS", "resolution_security_type": "equity"}
        preview = runtime.preview_trade(resolved)
        assert preview["rows"][0]["status"] == "instrument_resolution"
        result = runtime.commit_trade(confirmed(runtime, "trade", resolved))
        assert result["inserted_executions"] == 0
        assert result["resolved_executions"] == 1
        assert tuple(runtime.repo.connection.execute("SELECT execution_id,payload_json FROM canonical_executions").fetchone()) == tuple(original)
        facts = runtime.repo.executions(params["subject_id"], params["account_id"])
        assert len(facts) == 1
        assert facts[0].execution_id == original[0]
        assert facts[0].instrument.market == "XNAS"
        runtime.close()
        runtime = ProductRuntime(db)
        assert runtime.repo.executions(params["subject_id"], params["account_id"]) == facts
        repeat = runtime.commit_trade(confirmed(runtime, "trade", resolved))
        assert repeat["inserted_executions"] == repeat["resolved_executions"] == 0
        assert runtime.repo.connection.execute("SELECT COUNT(*) FROM execution_instrument_resolutions").fetchone()[0] == 1
    finally:
        runtime.close()
