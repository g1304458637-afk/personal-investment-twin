"""Real SDK, offline model: correction only reselects an immutable option catalog."""
import asyncio

import pytest
from agents.exceptions import ModelBehaviorError

from src.agents import decision_review as review
from src.agents.review_catalog import build_review_catalog
from src.agents.structured_finalizer import StructuredFinalizationUnavailable
from src.compare.demo import build_pair
from test_decision_review_agent import ScriptedModel, runtime, note
from review_option_helpers import choose_options, input_payload


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def model_for(context, outputs):
    tools = [("get_episode_facts", {}), ("search_review_facts", {"stance": "support", "topic": "all"}),
        ("search_review_facts", {"stance": "contradict", "topic": "all"}),
        ("get_registered_historical_comparisons", {}), ("get_self_history", {}), ("get_user_notes", {})]
    if context.comparison_id:
        tools.append(("get_same_stock_comparison", {}))
    return ScriptedModel([*tools, "user_reported_reason 只是候选，不能确认动机。", *outputs])


def execute(context, model):
    return asyncio.run(review.run_decision_review("为什么 A 亏而 B 赚？", context, runtime=runtime(model)))


def duplicate_fact(choice, catalog):
    return choice | {"factual_option_ids": [catalog["factual_options"][0]["option_id"]] * 2}


@pytest.mark.parametrize("failure", ["duplicate", "uncertainty_conflict"])
def test_one_semantic_correction_revalidates_same_catalog_without_tools(pair, monkeypatch, failure):
    context = build_review_catalog(pair.a, comparison=pair, notes=(note(pair),))
    bad = choose_options("unknown", change=duplicate_fact) if failure == "duplicate" else choose_options("unknown", "planned_staging_possible")
    audited, validated = [], []
    original_verify, original_audit = review.validate_finalization, review._audit
    def verify(value, local):
        validated.append(value)
        return original_verify(value, local)
    def audit(result, local):
        audited.append(result)
        return original_audit(result, local)
    monkeypatch.setattr(review, "validate_finalization", verify)
    monkeypatch.setattr(review, "_audit", audit)
    model = model_for(context, [bad, choose_options("unknown")])
    result = execute(context, model)
    assert len(validated) == 1  # Invalid combination cannot even expand to production refs.
    assert len(audited) == 2 and audited[0] is audited[1]
    assert result["possible_explanations"][0]["kind"] == "unknown"
    assert result["facts"][0]["value"]["result"]["pnl"] == pair.a.outcome.actual_result.pnl
    before, after = map(input_payload, model.inputs[-2:])
    feedback = after.pop("semantic_correction")
    assert feedback["code"] == ("duplicate_option_selection" if failure == "duplicate" else "uncertainty_option_conflict")
    assert after == before
    assert context.retrieved == set()
    assert model.requests[-1]["output_schema"].json_schema() == model.requests[-2]["output_schema"].json_schema()
    for request in model.requests[-2:]:
        assert request["tools"] == [] and request["model_settings"].tool_choice == "none"
        assert request["model_settings"].reasoning.effort == "none"


@pytest.mark.parametrize("failure", ["invented_option", "changed_scope", "invented_ref", "new_fact"])
def test_correction_cannot_escape_closed_choice_type(pair, failure):
    context = build_review_catalog(pair.a, comparison=pair)
    invalid = {"invented_option": {"claim_option_ids": ["claim_999"]},
        "changed_scope": {"scope": pair.b.episode.subject_id},
        "invented_ref": {"supporting_evidence_refs": ["invented-ref"]},
        "new_fact": {"profit": 99999}}[failure]
    repair = choose_options("unknown", change=lambda c, _: c | invalid)
    model = model_for(context, [choose_options("unknown", change=duplicate_fact), repair, repair])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        execute(context, model)
    assert len([r for r in model.requests if not r["tools"]]) == 3


def test_second_semantic_rejection_fails_closed_without_third_attempt(pair):
    context = build_review_catalog(pair.a)
    bad = choose_options("unknown", change=duplicate_fact)
    model = model_for(context, [bad, bad, choose_options("unknown")])
    with pytest.raises(review.ReviewVerificationError) as caught:
        execute(context, model)
    assert caught.value.issue.code == "duplicate_option_selection"
    assert caught.value.semantic_correction_exhausted is True
    assert len([r for r in model.requests if not r["tools"]]) == 2


@pytest.mark.parametrize("tool", ["get_episode_facts", "search_review_facts"])
def test_correction_cannot_execute_tools_or_retrieve(pair, tool):
    context = build_review_catalog(pair.a)
    model = model_for(context, [choose_options("unknown", change=duplicate_fact), (tool, {})])
    with pytest.raises(ModelBehaviorError):
        execute(context, model)
    assert model.requests[-1]["tools"] == []
    assert len([r for r in model.requests if not r["tools"]]) == 2


@pytest.mark.parametrize("order", ["format_first", "semantic_first"])
def test_format_and_semantic_budgets_are_independent(pair, order):
    context = build_review_catalog(pair.a)
    good, bad = choose_options("unknown"), choose_options("unknown", change=duplicate_fact)
    fenced = lambda request: "```json\n" + good(request) + "\n```"
    outputs = [fenced, bad, good] if order == "format_first" else [bad, fenced, good]
    model = model_for(context, outputs)
    assert execute(context, model)["possible_explanations"][0]["kind"] == "unknown"
    assert len([r for r in model.requests if not r["tools"]]) == 3
    assert "semantic_correction" in input_payload(model.inputs[-1])


def test_semantic_correction_does_not_reset_spent_format_budget(pair):
    context = build_review_catalog(pair.a)
    model = model_for(context, ["not JSON", choose_options("unknown", change=duplicate_fact), "still not JSON", choose_options("unknown")])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        execute(context, model)
    assert len([r for r in model.requests if not r["tools"]]) == 3


@pytest.mark.parametrize("field", ["supporting_evidence_refs", "contradictory_evidence_refs"])
def test_corrupted_expansion_is_still_rejected_by_authoritative_validator(pair, monkeypatch, field):
    context = build_review_catalog(pair.a, comparison=pair)
    original = review.expand_finalization
    def corrupt(choice, options):
        value = original(choice, options)
        setattr(value.possible_explanations[0], field, [pair.b.outcome.outcome_id])
        return value
    monkeypatch.setattr(review, "expand_finalization", corrupt)
    model = model_for(context, [choose_options("unknown")])
    with pytest.raises(review.ReviewVerificationError, match="evidence_scope_mismatch"):
        execute(context, model)
    # A broken deterministic bundle is not fixable by asking the LLM to retry.
    assert len([r for r in model.requests if not r["tools"]]) == 1


def test_every_option_is_validated_before_first_finalizer_call(pair, monkeypatch):
    context = build_review_catalog(pair.a, comparison=pair)
    verified = []
    original = review.verify_selection
    def verify(value, ctx):
        original(value, ctx)
        verified.append(value)
    monkeypatch.setattr(review, "verify_selection", verify)
    def choose(request):
        catalog = input_payload(request["input"])["option_catalog"]
        assert len(verified) == 1 + sum(len(catalog[k]) for k in ("factual_options", "historical_options", "claim_options"))
        return choose_options("unknown")(request)
    result = execute(context, model_for(context, [choose]))
    assert result["facts"] and len(verified) > 2
