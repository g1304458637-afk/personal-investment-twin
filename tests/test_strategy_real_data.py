"""run_custom own_account mode: user strategies on the instruments they
actually traded, with injected real-market bars (no network)."""
from pathlib import Path

from src.data import akshare_client
from toujing_core_runtime.product import ProductRuntime
from toujing_core_runtime.protocol import _product_methods

ROOT = Path(__file__).resolve().parents[1]


def _flat_bars(start: str, days: int, close: float) -> list[dict]:
    import pandas as pd
    return [{"date": v.date().isoformat(), "open": close, "high": close,
             "low": close, "close": close} for v in pd.bdate_range(start, periods=days)]


def _import_account(runtime) -> dict:
    scope = {"subject_id": "local-user", "account_id": "ACC-1"}
    trade = {**scope, "file_path": str(ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"),
             "display_name": "Workshop QA", "source_timezone": "Asia/Shanghai",
             "use_source_row_order_as_sequence": True, "initial_cash": 100000,
             "imported_at": "2026-09-12T00:00:00Z"}
    preview = runtime.preview_trade(trade)
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"],
                 expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
    runtime.commit_trade(trade)
    return scope


VALID_SPEC = {
    "schema_version": "user_strategy.v1", "name": "真实行情冒烟",
    "entry": {"all_of": [{"factor": "breakout_high", "params": {"window": 20}, "op": "true"}]},
    "exit": {"any_of": [{"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}],
             "stop_loss_pct": 0.1},
    "sizing": {"mode": "equal_weight", "fraction": 0.25},
    "constraints": {"max_positions": 4},
}


def test_own_account_mode_runs_on_real_instrument_bars(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "ws.sqlite3")
    try:
        _import_account(runtime)
        fetched = []
        def fake_fetch(instrument, start, end, **kwargs):
            fetched.append((instrument, kwargs.get("adjust")))
            import pandas as pd
            all_days = [v.date().isoformat() for v in pd.bdate_range("2024-10-01", periods=160)]
            out = [{"date": d, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0}
                   for d in all_days[:60]]
            out += [{"date": d, "open": 10.0 + 0.08 * i, "high": 10.0 + 0.08 * (i + 1) + 0.1,
                     "low": 10.0 + 0.08 * i - 0.05, "close": 10.0 + 0.08 * (i + 1)}
                    for i, d in enumerate(all_days[60:])]
            return out
        monkeypatch.setattr(akshare_client, "fetch_ohlc", fake_fetch)
        result = runtime.strategy_simulation_run_custom({
            "strategy": VALID_SPEC,
            "universe": "own_account",
            "subject_id": "local-user", "account_id": "ACC-1",
        })
        assert result["status"] == "available", (result["reason"], result)
        artifact = result["artifact"]
        assert artifact["summary"]["fill_count"] > 0, "the ramp must produce at least one breakout entry"
        assert fetched and fetched[0][1] == "hfq"
        limitations = "\n".join(artifact["limitations"])
        assert "真实交易过" in limitations and "后复权" in limitations and "幸存者偏差" in limitations
    finally:
        runtime.close()


def test_own_account_reports_unavailable_when_no_instrument_loads(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "ws-fail.sqlite3")
    try:
        _import_account(runtime)
        def failing_fetch(instrument, start, end, **kwargs):
            raise akshare_client.AkshareUnavailable("unsupported_instrument_suffix")
        monkeypatch.setattr(akshare_client, "fetch_ohlc", failing_fetch)
        result = runtime.strategy_simulation_run_custom({
            "strategy": VALID_SPEC, "universe": "own_account",
            "subject_id": "local-user", "account_id": "ACC-1",
        })
        assert result["status"] == "unavailable"
        assert result["reason"] == "no_real_instruments_could_be_loaded"
    finally:
        runtime.close()


def test_own_account_requires_account_identifiers(tmp_path):
    runtime = ProductRuntime(tmp_path / "ws-noacc.sqlite3")
    try:
        result = runtime.strategy_simulation_run_custom({
            "strategy": VALID_SPEC, "universe": "own_account",
        })
        assert result["reason"] == "own_account_requires_account"
    finally:
        runtime.close()
