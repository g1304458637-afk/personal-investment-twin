"""Minimal vectorbt replay adapter used only by the feasibility experiment.

This module maps normalized execution facts to vectorbt inputs.  It deliberately
does not calculate positions, PnL, fees, or returns itself.
"""

from __future__ import annotations

import pandas as pd
import vectorbt as vbt

from src.core.portfolio_replay import replay_multi_asset_executions_with_links


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
    """Replay one-symbol feasibility fixtures through the shared flexible core."""

    symbols = executions["symbol"].drop_duplicates().tolist()
    if len(symbols) != 1:
        raise ValueError("This feasibility adapter accepts exactly one symbol")
    symbol = symbols[0]
    if direction != "longonly":
        raise ValueError("This feasibility adapter supports longonly direction")
    marks = valuation_prices.copy()
    marks.name = symbol
    inferred_frequency = (
        pd.infer_freq(pd.DatetimeIndex(marks.index)) if len(marks.index) >= 3 else None
    )
    return replay_multi_asset_executions_with_links(
        executions,
        marks.to_frame(name=symbol),
        init_cash=init_cash,
        _cash_sharing=False,
        _freq=inferred_frequency,
    ).portfolio
