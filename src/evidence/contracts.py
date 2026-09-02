"""Stable, JSON-safe product contract for deterministic evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

import pandas as pd


EVIDENCE_SCHEMA_VERSION: Final = "1"
EVIDENCE_ID_PREFIX: Final = "ev_"

EvidenceStatus = Literal[
    "complete",
    "partial",
    "insufficient_evidence",
    "experimental",
]
DataTier = Literal["synthetic", "demo", "authorized_beta", "production"]

_EVIDENCE_STATUSES: Final = frozenset(
    {"complete", "partial", "insufficient_evidence", "experimental"}
)
_DATA_TIERS: Final = frozenset(
    {"synthetic", "demo", "authorized_beta", "production"}
)
_SYNTHETIC_DATA_TIERS: Final = frozenset({"synthetic", "demo"})
_EVIDENCE_ID_PATTERN: Final = re.compile(r"^ev_[0-9a-f]{64}$")


class _FrozenJsonDict(dict[str, object]):
    """JSON-serializable dict whose normal mutation APIs are disabled."""

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("JSON mapping is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _optional_timestamp(value: object, field_name: str) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a timestamp or None") from exc
    if pd.isna(timestamp):
        raise ValueError(f"{field_name} cannot be NaT")
    return timestamp


def _finite_number(value: object, field_name: str, *, allow_text: bool = False) -> None:
    if value is None:
        return
    if allow_text and isinstance(value, str):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a finite number or None")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")


def _json_safe(value: object, path: str = "$") -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            normalized[key] = _json_safe(item, f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains a non-JSON-safe value: {type(value).__name__}")


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return _FrozenJsonDict(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def freeze_json_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Validate and deeply freeze a JSON-safe mapping."""

    normalized = _json_safe(value)
    if not isinstance(normalized, dict):
        raise TypeError("value must be a mapping")
    frozen = _freeze_json(normalized)
    if not isinstance(frozen, Mapping):  # pragma: no cover - defensive invariant
        raise TypeError("value must be a mapping")
    return frozen


def canonical_json_bytes(value: object) -> bytes:
    """Return project-local deterministic JSON bytes.

    This intentionally supports only JSON-safe values, emits UTF-8 without
    whitespace, rejects non-finite floats, and recursively sorts object keys.
    It is not a complete RFC 8785 / JCS implementation.
    """

    normalized = _json_safe(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    source_type: str
    source_name: str
    data_version: str
    as_of: pd.Timestamp | None
    price_type: str | None
    is_synthetic: bool
    source_id: str | None = None
    instrument: str | None = None
    benchmark_id: str | None = None
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_type", _required_text(self.source_type, "source_type"))
        object.__setattr__(self, "source_name", _required_text(self.source_name, "source_name"))
        object.__setattr__(self, "data_version", _required_text(self.data_version, "data_version"))
        object.__setattr__(self, "as_of", _optional_timestamp(self.as_of, "as_of"))
        object.__setattr__(self, "price_type", _optional_text(self.price_type, "price_type"))
        if not isinstance(self.is_synthetic, bool):
            raise TypeError("is_synthetic must be bool")
        for field_name in ("source_id", "instrument", "benchmark_id"):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name), field_name),
            )
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        object.__setattr__(self, "attributes", freeze_json_mapping(self.attributes))

    def identity_payload(self) -> dict[str, object]:
        """Return stable source identity, excluding descriptive attributes."""

        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "data_version": self.data_version,
            "as_of": self.as_of.isoformat() if self.as_of is not None else None,
            "price_type": self.price_type,
            "is_synthetic": self.is_synthetic,
            "source_id": self.source_id,
            "instrument": self.instrument,
            "benchmark_id": self.benchmark_id,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    subject_id: str
    metric_id: str
    evidence_kind: str
    method_id: str
    method_version: str
    observation_start: pd.Timestamp | None
    observation_end: pd.Timestamp | None
    as_of: pd.Timestamp | None
    value: int | float | str | bool | None
    numerator: int | float | None
    denominator: int | float | str | None
    observation_count: int | None
    ci_lower: float | None
    ci_upper: float | None
    evidence_status: EvidenceStatus
    evidence_reason: str | None
    provenance: tuple[EvidenceProvenance, ...]
    data_tier: DataTier
    calculation_code_version: str
    limitations: tuple[str, ...]
    attributes: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not _EVIDENCE_ID_PATTERN.fullmatch(
            self.evidence_id
        ):
            raise ValueError("evidence_id must be ev_ followed by a SHA-256 hex digest")
        for field_name in (
            "subject_id",
            "metric_id",
            "evidence_kind",
            "method_id",
            "method_version",
            "calculation_code_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        for field_name in ("observation_start", "observation_end", "as_of"):
            object.__setattr__(
                self,
                field_name,
                _optional_timestamp(getattr(self, field_name), field_name),
            )
        if self.observation_start is not None and self.observation_end is not None:
            if self.observation_end < self.observation_start:
                raise ValueError("observation_end cannot precede observation_start")

        if not isinstance(self.value, (str, bool, int, float, type(None))):
            raise TypeError("value must be a JSON scalar")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("value must be finite")
        _finite_number(self.numerator, "numerator")
        _finite_number(self.denominator, "denominator", allow_text=True)
        if self.observation_count is not None:
            if isinstance(self.observation_count, bool) or not isinstance(
                self.observation_count, int
            ):
                raise TypeError("observation_count must be an integer or None")
            if self.observation_count < 0:
                raise ValueError("observation_count cannot be negative")
        _finite_number(self.ci_lower, "ci_lower")
        _finite_number(self.ci_upper, "ci_upper")

        if self.evidence_status not in _EVIDENCE_STATUSES:
            raise ValueError(f"Unsupported evidence_status: {self.evidence_status!r}")
        object.__setattr__(
            self,
            "evidence_reason",
            _optional_text(self.evidence_reason, "evidence_reason"),
        )
        provenance = tuple(self.provenance)
        if any(not isinstance(item, EvidenceProvenance) for item in provenance):
            raise TypeError("provenance must contain EvidenceProvenance values")
        object.__setattr__(self, "provenance", provenance)
        if self.data_tier not in _DATA_TIERS:
            raise ValueError(f"Unsupported data_tier: {self.data_tier!r}")
        if any(item.is_synthetic for item in provenance):
            if self.data_tier not in _SYNTHETIC_DATA_TIERS:
                raise ValueError(
                    "Synthetic provenance is allowed only for synthetic or demo data tiers"
                )

        limitations = tuple(self.limitations)
        if any(not isinstance(item, str) or not item.strip() for item in limitations):
            raise ValueError("limitations must contain non-empty strings")
        object.__setattr__(self, "limitations", tuple(item.strip() for item in limitations))
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        object.__setattr__(self, "attributes", freeze_json_mapping(self.attributes))


def evidence_identity_payload(
    *,
    subject_id: str,
    metric_id: str,
    evidence_kind: str,
    method_id: str,
    method_version: str,
    calculation_code_version: str,
    observation_start: pd.Timestamp | None,
    observation_end: pd.Timestamp | None,
    as_of: pd.Timestamp | None,
    value: int | float | str | bool | None,
    numerator: int | float | None,
    denominator: int | float | str | None,
    observation_count: int | None,
    evidence_status: EvidenceStatus,
    provenance: tuple[EvidenceProvenance, ...],
    identity_attributes: Mapping[str, object],
) -> dict[str, object]:
    """Build the deliberately bounded payload that determines evidence identity."""

    provenance_identity = [item.identity_payload() for item in provenance]
    provenance_identity.sort(key=canonical_json_bytes)
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "subject_id": subject_id,
        "metric_id": metric_id,
        "evidence_kind": evidence_kind,
        "method_id": method_id,
        "method_version": method_version,
        "calculation_code_version": calculation_code_version,
        "observation_start": (
            observation_start.isoformat() if observation_start is not None else None
        ),
        "observation_end": (
            observation_end.isoformat() if observation_end is not None else None
        ),
        "as_of": as_of.isoformat() if as_of is not None else None,
        "value_identity": {
            "value": value,
            "numerator": numerator,
            "denominator": denominator,
            "observation_count": observation_count,
            "evidence_status": evidence_status,
            "attributes": identity_attributes,
        },
        "provenance": provenance_identity,
    }


def create_evidence_record(
    *,
    subject_id: str,
    metric_id: str,
    evidence_kind: str,
    method_id: str,
    method_version: str,
    observation_start: pd.Timestamp | None,
    observation_end: pd.Timestamp | None,
    as_of: pd.Timestamp | None,
    value: int | float | str | bool | None,
    numerator: int | float | None,
    denominator: int | float | str | None,
    observation_count: int | None,
    ci_lower: float | None,
    ci_upper: float | None,
    evidence_status: EvidenceStatus,
    evidence_reason: str | None,
    provenance: tuple[EvidenceProvenance, ...],
    data_tier: DataTier,
    calculation_code_version: str,
    limitations: tuple[str, ...],
    attributes: Mapping[str, object],
    identity_attributes: Mapping[str, object],
) -> EvidenceRecord:
    """Create an immutable record and derive its ID from the bounded identity."""

    normalized_start = _optional_timestamp(observation_start, "observation_start")
    normalized_end = _optional_timestamp(observation_end, "observation_end")
    normalized_as_of = _optional_timestamp(as_of, "as_of")
    normalized_provenance = tuple(provenance)
    identity = evidence_identity_payload(
        subject_id=_required_text(subject_id, "subject_id"),
        metric_id=_required_text(metric_id, "metric_id"),
        evidence_kind=_required_text(evidence_kind, "evidence_kind"),
        method_id=_required_text(method_id, "method_id"),
        method_version=_required_text(method_version, "method_version"),
        calculation_code_version=_required_text(
            calculation_code_version,
            "calculation_code_version",
        ),
        observation_start=normalized_start,
        observation_end=normalized_end,
        as_of=normalized_as_of,
        value=value,
        numerator=numerator,
        denominator=denominator,
        observation_count=observation_count,
        evidence_status=evidence_status,
        provenance=normalized_provenance,
        identity_attributes=identity_attributes,
    )
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return EvidenceRecord(
        evidence_id=f"{EVIDENCE_ID_PREFIX}{digest}",
        subject_id=subject_id,
        metric_id=metric_id,
        evidence_kind=evidence_kind,
        method_id=method_id,
        method_version=method_version,
        observation_start=normalized_start,
        observation_end=normalized_end,
        as_of=normalized_as_of,
        value=value,
        numerator=numerator,
        denominator=denominator,
        observation_count=observation_count,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        evidence_status=evidence_status,
        evidence_reason=evidence_reason,
        provenance=normalized_provenance,
        data_tier=data_tier,
        calculation_code_version=calculation_code_version,
        limitations=limitations,
        attributes=attributes,
    )
