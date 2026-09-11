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
         "source_id": "akshare_public", "source_version": "1", "is_synthetic": False},
        {"date": "2025-01-03", "open": 10.5, "close": 11.0, "high": 11.2, "low": 10.4,
         "source_id": "akshare_public", "source_version": "1", "is_synthetic": False},
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
