"""Deterministic legality/expansion invariants; no network or financial formulas."""
import copy
from dataclasses import FrozenInstanceError, replace
import itertools
import json

import pytest
from agents.agent_output import AgentOutputSchema
from agents.exceptions import ModelBehaviorError
from jsonschema import Draft202012Validator

from src.agents.claim_contract import scope_of
from src.agents.claim_options import can_correct_choice
from src.agents.decision_review import (Hypothesis, ReviewSelection, ReviewVerificationError,
    prepare_finalization_options, expand_finalization, validate_finalization, verify_selection)
from src.agents.review_catalog import build_review_catalog
from src.agents.structured_finalizer import FinalizerOutputSchema
from src.compare.demo import build_pair
from test_decision_review_agent import note, selection
from test_review_claim_contract import positive_path_own  # Existing real Path fixture.
from test_review_semantic_correction import execute, model_for
from review_option_helpers import choose_options


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def read(context):
    context.retrieved.update(context.records)
    return context


def choice(options, *, kinds=("unknown",), facts=(), history=()):
    return options.choice_type(ReviewSelection)(
        factual_option_ids=[o.option_id for o in options.factual_options if set(o.evidence_refs) & set(facts)],
        historical_option_ids=[o.option_id for o in options.historical_options if set(o.evidence_refs) & set(history)],
        claim_option_ids=[next(o.option_id for o in options.claim_options if o.claim_kind == k) for k in kinds],
        question_kind="need_contemporaneous_records")


def test_comparison_context_contains_b_but_no_claim_option_can_use_b(pair):
    context = read(build_review_catalog(pair.a, comparison=pair, notes=(note(pair),)))
    options = prepare_finalization_options(context)
    b_refs = {r.ref for r in context.records.values() if scope_of(r) == scope_of(pair.b.episode)}
    assert {pair.a.outcome.outcome_id, pair.b.outcome.outcome_id, pair.comparison_id} == set(options.comparison_context.factual_refs)
    assert b_refs & {r for o in options.factual_options for r in o.evidence_refs}
    for option in options.claim_options:
        assert not b_refs & set(option.supporting_evidence_refs + option.contradictory_evidence_refs)
        assert option.claim_scope == scope_of(pair.a.episode)
    expanded = expand_finalization(choice(options), options)
    validate_finalization(expanded, context)
    assert pair.b.outcome.outcome_id in expanded.factual_refs
    assert pair.comparison_id in expanded.factual_refs


@pytest.mark.parametrize("state", ["missing", "unread", "insufficient", "wrong_subject", "wrong_account", "wrong_episode", "wrong_instrument", "complete"])
def test_user_reason_option_requires_complete_read_exact_scope(pair, state):
    context = read(build_review_catalog(pair.a, notes=() if state == "missing" else (note(pair, kind="reason"),)))
    if state == "unread":
        context.retrieved.remove("note-1")
    elif state == "insufficient":
        context.records["note-1"] = replace(context.records["note-1"], availability="insufficient_evidence")
    elif state.startswith("wrong_"):
        field = state.removeprefix("wrong_") + "_id"
        context.records["note-1"] = replace(context.records["note-1"], **{field: "unrelated"})
    options = prepare_finalization_options(context)
    assert ("user_reported_reason" in {o.claim_kind for o in options.claim_options}) == (state == "complete")
    if state == "complete":
        expanded = expand_finalization(choice(options, kinds=("user_reported_reason",)), options)
        validate_finalization(expanded, context)
        assert expanded.possible_explanations[0].supporting_evidence_refs == ["note-1"]
        assert expanded.possible_explanations[0].missing_information == ["independent_confirmation"]
        assert execute(context, model_for(context, [choose_options("user_reported_reason")]))["possible_explanations"][0]["kind"] == "user_reported_reason"


def test_unknown_is_terminal_uncertainty_with_factual_basis_not_evidence_roles(pair):
    context = read(build_review_catalog(pair.a, comparison=pair))
    options = prepare_finalization_options(context)
    unknown = next(o for o in options.claim_options if o.claim_kind == "unknown")
    assert unknown.supporting_evidence_refs == unknown.contradictory_evidence_refs == ()
    assert set(unknown.required_missing_information) == {"contemporaneous_plan", "reason_for_change"}
    with pytest.raises(ReviewVerificationError, match="roles"):
        replace(unknown, supporting_evidence_refs=(pair.a.outcome.outcome_id,))
    with pytest.raises(FrozenInstanceError):
        unknown.claim_kind = "user_reported_reason"
    expanded = expand_finalization(choice(options), options)
    assert len(expanded.factual_refs) == 3
    assert expanded.possible_explanations[0].missing_information


def test_all_options_and_supported_combinations_are_internally_valid(positive_path_own, pair):
    own_pair = replace(pair, a=positive_path_own)
    plan, reason = note(own_pair), note(own_pair, kind="reason") | {"note_id": "own-reason"}
    context = read(build_review_catalog(positive_path_own, notes=(plan, reason)))
    options = prepare_finalization_options(context)
    assert {o.claim_kind for o in options.claim_options} == {"unknown", "price_influence_possible", "planned_staging_possible", "user_reported_reason"}
    for case in options.validation_cases():
        verify_selection(ReviewSelection.model_validate(case), context)
    for option in options.claim_options:
        assert not set(option.supporting_evidence_refs) & set(option.contradictory_evidence_refs)
        assert all(scope_of(context.records[r]) == option.claim_scope
                   for r in option.supporting_evidence_refs + option.contradictory_evidence_refs)
    kinds = [o.claim_kind for o in options.claim_options if o.claim_kind != "unknown"]
    for size in range(1, len(kinds) + 1):
        for group in itertools.combinations(kinds, size):
            expanded = expand_finalization(choice(options, kinds=group), options)
            validate_finalization(expanded, context)
    price = next(o for o in options.claim_options if o.claim_kind == "price_influence_possible")
    assert price.contradictory_evidence_refs == ("note-1",)
    assert price.allowed_alternative_explanations == ("prior_staged_plan",)
    with pytest.raises(ReviewVerificationError, match="roles"):
        replace(price, contradictory_evidence_refs=price.supporting_evidence_refs)
    result = execute(context, model_for(context, [choose_options("price_influence_possible")]))
    assert result["possible_explanations"][0]["kind"] == "price_influence_possible"
    assert result["possible_explanations"][0]["contradictory_evidence_refs"] == ["note-1"]
    assert context.records["note-1"].value["temporal_kind"] == "retrospective"


def test_unread_mandatory_counter_material_makes_price_option_unavailable(positive_path_own, pair):
    context = read(build_review_catalog(positive_path_own, notes=(note(replace(pair, a=positive_path_own)),)))
    context.retrieved.remove("note-1")
    options = prepare_finalization_options(context)
    assert "price_influence_possible" not in {o.claim_kind for o in options.claim_options}
    assert "note-1" not in json.dumps(options.model_view())


@pytest.mark.parametrize("bad", ["nonexistent", "unexposed", "raw_ref", "raw_fields", "wrong_role"])
def test_wire_and_local_parser_both_reject_illegal_option_output(pair, bad):
    context = read(build_review_catalog(pair.a, notes=(note(pair),)))
    all_options = prepare_finalization_options(context)
    unexposed_id = next(o.option_id for o in all_options.claim_options if o.claim_kind == "planned_staging_possible")
    context.retrieved.remove("note-1")
    options = prepare_finalization_options(context)
    model_type = options.choice_type(ReviewSelection)
    raw = choice(options).model_dump()
    if bad == "raw_fields":
        raw["contradictory_evidence_refs"] = [pair.b.outcome.outcome_id]
    else:
        raw["claim_option_ids"] = [{"nonexistent": "claim_option_999", "unexposed": unexposed_id,
            "raw_ref": pair.b.outcome.outcome_id, "wrong_role": options.factual_options[0].option_id}[bad]]
    schema = FinalizerOutputSchema(model_type)
    assert list(Draft202012Validator(schema.json_schema()).iter_errors(raw))
    with pytest.raises(ModelBehaviorError):
        schema.validate_json(json.dumps(raw))
    # Even a forged typed instance cannot bypass the deterministic ID lookup.
    if bad != "raw_fields":
        with pytest.raises(ReviewVerificationError, match="option_not_exposed"):
            options.expand(model_type.model_construct(**raw))


@pytest.mark.parametrize("field", ["subject_id", "account_id", "episode_id", "instrument_id"])
def test_validator_still_rejects_manual_cross_scope_production_object(pair, field):
    context = read(build_review_catalog(pair.a))
    ref = next(r.ref for r in context.records.values() if r.kind == "decision")
    context.records[ref] = replace(context.records[ref], **{field: "unrelated"})
    h = Hypothesis(kind="unknown", supporting_evidence_refs=[ref], contradictory_evidence_refs=[],
                   alternative_explanations=[], missing_information=[])
    with pytest.raises(ReviewVerificationError, match="scope_mismatch"):
        validate_finalization(selection(context, possible_explanations=[h]), context)


def test_option_expansion_is_deterministic_and_public_schema_unchanged(pair):
    context = read(build_review_catalog(pair.a, comparison=pair))
    original_schema = AgentOutputSchema(ReviewSelection).json_schema()
    options = prepare_finalization_options(context)
    changed_order = copy.copy(context)
    changed_order.records = dict(reversed(list(context.records.items())))
    assert prepare_finalization_options(changed_order) == options
    picked = choice(options, facts=[o.evidence_refs[0] for o in options.factual_options[:3]])
    expanded = expand_finalization(picked, options)
    assert expanded == expand_finalization(picked, options)
    picked.factual_option_ids.reverse()
    assert expand_finalization(picked, options) == expanded
    assert set(expanded.factual_refs) <= context.retrieved
    assert AgentOutputSchema(ReviewSelection).json_schema() == original_schema


def test_historical_options_use_real_registered_receipts_never_direct_facts(tmp_path):
    from scripts.qa_decision_review_deepseek import prepare_context
    from toujing_core_runtime.product import ProductRuntime
    runtime = ProductRuntime(tmp_path / "options-qa.sqlite3")
    try:
        context = read(prepare_context(runtime))
        options = prepare_finalization_options(context)
        assert options.historical_options
        history = {r for o in options.historical_options for r in o.evidence_refs}
        assert not history & {r for o in options.factual_options for r in o.evidence_refs}
        assert not history & {r for o in options.claim_options for r in o.supporting_evidence_refs + o.contradictory_evidence_refs}
        expanded = expand_finalization(choice(options, history=history), options)
        validate_finalization(expanded, context)
        assert set(expanded.historical_comparison_refs) == history
        with pytest.raises(ReviewVerificationError, match="historical_hypothesis_is_not_actual_fact"):
            verify_selection(expanded.model_copy(update={"factual_refs": expanded.factual_refs + [next(iter(history))]}), context)
    finally:
        runtime.close()


def test_deterministic_bundle_bugs_never_authorize_semantic_correction(pair):
    context = read(build_review_catalog(pair.a))
    options = prepare_finalization_options(context)
    for code in ("evidence_scope_mismatch", "support_counter_material_overlap", "evidence_does_not_support_hypothesis"):
        assert not can_correct_choice(ReviewVerificationError(code), choice(options), options)
