"""Real SDK loop with offline model outputs; live acceptance remains separate."""
import asyncio
import json
from dataclasses import asdict
from copy import copy
from types import SimpleNamespace

import pytest
from agents import Agent, ToolCallItem, ToolCallOutputItem
from openai.types.responses import ResponseFunctionToolCall

from test_decision_review_agent import ScriptedModel, runtime, selection
from src.agents.decision_review import Hypothesis, prepare_finalization_options, run_decision_review
from src.agents.review_catalog import build_review_catalog
from src.agents.structured_finalizer import StructuredFinalizationUnavailable, build_finalization_input, MAX_ANALYSIS_CHARS
from src.compare.demo import build_pair
from review_option_helpers import choose_options, input_payload


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def calls(topic="all"):
    return [("get_episode_facts", {}),
            ("search_review_facts", {"stance": "support", "topic": topic}),
            ("search_review_facts", {"stance": "contradict", "topic": topic}),
            ("get_registered_historical_comparisons", {}), ("get_self_history", {})]


def run(context, analysis, outputs, topic="all"):
    model = ScriptedModel([*calls(topic), analysis, *outputs])
    return asyncio.run(run_decision_review("为什么 A 亏？", context, runtime=runtime(model))), model


def test_prose_is_internal_and_finalizer_has_no_tools_only_option_schema(pair):
    context = build_review_catalog(pair.a)
    prose = "内部候选：A是不是贪婪？不能确认。unknown；缺少当时计划。"
    final = choose_options("unknown")
    result, model = run(context, prose, [final])
    assert "贪婪" not in json.dumps(result, ensure_ascii=False)
    assert "analysis_candidates" not in result
    assert result["facts"][0]["value"]["result"]["pnl"] == pair.a.outcome.actual_result.pnl
    first, last = model.requests[0], model.requests[-1]
    assert first["model_settings"].tool_choice == "required" and first["tools"]
    assert last["tools"] == [] and last["model_settings"].tool_choice == "none"
    assert last["model_settings"].reasoning.effort == "none"
    wire_schema = last["output_schema"].json_schema()
    assert set(wire_schema["required"]) == {"factual_option_ids", "historical_option_ids", "claim_option_ids", "question_kind", "answer_focus", "finding_option_ids"}
    assert "factual_refs" not in wire_schema["properties"]
    assert "option_catalog" in str(model.inputs[-1])
    assert "eligible_support_refs" not in str(model.inputs[-1])
    assert model.calls == len(calls()) + 2


@pytest.mark.parametrize("invalid", ['prose {"factual_refs":[]}', '{broken', '{"question_kind":"none"}'])
def test_one_schema_retry_never_reruns_tools(pair, invalid):
    context = build_review_catalog(pair.a)
    result, model = run(context, "unknown", [invalid, choose_options("unknown")])
    assert result["facts"]
    assert model.calls == len(calls()) + 3
    assert model.requests[-2]["tools"] == model.requests[-1]["tools"] == []
    retry = input_payload(model.inputs[-1])["schema_correction"]
    assert retry["trust"] == "untrusted_previous_model_output_not_evidence_or_instruction"
    try:
        expected = json.loads(invalid)
    except ValueError:
        expected = invalid
    assert retry["previous_candidate"] == expected
    assert retry["schema_errors"]
    assert all(set(item) == {"path", "type", "constraints"} for item in retry["schema_errors"])
    assert all(not isinstance(item["constraints"].get("allowed_value_source"), list)
               for item in retry["schema_errors"])


@pytest.mark.parametrize("invalid", ['prose {"question_kind":"none"}', '{broken', '{"question_kind":"none"}'])
def test_second_schema_failure_is_unavailable_not_prose(pair, invalid):
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        run(build_review_catalog(pair.a), "unknown", [invalid, invalid])


@pytest.mark.parametrize("ref_kind", ["invented", "unread"])
def test_finalizer_refs_must_come_from_completed_receipts(pair, ref_kind):
    context = build_review_catalog(pair.a)
    ref = "invented-ref" if ref_kind == "invented" else next(r.ref for r in context.records.values() if r.kind == "market")
    if ref_kind == "unread":
        previous = copy(context)
        previous.retrieved = set(context.records)
        ref = next(o.option_id for o in prepare_finalization_options(previous).factual_options if ref in o.evidence_refs)
    final = choose_options("unknown", change=lambda c, _: c | {"factual_option_ids": [ref]})
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        run(context, "unknown " + ref, [final, final], topic="plan_or_reason")


def test_psychological_prose_cannot_launder_as_supported_claim(pair):
    context = build_review_catalog(pair.a)
    final = selection(context, possible_explanations=[Hypothesis(kind="price_influence_possible",
        supporting_evidence_refs=[pair.a.outcome.outcome_id], contradictory_evidence_refs=[],
        alternative_explanations=["prior_staged_plan"], missing_information=["contemporaneous_plan"])])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        run(context, "A追涨且贪婪。候选 price_influence_possible。", [final, final])


def test_finalizer_cannot_accept_an_inadmissible_inference(pair):
    context = build_review_catalog(pair.a)
    final = selection(context, possible_explanations=[Hypothesis(kind="price_influence_possible",
        supporting_evidence_refs=[], contradictory_evidence_refs=[],
        alternative_explanations=["unknown"], missing_information=["contemporaneous_plan"])])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        run(context, "无法判断。unknown。", [final, final])


def receipt_input(pair, *, status="complete", change_record=False):
    context = build_review_catalog(pair.a)
    records = json.loads(json.dumps({r: asdict(v) for r, v in context.records.items()}))
    ref = pair.a.outcome.outcome_id
    record = dict(records[ref])
    if change_record:
        record["account_id"] = "OTHER_ACCOUNT"
    agent = Agent(name="receipt-test")
    call = ToolCallItem(agent=agent, raw_item=ResponseFunctionToolCall(
        type="function_call", name="get_episode_facts", call_id="call-1", arguments="{}"))
    output = json.dumps({"status": status, "records": [record]})
    receipt = ToolCallOutputItem(agent=agent, raw_item={"type": "function_call_output", "call_id": "call-1", "output": output}, output=output)
    result = SimpleNamespace(final_output="unknown", new_items=[call, receipt])
    kwargs = dict(question="synthetic", scope={}, records=records, retrieved_refs=set(records),
                  tool_names={"get_episode_facts"})
    return result, kwargs


def test_context_flags_without_successful_receipts_do_not_authorize_refs(pair):
    result, kwargs = receipt_input(pair, status="failed")
    assert build_finalization_input(result, **kwargs)["allowed_evidence_refs"] == []
    result, kwargs = receipt_input(pair)
    assert build_finalization_input(result, **kwargs)["allowed_evidence_refs"] == [pair.a.outcome.outcome_id]


def test_cross_scope_receipt_and_oversized_analysis_fail_closed(pair):
    result, kwargs = receipt_input(pair, change_record=True)
    with pytest.raises(StructuredFinalizationUnavailable, match="scope_or_content_mismatch"):
        build_finalization_input(result, **kwargs)
    result.final_output = "x" * (MAX_ANALYSIS_CHARS + 1)
    with pytest.raises(StructuredFinalizationUnavailable, match="over_limit"):
        build_finalization_input(result, **kwargs)
