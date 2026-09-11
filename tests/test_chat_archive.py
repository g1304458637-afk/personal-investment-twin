import copy
import json
import sqlite3
from concurrent.futures import Future
from threading import Event
from types import SimpleNamespace as NS

import pytest

from test_account_review import account_context
from toujing_core_runtime.account_review import AccountReviewService
from toujing_core_runtime.chat_archive import ChatArchive


def item(scope):
    return {"scope": scope, "source_fingerprint": "fixed", "question": "解释比例", "history": [],
        "result": {"inference_id": "account_inference_x", "scope": scope, "invalidated": False,
                   "replaced_by": None, "answer": {"version": "account_review_answer_v1"}}}


def test_archive_is_separate_private_and_scope_isolated(tmp_path):
    path = tmp_path / "chat.sqlite3"
    a = {"subject_id": "a", "account_id": "one", "data_mode": "real_user", "scope_kind": "account"}
    b = {**a, "subject_id": "b"}
    archive = ChatArchive(path)
    saved = {"account_inference_x": {**item(a), "_desktop_model_key": "MUST_NOT_SAVE"}}
    archive.save(a, saved)
    assert "_desktop_model_key" not in archive.read(a)["account_inference_x"]
    assert ChatArchive(path).read(a)["account_inference_x"]["question"] == "解释比例"
    assert archive.read(b) == {}
    assert path.stat().st_mode & 0o777 == 0o600
    archive.save(b, {"account_inference_x": item(b)})
    archive.drop_account("a", "one")
    assert archive.read(a) == {} and archive.read(b)


def test_archive_rejects_corrupted_scope_and_rolls_back_failed_save(tmp_path):
    archive = ChatArchive(tmp_path / "chat.sqlite3")
    scope = {"subject_id": "a", "account_id": "one"}
    archive.save(scope, {"account_inference_x": item(scope)})
    bad = item(scope)
    bad["question"] = float("nan")
    with pytest.raises(ValueError):
        archive.save(scope, {"account_inference_x": bad})
    assert archive.read(scope)["account_inference_x"]["question"] == "解释比例"
    with sqlite3.connect(archive.path) as connection:
        connection.execute("UPDATE validated_conversations_v1 SET payload=?", (json.dumps({"x": item({})}),))
    with pytest.raises(ValueError, match="invalid"):
        archive.read(scope)


def test_fact_context_cache_is_fingerprint_bound_and_isolates_mutation(monkeypatch, account_context):
    service = AccountReviewService(NS())
    version = ["first"]
    calls = []
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: version[0])
    monkeypatch.setattr(service, "_source", lambda params: (calls.append(1), copy.deepcopy(account_context))[1])
    try:
        first, _ = service._source_with_fingerprint(account_context.scope)
        first.retrieved.add("not_shared")
        first.records.clear()
        second, _ = service._source_with_fingerprint(account_context.scope)
        assert second.records and not second.retrieved and len(calls) == 1
        version[0] = "changed"
        service._source_with_fingerprint(account_context.scope)
        assert len(calls) == 2
        service.drop_account(account_context.subject_id, account_context.account_id)
        assert not service._source_cache
        fingerprints = iter(["before", "after"])
        monkeypatch.setattr(service, "_source_fingerprint", lambda params: next(fingerprints))
        with pytest.raises(ValueError, match="facts_changed"):
            service._source_with_fingerprint(account_context.scope)
        assert not service._source_cache
    finally:
        service.close()


def test_completed_answer_restores_after_restart_without_model_or_facts_mutation(tmp_path, monkeypatch, account_context):
    product = NS(repo=NS(path=tmp_path / "facts.sqlite3"))
    scope = account_context.scope
    service = AccountReviewService(product)
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: "fixed")
    answer = {"version": "account_review_answer_v1", "summary": {"zh": "摘要", "en": "Summary"},
              "findings": [account_context.finding_options[0].public()], "guide_ids": []}
    future = Future()
    future.set_result({"scope": scope, "answer": answer})
    service.jobs["j"] = {"scope": scope, "question": "解释比例", "history": [], "source_params": scope,
        "source_fingerprint": "fixed", "future": future, "cancelled": Event(), "result": None}
    result = service.poll({**scope, "job_id": "j"})["result"]
    assert not result["session_only"]
    service.close()
    restored = AccountReviewService(product)
    try:
        monkeypatch.setattr(restored, "_source_with_fingerprint", lambda params: (copy.copy(account_context), "fixed"))
        view = restored.context(scope)
        assert view["conversation_turns"][0]["result"]["answer"] == answer
        assert not view["conversation_turns"][0]["result"]["invalidated"]
        assert restored._history(result["inference_id"], scope=scope, source_fingerprint="fixed")[0]["user_question"] == "解释比例"
        assert not restored.jobs and not product.repo.path.exists()
        with pytest.raises(ValueError, match="stale"):
            restored._history(result["inference_id"], scope=scope, source_fingerprint="changed")
        monkeypatch.setattr(restored, "_source_with_fingerprint", lambda params: (copy.copy(account_context), "changed"))
        assert restored.context(scope)["conversation_turns"][0]["result"]["invalidated"]
    finally:
        restored.close()
