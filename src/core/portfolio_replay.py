"""Thin vectorbt adapters for deterministic multi-asset portfolio replay.

This module validates and maps inputs into ``vectorbt.Portfolio`` objects.  It
does not calculate positions, cash, exposure, returns, or PnL itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd
import vectorbt as vbt
from vectorbt.portfolio.enums import RejectedOrderError, SizeType


NORMALIZED_EXECUTION_COLUMNS: Final[tuple[str, ...]] = (
    "event_time",
    "symbol",
    "side",
    "executed_quantity",
    "executed_price",
    "fee",
    "order_id",
    "execution_id",
)

_SIDE_SIGN: Final[dict[str, float]] = {"BUY": 1.0, "SELL": -1.0}


class PortfolioReplayError(ValueError):
    """Input cannot be represented by the bounded long-only replay adapter."""


def _validated_prices(valuation_prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(valuation_prices, pd.DataFrame):
        raise PortfolioReplayError("valuation_prices must be a pandas DataFrame")
    if valuation_prices.empty:
        raise PortfolioReplayError("valuation_prices must contain prices")

    marks = valuation_prices.copy()
    try:
        marks.index = pd.to_datetime(marks.index, errors="raise")
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("valuation_prices index must contain timestamps") from exc
    if marks.index.hasnans:
        raise PortfolioReplayError("valuation_prices index cannot contain NaT")
    if marks.index.duplicated().any():
        raise PortfolioReplayError("valuation_prices index must be unique")

    normalized_columns: list[str] = []
    for column in marks.columns:
        if pd.isna(column):
            raise PortfolioReplayError("valuation_prices symbol cannot be null")
        symbol = str(column).strip()
        if not symbol:
            raise PortfolioReplayError("valuation_prices symbol cannot be empty")
        normalized_columns.append(symbol)
    if len(set(normalized_columns)) != len(normalized_columns):
        raise PortfolioReplayError("valuation_prices symbols must be unique")
    marks.columns = normalized_columns

    try:
        marks = marks.apply(pd.to_numeric, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("valuation_prices must be numeric") from exc
    if marks.isna().any().any():
        raise PortfolioReplayError("valuation_prices cannot contain null values")
    if not np.isfinite(marks.to_numpy()).all():
        raise PortfolioReplayError("valuation_prices must be finite")
    if (marks <= 0).any().any():
        raise PortfolioReplayError("valuation_prices must be positive")
    return marks.sort_index(kind="stable")


def _validated_executions(executions: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(executions, pd.DataFrame):
        raise PortfolioReplayError("executions must be a pandas DataFrame")
    missing = sorted(set(NORMALIZED_EXECUTION_COLUMNS).difference(executions.columns))
    if missing:
        raise PortfolioReplayError(f"Missing normalized execution columns: {missing}")
    if executions.empty:
        raise PortfolioReplayError("At least one execution is required")

    frame = executions.loc[:, NORMALIZED_EXECUTION_COLUMNS].copy()
    required_facts = (
        "event_time",
        "symbol",
        "side",
        "executed_quantity",
        "executed_price",
        "fee",
        "execution_id",
    )
    null_columns = [field for field in required_facts if frame[field].isna().any()]
    if null_columns:
        raise PortfolioReplayError(
            f"Required normalized execution facts cannot be null: {null_columns}"
        )

    try:
        frame["event_time"] = pd.to_datetime(frame["event_time"], errors="raise")
        for field in ("executed_quantity", "executed_price", "fee"):
            frame[field] = pd.to_numeric(frame[field], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("Execution timestamps and numeric facts must be valid") from exc

    frame["symbol"] = frame["symbol"].astype(str).str.strip()
    frame["side"] = frame["side"].astype(str).str.strip().str.upper()
    if frame["symbol"].eq("").any():
        raise PortfolioReplayError("symbol cannot be empty")
    if set(frame["side"]).difference(_SIDE_SIGN):
        raise PortfolioReplayError("side must be BUY or SELL")

    numeric = frame[["executed_quantity", "executed_price", "fee"]].to_numpy()
    if not np.isfinite(numeric).all():
        raise PortfolioReplayError("Execution quantities, prices, and fees must be finite")
    if (frame["executed_quantity"] <= 0).any():
        raise PortfolioReplayError("executed_quantity must be positive")
    if (frame["executed_price"] <= 0).any():
        raise PortfolioReplayError("executed_price must be positive")
    if (frame["fee"] < 0).any():
        raise PortfolioReplayError("fee must be non-negative")
    if frame["execution_id"].duplicated().any():
        raise PortfolioReplayError("execution_id must be unique")
    if frame.duplicated(["event_time", "symbol"]).any():
        raise PortfolioReplayError(
            "Portfolio replay accepts at most one execution per symbol at a timestamp"
        )
    return frame.sort_values("event_time", kind="stable")


def _execution_call_sequence(
    frame: pd.DataFrame,
    marks: pd.DataFrame,
    symbols: list[str],
) -> np.ndarray:
    """Preserve normalized row order within each execution timestamp."""

    default = np.arange(len(symbols), dtype=np.int64)
    call_sequence = np.tile(default, (len(marks.index), 1))
    symbol_position = {symbol: position for position, symbol in enumerate(symbols)}
    for timestamp, rows in frame.groupby("event_time", sort=False):
        executed = [symbol_position[symbol] for symbol in rows["symbol"]]
        executed_set = set(executed)
        inactive = [position for position in default if position not in executed_set]
        call_sequence[marks.index.get_loc(timestamp)] = executed + inactive
    return call_sequence


def replay_multi_asset_executions(
    executions: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> vbt.Portfolio:
    """Replay normalized long-only executions with shared cash through vectorbt.

    Broker order and execution identifiers remain in the normalized input as an
    audit sidecar; vectorbt does not need them for portfolio calculations.  For
    executions sharing a timestamp, DataFrame row order is the execution order.
    """

    frame = _validated_executions(executions)
    marks = _validated_prices(valuation_prices)
    try:
        normalized_init_cash = float(init_cash)
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("init_cash must be numeric") from exc
    if not np.isfinite(normalized_init_cash) or normalized_init_cash <= 0:
        raise PortfolioReplayError("init_cash must be finite and positive")

    symbols = sorted(frame["symbol"].unique())
    missing_symbols = sorted(set(symbols).difference(marks.columns))
    if missing_symbols:
        raise PortfolioReplayError(
            f"Missing valuation price columns for executions: {missing_symbols}"
        )
    missing_times = pd.Index(frame["event_time"].unique()).difference(marks.index)
    if not missing_times.empty:
        raise PortfolioReplayError(
            f"Missing valuation timestamps for executions: {missing_times.tolist()}"
        )

    marks = marks.loc[:, symbols]
    indexed = frame.assign(
        signed_size=frame["executed_quantity"] * frame["side"].map(_SIDE_SIGN)
    ).set_index(["event_time", "symbol"])
    size = (
        indexed["signed_size"]
        .unstack("symbol")
        .reindex(index=marks.index, columns=symbols)
        .fillna(0.0)
    )
    order_price = (
        indexed["executed_price"]
        .unstack("symbol")
        .reindex(index=marks.index, columns=symbols)
        .fillna(marks)
    )
    fixed_fees = (
        indexed["fee"]
        .unstack("symbol")
        .reindex(index=marks.index, columns=symbols)
        .fillna(0.0)
    )
    # Keep vectorbt broadcasting on one asset axis.  ``unstack`` otherwise
    # retains a column-axis name that vectorbt treats as a second index level.
    size.columns.name = marks.columns.name
    order_price.columns.name = marks.columns.name
    fixed_fees.columns.name = marks.columns.name
    call_sequence = _execution_call_sequence(frame, marks, symbols)

    try:
        return vbt.Portfolio.from_orders(
            close=marks,
            size=size,
            size_type=SizeType.Amount,
            direction="longonly",
            price=order_price,
            fees=0.0,
            fixed_fees=fixed_fees,
            slippage=0.0,
            reject_prob=0.0,
            allow_partial=False,
            raise_reject=True,
            init_cash=normalized_init_cash,
            cash_sharing=True,
            group_by=True,
            call_seq=call_sequence,
        )
    except (RejectedOrderError, ValueError) as exc:
        raise PortfolioReplayError(f"vectorbt could not replay executions: {exc}") from exc


def simulate_target_weight_interval(
    valuation_prices: pd.DataFrame,
    *,
    init_value: float,
    target_weights: Mapping[str, float],
) -> vbt.Portfolio:
    """Create a no-rebalance, no-fee TargetPercent interval portfolio."""

    marks = _validated_prices(valuation_prices)
    if len(marks.index) < 2:
        raise PortfolioReplayError("An interval requires distinct start and end prices")
    try:
        normalized_init_value = float(init_value)
    except (TypeError, ValueError) as exc:
        raise PortfolioReplayError("init_value must be numeric") from exc
    if not np.isfinite(normalized_init_value) or normalized_init_value <= 0:
        raise PortfolioReplayError("init_value must be finite and positive")
    if not target_weights:
        raise PortfolioReplayError("At least one target weight is required")

    normalized: dict[str, float] = {}
    for raw_symbol, raw_weight in target_weights.items():
        if pd.isna(raw_symbol):
            raise PortfolioReplayError("target weight symbol cannot be null")
        symbol = str(raw_symbol).strip()
        if not symbol or symbol in normalized:
            raise PortfolioReplayError("target weight symbols must be non-empty and unique")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise PortfolioReplayError("target weights must be numeric") from exc
        if not np.isfinite(weight) or weight < 0:
            raise PortfolioReplayError("target weights must be finite and non-negative")
        normalized[symbol] = weight

    missing_symbols = sorted(set(normalized).difference(marks.columns))
    if missing_symbols:
        raise PortfolioReplayError(
            f"Missing valuation price columns for target weights: {missing_symbols}"
        )
    total_weight = sum(normalized.values())
    if total_weight <= 0 or total_weight > 1.0 + 1e-9:
        raise PortfolioReplayError("Target weights must have exposure in (0, 1]")

    symbols = sorted(normalized)
    marks = marks.loc[:, symbols]
    targets = pd.DataFrame(np.nan, index=marks.index, columns=symbols)
    targets.iloc[0] = pd.Series(normalized).reindex(symbols)

    try:
        return vbt.Portfolio.from_orders(
            close=marks,
            size=targets,
            size_type=SizeType.TargetPercent,
            direction="longonly",
            price=marks,
            val_price=marks,
            fees=0.0,
            fixed_fees=0.0,
            slippage=0.0,
            reject_prob=0.0,
            allow_partial=False,
            raise_reject=True,
            init_cash=normalized_init_value,
            cash_sharing=True,
            group_by=True,
            call_seq="auto",
        )
    except (RejectedOrderError, ValueError) as exc:
        raise PortfolioReplayError(
            f"vectorbt could not simulate target weights: {exc}"
        ) from exc
