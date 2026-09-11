"""Explicit product starters keep their goal without constraining free-form Q&A."""
import asyncio
import json

import pytest

from src.agents.decision_review import run_decision_review
from src.agents.review_answer import required_answer_focus
from test_decision_review_agent import ScriptedModel, runtime
from test_review_evidence_capacity import source_context
from review_option_helpers import input_payload


@pytest.mark.parametrize("question", [
    "这轮结果是怎样形成的，哪些操作值得回看？",
    " 这轮结果是怎样形成的, 哪些操作值得回看? ",
    "这轮结果是怎样形成的？",
    "How did this result develop, and which operations deserve a closer look?",
])
def test_explicit_whole_episode_starters_keep_their_goal(question):
    assert required_answer_focus(question) == "result_formation"


@pytest.mark.parametrize("question", ["5月8日减仓改变了什么？", "这轮结果是否和5月8日减仓有关？", "为什么我这次加仓？", "What did this reduction change?"])
def test_free_form_question_keeps_existing_focus_selection(question):
    assert required_answer_focus(question) is None


def test_both_ui_starters_are_registered():
    from pathlib import Path
    from src.agents import decision_review
    root = Path(decision_review.__file__).resolve().parents[2]
    code = (root / "apps/desktop/src/data/reviewAnswer.ts").read_text()
    for question in ("这轮结果是怎样形成的，哪些操作值得回看？",
                     "How did this result develop, and which operations deserve a closer look?"):
        assert question in code and required_answer_focus(question) == "result_formation"


def test_wrong_focus_uses_existing_single_format_retry_and_keeps_both_directions(source_context):
    def final(focus):
        def output(request):
            payload = input_payload(request["input"])
            assert payload["required_answer_focus"] == "result_formation"
            options = payload["option_catalog"]
            findings = [next(f["option_id"] for f in payload["answer_catalog"]
                            if f["kind"] == "local_comparison" and f["difference_direction"] == d)
                        for d in ("positive", "negative")]
            return json.dumps({"factual_option_ids": [o["option_id"] for o in options["factual_options"]],
                "historical_option_ids": [o["option_id"] for o in options["historical_options"]],
                "claim_option_ids": [next(o["option_id"] for o in options["claim_options"] if o["claim_kind"] == "unknown")],
                "answer_focus": focus, "finding_option_ids": findings, "question_kind": "none"})
        return output
    model = ScriptedModel(["内部候选，不能缩为一次减仓。", final("operation_impact"), final("result_formation")])
    result = asyncio.run(run_decision_review("这轮结果是怎样形成的，哪些操作值得回看？", source_context, runtime=runtime(model)))
    assert model.calls == 3
    assert result["answer"]["focus"] == "result_formation"
    assert {f["difference_direction"] for f in result["answer"]["findings"]} == {"positive", "negative"}
    assert len(result["facts"]) > 12 and len(result["historical_comparisons"]) > 4
    assert all(request["tools"] == [] for request in model.requests[-2:])
    assert all("answer_focus" not in request["output_schema"].json_schema()["properties"]
               for request in model.requests[-2:])
    correction = input_payload(model.inputs[-1])["schema_correction"]
    assert correction["previous_candidate"]["answer_focus"] == "operation_impact"
    assert correction["schema_errors"] == [{
        "path": "$.answer_focus", "type": "conflicting_fixed_field",
        "constraints": {"field_policy": "omit_code_owned_fixed_field"},
    }]


def test_fixed_focus_is_materialized_without_provider_echo(source_context):
    def final(request):
        payload = input_payload(request["input"])
        catalog = payload["option_catalog"]
        findings = [next(f["option_id"] for f in payload["answer_catalog"]
                         if f["kind"] == "local_comparison" and f["difference_direction"] == direction)
                    for direction in ("positive", "negative")]
        assert "answer_focus" not in request["output_schema"].json_schema()["properties"]
        return json.dumps({
            "factual_option_ids": [o["option_id"] for o in catalog["factual_options"]],
            "historical_option_ids": [o["option_id"] for o in catalog["historical_options"]],
            "claim_option_ids": [next(o["option_id"] for o in catalog["claim_options"]
                                      if o["claim_kind"] == "unknown")],
            "finding_option_ids": findings,
            "question_kind": "none",
        })
    model = ScriptedModel(["内部候选，不能缩为一次减仓。", final])
    result = asyncio.run(run_decision_review(
        "这轮结果是怎样形成的，哪些操作值得回看？", source_context, runtime=runtime(model)))
    assert result["answer"]["focus"] == "result_formation"
    assert len([request for request in model.requests if not request["tools"]]) == 1


def test_fixed_focus_semantic_correction_reuses_wire_selection(source_context):
    def final(directions):
        def output(request):
            payload = input_payload(request["input"])
            catalog = payload["option_catalog"]
            findings = [next(f["option_id"] for f in payload["answer_catalog"]
                             if f["kind"] == "local_comparison" and f["difference_direction"] == direction)
                        for direction in directions]
            return json.dumps({
                "factual_option_ids": [o["option_id"] for o in catalog["factual_options"]],
                "historical_option_ids": [o["option_id"] for o in catalog["historical_options"]],
                "claim_option_ids": [next(o["option_id"] for o in catalog["claim_options"]
                                          if o["claim_kind"] == "unknown")],
                "finding_option_ids": findings,
                "question_kind": "none",
            })
        return output
    model = ScriptedModel(["内部候选。", final(("positive",)), final(("positive", "negative"))])
    result = asyncio.run(run_decision_review(
        "这轮结果是怎样形成的，哪些操作值得回看？", source_context, runtime=runtime(model)))
    feedback = input_payload(model.inputs[-1])["semantic_correction"]
    assert feedback["code"] == "answer_relevant_comparison_or_counterexample_missing"
    assert feedback["json_path"] == "$.finding_option_ids"
    assert "answer_focus" not in feedback["previous_selection"]
    assert set(feedback["previous_selection"]) == set(model.requests[-1]["output_schema"].json_schema()["required"])
    assert {f["difference_direction"] for f in result["answer"]["findings"]} == {"positive", "negative"}
