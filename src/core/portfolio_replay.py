"""Thin vectorbt adapters for deterministic multi-asset portfolio replay.

This module validates and maps inputs into ``vectorbt.Portfolio`` objects.  It
does not calculate positions, cash, exposure, returns, or PnL itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
import vectorbt as vbt
from numba import njit
from vectorbt.portfolio.enums import (
    Direction,
    NoOrder,
    RejectedOrderError,
    SizeType,
)
from vectorbt.portfolio.nb import order_nb

from src.core.canonical_execution import (
    CanonicalExecutionV2,
    canonical_executions_to_frame,
)


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


@dataclass(frozen=True, slots=True)
class ReplayExecutionLink:
    """Verified link from one accepted execution to vectorbt records."""

    execution_id: str
    vectorbt_order_record_id: int
    vectorbt_exit_trade_record_id: int | None
    vectorbt_position_record_id: int | None


@dataclass(frozen=True, slots=True)
class PortfolioReplayResult:
    """Authoritative portfolio plus its execution-level record links."""

    portfolio: vbt.Portfolio
    execution_links: tuple[ReplayExecutionLink, ...]


@njit(cache=True)
def _flex_execution_order_nb(c, counts, columns, sizes, prices, fixed_fees):
    """Emit accepted broker fills in the adapter's canonical sequence."""

    if c.call_idx >= counts[c.i]:
        return -1, NoOrder
    slot = c.call_idx
    return columns[c.i, slot], order_nb(
        size=sizes[c.i, slot],
        price=prices[c.i, slot],
        size_type=SizeType.Amount,
        direction=Direction.LongOnly,
        fees=0.0,
        fixed_fees=fixed_fees[c.i, slot],
        slippage=0.0,
        reject_prob=0.0,
        allow_partial=False,
        raise_reject=True,
    )


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

    frame = executions.copy()
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
    if "execution_sequence" in frame.columns:
        numeric_sequence = pd.to_numeric(frame["execution_sequence"], errors="coerce")
        for _, rows in frame.assign(_sequence=numeric_sequence).groupby(
            "event_time", sort=False
        ):
            values = rows["_sequence"]
            if len(rows) > 1 and (
                values.isna().any() or values.duplicated().any()
            ):
                raise PortfolioReplayError(
                    "ambiguous_execution_order: same-time executions require unique sequence"
                )
        if numeric_sequence.isna().any():
            singleton_times = (
                frame.groupby("event_time")["event_time"].transform("size") == 1
            )
            numeric_sequence = numeric_sequence.where(~singleton_times, 0)
        if numeric_sequence.isna().any() or (numeric_sequence < 0).any():
            raise PortfolioReplayError("execution_sequence must be a non-negative number")
        if not np.equal(numeric_sequence, np.floor(numeric_sequence)).all():
            raise PortfolioReplayError("execution_sequence must contain integers")
        frame["execution_sequence"] = numeric_sequence.astype(np.int64)
        frame = frame.sort_values(
            ["event_time", "execution_sequence"], kind="stable"
        )
    else:
        # Legacy frames retain their established physical order, but cannot
        # claim a reliable order for colliding fills of the same instrument.
        if frame.duplicated(["event_time", "symbol"]).any():
            raise PortfolioReplayError(
                "Portfolio replay accepts at most one execution per symbol at a timestamp "
                "for legacy inputs; ambiguous_execution_order requires explicit sequence"
            )
        frame = frame.sort_values("event_time", kind="stable")
    return frame.reset_index(drop=True)


def _flex_order_arrays(
    frame: pd.DataFrame,
    marks: pd.DataFrame,
    symbols: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build compact flexible-order arrays without aggregating any fill."""

    per_bar = frame.groupby("event_time", sort=False).size()
    max_orders_per_bar = int(per_bar.max())
    counts = np.zeros(len(marks.index), dtype=np.int64)
    columns = np.zeros((len(marks.index), max_orders_per_bar), dtype=np.int64)
    sizes = np.zeros((len(marks.index), max_orders_per_bar), dtype=np.float64)
    prices = np.zeros((len(marks.index), max_orders_per_bar), dtype=np.float64)
    fees = np.zeros((len(marks.index), max_orders_per_bar), dtype=np.float64)
    symbol_position = {symbol: position for position, symbol in enumerate(symbols)}
    for timestamp, rows in frame.groupby("event_time", sort=False):
        bar = int(marks.index.get_loc(timestamp))
        counts[bar] = len(rows)
        for slot, (_, row) in enumerate(rows.iterrows()):
            columns[bar, slot] = symbol_position[str(row["symbol"])]
            sizes[bar, slot] = float(row["executed_quantity"]) * _SIDE_SIGN[str(row["side"])]
            prices[bar, slot] = float(row["executed_price"])
            fees[bar, slot] = float(row["fee"])
    return counts, columns, sizes, prices, fees


def _same_float(left: object, right: object) -> bool:
    try:
        return bool(np.isclose(float(left), float(right), rtol=1e-9, atol=1e-8))
    except (TypeError, ValueError):
        return False


def _verified_execution_links(
    portfolio: vbt.Portfolio,
    frame: pd.DataFrame,
) -> tuple[ReplayExecutionLink, ...]:
    orders = portfolio.orders.records_readable.sort_values("Order Id", kind="stable")
    if len(orders) != len(frame):
        raise PortfolioReplayError(
            "Replay link verification failed: accepted order count differs from execution count"
        )

    mutable: dict[str, dict[str, int | str | None]] = {}
    order_by_id: dict[int, pd.Series] = {}
    for (_, execution), (_, order) in zip(frame.iterrows(), orders.iterrows()):
        execution_id = str(execution["execution_id"])
        order_id = int(order["Order Id"])
        expected_side = "Buy" if execution["side"] == "BUY" else "Sell"
        if (
            str(order["Column"]) != str(execution["symbol"])
            or pd.Timestamp(order["Timestamp"]) != pd.Timestamp(execution["event_time"])
            or str(order["Side"]) != expected_side
            or not _same_float(order["Size"], execution["executed_quantity"])
            or not _same_float(order["Price"], execution["executed_price"])
            or not _same_float(order["Fees"], execution["fee"])
        ):
            raise PortfolioReplayError(
                f"Replay link verification failed for execution {execution_id}"
            )
        mutable[execution_id] = {
            "execution_id": execution_id,
            "vectorbt_order_record_id": order_id,
            "vectorbt_exit_trade_record_id": None,
            "vectorbt_position_record_id": None,
        }
        order_by_id[order_id] = order

    # Reverse index built once: the previous next()-over-all-executions scan
    # inside the exit loop made link verification O(sells x n) on large accounts.
    execution_by_order_record = {
        value["vectorbt_order_record_id"]: execution_id
        for execution_id, value in mutable.items()
    }

    # In vectorbt 1.1.0 get_exit_trades_nb, each long-position SELL order
    # produces one closed Exit Trade while scanning per-column Order Ids in
    # ascending order.  Validate every public field that links the two records.
    exits = portfolio.exit_trades.closed.records_readable
    for symbol in sorted(frame["symbol"].unique()):
        sell_ids = [
            int(row["Order Id"])
            for _, row in orders[
                (orders["Column"].astype(str) == symbol)
                & (orders["Side"].astype(str) == "Sell")
            ].iterrows()
        ]
        symbol_exits = exits[exits["Column"].astype(str) == symbol].sort_values(
            "Exit Trade Id", kind="stable"
        )
        if len(sell_ids) != len(symbol_exits):
            raise PortfolioReplayError(
                f"outcome_mapping_unavailable: SELL/Exit Trade count differs for {symbol}"
            )
        for order_id, (_, exit_record) in zip(sell_ids, symbol_exits.iterrows()):
            order = order_by_id[order_id]
            if (
                pd.Timestamp(exit_record["Exit Timestamp"])
                != pd.Timestamp(order["Timestamp"])
                or not _same_float(exit_record["Size"], order["Size"])
                or not _same_float(exit_record["Avg Exit Price"], order["Price"])
                or not _same_float(exit_record["Exit Fees"], order["Fees"])
            ):
                raise PortfolioReplayError(
                    f"outcome_mapping_unavailable: Exit Trade mismatch for order {order_id}"
                )
            # Reverse index built once: the previous next()-over-all-executions
            # scan made link verification O(sells x n) on large accounts.
            execution_id = execution_by_order_record.get(order_id)
            if execution_id is None:
                raise PortfolioReplayError(
                    f"outcome_mapping_unavailable: no execution maps to order record {order_id}"
                )
            mutable[execution_id]["vectorbt_exit_trade_record_id"] = int(
                exit_record["Exit Trade Id"]
            )
            mutable[execution_id]["vectorbt_position_record_id"] = int(
                exit_record["Position Id"]
            )

    positions = portfolio.positions.records_readable.sort_values(
        ["Column", "Position Id"], kind="stable"
    )
    order_to_execution = {
        int(value["vectorbt_order_record_id"]): key for key, value in mutable.items()
    }
    for symbol in sorted(frame["symbol"].unique()):
        symbol_positions = positions[
            positions["Column"].astype(str) == symbol
        ].sort_values("Position Id", kind="stable")
        position_ids = [int(value) for value in symbol_positions["Position Id"]]
        closed_position_ids = {
            int(row["Position Id"])
            for _, row in symbol_positions.iterrows()
            if str(row["Status"]) == "Closed"
        }
        closing_order_by_position: dict[int, int] = {}
        for value in mutable.values():
            position_id = value["vectorbt_position_record_id"]
            if position_id is None:
                continue
            order_id = int(value["vectorbt_order_record_id"])
            if int(position_id) in closed_position_ids:
                closing_order_by_position[int(position_id)] = max(
                    order_id,
                    closing_order_by_position.get(int(position_id), -1),
                )
        position_index = 0
        current_position_id: int | None = None
        symbol_orders = orders[orders["Column"].astype(str) == symbol].sort_values(
            "Order Id", kind="stable"
        )
        for _, order in symbol_orders.iterrows():
            order_id = int(order["Order Id"])
            if current_position_id is None:
                if position_index >= len(position_ids):
                    raise PortfolioReplayError(
                        f"Replay Position link verification failed for {symbol}"
                    )
                current_position_id = position_ids[position_index]
                position_index += 1
            execution_id = order_to_execution[order_id]
            existing = mutable[execution_id]["vectorbt_position_record_id"]
            if existing is not None and int(existing) != current_position_id:
                raise PortfolioReplayError(
                    f"Replay Position link mismatch for execution {execution_id}"
                )
            mutable[execution_id]["vectorbt_position_record_id"] = current_position_id
            if closing_order_by_position.get(current_position_id) == order_id:
                current_position_id = None
        if position_index != len(position_ids):
            raise PortfolioReplayError(
                f"Replay Position link count mismatch for {symbol}"
            )
    return tuple(
        ReplayExecutionLink(**item)  # type: ignore[arg-type]
        for item in mutable.values()
    )


def replay_multi_asset_executions_with_links(
    executions: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
    _cash_sharing: bool = True,
    _freq: str | None = None,
) -> PortfolioReplayResult:
    """Replay every fill through one flexible vectorbt engine and verify links."""

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
    counts, columns, sizes, prices, fees = _flex_order_arrays(frame, marks, symbols)
    try:
        portfolio = vbt.Portfolio.from_order_func(
            marks,
            _flex_execution_order_nb,
            counts,
            columns,
            sizes,
            prices,
            fees,
            flexible=True,
            max_orders=len(frame),
            init_cash=normalized_init_cash,
            cash_sharing=_cash_sharing,
            group_by=True if _cash_sharing else False,
            update_value=False,
            ffill_val_price=True,
            freq=_freq,
        )
    except (RejectedOrderError, ValueError) as exc:
        raise PortfolioReplayError(f"vectorbt could not replay executions: {exc}") from exc
    return PortfolioReplayResult(
        portfolio=portfolio,
        execution_links=_verified_execution_links(portfolio, frame),
    )


def replay_multi_asset_executions(
    executions: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> vbt.Portfolio:
    """Replay normalized long-only executions with shared cash through vectorbt.

    Broker order and execution identifiers remain an audit sidecar. Explicit
    ``execution_sequence`` controls same-time v2 ordering. Legacy frames retain
    stable row order only where the old contract is unambiguous.
    """

    return replay_multi_asset_executions_with_links(
        executions,
        valuation_prices,
        init_cash=init_cash,
    ).portfolio


def replay_canonical_executions(
    executions: Sequence[CanonicalExecutionV2],
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> PortfolioReplayResult:
    """Replay CanonicalExecutionV2 facts through the same financial core."""

    try:
        frame = canonical_executions_to_frame(executions)
    except ValueError as exc:
        raise PortfolioReplayError(str(exc)) from exc
    return replay_multi_asset_executions_with_links(
        frame,
        valuation_prices,
        init_cash=init_cash,
    )


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
