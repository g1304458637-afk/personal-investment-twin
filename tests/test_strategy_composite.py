"""Composite user-strategy tests: validation sandbox, factor goldens,
AND-entry, reverse exit, fixed stop, risk sizing."""
from __future__ import annotations

import pandas as pd
import pytest

from src.strategy.composite import (
    UserStrategyError,
    build_user_strategy_spec,
    make_provider,
    strategy_id_for,
    validate_user_strategy,
)
from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from tests.strategy_fixtures import bar, dataset_writer, flat_bar


def bdays(start: str, count: int) -> list[str]:
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


BASE_SPEC = {
    "schema_version": "user_strategy.v1",
    "name": "测试策略",
    "entry": {"all_of": [{"factor": "breakout_high", "params": {"window": 20}, "op": "true"}]},
    "exit": {"any_of": [{"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}],
             "stop_loss_pct": 0.10},
    "sizing": {"mode": "equal_weight", "fraction": 0.25},
    "constraints": {"max_positions": 4},
}


def breakout_dataset() -> tuple[list[str], list[dict]]:
    days = bdays("2025-01-02", 60)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    # Ramp up: breakout, then a slide that breaks the 10-day low.
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.2 * (i + 1)) for i, text in enumerate(days[30:50])]
    bars += [flat_bar(text, "SYN_POOL_B01", 14.0 - 0.6 * (i + 1)) for i, text in enumerate(days[50:])]
    return days, bars


def test_validation_sandbox_rejects_unknown_fields_factors_and_binds():
    raw = dict(BASE_SPEC, intruder=1)
    with pytest.raises(UserStrategyError, match="未知字段"):
        validate_user_strategy(raw)
    bad_factor = {"**": None}
    import copy
    spec = copy.deepcopy(BASE_SPEC)
    spec["entry"]["all_of"][0]["factor"] = "secret_alpha"
    with pytest.raises(UserStrategyError, match="未知因子"):
        validate_user_strategy(spec)
    spec = copy.deepcopy(BASE_SPEC)
    spec["entry"]["all_of"][0]["params"] = {"window": 20, "symbol": "600000.SH"}
    with pytest.raises(UserStrategyError, match="未知参数"):
        validate_user_strategy(spec)
    spec = copy.deepcopy(BASE_SPEC)
    spec["entry"]["all_of"] = spec["entry"]["all_of"] * 4
    with pytest.raises(UserStrategyError, match="1~3"):
        validate_user_strategy(spec)
    no_exit = copy.deepcopy(BASE_SPEC)
    no_exit["exit"] = {"any_of": [], "stop_loss_pct": None}
    with pytest.raises(UserStrategyError, match="至少需要一种退出机制"):
        validate_user_strategy(no_exit)


def test_build_spec_generates_user_provenance_and_stable_id():
    spec, normalized = build_user_strategy_spec(BASE_SPEC)
    assert spec.strategy_id.startswith("user_")
    assert spec.strategy_id == strategy_id_for(normalized)
    sources = {rule["source"] for rule in spec.rule_table}
    assert "user_defined" in sources and "system_execution" in sources
    assert any("不加仓" in rule["statement"] for rule in spec.rule_table)
    assert any("不是经典策略" in rule["statement"] for rule in spec.rule_table)
    # Reordering keys must not change the id (canonical JSON).
    spec2, _ = build_user_strategy_spec(dict(reversed(list(BASE_SPEC.items()))))
    assert spec2.strategy_id == spec.strategy_id


def test_entry_and_reverse_exit_round_trip(dataset_writer):
    days, bars = breakout_dataset()
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    spec_dict = {**BASE_SPEC, "exit": {"any_of": [
        {"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}], "stop_loss_pct": None}}
    spec, normalized = build_user_strategy_spec(spec_dict)
    result = run_simulation(spec, data, signal_provider=make_provider(normalized))
    buys = [f for f in result.fills if f.side == "BUY"]
    sells = [f for f in result.fills if f.side == "SELL"]
    assert buys and sells, "ramp-then-slide must produce entry and exit"
    assert any(o.reason_code == "user_entry" for o in result.orders)
    assert any(o.reason_code == "user_exit" for o in result.orders)


def test_stop_loss_fires_on_gap_cliff(dataset_writer):
    days = bdays("2025-01-02", 60)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    bars.append(bar(days[30], "SYN_POOL_B01", 10.0, 10.5, 10.0, 10.5))  # breakout close
    bars.append(bar(days[31], "SYN_POOL_B01", 10.5, 10.5, 10.5, 10.5))  # entry fills @10.5
    # Gap cliff: open 8.0 is below the 10% stop (9.45) -> stop fires at the open.
    bars.append(bar(days[32], "SYN_POOL_B01", 8.0, 8.2, 7.8, 8.0))
    bars += [flat_bar(text, "SYN_POOL_B01", 8.0) for text in days[33:]]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    spec, normalized = build_user_strategy_spec(BASE_SPEC)
    result = run_simulation(spec, data, signal_provider=make_provider(normalized))
    assert any(f.trigger == "stop_loss" for f in result.fills)


def test_and_conditions_require_every_factor(dataset_writer):
    days, bars = breakout_dataset()
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    spec_dict = {
        "schema_version": "user_strategy.v1", "name": "AND策略",
        "entry": {"all_of": [
            {"factor": "breakout_high", "params": {"window": 20}, "op": "true"},
            {"factor": "rsi", "params": {"window": 14}, "op": "lt", "threshold": 20},
        ]},
        "exit": {"any_of": [{"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}],
                 "stop_loss_pct": None},
        "sizing": {"mode": "equal_weight", "fraction": 0.25},
        "constraints": {"max_positions": 4},
    }
    spec, normalized = build_user_strategy_spec(spec_dict)
    # On the breakout day RSI is high (ramp), so the AND must block the entry.
    provider = make_provider(normalized)
    day = data.dates[35]
    exits, candidates = provider(spec.params, data, day, set(), set(), {"equity": 1e6})
    assert candidates == []
    result = run_simulation(spec, data, signal_provider=provider)
    assert result.fills == []


def test_risk_unit_sizing_golden(dataset_writer):
    days = bdays("2025-01-02", 60)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.2 * (i + 1)) for i, text in enumerate(days[30:50])]
    bars += [flat_bar(text, "SYN_POOL_B01", 14.0) for text in days[50:59]]
    bars.append(bar(days[59], "SYN_POOL_B01", 14.0, 14.5, 13.8, 14.2))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    spec_dict = {
        "schema_version": "user_strategy.v1", "name": "风险定尺",
        "entry": {"all_of": [{"factor": "breakout_high", "params": {"window": 20}, "op": "true"}]},
        "exit": {"any_of": [{"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}],
                 "stop_loss_pct": None},
        "sizing": {"mode": "risk_unit", "risk_fraction": 0.01, "notional_cap": 0.25},
        "constraints": {"max_positions": 4},
    }
    spec, normalized = build_user_strategy_spec(spec_dict)
    provider = make_provider(normalized)
    day = data.dates[59]
    exits, candidates = provider(spec.params, data, day, set(), set(), {"equity": 1_000_000.0})
    entry = next(c for c in candidates if c.kind == "entry_candidate")
    price = 14.2
    # 1% risk / (atr_ratio * price) shares, capped by 25% notional; lot-rounded.
    from src.strategy.factors import evaluate_factor, FACTOR_LIBRARY
    import src.strategy.factors as factors_mod
    series = data.series["SYN_POOL_B01"]
    idx = series.index_on_or_before(day)
    atr_ratio = factors_mod._atr_ratio(series, idx, 14)
    raw = min(0.01 * 1_000_000 / (atr_ratio * price), 0.25 * 1_000_000 / price)
    assert entry.intended_quantity == float(int(raw / 100) * 100)
