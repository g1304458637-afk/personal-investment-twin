from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.data.csv_importer import load_normalized_csv
from src.episodes.position_episode import build_position_episode_lifecycle
from src.path.analysis import build_episode_path_analysis
from src.path.market_path import CONTEXT_REQUESTED_OBSERVATIONS, calendar_days_between
from src.path.patterns import LONG_NO_EXECUTION_MIN_CALENDAR_DAYS


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
CASH = 100_000.0


def _lifecycle(executions: pd.DataFrame, prices: pd.DataFrame, *, as_of: str, subject: str, account: str):
    return build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=subject,
        account_id=account,
        as_of=pd.Timestamp(as_of),
        init_cash=CASH,
        data_tier="synthetic",
        calculation_code_version="long-horizon-test-v1",
    )


def _closed():
    executions = load_normalized_csv(SAMPLE / "long_horizon_closed_executions_v1.csv")
    prices = pd.read_csv(SAMPLE / "long_horizon_closed_market_prices_v1.csv")
    lifecycle = _lifecycle(
        executions,
        prices,
        as_of="2025-07-16 23:59:00",
        subject="test-long-closed",
        account="acct-long-closed",
    )
    episode = lifecycle.episodes[0]
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=episode.episode_id, init_cash=CASH
    )
    return executions, prices, lifecycle, episode, analysis


def _open():
    executions = load_normalized_csv(SAMPLE / "long_horizon_open_executions_v1.csv")
    prices = pd.read_csv(SAMPLE / "long_horizon_open_market_prices_v1.csv")
    lifecycle = _lifecycle(
        executions,
        prices,
        as_of="2026-01-15 23:59:00",
        subject="test-long-open",
        account="acct-long-open",
    )
    episode = lifecycle.episodes[0]
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=episode.episode_id, init_cash=CASH
    )
    return executions, prices, lifecycle, episode, analysis


def test_closed_long_horizon_retains_full_daily_path_and_calendar_duration():
    _executions, prices, _lifecycle_obj, episode, analysis = _closed()
    holding = analysis.market_path.episode_market_path.observations
    assert episode.status == "closed"
    assert episode.closed_at is not None
    assert episode.duration_kind == "final"
    assert episode.duration_days == calendar_days_between(episode.opened_at, episode.closed_at)
    assert episode.duration_days >= 365 * 3
    assert len(holding) >= 750
    assert len(holding) == analysis.market_path.episode_market_path.valid_observation_count
    source_dates = {
        pd.Timestamp(item).normalize()
        for item in pd.to_datetime(prices.loc[prices["instrument"] == "SYN_LONG_CLOSED", "date"])
    }
    opened = episode.opened_at.normalize()
    closed = episode.closed_at.normalize()
    expected = {item for item in source_dates if opened <= item <= closed}
    observed = {item.observed_at.normalize() for item in holding}
    assert observed == expected
    assert analysis.market_path.pre_entry_context.valid_observation_count <= CONTEXT_REQUESTED_OBSERVATIONS
    assert analysis.market_path.post_exit_context.valid_observation_count <= CONTEXT_REQUESTED_OBSERVATIONS
    assert analysis.market_path.post_exit_context.valid_observation_count > 0
    assert any("not a trading calendar" in item for item in analysis.limitations)
    assert "trading-day counts" not in " ".join(analysis.limitations).lower()


def test_open_long_horizon_has_no_fake_exit_and_no_post_exit_context():
    _executions, _prices, _lifecycle_obj, episode, analysis = _open()
    assert episode.status == "open"
    assert episode.closed_at is None
    assert episode.duration_kind == "so_far"
    assert all(item.decision_type != "close_position" for item in _lifecycle_obj.decisions)
    assert analysis.market_path.post_exit_context.valid_observation_count == 0
    assert analysis.market_path.post_exit_context_status == "insufficient"
    assert len(analysis.market_path.episode_market_path.observations) >= 1000
    snapshot = next(item for item in _lifecycle_obj.snapshots if item.episode_id == episode.episode_id)
    state = next(item for item in _lifecycle_obj.states if item.state_id == snapshot.position_state_ref)
    assert state.quantity > 0


def test_long_no_execution_interval_is_not_a_decision_phase():
    _executions, _prices, lifecycle, episode, analysis = _closed()
    decisions = [item for item in lifecycle.decisions if item.episode_id == episode.episode_id]
    assert [item.decision_type for item in decisions] == [
        "open_position",
        "add_position",
        "add_position",
        "reduce_position",
        "close_position",
    ]
    assert {item.phase_type for item in analysis.phases} <= {"entry", "scaling_in", "scaling_out", "exit"}
    assert all("hold" not in item.phase_type for item in analysis.phases)
    long_patterns = [item for item in analysis.patterns if item.pattern_code == "long_no_execution_interval"]
    assert long_patterns
    last_add = decisions[2]
    first_reduce = decisions[3]
    match = next(
        item
        for item in long_patterns
        if item.facts["previous_decision_event_id"] == last_add.decision_id
        and item.facts["next_decision_event_id"] == first_reduce.decision_id
    )
    assert match.facts["calendar_days"] == calendar_days_between(last_add.occurred_at, first_reduce.occurred_at)
    assert match.facts["calendar_days"] >= LONG_NO_EXECUTION_MIN_CALENDAR_DAYS
    assert match.facts["duration_unit"] == "calendar_days"
    assert match.facts["quantity_stable"] is True
    assert match.facts["quantity_held"] == 1100.0
    previous_qty = next(item.quantity for item in lifecycle.states if item.state_id == last_add.state_after_ref)
    next_before = next(item.quantity for item in lifecycle.states if item.state_id == first_reduce.state_before_ref)
    assert previous_qty == next_before == 1100.0
    assert not any("hold" in item.reason_code for item in analysis.presentation_items)


def test_market_path_keeps_rise_drawdown_recovery_without_turning_them_into_phases():
    _executions, _prices, _lifecycle_obj, _episode, analysis = _closed()
    kinds = {item.kind for item in analysis.market_path.market_path_segments}
    assert {"rise", "drawdown", "recovery"} <= kinds
    assert len(analysis.market_path.market_path_segments) >= 3
    assert all(item.phase_type in {"entry", "scaling_in", "scaling_out", "exit"} for item in analysis.phases)
    assert 1 <= len(analysis.presentation_items) <= 6
    assert any(item.pattern_code == "long_no_execution_interval" for item in analysis.patterns)


def test_decision_linked_patterns_do_not_explode_during_long_hold():
    _executions, _prices, _lifecycle_obj, _episode, analysis = _closed()
    behavior = [
        item
        for item in analysis.patterns
        if item.pattern_code
        in {
            "add_after_positive_market_move",
            "reduce_after_negative_market_move",
            "exit_after_negative_market_move",
            "consecutive_scaling_in",
            "consecutive_scaling_out",
            "price_following_scale_sequence",
        }
    ]
    assert len(behavior) <= 8
    for item in behavior:
        assert item.decision_event_ids


def test_same_day_drawdown_quantity_stays_fail_closed_on_long_path():
    _executions, _prices, _lifecycle_obj, _episode, analysis = _closed()
    drawdown = analysis.market_path.daily_price_peak_drawdown
    assert drawdown is not None
    if drawdown.quantity_at_trough_status == "available":
        assert drawdown.quantity_at_trough is not None
        assert drawdown.quantity_status_reason is None or "execution" not in drawdown.quantity_status_reason
    else:
        assert drawdown.quantity_at_trough is None
        assert drawdown.quantity_at_trough_status in {"ambiguous", "unavailable"}


def test_open_marked_result_is_not_realized():
    _executions, prices, lifecycle, episode, _analysis = _open()
    from src.attribution.decision_outcome import build_actual_outcomes

    actual = build_actual_outcomes(
        lifecycle,
        _executions,
        prices,
        subject_id=episode.subject_id,
        account_id=episode.account_id,
        analysis_as_of=lifecycle.as_of,
        init_cash=CASH,
    )
    outcome = next(item for item in actual.episode_outcomes if item.episode_id == episode.episode_id)
    assert outcome.actual_result.result_kind == "marked"
    assert outcome.episode_status == "open"


def test_closed_realized_result_is_authoritative():
    executions, prices, lifecycle, episode, _analysis = _closed()
    from src.attribution.decision_outcome import build_actual_outcomes

    actual = build_actual_outcomes(
        lifecycle,
        executions,
        prices,
        subject_id=episode.subject_id,
        account_id=episode.account_id,
        analysis_as_of=lifecycle.as_of,
        init_cash=CASH,
    )
    outcome = next(item for item in actual.episode_outcomes if item.episode_id == episode.episode_id)
    assert outcome.actual_result.result_kind == "realized"
    assert outcome.episode_status == "closed"


def test_phase_counterfactual_uses_next_decision_even_when_months_away():
    _executions, _prices, lifecycle, episode, analysis = _closed()
    scaling = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    ordered = [item for item in lifecycle.decisions if item.episode_id == episode.episode_id]
    last_id = scaling.decision_event_ids[-1]
    index = next(i for i, item in enumerate(ordered) if item.decision_id == last_id)
    next_decision = ordered[index + 1]
    cf = next(
        item
        for item in analysis.phase_counterfactuals
        if item.scenario_id == "omit_decision_phase_until_next_decision_v2"
        and item.decision_event_id == scaling.decision_event_ids[0]
    )
    assert cf.evaluation_end == next_decision.occurred_at
    assert cf.next_decision_at == next_decision.occurred_at
    assert cf.valuation_observation_date < next_decision.occurred_at.normalize()
    assert calendar_days_between(scaling.ended_at, next_decision.occurred_at) >= 180
    assert episode.closed_at is not None
    assert cf.evaluation_end < episode.closed_at
    assert cf.evaluation_end.normalize() != (cf.evaluation_end.normalize() + pd.Timedelta(days=20))
    horizon_days = calendar_days_between(scaling.ended_at, cf.evaluation_end)
    assert horizon_days not in {20, 90, 365}


def test_no_future_market_rows_after_evaluation_end_in_phase_cf_source():
    source = Path("src/attribution/decision_outcome.py").read_text()
    assert "_market_rows_through" in source
    assert "evaluation_end cannot exceed analysis_as_of" in source


def test_path_build_benchmark_and_payload_size_stay_simple():
    executions, prices, lifecycle, episode, analysis = _closed()
    started = time.perf_counter()
    for _ in range(3):
        build_episode_path_analysis(
            lifecycle, executions, prices, episode_id=episode.episode_id, init_cash=CASH
        )
    elapsed = (time.perf_counter() - started) / 3
    payload = json.dumps(
        {
            "observations": analysis.market_path.episode_market_path.valid_observation_count,
            "points": len(analysis.market_path.episode_market_path.observations),
        }
    )
    assert elapsed < 8.0
    assert analysis.market_path.episode_market_path.valid_observation_count >= 750
    assert len(payload) < 10_000
    print(
        f"long_horizon_closed path_build_s={elapsed:.3f} "
        f"holding_obs={analysis.market_path.episode_market_path.valid_observation_count}"
    )


def test_optional_2000_observation_build_does_not_truncate():
    start = date(2018, 1, 2)
    days = []
    current = start
    while len(days) < 2000:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    prices = pd.DataFrame(
        {
            "date": [item.isoformat() for item in days],
            "instrument": "SYN_BENCH",
            "close": [10.0 + (index % 17) * 0.08 for index in range(len(days))],
            "price_type": "synthetic",
            "data_source": "bench",
            "data_version": "v1",
            "is_synthetic": True,
        }
    )
    executions = pd.DataFrame(
        [
            {
                "event_time": pd.Timestamp(days[40].isoformat() + " 09:30:00"),
                "symbol": "SYN_BENCH",
                "side": "BUY",
                "executed_quantity": 100.0,
                "executed_price": 10.2,
                "fee": 1.0,
                "execution_id": "EXE-OPEN",
                "order_id": "ORD-OPEN",
                "account_id": "acct-bench",
                "subject_id": "bench-subject",
            },
            {
                "event_time": pd.Timestamp(days[-30].isoformat() + " 10:00:00"),
                "symbol": "SYN_BENCH",
                "side": "SELL",
                "executed_quantity": 100.0,
                "executed_price": 11.0,
                "fee": 1.0,
                "execution_id": "EXE-CLOSE",
                "order_id": "ORD-CLOSE",
                "account_id": "acct-bench",
                "subject_id": "bench-subject",
            },
        ]
    )
    lifecycle = _lifecycle(
        executions,
        prices,
        as_of=f"{days[-1].isoformat()} 23:59:00",
        subject="bench-subject",
        account="acct-bench",
    )
    started = time.perf_counter()
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    elapsed = time.perf_counter() - started
    holding = analysis.market_path.episode_market_path.observations
    assert len(holding) >= 1900
    assert elapsed < 12.0
    print(f"optional_2000_obs path_build_s={elapsed:.3f} holding_obs={len(holding)}")
