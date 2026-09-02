"""Transparent historical counts for deterministic Decision Evidence.

This module does not perform attribution.  It only maps already-classified
Sizing and Exit evidence into observations and summarizes those observations.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Iterable, Literal, Mapping

import pandas as pd
from scipy.stats import binomtest

if TYPE_CHECKING:
    from src.attribution.exit_timing_evidence import ExitTimingEvidence
    from src.attribution.sizing_evidence import SizingDecisionEvidence


DecisionOutcome = Literal["positive", "negative", "matched", "insufficient"]
StatisticsStatus = Literal["available", "insufficient_evidence"]

INTERVAL_METHOD: Final = "wilson_95_scipy"
HIT_RATE_DEFINITION: Final = (
    "Hit rate is positive_n / valid_n. Matched observations are valid but are "
    "not positive; insufficient observations are excluded from valid_n."
)
LIMITATION_NOTICE: Final = (
    "The Wilson interval is a binomial proportion confidence interval for the "
    "historical positive-decision proportion. It is not the user's future "
    "success probability, an investment-skill probability, a prediction "
    "interval, or a guarantee of future performance."
)
_OUTCOMES: Final = frozenset(
    {"positive", "negative", "matched", "insufficient"}
)
_SIZING_OUTCOMES: Final = {
    "outperformed_baseline": "positive",
    "underperformed_baseline": "negative",
    "matched_baseline": "matched",
}
_EXIT_OUTCOMES: Final = {
    "actual_exit_outperformed_hold_baseline": "positive",
    "actual_exit_underperformed_hold_baseline": "negative",
    "matched_hold_baseline": "matched",
}


@dataclass(frozen=True, slots=True)
class DecisionObservation:
    """One outcome already classified by a deterministic Evidence module."""

    decision_type: str
    decision_time: pd.Timestamp | None
    source_id: str
    outcome: DecisionOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, str) or not self.decision_type.strip():
            raise ValueError("decision_type must be a non-empty string")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if self.outcome not in _OUTCOMES:
            raise ValueError(f"Unsupported decision outcome: {self.outcome!r}")

        decision_time = self.decision_time
        if decision_time is not None:
            try:
                decision_time = pd.Timestamp(decision_time)
            except (TypeError, ValueError) as exc:
                raise ValueError("decision_time must be a timestamp or None") from exc
            if pd.isna(decision_time):
                decision_time = None
        if decision_time is None and self.outcome != "insufficient":
            raise ValueError("A valid observation must have a decision_time")

        object.__setattr__(self, "decision_type", self.decision_type.strip())
        object.__setattr__(self, "source_id", self.source_id.strip())
        object.__setattr__(self, "decision_time", decision_time)


@dataclass(frozen=True, slots=True)
class DecisionEvidenceStatistics:
    """Historical evidence volume and positive-outcome proportion.

    Dates span all observations that carry a decision timestamp, including
    insufficient observations.  No skill or future-performance claim is made.
    """

    decision_type: str
    total_observations: int
    valid_n: int
    insufficient_n: int
    positive_n: int
    negative_n: int
    matched_n: int
    hit_rate: float | None
    hit_rate_ci95_low: float | None
    hit_rate_ci95_high: float | None
    interval_method: str
    first_observation_time: pd.Timestamp | None
    last_observation_time: pd.Timestamp | None
    date_span_days: int | None
    evidence_status: StatisticsStatus
    evidence_reason: str | None
    hit_rate_definition: str
    limitation_notice: str


def _mapped_outcome(
    *,
    evidence_status: str,
    comparison: str | None,
    outcomes: Mapping[str, DecisionOutcome],
    evidence_name: str,
) -> DecisionOutcome:
    if evidence_status == "insufficient_evidence":
        return "insufficient"
    if evidence_status != "complete":
        raise ValueError(
            f"Unsupported {evidence_name} evidence status: {evidence_status!r}"
        )
    try:
        return outcomes[comparison]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported complete {evidence_name} comparison: {comparison!r}"
        ) from exc


def sizing_evidence_to_observation(
    evidence: SizingDecisionEvidence,
) -> DecisionObservation:
    """Map Sizing evidence semantics without recomputing its comparison."""

    decision_time = pd.Timestamp(evidence.decision_time)
    return DecisionObservation(
        decision_type="sizing",
        decision_time=decision_time,
        source_id=f"sizing-decision:{decision_time.isoformat()}",
        outcome=_mapped_outcome(
            evidence_status=evidence.evidence_status,
            comparison=evidence.comparison,
            outcomes=_SIZING_OUTCOMES,
            evidence_name="Sizing",
        ),
    )


def exit_timing_evidence_to_observation(
    evidence: ExitTimingEvidence,
) -> DecisionObservation:
    """Map Exit evidence semantics without recomputing its comparison."""

    return DecisionObservation(
        decision_type="exit_timing",
        decision_time=evidence.actual_exit_time,
        source_id=evidence.episode_id,
        outcome=_mapped_outcome(
            evidence_status=evidence.evidence_status,
            comparison=evidence.comparison,
            outcomes=_EXIT_OUTCOMES,
            evidence_name="Exit",
        ),
    )


def build_decision_evidence_statistics(
    observations: Iterable[DecisionObservation],
    *,
    decision_type: str | None = None,
) -> DecisionEvidenceStatistics:
    """Summarize one decision type and delegate its Wilson interval to SciPy.

    ``decision_type`` is only needed when an empty collection must be represented.
    Mixed decision types are rejected rather than silently pooled.
    """

    items = tuple(observations)
    if any(not isinstance(item, DecisionObservation) for item in items):
        raise TypeError("observations must contain DecisionObservation values")

    if decision_type is not None:
        if not isinstance(decision_type, str) or not decision_type.strip():
            raise ValueError("decision_type must be a non-empty string")
        decision_type = decision_type.strip()

    observed_types = {item.decision_type for item in items}
    if len(observed_types) > 1:
        raise ValueError("observations must all have the same decision_type")
    if observed_types:
        observed_type = next(iter(observed_types))
        if decision_type is not None and decision_type != observed_type:
            raise ValueError("decision_type does not match the observations")
        decision_type = observed_type
    if decision_type is None:
        raise ValueError("decision_type is required for an empty observation set")

    counts = Counter(item.outcome for item in items)
    positive_n = counts["positive"]
    negative_n = counts["negative"]
    matched_n = counts["matched"]
    insufficient_n = counts["insufficient"]
    valid_n = positive_n + negative_n + matched_n

    times = [item.decision_time for item in items if item.decision_time is not None]
    first_time = min(times) if times else None
    last_time = max(times) if times else None
    date_span_days = (
        int((last_time.normalize() - first_time.normalize()).days)
        if first_time is not None and last_time is not None
        else None
    )

    if valid_n == 0:
        hit_rate = None
        ci_low = None
        ci_high = None
        evidence_status: StatisticsStatus = "insufficient_evidence"
        evidence_reason = "No valid positive, negative, or matched observations"
    else:
        hit_rate = positive_n / valid_n
        interval = binomtest(positive_n, valid_n).proportion_ci(
            confidence_level=0.95,
            method="wilson",
        )
        ci_low = float(interval.low)
        ci_high = float(interval.high)
        evidence_status = "available"
        evidence_reason = None

    return DecisionEvidenceStatistics(
        decision_type=decision_type,
        total_observations=len(items),
        valid_n=valid_n,
        insufficient_n=insufficient_n,
        positive_n=positive_n,
        negative_n=negative_n,
        matched_n=matched_n,
        hit_rate=hit_rate,
        hit_rate_ci95_low=ci_low,
        hit_rate_ci95_high=ci_high,
        interval_method=INTERVAL_METHOD,
        first_observation_time=first_time,
        last_observation_time=last_time,
        date_span_days=date_span_days,
        evidence_status=evidence_status,
        evidence_reason=evidence_reason,
        hit_rate_definition=HIT_RATE_DEFINITION,
        limitation_notice=LIMITATION_NOTICE,
    )
