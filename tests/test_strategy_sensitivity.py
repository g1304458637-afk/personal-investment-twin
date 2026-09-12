"""Sensitivity runs: sandbox, order preservation, no-ranking, binding info."""
from __future__ import annotations

import pandas as pd
import pytest

from src.strategy.data import load_simulation_data
from src.strategy.sensitivity import SensitivityError, sensitivity_report
from src.strategy.strategies.t1 import build_t1_spec
from tests.strategy_fixtures import dataset_writer, flat_bar


def bdays(start: str, count: int) -> list[str]:
    return [v.date().isoformat() for v in pd.bdate_range(start, periods=count)]


def _spec():
    return build_t1_spec()


def test_rows_keep_caller_order_and_never_rank(dataset_writer):
    days = bdays("2025-01-02", 40)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    report = sensitivity_report(_spec(), data, parameter="position_fraction",
                                values=[0.6, 0.1, 0.25])
    # Flat history never trades, so all rows tie — the point is the ORDER.
    assert [row["value"] for row in report["rows"]] == [0.6, 0.1, 0.25]


def test_sandbox_rejects_disallowed_parameters_and_bad_values(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    with pytest.raises(SensitivityError, match="parameter_not_allowed"):
        sensitivity_report(_spec(), data, parameter="window", values=[10, 20])
    with pytest.raises(SensitivityError, match="2~6"):
        sensitivity_report(_spec(), data, parameter="stop_loss_pct", values=[0.1])
    with pytest.raises(SensitivityError, match="超出允许范围"):
        sensitivity_report(_spec(), data, parameter="position_fraction", values=[0.1, 1.5])


def test_identical_variants_reported_honestly(dataset_writer):
    days = bdays("2025-01-02", 40)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days]
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data = load_simulation_data(dataset_writer(universe, bars))
    # Flat history: no trades at all, so any stop value changes nothing.
    report = sensitivity_report(_spec(), data, parameter="stop_loss_pct", values=[0.05, 0.3])
    assert report["all_variants_identical"] is True
    assert any("未起作用" in item for item in report["limitations"])
