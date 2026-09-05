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
    assert summary["schema_sha256"] == "ff4d1ebd7f029111cde82fa001b742c1d80abf4924b618a6c35e5b665210127c"
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
