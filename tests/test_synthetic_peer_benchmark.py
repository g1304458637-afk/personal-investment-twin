from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src.behavior.portfolio_concentration import (
    build_portfolio_concentration_evidence,
)
from src.behavior.replay_state import prepare_behavior_replay
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.cohort.engine import (
    PERCENTILE_METHOD,
    QUANTILE_METHOD,
    build_peer_benchmark_results,
)
from src.cohort.models import CohortMember
from src.cohort.synthetic import (
    SYNTHETIC_PEER_COUNT,
    SyntheticCohortAccount,
    build_account_peer_metric_values,
    build_synthetic_peer_metric_values,
    generate_synthetic_cohort_accounts,
    synthetic_cohort_definition,
)
from src.data.csv_importer import load_normalized_csv
from src.episodes.investment_episode import from_vectorbt_position_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALCULATION_VERSION = "synthetic-peer-test-v1"
SUBJECT_ID = "demo-user:synthetic-behavior"


@pytest.fixture(scope="module")
def market_prices() -> pd.DataFrame:
    return pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )


@pytest.fixture(scope="module")
def accounts(market_prices: pd.DataFrame):
    return generate_synthetic_cohort_accounts(market_prices)


@pytest.fixture(scope="module")
def peer_values(accounts):
    return build_synthetic_peer_metric_values(
        accounts,
        calculation_code_version=CALCULATION_VERSION,
    )


@pytest.fixture(scope="module")
def subject_account(market_prices: pd.DataFrame) -> SyntheticCohortAccount:
    definition = synthetic_cohort_definition()
    member = CohortMember(
        subject_id=SUBJECT_ID,
        market=definition.market,
        asset_types=definition.asset_types,
        direction=definition.direction,
        observation_start=definition.observation_start,
        observation_end=definition.observation_end,
        leverage=False,
        data_tier="synthetic",
        data_quality_status="complete",
    )
    return SyntheticCohortAccount(
        member=member,
        executions=load_normalized_csv(
            PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
        ),
        market_prices=market_prices,
        init_cash=100_000.0,
    )


@pytest.fixture(scope="module")
def subject_values(subject_account):
    return build_account_peer_metric_values(
        subject_account,
        calculation_code_version=CALCULATION_VERSION,
    )


def _by_metric(values):
    return {item.metric_id: item for item in values}


def test_synthetic_generator_is_deterministic_and_has_72_unique_peers(
    market_prices: pd.DataFrame,
    accounts,
) -> None:
    repeated = generate_synthetic_cohort_accounts(market_prices)

    assert len(accounts) == SYNTHETIC_PEER_COUNT == 72
    assert [item.member.subject_id for item in accounts] == [
        item.member.subject_id for item in repeated
    ]
    assert len({item.member.subject_id for item in accounts}) == 72
    for first, second in zip(accounts, repeated, strict=True):
        pd.testing.assert_frame_equal(first.executions, second.executions)
        pd.testing.assert_frame_equal(first.market_prices, second.market_prices)


def test_generator_uses_one_exact_window_and_synthetic_tier(accounts) -> None:
    definition = synthetic_cohort_definition()

    assert all(item.member.observation_start == definition.observation_start for item in accounts)
    assert all(item.member.observation_end == definition.observation_end for item in accounts)
    assert all(item.member.data_tier == "synthetic" for item in accounts)
    assert all(item.member.market == definition.market for item in accounts)
    assert all(item.member.leverage is False for item in accounts)


def test_one_account_casts_one_vote_even_when_execution_counts_differ(
    accounts,
    peer_values,
) -> None:
    execution_counts = {item.member.subject_id: len(item.executions) for item in accounts}
    assert set(execution_counts.values()) == {3, 5, 7}

    votes = Counter((item.metric_id, item.subject_id) for item in peer_values)
    assert len(peer_values) == 72 * 3
    assert set(votes.values()) == {1}
    assert Counter(item.metric_id for item in peer_values) == {
        "portfolio_concentration_hhi": 72,
        "mean_daily_turnover": 72,
        "closed_episode_count": 72,
    }


def test_peer_hhi_is_copied_from_existing_hhi_builder(accounts, peer_values) -> None:
    account = accounts[17]
    expected = build_portfolio_concentration_evidence(
        account.executions,
        account.market_prices,
        init_cash=account.init_cash,
    )
    actual = next(
        item
        for item in peer_values
        if item.subject_id == account.member.subject_id
        and item.metric_id == "portfolio_concentration_hhi"
    )

    assert expected.evidence_status == "complete"
    assert actual.value == expected.hhi
    assert actual.source_evidence_id.startswith("ev_")


def test_peer_turnover_is_copied_from_existing_turnover_builder(
    accounts,
    peer_values,
) -> None:
    account = accounts[41]
    expected = build_turnover_intensity_evidence(
        account.executions,
        account.market_prices,
        init_cash=account.init_cash,
    )
    actual = next(
        item
        for item in peer_values
        if item.subject_id == account.member.subject_id
        and item.metric_id == "mean_daily_turnover"
    )

    assert expected.evidence_status == "complete"
    assert actual.value == expected.mean_daily_turnover
    assert actual.source_evidence_id.startswith("ev_")


def test_closed_episode_count_comes_from_vectorbt_positions_and_episode_mapper(
    accounts,
    peer_values,
) -> None:
    account = accounts[2]
    context = prepare_behavior_replay(
        account.executions,
        account.market_prices,
        init_cash=account.init_cash,
    )
    episodes = tuple(
        from_vectorbt_position_record(record)
        for _, record in context.portfolio.positions.records_readable.iterrows()
    )
    expected = sum(
        episode.status == "Closed"
        and episode.exit_time is not None
        and account.member.observation_start <= episode.exit_time.normalize()
        and episode.exit_time.normalize() <= account.member.observation_end
        for episode in episodes
    )
    actual = next(
        item
        for item in peer_values
        if item.subject_id == account.member.subject_id
        and item.metric_id == "closed_episode_count"
    )

    assert expected == 2
    assert actual.value == float(expected)
    assert actual.source_evidence_id.startswith("episode_set:")


def test_future_execution_and_price_do_not_change_window_metrics(accounts) -> None:
    account = accounts[11]
    original = build_account_peer_metric_values(
        account,
        calculation_code_version=CALCULATION_VERSION,
    )
    future_execution = account.executions.iloc[[0]].copy()
    future_execution.loc[:, "event_time"] = pd.Timestamp("2025-01-09")
    future_execution.loc[:, "order_id"] = "future-order"
    future_execution.loc[:, "execution_id"] = "future-execution"
    future_prices = account.market_prices.loc[
        pd.to_datetime(account.market_prices["date"]) == pd.Timestamp("2025-01-08")
    ].copy()
    future_prices.loc[:, "date"] = "2025-01-09"
    future_prices.loc[:, "close"] = future_prices["close"] * 100
    extended = replace(
        account,
        executions=pd.concat([account.executions, future_execution], ignore_index=True),
        market_prices=pd.concat([account.market_prices, future_prices], ignore_index=True),
    )

    assert build_account_peer_metric_values(
        extended,
        calculation_code_version=CALCULATION_VERSION,
    ) == original


def test_observation_end_includes_intraday_executions(accounts) -> None:
    account = accounts[0]
    end_date_execution = account.executions.iloc[[0]].copy()
    end_date_execution.loc[:, "event_time"] = pd.Timestamp("2025-01-08 10:00:00")
    end_date_execution.loc[:, "symbol"] = "SYN_NEUTRAL"
    end_date_execution.loc[:, "side"] = "SELL"
    end_date_execution.loc[:, "executed_quantity"] = 160.0
    end_date_execution.loc[:, "executed_price"] = 5.0
    end_date_execution.loc[:, "order_id"] = "end-date-order"
    end_date_execution.loc[:, "execution_id"] = "end-date-execution"
    extended = replace(
        account,
        executions=pd.concat(
            [account.executions, end_date_execution], ignore_index=True
        ),
    )
    original = _by_metric(
        build_account_peer_metric_values(
            account,
            calculation_code_version=CALCULATION_VERSION,
        )
    )
    result = _by_metric(
        build_account_peer_metric_values(
            extended,
            calculation_code_version=CALCULATION_VERSION,
        )
    )

    assert result["portfolio_concentration_hhi"].evidence_status == "complete"
    assert result["mean_daily_turnover"].evidence_status == "complete"
    assert result["portfolio_concentration_hhi"].value != original[
        "portfolio_concentration_hhi"
    ].value
    assert result["mean_daily_turnover"].value != original["mean_daily_turnover"].value
    assert original["closed_episode_count"].value == 0.0
    assert result["closed_episode_count"].value == 1.0


def test_missing_market_price_remains_insufficient_instead_of_being_filled(
    accounts,
) -> None:
    account = accounts[0]
    prices = account.market_prices.copy()
    missing = (
        (prices["instrument"] == "SYN_PAPER_WIN")
        & (pd.to_datetime(prices["date"]) == pd.Timestamp("2025-01-06"))
    )
    incomplete = replace(account, market_prices=prices.loc[~missing].copy())
    values = build_account_peer_metric_values(
        incomplete,
        calculation_code_version=CALCULATION_VERSION,
    )

    assert all(item.evidence_status == "insufficient_evidence" for item in values)
    assert all(item.value is None for item in values)


def test_whole_missing_market_date_cannot_shorten_the_comparable_window(
    accounts,
) -> None:
    account = accounts[0]
    incomplete = replace(
        account,
        market_prices=account.market_prices.loc[
            pd.to_datetime(account.market_prices["date"])
            != pd.Timestamp("2025-01-06")
        ].copy(),
    )

    values = build_account_peer_metric_values(
        incomplete,
        calculation_code_version=CALCULATION_VERSION,
    )

    assert all(item.evidence_status == "insufficient_evidence" for item in values)
    assert all(item.value is None for item in values)


def test_account_without_start_of_window_history_is_not_comparable(accounts) -> None:
    account = accounts[0]
    late = replace(
        account,
        executions=account.executions.assign(event_time=pd.Timestamp("2025-01-06")),
    )

    values = build_account_peer_metric_values(
        late,
        calculation_code_version=CALCULATION_VERSION,
    )

    assert all(item.evidence_status == "insufficient_evidence" for item in values)
    assert all(item.value is None for item in values)


def test_non_synthetic_price_provenance_is_rejected(accounts) -> None:
    account = accounts[0]
    non_synthetic = replace(
        account,
        market_prices=account.market_prices.assign(is_synthetic=False),
    )

    with pytest.raises(ValueError, match="synthetic provenance"):
        build_account_peer_metric_values(
            non_synthetic,
            calculation_code_version=CALCULATION_VERSION,
        )


def test_subject_metrics_use_the_same_existing_engine_definitions(
    subject_account,
    subject_values,
) -> None:
    actual = _by_metric(subject_values)
    expected_hhi = build_portfolio_concentration_evidence(
        subject_account.executions,
        subject_account.market_prices,
        init_cash=subject_account.init_cash,
    )
    expected_turnover = build_turnover_intensity_evidence(
        subject_account.executions,
        subject_account.market_prices,
        init_cash=subject_account.init_cash,
    )

    assert actual["portfolio_concentration_hhi"].value == expected_hhi.hhi
    assert actual["mean_daily_turnover"].value == expected_turnover.mean_daily_turnover
    assert actual["closed_episode_count"].value == 0.0


def test_real_synthetic_benchmark_excludes_subject_and_is_complete(
    accounts,
    peer_values,
    subject_values,
) -> None:
    definition = synthetic_cohort_definition()
    results = build_peer_benchmark_results(
        definition,
        [item.member for item in accounts],
        peer_values,
        subject_values,
        subject_id=SUBJECT_ID,
    )

    assert SUBJECT_ID not in {item.member.subject_id for item in accounts}
    assert [item.metric_id for item in results] == [
        "portfolio_concentration_hhi",
        "mean_daily_turnover",
        "closed_episode_count",
    ]
    assert all(item.cohort_n == 72 and item.metric_n == 72 for item in results)
    assert all(item.benchmark_status == "complete" for item in results)
    assert all(item.quantile_method == QUANTILE_METHOD for item in results)
    assert all(item.percentile_method == PERCENTILE_METHOD for item in results)
    assert all(item.observation_start == pd.Timestamp("2025-01-02") for item in results)
    assert all(item.observation_end == pd.Timestamp("2025-01-08") for item in results)


def test_generated_benchmark_values_are_stable_regression_facts(
    accounts,
    peer_values,
    subject_values,
) -> None:
    results = _by_metric(
        build_peer_benchmark_results(
            synthetic_cohort_definition(),
            [item.member for item in accounts],
            peer_values,
            subject_values,
            subject_id=SUBJECT_ID,
        )
    )

    assert results["portfolio_concentration_hhi"].subject_value == pytest.approx(
        0.4817677368212446
    )
    assert results["mean_daily_turnover"].subject_value == pytest.approx(
        0.021777318144968673
    )
    assert results["closed_episode_count"].subject_value == 0.0
    assert results["portfolio_concentration_hhi"].median == pytest.approx(
        0.4291886650455402
    )
    assert results["mean_daily_turnover"].median == pytest.approx(
        0.032980579381108655
    )
    assert results["closed_episode_count"].median == 1.0
