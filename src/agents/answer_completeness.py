"""Deterministic answer-content checks over already authorized public records.

This module does not judge indicator meaning or calculate a new metric. It only
checks that a result-seeking technical question reports at least one displayable
value already present in a cited, complete ``public_technical`` record.
"""
from __future__ import annotations

import math
import re
from typing import Any


_RESULT_REQUEST = re.compile(
    r"(?:请|帮我)?(?:读取|读出|算出|计算一下|列出|给出|显示|对照).{0,100}(?:技术指标|均线|SMA|EMA|MACD|RSI|ATR|量比)"
    r"|(?:技术指标|均线|SMA|EMA|MACD|RSI|ATR|量比).{0,20}(?:数值|值是多少|结果|当前|最新|截至)"
    r"|(?:read|fetch|show|report|calculate|compute|compare).{0,100}(?:technical indicators?|SMA|EMA|MACD|RSI|ATR|volume ratio)"
    r"|(?:technical indicators?|SMA|EMA|MACD|RSI|ATR|volume ratio).{0,24}(?:values?|results?|current|latest|as of)",
    re.I,
)
_DEFINITION_ONLY = re.compile(
    r"(?:是什么|什么是|定义|原理|公式|如何理解|怎么理解|如何计算|怎么计算)"
    r"|(?:what is|definition|meaning|formula|how (?:is|are|do|does).{0,20}(?:calculated|work))",
    re.I,
)
_OBSERVATION_CONTEXT = re.compile(
    r"(?:SHSE|SZSE|BJSE):\d{6}|\d{4}-\d{2}-\d{2}|(?:当前|最新|截至|区间|日线|数值|结果)"
    r"|(?:current|latest|as of|date range|daily|value|result)",
    re.I,
)

_METRIC_LABELS = {
    "sma": re.compile(r"SMA|简单移动平均|简单均线|日均线", re.I),
    "ema": re.compile(r"EMA|指数移动平均|指数均线", re.I),
    "macd": re.compile(r"MACD|信号线|柱值|histogram|signal line", re.I),
    "rsi": re.compile(r"RSI|相对强弱", re.I),
    "atr": re.compile(r"ATR|平均真实波幅|真实波幅", re.I),
    "volume_ratio": re.compile(r"量比|volume ratio", re.I),
}
_NUMBER_AFTER_LABEL = re.compile(
    r"^(?:\s*(?:的?(?:值|结果)(?:\s*(?:为|是|等于))?|为|是|等于|=|:|：|value(?:\s+is)?|is|was|stood\s+at)\s*)"
    r"(?P<number>[-+−]?(?:\d+(?:\.\d+)?|\.\d+))(?!\d|[./-]\d)(?!\s*%)",
    re.I,
)
_COLUMN_VALUE = re.compile(
    r"^\s+(?P<number>[-+−]?(?:\d+(?:\.\d+)?|\.\d+))(?!\d|[./-]\d)(?!\s*%)",
    re.I,
)
_PERCENT_UNIT = re.compile(r"^\s*(?:%|％)")
_CNY_UNIT = re.compile(
    r"^\s*(?:CNY|RMB|CN¥|¥|￥|人民币|元|yuan)(?![A-Za-z])",
    re.I,
)
_OTHER_CURRENCY_UNIT = re.compile(
    r"^\s*(?:美元|USD|US\$|\$|dollars?)(?![A-Za-z])",
    re.I,
)
_MULTIPLE_UNIT = re.compile(r"^\s*(?:倍|times?\b|[x×](?![A-Za-z]))", re.I)


def question_requests_technical_results(question: object) -> bool:
    """Distinguish a requested observation from a pure definition question."""
    if not isinstance(question, str) or not _RESULT_REQUEST.search(question):
        return False
    return not (_DEFINITION_ONLY.search(question) and not _OBSERVATION_CONTEXT.search(question))


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _display(value: float) -> str:
    rounded = round(float(value), 2)
    return f"{0.0 if rounded == 0 else rounded:.2f}"


def _metric_values(record: dict[str, Any]) -> list[tuple[str, str, tuple[float, ...], tuple[str, ...]]]:
    value = record.get("value")
    metrics = value.get("metrics") if isinstance(value, dict) else None
    if not isinstance(metrics, dict):
        return []
    found = []
    for name, metric in metrics.items():
        if not isinstance(name, str) or not isinstance(metric, dict) or metric.get("status") != "available":
            continue
        family = next((key for key in _METRIC_LABELS if name.startswith(key)), None)
        if family is None:
            continue
        raw = tuple(float(metric[key]) for key in ("value", "line", "signal", "histogram")
                    if _finite(metric.get(key)))
        display = metric.get("display_value")
        displays = ((display,) if isinstance(display, str) else
                    tuple(item for item in display.values() if isinstance(item, str))
                    if isinstance(display, dict) else tuple(_display(item) for item in raw))
        if raw and displays:
            found.append((name, family, raw, displays))
    return found


def _complete_technical_records(payload: dict[str, Any]) -> dict[str, list[tuple[str, str, tuple[float, ...], tuple[str, ...]]]]:
    found = {}
    records = payload.get("actually_read_records")
    if not isinstance(records, list):
        return found
    for record in records:
        if (not isinstance(record, dict) or record.get("kind") != "public_technical"
                or record.get("availability") != "complete" or not isinstance(record.get("ref"), str)):
            continue
        value = record.get("value")
        quality = value.get("data_quality") if isinstance(value, dict) else None
        if isinstance(quality, dict) and quality.get("status") == "partial":
            continue
        metrics = _metric_values(record)
        if metrics:
            found[record["ref"]] = metrics
    return found


def _normalized(text: str) -> str:
    return text.replace("−", "-")


def _metric_label(name: str, family: str) -> re.Pattern[str]:
    numbers = [int(value) for value in re.findall(r"\d+", name)]
    if family == "sma" and numbers:
        window = numbers[0]
        return re.compile(rf"(?:(?<![A-Z])SMA\s*{window}(?!\d)|(?<![A-Z])MA\s*{window}(?!\d)|{window}\s*日(?:简单)?均线|均线\s*(?:SMA|MA)?\s*{window}(?!\d))", re.I)
    if family == "ema" and numbers:
        window = numbers[0]
        return re.compile(rf"(?:EMA\s*{window}(?!\d)|{window}\s*日(?:指数)?均线|指数(?:移动)?平均\s*{window}(?!\d))", re.I)
    if family in {"rsi", "atr"} and numbers:
        token = family.upper()
        chinese = "相对强弱(?:指标)?" if family == "rsi" else "平均真实波幅|真实波幅"
        return re.compile(rf"(?:(?:{token}|{chinese})(?:\s*(?:[\(（\[]\s*{numbers[0]}\s*[\)）\]]|{numbers[0]}(?!\d)))?)", re.I)
    if family == "macd":
        return re.compile(r"(?:MACD(?:\s*[\(（\[]\s*12\s*[,，/]\s*26\s*[,，/]\s*9\s*[\)）\]])?(?:\s*(?:线|line))?|信号线|柱值|histogram|signal line)", re.I)
    if family == "volume_ratio" and numbers:
        return re.compile(rf"(?:量比(?:\s*[\(（\[]?\s*{numbers[0]}\s*[\)）\]]?)?|volume ratio(?:\s*[\(\[]?\s*{numbers[0]}\s*[\)\]]?)?)", re.I)
    return _METRIC_LABELS[family]


def _parameter_values(name: str) -> set[float]:
    return {float(value) for value in re.findall(r"\d+", name)}


def _unit_is_compatible(suffix: str, family: str) -> bool:
    """Validate only a unit immediately attached to the matched result.

    Punctuation ends the unit position, so a later sentence mentioning money or
    a percentage cannot invalidate an otherwise valid metric result.
    """
    if _PERCENT_UNIT.match(suffix):
        return False
    cny = _CNY_UNIT.match(suffix) is not None
    other_currency = _OTHER_CURRENCY_UNIT.match(suffix) is not None
    currency = cny or other_currency
    multiple = _MULTIPLE_UNIT.match(suffix) is not None
    if family == "rsi":
        return not currency and not multiple
    if family == "volume_ratio":
        return not currency
    # Moving averages, ATR and MACD remain on the price scale. CNY/元 is valid,
    # while a ratio suffix would turn the copied number into another quantity.
    return not multiple and not other_currency


def _reports_metric(text: object, metrics: list[tuple[str, str, tuple[float, ...], tuple[str, ...]]]) -> bool:
    if not isinstance(text, str):
        return False
    normalized = _normalized(text)
    for name, family, raw_values, _display_values in metrics:
        label_pattern = _metric_label(name, family)
        for label in label_pattern.finditer(normalized):
            tail = normalized[label.end():label.end() + 48]
            explicit = _NUMBER_AFTER_LABEL.match(tail)
            column = None if explicit else _COLUMN_VALUE.match(tail)
            match = explicit or column
            if match is None:
                continue
            token = match.group("number")
            try:
                number = float(token)
            except ValueError:
                continue
            if not _unit_is_compatible(tail[match.end():], family):
                continue
            # A bare `RSI 14` or `MACD 12 26 9` is a parameter listing, not a
            # result. Parenthesized parameters are consumed by the label, so a
            # following column value remains valid (`RSI(14) 56.7`).
            if (column is not None and number in _parameter_values(name)
                    and not re.search(r"[\(（\[]", label.group(0))):
                continue
            if any(round(number, 2) == round(value, 2) for value in raw_values):
                return True
    return False


def technical_result_findings(payload: object) -> list[dict[str, object]]:
    """Return one safe, targeted finding when available results were omitted.

    Partial/unavailable records and all-warmup metric sets are intentionally out
    of scope: an honest explanation of those states is a complete answer.
    """
    if not isinstance(payload, dict):
        return []
    question = payload.get("question", payload.get("user_question"))
    if not question_requests_technical_results(question):
        return []
    records = _complete_technical_records(payload)
    candidate = payload.get("candidate")
    paragraphs = candidate.get("paragraphs") if isinstance(candidate, dict) else None
    if not records or not isinstance(paragraphs, list) or not paragraphs:
        return []
    target = 0
    for index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            continue
        refs = paragraph.get("refs")
        cited = [records[ref] for ref in refs if ref in records] if isinstance(refs, list) else []
        if not cited:
            continue
        target = index
        metrics = [item for group in cited for item in group]
        text = paragraph.get("text")
        if (isinstance(text, dict) and _reports_metric(text.get("zh"), metrics)
                and _reports_metric(text.get("en"), metrics)):
            return []
    return [{"paragraph_index": target,
        "problem": "The question requested calculated technical results, but the answer reported no actual available indicator value from a cited public_technical record. Add at least one core indicator's recorded display value in both languages; dates and the 12/26/9 parameters do not count."}]
