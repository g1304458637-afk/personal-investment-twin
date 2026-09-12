"""L4 formula mode: DSL whitelist, evaluation goldens, end-to-end runs."""
from __future__ import annotations

import pandas as pd
import pytest

from src.strategy.composite import (
    FORMULA_SCHEMA,
    UserStrategyError,
    build_formula_strategy_spec,
    make_formula_provider,
)
from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from src.strategy.formula import FormulaError, parse_formula
from tests.strategy_fixtures import bar, dataset_writer, day, flat_bar


def bdays(start: str, count: int) -> list[str]:
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


def base_spec(**overrides) -> dict:
    spec = {
        "schema_version": FORMULA_SCHEMA,
        "name": "公式测试",
        "entry_formula": "close > highest(20)",
        "exit_formula": "close < lowest(10)",
        "stop_loss_pct": None,
        "sizing": {"mode": "equal_weight", "fraction": 0.25},
        "constraints": {"max_positions": 4},
    }
    spec.update(overrides)
    if spec.get("atr_trailing_mult") is None and "atr_trailing_mult" not in overrides:
        spec["atr_trailing_mult"] = None
    return spec


def test_parser_accepts_formulas_and_rejects_hostile_code():
    parse_formula("rsi(14) < 30 and close > sma(20) * 1.05")
    parse_formula("close > highest(20) and volume_ratio(20) > 1.5 or cross_up(5, 20)")
    for bad, why in [
        ('__import__("os").system("rm -rf /")', "被禁止"),
        ("open('/data/db.sqlite').read()", "只允许调用"),
        ("close.channel", "Attribute"),
        ("[x for x in closes]", "ListComp"),
        ("close < entry_price and True", "数字常量"),
        ("close < -entry_price", None),
    ]:
        if why is None:
            parse_formula(bad)
        else:
            with pytest.raises(FormulaError, match=why if why != "数字常量" else "数字常量"):
                parse_formula(bad)


def test_entry_price_rejected_in_entry_formula():
    with pytest.raises(UserStrategyError, match="entry_price"):
        build_formula_strategy_spec({
            **base_spec(),
            "entry_formula": "close < entry_price * 0.92",
            "exit_formula": None, "stop_loss_pct": 0.1,
        })


def test_ramp_slides_round_trip(dataset_writer):
    days = bdays("2025-01-02", 70)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.2 * (i + 1)) for i, text in enumerate(days[30:50])]
    bars += [flat_bar(text, "SYN_POOL_B01", 14.0 - 0.6 * (i + 1)) for i, text in enumerate(days[50:])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    spec, normalized = build_formula_strategy_spec({
        "schema_version": FORMULA_SCHEMA, "name": "突破",
        "entry_formula": "close > highest(20)",
        "exit_formula": "close < lowest(10)",
        "sizing": {"mode": "equal_weight", "fraction": 0.25},
        "constraints": {"max_positions": 4},
    })
    data = load_simulation_data(dataset_writer(universe, bars))
    result = run_simulation(spec, data, signal_provider=make_formula_provider(normalized))
    buys = [f for f in result.fills if f.side == "BUY"]
    sells = [f for f in result.fills if f.side == "SELL"]
    assert buys and sells, "ramp then slide must complete a round trip"
    assert any(o.reason_code == "user_entry" for o in result.orders)
    assert any(o.reason_code == "user_exit" for o in result.orders)


def test_trailing_stop_and_adds_end_to_end(dataset_writer):
    days = bdays("2025-01-02", 80)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:30]]
    bars += [flat_bar(text, "SYN_POOL_B01", 10.0 + 0.3 * (i + 1)) for i, text in enumerate(days[30:60])]
    bars += [flat_bar(text, "SYN_POOL_B01", 19.0 - 0.5 * (i + 1)) for i, text in enumerate(days[60:])]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    spec, normalized = build_formula_strategy_spec({
        "schema_version": FORMULA_SCHEMA, "name": "跟踪+加仓",
        "entry_formula": "close > highest(20)",
        "exit_formula": "",
        "stop_loss_pct": None,
        "atr_trailing_mult": 2.0,
        "adds": {"max_units": 3},
        "sizing": {"mode": "risk_unit", "risk_fraction": 0.01, "notional_cap": 0.25},
        "constraints": {"max_positions": 4},
    })
    data = load_simulation_data(dataset_writer(universe, bars))
    result = run_simulation(spec, data, signal_provider=make_formula_provider(normalized))
    trailing = [e for d in result.days for e in d.events if e.get("kind") == "stop_updated"]
    assert trailing, "climb must ratchet the ATR trailing stop"
    buys = [f for f in result.fills if f.side == "BUY"]
    assert len(buys) >= 2, "climb must trigger at least one add"
    sells = [f for f in result.fills if f.side == "SELL"]
    assert sells, "slide must close the position"
