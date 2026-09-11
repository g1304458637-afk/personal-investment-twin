"""akshare public OHLC client for same-instrument strategy comparison.

Fetches unadjusted daily A-share bars (public data, MIT-licensed client) with
a deterministic file cache.  Import of the heavy third-party package is lazy
so the sidecar handshake stays light.  All failures are explainable; nothing
here writes to user accounts, and synthetic instrument ids are refused.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

SOURCE_ID = "akshare_public"
SOURCE_VERSION = "1"
_CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "cache" / "akshare"
_COLUMN_MAP = {
    "日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
}


class AkshareUnavailable(RuntimeError):
    """The public market source could not answer; message is user-facing."""


def _cache_path(instrument: str, start: str, end: str) -> Path:
    return _CACHE_ROOT / f"{instrument}_{start}_{end}.json"


def normalize_instrument(instrument: str) -> str:
    """600000.SH / 600000.XSHG / 600000 -> 600000; refuses synthetic ids and unknown forms."""
    if instrument.upper().startswith("SYN"):
        raise AkshareUnavailable("refused_synthetic_instrument")
    text = instrument.strip().upper()
    if text.isdigit() and len(text) == 6:
        return text
    for suffix in (".SH", ".SZ", ".BJ", ".XSHG", ".XSHE", ".XBSE"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    raise AkshareUnavailable("unsupported_instrument_suffix")


def cached_bars(instrument: str, start: str, end: str) -> list[dict[str, Any]] | None:
    path = _cache_path(normalize_instrument(instrument), start, end)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["bars"]


def fetch_ohlc(instrument: str, start: str, end: str, *, force_refresh: bool = False,
               fetcher: Any = None) -> list[dict[str, Any]]:
    """Unadjusted daily OHLC for an A-share instrument, cache-first.

    ``start``/``end`` are ISO dates.  ``fetcher`` injects the akshare call in
    tests; production passes None to use the lazily imported real client.
    """
    normalized = normalize_instrument(instrument)
    if not force_refresh:
        cached = cached_bars(instrument, start, end)
        if cached is not None:
            return cached
    if fetcher is None:
        try:
            import akshare as akshare_module  # Heavy: import only when actually fetching.
        except Exception as exc:  # ImportError or a broken install: explainable, not a crash.
            raise AkshareUnavailable("akshare_import_failed") from exc

        def fetcher(symbol: str, period: str, start_date: str, end_date: str, adjust: str):
            return akshare_module.stock_zh_a_hist(symbol=symbol, period=period,
                start_date=start_date, end_date=end_date, adjust=adjust)

    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError as exc:
        raise AkshareUnavailable("invalid_market_window") from exc
    try:
        frame = fetcher(symbol=normalized, period="daily", start_date=start.replace("-", ""),
                        end_date=end.replace("-", ""), adjust="")  # adjust="": unadjusted bars.
    except AkshareUnavailable:
        raise
    except Exception as exc:
        raise AkshareUnavailable("akshare_request_failed") from exc
    missing = [column for column in _COLUMN_MAP if column not in getattr(frame, "columns", ())]
    if missing:
        raise AkshareUnavailable("akshare_columns_unrecognized")
    bars: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        bars.append({
            "date": str(row["日期"])[:10],
            "open": float(row["开盘"]), "close": float(row["收盘"]),
            "high": float(row["最高"]), "low": float(row["最低"]),
            "source_id": SOURCE_ID, "source_version": SOURCE_VERSION, "is_synthetic": False,
        })
    bars.sort(key=lambda item: item["date"])
    if not bars:
        raise AkshareUnavailable("akshare_empty_response")
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    _cache_path(normalized, start, end).write_text(
        json.dumps({"source": SOURCE_ID, "bars": bars}, ensure_ascii=False), encoding="utf-8")
    return bars
