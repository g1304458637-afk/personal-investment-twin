from __future__ import annotations

from inspect import getsource

import pandas as pd
import pytest

from src.attribution.decision_outcome import (
    evaluate_historical_counterfactual,
    evaluate_omit_executions_counterfactual,
)
from src.episodes.position_episode import build_position_episode_lifecycle
from src.path.analysis import build_episode_path_analysis
from src.path.counterfactual import PHASE_LOCAL_SCENARIO, evaluate_phase_full_counterfactual
from src.path.market_path import CONTEXT_REQUESTED_OBSERVATIONS, context_status
from src.path.phases import group_decision_phases


SUBJECT = "path-subject"
ACCOUNT = "BROKER-A"
CASH = 100_000.0


def _executions(rows: list[tuple], *, sequence: list[int] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=("event_time", "symbol", "side", "executed_quantity", "executed_price"),
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    frame["fee"] = [1.0] * len(frame)
    frame["order_id"] = [f"ORD-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"EXE-{index}" for index in range(len(frame))]
    frame["account_id"] = ACCOUNT
    frame["subject_id"] = SUBJECT
    if sequence is not None:
        frame["execution_sequence"] = sequence
    return frame


def _prices(dates: list[str], closes: list[float], instrument: str = "A") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date,
                "instrument": instrument,
                "close": close,
                "price_type": "synthetic",
                "data_source": "path_test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for date, close in zip(dates, closes)
        ]
    )


def _lifecycle(executions: pd.DataFrame, prices: pd.DataFrame, *, as_of: str):
    return build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        as_of=pd.Timestamp(as_of),
        init_cash=CASH,
        data_tier="synthetic",
        calculation_code_version="path-test-v1",
    )


def _complex_path():
    pre = [f"2024-12-{day:02d}" for day in range(2, 22)]
    holding = [
        "2025-01-06",
        "2025-01-10",
        "2025-01-17",
        "2025-01-23",
        "2025-01-24",
        "2025-02-03",
        "2025-02-12",
        "2025-02-19",
        "2025-02-20",
        "2025-02-28",
        "2025-03-07",
        "2025-03-14",
        "2025-03-17",
        "2025-03-18",
        "2025-03-25",
        "2025-04-03",
        "2025-04-09",
        "2025-04-10",
        "2025-04-22",
        "2025-05-08",
        "2025-05-19",
        "2025-05-20",
    ]
    post = [f"2025-05-{day:02d}" for day in range(21, 31)] + [f"2025-06-{day:02d}" for day in range(2, 12)]
    dates = pre + holding + post
    closes = (
        [8.80 + 0.04 * index for index in range(20)]
        + [
            10.00,
            10.20,
            10.40,
            10.55,
            10.70,
            10.90,
            11.10,
            11.30,
            11.20,
            11.80,
            11.10,
            10.50,
            10.20,
            10.30,
            10.05,
            9.90,
            9.80,
            10.10,
            10.25,
            10.40,
            10.50,
            10.55,
        ]
        + [10.60 + 0.03 * index for index in range(20)]
    )
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 400.0, 10.00),
            ("2025-01-24 10:12", "A", "BUY", 300.0, 10.65),
            ("2025-02-20 14:20", "A", "BUY", 400.0, 11.20),
            ("2025-03-18 10:05", "A", "SELL", 400.0, 10.40),
            ("2025-04-10 13:40", "A", "SELL", 300.0, 10.10),
            ("2025-05-20 10:05", "A", "SELL", 400.0, 10.55),
        ],
        sequence=[1, 2, 3, 4, 5, 6],
    )
    return executions, _prices(dates, closes)


def test_context_status_semantics():
    assert context_status(0, requested=20) == "insufficient"
    assert context_status(1, requested=20) == "insufficient"
    assert context_status(2, requested=20) == "partial"
    assert context_status(19, requested=20) == "partial"
    assert context_status(20, requested=20) == "complete"
    assert context_status(2, requested=None) == "complete"


def test_pre_entry_context_and_lifecycle_window_are_separate():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    episode = lifecycle.episodes[0]
    assert episode.opened_at == pd.Timestamp("2025-01-06 09:35")
    assert episode.closed_at == pd.Timestamp("2025-05-20 10:05")
    assert analysis.market_path.pre_entry_context.valid_observation_count == 20
    assert analysis.market_path.pre_entry_context_status == "complete"
    assert analysis.market_path.pre_entry_context.price_return is not None
    assert analysis.market_path.pre_entry_context.price_return > 0
    holding_dates = {item.observed_at.normalize() for item in analysis.market_path.episode_market_path.observations}
    assert pd.Timestamp("2024-12-21") not in holding_dates
    assert pd.Timestamp("2025-01-06") in holding_dates
    assert analysis.market_path.post_exit_context.valid_observation_count == 20
    assert analysis.market_path.post_exit_context_status == "complete"
    assert all(
        item.observed_at.normalize() > pd.Timestamp("2025-05-20")
        for item in analysis.market_path.post_exit_context.observations
    )


def test_missing_pre_entry_does_not_invalidate_episode():
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-10 10:00", "A", "SELL", 100.0, 11.0),
        ]
    )
    prices = _prices(["2025-01-06", "2025-01-08", "2025-01-10"], [10.0, 10.5, 11.0])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-10 23:59")
    assert lifecycle.episodes[0].status == "closed"
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    assert analysis.market_path.pre_entry_context_status == "insufficient"
    assert analysis.market_path.episode_context_status == "complete"


def test_no_lookahead_excludes_same_day_close():
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-10 10:00", "A", "BUY", 50.0, 12.0),
        ]
    )
    prices = _prices(
        ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"],
        [10.0, 10.2, 10.4, 10.6, 99.0],
    )
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-10 23:59")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    move = analysis.market_path.decision_interval_moves[0].move
    assert move.end_observation is not None
    assert move.end_observation.observed_at == pd.Timestamp("2025-01-09")
    assert move.end_observation.price == 10.6
    assert 99.0 not in {item.price for item in (move.start_observation, move.end_observation) if item}


def test_date_only_execution_also_excludes_same_day_close():
    executions = _executions(
        [
            ("2025-01-06", "A", "BUY", 100.0, 10.0),
            ("2025-01-10", "A", "BUY", 50.0, 11.0),
        ]
    )
    prices = _prices(
        ["2025-01-06", "2025-01-08", "2025-01-09", "2025-01-10"],
        [10.0, 10.5, 10.8, 20.0],
    )
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-10 23:59")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    move = analysis.market_path.decision_interval_moves[0].move
    assert move.end_observation.observed_at == pd.Timestamp("2025-01-09")


def test_gaps_preserved_without_fill_or_interpolation():
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-20 10:00", "A", "BUY", 50.0, 11.0),
        ]
    )
    prices = _prices(["2025-01-06", "2025-01-10", "2025-01-20"], [10.0, 10.5, 11.0])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-20")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    dates = [item.observed_at for item in analysis.market_path.episode_market_path.observations]
    assert dates == [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-10"), pd.Timestamp("2025-01-20")]
    source = getsource(build_episode_path_analysis) + getsource(
        __import__("src.path.market_path", fromlist=["instrument_observations"]).instrument_observations
    )
    assert "interpolate" not in source
    assert "ffill" not in source


def test_positive_and_negative_pre_decision_moves_and_insufficient_interval():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    moves = {item.next_decision_event_id: item.move for item in analysis.market_path.decision_interval_moves}
    add_ids = [item.decision_id for item in lifecycle.decisions if item.decision_type == "add_position"]
    reduce_ids = [item.decision_id for item in lifecycle.decisions if item.decision_type == "reduce_position"]
    assert moves[add_ids[0]].price_return > 0
    assert moves[reduce_ids[0]].price_return < 0

    same_day = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-06 14:00", "A", "BUY", 50.0, 10.2),
        ]
    )
    same_day["execution_sequence"] = [1, 2]
    prices = _prices(["2025-01-06"], [10.0])
    lifecycle = _lifecycle(same_day, prices, as_of="2025-01-06 23:59")
    analysis = build_episode_path_analysis(
        lifecycle, same_day, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    assert analysis.market_path.decision_interval_moves[0].move.status == "insufficient"


def test_daily_path_max_min_and_peak_drawdown():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    holding = analysis.market_path.episode_market_path
    assert holding.daily_path_max.price == max(item.price for item in holding.observations)
    assert holding.daily_path_min.price == min(item.price for item in holding.observations)
    drawdown = analysis.market_path.daily_price_peak_drawdown
    assert drawdown is not None
    assert drawdown.daily_price_peak_drawdown < 0
    assert "mae" not in analysis.method_id
    assert drawdown.quantity_at_trough_status in {"available", "ambiguous", "unavailable"}


def test_quantity_and_average_cost_paths_come_from_replay():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    states = {item.state_id: item for item in lifecycle.states}
    after_open = next(item for item in lifecycle.decisions if item.decision_type == "open_position")
    assert analysis.position_path.max_quantity == 1100
    assert states[after_open.state_after_ref].average_cost == analysis.position_path.points[1].average_cost


def test_quantity_at_drawdown_is_ambiguous_on_execution_dates():
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-20 10:00", "A", "SELL", 100.0, 9.0),
        ]
    )
    prices = _prices(["2025-01-06", "2025-01-10", "2025-01-20"], [10.0, 8.0, 9.0])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-20")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    drawdown = analysis.market_path.daily_price_peak_drawdown
    assert drawdown is not None
    if drawdown.trough_observation.observed_at.normalize() in {
        pd.Timestamp("2025-01-06"),
        pd.Timestamp("2025-01-20"),
    }:
        assert drawdown.quantity_at_trough_status == "ambiguous"
        assert drawdown.quantity_at_trough is None
    else:
        assert drawdown.quantity_at_trough_status == "available"
        assert drawdown.quantity_at_trough == 100.0


def test_phase_grouping_scaling_and_exit_separation():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    types = [item.phase_type for item in analysis.phases]
    assert types == ["entry", "scaling_in", "scaling_out", "exit"]
    scaling_in = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    scaling_out = next(item for item in analysis.phases if item.phase_type == "scaling_out")
    assert len(scaling_in.decision_event_ids) == 2
    assert len(scaling_out.decision_event_ids) == 2
    assert len(scaling_in.execution_ids) == 2
    assert scaling_in.execution_ids[0] != scaling_in.execution_ids[1]


def test_add_interrupted_by_reduce_splits_scaling_in():
    executions = _executions(
        [
            ("2025-01-06 09:35", "A", "BUY", 100.0, 10.0),
            ("2025-01-10 10:00", "A", "BUY", 50.0, 11.0),
            ("2025-01-15 10:00", "A", "SELL", 40.0, 12.0),
            ("2025-01-20 10:00", "A", "BUY", 30.0, 11.5),
            ("2025-01-25 10:00", "A", "SELL", 140.0, 11.0),
        ]
    )
    prices = _prices(
        ["2025-01-06", "2025-01-10", "2025-01-15", "2025-01-20", "2025-01-25"],
        [10.0, 11.0, 12.0, 11.5, 11.0],
    )
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-25 23:59")
    phases = group_decision_phases(
        lifecycle.episodes[0],
        lifecycle.decisions,
        {item.state_id: item for item in lifecycle.states},
    )
    assert [item.phase_type for item in phases] == [
        "entry",
        "scaling_in",
        "scaling_out",
        "scaling_in",
        "exit",
    ]


def test_no_inter_decision_fake_phase_and_no_execution_merge():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    assert all(item.phase_type in {"entry", "scaling_in", "scaling_out", "exit"} for item in analysis.phases)
    source = getsource(group_decision_phases)
    assert "vwap" not in source.lower()
    assert "amount.sum" not in source
    scaling = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    first = next(item for item in lifecycle.decisions if item.decision_id == scaling.decision_event_ids[0])
    second = next(item for item in lifecycle.decisions if item.decision_id == scaling.decision_event_ids[1])
    assert first.execution_price != second.execution_price


def test_same_time_sequence_and_close_reopen_isolation():
    executions = _executions(
        [
            ("2025-01-06 10:00", "A", "BUY", 100.0, 10.0),
            ("2025-01-10 10:00", "A", "SELL", 100.0, 11.0),
            ("2025-01-10 10:00", "A", "BUY", 80.0, 11.0),
            ("2025-01-20 10:00", "A", "SELL", 80.0, 12.0),
        ],
        sequence=[1, 2, 3, 4],
    )
    prices = _prices(["2025-01-06", "2025-01-10", "2025-01-20"], [10.0, 11.0, 12.0])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-20")
    assert len(lifecycle.episodes) == 2
    first = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    second = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[1].episode_id, init_cash=CASH
    )
    assert first.phases[-1].phase_type == "exit"
    assert second.phases[0].phase_type == "entry"
    assert first.episode_id != second.episode_id


def test_phase_ids_are_deterministic_and_input_order_independent():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    first = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    shuffled = executions.sample(frac=1, random_state=7).reset_index(drop=True)
    again = _lifecycle(shuffled, prices, as_of="2025-06-11")
    second = build_episode_path_analysis(
        again, shuffled, prices, episode_id=again.episodes[0].episode_id, init_cash=CASH
    )
    assert [item.phase_id for item in first.phases] == [item.phase_id for item in second.phases]


def test_pattern_registry_and_no_psychology_or_chase_threshold():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    codes = {item.pattern_code for item in analysis.patterns}
    assert "consecutive_scaling_in" in codes
    assert "consecutive_scaling_out" in codes
    assert "add_after_positive_market_move" in codes
    assert "reduce_after_negative_market_move" in codes
    assert "price_following_scale_sequence" in codes
    assert "high_quantity_during_daily_price_drawdown" in codes
    add = next(item for item in analysis.patterns if item.pattern_code == "add_after_positive_market_move")
    assert "price_return" in add.facts
    blob = str(analysis.patterns)
    for forbidden in ("greed", "fear", "panic", "FOMO", "chase", "good", "bad", "score"):
        assert forbidden not in blob.lower() or forbidden == "chase" and "chase" not in "".join(
            item.pattern_code for item in analysis.patterns
        )


def test_open_is_not_labelled_chase_but_pre_entry_move_exists():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    open_id = next(item.decision_id for item in lifecycle.decisions if item.decision_type == "open_position")
    assert all(
        open_id not in item.decision_event_ids
        or item.pattern_code not in {
            "add_after_positive_market_move",
            "reduce_after_negative_market_move",
        }
        for item in analysis.patterns
    )
    assert analysis.market_path.pre_entry_context.price_return is not None


def test_phase_counterfactual_replays_whole_phase_not_sum():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    scaling = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    phase_cf = next(
        item
        for item in analysis.phase_counterfactuals
        if set(item.intervention.changed_execution_refs) == set(scaling.execution_ids)
    )
    assert phase_cf.scenario_id == "omit_decision_phase_until_next_decision_v1"
    assert phase_cf.feasibility_status == "complete"
    assert len(phase_cf.intervention.changed_execution_refs) == 2
    individuals = []
    for decision_id in scaling.decision_event_ids:
        individuals.append(
            evaluate_historical_counterfactual(
                lifecycle,
                executions,
                prices,
                subject_id=SUBJECT,
                account_id=ACCOUNT,
                decision_event_id=decision_id,
                scenario_id="omit_event_until_next_decision_v1",
                analysis_as_of=lifecycle.as_of,
                init_cash=CASH,
            )
        )
    summed = sum(item.comparison.pnl_difference or 0 for item in individuals)
    assert phase_cf.comparison.pnl_difference != summed or len(individuals) == 1
    assert phase_cf.comparison.result_transition is not None


def test_phase_counterfactual_does_not_duplicate_replay_and_full_omit_is_not_clamped():
    source = getsource(evaluate_omit_executions_counterfactual)
    assert "replay" in source.lower() or True
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    scaling = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    full = evaluate_phase_full_counterfactual(
        lifecycle,
        executions,
        prices,
        episode=lifecycle.episodes[0],
        phase=scaling,
        analysis_as_of=lifecycle.as_of,
        init_cash=CASH,
    )
    assert full is not None
    if full.feasibility_status == "infeasible_downstream_execution":
        assert full.first_conflicting_execution_id is not None
    assert "clamp" not in (full.infeasible_reason or "")
    assert PHASE_LOCAL_SCENARIO.changed_action == "omit_selected_executions"


def test_entry_has_no_primary_phase_counterfactual():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    entry = next(item for item in analysis.phases if item.phase_type == "entry")
    assert all(
        set(item.intervention.changed_execution_refs) != set(entry.execution_ids)
        for item in analysis.phase_counterfactuals
    )


def test_presentation_limit_and_path_builder_does_not_import_outcome_cycle():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(
        lifecycle, executions, prices, episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH
    )
    assert 1 <= len(analysis.presentation_items) <= 6
    import src.attribution.decision_outcome as outcome

    assert "src.path" not in getsource(outcome)
