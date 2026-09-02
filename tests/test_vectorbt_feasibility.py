import numpy as np
import pandas as pd
import pytest

from src.core.vectorbt_validation import build_synthetic_case, replay_single_symbol_executions


INITIAL_CASH = 100_000.0
SYMBOL = "600000.SH"


@pytest.fixture
def synthetic_case():
    return build_synthetic_case()


@pytest.fixture
def portfolio(synthetic_case):
    executions, valuation_prices = synthetic_case
    return replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )


def test_final_cash_and_position_are_correct(portfolio):
    assert portfolio.cash().loc[:, SYMBOL].iloc[-1] == pytest.approx(103_855.90)
    assert portfolio.assets().loc[:, SYMBOL].iloc[-1] == pytest.approx(0.0)


def test_add_reduce_and_close_position_path_is_correct(portfolio):
    np.testing.assert_allclose(
        portfolio.assets().loc[:, SYMBOL].to_numpy(),
        [1000.0, 1500.0, 800.0, 1200.0, 0.0],
    )
    np.testing.assert_allclose(
        portfolio.cash().loc[:, SYMBOL].to_numpy(),
        [89_990.0, 84_484.5, 92_876.1, 88_271.5, 103_855.9],
    )


def test_realized_pnl_and_fees_match_manual_calculation(portfolio):
    # Gross PnL = sell proceeds 24,000 - buy cost 20,100 = 3,900.
    # Net PnL = 3,900 - total fees 44.10 = 3,855.90.
    assert portfolio.orders.fees.sum().loc[SYMBOL] == pytest.approx(44.10)
    assert portfolio.trades.closed.pnl.sum().loc[SYMBOL] == pytest.approx(3_855.90)
    assert portfolio.positions.closed.pnl.sum().loc[SYMBOL] == pytest.approx(3_855.90)
    assert portfolio.total_profit().loc[SYMBOL] == pytest.approx(3_855.90)


def test_open_position_exposes_realized_and_unrealized_pnl(synthetic_case):
    executions, valuation_prices = synthetic_case
    open_portfolio = replay_single_symbol_executions(
        executions.iloc[:4],
        valuation_prices.iloc[:4],
        init_cash=INITIAL_CASH,
    )

    # vectorbt allocates entry cost/fees proportionally (weighted-average semantics).
    assert open_portfolio.trades.closed.pnl.sum().loc[SYMBOL] == pytest.approx(1_151.0333333333)
    assert open_portfolio.trades.open.pnl.sum().loc[SYMBOL] == pytest.approx(920.4666666667)
    assert open_portfolio.positions.open.pnl.sum().loc[SYMBOL] == pytest.approx(2_071.50)
    assert open_portfolio.total_profit().loc[SYMBOL] == pytest.approx(2_071.50)


def test_orders_trades_positions_and_returns_are_exposed(portfolio):
    assert len(portfolio.orders.records_readable) == 5
    assert len(portfolio.entry_trades.records_readable) == 3
    assert len(portfolio.exit_trades.records_readable) == 2
    assert len(portfolio.positions.records_readable) == 1
    assert portfolio.orders.records_readable["Column"].unique().tolist() == [SYMBOL]

    np.testing.assert_allclose(
        portfolio.value().loc[:, SYMBOL].to_numpy(),
        [99_990.0, 100_984.5, 102_476.1, 102_071.5, 103_855.9],
    )
    assert portfolio.total_return().loc[SYMBOL] == pytest.approx(0.038559)


def test_fill_prices_are_distinct_from_marks_and_empty_bars_are_valued():
    event_time = pd.date_range("2026-02-01", periods=3, freq="D", name="event_time")
    executions = pd.DataFrame(
        {
            "event_time": [event_time[0], event_time[2]],
            "symbol": SYMBOL,
            "side": ["BUY", "SELL"],
            "executed_quantity": [100.0, 100.0],
            "executed_price": [9.5, 12.5],
            "fee": [1.0, 1.25],
            "order_id": ["ORD-A", "ORD-B"],
            "execution_id": ["EXE-A", "EXE-B"],
        }
    )
    valuation_prices = pd.Series([10.0, 11.0, 12.0], index=event_time, name=SYMBOL)

    result = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=10_000.0,
    )

    orders = result.orders.records_readable
    np.testing.assert_allclose(orders["Price"].to_numpy(), [9.5, 12.5])
    np.testing.assert_allclose(orders["Size"].to_numpy(), [100.0, 100.0])
    np.testing.assert_allclose(orders["Fees"].to_numpy(), [1.0, 1.25])
    assert orders["Timestamp"].tolist() == [event_time[0], event_time[2]]
    np.testing.assert_allclose(
        result.value().loc[:, SYMBOL].to_numpy(),
        [10_049.0, 10_149.0, 10_297.75],
    )
    assert result.total_profit().loc[SYMBOL] == pytest.approx(297.75)


def test_fractional_execution_quantity_is_not_rounded_or_dropped():
    event_time = pd.date_range("2026-03-01", periods=2, freq="D", name="event_time")
    executions = pd.DataFrame(
        {
            "event_time": event_time,
            "symbol": SYMBOL,
            "side": ["BUY", "SELL"],
            "executed_quantity": [0.5, 0.5],
            "executed_price": [10.0, 12.0],
            "fee": [0.1, 0.1],
            "order_id": ["ORD-F1", "ORD-F2"],
            "execution_id": ["EXE-F1", "EXE-F2"],
        }
    )
    valuation_prices = pd.Series([10.0, 12.0], index=event_time, name=SYMBOL)

    result = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=100.0,
    )

    np.testing.assert_allclose(result.orders.records_readable["Size"].to_numpy(), [0.5, 0.5])
    assert result.cash().loc[:, SYMBOL].iloc[-1] == pytest.approx(100.8)


@pytest.mark.parametrize(
    ("column", "invalid_value"),
    [
        ("executed_quantity", np.nan),
        ("executed_quantity", np.inf),
        ("executed_price", np.nan),
        ("executed_price", np.inf),
        ("fee", np.nan),
        ("fee", np.inf),
    ],
)
def test_invalid_execution_numbers_are_rejected(synthetic_case, column, invalid_value):
    executions, valuation_prices = synthetic_case
    executions.loc[0, column] = invalid_value

    with pytest.raises(ValueError):
        replay_single_symbol_executions(
            executions,
            valuation_prices,
            init_cash=INITIAL_CASH,
        )


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf])
def test_invalid_valuation_marks_are_rejected(synthetic_case, invalid_value):
    executions, valuation_prices = synthetic_case
    valuation_prices.iloc[0] = invalid_value

    with pytest.raises(ValueError):
        replay_single_symbol_executions(
            executions,
            valuation_prices,
            init_cash=INITIAL_CASH,
        )


def test_replay_is_deterministic(synthetic_case):
    executions, valuation_prices = synthetic_case
    first = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )
    second = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )

    pd.testing.assert_frame_equal(first.orders.records_readable, second.orders.records_readable)
    pd.testing.assert_frame_equal(first.cash(), second.cash())
    pd.testing.assert_frame_equal(first.value(), second.value())
