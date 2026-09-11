"""Failure metadata only: no prompts, model prose, arguments, refs or credentials."""
from contextvars import ContextVar
from functools import wraps
from datetime import datetime, timezone
import json
import os
from time import monotonic

_current = ContextVar("review_diagnostic", default=None)
STAGES = {"analysis", "receipt_binding", "option_preparation", "structured_finalization", "tool_audit", "claim_validation", "answer_composition"}
TOOLS = {"get_episode_facts", "get_registered_historical_comparisons", "get_self_history", "get_same_stock_comparison", "get_user_notes", "search_review_facts"}
CODES = set("""required_tool_choice_missing required_evidence_and_counterevidence_tools_not_executed
review_access_expired_or_revoked invalid_claim_option_roles invalid_claim_option_support
finalizer_schema_validation_failed finalization_input_over_limit analysis_text_unavailable_or_over_limit
required_facts_exceed_output_capacity option_not_exposed duplicate_option_selection uncertainty_option_conflict
authorized_comparison_receipt_required counterpart_outcome_receipt_required ambiguous_finalization_option_id
claim_option_scope_mismatch unretrieved_or_unknown_evidence evidence_scope_mismatch own_episode_result_required
own_episode_result_identity_mismatch historical_hypothesis_is_not_actual_fact unavailable_or_unregistered_historical_comparison
historical_hypothesis_is_not_motive_support support_counter_material_overlap evidence_does_not_support_hypothesis
contrary_plan_not_addressed hypothesis_needs_alternatives_and_missing_information
answer_invalid_financial_value answer_missing_observation_date answer_incomplete_comparison answer_invalid_prior_mark
invalid_answer_option_selection answer_option_changed_or_unread answer_relevant_comparison_or_counterexample_missing
answer_comparison_required answer_full_horizon_infeasibility_missing answer_summary_not_audited
answer_counterpart_not_authorized answer_reference_capacity_exceeded""".split())


STAGES |= {"researching", "reading", "searching", "quoting", "writing", "checking",
           "numeric_reference_validation", "grounding_validation"}
TOOLS |= set("""get_account_snapshot get_account_performance get_account_behavior get_account_self_history
get_account_episode_index get_investment_results get_investment_details get_account_performance_path
read_financial_concept get_current_allocation identify_public_security read_public_daily_ohlcv
read_public_quote_snapshot search_public_web read_stock_research_method
read_public_technical_indicators read_public_financials get_hypothetical_trade_impact
get_owned_period_comparison get_owned_same_stock_comparison""".split())
CODES |= set("""account_answer_invalid_guide account_answer_number_not_in_sources
account_answer_operation_count_mismatch account_answer_unread_reference account_completed_receipts_required
account_concept_source_required account_conversation_context_over_limit account_conversation_invalid_output
account_conversation_schema_failed account_conversation_unavailable account_fact_source_required
account_grounding_incomplete_coverage account_grounding_failed account_incomplete_tool_receipt
account_internal_reference_in_text account_invalid_tool_arguments account_invalid_tool_call
account_invalid_tool_receipt account_model_request_failed account_model_response_incomplete account_model_timeout
account_receipt_record_mismatch account_record_not_available account_record_scope_mismatch
account_research_incomplete account_review_cancelled account_review_timeout account_tool_batch_over_limit
account_unconfirmed_close_claim account_unpaired_tool_receipt invalid_account_conversation_context
invalid_account_question""".split())

FINALIZER_FIELDS = {"factual_option_ids", "historical_option_ids", "claim_option_ids",
                    "question_kind", "answer_focus", "finding_option_ids", "finding_ids", "guide_ids"}
FINALIZER_FAILURE_KINDS = {"invalid_json", "wrong_root_type", "missing_required_fields",
                           "unexpected_fields", "invalid_field_type_or_value",
                           "conflicting_fixed_field", "unknown_schema_failure"}
FINALIZER_NORMALIZATIONS = {"fixed_field_materialized", "matching_fixed_field_removed"}
FINALIZER_FAILURE_TYPES = {
    "json_invalid", "model_type", "missing", "extra_forbidden", "list_type", "dict_type",
    "string_type", "bool_type", "int_type", "float_type", "literal_error", "enum",
    "too_short", "too_long", "string_too_short", "string_too_long", "greater_than",
    "greater_than_equal", "less_than", "less_than_equal", "finite_number",
    "conflicting_fixed_field", "schema_validation_error",
}
SCHEMA_PATH_FIELDS = FINALIZER_FIELDS | {
    "paragraphs", "paragraph_index", "kind", "text", "zh", "en", "refs", "guides",
    "guide_id", "episode_id", "label", "supported", "reason", "question_answered",
    "guides_valid", "guide_findings", "guide_index", "issues", "findings", "problem",
}


def _safe_rejection_path(value):
    """Keep schema paths, never model values or arbitrary key names."""
    if value == "$":
        return value
    if not isinstance(value, str) or not value.startswith("$."):
        return None
    segments = value[2:].replace("[", ".").replace("]", "").split(".")
    named = [segment for segment in segments if not segment.isdigit()]
    allowed = FINALIZER_FIELDS | {"possible_explanations", "supporting_evidence_refs",
                                  "contradictory_evidence_refs", "missing_information",
                                  "alternative_explanations"}
    return value if named and all(segment in allowed for segment in named) else None


def _safe_schema_path(value):
    """Allow only code-owned schema names and bounded list indices."""
    if value == "$":
        return value
    if not isinstance(value, str) or not value.startswith("$."):
        return None
    segments = value[2:].replace("[", ".").replace("]", "").split(".")
    named = [segment for segment in segments if not segment.isdigit()]
    indices = [int(segment) for segment in segments if segment.isdigit()]
    return value if (named and all(segment in SCHEMA_PATH_FIELDS for segment in named)
                     and all(0 <= index <= 99 for index in indices)) else None


def mark(stage, **metadata):
    state = _current.get()
    if state is not None:
        state.update(stage=stage, **metadata)


def diagnosed(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        state = {"stage": "analysis", "correction_attempt": 0, "tool_audit_passed": None}
        started = monotonic()
        token = _current.set(state)
        try:
            return await function(*args, **kwargs)
        except Exception as error:
            error.review_diagnostic = {**state, "elapsed_ms": int((monotonic() - started) * 1000)}
            raise
        finally:
            _current.reset(token)
    return wrapped


def safe_failure(error):
    raw = getattr(error, "review_diagnostic", {})
    code = getattr(getattr(error, "issue", None), "code", None) or getattr(error, "code", None)
    if isinstance(code, str) and code.startswith("account_grounding:"):
        code = "account_grounding_failed"
    if isinstance(error, TimeoutError):
        code = "account_review_timeout"
    failure_fields = raw.get("finalizer_failure_fields", [])
    failure_fields = sorted(set(failure_fields) & FINALIZER_FIELDS) if isinstance(failure_fields, list) else []
    rejection_code = raw.get("semantic_rejection_code")
    failure_paths = raw.get("finalizer_failure_paths", [])
    failure_paths = (sorted(set(filter(None, (_safe_schema_path(item) for item in failure_paths))))
                     if isinstance(failure_paths, list) else [])
    failure_types = raw.get("finalizer_failure_types", [])
    failure_types = (sorted(set(failure_types) & FINALIZER_FAILURE_TYPES)
                     if isinstance(failure_types, list) else [])
    return {
        "code": code if code in CODES else "review_validation_failed",
        "stage": raw.get("stage") if raw.get("stage") in STAGES else "unclassified",
        "correction_attempt": 1 if raw.get("correction_attempt") == 1 else 0,
        "tool_audit_passed": raw.get("tool_audit_passed") if type(raw.get("tool_audit_passed")) is bool else None,
        "completed_tools": sorted(set(raw.get("completed_tools", [])) & TOOLS),
        "search_stances": sorted(set(raw.get("search_stances", [])) & {"support", "contradict"}),
        "semantic_rejection_code": rejection_code if rejection_code in CODES else None,
        "semantic_rejection_path": _safe_rejection_path(raw.get("semantic_rejection_path")),
        "finalizer_failure_kind": (raw.get("finalizer_failure_kind")
                                   if raw.get("finalizer_failure_kind") in FINALIZER_FAILURE_KINDS else None),
        "finalizer_failure_fields": failure_fields,
        "finalizer_failure_paths": failure_paths,
        "finalizer_failure_types": failure_types,
        "finalizer_normalization": (raw.get("finalizer_normalization")
                                    if raw.get("finalizer_normalization") in FINALIZER_NORMALIZATIONS else None),
        "finalizer_format_attempt": (raw.get("finalizer_format_attempt")
                                     if raw.get("finalizer_format_attempt") in {0, 1} else None),
        "elapsed_ms": raw.get("elapsed_ms") if type(raw.get("elapsed_ms")) is int and 0 <= raw["elapsed_ms"] <= 600_000 else None,
    }


def persist_failure(path, diagnostic):
    """Append sanitized metadata only. Logging failure never breaks polling."""
    allowed = {"code", "stage", "correction_attempt", "tool_audit_passed", "completed_tools",
               "search_stances", "semantic_rejection_code", "semantic_rejection_path",
               "finalizer_failure_kind", "finalizer_failure_fields", "finalizer_format_attempt",
               "finalizer_failure_paths", "finalizer_failure_types",
               "finalizer_normalization",
               "elapsed_ms", "diagnostic_id"}
    row = {key: value for key, value in diagnostic.items() if key in allowed}
    row["recorded_at"] = datetime.now(timezone.utc).isoformat()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
    except OSError:
        pass


def failure_reason(error):
    """Public translation keys only; never send exception prose to the UI."""
    from src.agents.claim_contract import ReviewVerificationError
    from src.agents.structured_finalizer import StructuredFinalizationUnavailable

    if isinstance(error, TimeoutError):
        return "review_timeout"
    if isinstance(error, StructuredFinalizationUnavailable):
        if str(error) in {"finalization_input_over_limit", "analysis_text_unavailable_or_over_limit"}:
            return "review_analysis_too_large"
        if str(error) == "review_access_expired_or_revoked":
            return "review_access_expired_or_revoked"
        return "review_answer_format_failed"
    if isinstance(error, ReviewVerificationError):
        if error.issue.code in {"answer_reference_capacity_exceeded", "required_facts_exceed_output_capacity"}:
            return "review_answer_assembly_failed"  # Compatibility with older workers.
        if error.issue.code == "review_access_expired_or_revoked":
            return "review_access_expired_or_revoked"
        return "review_answer_evidence_failed"
    return "review_analysis_failed"
