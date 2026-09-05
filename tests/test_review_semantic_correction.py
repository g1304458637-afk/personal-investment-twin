"""Real SDK with offline scripted responses; tests constraints, not live stability."""
import asyncio
import json
from dataclasses import replace

import pytest
from agents.agent_output import AgentOutputSchema
from agents.exceptions import ModelBehaviorError
from jsonschema import Draft202012Validator

from src.agents import decision_review as review
from src.agents.claim_contract import build_claim_candidates
from src.agents.review_catalog import build_review_catalog
from src.agents.structured_finalizer import FinalizerOutputSchema, StructuredFinalizationUnavailable
from src.compare.demo import build_pair
from test_decision_review_agent import ScriptedModel, runtime, selection, note


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def unknown():
    return review.Hypothesis(kind="unknown", supporting_evidence_refs=[], contradictory_evidence_refs=[],
        alternative_explanations=["unknown"], missing_information=["contemporaneous_plan"])


def unsupported_reason():
    return unknown().model_copy(update={"kind": "user_reported_reason"})


def candidate(context, explanation):
    return selection(context, possible_explanations=[explanation])


def model_for(context, outputs):
    tools = [("get_episode_facts", {}), ("search_review_facts", {"stance": "support", "topic": "all"}),
        ("search_review_facts", {"stance": "contradict", "topic": "all"}),
        ("get_registered_historical_comparisons", {}), ("get_self_history", {}), ("get_user_notes", {})]
    if context.comparison_id:
        tools.append(("get_same_stock_comparison", {}))
    # An unverified kind token is no longer permission to emit that kind.
    return ScriptedModel([*tools, "user_reported_reason 只是候选，实际没有用户理由。不能确认动机。", *outputs])


def execute(context, model):
    return asyncio.run(review.run_decision_review("为什么 A 亏而 B 赚？", context, runtime=runtime(model)))


def input_payload(raw):
    if isinstance(raw, list):
        raw = raw[0]["content"]
    # Decode QA INPUT only; an appended fixed format-retry notice is not model output.
    return json.JSONDecoder().raw_decode(raw)[0]


@pytest.mark.parametrize("role", ["supporting_evidence_refs", "contradictory_evidence_refs"])
def test_candidate_scope_excludes_counterpart_but_comparison_permits_it(pair, role):
    context = build_review_catalog(pair.a, comparison=pair)
    space = build_claim_candidates(context, set(context.records))
    b_ref = pair.b.outcome.outcome_id
    assert b_ref in space["comparison_context"]["eligible_factual_refs"]
    assert len(space["comparison_context"]["authorized_scopes"]) == 2
    assert space["claim_scope"]["episode_id"] == pair.a.episode.episode_id
    for explanation in space["explanations"].values():
        assert b_ref not in explanation["eligible_support_refs"]
        assert b_ref not in explanation["eligible_contradictory_refs"]
    wire = FinalizerOutputSchema(review.ReviewSelection, space)
    invalid = candidate(context, unknown().model_copy(update={role: [b_ref]}))
    assert list(Draft202012Validator(wire.json_schema()).iter_errors(invalid.model_dump()))
    # Valid production shape + invalid per-run semantics must not spend FORMAT budget.
    assert wire.validate_json(invalid.model_dump_json()) == invalid
    valid = selection(context, factual_refs=[pair.a.outcome.outcome_id, b_ref, pair.comparison_id])
    assert not list(Draft202012Validator(wire.json_schema()).iter_errors(valid.model_dump()))
    result = execute(context, model_for(context, [valid]))
    assert b_ref in {fact["ref"] for fact in result["facts"]}


@pytest.mark.parametrize("state", ["missing", "unread", "insufficient", "wrong_subject", "wrong_episode", "complete"])
def test_reason_admission_requires_read_complete_own_scoped_testimony(pair, state):
    notes = () if state == "missing" else (note(pair, "我当时的理由", "reason"),)
    context = build_review_catalog(pair.a, notes=notes)
    if state in {"insufficient", "wrong_subject", "wrong_episode"}:
        changes = {"insufficient": {"availability": "insufficient_evidence"},
                   "wrong_subject": {"subject_id": pair.b.episode.subject_id},
                   "wrong_episode": {"episode_id": pair.b.episode.episode_id}}[state]
        context.records["note-1"] = replace(context.records["note-1"], **changes)
    read = set(context.records) - ({"note-1"} if state == "unread" else set())
    space = build_claim_candidates(context, read)
    assert ("user_reported_reason" in space["admissible_claim_kinds"]) == (state == "complete")
    assert ("user_reported_reason" in space["explanations"]) == (state == "complete")
    if state == "complete":
        reason = space["explanations"]["user_reported_reason"]
        assert reason["eligible_support_refs"] == ["note-1"]
        assert reason["required_missing_information"] == ["independent_confirmation"]
        claim = unsupported_reason().model_copy(update={"supporting_evidence_refs": ["note-1"],
                                                       "missing_information": ["independent_confirmation"]})
        assert execute(context, model_for(context, [candidate(context, claim)]))["possible_explanations"][0]["kind"] == "user_reported_reason"


@pytest.mark.parametrize("failure", ["cross_scope", "unsupported_kind"])
def test_one_semantic_correction_revalidates_same_catalog_without_tools(pair, monkeypatch, failure):
    context = build_review_catalog(pair.a, comparison=pair)
    bad = unsupported_reason() if failure == "unsupported_kind" else unknown().model_copy(
        update={"contradictory_evidence_refs": [pair.b.outcome.outcome_id]})
    initial, corrected = candidate(context, bad), candidate(context, unknown())
    validated, audited = [], []
    original_verify, original_audit = review.verify_selection, review._audit
    def verify(value, local):
        validated.append(value)
        return original_verify(value, local)
    def audit(result, local):
        audited.append(result)
        return original_audit(result, local)
    monkeypatch.setattr(review, "verify_selection", verify)
    monkeypatch.setattr(review, "_audit", audit)
    model = model_for(context, [initial, corrected])
    result = execute(context, model)
    assert validated == [initial, corrected]
    assert len(audited) == 2 and audited[0] is audited[1]
    assert result["possible_explanations"][0]["kind"] == "unknown"
    assert result["facts"][0]["value"]["result"]["pnl"] == pair.a.outcome.actual_result.pnl
    before, after = map(input_payload, model.inputs[-2:])
    feedback = after.pop("semantic_correction")
    assert feedback["code"] == ("evidence_scope_mismatch" if failure == "cross_scope" else "evidence_does_not_support_hypothesis")
    assert after == before  # Includes exact catalog, allowed refs, claim scope and candidates.
    assert context.retrieved == set()
    for request in model.requests[-2:]:
        assert request["tools"] == []
        assert request["model_settings"].tool_choice == "none"
        assert request["model_settings"].reasoning.effort == "none"


@pytest.mark.parametrize("failure", ["invented", "changed_scope", "repeated"])
def test_invalid_correction_fails_closed_without_third_attempt(pair, failure):
    context = build_review_catalog(pair.a, comparison=pair)
    initial = candidate(context, unsupported_reason())
    if failure == "invented":
        repaired = unknown().model_copy(update={"supporting_evidence_refs": ["invented-ref"]})
    elif failure == "changed_scope":
        repaired = unknown().model_copy(update={"supporting_evidence_refs": [pair.b.outcome.outcome_id]})
    else:
        repaired = unsupported_reason()
    model = model_for(context, [initial, candidate(context, repaired), candidate(context, unknown())])
    with pytest.raises(review.ReviewVerificationError) as caught:
        execute(context, model)
    assert caught.value.semantic_correction_exhausted is True
    assert len([r for r in model.requests if not r["tools"]]) == 2


def test_correction_cannot_execute_requested_tool(pair):
    context = build_review_catalog(pair.a)
    model = model_for(context, [candidate(context, unsupported_reason()), ("get_episode_facts", {})])
    with pytest.raises(ModelBehaviorError):
        execute(context, model)
    assert model.requests[-1]["tools"] == []
    assert len([r for r in model.requests if not r["tools"]]) == 2


@pytest.mark.parametrize("order", ["format_first", "semantic_first"])
def test_format_and_semantic_budgets_are_independent(pair, order):
    context = build_review_catalog(pair.a)
    good, bad = candidate(context, unknown()), candidate(context, unsupported_reason())
    fenced = "```json\n" + good.model_dump_json() + "\n```"
    outputs = [fenced, bad, good] if order == "format_first" else [bad, fenced, good]
    model = model_for(context, outputs)
    assert execute(context, model)["possible_explanations"][0]["kind"] == "unknown"
    assert len([r for r in model.requests if not r["tools"]]) == 3
    assert "semantic_correction" in input_payload(model.inputs[-1])


def test_semantic_correction_does_not_reset_spent_format_budget(pair):
    context = build_review_catalog(pair.a)
    good, bad = candidate(context, unknown()), candidate(context, unsupported_reason())
    model = model_for(context, ["not JSON", bad, "still not JSON", good])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation_failed"):
        execute(context, model)
    assert len([r for r in model.requests if not r["tools"]]) == 3


def test_narrowing_does_not_mutate_production_schema(pair):
    original = AgentOutputSchema(review.ReviewSelection).json_schema()
    context = build_review_catalog(pair.a)
    space = build_claim_candidates(context, set(context.records))
    constrained = FinalizerOutputSchema(review.ReviewSelection, space).json_schema()
    assert constrained["$defs"]["Hypothesis"]["properties"]["kind"]["enum"] == ["unknown"]
    assert AgentOutputSchema(review.ReviewSelection).json_schema() == original
