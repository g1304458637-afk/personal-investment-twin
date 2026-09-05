"""RPC integration uses real deterministic engines and an offline SDK model."""

import time

import pytest

from test_product_runtime import _import_trades, _market_params, trade_params
from test_decision_review_agent import ScriptedModel, runtime as fake_runtime, selection
from toujing_core_runtime.product import ProductRuntime
from toujing_core_runtime import review


@pytest.fixture
def product(tmp_path):
    instance = ProductRuntime(tmp_path / "review.sqlite3")
    _import_trades(instance, trade_params())
    market = _market_params()
    preview = instance.preview_market(market)
    instance.commit_market(market | {"expected_file_sha256": preview["file_sha256"],
                                   "expected_preview_fingerprint": preview["preview_fingerprint"]})
    yield instance
    instance.close()


def scope(product):
    account = {"subject_id": "local-user", "account_id": "ACC-1"}
    episode = product.investments(account)["episodes"][0]
    return account | {"episode_id": episode["episode_id"]}


def test_real_context_copies_owned_results_and_registered_comparisons(product):
    params = scope(product)
    result = product.review_runtime().context(params)
    assert result["data_tier"] == "authorized_beta"
    episode = next(r for r in result["records"] if r["kind"] == "episode")
    actual = product.episode(params)["entry"]["outcome_story"]["episode_outcome"]["actual_result"]
    assert episode["value"]["result"] == actual
    assert all(r["account_id"] == "ACC-1" for r in result["records"])
    assert any(r["kind"] == "historical_comparison" for r in result["records"])
    with pytest.raises(ValueError):
        product.review_runtime().context(params | {"account_id": "OTHER"})


def test_share_export_import_permission_revocation_and_no_raw_file(product, tmp_path):
    params = scope(product)
    service = product.review_runtime()
    target = tmp_path / "episode.toujing-share.json"
    result = service.export_share(params | {"recipient_subject_id": "local-user", "recipient_account_id": "ACC-1",
        "owner_confirmed": True, "allow_agent_review": False, "expires_at": "2099-01-01T00:00:00Z", "file_path": str(target)})
    assert result["signer_fingerprint"] not in target.read_text()
    imported = service.import_share(params | {"trusted_sender_fingerprint": result["signer_fingerprint"], "file_path": str(target)})
    shared_params = params | {"share_id": imported["share_id"]}
    assert service.context(shared_params)["comparison"]["status"] != "unavailable"
    with pytest.raises(ValueError, match="agent"):
        service._context(shared_params, for_agent=True)
    with pytest.raises(FileExistsError):
        service.export_share(params | {"recipient_subject_id": "local-user", "recipient_account_id": "ACC-1",
            "owner_confirmed": True, "expires_at": "2099-01-01T00:00:00Z", "file_path": str(target)})
    service.revoke_share(shared_params)
    with pytest.raises(ValueError, match="authorized"):
        service.context(shared_params)


def test_native_agent_job_scope_notes_invalidate_and_never_write_financial_facts(product, monkeypatch):
    params = scope(product)
    service = product.review_runtime()
    context, _, _ = service._context(params)
    model = ScriptedModel([("get_episode_facts", {}), ("search_review_facts", {"stance": "support", "topic": "all"}),
                           ("search_review_facts", {"stance": "contradict", "topic": "all"}),
                           ("get_registered_historical_comparisons", {}), ("get_self_history", {}), selection(context), selection(context)])
    monkeypatch.setattr(review, "create_model_runtime", lambda: fake_runtime(model))
    before = product.repo.executions("local-user", "ACC-1")
    with pytest.raises(ValueError, match="consent"):
        service.start(params | {"question": "这轮怎么投的？"})
    job = service.start(params | {"question": "这轮怎么投的？", "allow_model_review": True})
    for _ in range(200):
        result = service.poll(params | job)
        if result["status"] != "running":
            break
        time.sleep(.01)
    assert result["status"] == "complete", result
    assert result["result"]["generated_at"]
    with pytest.raises(ValueError, match="not_owned"):
        service.poll(params | job | {"account_id": "OTHER"})
    note = service.add_note(params | {"text": "这是原先的分批计划（事后补记）", "note_kind": "plan"})["note"]
    assert note["temporal_kind"] == "retrospective"
    assert service.poll(params | job)["status"] == "stale"
    assert service.context(params)["inferences"][0]["invalidated"] is True
    assert product.repo.executions("local-user", "ACC-1") == before


def test_no_synthetic_fallback_and_unknown_episode_rejected(product):
    service = product.review_runtime()
    params = scope(product)
    with pytest.raises(ValueError, match="episode"):
        service.context(params | {"episode_id": "arbitrary"})
    with pytest.raises(ValueError, match="scope"):
        service.context(params | {"data_mode": "synthetic_pair"})


def test_changed_canonical_facts_cannot_publish_old_model_result(product, monkeypatch):
    from concurrent.futures import Future
    from threading import Event
    service, params = product.review_runtime(), scope(product)
    identity = tuple(params[k] for k in ("subject_id", "account_id", "episode_id"))
    completed = Future()
    completed.set_result({"scope": params})
    service.jobs["old"] = {"scope": identity, "future": completed, "cancelled": Event(),
        "note_fingerprint": service.store.note_fingerprint(*identity), "source_params": params,
        "source_fingerprint": service._source_fingerprint(params), "share_id": None, "result": None}
    monkeypatch.setattr(service, "_source_fingerprint", lambda p: "new-canonical-input-version")
    assert service.poll(params | {"job_id": "old"}) == {"status": "stale", "reason": "account_facts_changed", "result": None}
    assert not service.store.inferences(*identity)


def test_unregistered_counterfactual_cannot_enter_agent_catalog(product):
    from src.agents.review_catalog import build_review_catalog
    service, params = product.review_runtime(), scope(product)
    own, _, _, _ = service._own(params)
    with pytest.raises(ValueError, match="unregistered"):
        build_review_catalog(own, counterfactuals=({"scenario_id": "copy_counterpart_perfect_trades"},))
