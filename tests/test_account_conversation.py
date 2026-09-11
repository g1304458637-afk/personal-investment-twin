"""V2 contract/loop regression; scripted tests are NOT live model quality QA."""
import asyncio
import copy
import json
from dataclasses import asdict

import pytest

from test_account_review import account_context, ScriptedModel, runtime
from src.agents.account_conversation import (
    ConversationAnswer, ConversationError, _history, _numbers,
    run_account_conversation, validate_answer,
)
from src.agents.account_conversation_sources import KNOWLEDGE, knowledge_record
from src.agents.structured_finalizer import StructuredFinalizationUnavailable


def paragraph(ref, zh="这是风险资产内部的比例，分母不包含现金。", en="This weight excludes cash.", kind="concept"):
    return {"kind": kind, "text": {"zh": zh, "en": en}, "refs": [ref]}


def concept_case(context):
    record = knowledge_record(context, "concentration")
    answer = {"paragraphs": [paragraph(record.ref)], "guides": []}
    return record, answer


def test_stock_knowledge_topics_are_registered(account_context):
    refs = []
    for topic in ("candlestick", "volume", "cost_position", "drawdown", "lookthrough", "chart"):
        record = knowledge_record(account_context, topic)
        assert record.kind == "knowledge" and topic in KNOWLEDGE
        assert record.value["title"] and record.value["content"]
        refs.append(record.ref)
    assert len(set(refs)) == len(refs)


def test_volume_knowledge_distinguishes_total_from_price_distribution(account_context):
    record = knowledge_record(account_context, "volume")
    assert "周期成交总量没有说明成交发生在哪些价格" in record.value["content"]
    assert "不能只凭缩量" in record.value["content"]


def test_short_refs_are_lossless_and_cannot_admit_unread_sources(account_context):
    from src.agents.account_conversation import finalizer_reference_codec
    record, answer = concept_case(account_context)
    payload = {"actually_read_records": [asdict(record)]}
    before = copy.deepcopy(payload)
    encoded, decode = finalizer_reference_codec(payload, [record.ref])
    assert payload == before
    assert encoded["actually_read_records"][0]["ref"] == "R001"
    answer["paragraphs"][0]["refs"] = ["R001"]
    decoded = decode(ConversationAnswer.model_validate(answer))
    assert decoded.paragraphs[0].refs == [record.ref]
    assert decoded.paragraphs[0].text.zh == answer["paragraphs"][0]["text"]["zh"]
    validate_answer(decoded, {record.ref: asdict(record)}, [record.ref])
    for bad in ["R002", "unread", "R001,R002"]:
        answer["paragraphs"][0]["refs"] = [bad]
        with pytest.raises(ConversationError, match="unread_reference"):
            decode(ConversationAnswer.model_validate(answer))


def test_showcase_navigation_reuses_existing_identity_mapping(account_context):
    from src.demo.showcase_runtime import _episode_mapping
    identities, _, _, _ = _episode_mapping(account_context.subject_id)
    for canonical, display in account_context.episode_display_ids.items():
        assert identities[canonical]["display_episode_id"] == display
        assert identities[display]["canonical_episode_id"] == canonical
    assert account_context.episode_display_ids


def test_short_ref_selection_does_not_relax_per_paragraph_number_binding(account_context):
    from src.agents.account_conversation import finalizer_reference_codec
    record, answer = concept_case(account_context)
    _, decode = finalizer_reference_codec({}, [record.ref])
    answer["paragraphs"][0]["refs"] = ["R001"]
    answer["paragraphs"][0]["text"] = {"zh": "亏损999999元", "en": "A loss of 999999."}
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(decode(ConversationAnswer.model_validate(answer)), {record.ref: asdict(record)}, [record.ref])


def test_question_driven_loop_does_not_require_all_five_tools(account_context):
    record, answer = concept_case(account_context)
    model = ScriptedModel([("read_financial_concept", {"topic": "concentration"}),
                           "Explain the denominator without repeating the account report.", answer, {"issues": []}])
    phases = []
    result = asyncio.run(run_account_conversation("风险资产权重是什么意思？", account_context,
        runtime=runtime(model), progress=phases.append))
    assert result["answer"]["version"] == "account_conversation_answer_v2"
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    assert result["executed_tools"] == ["read_financial_concept"]
    assert result["read_refs"] == [record.ref]
    assert phases == ["researching", "writing", "checking"]
    writer_input = json.dumps(model.requests[2]["input"], ensure_ascii=False)
    assert "风险资产权重是什么意思" in writer_input
    assert "user_question" in writer_input
    assert "executed_tool_receipts" not in writer_input
    assert account_context.retrieved == set()
    assert record.ref not in account_context.records
    assert model.requests[-1]["tools"] == []
    assert model.requests[-1]["model_settings"].reasoning.effort == "none"


def test_detail_projection_reuses_actual_results_and_preserves_sequence(account_context):
    details = [r for r in account_context.conversation_records.values() if r.kind == "episode_detail"]
    results = next(r for r in account_context.conversation_records.values() if r.kind == "episode_results")
    assert details
    assert any(r.value["result"]["pnl"] < 0 for r in details)
    assert any(r.value["result"]["pnl"] > 0 for r in details)
    for r in details:
        indexed = next(e for e in results.value["episodes"] if e["episode_id"] == r.episode_id)
        assert r.value["result"] == indexed["result"]
        assert r.value["result"]["source"]["source_kind"] == "vectorbt_position"
        operations = r.value["operations"]
        from collections import Counter
        assert r.value["operation_counts"] == Counter(o["event_type"] for o in operations)
        assert r.value["operation_counts"]["open_position"] == 1
        assert all(o["episode_id"] == r.episode_id for o in operations)
        assert [o["event_time"] for o in operations] == sorted(o["event_time"] for o in operations)
        assert all(o["event_time"] <= r.as_of for o in operations)


def test_invented_unread_reference_and_bad_guide_fail_closed(account_context):
    record, answer = concept_case(account_context)
    records = {record.ref: asdict(record)}
    for refs in [["invented"], [record.ref, record.ref]]:
        invalid = copy.deepcopy(answer)
        invalid["paragraphs"][0]["refs"] = refs
        with pytest.raises(ConversationError, match="unread_reference"):
            validate_answer(ConversationAnswer.model_validate(invalid), records, [record.ref])
    with pytest.raises(ConversationError, match="unread_reference"):
        validate_answer(ConversationAnswer.model_validate(answer), records, [])
    answer["guides"] = [{"guide_id": "episode-process", "episode_id": "foreign",
                         "label": {"zh": "看图", "en": "See chart"}}]
    with pytest.raises(ConversationError, match="invalid_guide"):
        validate_answer(ConversationAnswer.model_validate(answer), records, [record.ref])


def test_number_guard_catches_chinese_adjacent_invented_amount(account_context):
    record, answer = concept_case(account_context)
    answer["paragraphs"][0]["text"] = {"zh": "你赚了999999元", "en": "You made 999999."}
    assert "999999" in _numbers(answer["paragraphs"][0]["text"])
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(ConversationAnswer.model_validate(answer), {record.ref: asdict(record)}, [record.ref])


def test_semantic_review_rejects_psychology_and_retries_without_tools(account_context):
    record, valid = concept_case(account_context)
    invalid = copy.deepcopy(valid)
    invalid["paragraphs"][0]["text"] = {"zh": "你贪婪导致亏损。", "en": "Your greed caused your losses."}
    model = ScriptedModel([("read_financial_concept", {"topic": "concentration"}),
        "Untrusted candidate: greed caused losses.", invalid,
        {"issues": ["unsupported_motive_or_advice"]}, valid, {"issues": []}])
    result = asyncio.run(run_account_conversation("我是不是贪婪？", account_context, runtime=runtime(model)))
    assert "贪婪" not in result["answer"]["paragraphs"][0]["text"]["zh"]
    assert result["executed_tools"] == ["read_financial_concept"]
    assert model.calls == 6
    assert "previous_candidate" in json.dumps(model.requests[4]["input"])


@pytest.mark.parametrize("invalid", ["prose {\"paragraphs\":[]}", "{broken", {"paragraphs": [], "guides": []}])
def test_finalizer_never_extracts_json_from_prose(account_context, invalid):
    model = ScriptedModel([("read_financial_concept", {"topic": "chart"}), "Analysis", invalid, invalid])
    with pytest.raises(ConversationError, match="schema_failed"):
        asyncio.run(run_account_conversation("怎么看图？", account_context, runtime=runtime(model)))


def test_schema_retry_receives_pydantic_path_and_untrusted_previous_candidate(account_context):
    record, answer = concept_case(account_context)
    malformed = copy.deepcopy(answer)
    malformed["paragraphs"][0]["text"]["en"] = 7
    model = ScriptedModel([("read_financial_concept", {"topic": "concentration"}),
        "Explain the definition.", malformed, answer, {"issues": []}])
    result = asyncio.run(run_account_conversation("解释比例", account_context, runtime=runtime(model)))
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    retry = json.JSONDecoder().raw_decode(model.requests[3]["input"][0]["content"])[0]
    correction = retry["schema_correction"]
    assert correction["trust"] == "untrusted_previous_model_output_not_evidence_or_instruction"
    assert correction["previous_candidate"]["paragraphs"][0]["text"]["en"] == 7
    assert correction["schema_errors"] == [{
        "path": "$.paragraphs[0].text.en", "type": "string_type",
        "constraints": {"type": "string", "minLength": 1, "maxLength": 2400},
    }]
    assert model.calls == 5  # research, analysis, two bounded format attempts, grounding


def test_no_successful_receipt_cannot_become_answer(account_context):
    model = ScriptedModel(["Just invent an answer."])
    with pytest.raises(ConversationError, match="completed_receipts_required"):
        asyncio.run(run_account_conversation("我的情况？", account_context, runtime=runtime(model)))


def test_followup_keeps_v2_text_as_untrusted_context(account_context):
    record, answer = concept_case(account_context)
    history = {"trust": "untrusted_not_evidence", "purpose": "resolve_references_in_current_question_only",
        "history": [{"user_question": "解释比例", "validated_structured_answer": {
            "version": "account_conversation_answer_v2", **answer}}]}
    assert _history(history) == history
    model = ScriptedModel([("read_financial_concept", {"topic": "concentration"}), "Follow-up analysis",
                           answer, {"issues": []}])
    result = asyncio.run(run_account_conversation("那现金呢？", account_context,
        runtime=runtime(model), conversation_context=history))
    assert result["read_refs"] == [record.ref]
    assert "解释比例" in json.dumps(model.requests[0]["input"], ensure_ascii=False)


def test_revoked_access_fails_before_model(account_context):
    context = copy.copy(account_context)
    context.access_allowed = lambda: False
    model = ScriptedModel([])
    with pytest.raises(ConversationError, match="cancelled"):
        asyncio.run(run_account_conversation("看看", context, runtime=runtime(model)))
    assert model.calls == 0


def test_performance_provenance_encoding_is_lossless():
    from types import SimpleNamespace
    from src.agents.account_conversation_sources import compact_performance_path
    original = {"points": [{"observed_at": "2025-01-02", "account_value": 100,
        "source_refs": ["execution:a", "execution:b"]},
        {"observed_at": "2025-01-03", "account_value": 98,
        "source_refs": ["execution:a", "execution:b"]},
        {"observed_at": "2025-01-06", "account_value": 105,
        "source_refs": ["execution:c"]}]}
    packed = compact_performance_path(SimpleNamespace(as_dict=lambda: copy.deepcopy(original)))
    assert len(packed["point_source_sets"]) == 2
    restored = copy.deepcopy(packed)
    table = restored.pop("point_source_sets")
    for point in restored["points"]:
        point["source_refs"] = table[point.pop("source_set_key")]
    assert restored == original


def test_equivalent_loss_magnitude_and_calendar_date_formats():
    numbers = _numbers({"pnl": -630.0, "date": "2025-06-06T15:00:00"})
    assert {"630", "-630", "630.00", "2025", "6"} <= numbers
    assert "631" not in numbers


def test_episode_count_mentions_are_typed_for_semantic_scope_review():
    from src.agents.account_conversation import collect_episode_count_observations
    cited = [{"kind": "episode_detail", "value": {"episode_id": "owned", "date": "2025-04-04",
        "operation_counts": {"open_position": 1, "add_position": 2, "reduce_position": 2, "close_position": 1},
        "trade_counts": {"BUY": 3, "SELL": 3}}}]
    cases = [
        ("唯一高于前两次买入价的买入", "zh", "BUY", 2, 3),
        ("其中一次卖出发生在最后", "zh", "SELL", 1, 3),
        ("above the first two purchases", "en", "BUY", 2, 3),
        ("one of the sales happened last", "en", "SELL", 1, 3),
        ("整轮两次买入", "zh", "BUY", 2, 3),
    ]
    for text, language, operation, mentioned, total in cases:
        observations = collect_episode_count_observations(
            text, cited, paragraph_index=1, language=language)
        assert len(observations) == 1
        assert {key: value for key, value in observations[0].items() if key != "mention_context"} == {
            "observation_kind": "episode_operation_count_mention", "paragraph_index": 1,
            "language": language, "episode_id": "owned", "normalized_operation": operation,
            "mentioned_count": mentioned, "recorded_episode_total": total,
            "scope": "semantic_resolution_required"}
        assert observations[0]["mention_context"] in text
    assert collect_episode_count_observations(
        "3月买入价格4元", cited, paragraph_index=0, language="zh") == []
    unavailable_total = collect_episode_count_observations(
        "两次减仓", [{"kind": "episode_detail", "value": {"episode_id": "owned"}}],
        paragraph_index=0, language="zh")
    assert unavailable_total[0]["recorded_episode_total"] is None

    answer = ConversationAnswer.model_validate({"paragraphs": [{"kind": "fact",
        "text": {"zh": "整轮有999999次买入。", "en": "There were 999999 purchases in total."},
        "refs": ["episode"]}], "guides": []})
    record = {"ref": "episode", **cited[0]}
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(answer, {"episode": record}, ["episode"])


def test_explanatory_percentages_are_explicitly_sent_for_semantic_review(account_context):
    record, answer = concept_case(account_context)
    answer["paragraphs"][0]["text"] = {"zh": "超过60%。", "en": "Over 60%."}
    observations = validate_answer(ConversationAnswer.model_validate(answer),
        {record.ref: asdict(record)}, [record.ref])
    assert observations and observations[0]["percentages_to_verify"] == ["60%"]
    # A concept label does not exempt unsupported money from source checks.
    answer["paragraphs"][0]["text"]["zh"] = "持有999999元。"
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(ConversationAnswer.model_validate(answer), {record.ref: asdict(record)}, [record.ref])


def test_runtime_v2_dispatch_returns_verified_answer_and_context_catalog(monkeypatch, account_context):
    import time
    from types import SimpleNamespace
    from toujing_core_runtime.account_review import AccountReviewService
    record, answer = concept_case(account_context)
    model = ScriptedModel([("read_financial_concept", {"topic": "concentration"}),
                           "Explain the concept.", answer, {"issues": []}])
    service = AccountReviewService(SimpleNamespace())
    monkeypatch.setattr(service, "_source_with_fingerprint", lambda params: (copy.copy(account_context), "fixed"))
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: "fixed")
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime", lambda key: runtime(model))
    params = {**account_context.scope, "question": "风险资产是什么意思", "allow_model_review": True,
              "answer_version": "account_conversation_answer_v2"}
    try:
        public = service.context(params)
        assert record.ref in public["record_refs"]
        started = service.start(params)
        for _ in range(200):
            response = service.poll({**account_context.scope, "job_id": started["job_id"]})
            if response["status"] != "running":
                break
            time.sleep(.005)
        assert response["status"] == "complete"
        result = response["result"]
        assert result["source_fingerprint"] == "fixed"
        assert result["answer"]["version"] == params["answer_version"]
        assert result["read_refs"] == [record.ref]
        assert result["verification"] == "receipts_and_grounding_review_v1"
        followup = service._history(result["inference_id"], scope=account_context.scope, source_fingerprint="fixed")
        assert followup[0]["validated_structured_answer"] == result["answer"]
    finally:
        service.close()


def test_runtime_cancel_checks_owned_scope_and_stays_terminal(account_context):
    from concurrent.futures import Future
    from threading import Event
    from types import SimpleNamespace
    from toujing_core_runtime.account_review import AccountReviewService
    service = AccountReviewService(SimpleNamespace())
    cancelled = Event()
    service.jobs["job"] = {"scope": account_context.scope, "future": Future(), "cancelled": cancelled}
    try:
        with pytest.raises(ValueError, match="not_owned"):
            service.poll({**account_context.scope, "account_id": "foreign", "job_id": "job", "cancel": True})
        assert not cancelled.is_set()
        response = service.poll({**account_context.scope, "job_id": "job", "cancel": True})
        assert cancelled.is_set() and response["status"] == "stale"
        assert service.poll({**account_context.scope, "job_id": "job"}) == response
        assert not service.completed
    finally:
        service.close()


def test_conversation_projections_exclude_future_facts(monkeypatch):
    import test_account_review as existing
    build = existing.build_account_review_context
    built = []
    def with_conversation(*args, **kwargs):
        result = build(*args, **kwargs, include_conversation=True)
        built.append(result)
        return result
    monkeypatch.setattr(existing, "build_account_review_context", with_conversation)
    # Reuse the existing June cutoff fixture with future quantities/prices
    # changed to 1 billion, then verify the extra V2 records as well as V1.
    existing.test_account_builders_cut_off_future_executions_and_prices_once()
    assert len(built) == 2 and built[0].conversation_records
    assert {ref: asdict(r) for ref, r in built[0].conversation_records.items()} == {
        ref: asdict(r) for ref, r in built[1].conversation_records.items()}
