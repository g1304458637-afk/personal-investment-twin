"""Real replay and review boundary tests; no provider/network calls."""
import json
import time
from pathlib import Path

import pandas as pd
import pytest

from src.agents.desktop_demo_source import SOURCES, SAMPLE_ROOT, load_demo_review
from src.data.csv_importer import load_normalized_csv
from toujing_core_runtime.product import ProductRuntime
from toujing_core_runtime import review
from test_decision_review_agent import ScriptedModel, runtime as fake_runtime
from review_option_helpers import choose_options

PAYLOAD = json.loads((Path(__file__).resolve().parents[1] /
    "apps/desktop/src/generated/backend-demo-evidence.json").read_text())


def scope(name):
    entry = next(e for e in PAYLOAD["position_episode_demo"]["entries"]
                 if e["episode"]["subject_id"] == f"demo-user:{name}")
    return {k: entry["episode"][k] for k in ("subject_id", "account_id", "episode_id")} | {"data_mode": "synthetic_episode"}, entry


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.name)
def test_qualified_identity_preserves_display_results_and_execution_facts(source):
    params, entry = scope(source.name)
    own, frame, market, mapping = load_demo_review(*(params[k] for k in ("subject_id", "account_id", "episode_id")))
    original = load_normalized_csv(SAMPLE_ROOT / source.executions)
    pd.testing.assert_frame_equal(frame[original.columns].drop(columns="symbol"), original.drop(columns="symbol"))
    assert frame.symbol.eq(own.instrument.instrument_id).all()
    assert market.instrument.eq(own.instrument.instrument_id).all()
    assert own.episode.instrument_id == own.instrument.instrument_id
    assert own.episode.execution_refs == tuple(entry["episode"]["execution_refs"])
    expected = entry["outcome_story"]["episode_outcome"]["actual_result"]
    for name in ("pnl", "return_value", "recorded_entry_fees", "recorded_exit_fees", "result_kind"):
        assert getattr(own.outcome.actual_result, name) == expected[name]
    assert mapping["display_episode_id"] == params["episode_id"]
    assert mapping["canonical_episode_id"] == own.episode.episode_id
    assert set(mapping["decision_display_ids"].values()) == set(entry["episode"]["decision_refs"])


def test_demo_review_job_uses_this_episode_and_preserves_scope_and_consent(tmp_path, monkeypatch):
    params, _ = scope("product-story")
    product = ProductRuntime(tmp_path / "review.sqlite3")
    try:
        service = product.review_runtime()
        first = service.context(params)
        assert first == service.context(params)
        assert first["data_tier"] == "synthetic"
        assert all(r["account_id"] == params["account_id"] for r in first["records"])
        fact = next(r for r in first["records"] if r["kind"] == "episode")
        assert fact["value"]["result"]["pnl"] == -283.5
        assert first["identity_mapping"]["display_episode_id"] == params["episode_id"]
        with pytest.raises(ValueError, match="consent"):
            service.start(params | {"question": "分析这轮投资"})
        model = ScriptedModel([("get_episode_facts", {}),
            ("search_review_facts", {"stance": "support", "topic": "all"}),
            ("search_review_facts", {"stance": "contradict", "topic": "all"}),
            ("get_registered_historical_comparisons", {}), ("get_self_history", {}),
            "候选分析", choose_options("unknown")])
        monkeypatch.setattr(review, "create_model_runtime", lambda: fake_runtime(model))
        job = service.start(params | {"question": "这轮怎么投的？", "allow_model_review": True})
        for _ in range(500):
            result = service.poll(params | job)
            if result["status"] != "running":
                break
            time.sleep(.01)
        assert result["status"] == "complete", result
        assert result["result"]["executed_tools"]
        with pytest.raises(ValueError, match="not_owned"):
            service.poll(params | job | {"episode_id": "unread-episode"})
        assert product.repo.list_accounts() == []
    finally:
        product.close()


@pytest.mark.parametrize("change", [{"subject_id": "someone-else"}, {"account_id": "other"},
    {"episode_id": "other"}, {"share_id": "not-authorized"}, {"compare_pair": True}])
def test_unregistered_or_cross_scope_demo_fails_closed(tmp_path, change):
    params, _ = scope("product-story")
    product = ProductRuntime(tmp_path / "review.sqlite3")
    try:
        with pytest.raises(ValueError):
            product.review_runtime().context(params | change)
    finally:
        product.close()
