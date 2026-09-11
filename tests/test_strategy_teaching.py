"""Strategy teaching guardrail tests: citations resolve, schema forbids verdicts."""
from __future__ import annotations

import pytest

from src.agents.strategy_teaching import (
    TeachingReferenceError,
    render_segment,
    resolve_report_path,
    teaching_output_schema,
)

REPORT = {
    "reports": [{
        "instrument": "SYN_VALUE",
        "window_user_net_cash_flow": 3980.0,
        "window_rule_fill_count": 3,
        "limitations": ["只并列事实"],
    }],
}


def test_reference_paths_resolve_into_report_values():
    assert resolve_report_path(REPORT, "reports.0.instrument") == "SYN_VALUE"
    assert resolve_report_path(REPORT, "reports.0.window_user_net_cash_flow") == 3980.0
    with pytest.raises(TeachingReferenceError):
        resolve_report_path(REPORT, "reports.0.next_day_prediction")


def test_render_segment_fills_numbers_from_the_report_only():
    rendered = render_segment(
        "该窗口记录侧净现金流 {user}，规则侧成交 {count} 笔。",
        REPORT,
        {"user": "reports.0.window_user_net_cash_flow", "count": "reports.0.window_rule_fill_count"},
    )
    assert rendered["accepted"] is True
    assert rendered["text"] == "该窗口记录侧净现金流 3980.0，规则侧成交 3 笔。"


def test_unknown_reference_fails_closed_instead_of_guessing():
    rendered = render_segment("未来五日预期涨幅 {target}。", REPORT,
                              {"target": "reports.0.forecast"})
    assert rendered == {"accepted": False, "reason": "unknown_reference",
                        "path": "reports.0.forecast", "text": None}


def test_schema_has_no_free_number_field_and_no_verdict_kind():
    schema = teaching_output_schema()
    segment = schema["properties"]["segments"]["items"]
    assert set(segment["required"]) == {"kind", "template", "references"}
    assert "verdict" not in segment["properties"]["kind"]["enum"]
    assert segment["properties"]["template"]["maxLength"] <= 400


def test_runner_renders_fake_model_output_and_drops_bad_references(monkeypatch):
    import asyncio
    from src.agents import strategy_teaching as teaching

    class FakeResult:
        final_output = teaching.TeachingAnswer(segments=[
            teaching.TeachingSegment(kind="entry_teaching", template="记录侧 {user}。",
                                     references={"user": "reports.0.window_user_net_cash_flow"}),
            teaching.TeachingSegment(kind="risk_teaching", template="预测 {target}。",
                                     references={"target": "reports.0.forecast"}),
        ])

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            return FakeResult()

    class FakeRuntime:
        model = model_settings = run_config = None

    monkeypatch.setattr(teaching, "Runner", FakeRunner)
    result = asyncio.run(teaching.run_teaching(FakeRuntime(), REPORT))
    assert result["status"] == "available" and len(result["texts"]) == 1
    assert "3980.0" in result["texts"][0] and result["dropped"][0]["path"] == "reports.0.forecast"


def test_protocol_entry_validates_report_and_model_key():
    from src.agents.strategy_teaching import explain_report
    import pytest
    with pytest.raises(ValueError, match="invalid_teaching_report"):
        explain_report({"report": {"schema_version": "nope"}})
    with pytest.raises(ValueError, match="model_not_configured"):
        explain_report({"report": {"schema_version": "strategy_comparison.v1"}})


def test_teaching_agent_is_tool_free_structured_output():
    from src.agents.strategy_teaching import build_teaching_agent
    agent = build_teaching_agent(model="fake", model_settings=None, run_config=None)
    assert agent.tools == [] and agent.output_type is not None
