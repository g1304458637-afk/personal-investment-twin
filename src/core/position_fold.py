"""Shared incremental position fold for vectorbt-equivalent state.

``advance_fold`` applies the engine's own position semantics to normalized
executions in canonical order, one pass: buys append ``size * price`` to a
per-symbol ``(entry_size_sum, entry_gross_sum)`` pair, partial sells rescale
BOTH sums by the remaining fraction, and a full exit resets them.  The ratio
``gross / size`` is then bit-identical to vectorbt's open-trade
"Avg Entry Price", and the running quantity is bit-identical to the
portfolio's asset row — a sequential blend or skipping the rescale each
differs in the last ulp (both wrong turns were found empirically via golden
builds; see commit 8a3ad20).
"""
from __future__ import annotations

import pandas as pd


def advance_fold(
    positions: dict[str, tuple[float, float, float]],
    frame: pd.DataFrame,
    start: int,
    count: int,
) -> None:
    """Extends ``positions`` from row ``start`` (inclusive) to ``count``.

    ``positions`` maps symbol -> (quantity, entry_size_sum, entry_gross_sum)
    and is updated in place; absent symbols start flat.  Callers own any
    caching/snapshot policy; the fold itself is stateless beyond the dict.
    """
    for i in range(start, count):
        row = frame.iloc[i]
        symbol = str(row["symbol"])
        size = float(row["executed_quantity"])
        price = float(row["executed_price"])
        quantity, entry_size_sum, entry_gross_sum = positions.get(symbol, (0.0, 0.0, 0.0))
        if str(row["side"]) == "BUY":
            positions[symbol] = (quantity + size, entry_size_sum + size, entry_gross_sum + size * price)
        else:
            remaining = quantity - size
            if remaining <= 1e-12:
                positions[symbol] = (0.0, 0.0, 0.0)
            else:
                fraction = (entry_size_sum - size) / entry_size_sum
                positions[symbol] = (remaining, entry_size_sum * fraction, entry_gross_sum * fraction)
