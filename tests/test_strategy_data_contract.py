"""Fixture generation determinism and dataset-loader fail-closed validation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.strategy.data import StrategyDataError, load_simulation_data
from tests.strategy_fixtures import dataset_writer, flat_bar

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_strategy_universe_fixtures.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("strategy_universe_builder", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_generation_is_deterministic_byte_for_byte():
    builder = _load_builder()
    first = builder._build_rows()
    second = builder._build_rows()
    assert first == second
    columns = ("date", "instrument", "open", "high", "low", "close")
    assert builder._csv_bytes(first[1], columns) == builder._csv_bytes(second[1], columns)


def test_loader_rejects_real_instruments_duplicate_dates_and_bad_ohlc(dataset_writer):
    days = [f"2025-01-{number:02d}" for number in range(2, 10)]
    base_universe = [{"instrument": "600000.SH", "display_name": "真实代码", "list_date": days[0],
                      "delist_date": ""}]
    with pytest.raises(StrategyDataError, match="non-synthetic"):
        load_simulation_data(dataset_writer(base_universe, [flat_bar(days[0], "600000.SH", 10.0)]))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0],
                 "delist_date": ""}]
    duplicate = [flat_bar(days[0], "SYN_POOL_B01", 10.0), flat_bar(days[0], "SYN_POOL_B01", 11.0)]
    with pytest.raises(StrategyDataError, match="duplicate price dates"):
        load_simulation_data(dataset_writer(universe, duplicate))
    inverted = [{"date": days[0], "instrument": "SYN_POOL_B01", "open": 10.0, "high": 9.0,
                 "low": 11.0, "close": 10.0}]
    with pytest.raises(StrategyDataError, match="inconsistent OHLC"):
        load_simulation_data(dataset_writer(universe, inverted))
    bars_before_listing = [flat_bar("2024-12-30", "SYN_POOL_B01", 10.0), flat_bar(days[0], "SYN_POOL_B01", 10.0)]
    with pytest.raises(StrategyDataError, match="before its list_date"):
        load_simulation_data(dataset_writer(universe, bars_before_listing))
    bars_after_delist = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe_delisted = [{**universe[0], "delist_date": days[4]}]
    with pytest.raises(StrategyDataError, match="after its delist_date"):
        load_simulation_data(dataset_writer(universe_delisted, bars_after_delist))


def test_engine_refuses_parameters_missing_required_keys(dataset_writer):
    days = [f"2025-01-{number:02d}" for number in range(2, 10)]
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01", "list_date": days[0],
                 "delist_date": ""}]
    directory = dataset_writer(universe, bars)
    data = load_simulation_data(directory)
    from src.strategy.spec import StrategySpec
    from src.strategy.engine import run_simulation
    broken = StrategySpec(strategy_id="x", version="1", title="t", description="d",
                          rule_table=(), params={"initial_cash": 100.0})
    with pytest.raises(KeyError):
        run_simulation(broken, data)
