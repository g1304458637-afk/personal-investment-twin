from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_desktop_demo_evidence import _json_value, build_export
from src.behavior.portfolio_concentration import build_portfolio_concentration_evidence
from src.behavior.replay_state import prepare_behavior_replay
from src.cohort.engine import PERCENTILE_METHOD
from src.cohort.synthetic import (
    build_synthetic_peer_metric_values,
    generate_synthetic_cohort_accounts,
    synthetic_cohort_definition,
)
from src.data.csv_importer import load_normalized_csv
from src.history.metric_series import build_portfolio_hhi_history
from src.pretrade.impact import ProposedTrade, simulate_trade_impact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUBJECT_ID = "demo-user:synthetic-behavior"
CALCULATION_VERSION = "pretrade-impact-test-v1"
INITIAL_CASH = 100_000.0


@pytest.fixture(scope="module")
def executions() -> pd.DataFrame:
    return load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
    )


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    return pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )


@pytest.fixture(scope="module")
def hhi_history(executions, prices):
    return build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=INITIAL_CASH,
        subject_id=SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_VERSION,
    )


@pytest.fixture(scope="module")
def peer_context(prices):
    definition = synthetic_cohort_definition()
    accounts = generate_synthetic_cohort_accounts(prices, definition=definition)
    values = build_synthetic_peer_metric_values(
        accounts,
        calculation_code_version=CALCULATION_VERSION,
    )
    return definition, accounts, values


def _trade(**changes) -> ProposedTrade:
    values = {
        "subject_id": SUBJECT_ID,
        "proposed_time": pd.Timestamp("2025-01-08 23:59:00"),
        "symbol": "SYN_PAPER_WIN",
        "side": "BUY",
        "quantity": 200.0,
        "execution_price": 13.0,
        "fees": 5.0,
    }
    values.update(changes)
    return ProposedTrade(**values)


def _simulate(trade, executions, prices, hhi_history, peer_context):
    definition, accounts, peer_values = peer_context
    return simulate_trade_impact(
        trade,
        executions,
        prices,
        init_cash=INITIAL_CASH,
        hhi_history=hhi_history,
        cohort_definition=definition,
        peer_members=(account.member for account in accounts),
        peer_metric_values=peer_values,
        calculation_code_version=CALCULATION_VERSION,
    )


def test_no_peer_context_skips_peer_benchmark_builders(
    monkeypatch, executions, prices, hhi_history
) -> None:
    import src.pretrade.impact as impact

    monkeypatch.setattr(
        impact,
        "_hhi_peer_result",
        lambda **_: pytest.fail("peer benchmark must not run when disabled"),
    )
    result = impact.simulate_trade_impact(
        _trade(),
        executions,
        prices,
        init_cash=INITIAL_CASH,
        hhi_history=hhi_history,
        cohort_definition=synthetic_cohort_definition(),
        peer_members=(),
        peer_metric_values=(),
        calculation_code_version=CALCULATION_VERSION,
        include_peer_context=False,
    )
    assert result.simulation_status == "complete"
    assert result.peer_context is None
    assert result.delta is not None and result.self_context is not None


def test_simulation_is_deterministic_and_does_not_mutate_executions(
    executions, prices, hhi_history, peer_context
) -> None:
    original = executions.copy(deep=True)
    first = _simulate(_trade(), executions, prices, hhi_history, peer_context)
    second = _simulate(_trade(), executions, prices, hhi_history, peer_context)

    assert first == second
    assert first.simulation_status == "complete"
    pd.testing.assert_frame_equal(executions, original)


def test_future_executions_do_not_enter_before_or_after(
    executions, prices, hhi_history, peer_context
) -> None:
    future = executions.iloc[[0]].copy()
    future.loc[:, "event_time"] = pd.Timestamp("2025-01-09 10:00:00")
    future.loc[:, "executed_quantity"] = 50_000.0
    future.loc[:, "order_id"] = "FUTURE-ORDER"
    future.loc[:, "execution_id"] = "FUTURE-EXECUTION"
    extended = pd.concat([executions, future], ignore_index=True)

    assert _simulate(_trade(), extended, prices, hhi_history, peer_context) == _simulate(
        _trade(), executions, prices, hhi_history, peer_context
    )


def test_future_prices_do_not_enter_before_or_after(
    executions, prices, hhi_history, peer_context
) -> None:
    future = prices.loc[prices["date"] == "2025-01-08"].copy()
    future.loc[:, "date"] = "2025-01-09"
    future.loc[:, "close"] = future["close"] * 100
    extended = pd.concat([prices, future], ignore_index=True)

    assert _simulate(_trade(), executions, extended, hhi_history, peer_context) == _simulate(
        _trade(), executions, prices, hhi_history, peer_context
    )


def test_buy_with_insufficient_cash_is_rejected_by_replay(
    executions, prices, hhi_history, peer_context
) -> None:
    result = _simulate(
        _trade(quantity=100_000.0), executions, prices, hhi_history, peer_context
    )

    assert result.simulation_status == "rejected"
    assert "cash is insufficient" in str(result.simulation_reason)
    assert result.before is not None
    assert result.after is None


def test_sell_above_position_is_rejected(
    executions, prices, hhi_history, peer_context
) -> None:
    result = _simulate(
        _trade(side="SELL", quantity=451.0),
        executions,
        prices,
        hhi_history,
        peer_context,
    )

    assert result.simulation_status == "rejected"
    assert "exceeds" in str(result.simulation_reason)
    assert result.before is not None


def test_short_trade_is_rejected(executions, prices, hhi_history, peer_context) -> None:
    result = _simulate(
        _trade(side="SELL", symbol="SYN_NOT_HELD", quantity=1.0),
        executions,
        prices,
        hhi_history,
        peer_context,
    )

    assert result.simulation_status == "rejected"
    assert "Short positions are unsupported" in str(result.simulation_reason)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"quantity": 0.0}, "quantity"),
        ({"quantity": -1.0}, "quantity"),
        ({"execution_price": 0.0}, "execution price"),
        ({"fees": -1.0}, "fees"),
        ({"side": "SHORT"}, "short trades"),
    ],
)
def test_invalid_proposed_trade_is_explicitly_rejected(
    changes, message, executions, prices, hhi_history, peer_context
) -> None:
    result = _simulate(
        _trade(**changes), executions, prices, hhi_history, peer_context
    )

    assert result.simulation_status == "rejected"
    assert message.lower() in str(result.simulation_reason).lower()


def test_unsupported_symbol_price_state_is_insufficient(
    executions, prices, hhi_history, peer_context
) -> None:
    result = _simulate(
        _trade(symbol="SYN_UNKNOWN"),
        executions,
        prices,
        hhi_history,
        peer_context,
    )

    assert result.simulation_status == "insufficient_evidence"
    assert "Missing market prices" in str(result.simulation_reason)
    assert result.after is None


def test_before_and_after_hhi_are_existing_builder_outputs(
    executions, prices, hhi_history, peer_context
) -> None:
    trade = _trade()
    result = _simulate(trade, executions, prices, hhi_history, peer_context)
    execution_times = pd.to_datetime(executions["event_time"])
    price_times = pd.to_datetime(prices["date"])
    prior = executions.loc[execution_times < trade.proposed_time].copy()
    price_prefix = prices.loc[price_times < trade.proposed_time].copy()
    hypothetical = pd.concat(
        [
            prior,
            pd.DataFrame(
                [
                    {
                        "event_time": trade.proposed_time,
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "executed_quantity": trade.quantity,
                        "executed_price": trade.execution_price,
                        "fee": trade.fees,
                        "order_id": "independent-test-order",
                        "execution_id": "independent-test-execution",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    expected_before = build_portfolio_concentration_evidence(
        prior, price_prefix, init_cash=INITIAL_CASH
    )
    expected_after = build_portfolio_concentration_evidence(
        hypothetical, price_prefix, init_cash=INITIAL_CASH
    )

    assert result.before is not None and result.after is not None
    assert result.before.hhi == expected_before.hhi
    assert result.after.hhi == expected_after.hhi
    for state, expected in ((result.before, expected_before), (result.after, expected_after)):
        components = {component.symbol: component for component in expected.weight_components}
        assert state.valuation_observation_date == expected.as_of_time.date().isoformat()
        for row in state.allocations:
            if row.kind == "cash":
                assert row.symbol is None and row.security_weight is None
                assert row.value == state.cash
            else:
                assert row.value == components[row.symbol].asset_value
                assert row.security_weight == components[row.symbol].weight
            assert row.account_weight == pytest.approx(row.value / state.portfolio_value)
        assert sum(row.value for row in state.allocations) == pytest.approx(state.portfolio_value)
        assert sum(row.account_weight for row in state.allocations) == pytest.approx(1)


def test_allocation_target_change_has_exact_replay_values(executions, prices, hhi_history, peer_context):
    result = _simulate(_trade(), executions, prices, hhi_history, peer_context)
    before = {row.symbol: row for row in result.before.allocations}
    after = {row.symbol: row for row in result.after.allocations}
    # 450 existing / 650 hypothetical units, both valued at the existing 13 mark.
    assert before["SYN_PAPER_WIN"].value == 5850
    assert after["SYN_PAPER_WIN"].value == 8450
    assert before[None].value == 91900
    assert after[None].value == 89295
    assert result.before.portfolio_value == 100600
    assert result.after.portfolio_value == 100595
    for symbol in before.keys() - {None, "SYN_PAPER_WIN"}:
        assert before[symbol].value == after[symbol].value


def test_fully_sold_holding_is_not_retained_as_a_fake_slice(executions, prices, hhi_history, peer_context):
    result = _simulate(_trade(side="SELL", quantity=450), executions, prices, hhi_history, peer_context)
    assert result.simulation_status == "complete"
    assert any(row.symbol == "SYN_PAPER_WIN" for row in result.before.allocations)
    assert not any(row.symbol == "SYN_PAPER_WIN" for row in result.after.allocations)


def test_before_and_after_state_values_are_read_from_vectorbt(
    executions, prices, hhi_history, peer_context
) -> None:
    trade = _trade()
    result = _simulate(trade, executions, prices, hhi_history, peer_context)
    execution_times = pd.to_datetime(executions["event_time"])
    price_times = pd.to_datetime(prices["date"])
    prior = executions.loc[execution_times < trade.proposed_time].copy()
    price_prefix = prices.loc[price_times < trade.proposed_time].copy()
    hypothetical = pd.concat(
        [
            prior,
            pd.DataFrame(
                [
                    {
                        "event_time": trade.proposed_time,
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "executed_quantity": trade.quantity,
                        "executed_price": trade.execution_price,
                        "fee": trade.fees,
                        "order_id": "state-test-order",
                        "execution_id": "state-test-execution",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    before_portfolio = prepare_behavior_replay(
        prior, price_prefix, init_cash=INITIAL_CASH
    ).portfolio
    after_portfolio = prepare_behavior_replay(
        hypothetical, price_prefix, init_cash=INITIAL_CASH
    ).portfolio

    assert result.before is not None and result.after is not None
    assert result.before.cash == float(before_portfolio.cash().iloc[-1])
    assert result.after.cash == float(after_portfolio.cash().iloc[-1])
    assert result.before.portfolio_value == float(before_portfolio.value().iloc[-1])
    assert result.after.portfolio_value == float(after_portfolio.value().iloc[-1])
    assert result.before.symbol_quantity == float(
        before_portfolio.assets().iloc[-1][trade.symbol]
    )
    assert result.after.symbol_quantity == float(
        after_portfolio.assets().iloc[-1][trade.symbol]
    )
    assert result.after.symbol_weight == pytest.approx(
        float(after_portfolio.asset_value(group_by=False).iloc[-1][trade.symbol])
        / float(after_portfolio.value().iloc[-1])
    )
    assert result.before.valuation_price == float(
        before_portfolio.close[trade.symbol].iloc[-1]
    )
    assert result.after.valuation_price == float(
        after_portfolio.close[trade.symbol].iloc[-1]
    )


def test_assumed_execution_price_is_separate_from_vectorbt_valuation_price(
    executions, prices, hhi_history, peer_context
) -> None:
    trade = _trade(execution_price=12.5)
    result = _simulate(trade, executions, prices, hhi_history, peer_context)

    assert result.after is not None
    assert trade.execution_price == pytest.approx(12.5)
    assert result.after.valuation_price == pytest.approx(13.0)
    assert result.after.valuation_price == float(
        prepare_behavior_replay(
            pd.concat(
                [
                    executions.loc[
                        pd.to_datetime(executions["event_time"]) < trade.proposed_time
                    ],
                    pd.DataFrame(
                        [
                            {
                                "event_time": trade.proposed_time,
                                "symbol": trade.symbol,
                                "side": trade.side,
                                "executed_quantity": trade.quantity,
                                "executed_price": trade.execution_price,
                                "fee": trade.fees,
                                "order_id": "price-semantics-order",
                                "execution_id": "price-semantics-execution",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            ),
            prices.loc[
                pd.to_datetime(prices["date"]) < trade.proposed_time
            ],
            init_cash=INITIAL_CASH,
        ).portfolio.close[trade.symbol].iloc[-1]
    )


def test_self_context_uses_real_no_lookahead_hhi_history(
    executions, prices, hhi_history, peer_context
) -> None:
    future_point = replace(
        hhi_history.points[-1],
        as_of=pd.Timestamp("2025-01-09"),
        value=0.999,
    )
    extended_history = replace(
        hhi_history,
        points=(*hhi_history.points, future_point),
    )
    result = _simulate(
        _trade(), executions, prices, extended_history, peer_context
    )

    assert result.self_context is not None
    assert result.self_context.historical_hhi_median == pytest.approx(
        0.3389322518110397
    )
    assert result.self_context.historical_observation_count == 5
    assert result.self_context.current_hhi == result.before.hhi
    assert result.self_context.proposed_hhi == result.after.hhi


def test_peer_context_reuses_same_cohort_and_rank_method(
    executions, prices, hhi_history, peer_context
) -> None:
    definition, accounts, _ = peer_context
    result = _simulate(_trade(), executions, prices, hhi_history, peer_context)

    assert SUBJECT_ID not in {account.member.subject_id for account in accounts}
    assert result.peer_context is not None
    assert result.peer_context.cohort_id == definition.cohort_id
    assert result.peer_context.cohort_n == 72
    assert result.peer_context.metric_n == 72
    assert result.peer_context.percentile_method == PERCENTILE_METHOD
    assert result.peer_context.current_percentile == pytest.approx(66.66666666666666)
    assert result.peer_context.proposed_percentile == pytest.approx(83.33333333333333)


def test_export_is_byte_deterministic_and_contains_complete_pretrade_demo() -> None:
    def rendered() -> bytes:
        return (
            json.dumps(_json_value(build_export()), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")

    first = rendered()
    second = rendered()
    payload = json.loads(first)

    assert first == second
    assert payload["pretrade_demo"]["simulation_status"] == "complete"
    assert payload["pretrade_demo"]["data_tier"] == "synthetic"
