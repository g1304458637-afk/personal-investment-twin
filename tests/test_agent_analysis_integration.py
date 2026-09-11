"""Exercise the real DSA adapter/tool/receipt/writer pipeline without a provider."""
import asyncio
import copy
import json
from datetime import datetime, timezone

import pytest

from test_account_review import account_context
from test_dsa_conversation import configured, response
from src.agents.account_conversation import CONVERSATION_TOOLS
from src.agents.dsa_conversation import run_dsa_conversation
from src.agents.dsa_conversation import public_failure_receipt
from src.agents.owned_analysis_tools import hypothetical_trade_impact


@pytest.mark.parametrize("fees", [None, 0.0])
def test_owned_trade_tool_reaches_validated_answer_and_dynamic_receipt(monkeypatch, account_context, fees):
    args = {"symbol": "SYN_GROWTH", "side": "BUY", "quantity": 300.0,
            "execution_price": 14.4, "fees": fees}
    expected = json.loads(hypothetical_trade_impact(copy.deepcopy(account_context), **args))
    record = expected["records"][0]
    zh = "请确认这笔拟交易的费用；不会默认按零计算。" if fees is None else "这是指定条件下的拟交易检查，没有写入实际成交。"
    en = "Please confirm the trade fee; zero is not assumed." if fees is None else "This is a hypothetical trade check, not a recorded execution."
    answer = {"paragraphs": [{"kind": "fact", "text": {"zh": zh, "en": en}, "refs": [record["ref"]]}], "guides": []}
    runtime, client, _ = configured(monkeypatch, [
        response(calls=[("impact", "get_hypothetical_trade_impact", args)]),
        response("Explain the actual tool result and whether clarification is required.")],
        [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("假设买入SYN_GROWTH，300股，成交价14.4，账户怎样变化？",
        account_context, runtime=runtime))
    assert result["analysis_read_refs"] == result["read_refs"] == [record["ref"]]
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    receipt = next(item for item in client.responses.create.call_args_list[1].kwargs["input"]
                   if item.get("type") == "function_call_output")
    assert json.loads(receipt["output"])["records"] == [record]
    assert record["ref"] not in account_context.records


def test_all_new_analysis_tools_have_strict_schema_and_are_registered():
    names = {"read_public_technical_indicators", "read_public_financials", "get_hypothetical_trade_impact",
             "get_owned_period_comparison", "get_owned_same_stock_comparison"}
    tools = {tool.name: tool for tool in CONVERSATION_TOOLS}
    assert names <= tools.keys()
    for name in names:
        schema = tools[name].params_json_schema
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    fee = tools["get_hypothetical_trade_impact"].params_json_schema["properties"]["fees"]
    assert {branch["type"] for branch in fee["anyOf"]} == {"number", "null"}


def test_service_outage_receipt_is_not_a_market_fact_or_arbitrary_provider_message(account_context):
    context = copy.deepcopy(account_context)
    out = public_failure_receipt(context, "read_public_financials",
        {"status": "tool_error", "records": [], "error": "fundamentals_timeout", "instruction": "secret-must-not-be-copied"})
    assert out["status"] == "insufficient_evidence"
    record = out["records"][0]
    assert record["availability"] == "unavailable"
    assert record["kind"] == "research_status"
    assert record["value"]["market_facts_returned"] is False
    assert record["ref"] in context.retrieved
    assert "secret-must-not-be-copied" not in json.dumps(record)
    for tool, code in [("read_public_financials", "invalid_tool_arguments"),
                       ("get_investment_details", "quotes_unavailable"),
                       ("read_public_financials", "secret-user-provider-message")]:
        error = {"status": "tool_error", "records": [], "error": code}
        assert public_failure_receipt(context, tool, error) is error


def test_public_outage_can_finish_with_a_verified_service_explanation(monkeypatch, account_context):
    from src.agents.public_research import PublicResearchAccess
    import src.agents.public_research as public
    context = copy.deepcopy(account_context)
    context.public_research = PublicResearchAccess(now=lambda: datetime(2026, 9, 10, tzinfo=timezone.utc))
    monkeypatch.setattr(public, "_fundamentals_client", lambda ctx: None)
    expected = public_failure_receipt(copy.deepcopy(context), "read_public_financials",
        {"status": "tool_error", "records": [], "error": "fundamentals_unavailable"})["records"][0]
    answer = {"paragraphs": [{"kind": "fact", "text": {
        "zh": "本次财报服务没有返回可用数据，可以稍后重试。", "en": "The statement service returned no usable data; please retry later."},
        "refs": [expected["ref"]]}], "guides": []}
    runtime, _, _ = configured(monkeypatch, [
        response(calls=[("financials", "read_public_financials", {"security_id": "SHSE:600519"})]),
        response("Explain that the financial service is unavailable, not that the company has no statements.")],
        [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("读取贵州茅台财报", context, runtime=runtime))
    assert result["research_read_refs"] == result["read_refs"] == [expected["ref"]]
    assert result["public_read_refs"] == []
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
