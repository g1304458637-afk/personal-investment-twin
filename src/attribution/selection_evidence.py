"""Factual asset-vs-benchmark evidence for one InvestmentEpisode.

This module orchestrates existing episode and local market-data semantics.  It
does not calculate alpha, attribution, contribution, or investor skill.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import empyrical
import pandas as pd

from src.data.local_market_data_provider import LocalMarketDataProvider
from src.episodes.investment_episode import InvestmentEpisode


MARKET_BENCHMARK_ID: Final = "CSI300"
ALLOWED_PRICE_TYPES: Final = frozenset(
    {"adjusted_close", "total_return", "synthetic"}
)

Comparison = Literal["outperformed", "underperformed", "matched"]
EvidenceStatus = Literal["complete", "partial", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class BenchmarkProvenance:
    benchmark_id: str
    benchmark_name: str
    benchmark_type: str
    data_source: str
    data_version: str
    as_of: pd.Timestamp
    price_type: str
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class IndustryProvenance:
    industry_id: str
    industry_name: str
    as_of: pd.Timestamp
    classification: str
    data_source: str
    data_version: str
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class SelectionEvidence:
    """Observed episode-period returns, without a skill or alpha conclusion."""

    episode_id: str
    symbol: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp | None
    asset_return: float | None
    market_benchmark_id: str
    market_benchmark_name: str | None
    market_benchmark_return: float | None
    market_comparison: Comparison | None
    industry_id: str | None
    industry_name: str | None
    industry_as_of_date: pd.Timestamp | None
    industry_benchmark_id: str | None
    industry_benchmark_name: str | None
    industry_benchmark_return: float | None
    industry_comparison: Comparison | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    industry_provenance: IndustryProvenance | None
    benchmark_provenance: tuple[BenchmarkProvenance, ...]


class _EvidenceDataError(ValueError):
    pass


def _required_text(row: pd.Series, field: str, context: str) -> str:
    if field not in row or pd.isna(row[field]):
        raise _EvidenceDataError(f"{context} has no {field}")
    value = str(row[field])
    if not value:
        raise _EvidenceDataError(f"{context} has an empty {field}")
    return value


def _price_window(
    provider: LocalMarketDataProvider,
    instrument: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame]:
    rows = provider.get_prices([instrument], start_date, end_date)
    context = f"Price data for {instrument}"

    if len(rows) < 2:
        raise _EvidenceDataError(f"{context} has fewer than 2 price points")
    if rows["date"].isna().any():
        raise _EvidenceDataError(f"{context} contains a null date")
    if rows["close"].isna().any():
        raise _EvidenceDataError(f"{context} contains a null close")

    rows = rows.sort_values("date", kind="stable").reset_index(drop=True)
    normalized_dates = rows["date"].dt.normalize()
    if normalized_dates.duplicated().any():
        raise _EvidenceDataError(f"{context} contains duplicate calendar dates")
    if normalized_dates.iloc[0] != start_date:
        raise _EvidenceDataError(f"{context} does not cover the episode start date")
    if normalized_dates.iloc[-1] != end_date:
        raise _EvidenceDataError(f"{context} does not cover the episode end date")

    close = rows["close"].astype(float)
    if not close.map(math.isfinite).all():
        raise _EvidenceDataError(f"{context} contains a non-finite close")
    if (close <= 0).any():
        raise _EvidenceDataError(f"{context} contains a non-positive close")

    _validated_price_provenance(rows, context)
    prices = pd.Series(close.to_numpy(), index=rows["date"], name=instrument)
    return prices, rows


def _synthetic_flag(value: object, context: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise _EvidenceDataError(f"{context} has an invalid is_synthetic value")


def _validated_price_provenance(
    price_rows: pd.DataFrame,
    context: str,
) -> dict[str, str | bool]:
    values: dict[str, object] = {}
    for field in ("data_source", "data_version", "price_type", "is_synthetic"):
        if field not in price_rows:
            raise _EvidenceDataError(f"{context} has no {field}")
        if price_rows[field].isna().any():
            raise _EvidenceDataError(f"{context} contains a null {field}")
        unique = price_rows[field].drop_duplicates()
        if len(unique) != 1:
            raise _EvidenceDataError(f"{context} has inconsistent {field}")
        values[field] = unique.iloc[0]

    data_source = str(values["data_source"])
    data_version = str(values["data_version"])
    price_type = str(values["price_type"])
    if not data_source.strip():
        raise _EvidenceDataError(f"{context} has an empty data_source")
    if not data_version.strip():
        raise _EvidenceDataError(f"{context} has an empty data_version")
    if price_type not in ALLOWED_PRICE_TYPES:
        raise _EvidenceDataError(
            f"{context} has unsupported price_type: {price_type}"
        )

    return {
        "data_source": data_source,
        "data_version": data_version,
        "price_type": price_type,
        "is_synthetic": _synthetic_flag(values["is_synthetic"], context),
    }


def _benchmark_provenance(
    mapping: pd.Series,
    price_rows: pd.DataFrame,
) -> BenchmarkProvenance:
    benchmark_id = _required_text(mapping, "benchmark_id", "Benchmark mapping")
    benchmark_name = _required_text(mapping, "benchmark_name", f"Benchmark {benchmark_id}")
    benchmark_type = _required_text(mapping, "benchmark_type", f"Benchmark {benchmark_id}")

    values = _validated_price_provenance(
        price_rows,
        f"Price data for {benchmark_id}",
    )

    return BenchmarkProvenance(
        benchmark_id=benchmark_id,
        benchmark_name=benchmark_name,
        benchmark_type=benchmark_type,
        data_source=str(values["data_source"]),
        data_version=str(values["data_version"]),
        as_of=pd.Timestamp(price_rows["date"].max()),
        price_type=str(values["price_type"]),
        is_synthetic=bool(values["is_synthetic"]),
    )


def _industry_provenance(
    membership: pd.Series,
    as_of: pd.Timestamp,
) -> IndustryProvenance:
    industry_id = _required_text(membership, "industry_id", "Industry membership")
    industry_name = _required_text(membership, "industry_name", "Industry membership")
    classification = _required_text(
        membership,
        "classification",
        "Industry membership",
    )
    data_source = _required_text(membership, "data_source", "Industry membership")
    data_version = _required_text(membership, "data_version", "Industry membership")
    if "is_synthetic" not in membership or pd.isna(membership["is_synthetic"]):
        raise _EvidenceDataError("Industry membership has no is_synthetic")

    return IndustryProvenance(
        industry_id=industry_id,
        industry_name=industry_name,
        as_of=as_of,
        classification=classification,
        data_source=data_source,
        data_version=data_version,
        is_synthetic=_synthetic_flag(
            membership["is_synthetic"],
            f"Industry membership {industry_id}",
        ),
    )


def _empyrical_total_return(prices: pd.Series, instrument: str) -> float:
    simple_returns = empyrical.simple_returns(prices)
    result = empyrical.cum_returns_final(simple_returns)
    if pd.isna(result) or not math.isfinite(float(result)):
        raise _EvidenceDataError(f"empyrical returned an invalid return for {instrument}")
    return float(result)


def _comparison(asset_return: float, benchmark_return: float) -> Comparison:
    if math.isclose(asset_return, benchmark_return, rel_tol=1e-9, abs_tol=1e-12):
        return "matched"
    if asset_return > benchmark_return:
        return "outperformed"
    return "underperformed"


def _insufficient_evidence(
    episode: InvestmentEpisode,
    end_time: pd.Timestamp | None,
    reason: str,
    *,
    market_benchmark_name: str | None = None,
    industry_id: str | None = None,
    industry_name: str | None = None,
    industry_as_of_date: pd.Timestamp | None = None,
    industry_benchmark_name: str | None = None,
    industry_provenance: IndustryProvenance | None = None,
    provenance: tuple[BenchmarkProvenance, ...] = (),
) -> SelectionEvidence:
    return SelectionEvidence(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        start_time=episode.entry_time,
        end_time=end_time,
        asset_return=None,
        market_benchmark_id=MARKET_BENCHMARK_ID,
        market_benchmark_name=market_benchmark_name,
        market_benchmark_return=None,
        market_comparison=None,
        industry_id=industry_id,
        industry_name=industry_name,
        industry_as_of_date=industry_as_of_date,
        industry_benchmark_id=industry_id,
        industry_benchmark_name=industry_benchmark_name,
        industry_benchmark_return=None,
        industry_comparison=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
        industry_provenance=industry_provenance,
        benchmark_provenance=provenance,
    )


def build_selection_evidence(
    episode: InvestmentEpisode,
    provider: LocalMarketDataProvider,
) -> SelectionEvidence:
    """Build factual SelectionEvidence using point-in-time local data.

    Returns are delegated exclusively to ``empyrical.simple_returns`` followed
    by ``empyrical.cum_returns_final``.  No excess-return or attribution
    formula is implemented here.
    """

    if episode.status == "Closed":
        end_time = episode.exit_time
    elif episode.status == "Open":
        end_time = episode.valuation_time
    else:
        return _insufficient_evidence(
            episode,
            None,
            f"Unsupported episode status: {episode.status}",
        )

    if pd.isna(episode.entry_time):
        return _insufficient_evidence(episode, end_time, "Episode has no valid start time")
    if end_time is None or pd.isna(end_time):
        return _insufficient_evidence(episode, None, "Episode has no valid end time")

    start_time = pd.Timestamp(episode.entry_time)
    end_time = pd.Timestamp(end_time)
    start_date = start_time.normalize()
    end_date = end_time.normalize()
    if end_date < start_date:
        return _insufficient_evidence(
            episode,
            end_time,
            "Episode end date precedes its start date",
        )

    market_name: str | None = None
    industry_id: str | None = None
    industry_name: str | None = None
    industry_as_of_date: pd.Timestamp | None = None
    industry_benchmark_name: str | None = None
    industry_provenance: IndustryProvenance | None = None
    provenance: list[BenchmarkProvenance] = []

    try:
        market_mapping = provider.get_benchmark(MARKET_BENCHMARK_ID)
        market_name = _required_text(
            market_mapping,
            "benchmark_name",
            f"Benchmark {MARKET_BENCHMARK_ID}",
        )
        market_type = _required_text(
            market_mapping,
            "benchmark_type",
            f"Benchmark {MARKET_BENCHMARK_ID}",
        )
        if market_type != "market":
            raise _EvidenceDataError(
                f"Benchmark {MARKET_BENCHMARK_ID} is not mapped as market"
            )
    except (LookupError, ValueError, _EvidenceDataError) as exc:
        return _insufficient_evidence(
            episode,
            end_time,
            f"Market benchmark mapping unavailable: {exc}",
        )

    try:
        industry = provider.get_industry(episode.symbol, episode.entry_time)
        industry_as_of_date = start_time
        industry_provenance = _industry_provenance(industry, industry_as_of_date)
        industry_id = industry_provenance.industry_id
        industry_name = industry_provenance.industry_name
    except (LookupError, ValueError, _EvidenceDataError) as exc:
        return _insufficient_evidence(
            episode,
            end_time,
            f"Point-in-time industry membership unavailable: {exc}",
            market_benchmark_name=market_name,
            industry_as_of_date=industry_as_of_date,
        )

    try:
        industry_mapping = provider.get_benchmark(industry_id)
        industry_benchmark_name = _required_text(
            industry_mapping,
            "benchmark_name",
            f"Benchmark {industry_id}",
        )
        industry_type = _required_text(
            industry_mapping,
            "benchmark_type",
            f"Benchmark {industry_id}",
        )
        if industry_type != "industry":
            raise _EvidenceDataError(f"Benchmark {industry_id} is not mapped as industry")
    except (LookupError, ValueError, _EvidenceDataError) as exc:
        return _insufficient_evidence(
            episode,
            end_time,
            f"Industry benchmark mapping unavailable: {exc}",
            market_benchmark_name=market_name,
            industry_id=industry_id,
            industry_name=industry_name,
            industry_as_of_date=industry_as_of_date,
            industry_provenance=industry_provenance,
        )

    try:
        asset_prices, _ = _price_window(
            provider, episode.symbol, start_date, end_date
        )
        market_prices, market_rows = _price_window(
            provider, MARKET_BENCHMARK_ID, start_date, end_date
        )
        market_provenance = _benchmark_provenance(market_mapping, market_rows)
        provenance.append(market_provenance)
        industry_prices, industry_rows = _price_window(
            provider, industry_id, start_date, end_date
        )
        industry_benchmark_provenance = _benchmark_provenance(
            industry_mapping, industry_rows
        )
        provenance.append(industry_benchmark_provenance)

        asset_return = _empyrical_total_return(asset_prices, episode.symbol)
        market_return = _empyrical_total_return(market_prices, MARKET_BENCHMARK_ID)
        industry_return = _empyrical_total_return(industry_prices, industry_id)
    except (ValueError, _EvidenceDataError) as exc:
        return _insufficient_evidence(
            episode,
            end_time,
            str(exc),
            market_benchmark_name=market_name,
            industry_id=industry_id,
            industry_name=industry_name,
            industry_as_of_date=industry_as_of_date,
            industry_benchmark_name=industry_benchmark_name,
            industry_provenance=industry_provenance,
            provenance=tuple(provenance),
        )

    evidence_status: EvidenceStatus
    evidence_reason: str | None
    if episode.status == "Closed":
        evidence_status = "complete"
        evidence_reason = None
    else:
        evidence_status = "partial"
        evidence_reason = "Open episode evaluated through valuation_time"

    return SelectionEvidence(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        start_time=start_time,
        end_time=end_time,
        asset_return=asset_return,
        market_benchmark_id=MARKET_BENCHMARK_ID,
        market_benchmark_name=market_name,
        market_benchmark_return=market_return,
        market_comparison=_comparison(asset_return, market_return),
        industry_id=industry_id,
        industry_name=industry_name,
        industry_as_of_date=industry_as_of_date,
        industry_benchmark_id=industry_id,
        industry_benchmark_name=industry_benchmark_name,
        industry_benchmark_return=industry_return,
        industry_comparison=_comparison(asset_return, industry_return),
        evidence_status=evidence_status,
        evidence_reason=evidence_reason,
        industry_provenance=industry_provenance,
        benchmark_provenance=tuple(provenance),
    )
