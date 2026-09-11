"""Sanitizer-only checks: no fake provider/model and no network requests."""
from scripts.qa_decision_review_deepseek import safe_text, sanitized_args, sanitized_model_error
from scripts.qa_decision_review_deepseek import wire_format_summary, final_text_summary
from scripts.qa_deepseek_structured_probes import MINIMAL_SCHEMA, validate_final
import pytest


def test_diagnostic_arguments_only_preserve_enums_and_known_synthetic_refs():
    assert sanitized_args('{"stance":"support","topic":"all","extra":"private text"}', set()) == {
        "stance": "support", "topic": "all", "[UNKNOWN_FIELD]": "[REDACTED]"}
    assert sanitized_args('{"refs":["synthetic-ref","unrecognized"]}', {"synthetic-ref"}) == {
        "refs": ["synthetic-ref", "[REDACTED]"]}
    assert sanitized_args('not json', set()) == "[INVALID_JSON_REDACTED]"


def test_diagnostic_error_scrubs_sensitive_text_and_validation_input():
    marker = "QA_ONLY_NOT_A_CREDENTIAL"
    assert marker not in safe_text(f"Failure {marker}", marker)
    assert "hidden" not in safe_text("Authorization: hidden\ninvalid argument")
    assert "invalid argument" in safe_text("Authorization: hidden\ninvalid argument")
    message = "Invalid JSON input for tool search_review_facts\ninput_value='private text', input_type=str"
    result = sanitized_model_error(message, "")
    assert "private text" not in result
    assert "search_review_facts" in result and "input_type=str" in result
    assert "private" not in sanitized_model_error('Expected dict for JSON: {"private": 1}', "")


def test_actual_installed_sdk_structured_mapping_and_schema_regression():
    from agents.agent_output import AgentOutputSchema
    from agents.models.openai_responses import Converter
    from src.agents.decision_review import ReviewSelection
    output = AgentOutputSchema(ReviewSelection)
    mapping = Converter.get_response_format(output)
    summary = wire_format_summary({"text": mapping})
    assert summary["text_format_type"] == "json_schema"
    assert summary["strict"] is True and summary["schema_present"] is True
    assert set(summary["top_level_required"]) == {"factual_refs", "historical_comparison_refs", "possible_explanations", "question_kind"}
    assert mapping["format"]["schema"] == output.json_schema()
    assert mapping["format"]["schema"]["additionalProperties"] is False
    # The evidence lists intentionally no longer inherit display-size limits.
    assert "maxItems" not in mapping["format"]["schema"]["properties"]["factual_refs"]
    assert "maxItems" not in mapping["format"]["schema"]["properties"]["historical_comparison_refs"]
    assert summary["schema_sha256"] == "c2c49cebbbc37d47cb31d0f6401cb98056661f3b29d3314865090ca91953edc0"
    assert wire_format_summary({})["schema_present"] is False


def body(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


@pytest.mark.parametrize("text,parsed,valid", [
    ('{"answer":"OK"}', True, True), ('```json\n{"answer":"OK"}\n```', False, False),
    ('Here is JSON: {"answer":"OK"}', False, False), ('{"answer":"OK"} commentary', False, False),
    ('{"answer":', False, False), ('{"answer":"NO"}', True, False),
    ('{"answer":"OK","extra":1}', True, False), ('{"answer":NaN}', False, False),
])
def test_probe_uses_exact_parse_and_strict_schema_without_repair(text, parsed, valid):
    assert validate_final(body(text)) == {"exact_json_parse_success": parsed, "schema_validation_success": valid}


def test_response_shape_redacts_before_bounded_previews():
    marker = "QA_ONLY_NOT_A_CREDENTIAL"
    text = " " * 290 + marker + "x" * 400 + marker + " "
    summary = final_text_summary(body(text), marker)
    assert summary["output_text_length"] == len(text)
    assert len(summary["prefix_sanitized"]) <= 300 and len(summary["suffix_sanitized"]) <= 300
    assert marker not in summary["prefix_sanitized"] + summary["suffix_sanitized"]
    fenced = final_text_summary(body('```json\n{"answer":"OK"}\n```'))
    assert fenced["starts_with_markdown_fence"] is True
    assert fenced["looks_like_json_object"] is False
    assert final_text_summary({"output": [{"type": "function_call"}]})["output_text_exists"] is False


def test_ladder_uses_real_fields_and_preserves_original_schema():
    from scripts.qa_deepseek_structured_probes import schema_ladder
    from agents.agent_output import AgentOutputSchema
    from src.agents.decision_review import ReviewSelection
    steps = schema_ladder()
    assert len(steps) == 11
    assert steps[0][1]["required"] == ["question_kind"]
    assert steps[3][1]["properties"]["possible_explanations"]["items"] == {"type": "string"}
    assert steps[4][1]["properties"]["possible_explanations"]["items"]["required"] == ["kind"]
    assert steps[-1][1] == AgentOutputSchema(ReviewSelection).json_schema()
    assert "$defs" not in steps[-2][1]
    assert steps[-2][1]["properties"]["possible_explanations"]["items"] == steps[-1][1]["$defs"]["Hypothesis"]


@pytest.mark.parametrize("change", [None, "unsupported_kind", "unknown_field", "too_many_hypotheses"])
def test_inline_probe_retains_validation_semantics(change):
    from scripts.qa_deepseek_structured_probes import schema_ladder
    from jsonschema import Draft202012Validator
    sample = {"question_kind": "need_contemporaneous_records", "factual_refs": ["synthetic-ref"],
              "historical_comparison_refs": [], "possible_explanations": [{"kind": "unknown",
                  "supporting_evidence_refs": [], "contradictory_evidence_refs": [],
                  "alternative_explanations": ["unknown"], "missing_information": ["contemporaneous_plan"]}]}
    if change == "unsupported_kind":
        sample["possible_explanations"][0]["kind"] = "greedy"
    elif change == "unknown_field":
        sample["financial_number"] = 1
    elif change == "too_many_hypotheses":
        sample["possible_explanations"] *= 4
    inline, original = [schema for _, schema in schema_ladder()[-2:]]
    left = not list(Draft202012Validator(inline).iter_errors(sample))
    right = not list(Draft202012Validator(original).iter_errors(sample))
    assert left == right == (change is None)


def test_qa_requires_actual_tool_free_strict_finalizer_wire():
    from scripts.qa_decision_review_deepseek import finalization_wire_verified
    request = dict(phase="finalizer", tool_count=0, tool_choice="none", reasoning={"effort": "none"},
                   text_format_type="json_schema", schema_present=True, strict=True)
    assert finalization_wire_verified([request])
    assert not finalization_wire_verified([])
    for key, value in {"phase": "analysis", "tool_count": 1, "tool_choice": "auto",
                       "reasoning": {}, "text_format_type": "text", "schema_present": False, "strict": False}.items():
        assert not finalization_wire_verified([request | {key: value}])


def test_semantic_diagnostic_has_exact_path_and_masks_unknown_refs():
    import json
    from scripts.qa_decision_review_deepseek import semantic_diagnostic
    from src.agents.decision_review import Hypothesis, ReviewVerificationError, verify_selection
    from src.agents.review_catalog import build_review_catalog
    from src.compare.demo import build_pair
    from test_decision_review_agent import selection
    context = build_review_catalog(build_pair().a)
    context.retrieved.update(context.records)
    ref = context.own.outcome.outcome_id
    claim = Hypothesis(kind="price_influence_possible", supporting_evidence_refs=[ref],
        contradictory_evidence_refs=[], alternative_explanations=["prior_staged_plan"],
        missing_information=["contemporaneous_plan"])
    candidate = selection(context, possible_explanations=[claim])
    with pytest.raises(ReviewVerificationError) as caught:
        verify_selection(candidate, context)
    diagnostic = semantic_diagnostic(candidate, context, caught.value)
    assert diagnostic["rejection"]["json_path"] == "$.possible_explanations[0].supporting_evidence_refs"
    assert diagnostic["rejection"]["code"] == "evidence_does_not_support_hypothesis"
    assert diagnostic["candidate"]["possible_explanations"][0] == claim.model_dump()
    assert diagnostic["referenced_evidence"][ref]["kind"] == "episode"
    marker = "UNTRUSTED_QA_MARKER_NOT_A_CREDENTIAL"
    candidate.factual_refs.append(marker)
    assert marker not in json.dumps(semantic_diagnostic(candidate, context, caught.value))
    from dataclasses import replace
    context.records[ref] = replace(context.records[ref], subject_id="REAL_SUBJECT")
    assert semantic_diagnostic(candidate, context, caught.value) == {"reason": "diagnostic_scope_not_allowed"}


def test_qa_revalidation_preserves_rejection_history_but_accepts_valid_correction():
    from scripts.qa_decision_review_deepseek import record_validation_status
    state = {"semantic_validation_attempts": []}
    record_validation_status(state, "claim_evidence_validation", False)
    assert state["claim_evidence_validation_failed"] is True
    record_validation_status(state, "claim_evidence_validation", True)
    assert state["claim_evidence_validation_entered"] is True
    assert state["claim_evidence_validation_failed"] is False
    assert state["semantic_validation_attempts"] == ["rejected", "valid"]


def test_qa_repeat_plan_is_fixed_and_covers_all_three_intents():
    from scripts.qa_decision_review_deepseek import ADVERSARIAL_QUESTIONS, qa_cases
    assert qa_cases(repeat=2) == [(None, 1), (None, 2)]
    assert qa_cases(adversarial_suite=True, repeat=2) == [
        (question, trial) for question in ADVERSARIAL_QUESTIONS for trial in (1, 2)]
    with pytest.raises(ValueError):
        qa_cases(repeat=4)


def test_option_diagnostic_masks_unknown_ids_and_refuses_real_context():
    import json
    from dataclasses import replace
    from scripts.qa_decision_review_deepseek import option_diagnostic
    from src.agents.decision_review import ReviewSelection, prepare_finalization_options
    from src.agents.review_catalog import build_review_catalog
    from src.compare.demo import build_pair
    context = build_review_catalog(build_pair().a)
    context.retrieved.update(context.records)
    options = prepare_finalization_options(context)
    marker = "UNTRUSTED_OPTION_MARKER"
    choice = options.choice_type(ReviewSelection).model_construct(factual_option_ids=[], historical_option_ids=[],
        claim_option_ids=[options.claim_options[0].option_id, marker], question_kind="none")
    diagnostic = option_diagnostic(options, context, choice)
    assert marker not in json.dumps(diagnostic)
    assert options.claim_options[0].option_id in diagnostic["selected_option_ids"]["claim_option_ids"]
    assert diagnostic["admissible_kinds"] == ["unknown"]
    assert diagnostic["generated_option_count"] == len(options.factual_options) + 1
    ref = context.own.outcome.outcome_id
    context.records[ref] = replace(context.records[ref], account_id="REAL_ACCOUNT")
    assert option_diagnostic(options, context, choice) == {"reason": "diagnostic_scope_not_allowed"}


def test_quality_view_copies_accepted_synthetic_numbers_and_comparison_only():
    from dataclasses import asdict, replace
    from scripts.qa_decision_review_deepseek import accepted_quality_facts
    from src.agents.review_catalog import build_review_catalog
    from src.compare.demo import build_pair
    pair = build_pair()
    context = build_review_catalog(pair.a, comparison=pair)
    refs = [pair.a.outcome.outcome_id, pair.b.outcome.outcome_id, pair.comparison_id]
    result = {"facts": [asdict(context.records[r]) for r in refs]}
    view = accepted_quality_facts(result, context)
    assert view[0]["value"]["result"]["pnl"] == pair.a.outcome.actual_result.pnl
    assert view[1]["value"]["result"]["pnl"] == pair.b.outcome.actual_result.pnl
    assert view[2]["value"]
    for visible, original in zip(view[2]["value"], context.records[pair.comparison_id].value):
        assert visible == {k: original[k] for k in visible}
    result["facts"][0]["value"] = {"result": {"pnl": "INVENTED_VALUE"}}
    assert len(accepted_quality_facts(result, context)) == 2
    context.records[refs[0]] = replace(context.records[refs[0]], subject_id="REAL_SUBJECT")
    assert accepted_quality_facts(result, context) == []


def test_diagnostic_observers_track_real_sdk_choices_but_never_certify_a_fake_wire(monkeypatch, capsys):
    """Exercise diagnostic wiring offline; missing real HTTP proof MUST be FAIL."""
    import asyncio
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from agents import Runner
    from src.agents import decision_review as review, investment_coach
    from src.agents.structured_finalizer import StructuredFinalizer
    from src.agents.review_catalog import build_review_catalog
    from src.compare.demo import build_pair
    from test_decision_review_agent import runtime
    from test_review_semantic_correction import model_for, duplicate_fact
    from review_option_helpers import choose_options
    from scripts.qa_decision_review_deepseek import diagnose
    context = build_review_catalog(build_pair().a)
    good = choose_options("unknown")
    fenced = lambda request: "```json\n" + good(request) + "\n```"
    model = model_for(context, [fenced, choose_options("unknown", change=duplicate_fact), good])
    model._client = SimpleNamespace(_client=SimpleNamespace(event_hooks={"request": [], "response": []}), close=AsyncMock())
    monkeypatch.setattr(investment_coach, "create_model_runtime", lambda **kwargs: runtime(model))
    originals = (Runner.__dict__["run"], review.prepare_finalization_options, review.expand_finalization,
                 review.can_correct_choice, StructuredFinalizer.finalize)
    assert asyncio.run(diagnose(context, "")) == 1
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    summary = next(e for e in events if e["event"] == "diagnostic_summary")
    assert summary["qa_status"] == "FAIL" and summary["reason"] == "incomplete_acceptance_diagnostics"
    assert summary["finalizer_wire_verified"] is False
    assert summary["format_retry_count"] == summary["semantic_correction_attempts"] == 1
    assert summary["claim_evidence_validation_failed"] is False
    assert summary["tool_receipt_audit_failed"] is False
    assert summary["option_selection_rejections"][0]["code"] == "duplicate_option_selection"
    assert summary["option_expansions"][0]["expansion"]["candidate"]["possible_explanations"][0]["kind"] == "unknown"
    assert any(e["event"] == "accepted_quality_facts" and e["facts"] for e in events)
    assert originals == (Runner.__dict__["run"], review.prepare_finalization_options, review.expand_finalization,
                         review.can_correct_choice, StructuredFinalizer.finalize)
    model._client.close.assert_awaited_once()
