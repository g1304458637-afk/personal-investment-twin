"""An early model stop must not skip mandatory evidence or bypass receipts."""
import asyncio
import json

import pytest

from src.agents import decision_review as review
from src.agents.review_catalog import build_review_catalog
from src.agents.structured_finalizer import StructuredFinalizationUnavailable
from src.compare.demo import build_pair
from test_decision_review_agent import ScriptedModel, runtime
from review_option_helpers import choose_options, input_payload


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def script_without_contradict():
    return [("get_episode_facts", {}),
            ("search_review_facts", {"stance": "support", "topic": "all"}),
            ("get_registered_historical_comparisons", {}), ("get_self_history", {}),
            "内部候选，不确认动机。", choose_options("unknown")]


def test_early_stop_completes_all_required_reads_once_without_extra_model_calls(pair):
    context = build_review_catalog(pair.a, comparison=pair)
    model = ScriptedModel(["内部候选，没有得到结论。", choose_options("unknown")])
    result = asyncio.run(review.run_decision_review("回看这轮", context, runtime=runtime(model)))
    payload = input_payload(model.inputs[-1])
    receipts = payload["executed_tool_receipts"]
    assert len(receipts) == 6
    assert {r["stance"] for r in receipts if r["tool_name"] == "search_review_facts"} == {"support", "contradict"}
    assert set(result["executed_tools"]) == {"get_episode_facts", "search_review_facts",
        "get_registered_historical_comparisons", "get_self_history", "get_same_stock_comparison"}
    assert model.calls == 2 and context.retrieved == context.searched == set()


@pytest.mark.parametrize("output", ['{"status":"failed","records":[]}', 'not a receipt', '{}'])
def test_failed_required_read_never_reaches_model_finalization(pair, monkeypatch, output):
    context = build_review_catalog(pair.a)
    original = review.search_review_facts.on_invoke_tool
    calls = []
    async def read(ctx, args):
        if json.loads(args)["stance"] == "contradict":
            calls.append(args)
            return output
        return await original(ctx, args)
    monkeypatch.setattr(review.search_review_facts, "on_invoke_tool", read)
    model = ScriptedModel(script_without_contradict())
    with pytest.raises(review.ReviewVerificationError, match="not_executed"):
        asyncio.run(review.run_decision_review("回看这轮", context, runtime=runtime(model)))
    assert len(calls) == 1 and model.calls == 5


def test_program_scheduled_receipt_cannot_launder_wrong_canonical_content(pair, monkeypatch):
    context = build_review_catalog(pair.a)
    original = review.search_review_facts.on_invoke_tool
    async def read(ctx, args):
        output = await original(ctx, args)
        if json.loads(args)["stance"] == "contradict":
            data = json.loads(output)
            data["records"][0]["account_id"] = "foreign-account"
            return json.dumps(data)
        return output
    monkeypatch.setattr(review.search_review_facts, "on_invoke_tool", read)
    model = ScriptedModel(script_without_contradict())
    with pytest.raises(StructuredFinalizationUnavailable, match="scope_or_content_mismatch"):
        asyncio.run(review.run_decision_review("回看这轮", context, runtime=runtime(model)))
    assert model.calls == 5


def test_revocation_prevents_completion_and_model_finalization(pair):
    context = build_review_catalog(pair.a)
    context.access_allowed = lambda: False
    model = ScriptedModel(["过早结束的候选。", choose_options("unknown")])
    with pytest.raises(review.ReviewVerificationError, match="expired_or_revoked"):
        asyncio.run(review.run_decision_review("回看这轮", context, runtime=runtime(model)))
    assert model.calls == 1


def test_direct_audit_still_rejects_unpaired_retrieval_flags(pair):
    from types import SimpleNamespace
    context = build_review_catalog(pair.a)
    context.retrieved.update(context.records)
    context.searched.update({"support", "contradict"})
    with pytest.raises(review.ReviewVerificationError, match="not_executed"):
        review._audit(SimpleNamespace(new_items=[]), context)
