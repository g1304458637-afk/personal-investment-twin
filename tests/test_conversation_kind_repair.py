"""Offline paragraph-kind repair and candlestick knowledge boundaries."""
import copy
import json
from dataclasses import asdict

import pytest

from test_account_review import account_context
from src.agents.account_conversation import ConversationAnswer, ConversationError, REVIEWER, WRITER, validate_answer
from src.agents.account_conversation_sources import KNOWLEDGE, knowledge_record
from src.agents.owned_analysis_tools import hypothetical_trade_impact


def _paragraph(kind, ref, zh, en):
    return ConversationAnswer.model_validate({"paragraphs": [{
        "kind": kind, "text": {"zh": zh, "en": en}, "refs": [ref],
    }], "guides": []})


def test_hypothetical_clarification_concept_gets_safe_kind_repair_details(account_context):
    receipt = json.loads(hypothetical_trade_impact(copy.deepcopy(account_context),
        symbol="SYN_GROWTH", side="BUY", quantity=300, execution_price=14.4, fees=None))
    record = receipt["records"][0]
    answer = _paragraph("concept", record["ref"],
        "本次拟交易检查需要先明确费用，不会默认按零费用计算。",
        "This hypothetical check requires an explicit fee and does not assume zero fees.")
    with pytest.raises(ConversationError, match="concept_source_required") as caught:
        validate_answer(answer, {record["ref"]: record}, [record["ref"]])
    detail = caught.value.details
    assert detail["paragraph_index"] == 0
    assert detail["cited_kinds"] == ["hypothetical_trade_impact"]
    assert detail["cited_availability"] == ["clarification_required"]
    assert detail["read_knowledge_refs"] == []
    assert detail["allowed_record_description_kinds"] == ["fact", "interpretation"]
    assert answer.paragraphs[0].kind == "concept"  # validation never auto-relabels prose

    repaired = _paragraph("fact", record["ref"], answer.paragraphs[0].text.zh,
                          answer.paragraphs[0].text.en)
    assert validate_answer(repaired, {record["ref"]: record}, [record["ref"]]) == []


def test_general_concept_still_requires_knowledge_while_registered_definition_passes(account_context):
    receipt = json.loads(hypothetical_trade_impact(copy.deepcopy(account_context),
        symbol="SYN_GROWTH", side="BUY", quantity=300, execution_price=14.4, fees=None))
    hypothetical = receipt["records"][0]
    unsupported = _paragraph("concept", hypothetical["ref"],
        "交易费用是所有市场中收益的通用定义组成。",
        "Trading fees are universally part of the definition of returns in every market.")
    with pytest.raises(ConversationError, match="concept_source_required"):
        validate_answer(unsupported, {hypothetical["ref"]: hypothetical}, [hypothetical["ref"]])

    knowledge = knowledge_record(copy.deepcopy(account_context), "candlestick")
    record = json.loads(json.dumps(asdict(knowledge), default=str))
    supported = _paragraph("concept", record["ref"],
        "OHLC不记录盘中高低点的先后或完整路径，因此不能仅凭长实体、短影线断言中途回撤小。",
        "OHLC does not record the intrabar order of highs and lows or the full path, so a long body and short wicks cannot establish a small intrabar drawdown.")
    assert validate_answer(supported, {record["ref"]: record}, [record["ref"]]) == []


def test_writer_and_verifier_state_kind_and_ohlc_boundaries():
    assert "kind=concept" in WRITER and "kind=fact" in WRITER and "kind=interpretation" in WRITER
    assert "不要仅因句子在“解释”假设结果就选 concept" in WRITER
    assert "不能用 concept 规避具体记录" in WRITER
    assert "最高价与最低价出现的先后" in KNOWLEDGE["candlestick"]["content"]
    assert "完整盘中路径" in KNOWLEDGE["candlestick"]["content"]
    assert "中途回撤小" in KNOWLEDGE["candlestick"]["content"]
    assert "单根OHLC/K线不记录" in REVIEWER and "unsupported_claim" in REVIEWER
