from dataclasses import replace

import pandas as pd
import pytest

from scripts.export_desktop_demo_evidence import build_export
from src.attribution.decision_evidence_statistics import (
    DecisionObservation,
    build_decision_evidence_statistics,
)
from src.attribution.exit_timing_evidence import (
    COUNTERFACTUAL_NOTICE,
    ExitPriceObservation,
    ExitTimingEvidence,
)
from src.attribution.selection_evidence import PriceProvenance
from src.behavior.loss_averaging import build_loss_averaging_evidence
from src.behavior.portfolio_concentration import (
    build_portfolio_concentration_evidence,
)
from src.evidence.adapters import (
    adapt_decision_evidence_statistics,
    adapt_exit_timing_evidence,
    adapt_loss_averaging_evidence,
    adapt_portfolio_concentration_evidence,
)
from src.evidence.explainability import (
    ExplainabilityError,
    build_completed_exit_decision_trace,
    build_explainability_view,
    build_open_position_valuation_trace,
    build_pretrade_hhi_trace,
    get_calculation_trace,
)
from src.evidence.registry import get_concept, list_concepts
from src.episodes.position_episode import (
    DecisionEvent,
    EpisodeSnapshot,
    PositionEpisode,
    ReplayPositionState,
)
from src.pretrade.impact import (
    LIMITATIONS as PRETRADE_LIMITATIONS,
    PortfolioImpactState,
    ProposedTrade,
    TradeImpact,
    TradeImpactDelta,
)


SUBJECT = "investor:explainability-test"
CODE_VERSION = "explainability-test-v1"


def _executions(rows: list[tuple[object, ...]]) -> pd.DataFrame:
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
    frame["fee"] = 0.0
    frame["order_id"] = [f"ORD-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"EXE-{index}" for index in range(len(frame))]
    return frame


def _prices(prices: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date,
                "instrument": symbol,
                "close": close,
                "price_type": "synthetic",
                "data_source": "explainability_test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for symbol, values in prices.items()
            for date, close in zip(dates, values)
        ]
    )


def _adapt_hhi(executions: pd.DataFrame, prices: pd.DataFrame):
    source = build_portfolio_concentration_evidence(
        executions,
        prices,
        init_cash=10_000.0,
    )
    record = adapt_portfolio_concentration_evidence(
        source,
        subject_id=SUBJECT,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )
    return source, record


def _loss_trace(second_buy_price: float):
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 100.0, 10.20),
            ("2025-01-03", "A", "BUY", 50.0, second_buy_price),
        ]
    )
    source = build_loss_averaging_evidence(
        executions,
        _prices({"A": [10.20, second_buy_price]}, ["2025-01-02", "2025-01-03"]),
        init_cash=10_000.0,
    )
    record = adapt_loss_averaging_evidence(
        source,
        subject_id=SUBJECT,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )
    return get_calculation_trace(record, source)


def _exit_source(*, complete: bool = True) -> ExitTimingEvidence:
    dates = pd.bdate_range("2025-02-03", periods=21)
    observations = tuple(
        ExitPriceObservation(date, 100.0 + index)
        for index, date in enumerate(dates)
    )
    return ExitTimingEvidence(
        episode_id="episode:exit-test",
        symbol="A",
        actual_exit_time=dates[0],
        actual_exit_price=99.50,
        policy_id="hold_20_sessions_v1",
        policy_sessions=20,
        counterfactual_exit_time=dates[-1] if complete else None,
        exit_session_market_price=100.0 if complete else None,
        counterfactual_exit_price=120.0 if complete else None,
        post_exit_asset_return=0.20 if complete else None,
        comparison=("actual_exit_underperformed_hold_baseline" if complete else None),
        evidence_status=("complete" if complete else "insufficient_evidence"),
        evidence_reason=(None if complete else "followup_window_not_elapsed"),
        provenance=PriceProvenance(
            instrument="A",
            data_source="explainability_test",
            data_version="v1",
            as_of=dates[-1] if complete else dates[0],
            price_type="synthetic",
            is_synthetic=True,
        ),
        counterfactual_notice=COUNTERFACTUAL_NOTICE,
        window_prices=observations if complete else (),
    )


def _adapt_exit(source: ExitTimingEvidence):
    return adapt_exit_timing_evidence(
        source,
        subject_id=SUBJECT,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )


def _complete_impact() -> TradeImpact:
    trade = ProposedTrade(
        SUBJECT,
        pd.Timestamp("2025-01-08 15:00"),
        "A",
        "BUY",
        10.0,
        13.0,
        1.0,
    )
    return TradeImpact(
        proposed_trade=trade,
        before=PortfolioImpactState(1_000.0, 2_000.0, 50.0, 0.30, 12.0, 0.52, 2),
        after=PortfolioImpactState(869.0, 1_989.0, 60.0, 0.36, 12.0, 0.58, 2),
        delta=TradeImpactDelta(-131.0, 0.06, 0.06),
        self_context=None,
        peer_context=None,
        simulation_status="complete",
        simulation_reason=None,
        data_tier="synthetic",
        limitations=PRETRADE_LIMITATIONS,
        hypothetical_execution_id="hypothetical:stable-test",
        before_hhi_evidence_id="ev_before",
        after_hhi_evidence_id="ev_after",
    )


def test_hhi_trace_matches_hand_calculation_and_provenance():
    source, record = _adapt_hhi(
        _executions(
            [
                ("2025-01-02", "A", "BUY", 5.0, 10.0),
                ("2025-01-02", "B", "BUY", 3.0, 10.0),
                ("2025-01-02", "C", "BUY", 2.0, 10.0),
            ]
        ),
        _prices(
            {"A": [10.0], "B": [10.0], "C": [10.0]},
            ["2025-01-02"],
        ),
    )

    trace = get_calculation_trace(record, source)

    assert [item.value for item in trace.inputs] == [0.5, 0.3, 0.2]
    assert [item.attributes["asset_value"] for item in trace.inputs] == [50.0, 30.0, 20.0]
    assert trace.operations[0].formula_display == "sum(weight_i ** 2)"
    assert trace.result == pytest.approx(0.5**2 + 0.3**2 + 0.2**2)
    assert all(item.source_ref in trace.source_refs for item in trace.inputs)
    assert trace.provenance == record.provenance


@pytest.mark.parametrize(
    ("second_buy_price", "expected"),
    ((9.40, True), (11.00, False)),
)
def test_loss_state_addition_trace_uses_actual_buy_execution_price(
    second_buy_price: float,
    expected: bool,
):
    trace = _loss_trace(second_buy_price)
    operation = next(item for item in trace.operations if item.operation_kind == "strict_less_than")
    inputs = {item.semantic_name: item for item in trace.inputs}

    assert inputs["pre_trade_avg_cost"].value == pytest.approx(10.20)
    assert inputs["execution_price"].value == pytest.approx(second_buy_price)
    assert inputs["execution_price"].source_ref == "execution:EXE-1"
    assert operation.formula_display == "execution_price < pre_trade_avg_cost"
    assert operation.result is expected


def test_exit_trace_keeps_episode_execution_context_separate_from_market_window():
    source = _exit_source()
    trace = get_calculation_trace(_adapt_exit(source), source)
    inputs = {item.input_id: item for item in trace.inputs}

    assert inputs["episode_avg_exit_price"].value == 99.50
    assert inputs["episode_avg_exit_price"].role == "context_not_return_formula"
    assert inputs["window_price:0"].value == 100.0
    assert inputs["window_price:20"].value == 120.0
    assert trace.operations[0].input_refs[0] == "window_price:0"
    assert "episode_avg_exit_price" not in trace.operations[0].input_refs
    assert trace.operations[0].attributes["episode_avg_exit_price_used_in_formula"] is False
    assert trace.result == 0.20


def test_pretrade_trace_does_not_confuse_execution_and_valuation_prices():
    trace = build_pretrade_hhi_trace(
        _complete_impact(),
        calculation_code_version=CODE_VERSION,
    )
    inputs = {item.input_id: item for item in trace.inputs}

    assert inputs["proposed_execution_price"].value == 13.0
    assert inputs["proposed_execution_price"].role == "execution_assumption"
    assert inputs["post_trade_valuation_price"].value == 12.0
    assert inputs["post_trade_valuation_price"].role == "mark_not_execution"
    assert trace.result == 0.06
    assert "future_return_prediction" in get_concept(
        trace.concept_id
    ).interpretation_boundary.prohibited_claims


def test_insufficient_followup_retains_reason_without_complete_operation():
    source = _exit_source(complete=False)
    trace = get_calculation_trace(_adapt_exit(source), source)

    assert trace.calculation_status == "insufficient"
    assert trace.result is None
    assert trace.operations == ()
    assert trace.reason == "followup_window_not_elapsed"
    assert trace.required_condition == "completed_final_exit_and_20_subsequent_market_sessions"
    assert trace.available_observation["window_price_count"] == 0


def test_statistical_trace_copies_existing_ci_without_recalculation():
    source = build_decision_evidence_statistics(
        (
            DecisionObservation("sizing", pd.Timestamp("2025-01-01"), "a", "positive"),
            DecisionObservation("sizing", pd.Timestamp("2025-01-02"), "b", "negative"),
            DecisionObservation("sizing", pd.Timestamp("2025-01-03"), "c", "matched"),
        )
    )
    record = adapt_decision_evidence_statistics(
        source,
        subject_id=SUBJECT,
        data_tier="synthetic",
        calculation_code_version=CODE_VERSION,
    )
    trace = get_calculation_trace(record, source)
    inputs = {item.input_id: item.value for item in trace.inputs}

    assert inputs["ci_lower"] == source.hit_rate_ci95_low
    assert inputs["ci_upper"] == source.hit_rate_ci95_high
    assert trace.operations[0].attributes["ci_recalculated"] is False


def test_same_evidence_produces_identical_trace_and_id():
    source, record = _adapt_hhi(
        _executions([("2025-01-02", "A", "BUY", 1.0, 10.0)]),
        _prices({"A": [10.0]}, ["2025-01-02"]),
    )

    first = get_calculation_trace(record, source)
    second = get_calculation_trace(record, source)

    assert first == second
    assert first.trace_id == second.trace_id


def test_future_evidence_cannot_enter_an_earlier_explainability_view():
    source, record = _adapt_hhi(
        _executions([("2025-01-02", "A", "BUY", 1.0, 10.0)]),
        _prices({"A": [10.0]}, ["2025-01-02"]),
    )

    with pytest.raises(ExplainabilityError, match="not available"):
        build_explainability_view(record, source, as_of=pd.Timestamp("2025-01-01"))


def test_missing_market_price_stays_insufficient_without_fill_or_guess():
    source, record = _adapt_hhi(
        _executions(
            [
                ("2025-01-02", "A", "BUY", 1.0, 10.0),
                ("2025-01-02", "B", "BUY", 1.0, 10.0),
            ]
        ),
        _prices({"A": [10.0]}, ["2025-01-02"]),
    )
    trace = get_calculation_trace(record, source)

    assert trace.calculation_status == "insufficient"
    assert trace.result is None
    assert trace.inputs == ()
    assert "Missing market prices" in trace.reason


def test_open_episode_mark_is_valuation_not_exit():
    episode = PositionEpisode(
        "episode:open", SUBJECT, "account:test", "A",
        pd.Timestamp("2025-01-01"), None, "open", "EXE-1", None,
        ("EXE-1",), ("decision:1",), (), 7, "so_far",
        "vectorbt_portfolio_replay_v1", CODE_VERSION, (), "synthetic", (),
    )
    state = ReplayPositionState(
        "state:open", SUBJECT, "account:test", "A",
        pd.Timestamp("2025-01-08"), "as_of_valuation", None, 100.0, 10.0,
        pd.Timestamp("2025-01-08"), 12.0, 1_200.0,
        "vectorbt_portfolio_replay_v1",
    )
    snapshot = EpisodeSnapshot("episode:open", pd.Timestamp("2025-01-08"), "state:open")

    trace = build_open_position_valuation_trace(
        episode,
        snapshot,
        state,
        calculation_code_version=CODE_VERSION,
    )

    assert trace.concept_id == "valuation_price"
    assert trace.inputs[0].role == "mark_not_exit"
    assert trace.available_observation["is_exit"] is False


def test_partial_sell_cannot_be_explained_as_final_exit():
    decision = DecisionEvent(
        "decision:reduce", "episode:1", "EXE-2", pd.Timestamp("2025-01-02"),
        "reduce_position", "SELL", 10.0, 12.0, 0.0,
        "state:before", "state:after", (),
    )

    with pytest.raises(ExplainabilityError, match="partial SELL"):
        build_completed_exit_decision_trace(
            decision,
            calculation_code_version=CODE_VERSION,
        )


def test_malformed_record_source_cross_reference_fails_closed():
    source, record = _adapt_hhi(
        _executions([("2025-01-02", "A", "BUY", 1.0, 10.0)]),
        _prices({"A": [10.0]}, ["2025-01-02"]),
    )

    with pytest.raises(ExplainabilityError, match="does not match"):
        get_calculation_trace(replace(record, value=0.25), source)


def test_complete_hhi_without_calculator_components_is_rejected():
    source, record = _adapt_hhi(
        _executions([("2025-01-02", "A", "BUY", 1.0, 10.0)]),
        _prices({"A": [10.0]}, ["2025-01-02"]),
    )
    malformed_source = replace(source, weight_components=())

    with pytest.raises(ExplainabilityError, match="trace component|weight components"):
        get_calculation_trace(record, malformed_source)


def test_registry_ids_and_evidence_method_bindings_are_unique():
    concepts = list_concepts()
    ids = [item.concept_id for item in concepts]
    bindings = [
        (item.metric_id, item.method_id, item.method_version)
        for item in concepts
        if item.metric_id is not None
    ]

    assert len(ids) == len(set(ids))
    assert len(bindings) == len(set(bindings))
    assert all(
        "investment_advice" in item.interpretation_boundary.prohibited_claims
        for item in concepts
    )
    assert {
        "portfolio_concentration_hhi",
        "turnover_intensity",
        "disposition_effect",
        "loss_state_addition",
        "sizing_equal_weight_comparison",
        "sell_decision_evidence",
        "post_exit_fixed_window_return",
        "pretrade_concentration_impact",
        "valuation_price",
        "execution_price",
    }.issubset(ids)


def test_demo_export_contains_real_end_to_end_trace_types():
    payload = build_export()
    explainability = payload["explainability"]
    views = explainability["evidence_views"]

    assert explainability["schema_version"] == "1"
    assert {
        view.concept.concept_id for view in views
    } == {
        "portfolio_concentration_hhi",
        "turnover_intensity",
        "loss_state_addition",
        "sizing_equal_weight_comparison",
        "post_exit_fixed_window_return",
    }
    assert explainability["pretrade_trace"].concept_id == "pretrade_concentration_impact"
    assert explainability["pretrade_trace"].calculation_status == "complete"
