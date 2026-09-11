"""Offline adapter/contract tests; not a substitute for live model quality QA."""
import asyncio
import copy
import json
from dataclasses import asdict
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from test_account_review import account_context, ScriptedModel, runtime
from test_account_conversation import concept_case
from src.agents.dsa_conversation import (
    ENGINE, TOOL_TIMEOUT_SECONDS, ResponsesAdapter, ToolCall, LLMResponse, audit_receipts, run_dsa_conversation,
)
from src.agents.account_conversation import ConversationError
from src.agents.dsa_vendor.runner import run_agent_loop
from src.agents.dsa_vendor.tools.registry import ToolRegistry, ToolDefinition


def response(text="", calls=(), status="completed"):
    return NS(status=status, output_text=text, output=[NS(type="function_call", call_id=id,
        name=name, arguments=json.dumps(args)) for id, name, args in calls], usage=NS(total_tokens=12))


def configured(monkeypatch, responses, final_outputs):
    # Private DSA judge uses explicit per-paragraph support, not an error-code
    # checklist. Preserve the old fixture shorthand for positive/negative cases.
    outputs = []
    count = 1
    for output in final_outputs:
        if isinstance(output, dict) and "paragraphs" in output:
            count = len(output["paragraphs"])
        if isinstance(output, dict) and "issues" in output:
            outputs.append({"paragraphs": [{"paragraph_index": i, "supported": not bool(output["issues"]),
                "reason": "Unsupported motive" if output["issues"] else "Supported by the cited definition"}
                for i in range(count)], "question_answered": True, "guides_valid": True})
        else:
            outputs.append(output)
    model = ScriptedModel(outputs)
    client = NS(responses=NS(create=AsyncMock(side_effect=responses)), close=AsyncMock())
    monkeypatch.setattr(model, "_get_client", lambda: client, raising=False)
    return runtime(model), client, model


def test_upstream_loop_reaches_existing_validation_without_second_analysis(monkeypatch, account_context):
    record, answer = concept_case(account_context)
    configured_runtime, client, model = configured(monkeypatch, [
        response("I will check the definition.", [("call1", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain the denominator without reading unrelated personal data.")], [answer, {"issues": []}])
    phases = []
    result = asyncio.run(run_dsa_conversation("风险资产权重是什么意思？", account_context,
        runtime=configured_runtime, progress=phases.append))
    assert result["engine"] == ENGINE
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    assert result["verification"] == "receipts_and_grounding_review_v1"
    assert result["executed_tools"] == ["read_financial_concept"]
    assert result["read_refs"] == [record.ref]
    assert "reading" in phases and phases[-2:] == ["writing", "checking"]
    assert len(model.requests) == 2 and all(r["tools"] == [] for r in model.requests)
    first, second = [c.kwargs for c in client.responses.create.call_args_list]
    assert first["reasoning"] == {"effort": "none"}
    assert first["tool_choice"] == "required" and first["store"] is False
    assert second["tool_choice"] == "auto"  # SDK reset_tool_choice parity, not JSON fallback.
    output = next(i for i in second["input"] if i.get("type") == "function_call_output")
    assert output["call_id"] == "call1" and json.loads(output["output"])["records"][0]["ref"] == record.ref
    assert account_context.retrieved == set() and record.ref not in account_context.records


@pytest.mark.parametrize("bad", [response(calls=[("x", "not_registered", {})]),
    response("unfinished", status="incomplete")])
def test_invalid_calls_fail_before_tool_or_finalizer(monkeypatch, account_context, bad):
    configured_runtime, _, model = configured(monkeypatch, [bad], [])
    with pytest.raises(ConversationError):
        asyncio.run(run_dsa_conversation("分析", account_context, runtime=configured_runtime))
    assert not model.requests and not account_context.retrieved


def test_foreign_episode_and_no_receipts_fail_closed(monkeypatch, account_context):
    for first in [response("Invent a result"), response(calls=[("x", "get_investment_details", {"episode_id": "foreign"})])]:
        configured_runtime, _, model = configured(monkeypatch, [first, response("Guess")], [])
        with pytest.raises(ConversationError, match="receipt"):
            asyncio.run(run_dsa_conversation("分析", account_context, runtime=configured_runtime))
        assert not model.requests


def test_invalid_arguments_can_be_corrected_without_crediting_failed_receipt(monkeypatch, account_context):
    record, answer = concept_case(account_context)
    configured_runtime, client, _ = configured(monkeypatch, [
        response(calls=[("bad", "read_financial_concept", {"topic": "unregistered"})]),
        response(calls=[("good", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain the actual definition")], [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("解释比例", account_context, runtime=configured_runtime))
    assert result["read_refs"] == [record.ref]
    failed = next(i for i in client.responses.create.call_args_list[1].kwargs["input"]
                  if i.get("type") == "function_call_output")
    assert json.loads(failed["output"])["records"] == []


def test_cancel_aborts_pending_model_request(monkeypatch, account_context):
    async def exercise():
        started, stopped = asyncio.Event(), asyncio.Event()
        async def slow(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        configured_runtime, client, model = configured(monkeypatch, [], [])
        client.responses.create.side_effect = slow
        task = asyncio.create_task(run_dsa_conversation("分析", account_context, runtime=configured_runtime))
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(stopped.wait(), 2)
        assert not model.requests
    asyncio.run(exercise())


def test_provider_errors_do_not_expose_secret_or_payload(monkeypatch, account_context):
    configured_runtime, _, _ = configured(monkeypatch, [RuntimeError("Authorization secret-private-data")], [])
    with pytest.raises(ConversationError) as error:
        asyncio.run(run_dsa_conversation("分析", account_context, runtime=configured_runtime))
    assert str(error.value) == "account_model_request_failed"
    assert error.value.__suppress_context__


def test_receipt_pairing_and_exact_record_content(account_context):
    record, _ = concept_case(account_context)
    value = json.loads(json.dumps(asdict(record)))
    messages = [{"role": "assistant", "tool_calls": [{"id": "c", "name": "read"}]},
        {"role": "tool", "name": "read", "tool_call_id": "c", "content": json.dumps({"status": "complete", "records": [value]})}]
    allowed, receipts = audit_receipts(messages, {record.ref: value}, {record.ref}, {"read"})
    assert allowed == [record.ref] and receipts[0]["call_id"] == "c"
    for altered in (messages[:1], messages[1:], [*messages, messages[1]]):
        with pytest.raises(ConversationError):
            audit_receipts(altered, {record.ref: value}, {record.ref}, {"read"})
    with pytest.raises(ConversationError):
        audit_receipts(messages, {record.ref: {**value, "value": "changed"}}, {record.ref}, {"read"})
    with pytest.raises(ConversationError):
        audit_receipts(messages, {record.ref: value}, set(), {"read"})


def test_upstream_timeout_and_non_retriable_cache():
    import time
    calls = []
    def slow():
        calls.append(1)
        time.sleep(.08)
        return {"ok": True}
    registry = ToolRegistry()
    registry.register(ToolDefinition("slow", "", [], slow, timeout_seconds=.01))
    responses = iter([LLMResponse(tool_calls=[ToolCall("a", "slow", {})]),
        LLMResponse(tool_calls=[ToolCall("b", "slow", {})]), LLMResponse(content="done")])
    result = run_agent_loop(messages=[], tool_registry=registry,
        llm_adapter=NS(call_with_tools=lambda *a, **kw: next(responses)), max_steps=3)
    assert result.success and len(calls) == 1
    assert result.tool_calls_log[0]["timeout"]
    assert result.tool_calls_log[1]["cached"]


def test_upstream_parallel_outputs_preserve_call_order():
    registry = ToolRegistry()
    registry.register(ToolDefinition("read", "", [], lambda **kw: kw))
    responses = iter([LLMResponse(tool_calls=[ToolCall("a", "read", {"value": 1}), ToolCall("b", "read", {"value": 2})]),
                      LLMResponse(content="done")])
    result = run_agent_loop(messages=[], tool_registry=registry,
        llm_adapter=NS(call_with_tools=lambda *a, **kw: next(responses)))
    assert [m["tool_call_id"] for m in result.messages if m["role"] == "tool"] == ["a", "b"]


def test_dsa_unsupported_psychology_still_requires_grounding(monkeypatch, account_context):
    _, valid = concept_case(account_context)
    invalid = copy.deepcopy(valid)
    invalid["paragraphs"][0]["text"] = {"zh": "你贪婪导致亏损", "en": "Greed caused your loss"}
    configured_runtime, client, _ = configured(monkeypatch, [
        response(calls=[("x", "read_financial_concept", {"topic": "concentration"})]), response("Greed caused loss")],
        [invalid, {"issues": ["unsupported_motive_or_advice"]}, valid, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("是不是贪婪？", account_context, runtime=configured_runtime))
    assert result["answer"]["paragraphs"] == valid["paragraphs"]
    assert client.responses.create.call_count == 2  # correction never re-runs research.


def test_runtime_explicit_dsa_dispatch_and_client_cleanup(monkeypatch, account_context):
    import time
    from toujing_core_runtime.account_review import AccountReviewService
    record, answer = concept_case(account_context)
    configured_runtime, client, _ = configured(monkeypatch, [
        response(calls=[("x", "read_financial_concept", {"topic": "concentration"})]), response("Explain")],
        [answer, {"issues": []}])
    service = AccountReviewService(NS())
    monkeypatch.setattr(service, "_source_with_fingerprint", lambda params: (copy.copy(account_context), "fixed"))
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: "fixed")
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime", lambda key: configured_runtime)
    try:
        job = service.start({**account_context.scope, "allow_model_review": True, "question": "解释比例",
            "answer_version": "account_conversation_answer_v2", "conversation_engine": "dsa"})
        for _ in range(200):
            reply = service.poll({**account_context.scope, "job_id": job["job_id"]})
            if reply["status"] != "running":
                break
            time.sleep(.01)
        assert reply["status"] == "complete"
        assert reply["result"]["engine"] == ENGINE
        assert reply["result"]["read_refs"] == [record.ref]
        client.close.assert_awaited_once()
    finally:
        service.close()


def test_second_candidate_is_not_pruned_into_a_dangling_answer(monkeypatch, account_context):
    _, answer = concept_case(account_context)
    unbound = copy.deepcopy(answer["paragraphs"][0])
    unbound["text"] = {"zh": "公告数值是999999元。", "en": "The announcement value is 999999."}
    dangling = copy.deepcopy(answer["paragraphs"][0])
    dangling["text"] = {"zh": "同一公告也解释了集中度。", "en": "The same announcement also explains concentration."}
    invalid = {**answer, "paragraphs": [unbound, dangling]}
    configured_runtime, client, model = configured(monkeypatch, [
        response(calls=[("x", "read_financial_concept", {"topic": "concentration"})]), response("Explain")],
        [invalid, {"issues": []}, invalid, {"paragraphs": [{"paragraph_index": 0, "supported": True,
            "reason": "A pruned remainder would look supported"}], "question_answered": True,
            "guides_valid": True}])
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        asyncio.run(run_dsa_conversation("解释比例", account_context, runtime=configured_runtime))
    assert client.responses.create.call_count == 2
    assert len(model.requests) == 3  # initial writer + judge + one complete-output repair


def test_no_remaining_grounded_answer_still_fails(monkeypatch, account_context):
    _, answer = concept_case(account_context)
    answer["paragraphs"][0]["text"] = {"zh": "你赚了999999元", "en": "You made 999999"}
    configured_runtime, _, _ = configured(monkeypatch, [
        response(calls=[("x", "read_financial_concept", {"topic": "concentration"})]), response("Invent")],
        [answer, {"issues": ["unsupported_claim"]}, answer])
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        asyncio.run(run_dsa_conversation("解释比例", account_context, runtime=configured_runtime))


@pytest.mark.parametrize("indices", [[0, 0], [1], [0, 1]])
def test_verifier_requires_exact_paragraph_coverage(monkeypatch, indices):
    from src.agents import dsa_conversation as dsa
    verdict = dsa.GroundingVerdict(paragraphs=[{"paragraph_index": i, "supported": True,
        "reason": "supported"} for i in indices], question_answered=True, guides_valid=True)
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    with pytest.raises(ConversationError, match="incomplete_coverage"):
        asyncio.run(dsa.verify_grounding(None, {"candidate": {"paragraphs": [{"text": {"zh": "解释"}}]}}, lambda: True))


def test_verifier_negative_findings_still_fail_closed(monkeypatch):
    from src.agents import dsa_conversation as dsa
    verdict = dsa.GroundingVerdict(paragraphs=[{"paragraph_index": 0, "supported": False,
        "reason": "Motive not supported by trading records"}], question_answered=False, guides_valid=False,
        guide_findings=[{"guide_index": 0, "reason": "Pretrade does not open the discussed investment"}])
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    result = asyncio.run(dsa.verify_grounding(None, {"candidate": {"paragraphs": [{"text": {"zh": "解释"}}],
        "guides": [{"guide_id": "pretrade-allocation", "episode_id": None}]}}, lambda: True))
    assert set(result.issues) == {"unsupported_claim", "question_not_answered", "wrong_guide"}
    assert result.findings[0].paragraph_index == 0
    assert result.guide_findings[0].guide_index == 0
    assert "Pretrade" in result.guide_findings[0].reason


def test_empty_candidate_guides_cannot_acquire_model_invented_wrong_guide(monkeypatch):
    from src.agents import dsa_conversation as dsa
    verdict = dsa.GroundingVerdict(paragraphs=[{"paragraph_index": 0, "supported": True,
        "reason": "The cited allocation supports the paragraph"}], question_answered=True,
        guides_valid=False, guide_findings=[{"guide_index": 0, "reason": "Invented guide failure"}])
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    result = asyncio.run(dsa.verify_grounding(None, {"candidate": {
        "paragraphs": [{"text": {"zh": "解释"}}], "guides": []}}, lambda: True))
    assert result.issues == []
    assert result.findings == [] and result.guide_findings == []


def test_contradictory_positive_guide_boolean_cannot_erase_rejection(monkeypatch):
    from src.agents import dsa_conversation as dsa
    verdict = dsa.GroundingVerdict(paragraphs=[{"paragraph_index": 0, "supported": True,
        "reason": "Supported"}], question_answered=True, guides_valid=True,
        guide_findings=[{"guide_index": 0, "reason": "Wrong target for this question"}])
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    result = asyncio.run(dsa.verify_grounding(None, {"candidate": {
        "paragraphs": [{"text": {"zh": "解释"}}],
        "guides": [{"guide_id": "pretrade-allocation", "episode_id": None}]}}, lambda: True))
    assert result.issues == ["wrong_guide"]
    assert result.guide_findings[0].reason == "Wrong target for this question"


def test_old_verifier_fixture_gets_safe_guide_only_correction_fallback(monkeypatch):
    from src.agents import dsa_conversation as dsa
    old_fixture = {"paragraphs": [{"paragraph_index": 0, "supported": True, "reason": "supported"}],
                   "question_answered": True, "guides_valid": False}
    verdict = dsa.GroundingVerdict.model_validate(old_fixture)
    assert verdict.guide_findings == []
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    result = asyncio.run(dsa.verify_grounding(None, {"candidate": {
        "paragraphs": [{"text": {"zh": "解释"}}],
        "guides": [{"guide_id": "pretrade-allocation", "episode_id": None}]}}, lambda: True))
    assert result.issues == ["wrong_guide"] and result.findings == []
    assert [item.guide_index for item in result.guide_findings] == [0]
    assert "navigation" in result.guide_findings[0].reason


def test_guide_finding_is_provider_required_but_locally_optional_for_old_fixtures():
    from src.agents import dsa_conversation as dsa
    from src.agents.structured_finalizer import FinalizerOutputSchema
    schema = FinalizerOutputSchema(dsa.GroundingVerdict).json_schema()
    assert "guide_findings" in schema["required"]
    assert schema["properties"]["guide_findings"]["maxItems"] == 3
    verdict = dsa.GroundingVerdict.model_validate({
        "paragraphs": [{"paragraph_index": 0, "supported": True, "reason": "supported"}],
        "question_answered": True, "guides_valid": True})
    assert verdict.guide_findings == []


def test_wrong_guide_repair_preserves_verified_paragraphs(monkeypatch, account_context):
    _, answer = concept_case(account_context)
    wrong = copy.deepcopy(answer)
    wrong["guides"] = [{"guide_id": "pretrade-allocation", "episode_id": None,
                        "label": {"zh": "查看账户持仓", "en": "Open account holdings"}}]
    rejected = {"paragraphs": [{"paragraph_index": 0, "supported": True,
        "reason": "The cited definition supports this paragraph"}], "question_answered": True,
        "guides_valid": False, "guide_findings": [{"guide_index": 0,
            "reason": "Pretrade requires a hypothetical trade and is not a holdings page"}]}
    accepted = {"paragraphs": [{"paragraph_index": 0, "supported": True,
        "reason": "The cited definition supports this paragraph"}], "question_answered": True,
        "guides_valid": True, "guide_findings": []}
    configured_runtime, client, model = configured(monkeypatch, [
        response(calls=[("x", "read_financial_concept", {"topic": "concentration"})]), response("Explain")],
        [wrong, rejected, answer, accepted])
    result = asyncio.run(run_dsa_conversation("风险资产权重是什么意思？", account_context,
        runtime=configured_runtime))
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    assert result["answer"]["guides"] == []
    assert client.responses.create.call_count == 2
    assert len(model.requests) == 4
    correction = json.dumps(model.requests[2]["input"], ensure_ascii=False)
    assert "guide_findings" in correction and "guide_index" in correction
    assert "Pretrade requires a hypothetical trade" in correction


def test_timeline_cannot_be_promoted_to_primary_cause_by_a_positive_judge(monkeypatch):
    from src.agents import dsa_conversation as dsa
    judge = AsyncMock(return_value=dsa.GroundingVerdict(paragraphs=[{"paragraph_index": 0,
        "supported": True, "reason": "The timeline is accurate"}], question_answered=True,
        guides_valid=True, guide_findings=[]))
    monkeypatch.setattr(dsa, "_structured", judge)
    result = asyncio.run(dsa.verify_grounding(None, {"candidate": {"paragraphs": [
        {"text": {"zh": "亏损主要来自持续加仓推高了成本", "en": "Loss was primarily due to additions"}}
    ]}}, lambda: True))
    assert result.issues == ["unsupported_claim"]
    assert result.findings[0].paragraph_index == 0
    judge.assert_awaited_once()


def test_public_tools_reuse_loop_and_disabled_search_is_only_a_service_receipt(monkeypatch, account_context):
    from src.agents.account_conversation import CONVERSATION_TOOLS
    from src.agents.public_research import PUBLIC_TOOLS, attach_public_research
    assert {tool.name for tool in PUBLIC_TOOLS} <= {tool.name for tool in CONVERSATION_TOOLS}
    attach_public_research(account_context, {"_desktop_search_enabled": False})
    record, answer = concept_case(account_context)
    phases = []
    configured_runtime, client, _ = configured(monkeypatch, [
        response(calls=[("s", "search_public_web", {"query": "贵州茅台"})]),
        response(calls=[("c", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain")], [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("风险资产权重是什么意思？", account_context,
        runtime=configured_runtime, progress=phases.append))
    assert "searching" in phases
    assert set(result["read_refs"]) == {record.ref, *result["research_read_refs"]}
    assert len(result["research_read_refs"]) == 1
    assert result["public_read_refs"] == []
    failed = next(item for item in client.responses.create.call_args_list[1].kwargs["input"]
                  if item.get("type") == "function_call_output")
    unavailable = json.loads(failed["output"])
    assert unavailable["status"] == "insufficient_evidence"
    assert unavailable["records"][0]["value"]["reason_code"] == "search_disabled"
    assert unavailable["records"][0]["value"]["market_facts_returned"] is False
    assert unavailable["records"][0]["availability"] == "unavailable"


def test_public_security_read_refs_are_isolated_and_quoting_is_reported(monkeypatch, account_context):
    from datetime import datetime, timezone
    from agents.tool_context import ToolContext
    from src.agents.public_research import attach_public_research, identify_public_security
    from test_account_conversation import paragraph
    clock = lambda: datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)
    attach_public_research(account_context, {"_desktop_search_enabled": False, "_public_now": clock})
    encoded = json.dumps({"query": "SZSE:000001"})
    probe = copy.copy(account_context)
    probe.records = dict(account_context.records)
    probe.retrieved = set()
    attach_public_research(probe, {"_desktop_search_enabled": False, "_public_now": clock})
    record = json.loads(asyncio.run(identify_public_security.on_invoke_tool(
        ToolContext(probe, tool_name="identify_public_security", tool_call_id="t", tool_arguments=encoded),
        encoded)))["records"][0]
    answer = {"paragraphs": [paragraph(record["ref"], zh="这是公开市场代码，不是账户持仓。",
        en="This is a public listing id, not an account holding.", kind="fact")], "guides": []}
    phases = []
    configured_runtime, _, _ = configured(monkeypatch, [
        response(calls=[("i", "identify_public_security", {"query": "SZSE:000001"})]),
        response("Explain")], [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("SZSE:000001是什么？", account_context,
        runtime=configured_runtime, progress=phases.append))
    assert "quoting" in phases
    assert result["public_read_refs"] == [record["ref"]]
    assert result["read_refs"] == [record["ref"]]
    assert result["public_sources"][0]["title"] == "SZSE:000001"


def test_conversation_tools_use_a_shared_quote_safe_timeout():
    assert TOOL_TIMEOUT_SECONDS == 20


def test_dsa_diagnostics_preserve_receipts_and_final_validation_stage(monkeypatch, account_context):
    from src.agents.review_diagnostics import safe_failure
    record, answer = concept_case(account_context)
    answer["paragraphs"][0]["text"] = {"zh": "999999元", "en": "999999 yuan"}
    configured_runtime, _, _ = configured(monkeypatch, [
        response(calls=[("call1", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain")], [answer, {"issues": ["unsupported_claim"]}, answer])
    with pytest.raises(ConversationError) as caught:
        asyncio.run(run_dsa_conversation("解释", account_context, runtime=configured_runtime))
    diagnostic = safe_failure(caught.value)
    assert diagnostic["code"] == "account_answer_number_not_in_sources"
    assert diagnostic["stage"] == "numeric_reference_validation"
    assert diagnostic["correction_attempt"] == 1 and diagnostic["tool_audit_passed"] is True
    assert diagnostic["completed_tools"] == ["read_financial_concept"]
    assert diagnostic["elapsed_ms"] >= 0
