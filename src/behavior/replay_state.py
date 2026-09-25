"""Shared vectorbt state for the bounded Behavior Evidence v1 metrics."""

from __future__ import annotations

import math
from collections import OrderedDict
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
    ReplayExecutionLink,
    _validated_executions,
    replay_multi_asset_executions_with_links,
)
from src.core.position_fold import advance_fold
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
    execution_links: tuple[ReplayExecutionLink, ...]
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
    if "market_date" in executions.columns:
        try:
            start_date = pd.to_datetime(
                executions["market_date"], errors="raise"
            ).min().normalize()
        except (TypeError, ValueError) as exc:
            raise BehaviorReplayError("execution market_date must contain dates") from exc
    else:
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

    if "market_date" in executions.columns:
        try:
            execution_market_dates = pd.to_datetime(
                executions["market_date"], errors="raise"
            ).dt.normalize()
        except (TypeError, ValueError) as exc:
            raise BehaviorReplayError("execution market_date must contain dates") from exc
        if execution_market_dates.isna().any():
            raise BehaviorReplayError("execution market_date cannot contain NaT")
    else:
        execution_market_dates = executions["event_time"].dt.normalize()
    execution_dates = pd.DatetimeIndex(execution_market_dates).unique()
    missing_execution_dates = execution_dates.difference(daily_prices.index)
    if not missing_execution_dates.empty:
        raise BehaviorReplayError(
            "Missing market prices for execution dates: "
            f"{missing_execution_dates.tolist()}"
        )

    valuation_times = daily_prices.index.union(
        pd.DatetimeIndex(executions["event_time"].unique())
    ).sort_values()
    market_date_by_time = {
        pd.Timestamp(event_time): pd.Timestamp(market_date)
        for event_time, market_date in zip(
            executions["event_time"], execution_market_dates
        )
    }
    valuation_prices = pd.DataFrame(
        [
            daily_prices.loc[
                market_date_by_time.get(pd.Timestamp(timestamp), timestamp.normalize())
            ].to_numpy()
            for timestamp in valuation_times
        ],
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
        replay = replay_multi_asset_executions_with_links(
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
        portfolio=replay.portfolio,
        execution_links=replay.execution_links,
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


_FOLD_CACHE: "OrderedDict[int, tuple[BehaviorReplayContext, dict[str, object]]]" = OrderedDict()
_FOLD_CACHE_MAX_CONTEXTS = 8
_FOLD_SNAPSHOTS_KEPT = 4


def clear_fold_cache() -> None:
    """Drops cached fold state (entries pin executions and replay contexts)."""
    _FOLD_CACHE.clear()


def _execution_count_before(context: BehaviorReplayContext, event_time: pd.Timestamp) -> tuple[int, dict[str, tuple[float, float, float]]]:
    """Count of fills strictly before ``event_time`` plus the position fold.

    The count comes from a cached searchsorted over execution timestamps
    (O(log n)); the fold advances monotonically with small snapshots, so a
    full prefix replay per query is never needed.
    """
    key = id(context)
    entry = _FOLD_CACHE.get(key)
    if entry is None or entry[0] is not context:
        times = context.executions["event_time"].to_numpy(dtype="datetime64[ns]")
        entry = (context, {"times": times, "positions": {}, "max": 0,
                           "snapshots": OrderedDict()})
        _FOLD_CACHE[key] = entry
        while len(_FOLD_CACHE) > _FOLD_CACHE_MAX_CONTEXTS:
            _FOLD_CACHE.popitem(last=False)
    cache = entry[1]
    count = int(cache["times"].searchsorted(event_time.to_datetime64(), side="left"))
    snapshots: OrderedDict = cache["snapshots"]
    if count in snapshots:
        return count, snapshots[count]
    if count < cache["max"]:
        cache["max"] = 0
        cache["positions"] = {}
        snapshots.clear()
    advance_fold(cache["positions"], context.executions, cache["max"], count)
    cache["max"] = count
    snapshots[count] = dict(cache["positions"])
    while len(snapshots) > _FOLD_SNAPSHOTS_KEPT:
        snapshots.popitem(last=False)
    return count, snapshots[count]


def prefix_portfolio_state(
    context: BehaviorReplayContext,
    event_time: pd.Timestamp,
) -> PrefixPortfolioState:
    """Holdings and open-position costs strictly before ``event_time``.

    Reads one row of the context's existing full replay (vectorbt is a
    sequential row fold, so a full-replay row is bit-identical to a prefix
    replay's row) and takes average costs from the shared position fold —
    no per-query prefix replay.
    """

    event_time = pd.Timestamp(event_time)
    symbols = context.daily_prices.columns
    fill_count, positions = _execution_count_before(context, event_time)
    if fill_count == 0:
        return PrefixPortfolioState(
            event_time=event_time,
            holdings=pd.Series(0.0, index=symbols, dtype=float),
            average_costs={},
        )

    portfolio = context.portfolio
    index = portfolio.assets().index
    # The row STRICTLY before event_time: fills at exactly t must not leak
    # into the pre-decision state (multiple fills can share one index row).
    # Quantities and cash cannot change between the previous row and t — no
    # fill exists in between — so this row IS the old prefix-replay state.
    # The margin guards move to the same row (previous close, not t's); they
    # are defensive checks only and never part of the returned state.
    row_idx = index.searchsorted(event_time, side="left") - 1
    try:
        if row_idx < 0:
            raise BehaviorReplayError("Prefix replay state is unavailable")
        holdings = portfolio.assets().iloc[row_idx].reindex(symbols, fill_value=0.0).astype(float)
        cash = float(portfolio.cash().iloc[row_idx])
        gross_exposure = float(portfolio.gross_exposure().iloc[row_idx])
    except BehaviorReplayError:
        raise
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
    average_costs: dict[str, float] = {}
    for symbol in holdings[holdings > 0].index:
        entry = positions.get(str(symbol))
        if entry is None or entry[1] <= 0:
            raise BehaviorReplayError(
                f"vectorbt has no unique current open-position state for {symbol}"
            )
        average_cost = entry[2] / entry[1]
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
