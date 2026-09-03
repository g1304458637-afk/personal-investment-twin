"""Thin adapters from frozen financial evidence into ``EvidenceRecord``."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.attribution.decision_evidence_statistics import DecisionEvidenceStatistics
from src.attribution.exit_timing_evidence import ExitTimingEvidence
from src.attribution.friction_evidence import FrictionEvidence
from src.attribution.selection_evidence import (
    BenchmarkProvenance,
    IndustryProvenance,
    PriceProvenance,
    SelectionEvidence,
)
from src.attribution.sizing_evidence import SizingDecisionEvidence
from src.behavior.disposition_effect import DispositionEffectEvidence
from src.behavior.loss_averaging import LossAveragingEvidence
from src.behavior.portfolio_concentration import PortfolioConcentrationEvidence
from src.behavior.turnover_intensity import TurnoverIntensityEvidence
from src.evidence.contracts import (
    DataTier,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceStatus,
    create_evidence_record,
)
from src.evidence.registry import (
    EXIT_METHOD_ID,
    FRICTION_METHOD_ID,
    METHOD_VERSION_V1,
    SELECTION_METHOD_ID,
    SIZING_METHOD_ID,
    STATISTICS_METHOD_ID,
    get_method_definition,
)


def _iso(value: pd.Timestamp | None) -> str | None:
    return pd.Timestamp(value).isoformat() if value is not None else None


def _status(value: str) -> EvidenceStatus:
    if value == "available":
        return "complete"
    if value in {"complete", "partial", "insufficient_evidence", "experimental"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported source evidence status: {value!r}")


def _record(
    *,
    subject_id: str,
    metric_id: str,
    evidence_kind: str,
    method_id: str,
    observation_start: pd.Timestamp | None,
    observation_end: pd.Timestamp | None,
    as_of: pd.Timestamp | None,
    value: int | float | str | bool | None,
    numerator: int | float | None,
    denominator: int | float | str | None,
    observation_count: int | None,
    ci_lower: float | None,
    ci_upper: float | None,
    evidence_status: str,
    evidence_reason: str | None,
    provenance: tuple[EvidenceProvenance, ...],
    data_tier: DataTier,
    calculation_code_version: str,
    attributes: Mapping[str, object],
    identity_attributes: Mapping[str, object],
    additional_limitations: tuple[str, ...] = (),
) -> EvidenceRecord:
    method = get_method_definition(method_id, METHOD_VERSION_V1)
    limitations = tuple(
        dict.fromkeys((*method.limitations, *additional_limitations))
    )
    return create_evidence_record(
        subject_id=subject_id,
        metric_id=metric_id,
        evidence_kind=evidence_kind,
        method_id=method.method_id,
        method_version=method.method_version,
        observation_start=observation_start,
        observation_end=observation_end,
        as_of=as_of,
        value=value,
        numerator=numerator,
        denominator=denominator,
        observation_count=observation_count,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        evidence_status=_status(evidence_status),
        evidence_reason=evidence_reason,
        provenance=provenance,
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        limitations=limitations,
        attributes=attributes,
        identity_attributes=identity_attributes,
    )


def adapt_price_provenance(value: PriceProvenance) -> EvidenceProvenance:
    return EvidenceProvenance(
        source_type="price_series",
        source_name=value.data_source,
        data_version=value.data_version,
        as_of=value.as_of,
        price_type=value.price_type,
        is_synthetic=value.is_synthetic,
        instrument=value.instrument,
    )


def adapt_benchmark_provenance(value: BenchmarkProvenance) -> EvidenceProvenance:
    return EvidenceProvenance(
        source_type="benchmark_price_series",
        source_name=value.data_source,
        data_version=value.data_version,
        as_of=value.as_of,
        price_type=value.price_type,
        is_synthetic=value.is_synthetic,
        benchmark_id=value.benchmark_id,
        attributes={
            "benchmark_name": value.benchmark_name,
            "benchmark_type": value.benchmark_type,
        },
    )


def adapt_industry_provenance(value: IndustryProvenance) -> EvidenceProvenance:
    return EvidenceProvenance(
        source_type="industry_classification",
        source_name=value.data_source,
        data_version=value.data_version,
        as_of=value.as_of,
        price_type=None,
        is_synthetic=value.is_synthetic,
        source_id=value.industry_id,
        attributes={
            "industry_name": value.industry_name,
            "classification": value.classification,
        },
    )


def _price_provenance(values: tuple[PriceProvenance, ...]) -> tuple[EvidenceProvenance, ...]:
    return tuple(adapt_price_provenance(item) for item in values)


def adapt_turnover_intensity_evidence(
    evidence: TurnoverIntensityEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    daily = [
        {
            "observation_date": _iso(item.observation_date),
            "traded_value": item.traded_value,
            "portfolio_value": item.portfolio_value,
            "turnover": item.turnover,
        }
        for item in evidence.daily_turnover
    ]
    start = evidence.daily_turnover[0].observation_date if evidence.daily_turnover else None
    end = evidence.daily_turnover[-1].observation_date if evidence.daily_turnover else None
    attributes = {
        "daily_turnover": daily,
        "observation_days": evidence.observation_days,
        "total_traded_value": evidence.total_traded_value,
        "synthetic_provenance_present": evidence.synthetic_provenance_present,
    }
    return _record(
        subject_id=subject_id,
        metric_id="mean_daily_turnover",
        evidence_kind="behavior_evidence",
        method_id=evidence.method_id,
        observation_start=start,
        observation_end=end,
        as_of=end,
        value=evidence.mean_daily_turnover,
        numerator=evidence.total_traded_value,
        denominator=evidence.denominator,
        observation_count=evidence.observation_count,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=_price_provenance(evidence.provenance),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes={
            "daily_turnover": daily,
            "observation_days": evidence.observation_days,
        },
        additional_limitations=(evidence.limitation,),
    )


def adapt_portfolio_concentration_evidence(
    evidence: PortfolioConcentrationEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    attributes = {
        "active_asset_count": evidence.active_asset_count,
        "top1_weight": evidence.top1_weight,
        "top3_weight": evidence.top3_weight,
        "weight_components": [
            {
                "symbol": item.symbol,
                "asset_value": item.asset_value,
                "weight": item.weight,
            }
            for item in evidence.weight_components
        ],
        "synthetic_provenance_present": evidence.synthetic_provenance_present,
    }
    return _record(
        subject_id=subject_id,
        metric_id="portfolio_concentration_hhi",
        evidence_kind="behavior_evidence",
        method_id=evidence.method_id,
        observation_start=evidence.as_of_time,
        observation_end=evidence.as_of_time,
        as_of=evidence.as_of_time,
        value=evidence.hhi,
        numerator=None,
        denominator=None,
        observation_count=evidence.observation_count,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=_price_provenance(evidence.provenance),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes={
            "active_asset_count": evidence.active_asset_count,
            "top1_weight": evidence.top1_weight,
            "top3_weight": evidence.top3_weight,
            "weight_components": attributes["weight_components"],
        },
        additional_limitations=(evidence.limitation,),
    )


def adapt_disposition_effect_evidence(
    evidence: DispositionEffectEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    attributes = {
        "realized_gains": evidence.realized_gains,
        "paper_gains": evidence.paper_gains,
        "realized_losses": evidence.realized_losses,
        "paper_losses": evidence.paper_losses,
        "neutral_observations": evidence.neutral_observations,
        "pgr": evidence.pgr,
        "plr": evidence.plr,
        "eligible_sale_events": evidence.eligible_sale_events,
        "synthetic_provenance_present": evidence.synthetic_provenance_present,
    }
    identity_attributes = {
        key: attributes[key]
        for key in (
            "realized_gains",
            "paper_gains",
            "realized_losses",
            "paper_losses",
            "neutral_observations",
            "pgr",
            "plr",
            "eligible_sale_events",
        )
    }
    return _record(
        subject_id=subject_id,
        metric_id="disposition_effect",
        evidence_kind="behavior_evidence",
        method_id=evidence.method_id,
        observation_start=None,
        observation_end=None,
        as_of=None,
        value=evidence.disposition_effect,
        numerator=None,
        denominator=None,
        observation_count=evidence.observation_count,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=_price_provenance(evidence.provenance),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=identity_attributes,
        additional_limitations=(evidence.limitation,),
    )


def adapt_loss_averaging_evidence(
    evidence: LossAveragingEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    events = [
        {
            "event_time": _iso(item.event_time),
            "symbol": item.symbol,
            "pre_trade_position": item.pre_trade_position,
            "pre_trade_avg_cost": item.pre_trade_avg_cost,
            "execution_price": item.execution_price,
            "added_quantity": item.added_quantity,
            "eligible_event": item.eligible_event,
            "event_detected": item.event_detected,
            "execution_id": item.execution_id,
        }
        for item in evidence.events
    ]
    event_times = [item.event_time for item in evidence.events]
    start = min(event_times) if event_times else None
    end = max(event_times) if event_times else None
    attributes = {
        "events": events,
        "eligible_add_events": evidence.eligible_add_events,
        "loss_averaging_events": evidence.loss_averaging_events,
        "synthetic_provenance_present": evidence.synthetic_provenance_present,
    }
    return _record(
        subject_id=subject_id,
        metric_id="loss_averaging_event_rate",
        evidence_kind="behavior_evidence",
        method_id=evidence.method_id,
        observation_start=start,
        observation_end=end,
        as_of=end,
        value=evidence.event_rate,
        numerator=evidence.loss_averaging_events,
        denominator=evidence.eligible_add_events,
        observation_count=evidence.observation_count,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=_price_provenance(evidence.provenance),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes={
            "events": events,
            "eligible_add_events": evidence.eligible_add_events,
        },
        additional_limitations=(evidence.limitation,),
    )


def adapt_selection_evidence(
    evidence: SelectionEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    provenance: list[EvidenceProvenance] = []
    if evidence.asset_provenance is not None:
        provenance.append(adapt_price_provenance(evidence.asset_provenance))
    if evidence.industry_provenance is not None:
        provenance.append(adapt_industry_provenance(evidence.industry_provenance))
    provenance.extend(
        adapt_benchmark_provenance(item) for item in evidence.benchmark_provenance
    )
    attributes = {
        "episode_id": evidence.episode_id,
        "symbol": evidence.symbol,
        "market_benchmark_id": evidence.market_benchmark_id,
        "market_benchmark_name": evidence.market_benchmark_name,
        "market_benchmark_return": evidence.market_benchmark_return,
        "market_comparison": evidence.market_comparison,
        "industry_id": evidence.industry_id,
        "industry_name": evidence.industry_name,
        "industry_as_of_date": _iso(evidence.industry_as_of_date),
        "industry_benchmark_id": evidence.industry_benchmark_id,
        "industry_benchmark_name": evidence.industry_benchmark_name,
        "industry_benchmark_return": evidence.industry_benchmark_return,
        "industry_comparison": evidence.industry_comparison,
    }
    identity_attributes = {
        key: attributes[key]
        for key in (
            "episode_id",
            "symbol",
            "market_benchmark_id",
            "market_benchmark_return",
            "market_comparison",
            "industry_id",
            "industry_as_of_date",
            "industry_benchmark_id",
            "industry_benchmark_return",
            "industry_comparison",
        )
    }
    return _record(
        subject_id=subject_id,
        metric_id="selection_episode_asset_return",
        evidence_kind="decision_evidence",
        method_id=SELECTION_METHOD_ID,
        observation_start=evidence.start_time,
        observation_end=evidence.end_time,
        as_of=evidence.end_time,
        value=evidence.asset_return,
        numerator=None,
        denominator=None,
        observation_count=None,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=tuple(provenance),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=identity_attributes,
    )


def adapt_sizing_evidence(
    evidence: SizingDecisionEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    attributes = {
        "active_assets": list(evidence.active_assets),
        "actual_weights": dict(evidence.actual_weights),
        "baseline_weights": dict(evidence.baseline_weights),
        "risky_exposure": evidence.risky_exposure,
        "actual_start_value": evidence.actual_start_value,
        "baseline_start_value": evidence.baseline_start_value,
        "actual_end_value": evidence.actual_end_value,
        "baseline_end_value": evidence.baseline_end_value,
        "comparison": evidence.comparison,
    }
    return _record(
        subject_id=subject_id,
        metric_id="sizing_equal_weight_comparison",
        evidence_kind="decision_evidence",
        method_id=SIZING_METHOD_ID,
        observation_start=evidence.decision_time,
        observation_end=evidence.interval_end_time,
        as_of=evidence.interval_end_time or evidence.decision_time,
        value=evidence.comparison,
        numerator=None,
        denominator=None,
        observation_count=None,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=(),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=attributes,
    )


def adapt_exit_timing_evidence(
    evidence: ExitTimingEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    provenance = (
        (adapt_price_provenance(evidence.provenance),)
        if evidence.provenance is not None
        else ()
    )
    attributes = {
        "episode_id": evidence.episode_id,
        "symbol": evidence.symbol,
        "actual_exit_price": evidence.actual_exit_price,
        "policy_id": evidence.policy_id,
        "policy_sessions": evidence.policy_sessions,
        "counterfactual_exit_time": _iso(evidence.counterfactual_exit_time),
        "exit_session_market_price": evidence.exit_session_market_price,
        "counterfactual_exit_price": evidence.counterfactual_exit_price,
        "comparison": evidence.comparison,
        "counterfactual_notice": evidence.counterfactual_notice,
        "window_prices": [
            {
                "observation_time": _iso(item.observation_time),
                "price": item.price,
            }
            for item in evidence.window_prices
        ],
    }
    identity_attributes = {
        key: attributes[key]
        for key in (
            "episode_id",
            "symbol",
            "actual_exit_price",
            "policy_id",
            "policy_sessions",
            "counterfactual_exit_time",
            "exit_session_market_price",
            "counterfactual_exit_price",
            "comparison",
            "window_prices",
        )
    }
    return _record(
        subject_id=subject_id,
        metric_id="exit_timing_post_exit_asset_return",
        evidence_kind="decision_evidence",
        method_id=evidence.policy_id or EXIT_METHOD_ID,
        observation_start=evidence.actual_exit_time,
        observation_end=evidence.counterfactual_exit_time,
        as_of=evidence.counterfactual_exit_time or evidence.actual_exit_time,
        value=evidence.post_exit_asset_return,
        numerator=None,
        denominator=None,
        observation_count=None,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=provenance,
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=identity_attributes,
        additional_limitations=(evidence.counterfactual_notice,),
    )


def adapt_friction_evidence(
    evidence: FrictionEvidence,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    attributes = {
        "recorded_fee_total": evidence.recorded_fee_total,
        "actual_end_value": evidence.actual_end_value,
        "zero_recorded_fee_end_value": evidence.zero_recorded_fee_end_value,
        "comparison": evidence.comparison,
        "included_costs": list(evidence.included_costs),
        "excluded_costs": list(evidence.excluded_costs),
    }
    identity_attributes = {
        key: attributes[key]
        for key in (
            "recorded_fee_total",
            "actual_end_value",
            "zero_recorded_fee_end_value",
            "comparison",
        )
    }
    return _record(
        subject_id=subject_id,
        metric_id="recorded_trading_friction_comparison",
        evidence_kind="decision_evidence",
        method_id=FRICTION_METHOD_ID,
        observation_start=evidence.start_time,
        observation_end=evidence.end_time,
        as_of=evidence.end_time,
        value=evidence.comparison,
        numerator=None,
        denominator=None,
        observation_count=evidence.execution_count,
        ci_lower=None,
        ci_upper=None,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=(),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=identity_attributes,
    )


def adapt_decision_evidence_statistics(
    evidence: DecisionEvidenceStatistics,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    attributes = {
        "decision_type": evidence.decision_type,
        "total_observations": evidence.total_observations,
        "valid_n": evidence.valid_n,
        "insufficient_n": evidence.insufficient_n,
        "positive_n": evidence.positive_n,
        "negative_n": evidence.negative_n,
        "matched_n": evidence.matched_n,
        "interval_method": evidence.interval_method,
        "date_span_days": evidence.date_span_days,
        "source_evidence_status": evidence.evidence_status,
        "hit_rate_definition": evidence.hit_rate_definition,
        "limitation_notice": evidence.limitation_notice,
    }
    identity_attributes = {
        key: attributes[key]
        for key in (
            "decision_type",
            "total_observations",
            "valid_n",
            "insufficient_n",
            "positive_n",
            "negative_n",
            "matched_n",
            "interval_method",
        )
    }
    return _record(
        subject_id=subject_id,
        metric_id=f"{evidence.decision_type}_decision_hit_rate",
        evidence_kind="aggregate_statistics",
        method_id=STATISTICS_METHOD_ID,
        observation_start=evidence.first_observation_time,
        observation_end=evidence.last_observation_time,
        as_of=evidence.last_observation_time,
        value=evidence.hit_rate,
        numerator=evidence.positive_n,
        denominator=evidence.valid_n,
        observation_count=evidence.total_observations,
        ci_lower=evidence.hit_rate_ci95_low,
        ci_upper=evidence.hit_rate_ci95_high,
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        provenance=(),
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        attributes=attributes,
        identity_attributes=identity_attributes,
        additional_limitations=(evidence.limitation_notice,),
    )


def adapt_evidence(
    evidence: object,
    *,
    subject_id: str,
    data_tier: DataTier,
    calculation_code_version: str,
) -> EvidenceRecord:
    """Dispatch one supported frozen evidence value to its thin adapter."""

    adapters = (
        (TurnoverIntensityEvidence, adapt_turnover_intensity_evidence),
        (PortfolioConcentrationEvidence, adapt_portfolio_concentration_evidence),
        (DispositionEffectEvidence, adapt_disposition_effect_evidence),
        (LossAveragingEvidence, adapt_loss_averaging_evidence),
        (SelectionEvidence, adapt_selection_evidence),
        (SizingDecisionEvidence, adapt_sizing_evidence),
        (ExitTimingEvidence, adapt_exit_timing_evidence),
        (FrictionEvidence, adapt_friction_evidence),
        (DecisionEvidenceStatistics, adapt_decision_evidence_statistics),
    )
    for evidence_type, adapter in adapters:
        if isinstance(evidence, evidence_type):
            return adapter(
                evidence,
                subject_id=subject_id,
                data_tier=data_tier,
                calculation_code_version=calculation_code_version,
            )
    raise TypeError(f"Unsupported evidence type: {type(evidence).__name__}")
