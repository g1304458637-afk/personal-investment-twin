"""Use the real import/replay/RPC chain with a temporary account, never user data."""
from pathlib import Path

from toujing_core_runtime.product import ProductRuntime
from src.presentation import runtime_episode

ROOT = Path(__file__).resolve().parents[1]


def test_real_episode_projection_is_additive_and_lens_failure_preserves_finance(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "lens-runtime.sqlite3")
    scope = {"subject_id": "local-user", "account_id": "ACC-1"}
    try:
        trade = {**scope, "file_path": str(ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"),
                 "display_name": "Lens QA fixture", "source_timezone": "Asia/Shanghai",
                 "use_source_row_order_as_sequence": True, "initial_cash": 100000,
                 "imported_at": "2026-09-11T00:00:00Z"}
        preview = runtime.preview_trade(trade)
        trade.update(expected_file_sha256=preview["batch"]["file_sha256"],
                     expected_preview_fingerprint=preview["preview_fingerprint"], duplicate_choices={})
        runtime.commit_trade(trade)
        market = {**scope, "file_path": str(ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv"),
                  "source_id": "user_csv", "source_version": "v1", "imported_at": "2026-09-11T00:01:00Z"}
        preview = runtime.preview_market(market)
        market.update(expected_file_sha256=preview["file_sha256"], expected_preview_fingerprint=preview["preview_fingerprint"])
        runtime.commit_market(market)
        account_before = runtime.investments(scope)
        executions_before = runtime.repo.executions("local-user", "ACC-1")
        request = {**scope, "episode_id": account_before["episodes"][0]["episode_id"]}
        first = runtime.episode(request)
        assert first["status"] == "available"
        entry = first["entry"]
        lens = entry["lens_review"]
        assert lens["schema_version"] == "decision_lens.v1"
        assert lens["data_tier"] == "authorized_beta"
        for method in lens["methods"]:
            assert len(method["checks"]) == len(entry["decisions"])
            for check in method["checks"]:
                decision = next(d for d in entry["decisions"] if d["decision_id"] == check["decision_id"])
                state = entry["states_by_ref"][decision["state_before_ref"]]
                assert check["actual"]["price"] == decision["execution_price"]
                assert check["actual"]["quantity_before"] == state["quantity"]
                assert check["market_date"] is not None
                if check["observed_through"] is not None:
                    assert check["observed_through"] < check["market_date"]
        # No 20-observation template pretends five fixture days form a full window.
        assert all(c["verdict"] == "insufficient" for c in lens["methods"][0]["checks"])
        assert any(c["verdict"] in {"aligned", "different"} for c in lens["methods"][2]["checks"])

        def unsupported_projection(*args, **kwargs):
            raise ValueError("deliberately unsupported optional metadata")

        monkeypatch.setattr(runtime_episode, "evaluate_episode_lenses", unsupported_projection)
        second = runtime.episode(request)
        assert second["status"] == "available"
        assert second["entry"]["lens_review"]["status"] == "unavailable"
        assert {k: v for k, v in second["entry"].items() if k != "lens_review"} == {
            k: v for k, v in entry.items() if k != "lens_review"}
        assert runtime.repo.executions("local-user", "ACC-1") == executions_before
        assert runtime.investments(scope) == account_before
    finally:
        runtime.close()
