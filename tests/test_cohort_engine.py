from __future__ import annotations

import pytest

from src.cohort.engine import (
    PERCENTILE_METHOD,
    QUANTILE_METHOD,
    build_peer_benchmark_results,
    exact_cohort_members,
)
from src.cohort.models import CohortDefinition, CohortMember, PeerMetricValue


HHI = "portfolio_concentration_hhi"
TURNOVER = "mean_daily_turnover"


def _definition(*, minimum: int = 30) -> CohortDefinition:
    return CohortDefinition(
        cohort_id="synthetic-cn-equity-v1",
        market="synthetic_cn_equity",
        asset_types=("equity",),
        direction="long",
        observation_start="2025-01-02",
        observation_end="2025-01-08",
        leverage_allowed=False,
        data_tier="synthetic",
        min_descriptive_n=minimum,
        description="Deterministic synthetic cohort",
        limitations=("Synthetic demo only",),
    )


def _members(count: int = 30) -> tuple[CohortMember, ...]:
    definition = _definition()
    return tuple(
        CohortMember(
            subject_id=f"peer-{index:02d}",
            market=definition.market,
            asset_types=definition.asset_types,
            direction=definition.direction,
            observation_start=definition.observation_start,
            observation_end=definition.observation_end,
            leverage=False,
            data_tier="synthetic",
            data_quality_status="complete",
        )
        for index in range(count)
    )


def _value(subject_id: str, metric: str, value: float | None, *, status: str = "complete", as_of: str = "2025-01-08") -> PeerMetricValue:
    return PeerMetricValue(subject_id, metric, value, status, f"evidence-{subject_id}-{metric}", as_of)


def test_exact_members_filter_every_declared_dimension() -> None:
    definition = _definition()
    good = _members(1)[0]
    wrong_window = CohortMember(
        **{name: getattr(good, name) for name in good.__dataclass_fields__} | {"observation_end": "2025-01-07"}
    )
    assert exact_cohort_members(definition, (good, wrong_window)) == (good,)


def test_synthetic_cohort_rejects_any_non_synthetic_member() -> None:
    member = _members(1)[0]
    mixed = CohortMember(
        **{name: getattr(member, name) for name in member.__dataclass_fields__} | {"subject_id": "bad", "data_tier": "production"}
    )
    with pytest.raises(ValueError, match="non-synthetic"):
        exact_cohort_members(_definition(), (member, mixed))


def test_cohort_v1_rejects_a_non_synthetic_definition() -> None:
    definition = _definition()
    non_synthetic = CohortDefinition(
        **{
            name: getattr(definition, name)
            for name in definition.__dataclass_fields__
        }
        | {"data_tier": "production"}
    )

    with pytest.raises(ValueError, match="only the synthetic"):
        exact_cohort_members(non_synthetic, ())


@pytest.mark.parametrize("n", [0, 1, 29])
def test_small_metric_sample_is_insufficient(n: int) -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, float(index)) for index, member in enumerate(members[:n]))
    result = build_peer_benchmark_results(definition, members, peers, (_value("subject", HHI, 4.0),), subject_id="subject")[0]
    assert result.benchmark_status == "insufficient_cohort"
    assert result.metric_n == n
    assert (result.p25, result.median, result.p75, result.percentile) == (None, None, None, None)


def test_n_30_uses_linear_quantiles_and_rank_percentile_deterministically() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, float(index + 1)) for index, member in enumerate(members))
    subject = (_value("subject", HHI, 15.0),)
    first = build_peer_benchmark_results(definition, members, peers, subject, subject_id="subject")
    second = build_peer_benchmark_results(definition, members, peers, subject, subject_id="subject")
    result = first[0]
    assert first == second
    assert (result.p25, result.median, result.p75) == (8.25, 15.5, 22.75)
    assert result.percentile == 50.0
    assert result.quantile_method == QUANTILE_METHOD
    assert result.percentile_method == PERCENTILE_METHOD


def test_rank_percentile_preserves_tie_semantics() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, 2.0 if index < 20 else 4.0) for index, member in enumerate(members))
    result = build_peer_benchmark_results(definition, members, peers, (_value("subject", HHI, 2.0),), subject_id="subject")[0]
    assert result.percentile == pytest.approx(35.0)


def test_subject_value_need_not_appear_in_peer_distribution() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(
        _value(member.subject_id, HHI, float(index + 1))
        for index, member in enumerate(members)
    )

    result = build_peer_benchmark_results(
        definition,
        members,
        peers,
        (_value("subject", HHI, 15.25),),
        subject_id="subject",
    )[0]

    assert 15.25 not in {item.value for item in peers}
    assert result.benchmark_status == "complete"
    assert result.subject_value == 15.25
    assert result.percentile == pytest.approx(50.0)


def test_peer_v1_rejects_unsupported_metrics() -> None:
    with pytest.raises(ValueError, match="does not support"):
        build_peer_benchmark_results(
            _definition(),
            _members(30),
            (),
            (_value("subject", "invented_score", 1.0),),
            subject_id="subject",
        )


def test_member_can_vote_once_per_metric() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, float(index)) for index, member in enumerate(members))
    with pytest.raises(ValueError, match="one value"):
        build_peer_benchmark_results(
            definition, members, peers + (_value(members[0].subject_id, HHI, 99.0),),
            (_value("subject", HHI, 1.0),), subject_id="subject"
        )


def test_metric_eligibility_is_independent_and_missing_values_do_not_change_cohort_n() -> None:
    definition = _definition()
    members = _members(30)
    hhi = tuple(_value(member.subject_id, HHI, float(index)) for index, member in enumerate(members))
    turnover = tuple(_value(member.subject_id, TURNOVER, None, status="insufficient_evidence") for member in members[:3])
    results = build_peer_benchmark_results(
        definition, members, hhi + turnover,
        (_value("subject", HHI, 1.0), _value("subject", TURNOVER, 1.0)), subject_id="subject"
    )
    assert [(result.cohort_n, result.metric_n, result.benchmark_status) for result in results] == [
        (30, 30, "complete"), (30, 0, "insufficient_cohort")
    ]


def test_invalid_or_misaligned_evidence_is_not_eligible() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, float(index), as_of="2025-01-07") for index, member in enumerate(members))
    result = build_peer_benchmark_results(definition, members, peers, (_value("subject", HHI, 1.0),), subject_id="subject")[0]
    assert result.metric_n == 0
    assert result.benchmark_status == "insufficient_cohort"


def test_subject_must_be_outside_cohort_and_subject_metric_must_match() -> None:
    definition = _definition()
    members = _members(30)
    peers = tuple(_value(member.subject_id, HHI, float(index)) for index, member in enumerate(members))
    with pytest.raises(ValueError, match="must not"):
        build_peer_benchmark_results(definition, members, peers, (_value(members[0].subject_id, HHI, 1.0),), subject_id=members[0].subject_id)
    with pytest.raises(ValueError, match="belong"):
        build_peer_benchmark_results(definition, members, peers, (_value("other", HHI, 1.0),), subject_id="subject")
