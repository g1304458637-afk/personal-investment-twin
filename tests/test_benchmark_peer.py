"""First direct tests for src/benchmark/peer.py.

The module was only exercised through scripts/export_desktop_demo_evidence.py
(its sole caller); these tests pin the orchestration contract directly.
"""
from pathlib import Path

import pandas as pd
import pytest

from src.benchmark.peer import build_synthetic_peer_benchmark
from src.data.csv_importer import load_normalized_csv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def executions() -> pd.DataFrame:
    return load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv")


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    return pd.read_csv(PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv")


def test_peer_benchmark_shape_and_determinism(executions, prices) -> None:
    first = build_synthetic_peer_benchmark(
        subject_id="demo-user:synthetic-behavior",
        subject_executions=executions,
        market_prices=prices,
        init_cash=100_000.0,
        calculation_code_version="peer-benchmark-test-v1",
    )
    assert first.cohort_n > 0
    assert len(first.metrics) > 0
    assert all(metric.subject_id == "demo-user:synthetic-behavior" for metric in first.metrics)

    # The benchmark is deterministic: identical inputs, identical output.
    second = build_synthetic_peer_benchmark(
        subject_id="demo-user:synthetic-behavior",
        subject_executions=executions,
        market_prices=prices,
        init_cash=100_000.0,
        calculation_code_version="peer-benchmark-test-v1",
    )
    assert second.cohort_n == first.cohort_n
    assert second.metrics == first.metrics


def test_unknown_subject_still_ranks_inside_cohort(executions, prices) -> None:
    result = build_synthetic_peer_benchmark(
        subject_id="demo-user:does-not-exist",
        subject_executions=executions,
        market_prices=prices,
        init_cash=100_000.0,
        calculation_code_version="peer-benchmark-test-v1",
    )
    assert result.metrics
    assert all(metric.subject_id == "demo-user:does-not-exist" for metric in result.metrics)
