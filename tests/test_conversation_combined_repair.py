"""One repair must see all defects on the same, already reference-valid answer."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test_account_review import account_context
from test_account_conversation import concept_case
from test_dsa_conversation import configured, response
from src.agents.dsa_conversation import run_dsa_conversation
from src.agents import account_conversation as conversation


def test_numeric_and_causal_defects_are_delivered_to_one_repair(monkeypatch, account_context):
    _, valid = concept_case(account_context)
    invalid = copy.deepcopy(valid)
    invalid["paragraphs"][0]["text"] = {
        "zh": "你的亏损主要来自999999元费用。",
        "en": "Your loss was mainly caused by fees of 999999.",
    }
    runtime, client, model = configured(monkeypatch, [
        response(calls=[("k", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain the records."),
    ], [invalid, {"issues": []}, valid, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("解释这个指标", account_context, runtime=runtime))
    assert result["answer"]["paragraphs"] == valid["paragraphs"]
    assert len(model.requests) == 4  # writer + judge + ONE repair + judge
    correction = json.dumps(model.requests[2]["input"], ensure_ascii=False)
    assert "numeric_errors" in correction and "999999" in correction
    assert "semantic_review" in correction and "primary causal contribution" in correction
    assert client.responses.create.call_count == 2  # no repeated research


def test_invalid_reference_never_reaches_semantic_judge(monkeypatch, account_context):
    _, valid = concept_case(account_context)
    invalid = copy.deepcopy(valid)
    invalid["paragraphs"][0]["refs"] = ["not-actually-read"]
    runtime, _, model = configured(monkeypatch, [
        response(calls=[("k", "read_financial_concept", {"topic": "concentration"})]),
        response("Explain the records."),
    ], [invalid, valid, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("解释这个指标", account_context, runtime=runtime))
    assert result["answer"]["paragraphs"] == valid["paragraphs"]
    assert len(model.requests) == 3  # invalid writer -> repair, not a judge of unread data


def test_second_candidate_cannot_drop_one_requested_technical_metric(monkeypatch):
    record = {"ref": "technical", "kind": "public_technical", "availability": "complete",
        "value": {"metrics": {
            "rsi_14": {"status": "available", "value": 56.7, "display_value": "56.70"},
            "macd_12_26_9": {"status": "available", "line": 9.0, "signal": 8.0,
                "histogram": 1.0, "display_value": {"line": "9.00", "signal": "8.00",
                    "histogram": "1.00"}},
        }}}
    invalid = conversation.ConversationAnswer.model_validate({"paragraphs": [
        {"kind": "fact", "refs": ["technical"],
            "text": {"zh": "RSI为56.70。", "en": "RSI is 56.70."}},
        {"kind": "fact", "refs": ["technical"],
            "text": {"zh": "MACD为999999。", "en": "MACD is 999999."}},
    ], "guides": []})
    writer = AsyncMock(side_effect=[invalid, invalid])
    judge = AsyncMock(return_value=conversation.GroundingReview(issues=[]))
    monkeypatch.setattr(conversation, "_structured", writer)
    local = SimpleNamespace(access_allowed=lambda: True, episode_display_ids={}, scope={"scope_kind": "account"},
        as_of="2026-09-10", data_tier="real_user")
    payload = {"allowed_evidence_refs": ["technical"], "executed_tool_receipts": [],
        "user_question": "请给出RSI和MACD的实际数值", "question_scope": local.scope}
    with pytest.raises(conversation.ConversationError, match="number_not_in_sources"):
        asyncio.run(conversation.finalize_account_conversation(payload["user_question"], local,
            runtime=SimpleNamespace(provider="test", model_name="test"), history=[],
            records={"technical": record}, payload=payload, report=lambda _: None,
            aggregate_validation_errors=True, grounding_checker=judge))
    assert writer.await_count == 2
    assert judge.await_count == 1  # no positive verdict over a locally pruned answer


def _episode_count_finalizer_inputs():
    record = {"ref": "episode", "kind": "episode_detail", "availability": "complete",
        "episode_id": "owned", "value": {"episode_id": "owned",
            "operation_counts": {"open_position": 1, "add_position": 2},
            "trade_counts": {"BUY": 3, "SELL": 1}}}
    local = SimpleNamespace(access_allowed=lambda: True, episode_display_ids={"owned": "shown"},
        scope={"scope_kind": "episode", "episode_id": "shown"}, as_of="2026-09-10",
        data_tier="real_user")
    payload = {"allowed_evidence_refs": ["episode"], "executed_tool_receipts": [],
        "user_question": "复盘买入", "question_scope": local.scope}
    runtime = SimpleNamespace(provider="test", model_name="test")
    return record, local, payload, runtime


def _count_answer(zh, en):
    return conversation.ConversationAnswer.model_validate({"paragraphs": [{"kind": "fact",
        "text": {"zh": zh, "en": en}, "refs": ["episode"]}], "guides": []})


def test_subset_count_mentions_reach_existing_judge_without_hard_rejection(monkeypatch):
    record, local, payload, runtime = _episode_count_finalizer_inputs()
    candidate = _count_answer(
        "唯一高于前两次买入价的买入发生在后面。",
        "The only buy above the first two purchases happened later.")
    writer = AsyncMock(return_value=candidate)
    judge = AsyncMock(return_value=conversation.GroundingReview(issues=[]))
    monkeypatch.setattr(conversation, "_structured", writer)
    result = asyncio.run(conversation.finalize_account_conversation(payload["user_question"], local,
        runtime=runtime, history=[], records={"episode": record}, payload=payload,
        report=lambda _: None, grounding_checker=judge))
    assert result["answer"]["paragraphs"] == candidate.model_dump()["paragraphs"]
    observations = judge.await_args.args[1]["numeric_observations"]
    assert [(item["language"], item["mentioned_count"], item["recorded_episode_total"])
            for item in observations] == [("zh", 2, 3), ("en", 2, 3)]


def test_wrong_whole_episode_count_is_repaired_by_same_semantic_judge(monkeypatch):
    record, local, payload, runtime = _episode_count_finalizer_inputs()
    wrong = _count_answer("整轮有两次买入。", "There were two purchases in total.")
    corrected = _count_answer("整轮有三次买入。", "There were three purchases in total.")
    writer = AsyncMock(side_effect=[wrong, corrected])
    judge = AsyncMock(side_effect=[conversation.GroundingReview(
        issues=["wrong_number_or_unit"], findings=[{"paragraph_index": 0,
            "problem": "The candidate states the whole-Episode total is two, but the cited record has three BUY operations."}]),
        conversation.GroundingReview(issues=[])])
    monkeypatch.setattr(conversation, "_structured", writer)
    result = asyncio.run(conversation.finalize_account_conversation(payload["user_question"], local,
        runtime=runtime, history=[], records={"episode": record}, payload=payload,
        report=lambda _: None, grounding_checker=judge))
    assert result["answer"]["paragraphs"] == corrected.model_dump()["paragraphs"]
    assert writer.await_count == judge.await_count == 2
    correction = writer.await_args_list[1].args[2]["correction"]
    assert correction["issues"] == "account_grounding:wrong_number_or_unit"
