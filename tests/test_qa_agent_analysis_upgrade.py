"""Offline content checks for the bounded agent-analysis QA harness."""
import sys
from types import ModuleType, SimpleNamespace
import pytest

from scripts.qa_agent_analysis_upgrade import QACheckError, _capture_diagnostics, _retention_summary, _validate_case


def test_schema_failure_reports_safe_fields_without_candidate_or_unknown_keys():
    from scripts.qa_agent_analysis_upgrade import _safe_failure
    from src.agents.account_conversation import ConversationError

    error = ConversationError("account_conversation_schema_failed")
    error.review_diagnostic = {
        "stage": "structured_finalization", "correction_attempt": 0,
        "finalizer_format_attempt": 1,
        "finalizer_failure_kind": "invalid_field_type_or_value",
        "finalizer_failure_paths": ["$.paragraphs[0].kind", "$.PRIVATE_INPUT"],
        "finalizer_failure_types": ["literal_error", "PRIVATE_INPUT"],
        "candidate": "PRIVATE_INPUT",
    }
    result = _safe_failure(error)
    assert result["finalizer_failure_paths"] == ["$.paragraphs[0].kind"]
    assert result["finalizer_failure_types"] == ["literal_error"]
    assert result["finalizer_format_attempt"] == 1
    assert "PRIVATE_INPUT" not in str(result)


def _result(*tools, public=False):
    return {"executed_tools": list(tools), "public_read_refs": ["public-record"] if public else []}


def test_technical_requires_a_dated_security_specific_indicator_value_not_only_warmup():
    _validate_case("technical600519", [_result("read_public_technical_indicators", public=True)], [[
        "SHSE:600519 截至2026-09-09，RSI(14)为52.30；仅描述已完成日线。"
    ]])
    with pytest.raises(QACheckError, match="technical_indicator_value_missing"):
        _validate_case("technical600519", [_result("read_public_technical_indicators", public=True)], [[
            "SHSE:600519 在2026-09-09使用RSI(14)、MACD(12,26,9)和均线参数，预热后再看。"
        ]])


def test_period_confirmation_requires_actual_percent_result_and_episode_path_guard_is_generic():
    _validate_case("period_dates", [
        _result(), _result("get_owned_period_comparison"),
    ], [["请先确认日期区间。"], ["2025-01-01至2025-06-30的收益率为3.20%，后一区间另列。"]])
    with pytest.raises(QACheckError, match="period_result_missing"):
        _validate_case("period_dates", [_result(), _result("get_owned_period_comparison")], [["日期区间已确认。"], [
            "2025-01-01至2025-06-30已确认，但没有可用比较结果。"
        ]])
    with pytest.raises(QACheckError, match="episode_price_path_misstated"):
        _validate_case("episode_result", [_result("get_investment_details")], [[
            "亏损630元，先买入后卖出；价格10.8→10.4→10.5，逐级走低。"
        ]])


def test_success_retention_summary_has_only_count_and_codes_not_candidate_text():
    summary = _retention_summary({"rejected_candidates": [
        {"paragraph_count": 2, "reason_code": "account_answer_number_not_in_sources", "candidate": "PRIVATE CANDIDATE"},
        {"paragraph_count": 1, "reason_code": "account_answer_number_not_in_sources"},
    ]})
    assert summary == {"rejected_candidate_count": 2, "reason_codes": ["account_answer_number_not_in_sources"]}
    assert "PRIVATE" not in str(summary)


def test_same_stock_natural_non_overlap_wording_is_accepted():
    _validate_case("same_stock", [_result("get_owned_same_stock_comparison")], [[
        "没有重叠的投资期间，一方是已实现结果，另一方是持有中估值，不能视为同区间绩效对比。"
    ]])


def test_repaired_validation_retains_only_redacted_rejection_metadata(monkeypatch):
    fake = ModuleType("src.agents.account_conversation")
    calls = []
    def validate(*_args):
        calls.append(None)
        if len(calls) == 1:
            raise RuntimeError("private diagnostic text")
        return []
    fake.validate_answer = validate
    monkeypatch.setitem(sys.modules, "src.agents.account_conversation", fake)
    import src.agents
    monkeypatch.setattr(src.agents, "account_conversation", fake, raising=False)
    capture = {}
    answer = SimpleNamespace(paragraphs=(), guides=())
    with _capture_diagnostics(True, capture):
        with pytest.raises(RuntimeError):
            fake.validate_answer(answer, {}, [])
        assert fake.validate_answer(answer, {}, []) == []
    assert "candidate" not in capture and "validation_details" not in capture
    assert _retention_summary(capture) == {"rejected_candidate_count": 1, "reason_codes": ["validation_rejected"]}
