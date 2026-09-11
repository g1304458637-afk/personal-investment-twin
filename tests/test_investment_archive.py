import pytest

from test_import_confirmation import confirmed
from test_product_runtime import trade_params, _market_params
from toujing_core_runtime.product import ProductRuntime
from src.presentation import investment_archive


def prepared(tmp_path):
    runtime = ProductRuntime(tmp_path / "archive.sqlite3")
    runtime.commit_trade(confirmed(runtime, "trade", trade_params()))
    runtime.commit_market(confirmed(runtime, "market", _market_params()))
    return runtime


def test_archive_results_copy_outcome_once_without_building_paths(tmp_path, monkeypatch):
    runtime = prepared(tmp_path)
    calls = []
    build = investment_archive.build_actual_outcomes
    def recorded(*args, **kwargs):
        result = build(*args, **kwargs)
        calls.append(result)
        return result
    monkeypatch.setattr(investment_archive, "build_actual_outcomes", recorded)
    # ProductRuntime now imports this function lazily; patch its defining module.
    monkeypatch.setattr("src.presentation.runtime_episode.episode_entry", lambda *a, **k: pytest.fail("list built full Episode"))
    try:
        result = runtime.investments(trade_params())
        assert len(calls) == 1
        assert len(result["episodes"]) == 2  # same security, separate closed and re-opened rounds
        outcomes = {item.episode_id: item for item in calls[0].episode_outcomes}
        for row in result["episodes"]:
            summary = row["outcome_summary"]
            outcome = outcomes[row["episode_id"]]
            assert summary["pnl"] == outcome.actual_result.pnl
            assert summary["return_value"] == outcome.actual_result.return_value
            assert summary["outcome_id"] == outcome.outcome_id
            assert summary["source"]["execution_refs"] == list(outcome.actual_result.source.execution_refs)
            assert row["currency"] == "CNY"
            assert summary["result_kind"] == ("marked" if row["status"] == "open" else "realized")
        closed = next(row for row in result["episodes"] if row["status"] == "closed")
        opened = next(row for row in result["episodes"] if row["status"] == "open")
        assert closed["outcome_summary"]["pnl"] == pytest.approx(366)
        assert opened["outcome_summary"]["pnl"] == pytest.approx(-1)
        assert closed["outcome_summary"]["result_at"] == closed["closed_at"]
        assert opened["outcome_summary"]["result_at"] == opened["valuation_at"]
    finally:
        runtime.close()


def test_unavailable_outcome_does_not_invent_a_return_or_hide_lifecycle(tmp_path, monkeypatch):
    runtime = prepared(tmp_path)
    def fail(*args, **kwargs):
        raise ValueError("authoritative record unavailable")
    monkeypatch.setattr(investment_archive, "build_actual_outcomes", fail)
    try:
        rows = runtime.investments(trade_params())["episodes"]
        assert len(rows) == 2
        for row in rows:
            summary = row["outcome_summary"]
            assert summary["result_kind"] == summary["availability"] == "unavailable"
            assert summary["pnl"] is summary["return_value"] is None
            assert "outcome_unavailable" in summary["reason"]
    finally:
        runtime.close()
