"""akshare client tests: mapping, cache, and explainable failures (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from src.data import akshare_client
from src.data.akshare_client import AkshareUnavailable, fetch_ohlc, normalize_instrument


def _fake_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"日期": "2025-01-02", "开盘": 10.0, "收盘": 10.5, "最高": 10.8, "最低": 9.9},
        {"日期": "2025-01-03", "开盘": 10.5, "收盘": 11.0, "最高": 11.2, "最低": 10.4},
    ])


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(akshare_client, "_CACHE_ROOT", tmp_path / "cache")
    return tmp_path


def test_normalize_instrument_accepts_exchange_suffixes_and_refuses_synthetic():
    assert normalize_instrument("600000.SH") == "600000"
    assert normalize_instrument("000001.XSHE") == "000001"
    assert normalize_instrument("600000.xshg") == "600000"
    with pytest.raises(AkshareUnavailable, match="refused_synthetic"):
        normalize_instrument("SYN_POOL_A01")
    with pytest.raises(AkshareUnavailable, match="unsupported_instrument_suffix"):
        normalize_instrument("AAPL")


def test_fetch_maps_columns_labels_source_and_writes_cache(isolated_cache):
    calls = []
    def fetcher(symbol, period, start_date, end_date, adjust):
        calls.append((symbol, period, start_date, end_date, adjust))
        return _fake_frame()
    bars = fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=fetcher)
    assert calls == [("600000", "daily", "20250101", "20250131", "")]
    assert bars == [
        {"date": "2025-01-02", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9,
         "volume": None, "source_id": "akshare_public", "source_version": "1",
         "adjust": "", "is_synthetic": False},
        {"date": "2025-01-03", "open": 10.5, "close": 11.0, "high": 11.2, "low": 10.4,
         "volume": None, "source_id": "akshare_public", "source_version": "1",
         "adjust": "", "is_synthetic": False},
    ]
    # Second call is served from the cache without touching the network.
    def exploding_fetcher(**kwargs):
        raise AssertionError("network must not be hit on cache hit")
    assert fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=exploding_fetcher) == bars


def test_request_failure_is_explainable(isolated_cache):
    def fetcher(**kwargs):
        raise ConnectionError("network down")
    with pytest.raises(AkshareUnavailable, match="akshare_request_failed"):
        fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=fetcher)


def test_unrecognized_columns_fail_closed(isolated_cache):
    def fetcher(**kwargs):
        return pd.DataFrame([{"unexpected": 1}])
    with pytest.raises(AkshareUnavailable, match="akshare_columns_unrecognized"):
        fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=fetcher)


def test_invalid_window_dates_fail_closed(isolated_cache):
    with pytest.raises(AkshareUnavailable, match="invalid_market_window"):
        fetch_ohlc("600000.SH", "not-a-date", "2025-01-31", fetcher=lambda **kwargs: _fake_frame())


def test_lazy_import_failure_is_explainable(isolated_cache, monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", None)  # import akshare raises ImportError.
    with pytest.raises(AkshareUnavailable, match="akshare_import_failed"):
        fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31")


def test_corrupt_cache_is_a_miss_and_gets_replaced(isolated_cache):
    from src.data.akshare_client import _cache_path, cached_bars

    cache_file = _cache_path("600000", "2025-01-01", "2025-01-31", "")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text('{"source": "akshare_public", "bars": [{"date": "2025-01-0', encoding="utf-8")
    assert cached_bars("600000.SH", "2025-01-01", "2025-01-31") is None
    assert not cache_file.exists()  # corrupt entry removed, not surfaced as JSONDecodeError

    calls = []
    def fetcher(**kwargs):
        calls.append(kwargs)
        return _fake_frame()
    assert fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=fetcher)[0]["close"] == 10.5
    assert calls, "corrupt cache must fall back to a fresh fetch"
    assert cached_bars("600000.SH", "2025-01-01", "2025-01-31") is not None


def test_cache_write_uses_temp_file_and_atomic_rename(isolated_cache, monkeypatch):
    import os

    from src.data.akshare_client import _CACHE_ROOT, _cache_path

    replacements = []
    real_replace = os.replace

    def recording_replace(src, dst):
        replacements.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(akshare_client.os, "replace", recording_replace)
    fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=lambda **kwargs: _fake_frame())

    target = _cache_path("600000", "2025-01-01", "2025-01-31", "")
    assert len(replacements) == 1
    src, dst = replacements[0]
    assert dst == str(target)
    assert src.startswith(str(_CACHE_ROOT)) and src.endswith(".tmp") and src != dst
    assert target.exists()
    assert not list(_CACHE_ROOT.glob("*.tmp"))  # no half-written leftovers
    def exploding_fetcher(**kwargs):
        raise AssertionError("network must not be hit after atomic rename")
    assert fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=exploding_fetcher)[0]["close"] == 10.5


def test_non_finite_and_unparseable_rows_are_dropped(isolated_cache):
    frame = pd.DataFrame([
        {"日期": "2025-01-02", "开盘": 10.0, "收盘": 10.5, "最高": 10.8, "最低": 9.9},
        {"日期": "2025-01-03", "开盘": float("nan"), "收盘": 11.0, "最高": 11.2, "最低": 10.4},
        {"日期": "2025-01-04", "开盘": 11.0, "收盘": float("inf"), "最高": 11.2, "最低": 10.4},
        {"日期": "2025-01-05", "开盘": 11.0, "收盘": 0.0, "最高": 11.2, "最低": 10.4},
        {"日期": "not-a-date", "开盘": 11.0, "收盘": 11.1, "最高": 11.2, "最低": 10.4},
    ])
    bars = fetch_ohlc("600000.SH", "2025-01-01", "2025-01-31", fetcher=lambda **kwargs: frame)
    assert [item["date"] for item in bars] == ["2025-01-02"]
