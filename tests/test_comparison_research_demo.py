import json

import numpy as np
import pandas as pd
import pytest

from scripts.export_comparison_demo import export_bytes
from src.behavior.replay_state import prepare_behavior_replay
from src.compare.research_demo import (
    END,
    INITIAL_CASH,
    START,
    SUBJECTS,
    SYNTHETIC_SCHEDULE,
    _period,
    _study_input_sha256,
    build_research_demo,
    study_inputs,
)


def _account(payload: dict[str, object], subject: str) -> dict[str, object]:
    accounts = payload["accounts"]
    assert isinstance(accounts, list)
    return next(item for item in accounts if item["subject_id"] == subject)


def _nested_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _nested_strings(key)
            yield from _nested_strings(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _nested_strings(item)


def _difference(comparison: dict[str, object], metric_id: str) -> dict[str, object]:
    return next(
        item for item in comparison["differences"] if item["metric_id"] == metric_id
    )


@pytest.fixture(scope="module")
def research_demo() -> dict[str, object]:
    return build_research_demo()


def test_research_demo_does_not_mutate_supplied_study_inputs():
    executions, prices = study_inputs(SUBJECTS[0])
    original_executions = executions.copy(deep=True)
    original_prices = prices.copy(deep=True)

    _period(SUBJECTS[0], executions, prices, START, END)

    pd.testing.assert_frame_equal(executions, original_executions)
    pd.testing.assert_frame_equal(prices, original_prices)


def test_three_subjects_remain_isolated_and_have_distinct_replay_results(
    research_demo,
):
    assert research_demo["calendar"] == SYNTHETIC_SCHEDULE
    assert [item["subject_id"] for item in research_demo["accounts"]] == list(SUBJECTS)
    full_returns = []
    for subject in SUBJECTS:
        account = _account(research_demo, subject)
        assert account["account_id"] == subject
        strings = set(_nested_strings(account))
        assert subject in strings
        assert not strings.intersection(set(SUBJECTS) - {subject})
        performance = account["periods"]["full"]["performance"]
        full_returns.append(performance["period_return"])
        assert performance["annualized_volatility"] is not None
        assert performance["sharpe_ratio"] is None
    assert len(set(full_returns)) == len(SUBJECTS)


def test_period_start_is_a_baseline_and_actions_are_start_exclusive(research_demo):
    account = _account(research_demo, SUBJECTS[0])
    full = account["periods"]["full"]
    executions, _ = study_inputs(SUBJECTS[0])
    days = pd.to_datetime(executions["event_time"]).dt.normalize()
    expected_actions = int(
        ((days > pd.Timestamp(START)) & (days <= pd.Timestamp(END))).sum()
    )

    assert full["boundary"] == "start_exclusive_end_inclusive"
    assert full["behavior"]["action_count"] == expected_actions
    assert len(full["operations"]) == expected_actions
    assert all(pd.Timestamp(item["date"]).date() > pd.Timestamp(START).date()
               for item in full["operations"])
    points = full["performance"]["points"]
    assert pd.Timestamp(points[0]["observed_at"]).date() == pd.Timestamp(START).date()
    assert points[0]["period_return"] is None
    assert full["performance"]["return_observation_count"] == len(points) - 1


def test_exported_account_values_are_the_existing_replay_values(research_demo):
    account = _account(research_demo, SUBJECTS[1])
    performance = account["periods"]["full"]["performance"]
    executions, prices = study_inputs(SUBJECTS[1])
    cutoff = pd.Timestamp(END) + pd.Timedelta(days=1)
    context = prepare_behavior_replay(
        executions.loc[executions["event_time"] < cutoff].copy(),
        prices.loc[prices["date"] < cutoff].copy(),
        init_cash=INITIAL_CASH,
    )
    authoritative_values = context.portfolio.value()
    dates = pd.Index(item.date() for item in authoritative_values.index)
    selected = authoritative_values.loc[
        (dates >= pd.Timestamp(START).date()) & (dates <= pd.Timestamp(END).date())
    ]
    selected_dates = pd.Index(item.date() for item in selected.index)
    eod = selected.groupby(selected_dates, sort=True).tail(1)

    np.testing.assert_allclose(
        [item["account_value"] for item in performance["points"]],
        eod.to_numpy(),
    )
    assert performance["period_return"] == pytest.approx(
        eod.iloc[-1] / eod.iloc[0] - 1.0
    )


def test_comparisons_are_scoped_and_report_exact_right_minus_left_differences(
    research_demo,
):
    accounts = {
        item["subject_id"]: item for item in research_demo["accounts"]
    }
    comparisons = research_demo["comparisons"]
    self_comparison = comparisons["self"]
    assert self_comparison["kind"] == "self_periods"
    assert self_comparison["left_account_id"] == SUBJECTS[0]
    assert self_comparison["right_account_id"] == SUBJECTS[0]
    assert self_comparison["left_period_start"].startswith(START)
    assert self_comparison["left_period_end"].startswith("2025-04-02")
    assert self_comparison["right_period_start"].startswith("2025-04-02")
    assert self_comparison["right_period_end"].startswith(END)
    earlier_return = accounts[SUBJECTS[0]]["periods"]["earlier"]["performance"][
        "period_return"
    ]
    recent_return = accounts[SUBJECTS[0]]["periods"]["recent"]["performance"][
        "period_return"
    ]
    assert _difference(self_comparison, "period_return")[
        "right_minus_left"
    ] == pytest.approx(100.0 * (recent_return - earlier_return))

    for professional_subject in SUBJECTS[1:]:
        by_period = comparisons["professional"][professional_subject]
        assert set(by_period) == {"full", "earlier", "recent"}
        for period_name, comparison in by_period.items():
            assert comparison["kind"] == "professional"
            assert comparison["left_account_id"] == SUBJECTS[0]
            assert comparison["right_account_id"] == professional_subject
            left = accounts[SUBJECTS[0]]["periods"][period_name]["performance"]
            right = accounts[professional_subject]["periods"][period_name][
                "performance"
            ]
            assert comparison["left_period_start"] == left["period_start"]
            assert comparison["left_period_end"] == left["period_end"]
            assert comparison["right_period_start"] == right["period_start"]
            assert comparison["right_period_end"] == right["period_end"]
            assert _difference(comparison, "period_return")[
                "right_minus_left"
            ] == pytest.approx(
                100.0 * (right["period_return"] - left["period_return"])
            )

    balanced = comparisons["professional"][SUBJECTS[1]]
    assert _difference(balanced["earlier"], "period_return")[
        "right_minus_left"
    ] > 0
    assert _difference(balanced["recent"], "period_return")[
        "right_minus_left"
    ] < 0


def test_allocation_uses_actual_replay_timestamp_and_explicit_eod_cutoff(
    research_demo,
):
    account = _account(research_demo, SUBJECTS[0])
    full = account["periods"]["full"]
    allocation = full["allocation"]
    final_performance_point = full["performance"]["points"][-1]

    assert allocation["valuation_observed_at"] == pd.Timestamp(
        final_performance_point["observed_at"]
    )
    assert allocation["observation_semantics"] == (
        "synthetic_daily_eod_last_actual_replay_observation"
    )
    assert allocation["lookthrough"]["as_of"] == (
        pd.Timestamp(END) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    )


def test_input_sha_covers_both_execution_and_price_facts_without_mutation():
    executions, prices = study_inputs(SUBJECTS[0])
    original_executions = executions.copy(deep=True)
    original_prices = prices.copy(deep=True)
    baseline = _study_input_sha256(((SUBJECTS[0], executions, prices),))

    changed_execution = executions.copy(deep=True)
    changed_execution.loc[0, "fee"] += 0.01
    changed_price = prices.copy(deep=True)
    changed_price.loc[0, "close"] += 0.01

    assert _study_input_sha256(
        ((SUBJECTS[0], changed_execution, prices),)
    ) != baseline
    assert _study_input_sha256(
        ((SUBJECTS[0], executions, changed_price),)
    ) != baseline
    pd.testing.assert_frame_equal(executions, original_executions)
    pd.testing.assert_frame_equal(prices, original_prices)


def test_consecutive_independent_exports_are_byte_deterministic_and_json_safe():
    first = export_bytes()
    second = export_bytes()

    assert first == second
    assert first.endswith(b"\n")
    decoded = json.loads(first)
    assert decoded["input_sha256"]
    assert decoded["accounts"][0]["periods"]["full"]["risk_schedule"] == {
        "annualization_factor": 252,
        "kind": SYNTHETIC_SCHEDULE,
        "risk_free_source_ref": None,
        "source_ref": (
            "comparison_research_demo_v1:"
            f"{SYNTHETIC_SCHEDULE}:{START}:{END}"
        ),
    }
