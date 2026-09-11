"""Finite receipt evidence is independent of the three displayed highlights.

Real current showcase data + scripted SDK choices; no credentials or network.
"""
import asyncio
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.agents.decision_review import (ReviewSelection, prepare_finalization_options,
    expand_finalization, validate_finalization, run_decision_review)
from src.agents.claim_contract import ReviewVerificationError
from src.agents.review_answer import (answer_choice_type, build_answer_options,
    include_answer_refs, compose_answer)
from toujing_core_runtime.product import ProductRuntime
from test_decision_review_agent import ScriptedModel, runtime
from review_option_helpers import input_payload


@pytest.fixture(scope="module")
def source_context(tmp_path_factory):
    # Resolve the repository independently of this test's staging directory.
    from src.agents import decision_review
    root = Path(decision_review.__file__).resolve().parents[2]
    data = json.loads((root / "apps/desktop/src/generated/showcase-demo.json").read_text())
    episode = data["position_episode_demo"]["default_episode_id"]
    product = ProductRuntime(tmp_path_factory.mktemp("receipt-capacity") / "qa.sqlite3")
    params = {"data_mode": "synthetic_showcase", "subject_id": "SYN_STUDY_SHOWCASE",
              "account_id": "SYN_STUDY_SHOWCASE", "episode_id": episode}
    try:
        yield product.review_runtime()._context(params)[0]
        assert product.repo.list_accounts() == []
    finally:
        product.close()


def prepared(source):
    context = copy.copy(source)
    context.records = dict(source.records)
    context.retrieved = set(context.records)
    claims = prepare_finalization_options(context)
    findings = build_answer_options(context)
    wire = answer_choice_type(claims.choice_type(ReviewSelection), findings)
    return context, claims, findings, wire


def choice(claims, findings, wire, *, fact_ids=None, history_ids=None, finding_ids=None):
    return wire(factual_option_ids=fact_ids if fact_ids is not None else [o.option_id for o in claims.factual_options],
        historical_option_ids=history_ids if history_ids is not None else [o.option_id for o in claims.historical_options],
        claim_option_ids=[next(o.option_id for o in claims.claim_options if o.claim_kind == "unknown")],
        question_kind="none", answer_focus="decision_reason",
        finding_option_ids=finding_ids or [findings[0].option_id])


def test_full_evidence_is_not_limited_by_three_highlights(source_context):
    context, claims, findings, wire = prepared(source_context)
    selected = choice(claims, findings, wire)
    result = include_answer_refs(selected, findings, expand_finalization(selected, claims), context)
    assert len(result.factual_refs) > 12
    assert len(result.historical_comparison_refs) > 4
    assert len(result.factual_refs) == len(set(result.factual_refs))
    assert len(result.historical_comparison_refs) == len(set(result.historical_comparison_refs))
    validate_finalization(result, context)
    assert len(compose_answer(selected, findings, result, context)["findings"]) == 1
    # Required own/counterpart outcomes stay; no result is discarded for space.
    assert set(claims.comparison_context.factual_refs) <= set(result.factual_refs)


def test_four_comparisons_plus_finding_fifth_is_a_valid_union(source_context):
    context, claims, findings, wire = prepared(source_context)
    found = next(f for f in findings if any(f.evidence_ref in o.evidence_refs for o in claims.historical_options))
    history = [o.option_id for o in claims.historical_options if found.evidence_ref not in o.evidence_refs][:4]
    assert len(history) == 4
    selected = choice(claims, findings, wire, fact_ids=[], history_ids=history, finding_ids=[found.option_id])
    before = expand_finalization(selected, claims)
    merged = include_answer_refs(selected, findings, before, context)
    assert len(before.historical_comparison_refs) == 4
    assert len(merged.historical_comparison_refs) == 5
    validate_finalization(merged, context)
    assert compose_answer(selected, findings, merged, context)["findings"][0]["evidence_ref"] == found.evidence_ref
    assert include_answer_refs(selected, findings, merged, context) == merged


def test_wire_is_still_finite_and_display_still_three(source_context):
    _, claims, findings, wire = prepared(source_context)
    schema = wire.model_json_schema()["properties"]
    assert schema["factual_option_ids"]["maxItems"] == len(claims.factual_options)
    assert schema["historical_option_ids"]["maxItems"] == len(claims.historical_options)
    assert schema["finding_option_ids"]["maxItems"] == 3
    with pytest.raises(ValidationError):
        choice(claims, findings, wire, fact_ids=["unexposed"])
    with pytest.raises(ValidationError):
        choice(claims, findings, wire, finding_ids=[f.option_id for f in findings[:4]])
    # Duplicate model selections still fail, not silently accepted by expansion.
    selected = choice(claims, findings, wire, fact_ids=[claims.factual_options[0].option_id] * 2)
    with pytest.raises(ReviewVerificationError, match="duplicate_option_selection"):
        expand_finalization(selected, claims)


@pytest.mark.parametrize("mutation", ["unread", "unknown", "subject_id", "account_id", "episode_id", "instrument_id"])
def test_larger_evidence_union_never_authorizes_invalid_reference(source_context, mutation):
    context, claims, findings, wire = prepared(source_context)
    selected = choice(claims, findings, wire)
    selection = expand_finalization(selected, claims)
    ref = findings[0].evidence_ref
    if mutation == "unread":
        context.retrieved.remove(ref)
    elif mutation == "unknown":
        del context.records[ref]
    else:
        context.records[ref] = replace(context.records[ref], **{mutation: "foreign"})
    with pytest.raises(ReviewVerificationError, match="unretrieved_or_unknown_evidence|evidence_scope_mismatch"):
        include_answer_refs(selected, findings, selection, context)


def test_scripted_sdk_completes_with_all_evidence_no_capacity_retry(source_context):
    def final(request):
        payload = input_payload(request["input"])
        catalog = payload["option_catalog"]
        return json.dumps({"factual_option_ids": [o["option_id"] for o in catalog["factual_options"]],
            "historical_option_ids": [o["option_id"] for o in catalog["historical_options"]],
            "claim_option_ids": [next(o["option_id"] for o in catalog["claim_options"] if o["claim_kind"] == "unknown")],
            "question_kind": "none", "answer_focus": "decision_reason",
            "finding_option_ids": [payload["answer_catalog"][0]["option_id"]]})
    steps = [("get_episode_facts", {}), ("search_review_facts", {"stance": "support", "topic": "all"}),
        ("search_review_facts", {"stance": "contradict", "topic": "all"}),
        ("get_registered_historical_comparisons", {}), ("get_self_history", {})]
    if source_context.comparison_id:
        steps.append(("get_same_stock_comparison", {}))
    steps += ["仅使用已读取记录，动机未知。", final]
    model = ScriptedModel(steps)
    result = asyncio.run(run_decision_review("这轮有哪些操作值得回看？", source_context, runtime=runtime(model)))
    assert len(result["facts"]) > 12 and len(result["historical_comparisons"]) > 4
    assert len(result["answer"]["findings"]) == 1
    assert len(model.requests) == len(steps)
    assert not source_context.retrieved  # Per-run retrieval never leaks into the context cache.
