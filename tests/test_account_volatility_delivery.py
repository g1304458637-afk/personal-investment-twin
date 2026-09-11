"""Real synthetic calculations and offline DSA tool delivery; no live provider."""
import asyncio
import json
from types import SimpleNamespace

import empyrical
import numpy as np
import pytest

from test_account_review import account_context
from test_dsa_conversation import configured, response
from src.agents.account_review_sources import build_account_review_context
from src.agents.dsa_conversation import run_dsa_conversation
from src.demo import showcase
from toujing_core_runtime.account_review import AccountReviewService


def performance_records(context):
    return {record.kind: record for record in (
        *context.records.values(), *context.conversation_records.values()
    ) if record.kind in {"performance", "performance_path"}}


def assert_risk_delivery(context):
    records = performance_records(context)
    summary, path = records["performance"].value, records["performance_path"].value
    returns = np.asarray([point["period_return"] for point in path["points"][1:]])
    expected = empyrical.annual_volatility(returns, annualization=252)
    assert summary["annualized_volatility"] == pytest.approx(expected)
    assert summary["annualized_volatility"] > 0
    for field in ("annualized_volatility", "annualization_factor", "return_observation_count"):
        assert summary[field] == path[field]
    assert summary["annualization_factor"] == 252
    assert summary["return_observation_count"] == 259
    assert summary["sharpe_ratio"] is None
    assert "daily_risk_statistics_require_explicit_complete_cadence" not in summary["limitations"]
    assert any("declared_synthetic_weekdays_not_exchange_calendar" in ref
               for ref in summary["source_refs"])
    return records


def test_showcase_supplies_verified_volatility_to_both_read_views(account_context):
    assert_risk_delivery(account_context)


def test_reference_showcase_uses_its_own_returns():
    service = AccountReviewService(SimpleNamespace())
    try:
        context = service._source({
            "scope_kind": "account", "subject_id": showcase.REFERENCE_SUBJECT,
            "account_id": showcase.REFERENCE_SUBJECT, "data_mode": "synthetic_showcase",
        })
        assert_risk_delivery(context)
    finally:
        service.close()


def test_undeclared_calendar_keeps_risk_metrics_unavailable(monkeypatch):
    # Even many observations and a synthetic data tier must not implicitly
    # certify a daily calendar. Exercise the common builder's default boundary.
    import toujing_core_runtime.account_review as module
    def without_policy(*args, **kwargs):
        kwargs.pop("risk_policy", None)
        return build_account_review_context(*args, **kwargs)
    monkeypatch.setattr(module, "build_account_review_context", without_policy)
    service = AccountReviewService(SimpleNamespace())
    try:
        context = service._source({
            "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
            "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
        })
        for record in performance_records(context).values():
            assert record.value["annualized_volatility"] is None
            assert record.value["return_observation_count"] == 259
            assert "daily_risk_statistics_require_explicit_complete_cadence" in record.value["limitations"]
    finally:
        service.close()


@pytest.mark.parametrize(("kind", "tool_name"), [
    ("performance", "get_account_performance"),
    ("performance_path", "get_account_performance_path"),
])
def test_dsa_model_receives_and_can_cite_computed_volatility(monkeypatch, account_context, kind, tool_name):
    record = assert_risk_delivery(account_context)[kind]
    formatted = format(record.value["annualized_volatility"], ".2%")
    answer = {"paragraphs": [{"kind": "fact", "text": {
        "zh": f"该示例账户的年化波动率约为{formatted}。",
        "en": f"The example account's annualized volatility is approximately {formatted}.",
    }, "refs": [record.ref]}], "guides": []}
    runtime, client, model = configured(monkeypatch, [
        response(calls=[("risk-call", tool_name, {})]),
        response("Use the computed annualized volatility and its stated period."),
    ], [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("我的年化波动率是多少？", account_context, runtime=runtime))
    second_request = client.responses.create.call_args_list[1].kwargs
    tool_result = next(item for item in second_request["input"]
                       if item.get("type") == "function_call_output")
    payload = json.loads(tool_result["output"])["records"][0]
    assert payload["value"]["annualized_volatility"] == record.value["annualized_volatility"]
    assert payload["value"]["annualization_factor"] == 252
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    assert result["executed_tools"] == [tool_name]
    assert record.ref in result["read_refs"]
    assert all(request["tools"] == [] for request in model.requests)
