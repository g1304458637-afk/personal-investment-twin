from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.attribution import selection_evidence as selection_module
from src.attribution.exit_timing_evidence import (
    COUNTERFACTUAL_NOTICE,
    POLICY_SESSIONS,
    PRIMARY_EXIT_POLICY,
    build_exit_timing_evidence,
)
from src.data.local_market_data_provider import LocalMarketDataProvider
from src.episodes.investment_episode import InvestmentEpisode


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXIT_PRICE_FIXTURE = (
    PROJECT_ROOT / "data" / "sample" / "synthetic_exit_timing_prices.csv"
)
REFERENCE_ROOT = PROJECT_ROOT / "data" / "reference"


def _episode(symbol: str) -> InvestmentEpisode:
    return InvestmentEpisode(
        episode_id=f"investment-episode:{symbol}:0",
        symbol=symbol,
        size=100.0,
        entry_time=pd.Timestamp("2025-01-06 09:35:00"),
        avg_entry_price=90.0,
        entry_fees=5.0,
        exit_time=pd.Timestamp("2025-06-02 10:05:00"),
        avg_exit_price=99.5,
        exit_fees=5.0,
        valuation_time=None,
        valuation_price=None,
        pnl=940.0,
        return_value=0.1044,
        direction="Long",
        status="Closed",
        position_id=0,
    )


@pytest.fixture
def provider(tmp_path: Path) -> LocalMarketDataProvider:
    root = tmp_path / "reference"
    root.mkdir()
    pd.read_csv(EXIT_PRICE_FIXTURE).to_csv(root / "prices.csv", index=False)
    pd.read_csv(REFERENCE_ROOT / "industry_membership.csv").to_csv(
        root / "industry_membership.csv",
        index=False,
    )
    pd.read_csv(REFERENCE_ROOT / "benchmark_mapping.csv").to_csv(
        root / "benchmark_mapping.csv",
        index=False,
    )
    return LocalMarketDataProvider(root)


@pytest.mark.parametrize(
    ("symbol", "expected_return", "expected_price", "expected_comparison"),
    [
        pytest.param(
            "SYN_EXIT_UP",
            0.20,
            120.0,
            "actual_exit_underperformed_hold_baseline",
            id="up",
        ),
        pytest.param(
            "SYN_EXIT_DOWN",
            -0.20,
            80.0,
            "actual_exit_outperformed_hold_baseline",
            id="down",
        ),
        pytest.param(
            "SYN_EXIT_FLAT",
            0.0,
            100.0,
            "matched_hold_baseline",
            id="flat",
        ),
    ],
)
def test_fixed_policy_up_down_and_flat_cases(
    provider,
    symbol,
    expected_return,
    expected_price,
    expected_comparison,
):
    evidence = build_exit_timing_evidence(_episode(symbol), provider)

    assert evidence.episode_id == f"investment-episode:{symbol}:0"
    assert evidence.symbol == symbol
    assert evidence.actual_exit_time == pd.Timestamp("2025-06-02 10:05:00")
    assert evidence.actual_exit_price == pytest.approx(99.5)
    assert evidence.exit_session_market_price == pytest.approx(100.0)
    assert evidence.counterfactual_exit_time == pd.Timestamp("2025-06-30")
    assert evidence.counterfactual_exit_price == pytest.approx(expected_price)
    assert evidence.post_exit_asset_return == pytest.approx(expected_return)
    assert evidence.comparison == expected_comparison
    assert evidence.evidence_status == "complete"
    assert evidence.evidence_reason is None


def test_policy_counts_market_sessions_not_calendar_days(provider):
    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.policy_id == "hold_20_sessions_v1"
    assert evidence.policy_id == PRIMARY_EXIT_POLICY
    assert evidence.policy_sessions == 20
    assert evidence.policy_sessions == POLICY_SESSIONS
    assert evidence.counterfactual_exit_time == pd.Timestamp("2025-06-30")
    assert (
        evidence.counterfactual_exit_time
        - evidence.actual_exit_time.normalize()
    ).days == 28
    assert evidence.counterfactual_notice == COUNTERFACTUAL_NOTICE
    assert "retrospective fixed-horizon counterfactual" in evidence.counterfactual_notice
    assert "knowable" in evidence.counterfactual_notice


def test_fixed_policy_does_not_select_future_best_price(provider):
    flat_prices = provider.get_prices(
        ["SYN_EXIT_FLAT"],
        "2025-06-02",
        "2025-06-30",
    )
    assert flat_prices["close"].max() == pytest.approx(150.0)

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_FLAT"), provider)

    assert evidence.counterfactual_exit_price == pytest.approx(100.0)
    assert evidence.post_exit_asset_return == pytest.approx(0.0)
    assert evidence.comparison == "matched_hold_baseline"


def test_data_after_policy_horizon_does_not_change_evidence(provider):
    source_row = provider.prices[
        provider.prices["instrument"] == "SYN_EXIT_UP"
    ].iloc[[-1]]
    duplicate_after_horizon = pd.concat([source_row, source_row], ignore_index=True)
    duplicate_after_horizon.loc[:, "date"] = pd.Timestamp("2025-07-01")
    provider.prices = pd.concat(
        [provider.prices, duplicate_after_horizon],
        ignore_index=True,
    )

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.evidence_status == "complete"
    assert evidence.counterfactual_exit_time == pd.Timestamp("2025-06-30")
    assert evidence.counterfactual_exit_price == pytest.approx(120.0)


def test_return_uses_empyrical_market_series_not_actual_avg_exit_price(provider):
    simple_returns = selection_module.empyrical.simple_returns
    cumulative_return = selection_module.empyrical.cum_returns_final
    with patch.object(
        selection_module.empyrical,
        "simple_returns",
        wraps=simple_returns,
    ) as simple_mock, patch.object(
        selection_module.empyrical,
        "cum_returns_final",
        wraps=cumulative_return,
    ) as cumulative_mock:
        evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    simple_mock.assert_called_once()
    cumulative_mock.assert_called_once()
    market_series = simple_mock.call_args.args[0]
    assert len(market_series) == 21
    assert market_series.iloc[0] == pytest.approx(100.0)
    assert market_series.iloc[-1] == pytest.approx(120.0)
    assert evidence.actual_exit_price == pytest.approx(99.5)
    assert evidence.post_exit_asset_return == pytest.approx(0.20)


def test_synthetic_price_provenance_is_preserved(provider):
    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    provenance = evidence.provenance
    assert provenance is not None
    assert provenance.instrument == "SYN_EXIT_UP"
    assert provenance.data_source == "local_exit_fixture"
    assert provenance.data_version == "v1"
    assert provenance.as_of == pd.Timestamp("2025-06-30")
    assert provenance.price_type == "synthetic"
    assert provenance.is_synthetic is True


def test_open_episode_is_insufficient_without_querying_market_data(provider):
    closed = _episode("SYN_EXIT_UP")
    episode = replace(
        closed,
        status="Open",
        exit_time=None,
        avg_exit_price=None,
        exit_fees=None,
        valuation_time=closed.exit_time,
        valuation_price=closed.avg_exit_price,
    )

    with patch.object(provider, "get_prices", wraps=provider.get_prices) as get_prices:
        evidence = build_exit_timing_evidence(episode, provider)

    get_prices.assert_not_called()
    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.comparison is None
    assert evidence.post_exit_asset_return is None
    assert "no completed final exit" in evidence.evidence_reason


def test_closed_episode_without_exit_time_is_insufficient(provider):
    episode = replace(_episode("SYN_EXIT_UP"), exit_time=None)

    evidence = build_exit_timing_evidence(episode, provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.actual_exit_time is None
    assert evidence.counterfactual_exit_time is None
    assert "exit_time" in evidence.evidence_reason


def test_non_long_episode_is_insufficient(provider):
    episode = replace(_episode("SYN_EXIT_UP"), direction="Short")

    evidence = build_exit_timing_evidence(episode, provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.comparison is None
    assert "Long Episodes only" in evidence.evidence_reason


def test_missing_actual_exit_session_price_is_insufficient(provider):
    provider.prices = provider.prices[
        ~(
            (provider.prices["instrument"] == "SYN_EXIT_UP")
            & (provider.prices["date"] == pd.Timestamp("2025-06-02"))
        )
    ].copy()

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.counterfactual_exit_time is None
    assert "no unique actual exit session" in evidence.evidence_reason


def test_fewer_than_twenty_post_exit_sessions_is_insufficient(provider):
    symbol_rows = provider.prices["instrument"] == "SYN_EXIT_UP"
    last_two_dates = pd.to_datetime(["2025-06-27", "2025-06-30"])
    provider.prices = provider.prices[
        ~(symbol_rows & provider.prices["date"].isin(last_two_dates))
    ].copy()

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.counterfactual_exit_time is None
    assert evidence.post_exit_asset_return is None
    assert "fewer than 20 subsequent sessions" in evidence.evidence_reason


@pytest.mark.parametrize(
    ("invalid_case", "expected_reason"),
    [
        pytest.param("unknown_type", "unsupported price_type", id="unknown-type"),
        pytest.param("mixed_type", "inconsistent price_type", id="mixed-type"),
        pytest.param(
            "invalid_synthetic",
            "invalid is_synthetic",
            id="invalid-synthetic",
        ),
    ],
)
def test_invalid_post_exit_provenance_is_insufficient(
    provider,
    invalid_case,
    expected_reason,
):
    rows = provider.prices["instrument"] == "SYN_EXIT_UP"
    if invalid_case == "unknown_type":
        provider.prices.loc[rows, "price_type"] = "raw_close"
    elif invalid_case == "mixed_type":
        row_index = provider.prices.index[rows][-1]
        provider.prices.loc[row_index, "price_type"] = "adjusted_close"
    else:
        provider.prices["is_synthetic"] = provider.prices["is_synthetic"].astype(
            object
        )
        provider.prices.loc[rows, "is_synthetic"] = "not-a-boolean"

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.post_exit_asset_return is None
    assert evidence.comparison is None
    assert expected_reason in evidence.evidence_reason


@pytest.mark.parametrize("invalid_price", [np.nan, 0.0, -1.0, np.inf])
def test_invalid_post_exit_price_is_insufficient(provider, invalid_price):
    provider.prices["close"] = provider.prices["close"].astype(float)
    row_index = provider.prices.index[
        (provider.prices["instrument"] == "SYN_EXIT_UP")
        & (provider.prices["date"] == pd.Timestamp("2025-06-10"))
    ][0]
    provider.prices.loc[row_index, "close"] = invalid_price

    evidence = build_exit_timing_evidence(_episode("SYN_EXIT_UP"), provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert evidence.post_exit_asset_return is None
    assert evidence.comparison is None
