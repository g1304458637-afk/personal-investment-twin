"""Small, queryable registry for evidence method specifications."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

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
from src.evidence.contracts import canonical_json_bytes, freeze_json_mapping


METHOD_VERSION_V1: Final = "1"
EVIDENCE_PRODUCER: Final = "personal-investment-twin"
SELECTION_METHOD_ID: Final = "selection_episode_twr_vs_benchmarks_v1"
SIZING_METHOD_ID: Final = "equal_weight_sizing_counterfactual_v1"
EXIT_METHOD_ID: Final = "hold_20_sessions_v1"
FRICTION_METHOD_ID: Final = "zero_recorded_fee_counterfactual_v1"
STATISTICS_METHOD_ID: Final = "decision_evidence_statistics_v1"
REGISTRY_REVISION: Final = 1


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
