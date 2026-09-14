"""Regression tests for the 2026-09 engine audit fixes.

Each test pins a bug found by the pre-open-source review: the turtle 2N stop
written as 0.0, the composite trailing stop using an ATR ratio as an absolute
price, `not` flipping insufficient data into a signal, RSI meaning different
things in the two user modes, adds wiping a ratcheted trailing stop, splits
with an ex-date off the bar calendar, the max-drawdown peak date, and the
r_multiple summary block.
"""
from __future__ import annotations

import datetime

import pandas as pd
import pytest

from src.strategy.account import StrategyAccount
from src.strategy.composite import (
    build_user_strategy_spec,
    make_provider,
)
from src.strategy.data import StrategyDataError, load_simulation_data
from src.strategy.engine import _build_summary, run_simulation
from src.strategy.formula import _f_rsi
from src.strategy.factors import _rsi
from src.strategy.records import DayRecord
from src.strategy.strategies.turtle import build_turtle_spec
from tests.strategy_fixtures import bar, dataset_writer, flat_bar


def bdays(start: str, count: int) -> list[str]:
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


def test_turtle_trailing_stop_price_stays_positive_and_fires(dataset_writer):
    # The engine used to read the stop_update condition's "threshold" (0.0 for
    # turtle), so every 2N stop was written as 0.0 and could never fire.
    days = bdays("2025-01-02", 130)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:56]]
    # Short climb: breakout + pyramid adds cap out at 4 units around 12.0, and
    # turtle only re-arms its stop on fills, so the stop sits at ~11.8
    # (last entry - 2N) from here on.
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.25 * (index + 1))
             for index, text in enumerate(days[56:66])]
    bars += [flat_bar(text, "SYN_POOL_B01", 13.0) for text in days[66:86]]
    # Intraday pierce below the ~11.8 stop while the close (13.0) stays above
    # the 20-day low: no low-exit order competes, so the next morning's stop
    # check must fire.
    bars.append(bar(days[86], "SYN_POOL_B01", 13.0, 13.0, 11.5, 13.0))
    bars += [flat_bar(text, "SYN_POOL_B01", 13.0) for text in days[87:]]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    result = run_simulation(build_turtle_spec(), data)

    updates = [e for d in result.days for e in d.events if e.get("kind") == "stop_updated"]
    assert updates, "the climb must produce trailing-stop updates"
    assert all(e["stop_price"] > 0 for e in updates), "a 0.0 stop price means the contract broke again"
    stop_fills = [f for f in result.fills if f.trigger == "stop_loss"]
    assert stop_fills, "the 2N stop must fire on the plunge, not just the 20-day-low exit"


def test_composite_trailing_stop_distance_matches_atr_rule(dataset_writer):
    # Rule text: stop = close - mult x ATR(14) in absolute price terms. The
    # provider used to subtract mult x (ATR/close), hugging the close.
    days = bdays("2025-01-02", 80)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    # Keep climbing to the end: ATR(14) then stays ~0.3 (every TR is 0.3),
    # so a ratcheted stop must sit ~0.6 below the close, not a few ticks.
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.3 * (i + 1)) for i, text in enumerate(days[30:])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    v2 = {"schema_version": "user_strategy.v2", "name": "跟踪止损距离",
          "entry": {"all_of": [{"factor": "breakout_high", "params": {"window": 20}, "op": "true"}]},
          "exit": {"any_of": [], "stop_loss_pct": None, "atr_trailing_mult": 2.0},
          "adds": {"max_units": 2},
          "sizing": {"mode": "risk_unit", "risk_fraction": 0.01, "notional_cap": 0.25},
          "constraints": {"max_positions": 4}}
    data = load_simulation_data(dataset_writer(universe, bars))
    spec, normalized = build_user_strategy_spec(v2)
    result = run_simulation(spec, data, signal_provider=make_provider(normalized))

    holdings = [h for d in result.days for h in d.holdings if h.get("stop_price")]
    assert holdings, "the climb must produce a ratcheted trailing stop"
    # ATR(14) over the steady +0.3 climb is ~0.3, so the stop must sit about
    # 2 x 0.3 = 0.6 below the close — not a few ticks below it.
    checked = 0
    for holding in holdings:
        close = holding["mark_price"]
        distance = close - holding["stop_price"]
        assert 0.3 < distance < 1.2, (
            f"stop distance {distance:.3f} at close {close:.2f} does not match 2 x ATR(~0.3)")
        checked += 1
    assert checked >= 3


def test_not_never_flips_insufficient_data_into_a_signal(dataset_writer):
    # volume_ratio is None when bars carry no volume (the synthetic universe);
    # `not (volume_ratio(20) > 2)` used to evaluate True every day and enter.
    from src.strategy.composite import FORMULA_SCHEMA, build_formula_strategy_spec, make_formula_provider

    days = bdays("2025-01-02", 60)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    raw = {"schema_version": FORMULA_SCHEMA, "name": "not 回归",
           "entry_formula": "not(volume_ratio(20) > 2)",
           "exit_formula": "close < lowest(10)",
           "stop_loss_pct": None, "atr_trailing_mult": None,
           "sizing": {"mode": "equal_weight", "fraction": 0.25},
           "constraints": {"max_positions": 4}}
    data = load_simulation_data(dataset_writer(universe, bars))
    spec, normalized = build_formula_strategy_spec(raw)
    result = run_simulation(spec, data, signal_provider=make_formula_provider(normalized))
    assert not result.fills, "volume is unavailable, so not(...) must keep the strategy out"


def test_formula_rsi_matches_factor_library_rsi(dataset_writer):
    days = bdays("2025-01-02", 45)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.2 * (index % 7))
            for index, text in enumerate(days)]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    series = data.series["SYN_POOL_B01"]
    for index in range(20, len(days)):
        assert _f_rsi(series, index, [14]) == _rsi(tuple(series.adjusted_close[: index + 1]), 14)


def test_add_without_stop_keeps_the_ratcheted_trailing_stop():
    account = StrategyAccount.opening(1_000_000.0)
    account.apply_buy("A", 100, 20.0, 0.0, day=datetime.date(2025, 1, 2), stop_price=19.0)
    # An add that carries no stop must not wipe the provider's trailing stop.
    account.apply_buy("A", 100, 21.0, 0.0, day=datetime.date(2025, 1, 3), stop_price=None)
    assert account.positions["A"].stop_price == 19.0
    # A fill that carries a stop still re-arms it.
    account.apply_buy("A", 100, 22.0, 0.0, day=datetime.date(2025, 1, 4), stop_price=20.9)
    assert account.positions["A"].stop_price == 20.9


def test_split_ex_date_off_the_bar_calendar_is_rejected(dataset_writer):
    days = bdays("2025-01-02", 30)
    # Skip days[10]: the split's ex-date lands on a calendar gap.
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days if text != days[10]]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    actions = [{"instrument": "SYN_POOL_B01", "ex_date": days[10], "action": "split", "ratio": 2.0}]
    with pytest.raises(StrategyDataError, match="ex_date"):
        load_simulation_data(dataset_writer(universe, bars, actions))


def test_split_on_a_traded_day_still_loads(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    actions = [{"instrument": "SYN_POOL_B01", "ex_date": days[15], "action": "split", "ratio": 2.0}]
    data = load_simulation_data(dataset_writer(universe, bars, actions))
    assert data.dates[0] is not None


def test_max_drawdown_peak_date_is_the_peak_before_the_trough():
    def record(day_text: str, equity: float, dd: float) -> DayRecord:
        return DayRecord(day=datetime.date.fromisoformat(day_text),
                         universe_count=1, equity=equity, drawdown_from_peak=dd)

    days = [record("2025-01-02", 100.0, 0.0), record("2025-01-03", 80.0, -0.2),
            record("2025-01-06", 120.0, 0.0)]
    round_trips = [{"instrument": "A", "closed_on": "2025-01-06", "pnl": 100.0,
                    "reason": "signal_exit", "r_multiple": 2.0},
                   {"instrument": "B", "closed_on": "2025-01-06", "pnl": -40.0,
                    "reason": "stop_loss", "r_multiple": -1.0},
                   {"instrument": "C", "closed_on": "2025-01-06", "pnl": 5.0,
                    "reason": "signal_exit", "r_multiple": None}]
    summary = _build_summary(None, 100.0, days, [], [], round_trips)
    assert summary["max_drawdown_peak_date"] == "2025-01-02"
    assert summary["max_drawdown_trough_date"] == "2025-01-03"
    stats = summary["r_multiple_stats"]
    assert stats["count"] == 2
    assert stats["avg_r"] == pytest.approx(0.5)
    assert stats["median_r"] == pytest.approx(0.5)
    assert stats["min_r"] == pytest.approx(-1.0)
    assert stats["max_r"] == pytest.approx(2.0)
    assert stats["skipped_no_stop"] == 1


def test_summary_without_r_bearing_trades_reports_nulls():
    def record(day_text: str, equity: float, dd: float) -> DayRecord:
        return DayRecord(day=datetime.date.fromisoformat(day_text),
                         universe_count=1, equity=equity, drawdown_from_peak=dd)

    days = [record("2025-01-02", 100.0, 0.0)]
    summary = _build_summary(None, 100.0, days, [], [], [])
    stats = summary["r_multiple_stats"]
    assert stats["count"] == 0 and stats["avg_r"] is None and stats["median_r"] is None
