"""Offline goldens for shared EMA and real-history content identity."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.public_technical import calculate_technical_indicators
from src.strategy.compare import multi_simulation_data, simulation_data_from_bars
from src.strategy.ema import clear_cache, ema_at, ema_series
from src.strategy.factors import _compute_ema_gap
from src.strategy.formula import _f_ema


def _bars(symbol: str, values: list[float], *, source: str = "fixture") -> list[dict]:
    del symbol
    first = date(2025, 1, 1)
    return [
        {"date": (first + timedelta(days=i)).isoformat(), "open": price,
         "high": price, "low": price, "close": price, "volume": float(100 + i),
         "currency": "CNY", "adjust": "hfq", "source_id": source,
         "source_version": "1"}
        for i, price in enumerate(values)
    ]


def test_ema_sma_seed_warmup_and_all_three_entry_points():
    clear_cache()
    values = [float(n) for n in range(1, 14)]
    bars = _bars("600000.SH", values)
    series = simulation_data_from_bars("600000.SH", bars, is_synthetic=False).series["600000.SH"]
    assert ema_series(values[:11], 12) == []
    assert ema_series(values[:12], 12) == [6.5]
    assert ema_series(values, 12) == [6.5, 7.5]
    assert _f_ema(series, 10, (12,)) is None
    assert _compute_ema_gap(series, 10, {"window": 12}) is None
    assert _f_ema(series, 11, (12,)) == 6.5
    assert _f_ema(series, 12, (12,)) == 7.5
    assert _compute_ema_gap(series, 12, {"window": 12}) == 13 / 7.5 - 1
    public = calculate_technical_indicators(bars, latest_bar_may_be_in_progress=False)
    assert public["metrics"]["ema_12"]["value"] == 7.5
    # Out-of-order queries and fresh instances must produce the same history.
    assert ema_at(series, 11, 12) == 6.5
    assert ema_at(series, 12, 12) == 7.5


def test_ema_uses_full_prefix_and_is_stable_under_repeated_queries():
    values = [10.0, 11.0, 12.0, 14.0, 10.0]
    series = simulation_data_from_bars("600000.SH", _bars("600000.SH", values),
                                       is_synthetic=False).series["600000.SH"]
    assert [_f_ema(series, i, (3,)) for i in range(5)] == [None, None, 11.0, 12.5, 11.25]
    assert [_f_ema(series, 4, (3,)) for _ in range(3)] == [11.25] * 3


def test_single_history_fingerprint_hashes_actual_values_and_provenance():
    rows = _bars("600000.SH", [10.0, 11.0, 12.0])
    def fingerprint(bars):
        return simulation_data_from_bars("600000.SH", bars, is_synthetic=False).fingerprint
    baseline = fingerprint(rows)
    assert baseline.startswith("history.v2:") and len(baseline) == len("history.v2:") + 64
    assert fingerprint(list(reversed(rows))) == baseline
    for key, new_value in (("open", 10.5), ("high", 12.5), ("low", 10.5),
                           ("close", 11.5), ("volume", 999.0),
                           ("source_id", "different"), ("adjust", "qfq"),
                           ("currency", "USD"), ("rule_version", "2"),
                           ("actions", [{"type": "split", "ratio": 2}])):
        changed = [dict(row) for row in rows]
        changed[1][key] = new_value
        if key == "open":
            changed[1]["low"] = new_value
        if key == "close":
            changed[1]["high"] = new_value
        assert fingerprint(changed) != baseline, key
    assert fingerprint([{k: v for k, v in row.items() if k != "currency"} for row in rows]) != baseline
    with pytest.raises(Exception, match="invalid volume"):
        fingerprint([{**rows[0], "volume": float("nan")}, *rows[1:]])


def test_multi_history_fingerprint_hashes_each_symbol_and_order_is_stable():
    a = _bars("600000.SH", [10.0, 11.0])
    b = _bars("000001.SZ", [20.0, 21.0])
    def fingerprint(mapping):
        return multi_simulation_data(mapping, is_synthetic=False).fingerprint
    baseline = fingerprint({"600000.SH": a, "000001.SZ": b})
    assert fingerprint({"000001.SZ": list(reversed(b)), "600000.SH": list(reversed(a))}) == baseline
    changed = [dict(row) for row in b]
    changed[0]["close"] = changed[0]["high"] = 22.0
    assert fingerprint({"600000.SH": a, "000001.SZ": changed}) != baseline
    assert fingerprint({"600000.SH": a}) != baseline
