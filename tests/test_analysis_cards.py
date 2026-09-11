"""Result cards use real local tool projections; no model or live provider calls."""
from __future__ import annotations

import asyncio
import copy
import json

import pandas as pd
import pytest
from agents.tool_context import ToolContext

from src.agents.analysis_cards import build_analysis_cards, validate_analysis_cards
from src.agents.owned_analysis_tools import (
    hypothetical_trade_impact, owned_period_comparison, owned_same_stock_comparison,
)
from src.agents.public_research import (
    attach_public_research, read_public_financials, read_public_technical_indicators,
)
from toujing_core_runtime.chat_archive import ChatArchive
from test_owned_analysis_tools import owned_context as owned_context_fixture


class _Quotes:
    def __init__(self):
        dates = pd.bdate_range(end="2026-09-05", periods=40)
        self.bars = pd.DataFrame([{"日期": date.strftime("%Y-%m-%d"), "开盘": 10 + index,
                                   "最高": 11 + index, "最低": 9 + index, "收盘": 10.5 + index,
                                   "成交量": 1000 + index * 10} for index, date in enumerate(dates)])

    def daily_ohlcv(self, code, start, end, adjust):
        assert (code, start, end, adjust) == ("000001", "2026-07-01", "2026-09-05", "qfq")
        return self.bars


class _Fundamentals:
    def financial_statements(self, code, market):
        assert (code, market) == ("000001", "SZSE")
        return {
            "income_statement": pd.DataFrame([{"报告日": "2026-06-30", "币种": "CNY", "营业收入": 100.0, "净利润": -10.0}]),
            "balance_sheet": pd.DataFrame([{"报告日": "2026-06-30", "币种": "CNY", "资产总计": 200.0, "负债合计": 50.0}]),
            "key_indicators": pd.DataFrame([{"REPORT_DATE": "2026-06-30", "ROE": 8.5}]),
        }


def _invoke(tool, context, **arguments):
    encoded = json.dumps(arguments, ensure_ascii=False)
    wrapped = ToolContext(context, tool_name=tool.name, tool_call_id="cards", tool_arguments=encoded)
    return json.loads(asyncio.run(tool.on_invoke_tool(wrapped, encoded)))["records"][0]


def _owned_context():
    return owned_context_fixture.__wrapped__()


def _real_records():
    context, *_ = _owned_context()
    impact = json.loads(hypothetical_trade_impact(
        context, symbol="SYN_GROWTH", side="BUY", quantity=300, execution_price=14.4, fees=0,
    ))["records"][0]
    period = json.loads(owned_period_comparison(
        context, earlier_start="2025-01-02", earlier_end="2025-03-31", later_start="2025-03-31", later_end="2025-06-30",
    ))["records"][0]
    attach_public_research(context, {
        "_desktop_search_enabled": False, "_public_quote_client": _Quotes(),
        "_public_fundamentals_client": _Fundamentals(),
        "_public_now": lambda: pd.Timestamp("2026-09-08T04:00:00Z").to_pydatetime(),
    })
    technical = _invoke(read_public_technical_indicators, context, security_id="SZSE:000001",
                        start_date="2026-07-01", end_date="2026-09-05", adjust="qfq")
    financials = _invoke(read_public_financials, context, security_id="SZSE:000001")
    return {record["ref"]: record for record in (impact, period, technical, financials)}


def test_cards_project_real_tool_records_with_correct_before_after_units_and_definitions():
    records = _real_records()
    before = copy.deepcopy(records)
    refs = list(records)
    cards = build_analysis_cards(records, refs, refs)
    by_kind = {card["kind"]: card for card in cards}
    assert set(by_kind) == {"hypothetical_trade_impact", "owned_period_comparison", "public_technical", "public_financials"}

    impact = by_kind["hypothetical_trade_impact"]
    assert [item["en"] for item in impact["columns"]] == ["Before trade", "After trade"]
    labels = {row["label"]["en"]: row for row in impact["rows"]}
    assert {"Cash", "Total account value", "Target security quantity", "Target security valuation price", "Target security account-value weight", "Concentration HHI (cash excluded)"} <= set(labels)
    assert labels["Cash"]["cells"][0]["en"] == "58,170.00 CNY"
    assert labels["Target security quantity"]["cells"][0]["en"] == "900"
    assert labels["Target security account-value weight"]["cells"][0]["en"] == "11.34%"
    assert "squared normalized non-cash" in labels["Concentration HHI (cash excluded)"]["explanation"]["en"]
    assert "may match" in labels["Target security valuation price"]["explanation"]["en"]

    technical = by_kind["public_technical"]
    assert [item["en"] for item in technical["columns"]] == ["Value", "Unit", "Definition"]
    technical_rows = {row["label"]["en"]: row for row in technical["rows"]}
    assert technical_rows["RSI(14)"]["cells"][1]["en"] == "0–100"
    assert "strength oscillator" in technical_rows["RSI(14)"]["cells"][2]["en"]
    assert technical_rows["MACD(12,26,9) histogram"]["cells"][1]["en"] == "CNY"
    assert "their difference" in technical_rows["MACD(12,26,9) histogram"]["cells"][2]["en"]

    financials = by_kind["public_financials"]
    financial_rows = {row["label"]["en"]: row for row in financials["rows"]}
    assert financial_rows["Revenue"]["cells"][0]["en"] == "100.00 CNY"
    assert financial_rows["Revenue"]["cells"][1]["en"] == "2026-06-30"
    assert financial_rows["Return on equity"]["cells"][0]["en"] == "8.50%"
    assert "locally derived" in financial_rows["Debt-to-assets"]["explanation"]["en"]
    assert "not provider-directly reported" in financials["notes"][-1]["en"]

    period = by_kind["owned_period_comparison"]
    period_rows = {row["label"]["en"]: row for row in period["rows"]}
    assert "including zero-trade days" in period_rows["Mean daily turnover"]["explanation"]["en"]
    assert "squared period-end holding weights" in period_rows["End-of-period holding concentration HHI"]["explanation"]["en"]
    assert "not a period average" in period_rows["End-of-period holding concentration HHI"]["explanation"]["en"]
    assert "earlier peak to a subsequent trough" in period_rows["Maximum drawdown magnitude"]["explanation"]["en"]
    assert "(effective_start, effective_end]" in period["notes"][1]["en"]
    assert "Forward-adjusted" in technical["subtitle"]["en"]
    validate_analysis_cards(cards)
    assert records == before


def test_actual_nonoverlapping_same_stock_projects_only_honest_side_by_side_outcomes():
    context, _, _, instruments, lifecycle = _owned_context()
    growth_id = instruments["SYN_GROWTH"].instrument_id
    episodes = sorted((item for item in lifecycle.episodes if item.instrument_id == growth_id), key=lambda item: item.opened_at)
    same_stock = json.loads(owned_same_stock_comparison(
        context, earlier_episode_id=context.episode_display_ids[episodes[0].episode_id],
        later_episode_id=context.episode_display_ids[episodes[1].episode_id],
    ))["records"][0]
    assert same_stock["availability"] == "insufficient_evidence"
    records = _real_records()
    records[same_stock["ref"]] = same_stock
    records["malformed"] = {"ref": "malformed", "kind": "owned_period_comparison", "availability": "complete", "value": {"effective_periods": {}}}
    before = copy.deepcopy(records)
    cards = build_analysis_cards(records, list(records), ["malformed", same_stock["ref"]])
    assert len(cards) == 1
    card = cards[0]
    assert card["kind"] == "owned_same_stock_comparison"
    assert card["title"]["zh"] == "两轮记录并排查看（不可直接比较）"
    assert "no verifiable shared-market comparison" in card["subtitle"]["en"]
    labels = {row["label"]["en"]: row for row in card["rows"]}
    assert labels["Result type"]["cells"][0]["en"] == "Realized"
    assert labels["Result type"]["cells"][1]["en"] == "Marked"
    assert labels["Actual result"]["cells"][0]["en"] == "-630.00 CNY"
    assert labels["Actual result"]["cells"][1]["en"] == "3,880.00 CNY"
    assert not any("difference" in row["label"]["en"].lower() or "delta" in row["label"]["en"].lower() for row in card["rows"])
    assert any("do not overlap" in note["en"] for note in card["notes"])
    assert records == before


def test_nonfinite_candidate_is_omitted_without_normalizing_or_mutating_it():
    record = {"ref": "nonfinite", "kind": "public_technical", "availability": "complete", "value": {"bad": float("nan")}}
    assert build_analysis_cards({"nonfinite": record}, ["nonfinite"], ["nonfinite"]) == []
    assert record["value"]["bad"] != record["value"]["bad"]


def test_cards_are_capped_and_schema_rejects_transport_tampering():
    records = _real_records()
    cards = build_analysis_cards(records, list(records), [*list(records), *list(records), "not-read"])
    assert len(cards) <= 5 and len({card["source_ref"] for card in cards}) == len(cards)
    bad = copy.deepcopy(cards)
    bad[0]["rows"][0]["cells"].pop()
    with pytest.raises(ValueError, match="invalid_analysis_cards"):
        validate_analysis_cards(bad)


def test_card_schema_enforces_explicit_string_and_collection_bounds_separately():
    records = _real_records()
    cards = build_analysis_cards(records, list(records), list(records))
    too_long_title = copy.deepcopy(cards)
    too_long_title[0]["title"]["en"] = "x" * 161
    with pytest.raises(ValueError, match="invalid_analysis_cards"):
        validate_analysis_cards(too_long_title)
    too_long_source = copy.deepcopy(cards)
    too_long_source[0]["source_ref"] = "x" * 1001
    with pytest.raises(ValueError, match="invalid_analysis_cards"):
        validate_analysis_cards(too_long_source)
    with pytest.raises(ValueError, match="invalid_analysis_cards"):
        validate_analysis_cards([*cards, cards[0], cards[0]])


def test_archive_roundtrip_preserves_real_cards_and_legacy_answer_without_new_global_validation(tmp_path):
    records = _real_records()
    cards = build_analysis_cards(records, list(records), list(records))
    scope = {"subject_id": "synthetic", "account_id": "cards", "scope_kind": "account", "data_mode": "synthetic"}
    archived = ChatArchive(tmp_path / "cards.sqlite3")
    base = {"scope": scope, "source_fingerprint": "fixed", "question": "question", "history": []}
    archived.save(scope, {
        "legacy": {**base, "result": {"scope": scope, "answer": {"version": "account_review_answer_v1"}}},
        "cards": {**base, "result": {"scope": scope, "analysis_cards": cards,
                                        "answer": {"version": "account_conversation_answer_v2", "paragraphs": [], "guides": []}}},
    })
    restored = archived.read(scope)
    assert restored["legacy"]["result"]["answer"]["version"] == "account_review_answer_v1"
    assert restored["cards"]["result"]["analysis_cards"] == cards
