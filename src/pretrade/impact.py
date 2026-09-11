"""Deterministic pre-trade state comparison over the existing vectorbt replay.

This module does not predict prices or returns and does not implement portfolio
accounting.  It creates one hypothetical normalized execution, delegates both
states to the existing replay/HHI paths, and exposes their factual difference.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from src.behavior.portfolio_concentration import (
    PortfolioConcentrationEvidence,
    build_portfolio_concentration_evidence,
)
from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay
from src.cohort.engine import PERCENTILE_METHOD, build_peer_benchmark_results
from src.cohort.models import CohortDefinition, CohortMember, PeerMetricValue
from src.cohort.synthetic import (
    build_synthetic_peer_metric_values,
    generate_synthetic_cohort_accounts,
    synthetic_cohort_definition,
)
from src.evidence.adapters import adapt_portfolio_concentration_evidence
from src.history.metric_series import HistoricalMetricSeries


SimulationStatus = Literal["complete", "rejected", "insufficient_evidence"]
METHOD_ID = "pretrade_hhi_impact_v1"
METHOD_VERSION = "1"


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ProposedTrade:
    """A user-supplied hypothetical execution, never a brokerage order."""

    subject_id: str
    proposed_time: pd.Timestamp
    symbol: str
    side: str
    quantity: float
    execution_price: float
    fees: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _required_text(self.subject_id, "subject_id"))
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        object.__setattr__(self, "side", _required_text(self.side, "side").upper())
        timestamp = pd.Timestamp(self.proposed_time)
        if pd.isna(timestamp):
            raise ValueError("proposed_time cannot be NaT")
        object.__setattr__(self, "proposed_time", timestamp)
        for name in ("quantity", "execution_price", "fees"):
            try:
                value = float(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise TypeError(f"{name} must be numeric") from exc
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AllocationComponent:
    """Replay values, with account and existing HHI denominators kept separate.

    This is a direct holding, not an inferred fund constituent or industry.
    Cash has no security-only weight. Names are never inferred from symbols.
    """

    symbol: str | None
    kind: Literal["security", "cash"]
    value: float
    account_weight: float
    security_weight: float | None


@dataclass(frozen=True, slots=True)
class PortfolioImpactState:
    """State read from vectorbt; symbol_weight uses total portfolio value.

    ``valuation_price`` is vectorbt's final ``close``/mark for the target
    symbol. It is not the proposed execution price and is never forecast.
    """

    cash: float
    portfolio_value: float
    symbol_quantity: float
    symbol_weight: float
    valuation_price: float
    hhi: float
    active_assets: int
    allocations: tuple[AllocationComponent, ...] = ()
    valuation_observation_date: str | None = None


@dataclass(frozen=True, slots=True)
class TradeImpactDelta:
    cash: float
    symbol_weight: float
    hhi: float


@dataclass(frozen=True, slots=True)
class SelfHhiContext:
    historical_hhi_median: float
    current_hhi: float
    proposed_hhi: float
    historical_observation_count: int
    history_method_id: str


@dataclass(frozen=True, slots=True)
class PeerHhiContext:
    cohort_id: str
    cohort_n: int
    metric_n: int
    cohort_hhi_median: float
    current_percentile: float
    proposed_percentile: float
    percentile_method: str


@dataclass(frozen=True, slots=True)
class TradeImpact:
    proposed_trade: ProposedTrade
    before: PortfolioImpactState | None
    after: PortfolioImpactState | None
    delta: TradeImpactDelta | None
    self_context: SelfHhiContext | None
    peer_context: PeerHhiContext | None
    simulation_status: SimulationStatus
    simulation_reason: str | None
    data_tier: Literal["synthetic"]
    limitations: tuple[str, ...]
    hypothetical_execution_id: str | None = None
    before_hhi_evidence_id: str | None = None
    after_hhi_evidence_id: str | None = None
    method_id: str = METHOD_ID
    method_version: str = METHOD_VERSION


LIMITATIONS = (
    "This is a deterministic hypothetical execution, not a brokerage order or recommendation.",
    "No future price, expected return, or trade outcome is predicted.",
    "Symbol weight is marked from vectorbt asset value divided by total portfolio value.",
    "Peer context uses a deterministic synthetic cohort and does not represent real investors.",
)


def _result(
    proposed_trade: ProposedTrade,
    status: SimulationStatus,
    reason: str | None,
    *,
    before: PortfolioImpactState | None = None,
    after: PortfolioImpactState | None = None,
    delta: TradeImpactDelta | None = None,
    self_context: SelfHhiContext | None = None,
    peer_context: PeerHhiContext | None = None,
    before_hhi_evidence_id: str | None = None,
    after_hhi_evidence_id: str | None = None,
) -> TradeImpact:
    return TradeImpact(
        proposed_trade=proposed_trade,
        before=before,
        after=after,
        delta=delta,
        self_context=self_context,
        peer_context=peer_context,
        simulation_status=status,
        simulation_reason=reason,
        data_tier="synthetic",
        limitations=LIMITATIONS,
        hypothetical_execution_id=_hypothetical_execution_id(proposed_trade),
        before_hhi_evidence_id=before_hhi_evidence_id,
        after_hhi_evidence_id=after_hhi_evidence_id,
    )


def _trade_rejection_reason(proposed_trade: ProposedTrade) -> str | None:
    if proposed_trade.side not in {"BUY", "SELL"}:
        return "Only BUY and SELL are supported; short trades are rejected"
    if not math.isfinite(proposed_trade.quantity) or proposed_trade.quantity <= 0:
        return "Proposed quantity must be finite and positive"
    if not math.isfinite(proposed_trade.execution_price) or proposed_trade.execution_price <= 0:
        return "Proposed execution price must be finite and positive"
    if not math.isfinite(proposed_trade.fees) or proposed_trade.fees < 0:
        return "Proposed fees must be finite and non-negative"
    return None


def _window_inputs(
    proposed_trade: ProposedTrade,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(executions, pd.DataFrame) or "event_time" not in executions.columns:
        raise ValueError("executions.event_time is required")
    if not isinstance(market_prices, pd.DataFrame) or "date" not in market_prices.columns:
        raise ValueError("market_prices.date is required")
    execution_times = pd.to_datetime(executions["event_time"], errors="raise")
    price_times = pd.to_datetime(market_prices["date"], errors="raise")
    return (
        executions.loc[execution_times < proposed_trade.proposed_time].copy(),
        market_prices.loc[price_times < proposed_trade.proposed_time].copy(),
    )


def _hypothetical_execution_id(proposed_trade: ProposedTrade) -> str:
    return (
        f"hypothetical:{proposed_trade.subject_id}:"
        f"{proposed_trade.proposed_time.isoformat()}:{proposed_trade.symbol}"
    )


def _hypothetical_executions(
    proposed_trade: ProposedTrade,
    prior_executions: pd.DataFrame,
) -> pd.DataFrame:
    identifier = _hypothetical_execution_id(proposed_trade)
    row = pd.DataFrame(
        [
            {
                "event_time": proposed_trade.proposed_time,
                "symbol": proposed_trade.symbol,
                "side": proposed_trade.side,
                "executed_quantity": proposed_trade.quantity,
                "executed_price": proposed_trade.execution_price,
                "fee": proposed_trade.fees,
                "order_id": identifier,
                "execution_id": identifier,
            }
        ]
    )
    return pd.concat([prior_executions, row], ignore_index=True, sort=False)


def _state_from_replay(
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    symbol: str,
    init_cash: float,
    hhi: PortfolioConcentrationEvidence,
) -> PortfolioImpactState:
    if hhi.evidence_status != "complete" or hhi.hhi is None:
        raise BehaviorReplayError(hhi.evidence_reason or "HHI evidence is insufficient")
    context = prepare_behavior_replay(executions, market_prices, init_cash=init_cash)
    cash = float(context.portfolio.cash().iloc[-1])
    portfolio_value = float(context.portfolio.value().iloc[-1])
    assets = context.portfolio.assets().iloc[-1]
    asset_values = context.portfolio.asset_value(group_by=False).iloc[-1]
    symbol_quantity = float(assets.get(symbol, 0.0))
    symbol_asset_value = float(asset_values.get(symbol, 0.0))
    try:
        valuation_price = float(context.portfolio.close[symbol].iloc[-1])
    except KeyError as exc:
        raise BehaviorReplayError(
            f"Missing market prices for target symbol: {symbol}"
        ) from exc
    values = (
        cash,
        portfolio_value,
        symbol_quantity,
        symbol_asset_value,
        valuation_price,
        float(hhi.hhi),
    )
    if not all(math.isfinite(value) for value in values) or portfolio_value <= 0:
        raise BehaviorReplayError("vectorbt state is not finite and positive")
    return PortfolioImpactState(
        cash=cash,
        portfolio_value=portfolio_value,
        symbol_quantity=symbol_quantity,
        symbol_weight=symbol_asset_value / portfolio_value,
        valuation_price=valuation_price,
        hhi=float(hhi.hhi),
        active_assets=hhi.active_asset_count,
        allocations=(
            AllocationComponent(None, "cash", cash, cash / portfolio_value, None),
            *(AllocationComponent(
                component.symbol,
                "security",
                float(asset_values[component.symbol]),
                float(asset_values[component.symbol]) / portfolio_value,
                component.weight,
            ) for component in sorted(hhi.weight_components, key=lambda item: item.symbol)),
        ),
        valuation_observation_date=hhi.as_of_time.date().isoformat(),
    )


def _self_context(
    proposed_trade: ProposedTrade,
    hhi_history: HistoricalMetricSeries,
    *,
    current_hhi: float,
    proposed_hhi: float,
) -> SelfHhiContext:
    if hhi_history.subject_id != proposed_trade.subject_id:
        raise ValueError("HHI history must belong to the proposed trade subject")
    if hhi_history.metric_id != "portfolio_concentration_hhi":
        raise ValueError("Self context requires portfolio HHI history")
    if hhi_history.data_tier != "synthetic":
        raise ValueError("Pre-trade v1 supports only synthetic HHI history")
    values = tuple(
        float(point.value)
        for point in hhi_history.points
        if point.as_of <= proposed_trade.proposed_time
        and point.evidence_status == "complete"
        and point.value is not None
        and math.isfinite(point.value)
    )
    if not values:
        raise ValueError("No valid historical HHI observations exist before the proposed trade")
    median = float(np.quantile(np.asarray(values, dtype=float), 0.5, method="linear"))
    return SelfHhiContext(
        historical_hhi_median=median,
        current_hhi=current_hhi,
        proposed_hhi=proposed_hhi,
        historical_observation_count=len(values),
        history_method_id=hhi_history.method_id,
    )


def _hhi_peer_result(
    *,
    subject_id: str,
    hhi: float,
    source_evidence_id: str,
    definition: CohortDefinition,
    members: tuple[CohortMember, ...],
    peer_hhi_values: tuple[PeerMetricValue, ...],
):
    subject_metric = PeerMetricValue(
        subject_id=subject_id,
        metric_id="portfolio_concentration_hhi",
        value=hhi,
        evidence_status="complete",
        source_evidence_id=source_evidence_id,
        as_of=definition.observation_end,
    )
    return build_peer_benchmark_results(
        definition,
        members,
        peer_hhi_values,
        (subject_metric,),
        subject_id=subject_id,
    )[0]


def simulate_trade_impact(
    proposed_trade: ProposedTrade,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
    hhi_history: HistoricalMetricSeries,
    cohort_definition: CohortDefinition,
    peer_members: Iterable[CohortMember],
    peer_metric_values: Iterable[PeerMetricValue],
    calculation_code_version: str,
    include_peer_context: bool = True,
) -> TradeImpact:
    """Replay current and hypothetical states without mutating canonical facts."""

    rejection = _trade_rejection_reason(proposed_trade)
    if rejection is not None:
        return _result(proposed_trade, "rejected", rejection)
    if include_peer_context and proposed_trade.proposed_time.normalize() != cohort_definition.observation_end:
        return _result(
            proposed_trade,
            "insufficient_evidence",
            "Proposed trade date is not aligned to the synthetic cohort observation end",
        )
    if not include_peer_context and (
        not hhi_history.points
        or proposed_trade.proposed_time.normalize()
        != hhi_history.points[-1].as_of.normalize()
    ):
        return _result(
            proposed_trade,
            "insufficient_evidence",
            "Proposed trade date is not aligned to the registered account source as of",
        )

    try:
        prior_executions, price_prefix = _window_inputs(
            proposed_trade,
            executions,
            market_prices,
        )
        if (
            proposed_trade.side == "SELL"
            and proposed_trade.symbol not in set(prior_executions["symbol"])
        ):
            return _result(
                proposed_trade,
                "rejected",
                "Short positions are unsupported; the subject holds no long quantity",
            )
        before_hhi = build_portfolio_concentration_evidence(
            prior_executions,
            price_prefix,
            init_cash=init_cash,
        )
        before = _state_from_replay(
            prior_executions,
            price_prefix,
            symbol=proposed_trade.symbol,
            init_cash=init_cash,
            hhi=before_hhi,
        )
    except (BehaviorReplayError, KeyError, TypeError, ValueError) as exc:
        return _result(proposed_trade, "insufficient_evidence", str(exc))

    if proposed_trade.side == "SELL":
        if before.symbol_quantity <= 1e-12:
            return _result(
                proposed_trade,
                "rejected",
                "Short positions are unsupported; the subject holds no long quantity",
                before=before,
            )
        if proposed_trade.quantity > before.symbol_quantity + 1e-12:
            return _result(
                proposed_trade,
                "rejected",
                "Proposed SELL quantity exceeds the existing long position",
                before=before,
            )

    hypothetical = _hypothetical_executions(proposed_trade, prior_executions)
    try:
        after_hhi = build_portfolio_concentration_evidence(
            hypothetical,
            price_prefix,
            init_cash=init_cash,
        )
        after = _state_from_replay(
            hypothetical,
            price_prefix,
            symbol=proposed_trade.symbol,
            init_cash=init_cash,
            hhi=after_hhi,
        )
    except (BehaviorReplayError, KeyError, TypeError, ValueError) as exc:
        reason = str(exc)
        if proposed_trade.side == "BUY" and (
            "Not enough cash to long" in reason
            or "Not enough cash to cover fees" in reason
            or "Final size is less than requested" in reason
        ):
            return _result(
                proposed_trade,
                "rejected",
                "Proposed BUY cannot be executed because cash is insufficient",
                before=before,
            )
        return _result(proposed_trade, "insufficient_evidence", reason, before=before)

    try:
        before_record = adapt_portfolio_concentration_evidence(
            before_hhi,
            subject_id=proposed_trade.subject_id,
            data_tier="synthetic",
            calculation_code_version=calculation_code_version,
        )
        after_record = adapt_portfolio_concentration_evidence(
            after_hhi,
            subject_id=proposed_trade.subject_id,
            data_tier="synthetic",
            calculation_code_version=calculation_code_version,
        )
        if not include_peer_context:
            self_context = _self_context(
                proposed_trade,
                hhi_history,
                current_hhi=before.hhi,
                proposed_hhi=after.hhi,
            )
            return _result(
                proposed_trade,
                "complete",
                None,
                before=before,
                after=after,
                delta=TradeImpactDelta(
                    cash=after.cash - before.cash,
                    symbol_weight=after.symbol_weight - before.symbol_weight,
                    hhi=after.hhi - before.hhi,
                ),
                self_context=self_context,
                before_hhi_evidence_id=before_record.evidence_id,
                after_hhi_evidence_id=after_record.evidence_id,
            )
        members = tuple(peer_members)
        peer_hhi_values = tuple(
            item
            for item in peer_metric_values
            if item.metric_id == "portfolio_concentration_hhi"
        )
        current_peer = _hhi_peer_result(
            subject_id=proposed_trade.subject_id,
            hhi=before.hhi,
            source_evidence_id=before_record.evidence_id,
            definition=cohort_definition,
            members=members,
            peer_hhi_values=peer_hhi_values,
        )
        proposed_peer = _hhi_peer_result(
            subject_id=proposed_trade.subject_id,
            hhi=after.hhi,
            source_evidence_id=after_record.evidence_id,
            definition=cohort_definition,
            members=members,
            peer_hhi_values=peer_hhi_values,
        )
        if (
            current_peer.benchmark_status != "complete"
            or proposed_peer.benchmark_status != "complete"
            or current_peer.median is None
            or current_peer.percentile is None
            or proposed_peer.percentile is None
            or current_peer.median != proposed_peer.median
            or current_peer.metric_n != proposed_peer.metric_n
            or current_peer.quantile_method != proposed_peer.quantile_method
            or current_peer.percentile_method != PERCENTILE_METHOD
            or proposed_peer.percentile_method != PERCENTILE_METHOD
        ):
            raise ValueError("Peer HHI context is insufficient or inconsistent")
        self_context = _self_context(
            proposed_trade,
            hhi_history,
            current_hhi=before.hhi,
            proposed_hhi=after.hhi,
        )
        peer_context = PeerHhiContext(
            cohort_id=current_peer.cohort_id,
            cohort_n=current_peer.cohort_n,
            metric_n=current_peer.metric_n,
            cohort_hhi_median=current_peer.median,
            current_percentile=current_peer.percentile,
            proposed_percentile=proposed_peer.percentile,
            percentile_method=current_peer.percentile_method,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _result(
            proposed_trade,
            "insufficient_evidence",
            str(exc),
            before=before,
            after=after,
        )

    return _result(
        proposed_trade,
        "complete",
        None,
        before=before,
        after=after,
        delta=TradeImpactDelta(
            cash=after.cash - before.cash,
            symbol_weight=after.symbol_weight - before.symbol_weight,
            hhi=after.hhi - before.hhi,
        ),
        self_context=self_context,
        peer_context=peer_context,
        before_hhi_evidence_id=before_record.evidence_id,
        after_hhi_evidence_id=after_record.evidence_id,
    )


def simulate_synthetic_trade_impact(
    proposed_trade: ProposedTrade,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    *,
    init_cash: float,
    hhi_history: HistoricalMetricSeries,
    calculation_code_version: str,
) -> TradeImpact:
    """Run v1 against the same fixed 72-account synthetic cohort as Compare."""

    definition = synthetic_cohort_definition()
    accounts = generate_synthetic_cohort_accounts(
        market_prices,
        definition=definition,
        init_cash=init_cash,
    )
    peer_values = build_synthetic_peer_metric_values(
        accounts,
        calculation_code_version=calculation_code_version,
    )
    return simulate_trade_impact(
        proposed_trade,
        executions,
        market_prices,
        init_cash=init_cash,
        hhi_history=hhi_history,
        cohort_definition=definition,
        peer_members=(account.member for account in accounts),
        peer_metric_values=peer_values,
        calculation_code_version=calculation_code_version,
    )
