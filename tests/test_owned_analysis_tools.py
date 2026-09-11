from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace

import pandas as pd
import pytest

import src.agents.owned_analysis_tools as owned_analysis_tools
from src.agents.account_review_sources import (
    PREPARED_HHI_HISTORY_ATTRIBUTE,
    _PreparedHhiHistory,
    _hhi_input_identity,
    build_account_review_context,
)
from src.agents.review_sources import SELF_HISTORY_CALCULATION_CODE_VERSION
from src.agents.owned_analysis_tools import (
    MATERIALIZER_ATTRIBUTE,
    OwnedAnalysisError,
    attach_owned_analysis_sources,
    hypothetical_trade_impact,
    owned_period_comparison,
    owned_same_stock_comparison,
)
from src.demo import showcase
from src.demo.showcase_runtime import (
    CALCULATION_CODE_VERSION,
    _episode_mapping,
    _lifecycle,
)


@pytest.fixture()
def owned_context():
    identities, executions, prices, instruments = _episode_mapping(showcase.SUBJECT_ID)
    lifecycle = _lifecycle(executions, prices, subject_id=showcase.SUBJECT_ID)
    context = build_account_review_context(
        executions,
        prices,
        subject_id=showcase.SUBJECT_ID,
        account_id=showcase.SUBJECT_ID,
        data_mode="synthetic_showcase",
        as_of=showcase.AS_OF,
        init_cash=showcase.INITIAL_CASH,
        data_tier="synthetic",
        currency="CNY",
        lifecycle=lifecycle,
        display_names={item.instrument_id: symbol for symbol, item in instruments.items()},
        source_refs=("registered-showcase-source",),
        include_conversation=True,
    )
    context.episode_display_ids = {
        episode.episode_id: str(identities[episode.episode_id]["display_episode_id"])
        for episode in lifecycle.episodes
    }
    attach_owned_analysis_sources(
        context,
        executions=executions,
        market_prices=prices,
        init_cash=showcase.INITIAL_CASH,
        instruments=instruments,
        source_refs=("registered-showcase-source",),
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    return context, executions, prices, instruments, lifecycle


def _payload(value: str) -> dict[str, object]:
    return json.loads(value)


def test_materializer_is_one_time_scoped_detached_and_not_publicly_serialized(owned_context):
    context, executions, prices, instruments, _ = owned_context
    source = getattr(context, MATERIALIZER_ATTRIBUTE)
    assert source.executions is not executions
    assert source.market_prices is not prices
    assert MATERIALIZER_ATTRIBUTE not in asdict(context)

    copied = copy.deepcopy(context)
    copied_source = getattr(copied, MATERIALIZER_ATTRIBUTE)
    assert copied_source.subject_id == context.subject_id
    assert copied_source.executions is not source.executions

    with pytest.raises(OwnedAnalysisError, match="already_attached"):
        attach_owned_analysis_sources(
            context,
            executions=executions,
            market_prices=prices,
            init_cash=showcase.INITIAL_CASH,
            instruments=instruments,
        )

    invalid = copy.deepcopy(context)
    invalid_source = getattr(invalid, MATERIALIZER_ATTRIBUTE)
    delattr(invalid, MATERIALIZER_ATTRIBUTE)
    setattr(invalid, PREPARED_HHI_HISTORY_ATTRIBUTE, _PreparedHhiHistory(
        subject_id=invalid.subject_id,
        account_id=invalid.account_id,
        data_tier=invalid.data_tier,
        as_of=pd.Timestamp(invalid.as_of),
        init_cash=invalid_source.init_cash,
        calculation_code_version=SELF_HISTORY_CALCULATION_CODE_VERSION,
        input_identity="not-the-registered-inputs",
        history=invalid_source.hhi_history,
    ))
    with pytest.raises(OwnedAnalysisError, match="prepared_history_invalid"):
        attach_owned_analysis_sources(
            invalid,
            executions=executions,
            market_prices=prices,
            init_cash=showcase.INITIAL_CASH,
            instruments=instruments,
        )

    sparse = copy.deepcopy(context)
    sparse_source = getattr(sparse, MATERIALIZER_ATTRIBUTE)
    delattr(sparse, MATERIALIZER_ATTRIBUTE)
    sparse_history = replace(
        sparse_source.hhi_history,
        points=sparse_source.hhi_history.points[:-1],
    )
    setattr(sparse, PREPARED_HHI_HISTORY_ATTRIBUTE, _PreparedHhiHistory(
        subject_id=sparse.subject_id,
        account_id=sparse.account_id,
        data_tier=sparse.data_tier,
        as_of=pd.Timestamp(sparse.as_of),
        init_cash=sparse_source.init_cash,
        calculation_code_version=SELF_HISTORY_CALCULATION_CODE_VERSION,
        input_identity=_hhi_input_identity(executions, prices),
        history=sparse_history,
    ))
    attach_owned_analysis_sources(
        sparse,
        executions=executions,
        market_prices=prices,
        init_cash=showcase.INITIAL_CASH,
        instruments=instruments,
    )
    sparse_payload = _payload(hypothetical_trade_impact(
        sparse,
        symbol="SYN_GROWTH",
        side="BUY",
        quantity=300,
        execution_price=14.4,
        fees=0,
    ))
    assert sparse_payload["status"] == "insufficient_evidence"

    legacy = copy.deepcopy(context)
    delattr(legacy, MATERIALIZER_ATTRIBUTE)
    attach_owned_analysis_sources(
        legacy,
        executions=executions,
        market_prices=prices,
        init_cash=showcase.INITIAL_CASH,
        instruments=instruments,
    )
    assert getattr(legacy, MATERIALIZER_ATTRIBUTE).hhi_history is None


def test_materializer_rejects_mixed_or_wrong_account_scope(owned_context):
    context, executions, prices, instruments, _ = owned_context
    fresh = copy.deepcopy(context)
    delattr(fresh, MATERIALIZER_ATTRIBUTE)
    wrong = executions.copy(deep=True)
    wrong.loc[wrong.index[0], "account_id"] = "another-account"
    with pytest.raises(OwnedAnalysisError, match="account_scope_mismatch"):
        attach_owned_analysis_sources(
            fresh,
            executions=wrong,
            market_prices=prices,
            init_cash=showcase.INITIAL_CASH,
            instruments=instruments,
        )


def test_hypothetical_buy_requires_explicit_fees_then_reports_current_state_only(
    monkeypatch, owned_context,
):
    context, executions, prices, _, _ = owned_context
    original_executions = executions.copy(deep=True)
    original_prices = prices.copy(deep=True)

    needs_fees = _payload(hypothetical_trade_impact(
        context,
        symbol="SYN_GROWTH",
        side="BUY",
        quantity=300,
        execution_price=14.4,
        fees=None,
    ))
    assert needs_fees["status"] == "insufficient_evidence"
    assert needs_fees["records"][0]["availability"] == "clarification_required"
    assert needs_fees["records"][0]["value"]["reason_code"] == "fees_required"
    assert needs_fees["records"][0]["value"]["requested_parameters"] == {
        "symbol": "SYN_GROWTH", "side": "BUY", "quantity": 300.0,
        "execution_price": 14.4, "fees": None,
    }
    assert "not executed trades" in needs_fees["records"][0]["value"]["parameter_semantics"]

    def unexpected_history_rebuild(*args, **kwargs):
        raise AssertionError("prepared account HHI history must be reused")

    monkeypatch.setattr(
        owned_analysis_tools,
        "build_portfolio_hhi_history",
        unexpected_history_rebuild,
    )

    completed = _payload(hypothetical_trade_impact(
        context,
        symbol="SYN_GROWTH",
        side="BUY",
        quantity=300,
        execution_price=14.4,
        fees=0,
    ))
    assert completed["status"] == "complete"
    record = completed["records"][0]
    assert record["kind"] == "hypothetical_trade_impact"
    assert record["availability"] == "complete"
    assert record["ref"] in context.retrieved
    assert record["value"]["hypothetical_only"] is True
    assert record["value"]["canonical_records_mutated"] is False
    assert record["value"]["requested_at"] == context.as_of
    assert record["value"]["impact"]["proposed_trade"]["fees"] == 0.0
    assert record["value"]["impact"]["peer_context"] is None
    assert record["value"]["impact"]["before"]["valuation_observation_date"] == pd.Timestamp(
        context.as_of
    ).date().isoformat()
    assert "executions" not in json.dumps(completed)
    assert "market_prices" not in json.dumps(completed)
    pd.testing.assert_frame_equal(executions, original_executions)
    pd.testing.assert_frame_equal(prices, original_prices)


def test_hypothetical_trade_rejects_unknown_instrument_and_insufficient_cash(owned_context):
    context, *_ = owned_context
    unknown = _payload(hypothetical_trade_impact(
        context,
        symbol="NOT_OWNED",
        side="BUY",
        quantity=1,
        execution_price=1,
        fees=0,
    ))
    assert unknown["status"] == "insufficient_evidence"
    assert unknown["records"][0]["value"]["reason_code"] == (
        "instrument_not_registered_in_owned_scope"
    )

    rejected = _payload(hypothetical_trade_impact(
        context,
        symbol="SYN_GROWTH",
        side="BUY",
        quantity=100_000_000,
        execution_price=14.4,
        fees=0,
    ))
    assert rejected["status"] == "complete"
    assert rejected["records"][0]["availability"] == "rejected"
    assert rejected["records"][0]["value"]["impact"]["simulation_status"] == "rejected"
    assert "cash is insufficient" in rejected["records"][0]["value"]["impact"]["simulation_reason"]

    non_finite = _payload(hypothetical_trade_impact(
        context,
        symbol="SYN_GROWTH",
        side="BUY",
        quantity=float("nan"),
        execution_price=14.4,
        fees=0,
    ))
    assert non_finite["status"] == "insufficient_evidence"
    assert non_finite["records"][0]["value"]["reason_code"] == (
        "hypothetical_trade_inputs_invalid"
    )


def test_owned_period_comparison_uses_later_minus_earlier_without_professional_data(owned_context):
    context, *_ = owned_context
    result = _payload(owned_period_comparison(
        context,
        earlier_start="2025-01-02",
        earlier_end="2025-03-31",
        later_start="2025-03-31",
        later_end="2025-06-30",
    ))
    assert result["status"] == "complete"
    record = result["records"][0]
    comparison = record["value"]["comparison"]
    assert record["value"]["requested_periods"] == {
        "earlier": {"start": "2025-01-02", "end": "2025-03-31"},
        "later": {"start": "2025-03-31", "end": "2025-06-30"},
    }
    assert record["value"]["effective_periods"]["earlier"] | {
        "requested_start": "2025-01-02",
        "requested_end": "2025-03-31",
        "effective_start": "2025-01-02",
        "effective_end": "2025-03-31",
        "start_clipped": False,
        "end_clipped": False,
    } == record["value"]["effective_periods"]["earlier"]
    assert "no missing boundary is filled or inferred" in record["value"]["period_semantics"]
    assert record["kind"] == "owned_period_comparison"
    assert comparison["kind"] == "self_periods"
    assert comparison["left_account_id"] == comparison["right_account_id"] == context.account_id
    assert "professional" not in record["tags"]
    assert all("right_minus_left" in item for item in comparison["differences"])

    future = _payload(owned_period_comparison(
        context,
        earlier_start="2025-01-02",
        earlier_end="2025-03-31",
        later_start="2025-03-31",
        later_end="2026-01-02",
    ))
    assert future["status"] == "insufficient_evidence"
    assert future["records"][0]["value"]["reason_code"] == (
        "owned_period_comparison_exceeds_account_as_of"
    )


def test_owned_period_comparison_clips_calendar_bounds_to_real_observations(owned_context):
    context, *_ = owned_context
    result = _payload(owned_period_comparison(
        context,
        earlier_start="2025-01-01",
        earlier_end="2025-06-30",
        later_start="2025-07-01",
        later_end="2025-12-31",
    ))
    assert result["status"] == "complete"
    value = result["records"][0]["value"]
    assert value["requested_periods"] == {
        "earlier": {"start": "2025-01-01", "end": "2025-06-30"},
        "later": {"start": "2025-07-01", "end": "2025-12-31"},
    }
    assert value["effective_periods"]["earlier"] | {
        "requested_start": "2025-01-01",
        "requested_end": "2025-06-30",
        "effective_start": "2025-01-02",
        "effective_end": "2025-06-30",
        "start_clipped": True,
        "end_clipped": False,
    } == value["effective_periods"]["earlier"]
    assert value["effective_periods"]["later"] | {
        "requested_start": "2025-07-01",
        "requested_end": "2025-12-31",
        "effective_start": "2025-07-01",
        "effective_end": "2025-12-31",
        "start_clipped": False,
        "end_clipped": False,
    } == value["effective_periods"]["later"]
    comparison = value["comparison"]
    assert comparison["left_period_start"].startswith("2025-01-02")
    assert comparison["left_period_end"].startswith("2025-06-30")
    assert comparison["right_period_start"].startswith("2025-07-01")
    assert comparison["right_period_end"].startswith("2025-12-31")
    metrics = {item["metric_id"]: item for item in value["display_metrics"]}
    assert metrics["period_return"] == {
        "metric_id": "period_return",
        "left": "5.39%",
        "right": "8.68%",
        "right_minus_left": "+3.29 pp（个百分点）",
        "source_unit": "percentage_points",
    }
    assert metrics["max_drawdown_magnitude"] | {
        "left": "2.34%", "right": "0.28%", "right_minus_left": "-2.05 pp（个百分点）",
    } == metrics["max_drawdown_magnitude"]
    assert metrics["mean_daily_turnover"] | {
        "left": "0.41%", "right": "0.32%", "right_minus_left": "-0.09 pp（个百分点）",
    } == metrics["mean_daily_turnover"]
    assert metrics["portfolio_hhi"] | {
        "left": "1.0000", "right": "0.4596", "right_minus_left": "-0.5404",
    } == metrics["portfolio_hhi"]
    assert metrics["recorded_fee_total"] | {
        "left": "50.00 CNY", "right": "40.00 CNY", "right_minus_left": "-10.00 CNY",
    } == metrics["recorded_fee_total"]
    assert "539.29%" not in json.dumps(value["display_metrics"])
    assert comparison["differences"][0]["left_value"] == pytest.approx(5.392939293929477)
    assert comparison["differences"][0]["right_minus_left"] == pytest.approx(3.2866976991626116)
    assert "not multiplied by 100 again" in value["display_metrics_semantics"]


def test_owned_period_unavailable_exposes_only_structured_observation_bounds(owned_context):
    context, *_ = owned_context
    result = _payload(owned_period_comparison(
        context,
        earlier_start="2025-01-03",
        earlier_end="2025-01-04",
        later_start="2025-01-05",
        later_end="2025-01-10",
    ))
    assert result["status"] == "insufficient_evidence"
    value = result["records"][0]["value"]
    assert value["reason_code"] == "owned_period_insufficient_complete_observations"
    assert value["requested_periods"]["earlier"] == {
        "start": "2025-01-03", "end": "2025-01-04",
    }
    assert value["unavailable_period_boundary"] == {
        "period": "earlier",
        "requested_start": "2025-01-03",
        "requested_end": "2025-01-04",
        "source_observation_start": "2025-01-02",
        "source_observation_end": "2025-12-31",
        "available_observation_start": "2025-01-02",
        "available_observation_end": "2025-12-31",
        "effective_start": "2025-01-03",
        "effective_end": "2025-01-03",
        "observation_count": 1,
    }


def test_owned_same_stock_accepts_registered_display_episode_ids_only(owned_context):
    context, _, _, instruments, lifecycle = owned_context
    growth_id = instruments["SYN_GROWTH"].instrument_id
    growth = sorted(
        (item for item in lifecycle.episodes if item.instrument_id == growth_id),
        key=lambda item: item.opened_at,
    )
    assert len(growth) >= 2
    earlier_display = context.episode_display_ids[growth[0].episode_id]
    later_display = context.episode_display_ids[growth[1].episode_id]

    result = _payload(owned_same_stock_comparison(
        context,
        earlier_episode_id=earlier_display,
        later_episode_id=later_display,
    ))
    # Position Episodes for one account cannot overlap.  The registered
    # same-stock method therefore preserves both owned episode facts but
    # correctly refuses to relabel them as a common-window comparison.
    assert result["status"] == "insufficient_evidence"
    record = result["records"][0]
    assert record["kind"] == "owned_same_stock_comparison"
    assert record["value"]["earlier_episode_id"] == growth[0].episode_id
    assert record["value"]["later_episode_id"] == growth[1].episode_id
    assert record["value"]["professional_or_peer_data_used"] is False
    assert record["value"]["comparison"]["earlier"]["episode_id"] == growth[0].episode_id
    assert record["value"]["comparison"]["later"]["episode_id"] == growth[1].episode_id
    assert "没有重叠的投资期间" in record["value"]["comparison"]["reasons"]
    assert "position_path" not in json.dumps(record["value"])

    arbitrary = _payload(owned_same_stock_comparison(
        context,
        earlier_episode_id="invented-episode",
        later_episode_id=later_display,
    ))
    assert arbitrary["status"] == "insufficient_evidence"
    assert arbitrary["records"][0]["value"]["reason_code"] == "owned_episode_selection_invalid"
