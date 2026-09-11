"""Bounded, point-in-time fund lookthrough for comparison allocation views.

This module deliberately starts with *authoritative account weights*.  It does
not replay a ledger, value positions, infer classifications, or reuse the
risky-assets-only HHI denominator.  A result is consequently a descriptive
allocation projection, rather than an accounting or performance calculation.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal, Sequence

import pandas as pd

from src.evidence.contracts import canonical_json_bytes


METHOD_ID = "dated_fund_lookthrough_v1"
METHOD_VERSION = "1"
EPSILON = 1e-12

PositionKind = Literal["cash", "security", "fund", "unknown"]
CyclePolicy = Literal["raise", "unknown"]


def _timestamp(value: object, field: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError(f"{field} must be a real timestamp")
    return stamp


def _weight(value: float, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < -EPSILON or number > 1 + EPSILON:
        raise ValueError(f"{field} must be a finite weight in [0, 1]")
    return 0.0 if abs(number) <= EPSILON else number


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


@dataclass(frozen=True, slots=True)
class AccountPosition:
    """One authoritative account allocation observation.

    ``weight`` is supplied by the account-state source and is never recomputed
    here.  ``observed_at`` describes when that state was observed; it is not a
    price date.
    """

    asset_id: str
    kind: PositionKind
    weight: float
    observed_at: pd.Timestamp
    source_id: str

    def __post_init__(self) -> None:
        _required(self.asset_id, "asset_id")
        if self.kind not in ("cash", "security", "fund", "unknown"):
            raise ValueError("unsupported position kind")
        object.__setattr__(self, "weight", _weight(self.weight, "position weight"))
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))
        _required(self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class FundMembership:
    """A dated constituent of a fund disclosure.

    A disclosure can be used only after all three relevant facts are true: it
    was effective, published, and observed by ``as_of``.  Rows sharing the
    same (fund, effective, published, observed) form one disclosure version.
    """

    fund_id: str
    constituent_id: str
    constituent_kind: PositionKind
    weight: float
    effective_at: pd.Timestamp
    published_at: pd.Timestamp
    observed_at: pd.Timestamp
    source_id: str

    def __post_init__(self) -> None:
        _required(self.fund_id, "fund_id")
        _required(self.constituent_id, "constituent_id")
        if self.constituent_kind not in ("cash", "security", "fund", "unknown"):
            raise ValueError("fund constituents must be cash, security, fund, or unknown")
        object.__setattr__(self, "weight", _weight(self.weight, "membership weight"))
        for field in ("effective_at", "published_at", "observed_at"):
            object.__setattr__(self, field, _timestamp(getattr(self, field), field))
        _required(self.source_id, "source_id")

    @property
    def available_at(self) -> pd.Timestamp:
        """Alias used by callers that call publication the availability date."""
        return self.published_at


@dataclass(frozen=True, slots=True)
class Classification:
    """Historically dated security classification; absent labels stay absent."""

    asset_id: str
    sector: str | None
    region: str | None
    effective_at: pd.Timestamp
    published_at: pd.Timestamp
    observed_at: pd.Timestamp
    source_id: str

    def __post_init__(self) -> None:
        _required(self.asset_id, "asset_id")
        for label in (self.sector, self.region):
            if label is not None and not isinstance(label, str):
                raise ValueError("classification labels must be strings or None")
        for field in ("effective_at", "published_at", "observed_at"):
            object.__setattr__(self, field, _timestamp(getattr(self, field), field))
        _required(self.source_id, "source_id")

    @property
    def available_at(self) -> pd.Timestamp:
        return self.published_at


# A more explicit name is useful to adapters, while retaining the short public
# name above for ergonomic direct construction.
SecurityClassification = Classification


@dataclass(frozen=True, slots=True)
class LookthroughPath:
    """One direct or indirect contribution to an output exposure."""

    weight: float
    direct: bool
    asset_path: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FundDisclosureProvenance:
    """The exact dated disclosure version used while expanding one fund."""

    fund_id: str
    effective_at: pd.Timestamp
    published_at: pd.Timestamp
    observed_at: pd.Timestamp
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Exposure:
    asset_id: str
    kind: PositionKind
    weight: float
    direct_weight: float
    indirect_weight: float
    paths: tuple[LookthroughPath, ...]
    classification: Classification | None = None

    @property
    def sector(self) -> str | None:
        return None if self.classification is None else self.classification.sector

    @property
    def region(self) -> str | None:
        return None if self.classification is None else self.classification.region


@dataclass(frozen=True, slots=True)
class ClassificationComponent:
    label: str
    weight: float
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassificationBreakdown:
    dimension: Literal["sector", "region"]
    denominator_weight: float
    classified_weight: float
    unclassified_weight: float
    components: tuple[ClassificationComponent, ...]


@dataclass(frozen=True, slots=True)
class LookthroughResult:
    lookthrough_id: str
    method_id: str
    method_version: str
    as_of: pd.Timestamp
    max_depth: int
    selected_disclosures: tuple[FundDisclosureProvenance, ...]
    exposures: tuple[Exposure, ...]
    sector_breakdown: ClassificationBreakdown
    region_breakdown: ClassificationBreakdown

    @property
    def security_exposures(self) -> tuple[Exposure, ...]:
        return tuple(item for item in self.exposures if item.kind == "security")

    @property
    def total_weight(self) -> float:
        return math.fsum(item.weight for item in self.exposures)


class LookthroughCycleError(ValueError):
    """Raised when a selected fund disclosure contains a fund cycle."""


def _version_key(item: FundMembership) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    return item.effective_at, item.published_at, item.observed_at


def _available_memberships(
    memberships: Sequence[FundMembership], as_of: pd.Timestamp,
) -> dict[str, tuple[FundMembership, ...]]:
    """Select exactly the most recent disclosure known at ``as_of`` per fund."""
    by_fund: dict[str, list[FundMembership]] = defaultdict(list)
    for item in memberships:
        if item.effective_at <= as_of and item.published_at <= as_of and item.observed_at <= as_of:
            by_fund[item.fund_id].append(item)
    selected: dict[str, tuple[FundMembership, ...]] = {}
    for fund_id, items in by_fund.items():
        latest = max(_version_key(item) for item in items)
        version = tuple(sorted(
            (item for item in items if _version_key(item) == latest),
            key=lambda item: (item.constituent_kind, item.constituent_id, item.source_id),
        ))
        # A repeated constituent in a disclosure is ambiguous rather than an
        # invitation to silently add two weights.
        identities = [(item.constituent_kind, item.constituent_id) for item in version]
        if len(identities) != len(set(identities)):
            raise ValueError(f"duplicate constituent in selected disclosure for {fund_id}")
        total = math.fsum(item.weight for item in version)
        if total > 1 + EPSILON:
            raise ValueError(f"selected disclosure weights exceed one for {fund_id}")
        selected[fund_id] = version
    return selected


def _unknown_id(parent_id: str, reason: str) -> str:
    # This is a display identity for unallocated coverage, never an instrument.
    return f"unknown:{parent_id}:{reason}"


def _classification_for(
    asset_id: str, classifications: Sequence[Classification], as_of: pd.Timestamp,
) -> Classification | None:
    candidates = [
        item for item in classifications
        if item.asset_id == asset_id
        and item.effective_at <= as_of and item.published_at <= as_of and item.observed_at <= as_of
    ]
    if not candidates:
        return None
    # Same effective/publication/observation version from different sources is
    # conflicting unless it says the same thing; source selection must be made
    # outside this projection.
    latest = max((item.effective_at, item.published_at, item.observed_at) for item in candidates)
    choices = [item for item in candidates
               if (item.effective_at, item.published_at, item.observed_at) == latest]
    labels = {(item.sector, item.region) for item in choices}
    if len(labels) != 1:
        raise ValueError(f"conflicting selected classification for {asset_id}")
    return sorted(choices, key=lambda item: item.source_id)[0]


def _breakdown(
    dimension: Literal["sector", "region"], exposures: Sequence[Exposure],
) -> ClassificationBreakdown:
    securities = [item for item in exposures if item.kind == "security"]
    denominator = math.fsum(item.weight for item in securities)
    grouped: dict[str, list[Exposure]] = defaultdict(list)
    unclassified = 0.0
    for item in securities:
        label = None if item.classification is None else getattr(item.classification, dimension)
        if label is None:
            unclassified += item.weight
        else:
            grouped[label].append(item)
    components = tuple(
        ClassificationComponent(
            label, math.fsum(item.weight for item in items),
            tuple(sorted({item.classification.source_id for item in items if item.classification})),
        )
        for label, items in sorted(grouped.items())
    )
    return ClassificationBreakdown(
        dimension, denominator, math.fsum(item.weight for item in securities) - unclassified,
        unclassified, components,
    )


def build_lookthrough(
    positions: Sequence[AccountPosition], memberships: Sequence[FundMembership], *,
    as_of: pd.Timestamp, max_depth: int = 1,
    classifications: Sequence[Classification] = (), cycle_policy: CyclePolicy = "raise",
) -> LookthroughResult:
    """Expand authoritative fund weights through known disclosures, at most ``max_depth``.

    A fund is removed only when it is actually expanded.  Missing disclosure
    coverage becomes an explicit ``unknown:*`` exposure; known constituents
    are never rescaled to make a pie look complete.  At the depth boundary a
    nested fund remains a fund exposure, which preserves conservation without
    pretending to know its underlying securities.
    """
    cutoff = _timestamp(as_of, "as_of")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a non-negative integer")
    if cycle_policy not in ("raise", "unknown"):
        raise ValueError("unsupported cycle policy")
    normalized_positions = tuple(sorted(positions, key=lambda item: (
        item.kind, item.asset_id, item.source_id, item.observed_at.isoformat(), item.weight,
    )))
    if not normalized_positions:
        raise ValueError("at least one authoritative account position is required")
    if any(item.observed_at > cutoff for item in normalized_positions):
        raise ValueError("account position was observed after as_of")
    position_keys = [(item.kind, item.asset_id) for item in normalized_positions]
    if len(position_keys) != len(set(position_keys)):
        raise ValueError("duplicate authoritative account position")
    if math.fsum(item.weight for item in normalized_positions) > 1 + EPSILON:
        raise ValueError("authoritative account weights exceed one")

    selected = _available_memberships(tuple(memberships), cutoff)
    paths_by_key: dict[tuple[PositionKind, str], list[LookthroughPath]] = defaultdict(list)
    used_disclosures: dict[str, FundDisclosureProvenance] = {}

    def add(kind: PositionKind, asset_id: str, weight: float, direct: bool,
            asset_path: tuple[str, ...], source_ids: tuple[str, ...]) -> None:
        if weight > EPSILON:
            paths_by_key[(kind, asset_id)].append(
                LookthroughPath(weight, direct, asset_path, source_ids)
            )

    def expand(kind: PositionKind, asset_id: str, weight: float, depth: int,
               asset_path: tuple[str, ...], source_ids: tuple[str, ...], direct: bool) -> None:
        if kind != "fund" or depth >= max_depth:
            add(kind, asset_id, weight, direct, asset_path, source_ids)
            return
        if asset_id in asset_path[:-1]:
            cycle = " -> ".join((*asset_path, asset_id))
            if cycle_policy == "raise":
                raise LookthroughCycleError(f"fund disclosure cycle: {cycle}")
            add("unknown", _unknown_id(asset_id, "cycle"), weight, False,
                (*asset_path, _unknown_id(asset_id, "cycle")), source_ids)
            return
        rows = selected.get(asset_id)
        if not rows:
            add("unknown", _unknown_id(asset_id, "not_disclosed"), weight, False,
                (*asset_path, _unknown_id(asset_id, "not_disclosed")), source_ids)
            return
        first = rows[0]
        used_disclosures[asset_id] = FundDisclosureProvenance(
            asset_id, first.effective_at, first.published_at, first.observed_at,
            tuple(sorted(item.source_id for item in rows)),
        )
        covered = math.fsum(item.weight for item in rows)
        for item in rows:
            expand(item.constituent_kind, item.constituent_id, weight * item.weight, depth + 1,
                   (*asset_path, item.constituent_id), (*source_ids, item.source_id), False)
        if covered < 1 - EPSILON:
            unknown = _unknown_id(asset_id, "uncovered")
            # The remainder is established by this selected disclosure, so its
            # source rows belong on the unknown path too; otherwise a consumer
            # cannot audit why the coverage stopped short of 100%.
            coverage_sources = tuple(item.source_id for item in rows)
            add("unknown", unknown, weight * (1 - covered), False,
                (*asset_path, unknown), (*source_ids, *coverage_sources))

    for position in normalized_positions:
        expand(position.kind, position.asset_id, position.weight, 0,
               (position.asset_id,), (position.source_id,), position.kind != "fund")

    exposures: list[Exposure] = []
    for (kind, asset_id), paths in sorted(paths_by_key.items(), key=lambda item: (item[0][0], item[0][1])):
        ordered_paths = tuple(sorted(paths, key=lambda item: (
            item.direct, item.asset_path, item.source_ids, item.weight,
        )))
        direct_weight = math.fsum(item.weight for item in ordered_paths if item.direct)
        indirect_weight = math.fsum(item.weight for item in ordered_paths if not item.direct)
        exposures.append(Exposure(
            asset_id, kind, direct_weight + indirect_weight, direct_weight, indirect_weight,
            ordered_paths,
            _classification_for(asset_id, classifications, cutoff) if kind == "security" else None,
        ))
    frozen_exposures = tuple(exposures)
    disclosures = tuple(used_disclosures[fund_id] for fund_id in sorted(used_disclosures))
    sector = _breakdown("sector", frozen_exposures)
    region = _breakdown("region", frozen_exposures)
    payload = {
        "method_id": METHOD_ID, "method_version": METHOD_VERSION, "as_of": cutoff.isoformat(),
        "max_depth": max_depth,
        "selected_disclosures": [
            {"fund_id": item.fund_id, "effective_at": item.effective_at.isoformat(),
             "published_at": item.published_at.isoformat(), "observed_at": item.observed_at.isoformat(),
             "source_ids": item.source_ids}
            for item in disclosures
        ],
        "exposures": [
            {"asset_id": item.asset_id, "kind": item.kind, "weight": item.weight,
             "direct_weight": item.direct_weight, "indirect_weight": item.indirect_weight,
             "paths": [{"weight": path.weight, "direct": path.direct,
                        "asset_path": path.asset_path, "source_ids": path.source_ids}
                       for path in item.paths],
             "classification": None if item.classification is None else {
                 "sector": item.classification.sector, "region": item.classification.region,
                 "effective_at": item.classification.effective_at.isoformat(),
                 "published_at": item.classification.published_at.isoformat(),
                 "observed_at": item.classification.observed_at.isoformat(),
                 "source_id": item.classification.source_id,
             }}
            for item in frozen_exposures
        ],
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return LookthroughResult("lookthrough_" + digest, METHOD_ID, METHOD_VERSION, cutoff, max_depth,
                             disclosures, frozen_exposures, sector, region)


# The verb-first alias keeps the boundary obvious in application services.
expand_lookthrough = build_lookthrough
