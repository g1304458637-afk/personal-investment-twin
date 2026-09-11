"""Same-instrument comparison tests: golden window PnL, isolation, determinism."""
from __future__ import annotations

from datetime import date

import pytest

from src.strategy.compare import (
    ComparisonError,
    compare_episode,
    compare_portfolio,
    simulation_data_from_bars,
)
from src.strategy.strategies.t1 import build_t1_spec

SPEC = build_t1_spec()


def bdays(start: str, count: int) -> list[str]:
    import pandas as pd
    return [value.date().isoformat() for value in pd.bdate_range(start, periods=count)]


def flat(text: str, close: float) -> dict:
    return {"date": text, "open": close, "high": close, "low": close, "close": close}


def bar(text: str, o: float, h: float, low: float, c: float) -> dict:
    return {"date": text, "open": o, "high": h, "low": low, "close": c}


def scenario_bars() -> list[dict]:
    """Climbing-base breakout: the rule buys day 27 @12.0 and exits day 29 @11.1."""
    days = bdays("2025-01-02", 32)
    bars = [flat(text, 11.3) for text in days[:25]]
    bars.append(bar(days[25], 11.3, 12.0, 11.3, 12.0))   # breakout close -> signal
    bars.append(bar(days[26], 12.0, 12.0, 12.0, 12.0))   # entry fill at open 12.0
    bars.append(bar(days[27], 12.0, 12.0, 11.1, 11.1))   # exit signal (stop untouched)
    bars.append(bar(days[28], 11.1, 11.1, 11.1, 11.1))   # exit fill at open 11.1
    bars.extend(flat(text, 11.1) for text in days[29:])
    return bars


def user_rows() -> list[dict]:
    return [
        {"execution_id": "u1", "day": "2025-02-07", "side": "BUY", "quantity": 1000.0,
         "price": 12.0, "fee": 5.0},
        {"execution_id": "u2", "day": "2025-02-11", "side": "SELL", "quantity": 1000.0,
         "price": 11.1, "fee": 16.1},
    ]


def test_same_instrument_replay_and_window_golden():
    report = compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                             executions=user_rows(), episode_id="ep1",
                             window_start=date(2025, 2, 6), window_end=date(2025, 2, 12))
    # Rule path: BUY 20800 @12 (fee 74.88), SELL 20800 @11.1 (fee 300.144).
    rule_fills = [(fill["side"], fill["quantity"], fill["price"]) for fill in report["rule_fills"]]
    assert rule_fills == [("BUY", 20800.0, 12.0), ("SELL", 20800.0, 11.1)]
    # Golden window net cash flows: buy outflows and sell inflows (with fees) inside the window.
    assert round(report["window_rule_net_cash_flow"], 6) == round((20800 * 11.1 - 300.144) - (20800 * 12.0 + 74.88), 6)
    assert round(report["window_user_net_cash_flow"], 6) == round((1000 * 11.1 - 16.1) - (1000 * 12.0 + 5.0), 6)
    assert report["window_user_fill_count"] == 2 and report["window_rule_fill_count"] == 2
    assert report["bar_count"] == 32
    assert any("不构成任何买卖结论" in item for item in report["limitations"])


def test_window_out_of_range_records_are_excluded_with_a_note():
    rows = user_rows() + [
        {"execution_id": "u3", "day": "2025-01-03", "side": "BUY", "quantity": 500.0,
         "price": 11.3, "fee": 5.0},
    ]
    report = compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                             executions=rows, episode_id="ep1",
                             window_start=date(2025, 2, 6), window_end=date(2025, 2, 12))
    assert report["window_user_fill_count"] == 2
    assert round(report["window_user_net_cash_flow"], 6) == -921.1
    assert any("落在可用行情范围之外" in item for item in report["limitations"])
    assert len(report["user_executions"]) == 3


def test_synthetic_isolation_refuses_mixed_or_mislabeled_data():
    with pytest.raises(ComparisonError, match="synthetic bars must use a SYN-prefixed"):
        simulation_data_from_bars("600000.SH", scenario_bars(), is_synthetic=True)
    with pytest.raises(ComparisonError, match="real bars cannot use synthetic"):
        simulation_data_from_bars("SYN_POOL_A01", scenario_bars(), is_synthetic=False)
    with pytest.raises(ComparisonError, match="belongs to"):
        compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                        executions=[{**user_rows()[0], "symbol": "SYN_POOL_A02"}],
                        episode_id="ep1", window_start=None, window_end=None)


def test_close_only_or_invalid_bars_fail_closed():
    days = bdays("2025-01-02", 30)
    close_only = [{"date": text, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0}
                  for text in days]
    # OHLC shape is required; a missing low is an invalid bar, not a guess.
    broken = [{key: row[key] for key in ("date", "open", "high", "close")} for row in close_only]
    with pytest.raises(ComparisonError, match="invalid OHLC"):
        simulation_data_from_bars("SYN_POOL_A01", broken, is_synthetic=True)
    duplicated = [*close_only, close_only[0]]
    with pytest.raises(ComparisonError, match="duplicate bar date"):
        simulation_data_from_bars("SYN_POOL_A01", duplicated, is_synthetic=True)
    inverted = [{"date": days[0], "open": 10.0, "high": 9.0, "low": 11.0, "close": 10.0}]
    with pytest.raises(ComparisonError, match="inconsistent OHLC"):
        simulation_data_from_bars("SYN_POOL_A01", inverted, is_synthetic=True)


def test_execution_amount_validation_fails_closed():
    with pytest.raises(ComparisonError, match="invalid side"):
        compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                        executions=[{**user_rows()[0], "side": "LONG"}],
                        episode_id="ep1", window_start=None, window_end=None)
    with pytest.raises(ComparisonError, match="invalid amounts"):
        compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                        executions=[{**user_rows()[0], "quantity": 0.0}],
                        episode_id="ep1", window_start=None, window_end=None)
    with pytest.raises(ComparisonError, match="calendar date"):
        compare_episode(SPEC, scenario_bars(), instrument="SYN_POOL_A01", is_synthetic=True,
                        executions=[{key: value for key, value in user_rows()[0].items()
                                     if key != "day"}],
                        episode_id="ep1", window_start=None, window_end=None)


def test_reruns_are_identical():
    kwargs = dict(instrument="SYN_POOL_A01", is_synthetic=True, executions=user_rows(),
                  episode_id="ep1", window_start=date(2025, 2, 6), window_end=date(2025, 2, 12))
    first = compare_episode(SPEC, scenario_bars(), **kwargs)
    second = compare_episode(SPEC, scenario_bars(), **kwargs)
    assert first == second


def test_portfolio_parallel_states_no_verdict_and_no_ranking():
    parallel = compare_portfolio(
        {"final_value": 980_000.0, "round_trips": 5},
        {"strategy": {"strategy_id": "toujing_t1_breakout_trend", "version": "1"},
         "summary": {"final_equity": 1_210_639.22, "total_return": 0.2106, "max_drawdown": -0.2743,
                     "total_fees": 95_173.78, "round_trip_count": 188, "win_rate": 0.1011,
                     "trading_days": 784}},
        note="并列事实",
    )
    assert parallel["strategy"]["strategy_id"] == "toujing_t1_breakout_trend"
    assert parallel["user"]["final_value"] == 980_000.0
    assert any("不是能力排名" in item for item in parallel["limitations"])
