"""The shipped ReviewPack is derived from the annual showcase account."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_showcase_review_pack_demo import _commit_showcase, export_bytes
from src.demo import showcase
from src.demo.showcase_runtime import _episode_mapping, source_fingerprint
from src.persistence import LocalRepository
from src.review_pack import build_review_pack

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def payload():
    return json.loads(export_bytes())


def test_showcase_pack_owner_source_and_episode_set_match_annual_demo(payload):
    annual = json.loads((ROOT / "apps/desktop/src/generated/showcase-demo.json").read_text())
    assert (payload["subject_id"], payload["account_id"]) == (
        annual["showcase"]["subject_id"], annual["showcase"]["account_id"])
    assert payload["data_tier"] == "synthetic"
    assert payload["source_fingerprint"] == annual["showcase"]["input_sha256"]
    assert payload["source_fingerprint"] == source_fingerprint(showcase.SUBJECT_ID, showcase.ACCOUNT_ID)
    assert payload["coverage"]["execution_count"] == annual["showcase"]["execution_count"] == 20
    assert payload["coverage"]["episode_count"] == len(annual["position_episode_demo"]["entries"]) == 5
    closed = {entry["episode"]["episode_id"]: entry for entry in annual["position_episode_demo"]["entries"]
              if entry["episode"]["status"] == "closed"}
    pack_rows = {row["episode_id"]: row for row in payload["exit_quality"]["episodes"]}
    assert set(pack_rows) == set(closed)
    for episode_id, row in pack_rows.items():
        assert row["instrument"] == closed[episode_id]["episode"]["instrument_id"]
        assert row["realized_pnl"] == pytest.approx(
            closed[episode_id]["outcome_story"]["episode_outcome"]["actual_result"]["pnl"])
        assert row["mfe_amount"] is not None and row["mae_amount"] is not None


def test_canonical_to_display_ids_are_ref_verified_and_finances_rebuild(payload, tmp_path):
    identity, _, _, _ = _episode_mapping(showcase.SUBJECT_ID)
    mappings = {item["display_episode_id"]: item for item in payload["episode_identity_mapping"]}
    assert set(mappings) == {row["episode_id"] for row in payload["exit_quality"]["episodes"]}
    repo = LocalRepository(tmp_path / "showcase.sqlite3")
    try:
        _commit_showcase(repo)
        rebuilt = build_review_pack(repo, showcase.SUBJECT_ID, showcase.ACCOUNT_ID)
    finally:
        repo.close()
    canonical_rows = {row["episode_id"]: row for row in rebuilt["exit_quality"]["episodes"]}
    for display_id, item in mappings.items():
        canonical_id = item["canonical_episode_id"]
        assert identity[canonical_id]["display_episode_id"] == display_id
        assert identity[display_id]["canonical_episode_id"] == canonical_id
        assert canonical_rows[canonical_id]["instrument"] == item["canonical_instrument_id"]
        display = next(row for row in payload["exit_quality"]["episodes"] if row["episode_id"] == display_id)
        for field in ("realized_pnl", "mfe_amount", "mae_amount", "mfe_pct", "mae_pct",
                      "exit_efficiency", "giveback_ratio", "hold_baseline_pnl", "hold_baseline_delta"):
            assert display[field] == pytest.approx(canonical_rows[canonical_id][field])
    assert payload["calendar"] == rebuilt["calendar"] | {
        "limitations": [*rebuilt["calendar"]["limitations"], payload["calendar"]["limitations"][-1]]}


def test_showcase_review_pack_export_is_byte_stable_and_legacy_fixture_is_preserved():
    path = ROOT / "apps/desktop/src/generated/showcase-review-pack-demo.json"
    assert path.read_bytes() == export_bytes()
    older = json.loads((ROOT / "apps/desktop/src/generated/review-pack-demo.json").read_text())
    assert older["account_id"] == "review_demo"
    assert len(older["exit_quality"]["episodes"]) == 13
