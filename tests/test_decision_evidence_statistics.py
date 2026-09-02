from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from scipy.stats import binomtest

from src.attribution import decision_evidence_statistics as statistics_module
from src.attribution.decision_evidence_statistics import (
    INTERVAL_METHOD,
    DecisionObservation,
    build_decision_evidence_statistics,
    exit_timing_evidence_to_observation,
    sizing_evidence_to_observation,
)
from src.attribution.exit_timing_evidence import (
    COUNTERFACTUAL_NOTICE,
    ExitTimingEvidence,
)
from src.attribution.sizing_evidence import SizingDecisionEvidence


DECISION_TIME = pd.Timestamp("2025-01-06 09:35:00")
EXIT_TIME = pd.Timestamp("2025-06-02 10:05:00")


def _sizing_evidence(
    comparison: str | None,
    *,
    status: str = "complete",
) -> SizingDecisionEvidence:
    return SizingDecisionEvidence(
        decision_time=DECISION_TIME,
        interval_end_time=pd.Timestamp("2025-02-10 09:35:00"),
        active_assets=("SYN_A", "SYN_B"),
        actual_weights={"SYN_A": 0.4, "SYN_B": 0.3},
        baseline_weights={"SYN_A": 0.35, "SYN_B": 0.35},
        risky_exposure=0.7,
        actual_start_value=100_000.0,
        baseline_start_value=100_000.0,
        actual_end_value=110_000.0,
        baseline_end_value=105_000.0,
        comparison=comparison,
        evidence_status=status,
        evidence_reason=("fixture is insufficient" if status != "complete" else None),
    )


def _exit_evidence(
    comparison: str | None,
    *,
    status: str = "complete",
    actual_exit_time: pd.Timestamp | None = EXIT_TIME,
) -> ExitTimingEvidence:
    return ExitTimingEvidence(
        episode_id="investment-episode:SYN_EXIT:0",
        symbol="SYN_EXIT",
        actual_exit_time=actual_exit_time,
        actual_exit_price=100.0,
        policy_id="hold_20_sessions_v1",
        policy_sessions=20,
        counterfactual_exit_time=pd.Timestamp("2025-06-30"),
        exit_session_market_price=100.0,
        counterfactual_exit_price=110.0,
        post_exit_asset_return=0.1,
        comparison=comparison,
        evidence_status=status,
        evidence_reason=("fixture is insufficient" if status != "complete" else None),
        provenance=None,
        counterfactual_notice=COUNTERFACTUAL_NOTICE,
    )


def _observation(
    outcome: str,
    day: str,
    *,
    source_id: str | None = None,
) -> DecisionObservation:
    return DecisionObservation(
        decision_type="sizing",
        decision_time=pd.Timestamp(day),
        source_id=source_id or f"sizing:{day}",
        outcome=outcome,
    )


@pytest.mark.parametrize(
    ("comparison", "status", "expected_outcome"),
    [
        pytest.param("outperformed_baseline", "complete", "positive", id="positive"),
        pytest.param(
            "underperformed_baseline", "complete", "negative", id="negative"
        ),
        pytest.param("matched_baseline", "complete", "matched", id="matched"),
        pytest.param(None, "insufficient_evidence", "insufficient", id="insufficient"),
    ],
)
def test_sizing_adapter_maps_upstream_classification(
    comparison,
    status,
    expected_outcome,
):
    observation = sizing_evidence_to_observation(
        _sizing_evidence(comparison, status=status)
    )

    assert observation.decision_type == "sizing"
    assert observation.decision_time == DECISION_TIME
    assert observation.source_id == f"sizing-decision:{DECISION_TIME.isoformat()}"
    assert observation.outcome == expected_outcome


@pytest.mark.parametrize(
    ("comparison", "status", "expected_outcome"),
    [
        pytest.param(
            "actual_exit_outperformed_hold_baseline",
            "complete",
            "positive",
            id="positive",
        ),
        pytest.param(
            "actual_exit_underperformed_hold_baseline",
            "complete",
            "negative",
            id="negative",
        ),
        pytest.param("matched_hold_baseline", "complete", "matched", id="matched"),
        pytest.param(None, "insufficient_evidence", "insufficient", id="insufficient"),
    ],
)
def test_exit_adapter_maps_upstream_classification(
    comparison,
    status,
    expected_outcome,
):
    evidence = _exit_evidence(comparison, status=status)

    observation = exit_timing_evidence_to_observation(evidence)

    assert observation.decision_type == "exit_timing"
    assert observation.decision_time == EXIT_TIME
    assert observation.source_id == evidence.episode_id
    assert observation.outcome == expected_outcome


def test_exit_insufficient_without_exit_time_remains_an_observation():
    evidence = _exit_evidence(
        None,
        status="insufficient_evidence",
        actual_exit_time=None,
    )

    observation = exit_timing_evidence_to_observation(evidence)

    assert observation.outcome == "insufficient"
    assert observation.decision_time is None
    assert observation.source_id == evidence.episode_id


def test_counts_valid_n_and_hit_rate_follow_transparent_definition():
    observations = [
        _observation("positive", "2025-01-01"),
        _observation("positive", "2025-01-08"),
        _observation("negative", "2025-01-15"),
        _observation("matched", "2025-01-22"),
        _observation("insufficient", "2025-01-29"),
    ]

    result = build_decision_evidence_statistics(observations)

    assert result.total_observations == 5
    assert result.positive_n == 2
    assert result.negative_n == 1
    assert result.matched_n == 1
    assert result.insufficient_n == 1
    assert result.valid_n == 4
    assert result.hit_rate == pytest.approx(0.5)
    assert result.evidence_status == "available"
    assert result.evidence_reason is None


def test_matched_is_valid_but_is_not_a_positive_hit():
    result = build_decision_evidence_statistics(
        [
            _observation("positive", "2025-01-01"),
            _observation("matched", "2025-01-02"),
        ]
    )

    assert result.valid_n == 2
    assert result.positive_n == 1
    assert result.matched_n == 1
    assert result.hit_rate == pytest.approx(0.5)
    assert "Matched observations are valid but are not positive" in (
        result.hit_rate_definition
    )


def test_insufficient_is_counted_but_excluded_from_valid_n():
    result = build_decision_evidence_statistics(
        [
            _observation("positive", "2025-01-01"),
            _observation("insufficient", "2025-01-02"),
            _observation("insufficient", "2025-01-03"),
        ]
    )

    assert result.total_observations == 3
    assert result.insufficient_n == 2
    assert result.valid_n == 1
    assert result.hit_rate == pytest.approx(1.0)


def test_wilson_interval_matches_direct_scipy_result():
    observations = [
        _observation("positive", "2025-01-01"),
        _observation("positive", "2025-01-02"),
        _observation("negative", "2025-01-03"),
        _observation("matched", "2025-01-04"),
    ]

    result = build_decision_evidence_statistics(observations)
    expected = binomtest(2, 4).proportion_ci(
        confidence_level=0.95,
        method="wilson",
    )

    assert result.hit_rate_ci95_low == pytest.approx(expected.low)
    assert result.hit_rate_ci95_high == pytest.approx(expected.high)
    assert result.interval_method == INTERVAL_METHOD == "wilson_95_scipy"


def test_wilson_interval_is_delegated_to_scipy_with_required_settings():
    scipy_result = Mock()
    scipy_result.proportion_ci.return_value = SimpleNamespace(low=0.1, high=0.9)
    with patch.object(
        statistics_module,
        "binomtest",
        return_value=scipy_result,
    ) as binomtest_mock:
        result = build_decision_evidence_statistics(
            [
                _observation("positive", "2025-01-01"),
                _observation("negative", "2025-01-02"),
            ]
        )

    binomtest_mock.assert_called_once_with(1, 2)
    scipy_result.proportion_ci.assert_called_once_with(
        confidence_level=0.95,
        method="wilson",
    )
    assert result.hit_rate_ci95_low == pytest.approx(0.1)
    assert result.hit_rate_ci95_high == pytest.approx(0.9)


def test_single_observation_has_available_but_wide_wilson_interval():
    result = build_decision_evidence_statistics(
        [_observation("positive", "2025-01-01")]
    )

    assert result.valid_n == 1
    assert result.hit_rate == pytest.approx(1.0)
    assert result.evidence_status == "available"
    assert result.hit_rate_ci95_low < 0.25
    assert result.hit_rate_ci95_high == pytest.approx(1.0)
    assert result.hit_rate_ci95_high - result.hit_rate_ci95_low > 0.7


def test_all_insufficient_has_no_rate_or_interval():
    observations = [
        _observation("insufficient", "2025-01-01"),
        DecisionObservation(
            decision_type="sizing",
            decision_time=None,
            source_id="sizing:missing-time",
            outcome="insufficient",
        ),
    ]

    result = build_decision_evidence_statistics(observations)

    assert result.total_observations == 2
    assert result.valid_n == 0
    assert result.insufficient_n == 2
    assert result.hit_rate is None
    assert result.hit_rate_ci95_low is None
    assert result.hit_rate_ci95_high is None
    assert result.evidence_status == "insufficient_evidence"
    assert result.evidence_reason is not None


def test_empty_collection_can_be_represented_with_explicit_decision_type():
    result = build_decision_evidence_statistics([], decision_type="exit_timing")

    assert result.decision_type == "exit_timing"
    assert result.total_observations == 0
    assert result.valid_n == 0
    assert result.evidence_status == "insufficient_evidence"
    assert result.first_observation_time is None
    assert result.last_observation_time is None
    assert result.date_span_days is None


def test_observation_dates_are_sorted_and_span_calendar_days():
    observations = [
        _observation("negative", "2025-02-10 08:00:00"),
        _observation("positive", "2025-01-01 18:00:00"),
        _observation("insufficient", "2025-01-21 12:00:00"),
    ]

    result = build_decision_evidence_statistics(observations)

    assert result.first_observation_time == pd.Timestamp("2025-01-01 18:00:00")
    assert result.last_observation_time == pd.Timestamp("2025-02-10 08:00:00")
    assert result.date_span_days == 40


def test_limitation_notice_is_structured_and_rejects_skill_or_prediction_claims():
    result = build_decision_evidence_statistics(
        [_observation("positive", "2025-01-01")]
    )

    assert "historical positive-decision proportion" in result.limitation_notice
    assert "not the user's future success probability" in result.limitation_notice
    assert "investment-skill probability" in result.limitation_notice
    assert "prediction interval" in result.limitation_notice
    assert "guarantee" in result.limitation_notice


def test_complete_evidence_with_unknown_comparison_is_rejected_not_guessed():
    with pytest.raises(ValueError, match="Unsupported complete Sizing comparison"):
        sizing_evidence_to_observation(_sizing_evidence(None))

    with pytest.raises(ValueError, match="Unsupported complete Exit comparison"):
        exit_timing_evidence_to_observation(_exit_evidence(None))


def test_mixed_decision_types_are_not_silently_pooled():
    sizing = _observation("positive", "2025-01-01")
    exit_observation = replace(
        sizing,
        decision_type="exit_timing",
        source_id="investment-episode:SYN_EXIT:0",
    )

    with pytest.raises(ValueError, match="same decision_type"):
        build_decision_evidence_statistics([sizing, exit_observation])


def test_explicit_decision_type_is_validated_before_comparison():
    observation = _observation("positive", "2025-01-01")

    with pytest.raises(ValueError, match="non-empty string"):
        build_decision_evidence_statistics([observation], decision_type=123)
