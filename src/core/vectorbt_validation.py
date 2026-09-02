"""Minimal vectorbt replay adapter used only by the feasibility experiment.

This module maps normalized execution facts to vectorbt inputs.  It deliberately
does not calculate positions, PnL, fees, or returns itself.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
import vectorbt as vbt


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


def build_synthetic_case() -> tuple[pd.DataFrame, pd.Series]:
    """Return the small, fully synthetic case used in the feasibility tests."""

    event_time = pd.date_range("2026-01-01", periods=5, freq="D", name="event_time")
    valuation_prices = pd.Series(
        [10.0, 11.0, 12.0, 11.5, 13.0],
        index=event_time,
        name="600000.SH",
    )
    executions = pd.DataFrame(
        {
            "event_time": event_time,
            "symbol": "600000.SH",
            "side": ["BUY", "BUY", "SELL", "BUY", "SELL"],
            "executed_quantity": [1000.0, 500.0, 700.0, 400.0, 1200.0],
            "executed_price": valuation_prices.to_numpy(),
            "fee": [10.0, 5.5, 8.4, 4.6, 15.6],
            "order_id": ["ORD-001", "ORD-002", "ORD-003", "ORD-004", "ORD-005"],
            "execution_id": ["EXE-001", "EXE-002", "EXE-003", "EXE-004", "EXE-005"],
        }
    )
    return executions, valuation_prices


def replay_single_symbol_executions(
    executions: pd.DataFrame,
    valuation_prices: pd.Series,
    *,
    init_cash: float,
    direction: str = "longonly",
) -> vbt.Portfolio:
    """Replay normalized executions through ``Portfolio.from_orders``.

    The narrow one-symbol/one-execution-per-timestamp boundary is intentional:
    it makes the feasibility claim testable without pretending that
    ``from_orders`` is a general broker-ledger import API.  Broker identifiers
    remain in ``executions`` as the audit sidecar because vectorbt order records
    do not retain them.
    """

    missing = sorted(set(NORMALIZED_EXECUTION_COLUMNS).difference(executions.columns))
    if missing:
        raise ValueError(f"Missing normalized execution columns: {missing}")
    if executions.empty:
        raise ValueError("At least one execution is required")
    if valuation_prices.empty:
        raise ValueError("At least one valuation price is required")

    frame = executions.loc[:, NORMALIZED_EXECUTION_COLUMNS].copy()
    null_columns = frame.columns[frame.isna().any()].tolist()
    if null_columns:
        raise ValueError(f"Normalized execution facts cannot be null: {null_columns}")

    frame["event_time"] = pd.to_datetime(frame["event_time"])
    frame["symbol"] = frame["symbol"].astype(str).str.strip()
    frame["side"] = frame["side"].astype(str).str.upper()
    frame["executed_quantity"] = pd.to_numeric(frame["executed_quantity"])
    frame["executed_price"] = pd.to_numeric(frame["executed_price"])
    frame["fee"] = pd.to_numeric(frame["fee"])

    numeric_facts = frame[["executed_quantity", "executed_price", "fee"]].to_numpy(dtype=float)
    if not np.isfinite(numeric_facts).all():
        raise ValueError("executed_quantity, executed_price, and fee must be finite")
    if frame["symbol"].eq("").any():
        raise ValueError("symbol cannot be empty")
    if frame["execution_id"].duplicated().any():
        raise ValueError("execution_id must be unique")
    if frame["event_time"].duplicated().any():
        raise ValueError(
            "This minimal from_orders adapter supports one execution per symbol/timestamp; "
            "sequence same-timestamp fills explicitly or use a flexible order function"
        )
    if set(frame["side"]).difference(_SIDE_SIGN):
        raise ValueError("side must be BUY or SELL")
    if (frame["executed_quantity"] <= 0).any():
        raise ValueError("executed_quantity must be positive")
    if (frame["executed_price"] <= 0).any():
        raise ValueError("executed_price must be positive")
    if (frame["fee"] < 0).any():
        raise ValueError("fee must be non-negative")

    symbols = frame["symbol"].drop_duplicates().tolist()
    if len(symbols) != 1:
        raise ValueError("This feasibility adapter accepts exactly one symbol")
    symbol = symbols[0]

    marks = pd.to_numeric(valuation_prices.copy()).astype(float)
    marks.index = pd.to_datetime(marks.index)
    marks = marks.sort_index()
    marks.name = symbol
    if marks.index.hasnans:
        raise ValueError("valuation_prices index cannot contain NaT")
    if marks.index.duplicated().any():
        raise ValueError("valuation_prices index must be unique")
    if not np.isfinite(marks.to_numpy()).all():
        raise ValueError("valuation_prices must be finite")
    if (marks <= 0).any():
        raise ValueError("valuation_prices must be positive")

    execution_times = pd.Index(frame["event_time"])
    missing_marks = execution_times.difference(marks.index)
    if not missing_marks.empty:
        raise ValueError(f"Missing valuation timestamps for executions: {missing_marks.tolist()}")

    aligned = frame.sort_values("event_time", kind="stable").set_index("event_time").reindex(marks.index)
    signed_size = (
        aligned["executed_quantity"] * aligned["side"].map(_SIDE_SIGN)
    ).fillna(0.0)
    order_price = aligned["executed_price"].fillna(marks)
    fixed_fees = aligned["fee"].fillna(0.0)

    inferred_frequency = pd.infer_freq(marks.index) if len(marks.index) >= 3 else None
    close_frame = marks.to_frame(name=symbol)
    size_frame = signed_size.to_frame(name=symbol)
    order_price_frame = order_price.to_frame(name=symbol)
    fixed_fees_frame = fixed_fees.to_frame(name=symbol)

    return vbt.Portfolio.from_orders(
        close=close_frame,
        size=size_frame,
        size_type="amount",
        direction=direction,
        price=order_price_frame,
        fees=0.0,
        fixed_fees=fixed_fees_frame,
        slippage=0.0,
        reject_prob=0.0,
        allow_partial=False,
        raise_reject=True,
        init_cash=init_cash,
        cash_sharing=False,
        freq=inferred_frequency,
    )
