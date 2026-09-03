"""Small, queryable registry for evidence method specifications."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from src.attribution.decision_evidence_statistics import (
    HIT_RATE_DEFINITION,
    INTERVAL_METHOD,
    LIMITATION_NOTICE,
)
from src.attribution.exit_timing_evidence import COUNTERFACTUAL_NOTICE
from src.behavior.disposition_effect import (
    LIMITATION as DISPOSITION_LIMITATION,
    METHOD_ID as DISPOSITION_METHOD_ID,
    METHOD_SOURCE as DISPOSITION_METHOD_SOURCE,
    SAMPLE_BASIS as DISPOSITION_SAMPLE_BASIS,
)
from src.behavior.loss_averaging import (
    LIMITATION as LOSS_AVERAGING_LIMITATION,
    METHOD_ID as LOSS_AVERAGING_METHOD_ID,
    METHOD_SOURCE as LOSS_AVERAGING_METHOD_SOURCE,
    SAMPLE_BASIS as LOSS_AVERAGING_SAMPLE_BASIS,
)
from src.behavior.portfolio_concentration import (
    LIMITATION as CONCENTRATION_LIMITATION,
    METHOD_ID as CONCENTRATION_METHOD_ID,
    METHOD_SOURCE as CONCENTRATION_METHOD_SOURCE,
    SAMPLE_BASIS as CONCENTRATION_SAMPLE_BASIS,
)
from src.behavior.turnover_intensity import (
    LIMITATION as TURNOVER_LIMITATION,
    METHOD_ID as TURNOVER_METHOD_ID,
    METHOD_SOURCE as TURNOVER_METHOD_SOURCE,
    SAMPLE_BASIS as TURNOVER_SAMPLE_BASIS,
)
from src.evidence.contracts import (
    EvidenceRecord,
    canonical_json_bytes,
    freeze_json_mapping,
)


METHOD_VERSION_V1: Final = "1"
EVIDENCE_PRODUCER: Final = "personal-investment-twin"
SELECTION_METHOD_ID: Final = "selection_episode_twr_vs_benchmarks_v1"
SIZING_METHOD_ID: Final = "equal_weight_sizing_counterfactual_v1"
EXIT_METHOD_ID: Final = "hold_20_sessions_v1"
FRICTION_METHOD_ID: Final = "zero_recorded_fee_counterfactual_v1"
STATISTICS_METHOD_ID: Final = "decision_evidence_statistics_v1"
PORTFOLIO_REPLAY_METHOD_ID: Final = "vectorbt_portfolio_replay_v1"
PRETRADE_IMPACT_METHOD_ID: Final = "pretrade_hhi_impact_v1"
NORMALIZED_EXECUTION_METHOD_ID: Final = "normalized_execution_contract_v1"
REGISTRY_REVISION: Final = 1
CONCEPT_REGISTRY_REVISION: Final = 1
DAILY_MARKET_AVAILABILITY_LIMITATION: Final = (
    "Current market data has daily date semantics and no intraday availability "
    "timestamp. The system excludes future dates but cannot prove that a day's "
    "final close was available at an intraday decision time."
)

TraceKind = Literal[
    "formula_components",
    "rule_observations",
    "comparison",
    "before_after",
    "statistical_summary",
    "source_fact",
]
_TRACE_KINDS = frozenset(
    {
        "formula_components",
        "rule_observations",
        "comparison",
        "before_after",
        "statistical_summary",
        "source_fact",
    }
)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class MethodDefinition:
    """Method specification plus system-generated registry metadata."""

    method_id: str
    method_version: str
    source: str
    sample_basis: str
    limitations: tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("method_id", "method_version", "source", "sample_basis"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        limitations = tuple(_text(item, "limitation") for item in self.limitations)
        object.__setattr__(self, "limitations", limitations)
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", freeze_json_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class InterpretationBoundary:
    """Machine-readable policy for what a concept can and cannot support."""

    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_claims",
            tuple(_text(item, "allowed_claim") for item in self.allowed_claims),
        )
        object.__setattr__(
            self,
            "prohibited_claims",
            tuple(_text(item, "prohibited_claim") for item in self.prohibited_claims),
        )
        if set(self.allowed_claims) & set(self.prohibited_claims):
            raise ValueError("Interpretation claims cannot be both allowed and prohibited")


@dataclass(frozen=True, slots=True)
class ConceptDefinition:
    """Stable semantics for one real financial fact or evidence method."""

    concept_id: str
    metric_id: str | None
    evidence_type: str | None
    method_id: str
    method_version: str
    category: str
    value_type: str
    unit: str
    directionality: str
    formula_kind: str
    formula_display: str
    title_key: str
    short_definition_key: str
    detailed_definition_key: str
    interpretation_boundary: InterpretationBoundary
    limitations: tuple[str, ...]
    methodology_refs: tuple[str, ...]
    calculation_trace_kind: TraceKind

    def __post_init__(self) -> None:
        for field_name in (
            "concept_id",
            "method_id",
            "method_version",
            "category",
            "value_type",
            "unit",
            "directionality",
            "formula_kind",
            "formula_display",
            "title_key",
            "short_definition_key",
            "detailed_definition_key",
            "calculation_trace_kind",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        for field_name in ("metric_id", "evidence_type"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
        object.__setattr__(
            self,
            "limitations",
            tuple(_text(item, "limitation") for item in self.limitations),
        )
        object.__setattr__(
            self,
            "methodology_refs",
            tuple(_text(item, "methodology_ref") for item in self.methodology_refs),
        )
        if self.calculation_trace_kind not in _TRACE_KINDS:
            raise ValueError("Unsupported calculation_trace_kind")


def _definition(
    *,
    method_id: str,
    source: str,
    sample_basis: str,
    limitations: tuple[str, ...],
    evidence_kind: str,
    module: str,
) -> MethodDefinition:
    spec = {
        "method_id": method_id,
        "method_version": METHOD_VERSION_V1,
        "source": source,
        "sample_basis": sample_basis,
        "limitations": limitations,
    }
    spec_digest = hashlib.sha256(canonical_json_bytes(spec)).hexdigest()
    return MethodDefinition(
        method_id=method_id,
        method_version=METHOD_VERSION_V1,
        source=source,
        sample_basis=sample_basis,
        limitations=limitations,
        metadata={
            "producer": EVIDENCE_PRODUCER,
            "registry_revision": REGISTRY_REVISION,
            "spec_digest": f"sha256:{spec_digest}",
            "evidence_kind": evidence_kind,
            "module": module,
        },
    )


_METHODS: Final = (
    _definition(
        method_id=TURNOVER_METHOD_ID,
        source=TURNOVER_METHOD_SOURCE,
        sample_basis=TURNOVER_SAMPLE_BASIS,
        limitations=(TURNOVER_LIMITATION,),
        evidence_kind="behavior_evidence",
        module="src.behavior.turnover_intensity",
    ),
    _definition(
        method_id=CONCENTRATION_METHOD_ID,
        source=CONCENTRATION_METHOD_SOURCE,
        sample_basis=CONCENTRATION_SAMPLE_BASIS,
        limitations=(CONCENTRATION_LIMITATION,),
        evidence_kind="behavior_evidence",
        module="src.behavior.portfolio_concentration",
    ),
    _definition(
        method_id=DISPOSITION_METHOD_ID,
        source=DISPOSITION_METHOD_SOURCE,
        sample_basis=DISPOSITION_SAMPLE_BASIS,
        limitations=(DISPOSITION_LIMITATION,),
        evidence_kind="behavior_evidence",
        module="src.behavior.disposition_effect",
    ),
    _definition(
        method_id=LOSS_AVERAGING_METHOD_ID,
        source=LOSS_AVERAGING_METHOD_SOURCE,
        sample_basis=LOSS_AVERAGING_SAMPLE_BASIS,
        limitations=(LOSS_AVERAGING_LIMITATION,),
        evidence_kind="behavior_evidence",
        module="src.behavior.loss_averaging",
    ),
    _definition(
        method_id=SELECTION_METHOD_ID,
        source=(
            "Existing SelectionEvidence: episode-period asset TWR and mapped "
            "market/industry benchmark TWR from empyrical."
        ),
        sample_basis="One InvestmentEpisode observation window.",
        limitations=(
            "SelectionEvidence is comparative episode evidence, not alpha or "
            "a conclusion about durable selection skill.",
        ),
        evidence_kind="decision_evidence",
        module="src.attribution.selection_evidence",
    ),
    _definition(
        method_id=SIZING_METHOD_ID,
        source=(
            "Existing SizingDecisionEvidence: vectorbt actual allocation versus "
            "an equal-weight baseline with matched start value and risky exposure."
        ),
        sample_basis="One completed interval between distinct sizing decisions.",
        limitations=(
            "The historical counterfactual is not sizing skill, alpha, causal "
            "attribution, or a recommendation.",
        ),
        evidence_kind="decision_evidence",
        module="src.attribution.sizing_evidence",
    ),
    _definition(
        method_id=EXIT_METHOD_ID,
        source="Existing ExitTimingEvidence fixed 20-session hold counterfactual.",
        sample_basis="One completed InvestmentEpisode exit and its fixed policy window.",
        limitations=(COUNTERFACTUAL_NOTICE,),
        evidence_kind="decision_evidence",
        module="src.attribution.exit_timing_evidence",
    ),
    _definition(
        method_id=FRICTION_METHOD_ID,
        source=(
            "Existing FrictionEvidence: actual recorded fees versus otherwise "
            "identical vectorbt replay with recorded fees set to zero."
        ),
        sample_basis="Normalized executions over one portfolio replay window.",
        limitations=(
            "Includes recorded explicit fees only; it does not estimate tax, "
            "slippage, spread, market impact, or opportunity cost.",
        ),
        evidence_kind="decision_evidence",
        module="src.attribution.friction_evidence",
    ),
    _definition(
        method_id=STATISTICS_METHOD_ID,
        source=(
            f"Existing DecisionEvidenceStatistics hit rate with {INTERVAL_METHOD}. "
            f"{HIT_RATE_DEFINITION}"
        ),
        sample_basis="Aggregated deterministic observations for one decision type.",
        limitations=(LIMITATION_NOTICE,),
        evidence_kind="aggregate_statistics",
        module="src.attribution.decision_evidence_statistics",
    ),
)

_METHOD_REGISTRY: Final = MappingProxyType(
    {(item.method_id, item.method_version): item for item in _METHODS}
)
if len(_METHOD_REGISTRY) != len(_METHODS):  # pragma: no cover - import invariant
    raise RuntimeError("Duplicate evidence method registration")


_NO_ADVICE = (
    "investment_advice",
    "buy_sell_recommendation",
    "future_return_prediction",
    "durable_skill_claim",
)
_NO_PSYCHOLOGY = (*_NO_ADVICE, "psychological_diagnosis", "motive_inference")


def _boundary(
    *allowed: str,
    prohibited: tuple[str, ...] = _NO_ADVICE,
) -> InterpretationBoundary:
    return InterpretationBoundary(
        allowed_claims=allowed,
        prohibited_claims=prohibited,
    )


def _concept(
    concept_id: str,
    *,
    metric_id: str | None,
    evidence_type: str | None,
    method_id: str,
    category: str,
    value_type: str,
    unit: str,
    directionality: str,
    formula_kind: str,
    formula_display: str,
    calculation_trace_kind: TraceKind,
    boundary: InterpretationBoundary,
    limitations: tuple[str, ...] = (),
    methodology_refs: tuple[str, ...] = (),
) -> ConceptDefinition:
    return ConceptDefinition(
        concept_id=concept_id,
        metric_id=metric_id,
        evidence_type=evidence_type,
        method_id=method_id,
        method_version=METHOD_VERSION_V1,
        category=category,
        value_type=value_type,
        unit=unit,
        directionality=directionality,
        formula_kind=formula_kind,
        formula_display=formula_display,
        title_key=f"evidence.concept.{concept_id}.title",
        short_definition_key=f"evidence.concept.{concept_id}.short",
        detailed_definition_key=f"evidence.concept.{concept_id}.detail",
        interpretation_boundary=boundary,
        limitations=limitations,
        methodology_refs=methodology_refs,
        calculation_trace_kind=calculation_trace_kind,
    )


_CONCEPTS: Final = (
    _concept(
        "portfolio_concentration_hhi",
        metric_id="portfolio_concentration_hhi",
        evidence_type="behavior_evidence",
        method_id=CONCENTRATION_METHOD_ID,
        category="portfolio_structure",
        value_type="ratio",
        unit="ratio",
        directionality="higher_means_mathematically_more_concentrated",
        formula_kind="sum_of_squared_weights",
        formula_display="sum(weight_i ** 2)",
        calculation_trace_kind="formula_components",
        boundary=_boundary("describe_security_weight_concentration"),
        limitations=(CONCENTRATION_LIMITATION, DAILY_MARKET_AVAILABILITY_LIMITATION),
        methodology_refs=("src.behavior.portfolio_concentration",),
    ),
    _concept(
        "turnover_intensity",
        metric_id="mean_daily_turnover",
        evidence_type="behavior_evidence",
        method_id=TURNOVER_METHOD_ID,
        category="trading_activity",
        value_type="rate",
        unit="ratio",
        directionality="higher_means_more_traded_value_per_portfolio_value",
        formula_kind="mean_of_daily_ratios",
        formula_display="mean(daily_traded_value / daily_portfolio_value)",
        calculation_trace_kind="formula_components",
        boundary=_boundary("describe_observed_turnover", prohibited=_NO_PSYCHOLOGY),
        limitations=(TURNOVER_LIMITATION, DAILY_MARKET_AVAILABILITY_LIMITATION),
        methodology_refs=("src.behavior.turnover_intensity",),
    ),
    _concept(
        "disposition_effect",
        metric_id="disposition_effect",
        evidence_type="behavior_evidence",
        method_id=DISPOSITION_METHOD_ID,
        category="behavior_evidence",
        value_type="difference",
        unit="ratio",
        directionality="signed_pgr_minus_plr",
        formula_kind="rate_difference",
        formula_display="PGR - PLR",
        calculation_trace_kind="formula_components",
        boundary=_boundary("describe_pgr_plr_observation", prohibited=_NO_PSYCHOLOGY),
        limitations=(DISPOSITION_LIMITATION, DAILY_MARKET_AVAILABILITY_LIMITATION),
        methodology_refs=("src.behavior.disposition_effect",),
    ),
    _concept(
        "loss_state_addition",
        metric_id="loss_averaging_event_rate",
        evidence_type="behavior_evidence",
        method_id=LOSS_AVERAGING_METHOD_ID,
        category="behavior_evidence",
        value_type="rule_event_rate",
        unit="ratio",
        directionality="higher_means_more_eligible_adds_matched_the_rule",
        formula_kind="strict_pre_trade_rule_and_rate",
        formula_display=(
            "count(execution_price < pre_trade_avg_cost) / "
            "eligible_existing_position_buys"
        ),
        calculation_trace_kind="rule_observations",
        boundary=_boundary("describe_loss_state_addition_rule", prohibited=_NO_PSYCHOLOGY),
        limitations=(LOSS_AVERAGING_LIMITATION,),
        methodology_refs=("src.behavior.loss_averaging",),
    ),
    _concept(
        "sizing_equal_weight_comparison",
        metric_id="sizing_equal_weight_comparison",
        evidence_type="decision_evidence",
        method_id=SIZING_METHOD_ID,
        category="decision_evidence",
        value_type="comparison",
        unit="comparison",
        directionality="actual_relative_to_fixed_equal_weight_baseline",
        formula_kind="counterfactual_comparison",
        formula_display="compare(actual_end_value, equal_weight_baseline_end_value)",
        calculation_trace_kind="comparison",
        boundary=_boundary("describe_actual_vs_equal_weight_baseline"),
        limitations=(
            *_METHOD_REGISTRY[(SIZING_METHOD_ID, METHOD_VERSION_V1)].limitations,
            DAILY_MARKET_AVAILABILITY_LIMITATION,
        ),
        methodology_refs=("src.attribution.sizing_evidence",),
    ),
    _concept(
        "sell_decision_evidence",
        metric_id=None,
        evidence_type="decision_fact",
        method_id=PORTFOLIO_REPLAY_METHOD_ID,
        category="decision_evidence",
        value_type="source_fact",
        unit="mixed",
        directionality="descriptive_only",
        formula_kind="completed_position_exit_context",
        formula_display="completed Position exit facts",
        calculation_trace_kind="source_fact",
        boundary=_boundary("describe_completed_exit_facts"),
        limitations=(
            "Only a completed final SELL that returns the Position to zero is an exit.",
            "A partial SELL is a position reduction, and an Open Position mark is not an exit.",
        ),
        methodology_refs=("src.attribution.exit_timing_evidence",),
    ),
    _concept(
        "post_exit_fixed_window_return",
        metric_id="exit_timing_post_exit_asset_return",
        evidence_type="decision_evidence",
        method_id=EXIT_METHOD_ID,
        category="decision_evidence",
        value_type="return",
        unit="ratio",
        directionality="signed_market_return_after_completed_exit_session",
        formula_kind="empyrical_total_return",
        formula_display=(
            "empyrical.cum_returns_final(empyrical.simple_returns(window_market_prices))"
        ),
        calculation_trace_kind="formula_components",
        boundary=_boundary("describe_fixed_window_post_exit_market_return"),
        limitations=(COUNTERFACTUAL_NOTICE, DAILY_MARKET_AVAILABILITY_LIMITATION),
        methodology_refs=("src.attribution.exit_timing_evidence",),
    ),
    _concept(
        "pretrade_concentration_impact",
        metric_id="pretrade_portfolio_hhi_delta",
        evidence_type="hypothetical_impact",
        method_id=PRETRADE_IMPACT_METHOD_ID,
        category="pre_trade",
        value_type="before_after",
        unit="ratio",
        directionality="signed_post_trade_minus_current_hhi",
        formula_kind="deterministic_before_after",
        formula_display="post_trade_hhi - current_hhi",
        calculation_trace_kind="before_after",
        boundary=_boundary("describe_hypothetical_portfolio_state_change"),
        limitations=(
            "This is a deterministic hypothetical execution, not a brokerage order.",
            "No future return or execution likelihood is predicted.",
            DAILY_MARKET_AVAILABILITY_LIMITATION,
        ),
        methodology_refs=("src.pretrade.impact",),
    ),
    _concept(
        "valuation_price",
        metric_id=None,
        evidence_type="financial_fact",
        method_id=PORTFOLIO_REPLAY_METHOD_ID,
        category="valuation",
        value_type="price",
        unit="currency_per_unit",
        directionality="descriptive_only",
        formula_kind="replay_mark",
        formula_display="vectorbt close at valuation time",
        calculation_trace_kind="source_fact",
        boundary=_boundary("describe_mark_to_market_price"),
        limitations=(
            "A valuation price is a mark and is not an executed sale price.",
            DAILY_MARKET_AVAILABILITY_LIMITATION,
        ),
        methodology_refs=("src.core.portfolio_replay",),
    ),
    _concept(
        "execution_price",
        metric_id=None,
        evidence_type="financial_fact",
        method_id=NORMALIZED_EXECUTION_METHOD_ID,
        category="execution",
        value_type="price",
        unit="currency_per_unit",
        directionality="descriptive_only",
        formula_kind="source_fact",
        formula_display="normalized executed_price",
        calculation_trace_kind="source_fact",
        boundary=_boundary("describe_actual_or_explicitly_hypothetical_execution_price"),
        limitations=(
            "Execution price must retain whether its source is actual or hypothetical.",
        ),
        methodology_refs=("docs/NORMALIZED_EXECUTIONS_CONTRACT.md",),
    ),
    _concept(
        "selection_episode_asset_return",
        metric_id="selection_episode_asset_return",
        evidence_type="decision_evidence",
        method_id=SELECTION_METHOD_ID,
        category="decision_evidence",
        value_type="return",
        unit="ratio",
        directionality="signed_episode_period_asset_market_return",
        formula_kind="empyrical_total_return",
        formula_display="empyrical.cum_returns_final(empyrical.simple_returns(asset_prices))",
        calculation_trace_kind="formula_components",
        boundary=_boundary("describe_episode_asset_and_benchmark_returns"),
        limitations=(
            *_METHOD_REGISTRY[(SELECTION_METHOD_ID, METHOD_VERSION_V1)].limitations,
            DAILY_MARKET_AVAILABILITY_LIMITATION,
        ),
        methodology_refs=("src.attribution.selection_evidence",),
    ),
    _concept(
        "recorded_trading_friction",
        metric_id="recorded_trading_friction_comparison",
        evidence_type="decision_evidence",
        method_id=FRICTION_METHOD_ID,
        category="decision_evidence",
        value_type="comparison",
        unit="currency",
        directionality="actual_relative_to_zero_recorded_fee_baseline",
        formula_kind="counterfactual_comparison",
        formula_display="compare(actual_end_value, zero_recorded_fee_end_value)",
        calculation_trace_kind="comparison",
        boundary=_boundary("describe_recorded_explicit_fee_effect"),
        limitations=_METHOD_REGISTRY[(FRICTION_METHOD_ID, METHOD_VERSION_V1)].limitations,
        methodology_refs=("src.attribution.friction_evidence",),
    ),
    _concept(
        "decision_evidence_hit_rate",
        metric_id=None,
        evidence_type="aggregate_statistics",
        method_id=STATISTICS_METHOD_ID,
        category="aggregate_statistics",
        value_type="rate_with_interval",
        unit="ratio",
        directionality="positive_observations_divided_by_valid_observations",
        formula_kind="existing_statistical_result",
        formula_display="positive_n / valid_n with existing Wilson CI",
        calculation_trace_kind="statistical_summary",
        boundary=_boundary("describe_registered_aggregate_statistics"),
        limitations=_METHOD_REGISTRY[(STATISTICS_METHOD_ID, METHOD_VERSION_V1)].limitations,
        methodology_refs=("src.attribution.decision_evidence_statistics",),
    ),
)

_CONCEPT_REGISTRY: Final = MappingProxyType(
    {item.concept_id: item for item in _CONCEPTS}
)
if len(_CONCEPT_REGISTRY) != len(_CONCEPTS):  # pragma: no cover - import invariant
    raise RuntimeError("Duplicate concept_id registration")

_EVIDENCE_CONCEPTS = tuple(
    item for item in _CONCEPTS if item.metric_id is not None
)
_EVIDENCE_CONCEPT_REGISTRY: Final = MappingProxyType(
    {
        (item.metric_id, item.method_id, item.method_version): item
        for item in _EVIDENCE_CONCEPTS
    }
)
if len(_EVIDENCE_CONCEPT_REGISTRY) != len(_EVIDENCE_CONCEPTS):
    raise RuntimeError("Conflicting evidence concept method binding")


def get_method_definition(
    method_id: str,
    method_version: str = METHOD_VERSION_V1,
) -> MethodDefinition:
    """Return one registered method definition."""

    try:
        return _METHOD_REGISTRY[(method_id, method_version)]
    except KeyError as exc:
        raise KeyError(
            f"Unknown evidence method: {method_id!r} version {method_version!r}"
        ) from exc


def list_method_definitions() -> tuple[MethodDefinition, ...]:
    """Return registered method specifications in stable declaration order."""

    return _METHODS


def get_concept(concept_id: str) -> ConceptDefinition:
    """Return one registered ConceptDefinition by stable semantic ID."""

    try:
        return _CONCEPT_REGISTRY[concept_id]
    except KeyError as exc:
        raise KeyError(f"Unknown evidence concept: {concept_id!r}") from exc


def get_concept_for_evidence(record: EvidenceRecord) -> ConceptDefinition:
    """Resolve the exact metric/method/version binding for an EvidenceRecord."""

    key = (record.metric_id, record.method_id, record.method_version)
    try:
        return _EVIDENCE_CONCEPT_REGISTRY[key]
    except KeyError as exc:
        raise KeyError(f"No concept is registered for evidence binding: {key!r}") from exc


def list_concepts() -> tuple[ConceptDefinition, ...]:
    """Return ConceptDefinitions in stable declaration order."""

    return _CONCEPTS
