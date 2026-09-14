"""Protocol-level integration for review_pack.get and episode_tags.set."""
from __future__ import annotations

from pathlib import Path

from tests.test_product_runtime import prices_file, trade_params
from toujing_core_runtime.protocol import _product_methods, handle_request


def _request(method: str, params: object) -> dict[str, object]:
    return {"protocol_version": "1", "request_id": "req-1", "method": method, "params": params}


def _import_account_with_episode(tmp_path: Path, methods) -> str:
    trade = dict(trade_params())
    trade["file_path"] = str(trade["file_path"])
    preview = handle_request(_request("ingestion.preview_trade_csv", trade), methods)[0]["result"]
    trade["expected_file_sha256"] = preview["batch"]["file_sha256"]
    trade["expected_preview_fingerprint"] = preview["preview_fingerprint"]
    handle_request(_request("ingestion.commit_trade_import", {**trade, "duplicate_choices": {}}), methods)
    market = {"file_path": str(prices_file(tmp_path)), "subject_id": "local-user",
              "account_id": "ACC-1", "source_id": "user_csv", "source_version": "v1",
              "imported_at": "2026-09-04T12:01:00Z"}
    market_preview = handle_request(_request("market.preview_price_csv", market), methods)[0]["result"]
    market["expected_file_sha256"] = market_preview["file_sha256"]
    market["expected_preview_fingerprint"] = market_preview["preview_fingerprint"]
    handle_request(_request("market.commit_price_import", market), methods)
    investments = handle_request(
        _request("investments.list", {"subject_id": "local-user", "account_id": "ACC-1"}), methods)[0]["result"]
    return investments["episodes"][0]["episode_id"]


def test_review_pack_and_episode_tags_through_protocol(tmp_path):
    methods, product = _product_methods(str(tmp_path / "db.sqlite3"))
    try:
        episode_id = _import_account_with_episode(tmp_path, methods)

        response, _ = handle_request(_request(
            "review_pack.get", {"subject_id": "local-user", "account_id": "ACC-1"}), methods)
        assert response["error"] is None
        pack = response["result"]
        assert pack["schema_version"] == "review_pack.v1"
        assert pack["coverage"]["execution_count"] == 5
        assert any(item["episode_id"] == episode_id for item in pack["exit_quality"]["episodes"])

        response, _ = handle_request(_request("episode_tags.set", {
            "subject_id": "local-user", "account_id": "ACC-1", "episode_id": episode_id,
            "tags": ["  按计划执行 ", "按计划执行", "", "突破"]}), methods)
        assert response["error"] is None
        assert response["result"]["tags"] == ["按计划执行", "突破"]

        pack = handle_request(_request(
            "review_pack.get", {"subject_id": "local-user", "account_id": "ACC-1"}), methods)[0]["result"]
        stored = next(item for item in pack["episode_tags"] if item["episode_id"] == episode_id)
        assert stored["tags"] == ["按计划执行", "突破"]

        # Tags on an episode of a different account must not pass ownership.
        response, _ = handle_request(_request("episode_tags.set", {
            "subject_id": "local-user", "account_id": "OTHER", "episode_id": episode_id,
            "tags": ["x"]}), methods)
        assert response["error"] is not None

        bad = handle_request(_request("episode_tags.set", {
            "subject_id": "local-user", "account_id": "ACC-1", "episode_id": episode_id,
            "tags": "breakout"}), methods)
        assert bad[0]["error"] is not None
    finally:
        product.close()


def test_review_pack_unknown_account_fails_cleanly(tmp_path):
    methods, product = _product_methods(str(tmp_path / "db.sqlite3"))
    try:
        response, _ = handle_request(_request(
            "review_pack.get", {"subject_id": "nobody", "account_id": "NONE"}), methods)
        assert response["error"] is not None
    finally:
        product.close()
