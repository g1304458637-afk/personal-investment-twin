"""Financial validation regression: exact units, currencies and cited paragraphs."""
import pytest
from src.agents.account_conversation import ConversationAnswer, ConversationError, validate_answer


def answer(text, ref="source"):
    return ConversationAnswer(paragraphs=[{"kind": "fact", "text": {"zh": text, "en": text}, "refs": [ref]}], guides=[])


def records(text):
    return {"source": {"kind": "public_search", "value": {"excerpt": text}}}


@pytest.mark.parametrize("source,text", [
    ("12.69亿元", "CNY 1.269 billion"),
    ("12.69亿元", "1,269 million yuan"),
    ("26.46亿元", "RMB 2.646 billion"),
    ("9.52亿元", "CNY 952 million"),
    ("3.35亿元", "CNY 335 million"),
    ("12.69亿元", "1,269,000,000元"),
    ("CNY 1.269 billion", "12.69亿元"),
    ("-12.69亿元", "CNY -1.269 billion"),
    ("1269万美元", "USD 12.69 million"),
    ("1.269亿港元", "HKD 126.9 million"),
    ("1.5万亿元", "CNY 1.5 trillion"),
    ("12.69 亿元", "RMB 1.269 billion"),
])
def test_exact_monetary_conversion(source, text):
    assert validate_answer(answer(text), records(source), ["source"]) == []


@pytest.mark.parametrize("text", [
    "CNY 1.269 million", "CNY 12.69 billion", "USD 1.269 billion",
    "USD 12.69 million", "HKD 12.69 billion", "CNY -1.269 billion",
    "CNY 1.27 billion", "1.269%", "1.269 shares", "1.269 billion",
    "CNY 1.269 billion and 1.269 shares", "CNY 1.269 billion and USD 1.269 billion",
])
def test_incorrect_or_unbound_conversion(text):
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(answer(text), records("12.69亿元"), ["source"])


def test_conversion_cannot_borrow_other_paragraph_or_unread_sources():
    sources = {**records("12.69亿元"), "other": {"kind": "public_search", "value": "1元"}}
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(answer("CNY 1.269 billion", "other"), sources, ["other", "source"])
    with pytest.raises(ConversationError, match="unread_reference"):
        validate_answer(answer("CNY 1.269 billion"), sources, ["other"])


def test_nonfinancial_numbers_do_not_admit_money_conversions():
    for source in ["12.69%", "1269000000 shares", "12.69"]:
        with pytest.raises(ConversationError, match="number_not_in_sources"):
            validate_answer(answer("CNY 1.269 billion"), records(source), ["source"])
