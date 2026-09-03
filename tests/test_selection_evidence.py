from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.attribution import selection_evidence as selection_module
from src.attribution.selection_evidence import build_selection_evidence
from src.core.vectorbt_validation import replay_single_symbol_executions
from src.data.csv_importer import load_normalized_csv
from src.data.local_market_data_provider import LocalMarketDataProvider
from src.episodes.investment_episode import (
    InvestmentEpisode,
    from_vectorbt_position_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "synthetic_executions.csv"
REFERENCE_ROOT = PROJECT_ROOT / "data" / "reference"
INITIAL_CASH = 100_000.0


@pytest.fixture(scope="module")
def normalized_executions() -> pd.DataFrame:
    return load_normalized_csv(SAMPLE_CSV)


def _episode(executions: pd.DataFrame) -> InvestmentEpisode:
    symbol = executions["symbol"].iat[0]
    valuation_prices = executions.set_index("event_time")["executed_price"].rename(symbol)
    portfolio = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )
    record = portfolio.positions.records_readable.iloc[0]
    if record["Status"] == "Open":
        return from_vectorbt_position_record(
            record,
            valuation_time=portfolio.close.index[-1],
            valuation_price=portfolio.close[symbol].iloc[-1],
        )
    return from_vectorbt_position_record(record)


@pytest.fixture(scope="module")
def closed_episode(normalized_executions: pd.DataFrame) -> InvestmentEpisode:
    return _episode(normalized_executions)


@pytest.fixture(scope="module")
def provider() -> LocalMarketDataProvider:
    return LocalMarketDataProvider(REFERENCE_ROOT)


def _temporary_provider(
    tmp_path: Path,
    *,
    prices: pd.DataFrame | None = None,
    benchmark_mapping: pd.DataFrame | None = None,
    industry_membership: pd.DataFrame | None = None,
) -> LocalMarketDataProvider:
    root = tmp_path / "reference"
    root.mkdir()
    if prices is None:
        prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    if benchmark_mapping is None:
        benchmark_mapping = pd.read_csv(REFERENCE_ROOT / "benchmark_mapping.csv")
    if industry_membership is None:
        industry_membership = pd.read_csv(REFERENCE_ROOT / "industry_membership.csv")

    prices.to_csv(root / "prices.csv", index=False)
    benchmark_mapping.to_csv(root / "benchmark_mapping.csv", index=False)
    industry_membership.to_csv(
        root / "industry_membership.csv",
        index=False,
    )
    return LocalMarketDataProvider(root)


def _assert_no_calculated_evidence(evidence) -> None:
    assert evidence.asset_return is None
    assert evidence.market_benchmark_return is None
    assert evidence.industry_benchmark_return is None
    assert evidence.market_comparison is None
    assert evidence.industry_comparison is None


def test_closed_episode_builds_complete_selection_evidence(
    closed_episode: InvestmentEpisode,
    provider: LocalMarketDataProvider,
):
    evidence = build_selection_evidence(closed_episode, provider)

    assert evidence.episode_id == closed_episode.episode_id
    assert evidence.symbol == "600000.SH"
    assert evidence.start_time == pd.Timestamp("2025-01-06 09:35:00")
    assert evidence.end_time == pd.Timestamp("2025-05-20 10:05:00")
    assert evidence.asset_return == pytest.approx(0.30)
    assert evidence.market_benchmark_id == "CSI300"
    assert evidence.market_benchmark_name == "沪深300"
    assert evidence.market_benchmark_return == pytest.approx(0.08)
    assert evidence.market_comparison == "outperformed"
    assert evidence.industry_id == "SW_BANK"
    assert evidence.industry_name == "银行"
    assert evidence.industry_as_of_date == closed_episode.entry_time
    assert evidence.industry_benchmark_id == "SW_BANK"
    assert evidence.industry_benchmark_name == "银行行业基准"
    assert evidence.industry_benchmark_return == pytest.approx(0.25)
    assert evidence.industry_comparison == "outperformed"
    assert evidence.evidence_status == "complete"
    assert evidence.evidence_reason is None


def test_benchmark_provenance_is_preserved(
    closed_episode: InvestmentEpisode,
    provider: LocalMarketDataProvider,
):
    evidence = build_selection_evidence(closed_episode, provider)
    provenance = {item.benchmark_id: item for item in evidence.benchmark_provenance}

    asset = evidence.asset_provenance
    assert asset is not None
    assert asset.instrument == "600000.SH"
    assert asset.data_source == "local_fixture"
    assert asset.data_version == "v1"
    assert asset.as_of == pd.Timestamp("2025-05-20")
    assert asset.price_type == "synthetic"
    assert asset.is_synthetic is True

    assert set(provenance) == {"CSI300", "SW_BANK"}
    assert provenance["CSI300"].benchmark_name == "沪深300"
    assert provenance["CSI300"].benchmark_type == "market"
    assert provenance["SW_BANK"].benchmark_name == "银行行业基准"
    assert provenance["SW_BANK"].benchmark_type == "industry"
    for item in provenance.values():
        assert item.data_source == "local_fixture"
        assert item.data_version == "v1"
        assert item.as_of == pd.Timestamp("2025-05-20")
        assert item.price_type == "synthetic"
        assert item.is_synthetic is True

    industry = evidence.industry_provenance
    assert industry is not None
    assert industry.industry_id == "SW_BANK"
    assert industry.industry_name == "银行"
    assert industry.as_of == closed_episode.entry_time
    assert industry.classification == "synthetic_industry"
    assert industry.data_source == "local_fixture"
    assert industry.data_version == "v1"
    assert industry.is_synthetic is True


def test_open_episode_is_partial_and_uses_valuation_time(
    normalized_executions: pd.DataFrame,
    provider: LocalMarketDataProvider,
):
    episode = _episode(normalized_executions.iloc[:2].copy())
    assert episode.status == "Open"
    assert episode.exit_time is None

    evidence = build_selection_evidence(episode, provider)

    assert evidence.evidence_status == "partial"
    assert evidence.end_time == episode.valuation_time
    assert evidence.end_time == pd.Timestamp("2025-02-10 10:12:00")
    assert evidence.asset_return == pytest.approx(0.10)


def test_missing_benchmark_mapping_returns_insufficient_evidence(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    mappings = pd.read_csv(REFERENCE_ROOT / "benchmark_mapping.csv")
    mappings = mappings[mappings["benchmark_id"] != "SW_BANK"]
    missing_mapping_provider = _temporary_provider(
        tmp_path,
        benchmark_mapping=mappings,
    )

    evidence = build_selection_evidence(closed_episode, missing_mapping_provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert "Industry benchmark mapping unavailable" in evidence.evidence_reason
    _assert_no_calculated_evidence(evidence)


def test_missing_benchmark_endpoint_returns_insufficient_evidence(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    prices = prices[
        ~(
            (prices["instrument"] == "CSI300")
            & (prices["date"] == "2025-05-20")
        )
    ]
    missing_endpoint_provider = _temporary_provider(tmp_path, prices=prices)

    evidence = build_selection_evidence(closed_episode, missing_endpoint_provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert "CSI300" in evidence.evidence_reason
    assert "end date" in evidence.evidence_reason
    _assert_no_calculated_evidence(evidence)


@pytest.mark.parametrize(
    ("invalid_case", "expected_reason"),
    [
        pytest.param("unknown_price_type", "unsupported price_type", id="unknown-type"),
        pytest.param("mixed_price_type", "inconsistent price_type", id="mixed-types"),
        pytest.param("mixed_data_version", "inconsistent data_version", id="mixed-versions"),
        pytest.param(
            "invalid_is_synthetic",
            "invalid is_synthetic",
            id="invalid-synthetic-flag",
        ),
    ],
)
def test_invalid_asset_price_provenance_returns_insufficient_evidence(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
    invalid_case: str,
    expected_reason: str,
):
    prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    asset_rows = prices["instrument"] == "600000.SH"
    asset_indices = prices.index[asset_rows]

    if invalid_case == "unknown_price_type":
        prices.loc[asset_rows, "price_type"] = "unknown"
    elif invalid_case == "mixed_price_type":
        prices.loc[asset_indices[-1], "price_type"] = "adjusted_close"
    elif invalid_case == "mixed_data_version":
        prices.loc[asset_indices[-1], "data_version"] = "v2"
    else:
        prices["is_synthetic"] = prices["is_synthetic"].astype(object)
        prices.loc[asset_rows, "is_synthetic"] = "not-a-boolean"

    invalid_provider = _temporary_provider(tmp_path, prices=prices)
    evidence = build_selection_evidence(closed_episode, invalid_provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert "600000.SH" in evidence.evidence_reason
    assert expected_reason in evidence.evidence_reason
    assert evidence.asset_provenance is None
    _assert_no_calculated_evidence(evidence)


def test_invalid_benchmark_price_type_returns_insufficient_evidence(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    prices.loc[prices["instrument"] == "CSI300", "price_type"] = "raw_close"
    invalid_provider = _temporary_provider(tmp_path, prices=prices)

    evidence = build_selection_evidence(closed_episode, invalid_provider)

    assert evidence.evidence_status == "insufficient_evidence"
    assert "CSI300" in evidence.evidence_reason
    assert "unsupported price_type" in evidence.evidence_reason
    _assert_no_calculated_evidence(evidence)


def test_identical_asset_and_benchmark_paths_are_matched(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    market_path = (
        prices[prices["instrument"] == "CSI300"]
        .set_index("date")["close"]
        .to_dict()
    )
    same_path = prices["instrument"].isin(["600000.SH", "SW_BANK"])
    prices.loc[same_path, "close"] = prices.loc[same_path, "date"].map(market_path)
    matched_provider = _temporary_provider(tmp_path, prices=prices)

    evidence = build_selection_evidence(closed_episode, matched_provider)

    assert evidence.evidence_status == "complete"
    assert evidence.market_comparison == "matched"
    assert evidence.industry_comparison == "matched"


def test_point_in_time_industry_uses_episode_entry_membership(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    memberships = pd.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "industry_id": "SW_BANK",
                "industry_name": "银行",
                "valid_from": "2020-01-01",
                "valid_to": "2025-01-31",
                "classification": "synthetic_industry",
                "data_source": "local_fixture",
                "data_version": "v1",
                "is_synthetic": True,
            },
            {
                "symbol": "600000.SH",
                "industry_id": "SW_FUTURE",
                "industry_name": "未来行业",
                "valid_from": "2025-02-01",
                "valid_to": None,
                "classification": "synthetic_industry",
                "data_source": "local_fixture",
                "data_version": "v1",
                "is_synthetic": True,
            },
        ]
    )
    point_in_time_provider = _temporary_provider(
        tmp_path,
        industry_membership=memberships,
    )

    evidence = build_selection_evidence(closed_episode, point_in_time_provider)

    assert evidence.evidence_status == "complete"
    assert evidence.industry_id == "SW_BANK"
    assert evidence.industry_as_of_date == closed_episode.entry_time
    assert evidence.industry_provenance is not None
    assert evidence.industry_provenance.as_of == closed_episode.entry_time


def test_nearly_equal_returns_are_matched_with_float_tolerance(
    tmp_path: Path,
    closed_episode: InvestmentEpisode,
):
    prices = pd.read_csv(REFERENCE_ROOT / "prices.csv")
    market_path = (
        prices[prices["instrument"] == "CSI300"]
        .set_index("date")["close"]
        .to_dict()
    )
    asset_rows = prices["instrument"] == "600000.SH"
    prices.loc[asset_rows, "close"] = prices.loc[asset_rows, "date"].map(market_path)
    last_asset_row = prices.index[asset_rows][-1]
    prices.loc[last_asset_row, "close"] = 108.000000001
    nearly_matched_provider = _temporary_provider(tmp_path, prices=prices)

    evidence = build_selection_evidence(closed_episode, nearly_matched_provider)

    assert evidence.evidence_status == "complete"
    assert evidence.asset_return != evidence.market_benchmark_return
    assert evidence.market_comparison == "matched"


def test_returns_are_computed_through_empyrical(
    closed_episode: InvestmentEpisode,
    provider: LocalMarketDataProvider,
):
    with (
        patch.object(
            selection_module.empyrical,
            "simple_returns",
            wraps=selection_module.empyrical.simple_returns,
        ) as simple_returns,
        patch.object(
            selection_module.empyrical,
            "cum_returns_final",
            wraps=selection_module.empyrical.cum_returns_final,
        ) as cum_returns_final,
    ):
        evidence = build_selection_evidence(closed_episode, provider)

    assert evidence.evidence_status == "complete"
    assert simple_returns.call_count == 3
    assert cum_returns_final.call_count == 3
