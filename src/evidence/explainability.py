"""Deterministic concept and calculation traces for existing financial facts.

The builders in this module never replay a portfolio or evaluate a financial
formula.  They validate an existing EvidenceRecord against the frozen source
result and serialize intermediate components emitted by that original
calculator.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from src.attribution.decision_evidence_statistics import DecisionEvidenceStatistics
from src.attribution.exit_timing_evidence import ExitTimingEvidence
from src.attribution.sizing_evidence import SizingDecisionEvidence
from src.behavior.loss_averaging import LossAveragingEvidence
from src.behavior.portfolio_concentration import PortfolioConcentrationEvidence
from src.behavior.turnover_intensity import TurnoverIntensityEvidence
from src.episodes.position_episode import (
    DecisionEvent,
    EpisodeSnapshot,
    PositionEpisode,
    ReplayPositionState,
)
from src.evidence.contracts import (
    EvidenceProvenance,
    EvidenceRecord,
    canonical_json_bytes,
    freeze_json_mapping,
)
from src.evidence.registry import (
    METHOD_VERSION_V1,
    STATISTICS_METHOD_ID,
    ConceptDefinition,
    InterpretationBoundary,
    get_concept,
    get_concept_for_evidence,
)
from src.pretrade.impact import TradeImpact
from src.twin.state import evidence_available_at


CALCULATION_TRACE_SCHEMA_VERSION = "1"
_TRACE_ID_PATTERN = re.compile(r"^ct_[0-9a-f]{64}$")

TraceScalar = int | float | str | bool | None
CalculationStatus = Literal["complete", "partial", "insufficient", "rejected"]
AvailabilityStatus = Literal["available", "unavailable"]
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


class ExplainabilityError(ValueError):
    """An evidence/source pair cannot produce a trustworthy trace."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExplainabilityError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: object | None, name: str) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ExplainabilityError(f"{name} must be a timestamp or None") from exc
    if pd.isna(result):
        raise ExplainabilityError(f"{name} cannot be NaT")
    return result


def _scalar(value: object, name: str) -> TraceScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExplainabilityError(f"{name} must be finite")
        return value
    raise ExplainabilityError(f"{name} must be a JSON scalar")


@dataclass(frozen=True, slots=True)
class CalculationInput:
    input_id: str
    semantic_name: str
    label_key: str
    value: TraceScalar
    unit: str
    timestamp: pd.Timestamp | None
    source_type: str
    source_ref: str
    role: str
    availability_status: AvailabilityStatus = "available"
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "input_id",
            "semantic_name",
            "label_key",
            "unit",
            "source_type",
            "source_ref",
            "role",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "value", _scalar(self.value, "input.value"))
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp, "input.timestamp"))
        if self.availability_status not in {"available", "unavailable"}:
            raise ExplainabilityError("Unsupported input availability_status")
        if not isinstance(self.attributes, Mapping):
            raise ExplainabilityError("input.attributes must be a mapping")
        object.__setattr__(self, "attributes", freeze_json_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class CalculationOperation:
    operation_id: str
    operation_kind: str
    formula_display: str
    input_refs: tuple[str, ...]
    result: TraceScalar
    unit: str
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("operation_id", "operation_kind", "formula_display", "unit"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        refs = tuple(_text(item, "operation.input_ref") for item in self.input_refs)
        object.__setattr__(self, "input_refs", refs)
        object.__setattr__(self, "result", _scalar(self.result, "operation.result"))
        if not isinstance(self.attributes, Mapping):
            raise ExplainabilityError("operation.attributes must be a mapping")
        object.__setattr__(self, "attributes", freeze_json_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class ObservationWindow:
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    policy_sessions: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _timestamp(self.start, "window.start"))
        object.__setattr__(self, "end", _timestamp(self.end, "window.end"))
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ExplainabilityError("observation window end cannot precede start")
        if self.policy_sessions is not None:
            if (
                isinstance(self.policy_sessions, bool)
                or not isinstance(self.policy_sessions, int)
                or self.policy_sessions <= 0
            ):
                raise ExplainabilityError("policy_sessions must be positive")


@dataclass(frozen=True, slots=True)
class CalculationTrace:
    trace_id: str
    evidence_id: str | None
    subject_ref: str
    concept_id: str
    method_id: str
    method_version: str
    trace_kind: str
    as_of: pd.Timestamp | None
    calculation_status: CalculationStatus
    result: TraceScalar
    unit: str
    formula_kind: str
    formula_display: str
    inputs: tuple[CalculationInput, ...]
    operations: tuple[CalculationOperation, ...]
    observation_window: ObservationWindow | None
    source_refs: tuple[str, ...]
    provenance: tuple[EvidenceProvenance, ...]
    limitations: tuple[str, ...]
    calculation_code_version: str
    reason: str | None
    required_condition: str | None
    available_observation: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.trace_id, str) or not _TRACE_ID_PATTERN.fullmatch(
            self.trace_id
        ):
            raise ExplainabilityError("trace_id must be ct_ followed by SHA-256")
        if self.evidence_id is not None:
            object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        for name in (
            "subject_ref",
            "concept_id",
            "method_id",
            "method_version",
            "trace_kind",
            "unit",
            "formula_kind",
            "formula_display",
            "calculation_code_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        if self.trace_kind not in _TRACE_KINDS:
            raise ExplainabilityError("Unsupported trace_kind")
        if self.calculation_status not in {
            "complete",
            "partial",
            "insufficient",
            "rejected",
        }:
            raise ExplainabilityError("Unsupported calculation_status")
        object.__setattr__(self, "result", _scalar(self.result, "trace.result"))
        if self.calculation_status == "complete" and self.result is None:
            raise ExplainabilityError("A complete trace must retain its source result")
        if self.calculation_status in {"insufficient", "rejected"} and self.result is not None:
            raise ExplainabilityError("An incomplete trace cannot invent a result")
        inputs = tuple(self.inputs)
        operations = tuple(self.operations)
        input_ids = {item.input_id for item in inputs}
        if len(input_ids) != len(inputs):
            raise ExplainabilityError("Calculation input IDs must be unique")
        operation_ids = {item.operation_id for item in operations}
        if len(operation_ids) != len(operations):
            raise ExplainabilityError("Calculation operation IDs must be unique")
        unknown_refs = {
            ref for operation in operations for ref in operation.input_refs
            if ref not in input_ids
        }
        if unknown_refs:
            raise ExplainabilityError(f"Operation references unknown inputs: {unknown_refs}")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(
            self,
            "source_refs",
            tuple(_text(item, "source_ref") for item in self.source_refs),
        )
        provenance = tuple(self.provenance)
        if any(not isinstance(item, EvidenceProvenance) for item in provenance):
            raise ExplainabilityError("trace provenance must contain EvidenceProvenance")
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(
            self,
            "limitations",
            tuple(_text(item, "limitation") for item in self.limitations),
        )
        if self.reason is not None:
            object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if self.required_condition is not None:
            object.__setattr__(
                self,
                "required_condition",
                _text(self.required_condition, "required_condition"),
            )
        if not isinstance(self.available_observation, Mapping):
            raise ExplainabilityError("available_observation must be a mapping")
        object.__setattr__(
            self,
            "available_observation",
            freeze_json_mapping(self.available_observation),
        )


@dataclass(frozen=True, slots=True)
class EvidenceResultSnapshot:
    value: TraceScalar
    numerator: int | float | None
    denominator: int | float | str | None
    observation_count: int | None
    ci_lower: float | None
    ci_upper: float | None
    evidence_status: str
    evidence_reason: str | None


@dataclass(frozen=True, slots=True)
class EvidenceExplainabilityView:
    evidence_id: str
    concept: ConceptDefinition
    result: EvidenceResultSnapshot
    calculation_trace: CalculationTrace
    provenance: tuple[EvidenceProvenance, ...]
    limitations: tuple[str, ...]
    interpretation_boundary: InterpretationBoundary


def _input_payload(item: CalculationInput) -> dict[str, object]:
    return {
        "input_id": item.input_id,
        "semantic_name": item.semantic_name,
        "label_key": item.label_key,
        "value": item.value,
        "unit": item.unit,
        "timestamp": item.timestamp.isoformat() if item.timestamp is not None else None,
        "source_type": item.source_type,
        "source_ref": item.source_ref,
        "role": item.role,
        "availability_status": item.availability_status,
        "attributes": item.attributes,
    }


def _operation_payload(item: CalculationOperation) -> dict[str, object]:
    return {
        "operation_id": item.operation_id,
        "operation_kind": item.operation_kind,
        "formula_display": item.formula_display,
        "input_refs": item.input_refs,
        "result": item.result,
        "unit": item.unit,
        "attributes": item.attributes,
    }


def _trace(
    *,
    evidence_id: str | None,
    subject_ref: str,
    concept: ConceptDefinition,
    as_of: pd.Timestamp | None,
    calculation_status: CalculationStatus,
    result: TraceScalar,
    inputs: Sequence[CalculationInput],
    operations: Sequence[CalculationOperation],
    observation_window: ObservationWindow | None,
    source_refs: Sequence[str],
    provenance: Sequence[EvidenceProvenance],
    limitations: Sequence[str],
    calculation_code_version: str,
    reason: str | None = None,
    required_condition: str | None = None,
    available_observation: Mapping[str, object] | None = None,
) -> CalculationTrace:
    normalized_as_of = _timestamp(as_of, "as_of")
    normalized_inputs = tuple(inputs)
    normalized_operations = tuple(operations)
    normalized_sources = tuple(
        dict.fromkeys(
            (*source_refs, *(item.source_ref for item in normalized_inputs))
        )
    )
    normalized_provenance = tuple(provenance)
    normalized_limitations = tuple(dict.fromkeys(limitations))
    available = {} if available_observation is None else dict(available_observation)
    identity = {
        "schema_version": CALCULATION_TRACE_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "subject_ref": subject_ref,
        "concept_id": concept.concept_id,
        "method_id": concept.method_id,
        "method_version": concept.method_version,
        "trace_kind": concept.calculation_trace_kind,
        "as_of": normalized_as_of.isoformat() if normalized_as_of is not None else None,
        "calculation_status": calculation_status,
        "result": result,
        "unit": concept.unit,
        "formula_kind": concept.formula_kind,
        "formula_display": concept.formula_display,
        "inputs": [_input_payload(item) for item in normalized_inputs],
        "operations": [_operation_payload(item) for item in normalized_operations],
        "observation_window": (
            {
                "start": observation_window.start.isoformat()
                if observation_window and observation_window.start is not None
                else None,
                "end": observation_window.end.isoformat()
                if observation_window and observation_window.end is not None
                else None,
                "policy_sessions": observation_window.policy_sessions
                if observation_window
                else None,
            }
            if observation_window is not None
            else None
        ),
        "source_refs": normalized_sources,
        "provenance": [item.identity_payload() for item in normalized_provenance],
        "limitations": normalized_limitations,
        "calculation_code_version": calculation_code_version,
        "reason": reason,
        "required_condition": required_condition,
        "available_observation": available,
    }
    trace_id = "ct_" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return CalculationTrace(
        trace_id=trace_id,
        evidence_id=evidence_id,
        subject_ref=subject_ref,
        concept_id=concept.concept_id,
        method_id=concept.method_id,
        method_version=concept.method_version,
        trace_kind=concept.calculation_trace_kind,
        as_of=normalized_as_of,
        calculation_status=calculation_status,
        result=result,
        unit=concept.unit,
        formula_kind=concept.formula_kind,
        formula_display=concept.formula_display,
        inputs=normalized_inputs,
        operations=normalized_operations,
        observation_window=observation_window,
        source_refs=normalized_sources,
        provenance=normalized_provenance,
        limitations=normalized_limitations,
        calculation_code_version=calculation_code_version,
        reason=reason,
        required_condition=required_condition,
        available_observation=available,
    )


def _calculation_status(record: EvidenceRecord) -> CalculationStatus:
    if record.evidence_status == "complete":
        return "complete"
    if record.evidence_status == "partial":
        return "partial"
    return "insufficient"


def _same(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return left == right
    return left == right


def _validate_record(
    record: EvidenceRecord,
    *,
    metric_id: str,
    method_id: str,
    value: object,
    evidence_status: str,
    numerator: object = ...,
    denominator: object = ...,
    ci_lower: object = ...,
    ci_upper: object = ...,
) -> None:
    expected_status = "complete" if evidence_status == "available" else evidence_status
    checks = {
        "metric_id": (record.metric_id, metric_id),
        "method_id": (record.method_id, method_id),
        "method_version": (record.method_version, METHOD_VERSION_V1),
        "value": (record.value, value),
        "evidence_status": (record.evidence_status, expected_status),
    }
    if numerator is not ...:
        checks["numerator"] = (record.numerator, numerator)
    if denominator is not ...:
        checks["denominator"] = (record.denominator, denominator)
    if ci_lower is not ...:
        checks["ci_lower"] = (record.ci_lower, ci_lower)
    if ci_upper is not ...:
        checks["ci_upper"] = (record.ci_upper, ci_upper)
    mismatches = [name for name, (actual, expected) in checks.items() if not _same(actual, expected)]
    if mismatches:
        raise ExplainabilityError(
            "EvidenceRecord does not match its deterministic source: "
            + ", ".join(mismatches)
        )


def _validate_attributes(record: EvidenceRecord, key: str, expected: object) -> None:
    if key not in record.attributes:
        raise ExplainabilityError(f"EvidenceRecord is missing trace component: {key}")
    if canonical_json_bytes(record.attributes[key]) != canonical_json_bytes(expected):
        raise ExplainabilityError(f"EvidenceRecord trace component is inconsistent: {key}")


def _validate_attribute_mapping(
    record: EvidenceRecord,
    expected: Mapping[str, object],
) -> None:
    for key, value in expected.items():
        _validate_attributes(record, key, value)


def _ensure_available(record: EvidenceRecord, as_of: pd.Timestamp | None) -> None:
    if as_of is None:
        return
    requested = _timestamp(as_of, "requested as_of")
    available_at = evidence_available_at(record)
    if available_at is not None and requested is not None and available_at > requested:
        raise ExplainabilityError("Evidence was not available at the requested as_of")


def _ci_input(record: EvidenceRecord, name: str, value: float | None) -> CalculationInput:
    return CalculationInput(
        input_id=name,
        semantic_name=name,
        label_key=f"evidence.input.{name}",
        value=value,
        unit="ratio",
        timestamp=record.as_of,
        source_type="evidence",
        source_ref=f"evidence:{record.evidence_id}",
        role="existing_statistical_result",
        availability_status="available" if value is not None else "unavailable",
    )


def build_hhi_trace(
    record: EvidenceRecord,
    evidence: PortfolioConcentrationEvidence,
) -> CalculationTrace:
    concept = get_concept_for_evidence(record)
    _validate_record(
        record,
        metric_id="portfolio_concentration_hhi",
        method_id=evidence.method_id,
        value=evidence.hhi,
        evidence_status=evidence.evidence_status,
    )
    components = [
        {"symbol": item.symbol, "asset_value": item.asset_value, "weight": item.weight}
        for item in evidence.weight_components
    ]
    _validate_attributes(record, "weight_components", components)
    if evidence.evidence_status == "complete" and not evidence.weight_components:
        raise ExplainabilityError("Complete HHI evidence lacks weight components")
    inputs = tuple(
        CalculationInput(
            input_id=f"weight:{item.symbol}",
            semantic_name="security_weight",
            label_key="evidence.input.security_weight",
            value=item.weight,
            unit="ratio",
            timestamp=evidence.as_of_time,
            source_type="portfolio_state",
            source_ref=f"portfolio_state:{record.evidence_id}:{item.symbol}",
            role="formula_component",
            attributes={"symbol": item.symbol, "asset_value": item.asset_value},
        )
        for item in evidence.weight_components
    )
    operations = (
        CalculationOperation(
            operation_id="hhi",
            operation_kind="sum_of_squared_inputs",
            formula_display=concept.formula_display,
            input_refs=tuple(item.input_id for item in inputs),
            result=evidence.hhi,
            unit="ratio",
            attributes={"term_count": len(inputs)},
        ),
    ) if evidence.evidence_status == "complete" else ()
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(record.observation_start, record.observation_end),
        source_refs=(f"evidence:{record.evidence_id}",),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(
            None if record.evidence_status == "complete"
            else "positive_risky_asset_value_and_complete_market_panel"
        ),
        available_observation={
            "active_asset_count": evidence.active_asset_count,
            "weight_component_count": len(evidence.weight_components),
        },
    )


def build_turnover_trace(
    record: EvidenceRecord,
    evidence: TurnoverIntensityEvidence,
) -> CalculationTrace:
    concept = get_concept_for_evidence(record)
    _validate_record(
        record,
        metric_id="mean_daily_turnover",
        method_id=evidence.method_id,
        value=evidence.mean_daily_turnover,
        evidence_status=evidence.evidence_status,
        numerator=evidence.total_traded_value,
        denominator=evidence.denominator,
    )
    expected_daily = [
        {
            "observation_date": item.observation_date.isoformat(),
            "traded_value": item.traded_value,
            "portfolio_value": item.portfolio_value,
            "turnover": item.turnover,
        }
        for item in evidence.daily_turnover
    ]
    _validate_attributes(record, "daily_turnover", expected_daily)
    inputs: list[CalculationInput] = []
    operations: list[CalculationOperation] = []
    daily_turnover_ids: list[str] = []
    for index, item in enumerate(evidence.daily_turnover):
        traded_id = f"day:{index}:traded_value"
        value_id = f"day:{index}:portfolio_value"
        turnover_id = f"day:{index}:turnover_value"
        daily_turnover_ids.append(turnover_id)
        source_ref = f"portfolio_state:{record.evidence_id}:{item.observation_date.isoformat()}"
        inputs.extend(
            (
                CalculationInput(
                    traded_id,
                    "daily_traded_value",
                    "evidence.input.daily_traded_value",
                    item.traded_value,
                    "currency",
                    item.observation_date,
                    "portfolio_orders",
                    source_ref,
                    "numerator_component",
                ),
                CalculationInput(
                    value_id,
                    "daily_portfolio_value",
                    "evidence.input.daily_portfolio_value",
                    item.portfolio_value,
                    "currency",
                    item.observation_date,
                    "portfolio_state",
                    source_ref,
                    "denominator_component",
                ),
                CalculationInput(
                    turnover_id,
                    "daily_turnover",
                    "evidence.input.daily_turnover",
                    item.turnover,
                    "ratio",
                    item.observation_date,
                    "evidence",
                    f"evidence:{record.evidence_id}",
                    "existing_daily_result",
                ),
            )
        )
        operations.append(
            CalculationOperation(
                f"day:{index}:turnover",
                "ratio",
                "daily_traded_value / daily_portfolio_value",
                (traded_id, value_id),
                item.turnover,
                "ratio",
            )
        )
    if record.evidence_status == "complete":
        operations.append(
            CalculationOperation(
                "mean_daily_turnover",
                "mean_existing_daily_results",
                concept.formula_display,
                tuple(daily_turnover_ids),
                evidence.mean_daily_turnover,
                "ratio",
                {"daily_observation_count": len(evidence.daily_turnover)},
            )
        )
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(record.observation_start, record.observation_end),
        source_refs=(f"evidence:{record.evidence_id}",),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(
            None if record.evidence_status == "complete"
            else "complete_market_panel_and_positive_portfolio_value"
        ),
        available_observation={"daily_observation_count": len(evidence.daily_turnover)},
    )


def build_loss_state_addition_trace(
    record: EvidenceRecord,
    evidence: LossAveragingEvidence,
) -> CalculationTrace:
    concept = get_concept_for_evidence(record)
    _validate_record(
        record,
        metric_id="loss_averaging_event_rate",
        method_id=evidence.method_id,
        value=evidence.event_rate,
        evidence_status=evidence.evidence_status,
        numerator=evidence.loss_averaging_events,
        denominator=evidence.eligible_add_events,
    )
    expected_events = [
        {
            "event_time": item.event_time.isoformat(),
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
    _validate_attributes(record, "events", expected_events)
    inputs: list[CalculationInput] = []
    operations: list[CalculationOperation] = []
    execution_refs: list[str] = []
    for index, event in enumerate(evidence.events):
        if event.execution_id is None:
            raise ExplainabilityError(
                "Loss-state Addition event lacks its execution reference"
            )
        execution_ref = f"execution:{event.execution_id}"
        execution_refs.append(execution_ref)
        if not event.eligible_event:
            continue
        average_id = f"event:{index}:pre_trade_avg_cost"
        price_id = f"event:{index}:execution_price"
        inputs.extend(
            (
                CalculationInput(
                    average_id,
                    "pre_trade_avg_cost",
                    "evidence.input.pre_trade_avg_cost",
                    event.pre_trade_avg_cost,
                    "currency_per_unit",
                    event.event_time,
                    "replay_state",
                    f"replay_state:before:{execution_ref}",
                    "comparison_reference",
                    attributes={"symbol": event.symbol},
                ),
                CalculationInput(
                    price_id,
                    "execution_price",
                    "evidence.input.execution_price",
                    event.execution_price,
                    "currency_per_unit",
                    event.event_time,
                    "execution",
                    execution_ref,
                    "comparison_value",
                    attributes={"symbol": event.symbol},
                ),
            )
        )
        operations.append(
            CalculationOperation(
                f"event:{index}:loss_state_addition",
                "strict_less_than",
                "execution_price < pre_trade_avg_cost",
                (price_id, average_id),
                event.event_detected,
                "boolean",
                {"eligible_event": event.eligible_event},
            )
        )
    inputs.extend(
        (
            CalculationInput(
                "loss_state_addition_events",
                "loss_state_addition_events",
                "evidence.input.loss_state_addition_events",
                evidence.loss_averaging_events,
                "count",
                record.as_of,
                "evidence",
                f"evidence:{record.evidence_id}",
                "numerator_count",
            ),
            CalculationInput(
                "eligible_add_events",
                "eligible_add_events",
                "evidence.input.eligible_add_events",
                evidence.eligible_add_events,
                "count",
                record.as_of,
                "evidence",
                f"evidence:{record.evidence_id}",
                "denominator_count",
            ),
        )
    )
    if record.evidence_status == "complete":
        operations.append(
            CalculationOperation(
                "loss_state_addition_rate",
                "ratio_of_existing_counts",
                "loss_state_addition_events / eligible_add_events",
                ("loss_state_addition_events", "eligible_add_events"),
                evidence.event_rate,
                "ratio",
                {
                    "numerator": evidence.loss_averaging_events,
                    "denominator": evidence.eligible_add_events,
                },
            )
        )
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(record.observation_start, record.observation_end),
        source_refs=(f"evidence:{record.evidence_id}", *execution_refs),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(
            None if record.evidence_status == "complete"
            else "at_least_one_existing_position_buy"
        ),
        available_observation={
            "buy_observation_count": evidence.observation_count,
            "eligible_add_events": evidence.eligible_add_events,
        },
    )


def build_sizing_trace(
    record: EvidenceRecord,
    evidence: SizingDecisionEvidence,
) -> CalculationTrace:
    concept = get_concept_for_evidence(record)
    _validate_record(
        record,
        metric_id="sizing_equal_weight_comparison",
        method_id=concept.method_id,
        value=evidence.comparison,
        evidence_status=evidence.evidence_status,
    )
    _validate_attribute_mapping(
        record,
        {
            "active_assets": list(evidence.active_assets),
            "actual_weights": dict(evidence.actual_weights),
            "baseline_weights": dict(evidence.baseline_weights),
            "risky_exposure": evidence.risky_exposure,
            "actual_start_value": evidence.actual_start_value,
            "baseline_start_value": evidence.baseline_start_value,
            "actual_end_value": evidence.actual_end_value,
            "baseline_end_value": evidence.baseline_end_value,
            "comparison": evidence.comparison,
        },
    )
    actual_ref = f"portfolio_state:actual:{evidence.decision_time.isoformat()}"
    baseline_ref = f"counterfactual:{concept.method_id}:{evidence.decision_time.isoformat()}"
    inputs = tuple(
        CalculationInput(
            input_id=name,
            semantic_name=name,
            label_key=f"evidence.input.{name}",
            value=value,
            unit="currency",
            timestamp=evidence.interval_end_time if name.endswith("end_value") else evidence.decision_time,
            source_type="portfolio_state" if name.startswith("actual") else "counterfactual_portfolio",
            source_ref=actual_ref if name.startswith("actual") else baseline_ref,
            role="comparison_value" if name.endswith("end_value") else "matched_start_value",
        )
        for name, value in (
            ("actual_start_value", evidence.actual_start_value),
            ("baseline_start_value", evidence.baseline_start_value),
            ("actual_end_value", evidence.actual_end_value),
            ("baseline_end_value", evidence.baseline_end_value),
        )
        if value is not None
    )
    operations = (
        CalculationOperation(
            "sizing_comparison",
            "compare_existing_results",
            concept.formula_display,
            tuple(item.input_id for item in inputs if item.input_id.endswith("end_value")),
            evidence.comparison,
            "comparison",
            {
                "actual_weights": evidence.actual_weights,
                "baseline_weights": evidence.baseline_weights,
                "risky_exposure": evidence.risky_exposure,
            },
        ),
    ) if evidence.evidence_status == "complete" else ()
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(record.observation_start, record.observation_end),
        source_refs=(f"evidence:{record.evidence_id}", actual_ref, baseline_ref),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(
            None if record.evidence_status == "complete"
            else "completed_interval_with_two_or_more_active_assets"
        ),
        available_observation={"active_asset_count": len(evidence.active_assets)},
    )


def build_exit_fixed_window_trace(
    record: EvidenceRecord,
    evidence: ExitTimingEvidence,
) -> CalculationTrace:
    concept = get_concept_for_evidence(record)
    _validate_record(
        record,
        metric_id="exit_timing_post_exit_asset_return",
        method_id=evidence.policy_id,
        value=evidence.post_exit_asset_return,
        evidence_status=evidence.evidence_status,
    )
    expected_prices = [
        {"observation_time": item.observation_time.isoformat(), "price": item.price}
        for item in evidence.window_prices
    ]
    _validate_attribute_mapping(
        record,
        {
            "episode_id": evidence.episode_id,
            "symbol": evidence.symbol,
            "actual_exit_price": evidence.actual_exit_price,
            "policy_id": evidence.policy_id,
            "policy_sessions": evidence.policy_sessions,
            "counterfactual_exit_time": (
                evidence.counterfactual_exit_time.isoformat()
                if evidence.counterfactual_exit_time is not None
                else None
            ),
            "exit_session_market_price": evidence.exit_session_market_price,
            "counterfactual_exit_price": evidence.counterfactual_exit_price,
            "comparison": evidence.comparison,
            "window_prices": expected_prices,
        },
    )
    if evidence.evidence_status == "complete":
        expected_count = evidence.policy_sessions + 1
        if len(evidence.window_prices) != expected_count:
            raise ExplainabilityError(
                "Complete Exit evidence lacks the full validated price window"
            )
        first = evidence.window_prices[0]
        last = evidence.window_prices[-1]
        if (
            first.observation_time.normalize() != evidence.actual_exit_time.normalize()
            or first.price != evidence.exit_session_market_price
            or last.observation_time.normalize()
            != evidence.counterfactual_exit_time.normalize()
            or last.price != evidence.counterfactual_exit_price
        ):
            raise ExplainabilityError(
                "Exit price window endpoints do not match deterministic evidence"
            )
    inputs: list[CalculationInput] = []
    if evidence.actual_exit_price is not None:
        inputs.append(
            CalculationInput(
                "episode_avg_exit_price",
                "episode_avg_exit_price",
                "evidence.input.episode_avg_exit_price",
                evidence.actual_exit_price,
                "currency_per_unit",
                evidence.actual_exit_time,
                "position_episode",
                f"episode:{evidence.episode_id}",
                "context_not_return_formula",
                attributes={"not_window_market_price": True},
            )
        )
    market_input_ids: list[str] = []
    for index, item in enumerate(evidence.window_prices):
        input_id = f"window_price:{index}"
        market_input_ids.append(input_id)
        inputs.append(
            CalculationInput(
                input_id,
                "window_market_price",
                "evidence.input.window_market_price",
                item.price,
                "currency_per_unit",
                item.observation_time,
                "market_price",
                f"market_price:{evidence.symbol}:{item.observation_time.isoformat()}",
                "return_series_component",
                attributes={"symbol": evidence.symbol, "series_index": index},
            )
        )
    operations = (
        CalculationOperation(
            "post_exit_fixed_window_return",
            "empyrical_total_return_existing_result",
            concept.formula_display,
            tuple(market_input_ids),
            evidence.post_exit_asset_return,
            "ratio",
            {
                "comparison": evidence.comparison,
                "policy_sessions": evidence.policy_sessions,
                "return_price_basis": "validated_market_price_series",
                "episode_avg_exit_price_used_in_formula": False,
            },
        ),
    ) if evidence.evidence_status == "complete" else ()
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(
            evidence.actual_exit_time,
            evidence.counterfactual_exit_time,
            evidence.policy_sessions,
        ),
        source_refs=(
            f"evidence:{record.evidence_id}",
            f"episode:{evidence.episode_id}",
            *(item.source_ref for item in inputs if item.source_type == "market_price"),
        ),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(
            None if record.evidence_status == "complete"
            else "completed_final_exit_and_20_subsequent_market_sessions"
        ),
        available_observation={"window_price_count": len(evidence.window_prices)},
    )


def build_statistics_trace(
    record: EvidenceRecord,
    evidence: DecisionEvidenceStatistics,
) -> CalculationTrace:
    _validate_record(
        record,
        metric_id=f"{evidence.decision_type}_decision_hit_rate",
        method_id=STATISTICS_METHOD_ID,
        value=evidence.hit_rate,
        evidence_status=evidence.evidence_status,
        numerator=evidence.positive_n,
        denominator=evidence.valid_n,
        ci_lower=evidence.hit_rate_ci95_low,
        ci_upper=evidence.hit_rate_ci95_high,
    )
    _validate_attribute_mapping(
        record,
        {
            "decision_type": evidence.decision_type,
            "total_observations": evidence.total_observations,
            "valid_n": evidence.valid_n,
            "insufficient_n": evidence.insufficient_n,
            "positive_n": evidence.positive_n,
            "negative_n": evidence.negative_n,
            "matched_n": evidence.matched_n,
            "interval_method": evidence.interval_method,
        },
    )
    concept = get_concept("decision_evidence_hit_rate")
    inputs = (
        CalculationInput(
            "positive_n", "positive_n", "evidence.input.positive_n",
            evidence.positive_n, "count", record.as_of, "evidence",
            f"evidence:{record.evidence_id}", "existing_count",
        ),
        CalculationInput(
            "valid_n", "valid_n", "evidence.input.valid_n",
            evidence.valid_n, "count", record.as_of, "evidence",
            f"evidence:{record.evidence_id}", "existing_count",
        ),
        _ci_input(record, "ci_lower", record.ci_lower),
        _ci_input(record, "ci_upper", record.ci_upper),
    )
    operations = (
        CalculationOperation(
            "decision_hit_rate",
            "existing_statistical_result",
            concept.formula_display,
            ("positive_n", "valid_n"),
            evidence.hit_rate,
            "ratio",
            {
                "interval_method": evidence.interval_method,
                "ci_input_refs": ("ci_lower", "ci_upper"),
                "ci_recalculated": False,
            },
        ),
    ) if record.evidence_status == "complete" else ()
    return _trace(
        evidence_id=record.evidence_id,
        subject_ref=record.subject_id,
        concept=concept,
        as_of=record.as_of,
        calculation_status=_calculation_status(record),
        result=record.value,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(record.observation_start, record.observation_end),
        source_refs=(f"evidence:{record.evidence_id}",),
        provenance=record.provenance,
        limitations=(*record.limitations, *concept.limitations),
        calculation_code_version=record.calculation_code_version,
        reason=record.evidence_reason,
        required_condition=(None if record.evidence_status == "complete" else "valid_n_gt_zero"),
        available_observation={
            "total_observations": evidence.total_observations,
            "valid_n": evidence.valid_n,
            "insufficient_n": evidence.insufficient_n,
        },
    )


def build_pretrade_hhi_trace(
    impact: TradeImpact,
    *,
    calculation_code_version: str,
) -> CalculationTrace:
    concept = get_concept("pretrade_concentration_impact")
    if (
        impact.method_id != concept.method_id
        or impact.method_version != concept.method_version
    ):
        raise ExplainabilityError("TradeImpact method binding is not registered")
    if impact.hypothetical_execution_id is None:
        raise ExplainabilityError("TradeImpact lacks its hypothetical execution reference")
    subject_ref = impact.hypothetical_execution_id
    inputs = [
        CalculationInput(
            "proposed_execution_price",
            "execution_price",
            "evidence.input.execution_price",
            impact.proposed_trade.execution_price,
            "currency_per_unit",
            impact.proposed_trade.proposed_time,
            "hypothetical_execution",
            subject_ref,
            "execution_assumption",
        )
    ]
    operations: tuple[CalculationOperation, ...] = ()
    source_refs = [subject_ref]
    result: TraceScalar = None
    status: CalculationStatus
    if impact.simulation_status == "complete":
        if (
            impact.before is None
            or impact.after is None
            or impact.delta is None
            or impact.before_hhi_evidence_id is None
            or impact.after_hhi_evidence_id is None
        ):
            raise ExplainabilityError("Complete TradeImpact lacks deterministic HHI references")
        before_ref = f"evidence:{impact.before_hhi_evidence_id}"
        after_ref = f"evidence:{impact.after_hhi_evidence_id}"
        source_refs.extend((before_ref, after_ref))
        inputs.extend(
            (
                CalculationInput(
                    "current_hhi", "current_hhi", "evidence.input.current_hhi",
                    impact.before.hhi, "ratio", impact.proposed_trade.proposed_time,
                    "evidence", before_ref, "before_value",
                ),
                CalculationInput(
                    "post_trade_hhi", "post_trade_hhi", "evidence.input.post_trade_hhi",
                    impact.after.hhi, "ratio", impact.proposed_trade.proposed_time,
                    "evidence", after_ref, "after_value",
                ),
                CalculationInput(
                    "post_trade_valuation_price",
                    "valuation_price",
                    "evidence.input.valuation_price",
                    impact.after.valuation_price,
                    "currency_per_unit",
                    impact.proposed_trade.proposed_time,
                    "portfolio_state",
                    after_ref,
                    "mark_not_execution",
                ),
            )
        )
        result = impact.delta.hhi
        operations = (
            CalculationOperation(
                "pretrade_hhi_delta",
                "existing_before_after_delta",
                concept.formula_display,
                ("current_hhi", "post_trade_hhi"),
                impact.delta.hhi,
                "ratio",
                {"delta_recalculated": False},
            ),
        )
        status = "complete"
    else:
        status = "rejected" if impact.simulation_status == "rejected" else "insufficient"
    return _trace(
        evidence_id=None,
        subject_ref=subject_ref,
        concept=concept,
        as_of=impact.proposed_trade.proposed_time,
        calculation_status=status,
        result=result,
        inputs=inputs,
        operations=operations,
        observation_window=ObservationWindow(None, impact.proposed_trade.proposed_time),
        source_refs=source_refs,
        provenance=(),
        limitations=(*impact.limitations, *concept.limitations),
        calculation_code_version=calculation_code_version,
        reason=impact.simulation_reason,
        required_condition=(
            None if status == "complete" else "valid_supported_trade_and_complete_replay"
        ),
        available_observation={
            "before_state_available": impact.before is not None,
            "after_state_available": impact.after is not None,
        },
    )


def build_open_position_valuation_trace(
    episode: PositionEpisode,
    snapshot: EpisodeSnapshot,
    state: ReplayPositionState,
    *,
    calculation_code_version: str,
) -> CalculationTrace:
    if episode.status != "open" or episode.closed_at is not None or episode.closing_execution_id is not None:
        raise ExplainabilityError("Only a valid Open Episode can produce an open valuation trace")
    if snapshot.episode_id != episode.episode_id or snapshot.position_state_ref != state.state_id:
        raise ExplainabilityError("Open Episode valuation references are inconsistent")
    if state.boundary != "as_of_valuation" or state.valuation_price is None:
        raise ExplainabilityError("Open Episode has no valid as-of valuation state")
    concept = get_concept("valuation_price")
    input_item = CalculationInput(
        "valuation_price",
        "valuation_price",
        "evidence.input.valuation_price",
        state.valuation_price,
        "currency_per_unit",
        state.valuation_at,
        "replay_state",
        f"position_state:{state.state_id}",
        "mark_not_exit",
        attributes={"episode_status": "open", "is_exit": False},
    )
    return _trace(
        evidence_id=None,
        subject_ref=episode.episode_id,
        concept=concept,
        as_of=snapshot.as_of,
        calculation_status="complete",
        result=state.valuation_price,
        inputs=(input_item,),
        operations=(),
        observation_window=ObservationWindow(episode.opened_at, snapshot.as_of),
        source_refs=(f"episode:{episode.episode_id}", f"position_state:{state.state_id}"),
        provenance=episode.provenance,
        limitations=(*episode.limitations, *concept.limitations),
        calculation_code_version=calculation_code_version,
        available_observation={"episode_status": "open", "is_exit": False},
    )


def build_completed_exit_decision_trace(
    decision: DecisionEvent,
    *,
    calculation_code_version: str,
) -> CalculationTrace:
    if decision.decision_type != "close_position" or decision.side != "SELL":
        raise ExplainabilityError("A partial SELL is not a completed final exit")
    concept = get_concept("sell_decision_evidence")
    execution_ref = f"execution:{decision.execution_id}"
    inputs = (
        CalculationInput(
            "execution_price", "execution_price", "evidence.input.execution_price",
            decision.execution_price, "currency_per_unit", decision.occurred_at,
            "execution", execution_ref, "actual_final_exit_execution",
        ),
        CalculationInput(
            "executed_quantity", "executed_quantity", "evidence.input.executed_quantity",
            decision.executed_quantity, "quantity", decision.occurred_at,
            "execution", execution_ref, "actual_final_exit_execution",
        ),
    )
    return _trace(
        evidence_id=None,
        subject_ref=decision.decision_id,
        concept=concept,
        as_of=decision.occurred_at,
        calculation_status="complete",
        result=decision.decision_type,
        inputs=inputs,
        operations=(),
        observation_window=ObservationWindow(decision.occurred_at, decision.occurred_at),
        source_refs=(execution_ref, f"decision:{decision.decision_id}"),
        provenance=(),
        limitations=concept.limitations,
        calculation_code_version=calculation_code_version,
        available_observation={"decision_type": decision.decision_type},
    )


def get_calculation_trace(
    record: EvidenceRecord,
    source_evidence: object,
    *,
    as_of: pd.Timestamp | None = None,
) -> CalculationTrace:
    """Build a trace only from its matching deterministic source result."""

    _ensure_available(record, as_of)
    if isinstance(source_evidence, PortfolioConcentrationEvidence):
        return build_hhi_trace(record, source_evidence)
    if isinstance(source_evidence, TurnoverIntensityEvidence):
        return build_turnover_trace(record, source_evidence)
    if isinstance(source_evidence, LossAveragingEvidence):
        return build_loss_state_addition_trace(record, source_evidence)
    if isinstance(source_evidence, SizingDecisionEvidence):
        return build_sizing_trace(record, source_evidence)
    if isinstance(source_evidence, ExitTimingEvidence):
        return build_exit_fixed_window_trace(record, source_evidence)
    if isinstance(source_evidence, DecisionEvidenceStatistics):
        return build_statistics_trace(record, source_evidence)
    raise ExplainabilityError(
        f"No CalculationTrace builder exists for {type(source_evidence).__name__}"
    )


def build_explainability_view(
    record: EvidenceRecord,
    source_evidence: object,
    *,
    as_of: pd.Timestamp | None = None,
) -> EvidenceExplainabilityView:
    """Return Concept + original result + trace + policy boundaries."""

    trace = get_calculation_trace(record, source_evidence, as_of=as_of)
    concept = (
        get_concept("decision_evidence_hit_rate")
        if record.method_id == STATISTICS_METHOD_ID
        else get_concept_for_evidence(record)
    )
    if trace.concept_id != concept.concept_id:
        raise ExplainabilityError("CalculationTrace concept does not match EvidenceRecord")
    return EvidenceExplainabilityView(
        evidence_id=record.evidence_id,
        concept=concept,
        result=EvidenceResultSnapshot(
            value=record.value,
            numerator=record.numerator,
            denominator=record.denominator,
            observation_count=record.observation_count,
            ci_lower=record.ci_lower,
            ci_upper=record.ci_upper,
            evidence_status=record.evidence_status,
            evidence_reason=record.evidence_reason,
        ),
        calculation_trace=trace,
        provenance=record.provenance,
        limitations=record.limitations,
        interpretation_boundary=concept.interpretation_boundary,
    )
