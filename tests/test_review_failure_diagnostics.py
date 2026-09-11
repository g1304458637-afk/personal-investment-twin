import asyncio
import json
import sqlite3
from concurrent.futures import Future
from threading import Event
from types import SimpleNamespace

import pytest

from src.agents.claim_contract import ReviewVerificationError
from src.agents.review_diagnostics import diagnosed, mark, persist_failure, safe_failure, failure_reason
from src.agents.structured_finalizer import StructuredFinalizationUnavailable
from toujing_core_runtime.review import ReviewRuntime


def test_metadata_is_allowlisted_not_model_or_exception_text():
    error = ReviewVerificationError("private-test-secret", refs=("private-account",), expected="private-model-prose")
    error.review_diagnostic = {"stage": "private-text", "completed_tools": ["private-tool", "get_episode_facts"],
                               "search_stances": ["private-stance", "support"], "question": "private-question"}
    result = safe_failure(error)
    assert "private" not in json.dumps(result)
    assert result["completed_tools"] == ["get_episode_facts"]
    assert result["code"] == "review_validation_failed"


def test_diagnostic_preserves_failure_and_isolates_concurrent_runs():
    @diagnosed
    async def attempt(stage):
        mark(stage, correction_attempt=1, tool_audit_passed=True)
        await asyncio.sleep(0)
        raise ReviewVerificationError("answer_summary_not_audited")
    async def run():
        return await asyncio.gather(attempt("answer_composition"), attempt("claim_validation"), return_exceptions=True)
    errors = asyncio.run(run())
    assert all(isinstance(error, ReviewVerificationError) for error in errors)
    assert [safe_failure(e)["stage"] for e in errors] == ["answer_composition", "claim_validation"]
    assert safe_failure(errors[0])["correction_attempt"] == 1
    assert safe_failure(ReviewVerificationError("answer_summary_not_audited"))["stage"] == "unclassified"


def test_finalizer_diagnostic_keeps_only_failure_shape_and_code_fields():
    from typing import Literal
    from pydantic import BaseModel, ConfigDict
    from src.agents.structured_finalizer import FinalizerOutputSchema

    class Choice(BaseModel):
        model_config = ConfigDict(extra="forbid")
        answer_focus: Literal["result_formation"]
        finding_option_ids: list[Literal["synthetic-option"]]

    @diagnosed
    async def attempt():
        FinalizerOutputSchema(Choice).validate_json(
            '{"answer_focus":"result_formation","private-account-fact":"do not retain"}')

    async def run():
        return (await asyncio.gather(attempt(), return_exceptions=True))[0]
    error = asyncio.run(run())
    diagnostic = safe_failure(error)
    assert diagnostic["finalizer_failure_kind"] == "missing_required_fields"
    assert diagnostic["finalizer_failure_fields"] == ["finding_option_ids"]
    assert diagnostic["finalizer_failure_paths"] == ["$", "$.finding_option_ids"]
    assert diagnostic["finalizer_failure_types"] == ["extra_forbidden", "missing"]
    assert "private-account-fact" not in json.dumps(diagnostic)


def test_account_answer_schema_diagnostic_keeps_nested_code_path_not_candidate(tmp_path):
    from src.agents.account_conversation import ConversationAnswer
    from src.agents.structured_finalizer import FinalizerOutputSchema

    @diagnosed
    async def attempt():
        FinalizerOutputSchema(ConversationAnswer).validate_json(json.dumps({
            "paragraphs": [{"kind": "fact", "text": {"zh": "private answer", "en": 7},
                            "refs": ["private-ref"]}],
            "guides": [],
        }))

    async def run():
        return (await asyncio.gather(attempt(), return_exceptions=True))[0]
    error = asyncio.run(run())
    diagnostic = safe_failure(error)
    assert diagnostic["finalizer_failure_paths"] == ["$.paragraphs[0].text.en"]
    assert diagnostic["finalizer_failure_types"] == ["string_type"]
    assert "private" not in json.dumps(diagnostic)
    path = tmp_path / "safe-schema-failure.jsonl"
    persist_failure(path, diagnostic)
    persisted = json.loads(path.read_text())
    assert persisted["finalizer_failure_paths"] == ["$.paragraphs[0].text.en"]
    assert persisted["finalizer_failure_types"] == ["string_type"]
    assert "private" not in path.read_text()


def test_semantic_rejection_diagnostic_allows_code_path_not_values():
    error = StructuredFinalizationUnavailable("finalizer_schema_validation_failed")
    error.review_diagnostic = {
        "stage": "structured_finalization",
        "semantic_rejection_code": "answer_relevant_comparison_or_counterexample_missing",
        "semantic_rejection_path": "$.finding_option_ids",
        "finalizer_format_attempt": 1,
        "private": "account fact",
    }
    diagnostic = safe_failure(error)
    assert diagnostic["code"] == "finalizer_schema_validation_failed"
    assert diagnostic["semantic_rejection_code"] == "answer_relevant_comparison_or_counterexample_missing"
    assert diagnostic["semantic_rejection_path"] == "$.finding_option_ids"
    assert diagnostic["finalizer_format_attempt"] == 1
    assert "account fact" not in json.dumps(diagnostic)


def test_poll_writes_one_safe_record_and_no_answer(tmp_path):
    runtime = object.__new__(ReviewRuntime)
    connection = sqlite3.connect(tmp_path / "test.sqlite3")
    runtime.store = SimpleNamespace(connection=connection, note_fingerprint=lambda *args: "notes")
    runtime._source_fingerprint = lambda params: "source"
    error = ReviewVerificationError("answer_summary_not_audited", refs=("private-ref",), expected="private-text")
    error.review_diagnostic = {"stage": "answer_composition", "tool_audit_passed": True}
    future = Future(); future.set_exception(error)
    runtime.jobs = {"job": {"scope": ("s", "a", "e"), "future": future, "note_fingerprint": "notes",
                            "source_params": {}, "source_fingerprint": "source", "share_id": None, "cancelled": Event()}}
    params = {"subject_id": "s", "account_id": "a", "episode_id": "e", "job_id": "job"}
    result = runtime.poll(params)
    assert runtime.poll(params) == result
    assert result["result"] is None and result["reason"] == "review_answer_evidence_failed"
    lines = (tmp_path / "review-diagnostics.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["code"] == "answer_summary_not_audited"
    assert "private" not in lines[0]
    connection.close()


@pytest.mark.parametrize(("error", "reason"), [
    (TimeoutError("secret"), "review_timeout"),
    (StructuredFinalizationUnavailable("finalization_input_over_limit"), "review_analysis_too_large"),
    (StructuredFinalizationUnavailable("finalizer_schema_validation_failed"), "review_answer_format_failed"),
    (ReviewVerificationError("answer_reference_capacity_exceeded"), "review_answer_assembly_failed"),
    (ReviewVerificationError("unretrieved_or_unknown_evidence"), "review_answer_evidence_failed"),
    (ReviewVerificationError("review_access_expired_or_revoked"), "review_access_expired_or_revoked"),
    (ValueError("private secret exception"), "review_analysis_failed"),
])
def test_public_failure_is_specific_and_never_contains_exception_text(error, reason):
    assert failure_reason(error) == reason


@pytest.mark.parametrize("code", ["account_model_request_failed", "account_model_timeout",
    "account_answer_number_not_in_sources", "account_research_incomplete"])
def test_dsa_failure_codes_survive_without_exception_prose(code):
    from src.agents.account_conversation import ConversationError
    error = ConversationError(code, {"private": "secret-model-prose"})
    assert safe_failure(error)["code"] == code
    assert "secret" not in json.dumps(safe_failure(error))


def test_dsa_grounding_and_unknown_errors_remain_safe():
    from src.agents.account_conversation import ConversationError
    assert safe_failure(ConversationError("account_grounding:unsupported_claim"))["code"] == "account_grounding_failed"
    assert safe_failure(ConversationError("private-secret"))["code"] == "review_validation_failed"
    assert safe_failure(RuntimeError("private-secret"))["code"] == "review_validation_failed"
    assert safe_failure(TimeoutError())["code"] == "account_review_timeout"


def test_account_poll_persists_one_safe_diagnostic_and_returns_copy(tmp_path):
    from threading import Lock
    from src.agents.account_conversation import ConversationError
    from toujing_core_runtime.account_review import AccountReviewService
    service = object.__new__(AccountReviewService)
    service.product = SimpleNamespace(repo=SimpleNamespace(path=tmp_path / "test.sqlite3"))
    service._lock = Lock()
    service._source_fingerprint = lambda params: "source"
    scope = {"scope_kind": "account", "subject_id": "s", "account_id": "a", "data_mode": "real_user"}
    error = ConversationError("account_answer_number_not_in_sources", {"private": "secret-content"})
    error.review_diagnostic = {"stage": "numeric_reference_validation", "correction_attempt": 1,
                              "completed_tools": ["search_public_web"], "elapsed_ms": 33000}
    future = Future(); future.set_exception(error)
    service.jobs = {"j": {"scope": scope, "future": future, "cancelled": Event(), "source_params": scope,
                          "source_fingerprint": "source"}}
    params = {**scope, "job_id": "j"}
    result = service.poll(params)
    assert result["reason"] == "account_review_analysis_failed" and result["result"] is None
    assert result["diagnostic"]["code"] == "account_answer_number_not_in_sources"
    assert result["diagnostic"]["stage"] == "numeric_reference_validation"
    lines = (tmp_path / "review-diagnostics.jsonl").read_text().splitlines()
    assert len(lines) == 1 and "secret" not in lines[0]
    assert json.loads(lines[0])["elapsed_ms"] == 33000
    result["diagnostic"]["code"] = "mutated"
    assert service.poll(params)["diagnostic"]["code"] == "account_answer_number_not_in_sources"
    assert len((tmp_path / "review-diagnostics.jsonl").read_text().splitlines()) == 1


def test_unwritable_diagnostic_is_nonfatal(tmp_path):
    from src.agents.review_diagnostics import persist_failure
    persist_failure(tmp_path / "missing" / "log.jsonl", safe_failure(TimeoutError()))
