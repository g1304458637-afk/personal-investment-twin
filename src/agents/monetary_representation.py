"""Exact monetary display equivalence, not FX, rounding or financial inference.

Only explicit currency/unit text in the paragraph's own cited records can admit
a converted number. Other occurrences of that token still require their source.
Entity, reporting period and accounting meaning remain subject to grounding.
"""
from dataclasses import dataclass
from decimal import Decimal
import re

_CURRENCY = r"人民币|美元|港元|港币|CNY\b|RMB\b|USD\b|HKD\b|yuan\b"
_SCALE = r"万亿|亿|万|千|trillion\b|billion\b|million\b|thousand\b"
_MONEY = re.compile(
    rf"(?<![\dA-Za-z_.])(?:(?P<prefix>{_CURRENCY})\s*)?"
    rf"(?P<number>[-+]?\d+(?:,\d{{3}})*(?:\.\d+)?)\s*"
    rf"(?P<scale>{_SCALE})?\s*(?P<suffix>{_CURRENCY}|元)?", re.I)
_CURRENCIES = {"人民币": "CNY", "元": "CNY", "yuan": "CNY", "cny": "CNY", "rmb": "CNY",
               "美元": "USD", "usd": "USD", "港元": "HKD", "港币": "HKD", "hkd": "HKD"}
_SCALES = {"": 1, "千": 1000, "thousand": 1000, "万": 10000,
           "million": 1000000, "亿": 100000000, "billion": 1000000000,
           "万亿": 1000000000000, "trillion": 1000000000000}


@dataclass(frozen=True)
class Money:
    start: int
    end: int
    token: str
    currency: str
    value: Decimal


def _amounts(text):
    for match in _MONEY.finditer(text):
        prefix = _CURRENCIES.get((match['prefix'] or '').lower())
        suffix = _CURRENCIES.get((match['suffix'] or '').lower())
        if not (prefix or suffix) or (prefix and suffix and prefix != suffix):
            continue
        token = match['number'].lstrip('+').replace(',', '')
        yield Money(*match.span('number'), token, prefix or suffix,
                    Decimal(token) * _SCALES[(match['scale'] or '').lower()])


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def monetary_number_binding(text, cited_values, missing, number_pattern):
    sources = [amount for source in _strings(cited_values) for amount in _amounts(source)]
    equivalents = {(a.currency, a.value) for a in sources}
    source_tokens = {a.token for a in sources}
    mentions = list(_amounts(text))
    supported_spans = {(a.start, a.end) for a in mentions if (a.currency, a.value) in equivalents}
    # A repeated token in a date, count, percentage or unsupported amount must
    # not be excused by an unrelated valid currency conversion in the same text.
    occurrences = {}
    for match in number_pattern.finditer(text):
        occurrences.setdefault(match.group().lstrip('+').replace(',', ''), []).append(match.span())
    remaining = {token for token in missing
                 if not occurrences.get(token) or not all(span in supported_spans for span in occurrences[token])}
    # Literal digit membership also cannot turn 12.69亿元 into 12.69 billion USD.
    remaining.update(a.token for a in mentions
                     if a.token in source_tokens and (a.currency, a.value) not in equivalents)
    return remaining
