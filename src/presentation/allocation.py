"""Position allocation block for the investments catalog.

Weights are deterministic Python computations over the episode snapshots the
runtime already rendered — never recomputed in the UI.  Open positions whose
market value is missing are counted (skipped_no_market_value) instead of
silently dropping out of the denominator: a missing mark must shrink the
reported coverage, not inflate the remaining weights.
"""
from __future__ import annotations

from typing import Any, Mapping

DEFINITION = (
    "权重 = 该持仓市值 ÷ 持仓总市值，仅统计当前持仓，不含现金；"
    "HHI 为各持仓权重的平方和（0–1，越大越集中）。"
    "缺少市值的持仓不计入分母，单独计数。"
)


def allocation_block(entries: list[Mapping[str, Any]]) -> dict[str, object]:
    """Build the allocation summary from rendered episode entries.

    ``entries`` items carry at least: instrument_id, display_name, status,
    quantity, market_value, valuation_at.  Deterministic ordering: value
    descending, then instrument_id ascending.
    """
    positions: list[dict[str, object]] = []
    skipped_no_market_value = 0
    for entry in entries:
        if entry.get("status") != "open":
            continue
        market_value = entry.get("market_value")
        if market_value is None:
            skipped_no_market_value += 1
            continue
        positions.append({
            "instrument_id": str(entry.get("instrument_id")),
            "display_name": str(entry.get("display_name") or entry.get("instrument_id")),
            "quantity": entry.get("quantity"),
            "market_value": float(market_value),
            "currency": entry.get("currency"),
            "as_of": entry.get("valuation_at"),
        })
    positions.sort(key=lambda item: (-item["market_value"], str(item["instrument_id"])))
    total = sum(float(item["market_value"]) for item in positions)
    weights = [item["market_value"] / total for item in positions] if total > 0 else None
    if weights is None:
        for item in positions:
            item["weight"] = None
        hhi = None
    else:
        for item, weight in zip(positions, weights):
            item["weight"] = weight
        hhi = sum(weight * weight for weight in weights)
    return {
        "positions": positions,
        "positions_value": total,
        "position_count": len(positions),
        "skipped_no_market_value": skipped_no_market_value,
        "hhi": hhi,
        "definition": DEFINITION,
    }
