"""Comparison navigation uses read canonical IDs and their local UI aliases."""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from src.agents import account_conversation as conversation


def record(kind="owned_same_stock_comparison"):
    return {"ref": "comparison", "kind": kind, "availability": "available",
        "value": {"comparison": {"earlier": {"episode_id": "internal-a"},
            "later": {"episode_id": "internal-b"}}}}


def test_three_decimal_and_four_decimal_percent_are_display_not_new_math():
    source = conversation._numbers({"weight": 34800 / 56160, "hhi": 0.45960260062824165})
    assert {"61.9658%", "61.966%", "0.460"} <= source
    assert "62.1234%" not in source


def test_comma_parameter_lists_and_iso_clocks_are_format_equivalent():
    assert conversation._numbers("MACD(12,26,9)") == {"12", "26", "9"}
    assert conversation._numbers("CNY 1,234,567.89") == {"1234567.89"}
    assert conversation._numbers("15:30") <= conversation._numbers("2026-08-21T15:30:00+08:00")
    assert "17" not in conversation._numbers("2026-08-21T15:30:00+08:00")


def answer(episode_id):
    return conversation.ConversationAnswer.model_validate({"paragraphs": [{
        "kind": "fact", "text": {"zh": "两轮分别展示。", "en": "The episodes are shown separately."},
        "refs": ["comparison"]}], "guides": [{"guide_id": "episode-process",
            "episode_id": episode_id, "label": {"zh": "查看这轮过程", "en": "View this episode"}}]})


def test_both_actually_read_comparison_episodes_can_be_opened():
    records = {"comparison": record()}
    assert conversation.read_episode_ids(records, records) == {"internal-a", "internal-b"}
    for episode_id in ("internal-a", "internal-b"):
        assert conversation.validate_answer(answer(episode_id), records, records) == []
    for episode_id in ("foreign", "display-a"):
        with pytest.raises(conversation.ConversationError, match="invalid_guide"):
            conversation.validate_answer(answer(episode_id), records, records)


def test_public_or_unread_nested_ids_cannot_authorize_navigation():
    records = {"comparison": record("public_search"), "unread": record()}
    assert conversation.read_episode_ids(records, ["comparison"]) == set()
    with pytest.raises(conversation.ConversationError, match="invalid_guide"):
        conversation.validate_answer(answer("internal-a"), records, ["comparison"])


@pytest.mark.parametrize("kind", ["public_search", "public_technical", "research_status", "knowledge"])
def test_external_root_ids_and_episode_arrays_cannot_authorize_navigation(kind):
    forged = record(kind)
    forged["episode_id"] = "internal-a"
    forged["value"]["episodes"] = [{"episode_id": "internal-a"}]
    assert conversation.read_episode_ids({"comparison": forged}, ["comparison"]) == set()
    candidate = answer("internal-a")
    if kind == "knowledge":
        candidate = candidate.model_copy(update={"paragraphs": [
            candidate.paragraphs[0].model_copy(update={"kind": "concept"})]})
    with pytest.raises(conversation.ConversationError, match="invalid_guide"):
        conversation.validate_answer(candidate, {"comparison": forged}, ["comparison"])


def test_alias_map_is_passed_to_writer_and_judge_only_for_read_ids(monkeypatch):
    records = {"comparison": record()}
    local = SimpleNamespace(episode_display_ids={"internal-a": "display-a",
        "internal-b": "display-b", "unread-c": "display-c"}, access_allowed=lambda: True,
        scope={}, as_of="2025-12-31", data_tier="Synthetic")
    payload = {"allowed_evidence_refs": ["comparison"], "executed_tool_receipts": [],
        "user_question": "Compare display-a and display-b"}
    captured = {}
    async def writer(runtime, instructions, value, schema, access):
        captured["writer"] = copy.deepcopy(value)
        result = answer("internal-b").model_dump()
        result["paragraphs"][0]["refs"] = ["R001"]
        return conversation.ConversationAnswer.model_validate(result)
    async def judge(runtime, value, access):
        captured["judge"] = copy.deepcopy(value)
        return conversation.GroundingReview(issues=[])
    monkeypatch.setattr(conversation, "_structured", writer)
    asyncio.run(conversation.finalize_account_conversation("Compare display-a and display-b", local,
        runtime=SimpleNamespace(provider="test", model_name="test"), history=[], records=records,
        payload=payload, report=lambda _: None, grounding_checker=judge))
    for stage in ("writer", "judge"):
        assert captured[stage]["read_episode_aliases"] == {
            "internal-a": "display-a", "internal-b": "display-b"}
        assert "display-c" not in str(captured[stage])
