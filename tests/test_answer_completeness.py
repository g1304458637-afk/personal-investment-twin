"""Offline completeness checks for calculated public technical answers."""
import copy
import asyncio
from unittest.mock import AsyncMock

from test_account_review import account_context
from test_public_analysis import AnalysisQuotes, _bars
from test_public_research import _context, _invoke
from src.agents.answer_completeness import (
    question_requests_technical_results,
    technical_result_findings,
)
from src.agents.public_research import read_public_technical_indicators, reset_public_caches


def test_positive_semantic_verdict_cannot_publish_definitions_only(monkeypatch):
    from src.agents import dsa_conversation as dsa
    record = {"ref": "technical", "kind": "public_technical", "availability": "complete",
        "value": {"metrics": {"rsi_14": {"status": "available", "value": 56.7,
            "display_value": "56.70", "window": 14}}}}
    candidate = _paragraph(["technical"], "RSI使用14期参数。", "RSI uses a 14-period parameter.")
    verdict = dsa.GroundingVerdict(paragraphs=[{"paragraph_index": 0,
        "supported": True, "reason": "Parameters are correct"}], question_answered=True,
        guides_valid=True)
    monkeypatch.setattr(dsa, "_structured", AsyncMock(return_value=verdict))
    result = asyncio.run(dsa.verify_grounding(None, _payload(QUESTION, record, [candidate]), lambda: True))
    assert "question_not_answered" in result.issues
    assert "actual available indicator value" in result.findings[0].problem


QUESTION = ("请读取 SHSE:600519 在 2026-01-01 至 2026-09-09 的已完成日线技术指标，"
            "保留指标参数、预热与数据状态。")


def _technical_record(account_context, count=40):
    reset_public_caches()
    result = _invoke(read_public_technical_indicators,
        _context(copy.deepcopy(account_context), quotes=AnalysisQuotes(_bars(count))),
        security_id="SHSE:600519", start_date="2026-01-01", end_date="2026-09-09", adjust="qfq")
    return result["records"][0]


def _payload(question, record, paragraphs):
    return {"question": question, "actually_read_records": [record],
            "candidate": {"paragraphs": paragraphs, "guides": []}}


def _paragraph(refs, zh, en):
    return {"kind": "fact", "refs": refs, "text": {"zh": zh, "en": en}}


def test_result_question_cannot_be_satisfied_by_definitions_parameters_or_dates(account_context):
    record = _technical_record(account_context)
    candidate = _paragraph([record["ref"]],
        "MACD使用12、26、9参数，数据截至2026-09-09；RSI需要预热。",
        "MACD uses 12, 26 and 9; data runs to 2026-09-09, and RSI needs warmup.")
    findings = technical_result_findings(_payload(QUESTION, record, [candidate]))
    assert len(findings) == 1 and findings[0]["paragraph_index"] == 0
    assert "12/26/9 parameters do not count" in findings[0]["problem"]


def test_recorded_display_value_in_both_languages_satisfies_result_completeness(account_context):
    record = _technical_record(account_context)
    display = record["value"]["metrics"]["rsi_14"]["display_value"]
    assert display.endswith(".00") and "%" not in display
    candidate = _paragraph([record["ref"]], f"RSI为{display}。", f"RSI is {display}.")
    assert technical_result_findings(_payload(QUESTION, record, [candidate])) == []
    rounded = _paragraph([record["ref"]], "RSI值为100。", "RSI is 100.")
    assert technical_result_findings(_payload(QUESTION, record, [rounded])) == []
    missing_translation = _paragraph([record["ref"]], f"RSI为{display}。", "RSI has enough warmup.")
    assert technical_result_findings(_payload(QUESTION, record, [missing_translation]))
    sma = record["value"]["metrics"]["sma_5"]["display_value"]
    listed = _paragraph([record["ref"]], f"均线MA5：{sma}。", f"SMA5: {sma}.")
    assert technical_result_findings(_payload(QUESTION, record, [listed])) == []

    # A value copied under a paragraph that does not cite its technical record
    # cannot satisfy the evidence/result boundary.
    candidate["refs"] = ["knowledge-only"]
    assert technical_result_findings(_payload(QUESTION, record, [candidate]))[0]["paragraph_index"] == 0


def test_definition_questions_and_partial_or_warmup_records_are_not_over_rejected(account_context):
    record = _technical_record(account_context)
    definition = _paragraph([record["ref"]], "RSI是什么？", "What is RSI?")
    assert not question_requests_technical_results("RSI是什么？")
    assert not question_requests_technical_results("How is MACD calculated?")
    assert question_requests_technical_results(QUESTION)
    assert question_requests_technical_results("Read the latest RSI value for SHSE:600519.")
    assert technical_result_findings(_payload("RSI是什么？", record, [definition])) == []

    warmup = _technical_record(account_context, count=4)
    assert warmup["availability"] == "insufficient"
    assert technical_result_findings(_payload(QUESTION, warmup, [definition])) == []
    partial = copy.deepcopy(record)
    partial["availability"] = "insufficient"
    partial["value"]["data_quality"] = {"status": "partial"}
    assert technical_result_findings(_payload(QUESTION, partial, [definition])) == []


def test_metric_label_must_bind_a_nearby_result_not_an_unrelated_same_number():
    record = {"ref": "technical", "kind": "public_technical", "availability": "complete",
        "value": {"metrics": {"rsi_14": {"status": "available", "value": 9.0,
                                            "display_value": "9.00"}}}}
    unrelated = _paragraph([record["ref"]],
        "RSI使用14期参数；日期是2026-09-09，另一个无关金额是9.00元。",
        "RSI uses a 14-period window; the date is 2026-09-09 and an unrelated amount is 9.00.")
    assert technical_result_findings(_payload(QUESTION, record, [unrelated]))
    bare_parameter = _paragraph([record["ref"]], "RSI 14是参数。", "RSI 14 is the window.")
    assert technical_result_findings(_payload(QUESTION, record, [bare_parameter]))
    wrong_unit = _paragraph([record["ref"]], "RSI为9%。", "RSI is 9%.")
    assert technical_result_findings(_payload(QUESTION, record, [wrong_unit]))
    for zh, en in [
        ("RSI为9元。", "RSI is 9 CNY."),
        ("RSI为9倍。", "RSI is 9 times."),
    ]:
        assert technical_result_findings(_payload(QUESTION, record,
            [_paragraph([record["ref"]], zh, en)]))

    for zh, en in [
        ("RSI(14)=9.00。", "RSI(14)=9.00."),
        ("RSI为9。", "RSI is 9."),
        ("RSI(14) 9.0。", "RSI(14) 9.0."),
    ]:
        assert technical_result_findings(_payload(QUESTION, record,
            [_paragraph([record["ref"]], zh, en)])) == []


def test_metric_result_units_follow_the_indicator_quantity():
    def record(name, value=9.0):
        return {"ref": "technical", "kind": "public_technical", "availability": "complete",
            "value": {"metrics": {name: {"status": "available", "value": value,
                                           "display_value": f"{value:.2f}"}}}}

    volume = record("volume_ratio_5")
    for zh, en in [("量比为9倍。", "Volume ratio is 9 times."),
                   ("量比为9。", "Volume ratio is 9.")]:
        assert technical_result_findings(_payload(QUESTION, volume,
            [_paragraph([volume["ref"]], zh, en)])) == []
    for zh, en in [("量比为9元。", "Volume ratio is 9 CNY."),
                   ("量比为9%。", "Volume ratio is 9%.")]:
        assert technical_result_findings(_payload(QUESTION, volume,
            [_paragraph([volume["ref"]], zh, en)]))

    for name, zh_label, en_label in [
        ("sma_5", "MA5", "SMA5"),
        ("ema_12", "EMA12", "EMA12"),
        ("atr_14", "ATR(14)", "ATR(14)"),
    ]:
        price_metric = record(name)
        for zh, en in [(f"{zh_label}为9元。", f"{en_label} is 9 CNY."),
                       (f"{zh_label}为9。", f"{en_label} is 9.")]:
            assert technical_result_findings(_payload(QUESTION, price_metric,
                [_paragraph([price_metric["ref"]], zh, en)])) == []
        assert technical_result_findings(_payload(QUESTION, price_metric,
            [_paragraph([price_metric["ref"]], f"{zh_label}为9%。", f"{en_label} is 9%.")]))
        assert technical_result_findings(_payload(QUESTION, price_metric,
            [_paragraph([price_metric["ref"]], f"{zh_label}为9美元。", f"{en_label} is 9 USD.")]))

    macd = {"ref": "technical", "kind": "public_technical", "availability": "complete",
        "value": {"metrics": {"macd_12_26_9": {"status": "available", "line": 9.0,
            "signal": 8.0, "histogram": 1.0,
            "display_value": {"line": "9.00", "signal": "8.00", "histogram": "1.00"}}}}}
    assert technical_result_findings(_payload(QUESTION, macd, [
        _paragraph([macd["ref"]], "MACD线为9元。", "MACD line is 9 CNY.")])) == []
    assert technical_result_findings(_payload(QUESTION, macd, [
        _paragraph([macd["ref"]], "MACD线为9%。", "MACD line is 9%.")]))

    # Unit matching stops at punctuation; later prose must not retroactively
    # change the unit of the already reported indicator.
    rsi = record("rsi_14")
    candidate = _paragraph([rsi["ref"]],
        "RSI为9。后文提到9元费用。", "RSI is 9. A later sentence mentions 9 CNY.")
    assert technical_result_findings(_payload(QUESTION, rsi, [candidate])) == []


def test_every_available_technical_metric_has_plain_display_values(account_context):
    record = _technical_record(account_context)
    metrics = record["value"]["metrics"]
    for metric in metrics.values():
        if metric["status"] != "available":
            continue
        display = metric["display_value"]
        values = display.values() if isinstance(display, dict) else [display]
        assert all(isinstance(value, str) and value.count(".") == 1 for value in values)
        assert all("%" not in value for value in values)
        if "value" in metric:
            assert display == f'{metric["value"]:.2f}'
        else:
            assert display == {key: f'{metric[key]:.2f}' for key in ("line", "signal", "histogram")}
    macd = metrics["macd_12_26_9"]
    assert (macd["fast_period"], macd["slow_period"], macd["signal_period"]) == (12, 26, 9)
