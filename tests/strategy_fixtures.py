"""Shared helpers for strategy simulation tests: tiny crafted datasets."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from src.strategy.report import result_to_dict
from src.strategy.strategies.t1 import T1_PARAMS, build_t1_spec


def day(text: str) -> date:
    return date.fromisoformat(text)


def write_dataset(root: Path, universe_rows: list[dict[str, object]],
                  price_rows: list[dict[str, object]],
                  action_rows: list[dict[str, object]] | None = None) -> Path:
    directory = root / "strategy_universe"
    directory.mkdir(parents=True, exist_ok=True)

    def csv(rows: list[dict[str, object]], columns: list[str]) -> str:
        head = ",".join(columns)
        lines = [head]
        for row in rows:
            lines.append(",".join("" if row.get(column) is None else str(row.get(column))
                                  for column in columns))
        return "\n".join(lines) + "\n"

    (directory / "universe.csv").write_text(csv(universe_rows, ["instrument", "display_name", "list_date", "delist_date"]), encoding="utf-8")
    (directory / "prices.csv").write_text(csv(price_rows, ["date", "instrument", "open", "high", "low", "close"]), encoding="utf-8")
    if action_rows is not None:
        (directory / "corporate_actions.csv").write_text(
            csv(action_rows, ["instrument", "ex_date", "action", "ratio"]), encoding="utf-8")
    return directory


def flat_bar(day_text: str, instrument: str, close: float) -> dict[str, object]:
    return {"date": day_text, "instrument": instrument, "open": close, "high": close,
            "low": close, "close": close}


def bar(day_text: str, instrument: str, open_: float, high: float, low: float, close: float) -> dict[str, object]:
    return {"date": day_text, "instrument": instrument, "open": open_, "high": high,
            "low": low, "close": close}


def run_params(**overrides) -> dict[str, float | int | str]:
    params = dict(T1_PARAMS)
    params.update(overrides)
    return params


def run_spec(params: dict[str, float | int | str] | None = None):
    spec = build_t1_spec()
    if params is not None:
        merged = dict(spec.params)
        merged.update(params)
        from src.strategy.spec import StrategySpec
        spec = StrategySpec(strategy_id=spec.strategy_id, version=spec.version, title=spec.title,
                            description=spec.description, rule_table=spec.rule_table, params=merged)
    return spec


def run(dataset_dir: Path, params: dict[str, float | int | str] | None = None):
    data = load_simulation_data(dataset_dir)
    result = run_simulation(run_spec(params), data)
    return data, result, result_to_dict(result)


@pytest.fixture()
def dataset_writer(tmp_path: Path):
    """Return a callable that writes crafted CSVs and returns the dataset dir."""
    def _write(universe_rows, price_rows, action_rows=None) -> Path:
        return write_dataset(tmp_path, universe_rows, price_rows, action_rows)
    return _write
