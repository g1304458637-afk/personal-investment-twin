"""Minimal historical market-data ingestion boundary."""

from .generic_csv import (
    GENERIC_HISTORICAL_PRICE_CSV_V1,
    GenericHistoricalPriceCsvAdapter,
    GenericPriceCsvConfig,
)
from .models import (
    HistoricalPriceFact,
    MarketDataAvailability,
    MarketDataImportPreview,
    facts_to_market_data_frame,
    resolve_market_data_requirements,
)

__all__ = [
    "GENERIC_HISTORICAL_PRICE_CSV_V1",
    "GenericHistoricalPriceCsvAdapter",
    "GenericPriceCsvConfig",
    "HistoricalPriceFact",
    "EpisodeBuildGateResult",
    "MarketDataAvailability",
    "MarketDataImportPreview",
    "facts_to_market_data_frame",
    "resolve_market_data_requirements",
    "build_episode_when_market_ready",
]


def __getattr__(name):
    # Ingestion/account startup must not load the financial replay engine.
    if name in {"EpisodeBuildGateResult", "build_episode_when_market_ready"}:
        from . import episode_gate
        return getattr(episode_gate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
