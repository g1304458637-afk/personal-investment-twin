"""Numeric text normalization shared by the CSV ingestion readers.

Hand-prepared generic CSVs and broker exports both carry human-formatted
numbers: thousands separators, currency suffixes and full-width characters.
The broker adapter normalized these; the generic reader rejected them, so a
user routed back to the "generic_csv_v1 format" hit a stricter parser than
the one that sent them there.  Both now share this one normalizer.
"""
from __future__ import annotations

import re

# Full-width ASCII (０-９，．，＋－…) folds to its ASCII counterpart;
# \u3000 is the full-width space.
_FULLWIDTH_MAP: dict[str, str] = {
    chr(0xFF01 + offset): chr(0x21 + offset) for offset in range(0x5E)
}
_FULLWIDTH_MAP["\u3000"] = " "

_STRIP_CHARS = (" ", ",", "元", "￥", "¥")
_SIGN_RE = re.compile(r"^[+-]?")


def clean_numeric_text(raw: str) -> str:
    """Fold full-width chars and strip separators/currency around a number.

    The sign (if any) is preserved even though the strip set contains "，":
    "-1,234.56" must stay negative.
    """
    text = raw.translate(_FULLWIDTH_MAP)
    sign = ""
    match = _SIGN_RE.match(text)
    if match and text[: match.end()] in ("-", "+"):
        sign, text = text[: match.end()], text[match.end() :]
    for char in _STRIP_CHARS:
        text = text.replace(char, "")
    return sign + text.strip()
