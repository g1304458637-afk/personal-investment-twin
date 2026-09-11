"""Real Synthetic runtime facts + scripted SDK choices, not live-model quality QA."""
import asyncio
import copy
import json
from dataclasses import replace

import pytest

from src.agents.decision_review import run_decision_review, prepare_finalization_options, ReviewSelection
from src.agents.review_answer import (build_answer_options, answer_choice_type, compose_answer,
                                      include_answer_refs, LOCAL, FULL)
from src.agents.claim_contract import ReviewVerificationError
from src.agents.structured_finalizer import StructuredFinalizationUnavailable
from toujing_core_runtime.product import ProductRuntime
from test_desktop_demo_review import scope
from test_decision_review_agent import ScriptedModel, runtime
from review_option_helpers import choose_options, input_payload
from src.agents.review_catalog import build_review_catalog
from src.compare.demo import build_pair
from test_decision_review_agent import execute


@pytest.fixture(scope="module")
def story_context(tmp_path_factory):
    product = ProductRuntime(tmp_path_factory.mktemp("answer-v2") / "qa.sqlite3")
    try:
        params, _ = scope("product-story")
        yield product.review_runtime()._context(params)[0]
    finally:
        product.close()


def cf_ref(context, day, scenario=LOCAL):
    return next(r.ref for r in context.records.values() if r.kind == "historical_comparison"
                and r.value["decision_at"].startswith(day) and r.value["scenario_id"] == scenario)


def choose_answer(focus, refs):
    def output(request):
        payload = input_payload(request["input"])
        base = json.loads(choose_options("unknown")(request))
        by_ref = {o["evidence_ref"]: o["option_id"] for o in payload["answer_catalog"]}
        return json.dumps(base | {"answer_focus": focus, "question_kind": "none",
                                  "finding_option_ids": [by_ref[r] for r in refs]})
    return output


def run(context, final, *, extra=(), omit_contradict=False, prose="内部候选：依据局部比较，不确定动机。"):
    steps = [("get_episode_facts", {}), ("search_review_facts", {"stance": "support", "topic": "all"})]
    if not omit_contradict:
        steps.append(("search_review_facts", {"stance": "contradict", "topic": "all"}))
    steps += [("get_registered_historical_comparisons", {}), ("get_self_history", {}), prose, final, *extra]
    model = ScriptedModel(steps)
    return asyncio.run(run_decision_review("这轮为什么亏损？", context, runtime=runtime(model))), model


def test_real_runtime_result_and_opposite_local_comparisons_reach_answer(story_context):
    refs = [cf_ref(story_context, "2025-02-20"), cf_ref(story_context, "2025-03-18")]
    result, model = run(story_context, choose_answer("result_formation", refs))
    assert result["version"] == "evidence_grounded_review_v2"
    answer = result["answer"]
    assert "-283.50 CNY" in answer["summary"]["zh"]
    assert [f["evidence_ref"] for f in answer["findings"]] == refs
    first, second = answer["findings"]
    for value in ("2025-03-17", "2025-03-18", "-770.50", "-256.00", "514.50"):
        assert value in first["body"]["zh"]
    assert "-48.00" in second["body"]["zh"]
    assert "不能相加" in answer["qualification"]["zh"]
    assert set(refs) <= {r["ref"] for r in result["historical_comparisons"]}
    assert not set(refs) & {r["ref"] for r in result["facts"]}
    assert not story_context.retrieved
    assert model.requests[0]["model_settings"].tool_choice == "required"
    assert model.requests[-1]["tools"] == []
    assert model.requests[-1]["model_settings"].reasoning.effort == "none"


def test_only_supporting_loss_story_requires_bounded_reselection(story_context):
    add, reduce = cf_ref(story_context, "2025-02-20"), cf_ref(story_context, "2025-03-18")
    result, model = run(story_context, choose_answer("result_formation", [add]),
                        extra=[choose_answer("result_formation", [add, reduce])])
    assert len(result["answer"]["findings"]) == 2
    assert model.calls == 8
    assert all(not request["tools"] for request in model.requests[-2:])
    assert "answer_relevant_comparison_or_counterexample_missing" in str(model.inputs[-1])


def test_repeated_one_sided_answer_fails_closed(story_context):
    bad = choose_answer("result_formation", [cf_ref(story_context, "2025-02-20")])
    with pytest.raises(ReviewVerificationError, match="counterexample_missing"):
        run(story_context, bad, extra=[bad])


def test_specific_operation_keeps_local_and_infeasible_full_horizon(story_context):
    refs = [cf_ref(story_context, "2025-02-20"), cf_ref(story_context, "2025-02-20", FULL)]
    result, _ = run(story_context, choose_answer("operation_impact", refs))
    block = result["answer"]["findings"][1]
    assert block["kind"] == "infeasible_comparison"
    assert "没有这个假设的整轮结果" in block["body"]["zh"]
    assert refs[1] not in {r["ref"] for r in result["historical_comparisons"]}


def test_hiding_known_full_horizon_failure_is_rejected(story_context):
    bad = choose_answer("operation_impact", [cf_ref(story_context, "2025-02-20")])
    with pytest.raises(ReviewVerificationError, match="infeasibility_missing"):
        run(story_context, bad, extra=[bad])


def test_internal_psychology_and_prose_never_become_answer(story_context):
    refs = [cf_ref(story_context, "2025-02-20"), cf_ref(story_context, "2025-03-18")]
    result, _ = run(story_context, choose_answer("result_formation", refs), prose="A贪婪追涨，亏损全因恐惧！")
    output = json.dumps(result["answer"], ensure_ascii=False)
    assert not any(label in output for label in ("贪婪", "追涨", "恐惧"))


def test_required_receipt_completion_still_precedes_answer(story_context):
    final = choose_answer("result_formation", [cf_ref(story_context, "2025-02-20"), cf_ref(story_context, "2025-03-18")])
    result, model = run(story_context, final, omit_contradict=True)
    from review_option_helpers import input_payload
    assert any(r["stance"] == "contradict" for r in input_payload(model.inputs[-1])["executed_tool_receipts"])
    assert len(result["answer"]["findings"]) == 2


@pytest.mark.parametrize("bad", ["prose {\"answer_focus\":\"result_formation\"}", "{broken",
                                '{"finding_option_ids":["invented"]}'])
def test_strict_final_schema_failure_does_not_show_prose(story_context, bad):
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        run(story_context, bad, extra=[bad])


@pytest.mark.parametrize("mutation", ["unread", "subject_id", "account_id", "episode_id", "instrument_id"])
def test_options_exclude_unread_or_foreign_records(story_context, mutation):
    context = copy.copy(story_context)
    context.records = dict(context.records)
    context.retrieved = set(context.records)
    ref = cf_ref(context, "2025-02-20")
    if mutation == "unread":
        context.retrieved.remove(ref)
    else:
        context.records[ref] = replace(context.records[ref], **{mutation: "other"})
    assert ref not in {o.evidence_ref for o in build_answer_options(context)}


def test_model_cannot_add_amount_or_free_claim_to_wire_schema(story_context):
    context = copy.copy(story_context)
    context.retrieved = set(context.records)
    options = prepare_finalization_options(context)
    schema = answer_choice_type(options.choice_type(ReviewSelection), build_answer_options(context)).model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"factual_option_ids", "historical_option_ids", "claim_option_ids",
                                         "question_kind", "answer_focus", "finding_option_ids"}


def test_authorized_counterpart_outcome_stays_visible_with_own_period():
    pair = build_pair()
    result, _ = execute(build_review_catalog(pair.a, comparison=pair), choose_options("unknown"))
    summaries = result["answer"]["comparison_summary"]
    assert len(summaries) == 1
    assert f"{pair.b.outcome.actual_result.pnl:,.2f} CNY" in summaries[0]["zh"]
    assert "不是共同区间" in summaries[0]["zh"]


def test_changed_finding_cannot_bypass_canonical_content_check(story_context):
    context = copy.copy(story_context)
    context.retrieved = set(context.records)
    options = build_answer_options(context)
    claims = prepare_finalization_options(context)
    choice_type = answer_choice_type(claims.choice_type(ReviewSelection), options)
    choice = choice_type(factual_option_ids=[], historical_option_ids=[],
        claim_option_ids=[next(c.option_id for c in claims.claim_options if c.claim_kind == "unknown")],
        question_kind="none", answer_focus="decision_reason", finding_option_ids=[options[0].option_id])
    selection = ReviewSelection.model_validate(claims.expand(choice))
    altered = (replace(options[0], body={"zh": "编造的金额", "en": "Invented amount"}), *options[1:])
    with pytest.raises(ReviewVerificationError, match="changed_or_unread"):
        compose_answer(choice, altered, include_answer_refs(choice, options, selection, context), context)
