"""akshare public OHLC client for same-instrument strategy comparison.

Fetches unadjusted daily A-share bars (public data, MIT-licensed client) with
a deterministic file cache.  Import of the heavy third-party package is lazy
so the sidecar handshake stays light.  All failures are explainable; nothing
here writes to user accounts, and synthetic instrument ids are refused.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
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


def _cache_path(instrument: str, start: str, end: str, adjust: str) -> Path:
    suffix = adjust or "raw"
    return _CACHE_ROOT / f"{instrument}_{start}_{end}_{suffix}.json"


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


def cached_bars(instrument: str, start: str, end: str, adjust: str = "") -> list[dict[str, Any]] | None:
    """Return cached bars, treating an unreadable or corrupt file as a miss.

    A truncated or tampered cache entry must never surface as a raw
    ``JSONDecodeError``/``OSError``; it is dropped (the file is removed) and
    the caller falls through to a fresh fetch.
    """
    path = _cache_path(normalize_instrument(instrument), start, end, adjust)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        bars = payload["bars"]
    except (OSError, ValueError, KeyError, TypeError):
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return bars if isinstance(bars, list) else None


def fetch_ohlc(instrument: str, start: str, end: str, *, force_refresh: bool = False,
               fetcher: Any = None, adjust: str = "") -> list[dict[str, Any]]:
    """Daily OHLC for an A-share instrument, cache-first.

    ``adjust``: "" for unadjusted (real traded prices) or "hfq" for the
    backward-adjusted continuous series backtests need.  ``start``/``end``
    are ISO dates.  ``fetcher`` injects the akshare call in tests;
    production passes None to use the lazily imported real client.
    """
    if adjust not in {"", "hfq", "qfq"}:
        raise AkshareUnavailable("unsupported_adjust")
    normalized = normalize_instrument(instrument)
    if not force_refresh:
        cached = cached_bars(instrument, start, end, adjust)
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
                        end_date=end.replace("-", ""), adjust=adjust)
    except AkshareUnavailable:
        raise
    except Exception as exc:
        raise AkshareUnavailable("akshare_request_failed") from exc
    missing = [column for column in _COLUMN_MAP if column not in getattr(frame, "columns", ())]
    if missing:
        raise AkshareUnavailable("akshare_columns_unrecognized")
    bars: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        try:
            observation_date = date.fromisoformat(str(row["日期"])[:10]).isoformat()
            values = {
                "open": float(row["开盘"]),
                "close": float(row["收盘"]),
                "high": float(row["最高"]),
                "low": float(row["最低"]),
            }
        except (TypeError, ValueError):
            continue
        # Only finite, positive OHLC observations are contract-valid; NaN/inf
        # rows (suspensions, vendor glitches) are skipped, never cached.
        if any(not math.isfinite(value) or value <= 0 for value in values.values()):
            continue
        try:
            volume_raw = row.get("成交量")
            volume = float(volume_raw) if volume_raw not in (None, "", 0) else None
            if volume is not None and not math.isfinite(volume):
                volume = None
        except (TypeError, ValueError):
            # A vendor volume format change must degrade to an unknown-volume
            # row, exactly like the OHLC row-skip policy above — never an
            # uncaught ValueError escaping fetch_ohlc.
            volume = None
        bars.append({
            "date": observation_date,
            "open": values["open"], "close": values["close"],
            "high": values["high"], "low": values["low"],
            "volume": volume,
            "source_id": SOURCE_ID, "source_version": SOURCE_VERSION,
            "adjust": adjust, "is_synthetic": False,
        })
    bars.sort(key=lambda item: item["date"])
    if not bars:
        raise AkshareUnavailable("akshare_empty_response")
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target = _cache_path(normalized, start, end, adjust)
    # Write-then-rename keeps concurrent readers from ever observing a
    # half-written cache file under the final name.
    descriptor, temp_name = tempfile.mkstemp(
        dir=_CACHE_ROOT, prefix=f"{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps({"source": SOURCE_ID, "adjust": adjust, "bars": bars}, ensure_ascii=False)
            )
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return bars
