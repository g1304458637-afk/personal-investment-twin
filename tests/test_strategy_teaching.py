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
