from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

from src.attribution.decision_outcome import (
    COUNTERFACTUAL_SCENARIOS,
    AuthoritativeSourceRef,
    OutcomeAttributionError,
    OutcomeResult,
    build_actual_outcomes,
    compare_outcome_results,
    evaluate_historical_counterfactual,
)
from src.evidence.contracts import create_evidence_record
from src.episodes.position_episode import build_position_episode_lifecycle


SUBJECT_ID = "outcome-subject"
ACCOUNT_ID = "BROKER-A"
INITIAL_CASH = 100_000.0
CODE_VERSION = "decision-outcome-test-v1"


def _executions(
    rows: list[tuple[str, str, str, float, float]],
    *,
    fees: list[float] | None = None,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=(
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
        ),
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    frame["fee"] = fees if fees is not None else [0.0] * len(frame)
    frame["order_id"] = [f"ORD-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"EXE-{index}" for index in range(len(frame))]
    frame["account_id"] = ACCOUNT_ID
    frame["subject_id"] = SUBJECT_ID
    return frame


def _prices(values: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date,
                "instrument": symbol,
                "close": close,
                "price_type": "synthetic",
                "data_source": "decision_outcome_test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for symbol, closes in values.items()
            for date, close in zip(dates, closes)
        ]
    )


def _lifecycle(
    executions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    as_of: str,
):
    return build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        as_of=pd.Timestamp(as_of),
        init_cash=INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )


def _actual(executions: pd.DataFrame, prices: pd.DataFrame, *, as_of: str):
    lifecycle = _lifecycle(executions, prices, as_of=as_of)
    analysis = build_actual_outcomes(
        lifecycle,
        executions,
        prices,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        analysis_as_of=pd.Timestamp(as_of),
        init_cash=INITIAL_CASH,
    )
    return lifecycle, analysis


def _scenario(
    executions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    as_of: str,
    decision_index: int,
    scenario_id: str,
    exit_evidence=None,
):
    lifecycle = _lifecycle(executions, prices, as_of=as_of)
    result = evaluate_historical_counterfactual(
        lifecycle,
        executions,
        prices,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        decision_event_id=lifecycle.decisions[decision_index].decision_id,
        scenario_id=scenario_id,
        analysis_as_of=pd.Timestamp(as_of),
        init_cash=INITIAL_CASH,
        exit_evidence=exit_evidence,
    )
    return lifecycle, result


def _source(kind: str = "vectorbt_position") -> AuthoritativeSourceRef:
    return AuthoritativeSourceRef(
        source_kind=kind,  # type: ignore[arg-type]
        source_record_id=f"{kind}:test",
        replay_scope_id="replay-test",
        vectorbt_record_id=0,
        execution_refs=("EXE-0",),
    )


def _result(pnl: float, *, basis: str = "net_pnl") -> OutcomeResult:
    sign = "profit" if pnl > 0 else "loss" if pnl < 0 else "flat"
    return OutcomeResult(
        result_kind="counterfactual",
        result_basis=basis,  # type: ignore[arg-type]
        pnl=pnl,
        return_value=None,
        result_sign=sign,
        position_status="closed",
        recorded_entry_fees=0.0,
        recorded_exit_fees=0.0,
        valuation_at=None,
        valuation_price=None,
        source=_source(),
    )


def test_closed_episode_pnl_is_copied_from_vectorbt_position():
    executions = _executions(
        [("2025-01-02 09:30", "A", "BUY", 100, 10),
         ("2025-01-03 09:30", "A", "SELL", 100, 12)],
        fees=[1.0, 2.0],
    )
    prices = _prices({"A": [10, 12]}, ["2025-01-02", "2025-01-03"])

    lifecycle, analysis = _actual(executions, prices, as_of="2025-01-03 23:59")

    episode = analysis.episode_outcomes[0]
    assert episode.actual_result.pnl == pytest.approx(197.0)
    assert episode.actual_result.result_kind == "realized"
    assert episode.actual_result.source.source_kind == "vectorbt_position"
    assert episode.actual_result.source.execution_refs == ("EXE-0", "EXE-1")
    assert episode.decision_event_refs == lifecycle.episodes[0].decision_refs
    assert episode.execution_refs == lifecycle.episodes[0].execution_refs
    assert analysis.decision_outcomes[0].episode_result_ref == episode.outcome_id
    assert analysis.decision_outcomes[0].provenance == episode.provenance


def test_partial_sell_maps_to_one_authoritative_closed_exit_trade():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 40, 12)],
        fees=[1.0, 2.0],
    )
    prices = _prices({"A": [10, 12]}, ["2025-01-02", "2025-01-03"])

    _, analysis = _actual(executions, prices, as_of="2025-01-03")
    sell = analysis.decision_outcomes[1]

    assert sell.event_type == "reduce_position"
    assert sell.after.quantity == pytest.approx(60.0)
    assert sell.immediate_result is not None
    assert sell.immediate_result.pnl == pytest.approx(77.6)
    assert sell.immediate_result.recorded_entry_fees == pytest.approx(0.4)
    assert sell.immediate_result.recorded_exit_fees == pytest.approx(2.0)
    assert sell.immediate_result.source.source_kind == "vectorbt_exit_trade"
    assert sell.immediate_result.source.execution_refs == ("EXE-1",)


def test_loss_realization_does_not_close_partial_position():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 50, 8)]
    )
    prices = _prices({"A": [10, 8]}, ["2025-01-02", "2025-01-03"])

    _, analysis = _actual(executions, prices, as_of="2025-01-03")

    sell = analysis.decision_outcomes[1]
    assert sell.immediate_result is not None
    assert sell.immediate_result.pnl == pytest.approx(-100.0)
    assert sell.immediate_result.result_sign == "loss"
    assert sell.after.position_status == "open"
    assert analysis.episode_outcomes[0].episode_status == "open"


def test_buy_has_no_invented_realized_result():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [11]}, ["2025-01-02"])

    _, analysis = _actual(executions, prices, as_of="2025-01-02")

    buy = analysis.decision_outcomes[0]
    assert buy.immediate_result is None
    assert buy.relation_types == ("deterministic_state_transition",)


def test_open_episode_result_is_marked_not_realized_or_exit():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 40, 12)],
        fees=[1.0, 2.0],
    )
    prices = _prices({"A": [10, 12, 9]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, analysis = _actual(executions, prices, as_of="2025-01-04")
    result = analysis.episode_outcomes[0].actual_result

    assert result.result_kind == "marked"
    assert result.position_status == "open"
    assert result.valuation_at == pd.Timestamp("2025-01-04")
    assert result.valuation_price == pytest.approx(9.0)
    assert analysis.episode_outcomes[0].relation_type == "marked_position_result"


def test_decision_states_preserve_vectorbt_quantity_and_average_cost():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 12),
         ("2025-01-04", "A", "SELL", 20, 11)]
    )
    prices = _prices({"A": [10, 12, 11]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, analysis = _actual(executions, prices, as_of="2025-01-04")

    add = analysis.decision_outcomes[1]
    reduce = analysis.decision_outcomes[2]
    assert add.before.quantity == pytest.approx(100)
    assert add.before.average_cost == pytest.approx(10)
    assert add.after.quantity == pytest.approx(150)
    assert add.after.average_cost == pytest.approx(10.6666666667)
    assert reduce.after.quantity == pytest.approx(130)
    assert reduce.after.average_cost == pytest.approx(10.6666666667)


def test_final_sell_becomes_closed_and_uses_second_exit_trade():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 40, 12),
         ("2025-01-04", "A", "SELL", 60, 8)],
        fees=[1.0, 2.0, 3.0],
    )
    prices = _prices({"A": [10, 12, 8]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, analysis = _actual(executions, prices, as_of="2025-01-04")

    first_sell, final_sell = analysis.decision_outcomes[1:]
    assert first_sell.immediate_result.source.vectorbt_record_id == 0
    assert final_sell.immediate_result.source.vectorbt_record_id == 1
    assert final_sell.after.position_status == "flat"
    assert final_sell.event_type == "close_position"
    assert analysis.episode_outcomes[0].actual_result.pnl == pytest.approx(-46.0)


def test_local_omit_add_uses_two_replays_and_expected_marked_results():
    executions = _executions(
        [("2025-01-02 09:30", "A", "BUY", 100, 10),
         ("2025-01-03 09:30", "A", "BUY", 50, 12),
         ("2025-01-04 09:30", "A", "SELL", 10, 9)]
    )
    prices = _prices({"A": [10, 12, 9]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-04 23:59",
        decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert result.feasibility_status == "complete"
    assert result.evaluation_end == pd.Timestamp("2025-01-04 09:30")
    assert result.actual_result.pnl == pytest.approx(-250.0)
    assert result.counterfactual_result.pnl == pytest.approx(-100.0)
    assert result.comparison.pnl_difference == pytest.approx(150.0)
    assert result.comparison.result_transition == "loss_reduced"


def test_local_omit_reduce_reports_counterfactual_minus_actual_direction():
    executions = _executions(
        [("2025-01-02 09:30", "A", "BUY", 100, 10),
         ("2025-01-03 09:30", "A", "SELL", 40, 9),
         ("2025-01-04 09:30", "A", "SELL", 10, 8)]
    )
    prices = _prices({"A": [10, 9, 8]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-04 23:59",
        decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert result.actual_result.pnl == pytest.approx(-160.0)
    assert result.counterfactual_result.pnl == pytest.approx(-200.0)
    assert result.comparison.pnl_difference == pytest.approx(-40.0)
    assert result.comparison.result_transition == "loss_increased"


def test_full_episode_omit_is_complete_only_when_all_later_orders_remain_legal():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 20, 12),
         ("2025-01-04", "A", "SELL", 40, 15),
         ("2025-01-05", "A", "SELL", 60, 14)]
    )
    prices = _prices(
        {"A": [10, 12, 15, 14, 13]},
        ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"],
    )

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-06",
        decision_index=1,
        scenario_id="omit_event_preserve_later_executions_v1",
    )

    assert result.feasibility_status == "complete"
    assert result.actual_result.pnl == pytest.approx(460.0)
    assert result.actual_result.position_status == "open"
    assert result.counterfactual_result.pnl == pytest.approx(440.0)
    assert result.counterfactual_result.position_status == "closed"
    assert result.comparison.pnl_difference == pytest.approx(-20.0)


def test_full_episode_omit_fails_closed_at_first_illegal_downstream_order():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 11),
         ("2025-01-04", "A", "SELL", 120, 12)]
    )
    prices = _prices({"A": [10, 11, 12]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-04",
        decision_index=1,
        scenario_id="omit_event_preserve_later_executions_v1",
    )

    assert result.feasibility_status == "infeasible_downstream_execution"
    assert result.first_conflicting_execution_id == "EXE-2"
    assert result.actual_result is None
    assert result.counterfactual_result is None
    assert result.comparison.comparison_status == "not_applicable"

    _, local = _scenario(
        executions,
        prices,
        as_of="2025-01-04",
        decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )
    assert local.feasibility_status == "complete"


def test_infeasible_full_omit_never_clamps_or_rescales_downstream_quantity():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 11),
         ("2025-01-04", "A", "SELL", 120, 12)]
    )
    original = executions.copy(deep=True)
    prices = _prices({"A": [10, 11, 12]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-04",
        decision_index=1,
        scenario_id="omit_event_preserve_later_executions_v1",
    )

    pd.testing.assert_frame_equal(executions, original)
    assert executions.loc[2, "executed_quantity"] == 120
    assert "absolute_quantity" in result.downstream_order_policy


def test_local_open_omit_without_exact_as_of_price_is_insufficient_not_filled():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10, 11]}, ["2025-01-02", "2025-01-03"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-04",
        decision_index=0,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert result.feasibility_status == "insufficient_counterfactual_data"
    assert result.actual_result is None
    assert result.counterfactual_result is None
    assert "No unique market price" in result.infeasible_reason


def test_local_open_omit_represents_structural_absence_without_fake_return():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10, 11]}, ["2025-01-02", "2025-01-03"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-03",
        decision_index=0,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert result.feasibility_status == "complete"
    assert result.actual_result.source.source_kind == "vectorbt_position"
    assert result.counterfactual_result.position_status == "absent"
    assert result.counterfactual_result.pnl == 0.0
    assert result.counterfactual_result.return_value is None
    assert (
        result.counterfactual_result.source.source_kind
        == "registered_counterfactual_position_absent"
    )


def test_price_after_local_evaluation_horizon_does_not_change_result_or_id():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 12),
         ("2025-01-04", "A", "SELL", 10, 9)]
    )
    base_prices = _prices(
        {"A": [10, 12, 9, 20]},
        ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
    )
    changed = base_prices.copy(deep=True)
    changed.loc[changed["date"] == "2025-01-05", "close"] = 999.0

    _, first = _scenario(
        executions, base_prices, as_of="2025-01-05", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )
    _, second = _scenario(
        executions, changed, as_of="2025-01-05", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert first == second


def test_execution_after_analysis_as_of_does_not_change_actual_outcomes():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10, 11]}, ["2025-01-02", "2025-01-03"])
    lifecycle, first = _actual(executions, prices, as_of="2025-01-03")
    future = _executions([("2025-01-04", "A", "SELL", 100, 999)])
    future["order_id"] = "ORD-FUTURE"
    future["execution_id"] = "EXE-FUTURE"
    extended = pd.concat([executions, future], ignore_index=True)

    second = build_actual_outcomes(
        lifecycle,
        extended,
        prices,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        analysis_as_of=pd.Timestamp("2025-01-03"),
        init_cash=INITIAL_CASH,
    )

    assert second == first


def test_wrong_subject_fails_closed_for_executions():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10]}, ["2025-01-02"])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-02")
    executions["subject_id"] = "another-subject"

    with pytest.raises(OutcomeAttributionError, match="subject_id"):
        build_actual_outcomes(
            lifecycle,
            executions,
            prices,
            subject_id=SUBJECT_ID,
            account_id=ACCOUNT_ID,
            analysis_as_of=pd.Timestamp("2025-01-02"),
            init_cash=INITIAL_CASH,
        )


def test_actual_and_counterfactual_ids_are_deterministic():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 12),
         ("2025-01-04", "A", "SELL", 10, 9)]
    )
    prices = _prices({"A": [10, 12, 9]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    _, first_actual = _actual(executions, prices, as_of="2025-01-04")
    _, second_actual = _actual(executions.copy(), prices.copy(), as_of="2025-01-04")
    _, first_cf = _scenario(
        executions, prices, as_of="2025-01-04", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )
    _, second_cf = _scenario(
        executions.copy(), prices.copy(), as_of="2025-01-04", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert first_actual == second_actual
    assert first_cf == second_cf


def test_counterfactual_id_changes_when_input_data_version_changes():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 12),
         ("2025-01-04", "A", "SELL", 10, 9)]
    )
    prices = _prices({"A": [10, 12, 9]}, ["2025-01-02", "2025-01-03", "2025-01-04"])
    revised = prices.copy(deep=True)
    revised["data_version"] = "v2"

    _, first = _scenario(
        executions, prices, as_of="2025-01-04", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )
    _, second = _scenario(
        executions, revised, as_of="2025-01-04", decision_index=1,
        scenario_id="omit_event_until_next_decision_v1",
    )

    assert first.counterfactual_id != second.counterfactual_id


def test_distinct_time_input_order_is_canonicalized_by_existing_replay():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "BUY", 50, 12),
         ("2025-01-04", "A", "SELL", 10, 9)]
    )
    prices = _prices({"A": [10, 12, 9]}, ["2025-01-02", "2025-01-03", "2025-01-04"])
    shuffled = executions.iloc[[2, 0, 1]].reset_index(drop=True)

    _, first = _actual(executions, prices, as_of="2025-01-04")
    _, second = _actual(shuffled, prices, as_of="2025-01-04")

    assert second == first


def test_result_basis_mismatch_prevents_pnl_comparison():
    comparison = compare_outcome_results(
        _result(-10, basis="net_pnl"),
        _result(5, basis="gross_pnl_before_incremental_friction"),
    )

    assert comparison.comparison_status == "unavailable_result_basis_mismatch"
    assert comparison.result_basis is None
    assert comparison.pnl_difference is None
    assert comparison.result_transition is None


def test_net_basis_comparison_has_frozen_counterfactual_minus_actual_sign():
    comparison = compare_outcome_results(_result(-100), _result(20))

    assert comparison.comparison_status == "complete"
    assert comparison.result_basis == "net_pnl"
    assert comparison.pnl_difference == pytest.approx(120)
    assert comparison.result_transition == "loss_to_profit"


@pytest.mark.parametrize(
    ("actual", "counterfactual", "transition"),
    [
        (-100.0, -40.0, "loss_reduced"),
        (-40.0, -100.0, "loss_increased"),
        (0.0, 0.0, "matched"),
        (100.0, 150.0, "profit_increased"),
        (100.0, -1.0, "profit_to_loss"),
    ],
)
def test_result_transition_is_objective_arithmetic(actual, counterfactual, transition):
    assert compare_outcome_results(
        _result(actual), _result(counterfactual)
    ).result_transition == transition


def test_exit_scenario_reuses_exact_existing_evidence_without_recalculation():
    executions = _executions(
        [("2025-06-01", "A", "BUY", 100, 90),
         ("2025-06-02", "A", "SELL", 100, 99.5)]
    )
    dates = pd.date_range("2025-06-01", periods=22, freq="D")
    prices = _prices(
        {"A": [90.0, 100.0, *([101.0] * 19), 120.0]},
        [str(item.date()) for item in dates],
    )
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-22")
    episode = lifecycle.episodes[0]
    evidence = create_evidence_record(
        subject_id=SUBJECT_ID,
        metric_id="exit_timing_post_exit_asset_return",
        evidence_kind="decision_evidence",
        method_id="hold_20_sessions_v1",
        method_version="1",
        observation_start=pd.Timestamp("2025-06-02"),
        observation_end=pd.Timestamp("2025-06-22"),
        as_of=pd.Timestamp("2025-06-22"),
        value=0.20,
        numerator=None,
        denominator=None,
        observation_count=21,
        ci_lower=None,
        ci_upper=None,
        evidence_status="complete",
        evidence_reason=None,
        provenance=(),
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        limitations=("Fixed historical window.",),
        attributes={
            "episode_id": episode.episode_id,
            "actual_exit_price": 99.5,
            "exit_session_market_price": 100.0,
            "counterfactual_exit_price": 120.0,
        },
        identity_attributes={"episode_id": episode.episode_id},
    )

    result = evaluate_historical_counterfactual(
        lifecycle,
        executions,
        prices,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        decision_event_id=lifecycle.decisions[1].decision_id,
        scenario_id="existing_exit_evidence_reuse_v1",
        analysis_as_of=pd.Timestamp("2025-06-22"),
        init_cash=INITIAL_CASH,
        exit_evidence=evidence,
    )

    assert result.feasibility_status == "complete"
    assert result.baseline_evidence_ref == evidence.evidence_id
    assert result.counterfactual_result is None
    assert result.evaluation_end == evidence.observation_end
    assert result.price_basis == "existing_exit_evidence:exit_session_market_price_to_policy_end"
    assert evidence.attributes["actual_exit_price"] == 99.5
    assert evidence.attributes["exit_session_market_price"] == 100.0
    assert evidence.value == pytest.approx(0.20)


def test_exit_evidence_from_another_subject_fails_closed():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 100, 11)]
    )
    prices = _prices({"A": [10, 11]}, ["2025-01-02", "2025-01-03"])
    lifecycle = _lifecycle(executions, prices, as_of="2025-01-03")
    evidence = create_evidence_record(
        subject_id="another-subject",
        metric_id="exit_timing_post_exit_asset_return",
        evidence_kind="decision_evidence",
        method_id="hold_20_sessions_v1",
        method_version="1",
        observation_start=pd.Timestamp("2025-01-03"),
        observation_end=pd.Timestamp("2025-01-03"),
        as_of=pd.Timestamp("2025-01-03"),
        value=0.0,
        numerator=None,
        denominator=None,
        observation_count=1,
        ci_lower=None,
        ci_upper=None,
        evidence_status="complete",
        evidence_reason=None,
        provenance=(),
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
        limitations=(),
        attributes={"episode_id": lifecycle.episodes[0].episode_id},
        identity_attributes={"episode_id": lifecycle.episodes[0].episode_id},
    )

    with pytest.raises(OutcomeAttributionError, match="subject_id"):
        evaluate_historical_counterfactual(
            lifecycle,
            executions,
            prices,
            subject_id=SUBJECT_ID,
            account_id=ACCOUNT_ID,
            decision_event_id=lifecycle.decisions[1].decision_id,
            scenario_id="existing_exit_evidence_reuse_v1",
            analysis_as_of=pd.Timestamp("2025-01-03"),
            init_cash=INITIAL_CASH,
            exit_evidence=evidence,
        )


def test_close_and_reopen_episodes_keep_separate_position_sources():
    executions = _executions(
        [("2025-01-02 09:30", "A", "BUY", 100, 10),
         ("2025-01-03 10:00", "A", "SELL", 100, 11),
         ("2025-01-03 14:00", "A", "BUY", 40, 12)]
    )
    prices = _prices({"A": [10, 11.5]}, ["2025-01-02", "2025-01-03"])

    _, analysis = _actual(executions, prices, as_of="2025-01-03 23:59")

    assert [item.episode_status for item in analysis.episode_outcomes] == ["closed", "open"]
    assert [
        item.actual_result.source.vectorbt_record_id
        for item in analysis.episode_outcomes
    ] == [0, 1]
    assert analysis.episode_outcomes[0].execution_refs == ("EXE-0", "EXE-1")
    assert analysis.episode_outcomes[1].execution_refs == ("EXE-2",)


def test_unregistered_and_deferred_scenarios_return_explicit_unsupported_status():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100, 10),
         ("2025-01-03", "A", "SELL", 40, 11)]
    )
    prices = _prices({"A": [10, 11]}, ["2025-01-02", "2025-01-03"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-03",
        decision_index=1,
        scenario_id="close_all_instead_of_reduce_v1",
    )

    assert result.feasibility_status == "unsupported_scenario"
    assert "not registered" in result.infeasible_reason
    assert "close_all_instead_of_reduce_v1" not in COUNTERFACTUAL_SCENARIOS


def test_registered_scenario_rejects_inapplicable_event_without_losing_version():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10]}, ["2025-01-02"])

    _, result = _scenario(
        executions,
        prices,
        as_of="2025-01-02",
        decision_index=0,
        scenario_id="existing_exit_evidence_reuse_v1",
    )

    assert result.feasibility_status == "unsupported_scenario"
    assert result.scenario_version == "1"


def test_mapping_ambiguity_fails_closed():
    from src.attribution.decision_outcome import _unique

    records = pd.DataFrame({"id": [1, 2]})
    with pytest.raises(OutcomeAttributionError, match="found 2"):
        _unique(records, pd.Series([True, True]), "exit trade")


def test_same_timestamp_multi_symbol_order_mapping_is_deterministic():
    executions = _executions(
        [("2025-01-02 09:30", "B", "BUY", 10, 20),
         ("2025-01-02 09:30", "A", "BUY", 10, 10)]
    )
    prices = _prices(
        {"A": [10, 11], "B": [20, 21]},
        ["2025-01-02", "2025-01-03"],
    )

    _, first = _actual(executions, prices, as_of="2025-01-03")
    _, second = _actual(executions.copy(deep=True), prices.copy(deep=True), as_of="2025-01-03")

    assert first == second
    sources = {
        item.execution_id: item.execution_source.vectorbt_record_id
        for item in first.decision_outcomes
    }
    assert sources == {"EXE-0": 0, "EXE-1": 1}


def test_outcome_contract_has_no_recommendation_or_optimizer_fields():
    from src.attribution.decision_outcome import HistoricalCounterfactualResult

    names = {item.name for item in fields(HistoricalCounterfactualResult)}
    assert names.isdisjoint(
        {
            "recommended_action",
            "should_buy",
            "should_sell",
            "best_trade",
            "optimal_exit",
            "target_weight",
        }
    )


def test_outcome_module_contains_no_handcrafted_price_cost_quantity_pnl_formula():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "attribution"
        / "decision_outcome.py"
    ).read_text(encoding="utf-8")

    assert "execution_price - average_cost" not in source
    assert "(price - cost)" not in source
    assert "* quantity" not in source


def test_calculation_code_version_is_part_of_outcome_contract_and_identity():
    executions = _executions([("2025-01-02", "A", "BUY", 100, 10)])
    prices = _prices({"A": [10]}, ["2025-01-02"])

    _, analysis = _actual(executions, prices, as_of="2025-01-02")

    assert analysis.calculation_code_version == CODE_VERSION
    assert analysis.episode_outcomes[0].calculation_code_version == CODE_VERSION
    assert analysis.decision_outcomes[0].calculation_code_version == CODE_VERSION
