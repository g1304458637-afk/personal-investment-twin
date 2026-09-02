"""Recorded explicit trading-fee evidence from two vectorbt replays.

This module does not estimate tax, slippage, spread, market impact, opportunity
cost, trading skill, or causal contribution.  It only removes the normalized
``fee`` facts while holding the other recorded executions fixed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import pandas as pd

from src.core.portfolio_replay import (
    PortfolioReplayError,
    replay_multi_asset_executions,
)


Comparison = Literal[
    "lower_than_zero_fee_baseline",
    "matched_zero_fee_baseline",
]
EvidenceStatus = Literal["complete", "insufficient_evidence"]

INCLUDED_COSTS: Final[tuple[str, ...]] = ("recorded_fee",)
EXCLUDED_COSTS: Final[tuple[str, ...]] = (
    "unrecorded_tax",
    "slippage",
    "bid_ask_spread",
    "market_impact",
    "opportunity_cost",
)
_ORDER_FACT_COLUMNS: Final[tuple[str, ...]] = (
    "Timestamp",
    "Column",
    "Side",
    "Size",
    "Price",
)


@dataclass(frozen=True, slots=True)
class FrictionEvidence:
    """Observed effect of recorded explicit fees over one replay window."""

    start_time: pd.Timestamp | None
    end_time: pd.Timestamp | None
    execution_count: int
    recorded_fee_total: float | None
    actual_end_value: float | None
    zero_recorded_fee_end_value: float | None
    comparison: Comparison | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    included_costs: tuple[str, ...]
    excluded_costs: tuple[str, ...]


def _insufficient(
    reason: str,
    execution_count: int,
    *,
    start_time: pd.Timestamp | None = None,
    end_time: pd.Timestamp | None = None,
    recorded_fee_total: float | None = None,
    actual_end_value: float | None = None,
    zero_recorded_fee_end_value: float | None = None,
) -> FrictionEvidence:
    return FrictionEvidence(
        start_time=start_time,
        end_time=end_time,
        execution_count=execution_count,
        recorded_fee_total=recorded_fee_total,
        actual_end_value=actual_end_value,
        zero_recorded_fee_end_value=zero_recorded_fee_end_value,
        comparison=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
        included_costs=INCLUDED_COSTS,
        excluded_costs=EXCLUDED_COSTS,
    )


def build_friction_evidence(
    executions: pd.DataFrame,
    valuation_prices: pd.DataFrame,
    *,
    init_cash: float,
) -> FrictionEvidence:
    """Compare actual recorded fees with the same executions at zero fee.

    Both portfolios are created by ``replay_multi_asset_executions``.  The
    counterfactual preserves DataFrame row order and every normalized execution
    field except ``fee``.
    """

    execution_count = len(executions) if isinstance(executions, pd.DataFrame) else 0
    if execution_count == 0:
        return _insufficient("At least one execution is required", execution_count)

    try:
        actual = replay_multi_asset_executions(
            executions,
            valuation_prices,
            init_cash=init_cash,
        )
    except PortfolioReplayError as exc:
        return _insufficient(f"Actual replay unavailable: {exc}", execution_count)

    zero_fee_executions = executions.copy(deep=True)
    zero_fee_executions.loc[:, "fee"] = 0.0
    try:
        zero_fee = replay_multi_asset_executions(
            zero_fee_executions,
            valuation_prices,
            init_cash=init_cash,
        )
    except PortfolioReplayError as exc:
        return _insufficient(
            f"Zero-recorded-fee replay unavailable: {exc}",
            execution_count,
        )

    actual_orders = actual.orders.records_readable.reset_index(drop=True)
    zero_fee_orders = zero_fee.orders.records_readable.reset_index(drop=True)
    if len(actual_orders) != execution_count or len(zero_fee_orders) != execution_count:
        return _insufficient(
            "Replay did not preserve the complete execution set",
            execution_count,
        )
    if not actual_orders.loc[:, _ORDER_FACT_COLUMNS].equals(
        zero_fee_orders.loc[:, _ORDER_FACT_COLUMNS]
    ):
        return _insufficient(
            "Actual and zero-recorded-fee replay execution facts differ",
            execution_count,
        )
    if not (zero_fee_orders["Fees"].to_numpy(dtype=float) == 0.0).all():
        return _insufficient(
            "Zero-recorded-fee replay contains a non-zero fee",
            execution_count,
        )

    recorded_fee_total = float(actual_orders["Fees"].sum())
    actual_end_value = float(actual.value().iloc[-1])
    zero_fee_end_value = float(zero_fee.value().iloc[-1])
    start_time = pd.Timestamp(actual.value().index[0])
    end_time = pd.Timestamp(actual.value().index[-1])
    result_values = np.array(
        [recorded_fee_total, actual_end_value, zero_fee_end_value],
        dtype=float,
    )
    if not np.isfinite(result_values).all() or recorded_fee_total < 0:
        return _insufficient(
            "vectorbt returned invalid friction evidence",
            execution_count,
            start_time=start_time,
            end_time=end_time,
        )

    values_match = math.isclose(
        actual_end_value,
        zero_fee_end_value,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )
    if actual_end_value > zero_fee_end_value and not values_match:
        return _insufficient(
            "Actual end value exceeds the otherwise identical zero-fee baseline",
            execution_count,
            start_time=start_time,
            end_time=end_time,
            recorded_fee_total=recorded_fee_total,
            actual_end_value=actual_end_value,
            zero_recorded_fee_end_value=zero_fee_end_value,
        )

    comparison: Comparison
    if values_match:
        comparison = "matched_zero_fee_baseline"
    else:
        comparison = "lower_than_zero_fee_baseline"

    return FrictionEvidence(
        start_time=start_time,
        end_time=end_time,
        execution_count=execution_count,
        recorded_fee_total=recorded_fee_total,
        actual_end_value=actual_end_value,
        zero_recorded_fee_end_value=zero_fee_end_value,
        comparison=comparison,
        evidence_status="complete",
        evidence_reason=None,
        included_costs=INCLUDED_COSTS,
        excluded_costs=EXCLUDED_COSTS,
    )
