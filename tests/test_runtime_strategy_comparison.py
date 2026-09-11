"""Runtime strategy_comparison.get: real import chain, injected market source.

The comparison runs read-only against a temporary account; the akshare fetch
is injected so no network is touched.
"""
from pathlib import Path

import pytest

from src.data import akshare_client
from toujing_core_runtime.product import ProductRuntime

ROOT = Path(__file__).resolve().parents[1]


def _flat_bars(start: str, days: int, close: float) -> list[dict]:
    import pandas as pd
    return [{"date": value.date().isoformat(), "open": close, "high": close,
             "low": close, "close": close} for value in pd.bdate_range(start, periods=days)]


def _import_account(runtime: ProductRuntime) -> str:
    scope = {"subject_id": "local-user", "account_id": "ACC-1"}
    trade = {**scope, "file_path": str(ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"),
             "display_name": "Comparison QA fixture", "source_timezone": "Asia/Shanghai",
             "use_source_row_order_as_sequence": True, "initial_cash": 100000,
             "imported_at": "2026-09-12T00:00:00Z"}
    preview = runtime.preview_trade(trade)
    trade.update(expected_file_sha256=preview["batch"]["file_sha256"],
                 expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
    runtime.commit_trade(trade)
    market = {**scope, "file_path": str(ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv"),
              "source_id": "user_csv", "source_version": "v1", "imported_at": "2026-09-12T00:01:00Z"}
    preview = runtime.preview_market(market)
    market.update(expected_file_sha256=preview["file_sha256"], expected_preview_fingerprint=preview["preview_fingerprint"])
    runtime.commit_market(market)
    return scope


def test_strategy_comparison_returns_available_report_without_touching_records(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "comparison-runtime.sqlite3")
    try:
        _import_account(runtime)
        episodes = runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})["episodes"]
        assert episodes, "fixture must produce at least one episode"
        episode_id = episodes[0]["episode_id"]
        executions_before = runtime.repo.executions("local-user", "ACC-1")

        monkeypatch.setattr(akshare_client, "fetch_ohlc",
                            lambda instrument, start, end, **kwargs: _flat_bars("2024-10-01", 140, 10.0))
        result = runtime.strategy_comparison({"subject_id": "local-user", "account_id": "ACC-1",
                                              "episode_id": episode_id})
        assert result["status"] == "available"
        report = result["report"]
        assert report["instrument"].startswith("inst_v2_")
        assert report["is_synthetic"] is False
        assert len(report["user_executions"]) == len(executions_before)
        assert any("akshare" in item for item in report["limitations"])
        assert any("不会修改任何记录" in item for item in report["limitations"])
        # Flat bars never trigger the breakout entry: the rule side stays flat, honestly.
        assert report["rule_fills"] == []
        # Hand-reconciled recorded-side window net: only executions inside the
        # episode window count (compare excludes the rest with a note).
        from src.core.canonical_execution import canonical_executions_to_frame
        frame = canonical_executions_to_frame(runtime.repo.executions("local-user", "ACC-1"))
        window_start = episodes[0]["opened_at"][:10]
        window_end = (episodes[0]["closed_at"] or "9999-12-31")[:10]
        expected = round(sum((-(float(row["executed_quantity"]) * float(row["executed_price"]) + float(row["fee"])))
                             if row["side"] == "BUY"
                             else (float(row["executed_quantity"]) * float(row["executed_price"]) - float(row["fee"]))
                             for _, row in frame.iterrows()
                             if window_start <= str(row["market_date"])[:10] <= window_end), 6)
        assert abs(report["window_user_net_cash_flow"] - expected) < 1e-6
        # Read-only: nothing changed.
        assert runtime.repo.executions("local-user", "ACC-1") == executions_before
    finally:
        runtime.close()


def test_strategy_comparison_reports_unavailable_when_market_source_fails(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "comparison-runtime-fail.sqlite3")
    try:
        _import_account(runtime)
        episodes = runtime.investments({"subject_id": "local-user", "account_id": "ACC-1"})["episodes"]
        episode_id = episodes[0]["episode_id"]

        def exploding_fetch(instrument, start, end, **kwargs):
            raise akshare_client.AkshareUnavailable("akshare_request_failed")

        monkeypatch.setattr(akshare_client, "fetch_ohlc", exploding_fetch)
        result = runtime.strategy_comparison({"subject_id": "local-user", "account_id": "ACC-1",
                                              "episode_id": episode_id})
        assert result == {"status": "unavailable", "reason": "akshare_request_failed", "report": None}

        result = runtime.strategy_comparison({"subject_id": "local-user", "account_id": "ACC-1",
                                              "episode_id": "pe_does_not_exist"})
        assert result["status"] == "unavailable"
        assert result["reason"] == "episode does not belong to this account"
    finally:
        runtime.close()
