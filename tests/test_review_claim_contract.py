"""Deterministic claim/evidence relationship checks for decision review.

These tests deliberately use real Path observations.  A review claim must not
be made valid by adding a convenient tag to an unrelated record.
"""

from dataclasses import replace

import pandas as pd
import pytest

from src.agents.claim_contract import build_claim_contract
from src.agents.decision_review import (
    Hypothesis,
    ReviewSelection,
    ReviewVerificationError,
    verify_selection,
)
from src.agents.review_catalog import build_review_catalog
from src.compare.demo import AS_OF, INSTRUMENT, build_pair, pair_inputs
from src.compare.same_stock import build_episode_compare_facts


@pytest.fixture(scope="module")
def pair():
    return build_pair()


@pytest.fixture(scope="module")
def positive_path_own(pair):
    """Use the established two-observation timing that emits the real pattern."""
    frames, prices = pair_inputs()
    frame = frames["A"].copy()
    frame.loc[1, "event_time"] = prices.date.iloc[3] + pd.Timedelta(hours=10)
    frame.loc[2, "event_time"] = prices.date.iloc[5] + pd.Timedelta(hours=10)
    return build_episode_compare_facts(
        frame,
        prices,
        subject_id=pair.a.episode.subject_id,
        account_id=pair.a.episode.account_id,
        instrument=INSTRUMENT,
        as_of=AS_OF,
        init_cash=100_000,
        data_tier="synthetic",
    )


def _selection(context, *, factual_refs=None, explanations=()):
    return ReviewSelection(
        factual_refs=factual_refs or [context.own.outcome.outcome_id],
        historical_comparison_refs=[],
        possible_explanations=list(explanations),
        question_kind="need_contemporaneous_records",
    )


def _positive_pattern(context):
    return next(
        record
        for record in context.records.values()
        if record.kind == "path" and "add_after_positive_market_move" in record.tags
    )


def _price_claim(pattern_ref, *, contradictory=(), missing=("contemporaneous_plan",)):
    return Hypothesis(
        kind="price_influence_possible",
        supporting_evidence_refs=[pattern_ref],
        contradictory_evidence_refs=list(contradictory),
        alternative_explanations=["prior_staged_plan"],
        missing_information=list(missing),
    )


def _retrieve_all(context):
    context.retrieved.update(context.records)
    return context


def _assert_issue(exc_info, *, code=None, path_contains=None):
    issue = exc_info.value.issue
    if code is not None:
        expected_codes = (code,) if isinstance(code, str) else code
        assert issue.code in expected_codes
    if path_contains is not None:
        assert path_contains in issue.json_path
    assert isinstance(issue.expected_rule, str)
    return issue


def _plan_note(own, *, note_id="note-plan-1", note_kind="plan"):
    episode = own.episode
    return {
        "note_id": note_id,
        "subject_id": episode.subject_id,
        "account_id": episode.account_id,
        "episode_id": episode.episode_id,
        "decision_id": None,
        "source": "user",
        "note_kind": note_kind,
        "text": "建仓之前已有分批计划",
        "authored_at": "2026-09-05T12:00:00+00:00",
        "recorded_at": "2026-09-05T12:00:00+00:00",
        "temporal_kind": "retrospective",
    }


def test_valid_factual_and_descriptive_path_record_pass_without_changing_numbers(positive_path_own):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)
    pnl_before = context.records[positive_path_own.outcome.outcome_id].value["result"]["pnl"]

    verify_selection(
        _selection(
            context,
            factual_refs=[positive_path_own.outcome.outcome_id, pattern.ref],
            explanations=[_price_claim(pattern.ref)],
        ),
        context,
    )

    assert context.records[positive_path_own.outcome.outcome_id].value["result"]["pnl"] == pnl_before
    assert pattern.value["pattern_code"] == "add_after_positive_market_move"
    assert pattern.value["facts"]["price_return"] > 0


def test_default_timing_has_no_authoritative_positive_path_and_rejects_price_inference(pair):
    context = _retrieve_all(build_review_catalog(pair.a))
    assert not any("add_after_positive_market_move" in record.tags for record in context.records.values())
    rule = build_claim_contract(context, set(context.retrieved))["price_influence_possible"]
    assert rule["eligible_support_refs"] == []
    assert rule["available"] is False
    add_decision = next(
        record.ref
        for record in context.records.values()
        if record.kind == "decision" and "add_position" in record.tags
    )

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[_price_claim(add_decision)]), context)

    _assert_issue(
        exc_info,
        code="evidence_does_not_support_hypothesis",
        path_contains="possible_explanations[0].supporting_evidence_refs",
    )


def test_real_positive_path_pattern_is_eligible_and_price_inference_passes(positive_path_own):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)
    contract = build_claim_contract(context, {pattern.ref})

    assert pattern.ref in contract["price_influence_possible"]["eligible_support_refs"]
    assert contract["price_influence_possible"]["available"] is True
    verify_selection(_selection(context, explanations=[_price_claim(pattern.ref)]), context)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("kind", "decision"),
        ("availability", "insufficient_evidence"),
        ("episode_id", "foreign-episode"),
        ("instrument_id", "foreign-instrument"),
    ],
)
def test_wrong_record_type_status_or_exact_scope_is_not_support(
    positive_path_own, field, replacement
):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)
    context.records[pattern.ref] = replace(pattern, **{field: replacement})

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[_price_claim(pattern.ref)]), context)

    _assert_issue(
        exc_info,
        code=("evidence_does_not_support_hypothesis", "evidence_scope_mismatch"),
        path_contains="possible_explanations[0].supporting_evidence_refs",
    )


@pytest.mark.parametrize(
    ("embedded_field", "replacement"),
    [
        ("episode_id", "foreign-episode"),
        ("pattern_code", "consecutive_scaling_in"),
    ],
)
def test_wrong_embedded_path_episode_or_code_is_not_support(
    positive_path_own, embedded_field, replacement
):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)
    value = dict(pattern.value)
    value[embedded_field] = replacement
    context.records[pattern.ref] = replace(pattern, value=value)

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[_price_claim(pattern.ref)]), context)

    _assert_issue(
        exc_info,
        code="evidence_does_not_support_hypothesis",
        path_contains="possible_explanations[0].supporting_evidence_refs",
    )


def test_one_valid_and_one_foreign_support_ref_does_not_hide_foreign_evidence(positive_path_own):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)
    foreign_ref = "foreign-positive-path"
    foreign_value = dict(pattern.value)
    foreign_value["episode_id"] = "foreign-episode"
    context.records[foreign_ref] = replace(
        pattern,
        ref=foreign_ref,
        episode_id="foreign-episode",
        value=foreign_value,
    )
    context.retrieved.add(foreign_ref)
    claim = _price_claim(pattern.ref).model_copy(
        update={"supporting_evidence_refs": [pattern.ref, foreign_ref]}
    )

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[claim]), context)

    issue = _assert_issue(
        exc_info,
        code=("evidence_does_not_support_hypothesis", "evidence_scope_mismatch"),
        path_contains="possible_explanations[0].supporting_evidence_refs",
    )
    assert foreign_ref in issue.refs


def test_known_prior_plan_is_required_counter_material(positive_path_own):
    note = _plan_note(positive_path_own)
    context = _retrieve_all(build_review_catalog(positive_path_own, notes=(note,)))
    pattern = _positive_pattern(context)
    contract = build_claim_contract(context, set(context.retrieved))
    rule = contract["price_influence_possible"]
    assert note["note_id"] in rule["required_counter_material_refs"]

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[_price_claim(pattern.ref)]), context)
    _assert_issue(
        exc_info,
        code="contrary_plan_not_addressed",
        path_contains="possible_explanations[0].contradictory_evidence_refs",
    )

    verify_selection(
        _selection(
            context,
            explanations=[_price_claim(pattern.ref, contradictory=[note["note_id"]])],
        ),
        context,
    )


def test_same_ref_cannot_fill_support_and_counter_material_roles(positive_path_own):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(
            _selection(
                context,
                explanations=[_price_claim(pattern.ref, contradictory=[pattern.ref])],
            ),
            context,
        )

    _assert_issue(
        exc_info,
        path_contains="possible_explanations[0].contradictory_evidence_refs",
    )


def test_price_inference_requires_contemporaneous_plan_as_missing_information(positive_path_own):
    context = _retrieve_all(build_review_catalog(positive_path_own))
    pattern = _positive_pattern(context)

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(
            _selection(
                context,
                explanations=[_price_claim(pattern.ref, missing=["independent_confirmation"])],
            ),
            context,
        )

    _assert_issue(
        exc_info,
        path_contains="possible_explanations[0].missing_information",
    )


@pytest.mark.parametrize("reference_kind", ["unread", "nonexistent"])
def test_unread_or_nonexistent_support_ref_is_rejected(positive_path_own, reference_kind):
    context = build_review_catalog(positive_path_own)
    pattern = _positive_pattern(context)
    context.retrieved.add(positive_path_own.outcome.outcome_id)
    ref = pattern.ref if reference_kind == "unread" else "not-a-review-ref"

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(_selection(context, explanations=[_price_claim(ref)]), context)

    _assert_issue(
        exc_info,
        code="unretrieved_or_unknown_evidence",
        path_contains="possible_explanations[0].supporting_evidence_refs",
    )


def test_historical_comparison_cannot_be_selected_as_actual_fact(pair):
    context = build_review_catalog(pair.a)
    outcome_ref = pair.a.outcome.outcome_id
    historical_ref = "historical-test-ref"
    context.records[historical_ref] = replace(
        context.records[outcome_ref],
        ref=historical_ref,
        kind="historical_comparison",
    )
    context.retrieved.update({outcome_ref, historical_ref})

    with pytest.raises(ReviewVerificationError) as exc_info:
        verify_selection(
            _selection(context, factual_refs=[outcome_ref, historical_ref]),
            context,
        )

    _assert_issue(
        exc_info,
        code="historical_hypothesis_is_not_actual_fact",
        path_contains="factual_refs[1]",
    )


def test_catalog_rejects_note_ref_collision_with_authoritative_outcome(pair):
    note = _plan_note(pair.a, note_id=pair.a.outcome.outcome_id)
    with pytest.raises(ValueError, match="duplicate|collision"):
        build_review_catalog(pair.a, notes=(note,))


def test_catalog_rejects_unknown_note_kind(pair):
    with pytest.raises(ValueError, match="note_kind|invalid"):
        build_review_catalog(pair.a, notes=(_plan_note(pair.a, note_kind="other"),))
