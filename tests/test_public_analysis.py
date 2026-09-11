"""Offline checks for deterministic public technical/fundamental adapters."""
from __future__ import annotations

import pandas as pd
import pytest

from test_account_review import account_context
from test_public_research import _context, _invoke
from src.agents.public_research import (
    _QUOTE_CACHE,
    PUBLIC_RECORD_KINDS,
    PUBLIC_TOOLS,
    read_public_daily_ohlcv,
    read_public_financials,
    read_public_technical_indicators,
    reset_public_caches,
)
from src.agents.public_technical import calculate_technical_indicators
from src.agents.public_fundamentals import normalize_financials


class AnalysisQuotes:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def daily_ohlcv(self, code, start, end, adjust):
        self.calls.append((code, start, end, adjust))
        return self.bars


class Fundamentals:
    def __init__(self, value):
        self.value = value

    def financial_statements(self, code, market):
        assert (code, market) == ("000001", "SZSE")
        return self.value


class BrokenFundamentals:
    def financial_statements(self, code, market):
        raise RuntimeError("provider unavailable")


def _bars(count=40, *, last_date="2026-09-05"):
    dates = pd.bdate_range(end=last_date, periods=count)
    return pd.DataFrame([{"日期": day.strftime("%Y-%m-%d"), "开盘": 10 + index,
                          "最高": 11 + index, "最低": 9 + index, "收盘": 10.5 + index,
                          "成交量": 1000 + index * 10} for index, day in enumerate(dates)])


def test_technical_tool_calculates_disclosed_metrics_and_preserves_warmups(account_context):
    result = _invoke(read_public_technical_indicators, _context(account_context, quotes=AnalysisQuotes(_bars())),
        security_id="SZSE:000001", start_date="2026-07-01", end_date="2026-09-05", adjust="qfq")
    value = result["records"][0]["value"]
    assert result["status"] == "complete"
    assert value["price_basis"] == "forward_adjusted"
    assert value["metrics"]["sma_5"]["status"] == "available"
    assert value["metrics"]["macd_12_26_9"]["status"] == "available"
    assert value["metrics"]["rsi_14"]["value"] == 100.0
    assert "signal" not in value and "recommendation" not in value
    short = _invoke(read_public_technical_indicators, _context(account_context, quotes=AnalysisQuotes(_bars(4))),
        security_id="SZSE:000001", start_date="2026-09-01", end_date="2026-09-05")
    assert short["status"] == "insufficient_evidence"
    assert short["records"][0]["value"]["metrics"]["sma_5"]["reason"] == "insufficient_closed_bars"


def test_technical_tool_excludes_todays_unfinished_bar(account_context):
    reset_public_caches()
    bars = _bars(20, last_date="2026-09-08")
    result = _invoke(read_public_technical_indicators, _context(account_context, quotes=AnalysisQuotes(bars)),
        security_id="SZSE:000001", start_date="2026-08-01", end_date="2026-09-08", adjust="none")
    value = result["records"][0]["value"]
    assert value["latest_bar_excluded_as_in_progress"] is True
    assert value["closed_bar_count"] == 19
    assert value["last_closed_bar_date"] < "2026-09-08"


def test_technical_and_daily_caches_do_not_relabel_or_poison_market_data(account_context):
    reset_public_caches()
    quotes = AnalysisQuotes(_bars(20))
    daily_context = _context(account_context, quotes=quotes)
    daily = _invoke(read_public_daily_ohlcv, daily_context, security_id="SZSE:000001",
                    start_date="2026-08-01", end_date="2026-09-05", adjust="none")
    market_fetched_at = daily["records"][0]["value"]["fetched_at"]
    technical = _invoke(read_public_technical_indicators, _context(account_context, quotes=quotes),
                        security_id="SZSE:000001", start_date="2026-08-01", end_date="2026-09-05", adjust="none")
    value = technical["records"][0]["value"]
    assert len(quotes.calls) == 1
    assert value["market_data_fetched_at"] == value["fetched_at"] == market_fetched_at
    assert value["calculated_at"] == market_fetched_at
    reset_public_caches()
    quotes = AnalysisQuotes(_bars(20))
    _invoke(read_public_technical_indicators, _context(account_context, quotes=quotes),
            security_id="SZSE:000001", start_date="2026-08-01", end_date="2026-09-05", adjust="none")
    assert ("ohlcv", "SZSE:000001", "2026-08-01", "2026-09-05", "none") not in _QUOTE_CACHE
    _invoke(read_public_daily_ohlcv, _context(account_context, quotes=quotes), security_id="SZSE:000001",
            start_date="2026-08-01", end_date="2026-09-05", adjust="none")
    assert len(quotes.calls) == 2


def test_invalid_or_future_source_bars_are_excluded_and_not_completed(account_context):
    reset_public_caches()
    bars = pd.concat([_bars(40), pd.DataFrame([{"日期": "2026-10-01", "开盘": 1, "最高": 2, "最低": 0.5, "收盘": 1, "成交量": 10}])], ignore_index=True)
    result = _invoke(read_public_technical_indicators, _context(account_context, quotes=AnalysisQuotes(bars)),
        security_id="SZSE:000001", start_date="2026-07-01", end_date="2026-12-31", adjust="qfq")
    assert result["status"] == "insufficient_evidence"
    quality = result["records"][0]["value"]["data_quality"]
    assert quality["excluded_source_rows"] == 1
    assert quality["reason"] == "invalid_out_of_range_or_future_source_rows_excluded"


def test_rsi_flat_and_rising_series_and_unclosed_bar_cannot_look_ahead():
    def rows(closes):
        return [{"date": f"2026-08-{index + 1:02d}", "open": close, "high": close + 1,
                 "low": close - 1, "close": close, "volume": 100.0} for index, close in enumerate(closes)]
    assert calculate_technical_indicators(rows([10.0] * 16), latest_bar_may_be_in_progress=False)["metrics"]["rsi_14"]["value"] == 50.0
    assert calculate_technical_indicators(rows(list(range(10, 26))), latest_bar_may_be_in_progress=False)["metrics"]["rsi_14"]["value"] == 100.0
    closed = rows([10.0 + index for index in range(20)])
    with_unclosed_spike = [*closed, {**closed[-1], "date": "2026-09-30", "open": 1, "high": 999, "low": 0.1, "close": 999, "volume": 999999}]
    baseline = calculate_technical_indicators(closed, latest_bar_may_be_in_progress=False)
    protected = calculate_technical_indicators(with_unclosed_spike, latest_bar_may_be_in_progress=True)
    assert protected["metrics"] == baseline["metrics"]


def test_fundamentals_are_structured_and_partially_available(account_context):
    statements = {
        "income_statement": pd.DataFrame([{"报告日": "2025-12-31", "币种": "CNY", "营业收入": 100.0, "净利润": -10.0},
                                             {"报告日": "2026-12-31", "币种": "CNY", "营业收入": 999.0, "净利润": 999.0}]),
        "balance_sheet": pd.DataFrame([{"报告日": "2025-12-31", "币种": "CNY", "资产总计": 200.0, "负债合计": 50.0, "所有者权益合计": float("nan")}]),
        "cash_flow_statement_error": "provider_timeout",
        "key_indicators": pd.DataFrame([{"REPORT_DATE": "2025-12-31", "ROE": 8.5, "毛利率": None}]),
    }
    context = _context(account_context)
    context.public_research.fundamentals_client = Fundamentals(statements)
    result = _invoke(read_public_financials, context, security_id="SZSE:000001")
    value = result["records"][0]["value"]["statements"]
    assert result["status"] == "complete"
    assert value["income_statement"]["fields"]["revenue"]["value"] == 100.0
    assert value["income_statement"]["fields"]["net_income"]["value"] == -10.0
    assert value["income_statement"]["fields"]["revenue"]["unit"] == "CNY"
    assert value["income_statement"]["fields"]["revenue"]["scale"] == "provider_reported_amount_not_normalized"
    assert value["income_statement"]["report_period"] == "2025-12-31"
    assert value["balance_sheet"]["fields"]["total_equity"]["status"] == "unavailable"
    assert value["key_indicators"]["fields"]["gross_margin"]["status"] == "unavailable"
    assert value["cash_flow_statement"]["status"] == "unavailable"
    assert value["cash_flow_statement"]["reason"] == "provider_timeout"
    assert value["key_indicators"]["fields"]["debt_to_assets"]["value"] == 0.25
    assert result["records"][0]["ref"] in context.retrieved
    assert result["records"][0]["value"]["latest_report_is_not_point_in_time"] is True


def test_empty_indicators_do_not_hide_available_statements_and_provider_errors_are_clear(monkeypatch, account_context):
    context = _context(account_context)
    context.public_research.fundamentals_client = Fundamentals({
        "income_statement": pd.DataFrame([{"报告日": "2025-12-31", "营业收入": 12.0}]),
        "key_indicators": pd.DataFrame(),
    })
    partial = _invoke(read_public_financials, context, security_id="SZSE:000001")
    assert partial["status"] == "complete"
    assert partial["records"][0]["value"]["statements"]["key_indicators"]["status"] == "unavailable"
    failed_context = _context(account_context)
    failed_context.public_research.fundamentals_client = BrokenFundamentals()
    failed = _invoke(read_public_financials, failed_context, security_id="SZSE:000001")
    assert failed == {"status": "tool_error", "records": [], "error": "fundamentals_unavailable", "instruction": "Structured financial statements were not returned. Do not substitute news snippets."}
    budgets = []
    def timeout_call(function, timeout):
        budgets.append(timeout)
        raise TimeoutError()
    monkeypatch.setattr("src.agents.public_research._run_with_timeout", timeout_call)
    timeout = _invoke(read_public_financials, failed_context, security_id="SZSE:000001")
    assert timeout["error"] == "fundamentals_timeout" and timeout["records"] == [] and budgets == [18]


def test_financial_all_provider_downgrade_has_a_fixed_provider_status(account_context):
    context = _context(account_context)
    context.public_research.fundamentals_client = Fundamentals({
        "income_statement_error": "provider_timeout", "balance_sheet_error": "provider_timeout",
        "cash_flow_statement_error": "provider_timeout", "key_indicators_error": "provider_timeout",
    })
    result = _invoke(read_public_financials, context, security_id="SZSE:000001")
    value = result["records"][0]["value"]
    assert result["status"] == "insufficient_evidence"
    assert value["provider_status"] == "provider_timeout"
    assert {section["reason"] for section in value["statements"].values() if section["status"] == "unavailable"} == {"provider_timeout"}


def test_financial_periods_dates_booleans_and_parent_profit_are_not_conflated():
    normalized = normalize_financials({
        "income_statement": pd.DataFrame([
            {"报告日": "2025-99-99", "营业收入": 999.0, "净利润": 999.0, "PARENT_NETPROFIT": 999.0},
            {"报告日": "2025-12-31", "营业收入": 100.0, "净利润": True, "PARENT_NETPROFIT": 7.0},
        ]),
        "balance_sheet": pd.DataFrame([{"报告日": "2025-09-30", "资产总计": 200.0, "负债合计": 50.0}]),
        "key_indicators": pd.DataFrame([{"REPORT_DATE": "2025-12-31", "ROE": 8.0}]),
    }, as_of="2026-01-01T00:00:00+00:00")
    income = normalized["income_statement"]
    assert income["report_period"] == "2025-12-31"
    assert income["fields"]["revenue"]["value"] == 100.0
    assert income["fields"]["net_income"]["status"] == "unavailable"  # bool is not a financial number
    assert income["fields"]["net_income_attributable_to_parent"]["value"] == 7.0
    indicators = normalized["key_indicators"]
    assert indicators["report_period"] == "2025-12-31"
    debt = indicators["fields"]["debt_to_assets"]
    assert debt["value"] == 0.25 and debt["report_period"] == "2025-09-30"
    assert debt["source_section"] == "balance_sheet"
    derived_only = normalize_financials({"balance_sheet": pd.DataFrame([
        {"报告日": "2025-09-30", "资产总计": 100.0, "负债合计": 20.0}])})
    assert derived_only["key_indicators"]["status"] == "partial"
    assert derived_only["key_indicators"]["report_period"] is None


def test_provider_percent_and_derived_ratio_have_unambiguous_displays():
    normalized = normalize_financials({
        "balance_sheet": pd.DataFrame([{"报告日": "2025-06-30", "资产总计": 1000.0, "负债合计": 151.9}]),
        "key_indicators": pd.DataFrame([{"REPORT_DATE": "2025-06-30", "ROE": 16.75}]),
    })
    roe = normalized["key_indicators"]["fields"]["return_on_equity"]
    debt = normalized["key_indicators"]["fields"]["debt_to_assets"]
    assert roe == {"status": "available", "value": 16.75, "source_field": "ROE", "unit": "percent",
                   "scale": "provider_reported_percent", "display_value": "16.75%"}
    assert debt["value"] == 0.1519 and debt["unit"] == "ratio"
    assert debt["display_value"] == "15.19%"
    assert "1675%" not in roe["display_value"] and "1519%" not in debt["display_value"]


def test_analysis_exports_and_record_kinds_are_registered():
    names = {tool.name for tool in PUBLIC_TOOLS}
    assert {"read_public_technical_indicators", "read_public_financials"} <= names
    assert {"public_technical", "public_financials"} <= PUBLIC_RECORD_KINDS
