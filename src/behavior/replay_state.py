"""Shared vectorbt state for the bounded Behavior Evidence v1 metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.attribution.selection_evidence import (
    PriceProvenance,
    _EvidenceDataError,
    _validated_price_provenance,
)
from src.core.portfolio_replay import (
    PortfolioReplayError,
    _validated_executions,
    replay_multi_asset_executions,
)
from src.data.local_market_data_provider import PRICE_COLUMNS


class BehaviorReplayError(ValueError):
    """Behavior evidence cannot be built from the supplied deterministic facts."""


@dataclass(frozen=True, slots=True)
class BehaviorReplayContext:
    """Validated market panel plus its full vectorbt portfolio replay."""

    executions: pd.DataFrame
    daily_prices: pd.DataFrame
    valuation_prices: pd.DataFrame
    portfolio: object
    init_cash: float
    provenance: tuple[PriceProvenance, ...]

    @property
    def synthetic_provenance_present(self) -> bool:
        return any(item.is_synthetic for item in self.provenance)


@dataclass(frozen=True, slots=True)
class PrefixPortfolioState:
    """Pre-decision vectorbt holdings and open-position average entry prices."""

    event_time: pd.Timestamp
    holdings: pd.Series
    average_costs: dict[str, float]


def _market_panel(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[PriceProvenance, ...]]:
    if not isinstance(market_prices, pd.DataFrame) or market_prices.empty:
        raise BehaviorReplayError("Market prices must contain observations")
    missing = sorted(PRICE_COLUMNS.difference(market_prices.columns))
    if missing:
        raise BehaviorReplayError(f"Missing Market Data Contract columns: {missing}")

    rows = market_prices.loc[:, sorted(PRICE_COLUMNS)].copy()
    if rows["instrument"].isna().any():
        raise BehaviorReplayError("Market price instrument cannot be null")
    rows["instrument"] = rows["instrument"].astype(str).str.strip()
    if rows["instrument"].eq("").any():
        raise BehaviorReplayError("Market price instrument cannot be empty")
    try:
        rows["date"] = pd.to_datetime(rows["date"], errors="raise")
        rows["close"] = pd.to_numeric(rows["close"], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise BehaviorReplayError("Market price dates and closes must be valid") from exc
    if rows["date"].isna().any():
        raise BehaviorReplayError("Market price date cannot be null")
    if rows["close"].isna().any() or not np.isfinite(rows["close"]).all():
        raise BehaviorReplayError("Market price close must be finite")
    if (rows["close"] <= 0).any():
        raise BehaviorReplayError("Market price close must be positive")

    rows["calendar_date"] = rows["date"].dt.normalize()
    symbols = tuple(sorted(executions["symbol"].unique()))
    start_date = pd.Timestamp(executions["event_time"].min()).normalize()
    selected = rows[
        rows["instrument"].isin(symbols) & (rows["calendar_date"] >= start_date)
    ].copy()
    missing_symbols = sorted(set(symbols).difference(selected["instrument"].unique()))
    if missing_symbols:
        raise BehaviorReplayError(
            f"Missing market prices for execution symbols: {missing_symbols}"
        )
    if selected.duplicated(["calendar_date", "instrument"]).any():
        raise BehaviorReplayError(
            "Market prices must contain one observation per symbol and calendar date"
        )

    provenance: list[PriceProvenance] = []
    for symbol in symbols:
        symbol_rows = selected[selected["instrument"] == symbol].sort_values(
            "calendar_date",
            kind="stable",
        )
        try:
            values = _validated_price_provenance(
                symbol_rows,
                f"Behavior market prices for {symbol}",
            )
        except _EvidenceDataError as exc:
            raise BehaviorReplayError(str(exc)) from exc
        provenance.append(
            PriceProvenance(
                instrument=symbol,
                data_source=str(values["data_source"]),
                data_version=str(values["data_version"]),
                as_of=pd.Timestamp(symbol_rows["calendar_date"].max()),
                price_type=str(values["price_type"]),
                is_synthetic=bool(values["is_synthetic"]),
            )
        )

    daily_prices = selected.pivot(
        index="calendar_date",
        columns="instrument",
        values="close",
    ).sort_index(kind="stable")
    daily_prices = daily_prices.reindex(columns=symbols)
    if daily_prices.isna().any().any():
        raise BehaviorReplayError(
            "Market price panel is incomplete; forward fill is not allowed"
        )
    daily_prices.index.name = "event_time"
    daily_prices.columns.name = None

    execution_dates = pd.DatetimeIndex(executions["event_time"]).normalize().unique()
    missing_execution_dates = execution_dates.difference(daily_prices.index)
    if not missing_execution_dates.empty:
        raise BehaviorReplayError(
            "Missing market prices for execution dates: "
            f"{missing_execution_dates.tolist()}"
        )

    valuation_times = daily_prices.index.union(
        pd.DatetimeIndex(executions["event_time"].unique())
    ).sort_values()
    valuation_prices = pd.DataFrame(
        [daily_prices.loc[timestamp.normalize()].to_numpy() for timestamp in valuation_times],
        index=valuation_times,
        columns=daily_prices.columns,
    )
    valuation_prices.index.name = "event_time"
    return daily_prices, valuation_prices, tuple(provenance)


def prepare_behavior_replay(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> BehaviorReplayContext:
    """Validate contract data and build the single full vectorbt replay."""

    try:
        frame = _validated_executions(executions)
        daily_prices, valuation_prices, provenance = _market_panel(
            frame,
            market_prices,
        )
        portfolio = replay_multi_asset_executions(
            frame,
            valuation_prices,
            init_cash=init_cash,
        )
    except (KeyError, PortfolioReplayError, BehaviorReplayError) as exc:
        raise BehaviorReplayError(str(exc)) from exc

    return BehaviorReplayContext(
        executions=frame,
        daily_prices=daily_prices,
        valuation_prices=valuation_prices,
        portfolio=portfolio,
        init_cash=float(init_cash),
        provenance=provenance,
    )


def market_price(
    context: BehaviorReplayContext,
    event_time: pd.Timestamp,
    symbol: str,
) -> float:
    """Return that calendar day's validated market close without filling."""

    try:
        value = float(context.daily_prices.loc[event_time.normalize(), symbol])
    except KeyError as exc:
        raise BehaviorReplayError(
            f"Missing market price for {symbol} at {event_time.normalize().date()}"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise BehaviorReplayError("Market price must be finite and positive")
    return value


def prefix_portfolio_state(
    context: BehaviorReplayContext,
    event_time: pd.Timestamp,
) -> PrefixPortfolioState:
    """Replay executions strictly before ``event_time`` and inspect vectorbt."""

    event_time = pd.Timestamp(event_time)
    prior = context.executions[context.executions["event_time"] < event_time]
    symbols = context.daily_prices.columns
    if prior.empty:
        return PrefixPortfolioState(
            event_time=event_time,
            holdings=pd.Series(0.0, index=symbols, dtype=float),
            average_costs={},
        )

    try:
        portfolio = replay_multi_asset_executions(
            prior,
            context.valuation_prices.loc[:event_time],
            init_cash=context.init_cash,
        )
    except PortfolioReplayError as exc:
        raise BehaviorReplayError(f"Prefix replay unavailable: {exc}") from exc

    assets = portfolio.assets()
    try:
        holdings = assets.loc[event_time].reindex(symbols, fill_value=0.0).astype(float)
        cash = float(portfolio.cash().loc[event_time])
        gross_exposure = float(portfolio.gross_exposure().loc[event_time])
    except (KeyError, TypeError, ValueError) as exc:
        raise BehaviorReplayError("Prefix replay state is unavailable") from exc
    if not np.isfinite(holdings.to_numpy()).all() or (holdings < -1e-9).any():
        raise BehaviorReplayError("Short or invalid prefix holdings are unsupported")
    if not math.isfinite(cash) or cash < -1e-8:
        raise BehaviorReplayError("Margin cash is unsupported")
    if not math.isfinite(gross_exposure) or gross_exposure > 1.0 + 1e-9:
        raise BehaviorReplayError("Margin exposure is unsupported")
    holdings = holdings.mask(holdings.abs() <= 1e-12, 0.0)

    # ``positions.open`` aggregates the entire lifecycle.  After a partial
    # exit followed by another entry its Avg Entry Price is not necessarily
    # the cost basis of the quantity that remains open.  vectorbt's open exit
    # trade is the current remaining-position record.
    open_positions = portfolio.exit_trades.open.records_readable
    average_costs: dict[str, float] = {}
    for symbol in holdings[holdings > 0].index:
        records = open_positions[open_positions["Column"] == symbol]
        if len(records) != 1:
            raise BehaviorReplayError(
                f"vectorbt has no unique current open-position state for {symbol}"
            )
        record = records.iloc[0]
        average_cost = float(record["Avg Entry Price"])
        if not math.isfinite(average_cost) or average_cost <= 0:
            raise BehaviorReplayError(
                f"vectorbt open-position average cost is unavailable for {symbol}"
            )
        average_costs[str(symbol)] = average_cost

    return PrefixPortfolioState(
        event_time=event_time,
        holdings=holdings,
        average_costs=average_costs,
    )


def daily_portfolio_value(context: BehaviorReplayContext) -> pd.Series:
    """Return end-of-calendar-day vectorbt portfolio values."""

    values = context.portfolio.value().copy()
    values.index = pd.DatetimeIndex(values.index).normalize()
    return values.groupby(level=0, sort=True).last().reindex(context.daily_prices.index)
