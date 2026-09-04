from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import vectorbt as vbt
from vectorbt.portfolio.enums import SizeType

from src.core.canonical_execution import (
    canonical_execution,
    canonical_executions_to_frame,
    execution_time,
    fee_fact,
    instrument_ref,
)
from src.core.portfolio_replay import (
    PortfolioReplayError,
    replay_canonical_executions,
    replay_multi_asset_executions,
    replay_multi_asset_executions_with_links,
)
from src.core.vectorbt_validation import (
    build_synthetic_case,
    replay_single_symbol_executions,
)
from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay


def _instrument(symbol="A", market="MARKET_A"):
    return instrument_ref(local_symbol=symbol, market=market, security_type="equity")


def _fill(
    execution_id,
    *,
    instrument=None,
    when="2025-01-02 10:00:00+00:00",
    sequence=0,
    side="BUY",
    quantity=10,
    price=10,
    fee=1,
):
    return canonical_execution(
        subject_id="SUBJECT",
        account_id="ACCOUNT",
        execution_id=execution_id,
        source_execution_id=execution_id,
        source_order_id=f"ORDER-{execution_id}",
        instrument=instrument or _instrument(),
        event_time=execution_time(when, precision="second"),
        execution_sequence=sequence,
        sequence_source="broker_sequence",
        side=side,
        executed_quantity=quantity,
        executed_price=price,
        fee=fee_fact(fee),
        source="test_broker",
        source_record_ref=f"record:{execution_id}",
    )


def _marks(executions, values=None):
    frame = canonical_executions_to_frame(executions)
    symbols = sorted(frame["symbol"].unique())
    values = values or {symbol: 12.0 for symbol in symbols}
    return pd.DataFrame(
        [[values[symbol] for symbol in symbols]],
        index=pd.DatetimeIndex([frame["event_time"].iloc[0]], name="event_time"),
        columns=symbols,
    )


def test_same_time_same_symbol_buy_fills_are_not_aggregated_or_dropped():
    fills = (
        _fill("BUY-1", sequence=1, quantity=30, price=10, fee=1),
        _fill("BUY-2", sequence=2, quantity=20, price=11, fee=2),
    )
    result = replay_canonical_executions(fills, _marks(fills), init_cash=10_000)
    orders = result.portfolio.orders.records_readable

    assert len(orders) == len(result.execution_links) == 2
    assert orders["Size"].tolist() == [30.0, 20.0]
    assert orders["Price"].tolist() == [10.0, 11.0]
    assert orders["Fees"].tolist() == [1.0, 2.0]
    assert [item.execution_id for item in result.execution_links] == ["BUY-1", "BUY-2"]
    position = result.portfolio.positions.records_readable.iloc[0]
    assert position["Avg Entry Price"] == pytest.approx(10.4)


def test_identical_same_time_sell_fills_keep_distinct_authoritative_links():
    fills = (
        _fill("BUY", when="2025-01-01 10:00:00+00:00", quantity=40, fee=1),
        _fill("SELL-1", sequence=1, side="SELL", quantity=20, price=12, fee=1),
        _fill("SELL-2", sequence=2, side="SELL", quantity=20, price=12, fee=1),
    )
    frame = canonical_executions_to_frame(fills)
    symbol = fills[0].instrument.instrument_id
    marks = pd.DataFrame(
        {symbol: [10.0, 12.0]},
        index=pd.to_datetime([frame.event_time.iloc[0], frame.event_time.iloc[1]]),
    )
    result = replay_canonical_executions(fills, marks, init_cash=10_000)
    links = {item.execution_id: item for item in result.execution_links}

    assert len(result.portfolio.orders.records_readable) == 3
    assert len(result.portfolio.exit_trades.closed.records_readable) == 2
    assert links["SELL-1"].vectorbt_order_record_id != links["SELL-2"].vectorbt_order_record_id
    assert links["SELL-1"].vectorbt_exit_trade_record_id == 0
    assert links["SELL-2"].vectorbt_exit_trade_record_id == 1
    assert links["SELL-1"].vectorbt_position_record_id == 0
    assert links["SELL-2"].vectorbt_position_record_id == 0


def test_physical_input_order_cannot_override_explicit_sequence():
    canonical = (
        _fill("FIRST", sequence=1, quantity=10, price=10),
        _fill("SECOND", sequence=2, quantity=10, price=11),
    )
    marks = _marks(canonical)
    first = replay_canonical_executions(canonical, marks, init_cash=1_000)
    reversed_input = replay_canonical_executions(tuple(reversed(canonical)), marks, init_cash=1_000)

    pd.testing.assert_frame_equal(
        first.portfolio.orders.records_readable,
        reversed_input.portfolio.orders.records_readable,
    )
    assert first.execution_links == reversed_input.execution_links


def test_ambiguous_same_time_order_is_rejected_instead_of_guessed():
    frame = pd.DataFrame(
        {
            "event_time": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "symbol": ["A", "A"],
            "side": ["BUY", "BUY"],
            "executed_quantity": [1, 1],
            "executed_price": [10, 11],
            "fee": [0, 0],
            "order_id": ["O1", "O2"],
            "execution_id": ["E1", "E2"],
        }
    )
    marks = pd.DataFrame({"A": [10]}, index=pd.to_datetime(["2025-01-01"]))
    with pytest.raises(PortfolioReplayError, match="ambiguous_execution_order"):
        replay_multi_asset_executions(frame, marks, init_cash=100)


def test_legacy_single_symbol_entrypoint_uses_the_same_flexible_core():
    frame = pd.DataFrame(
        {
            "event_time": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "symbol": ["A", "A"],
            "side": ["BUY", "BUY"],
            "executed_quantity": [1.0, 2.0],
            "executed_price": [10.0, 11.0],
            "fee": [0.0, 0.0],
            "order_id": ["O1", "O2"],
            "execution_id": ["E1", "E2"],
            "execution_sequence": [1, 2],
        }
    )
    marks = pd.Series([12.0], index=pd.to_datetime(["2025-01-01"]), name="A")
    portfolio = replay_single_symbol_executions(frame, marks, init_cash=100)
    assert portfolio.orders.records_readable["Price"].tolist() == [10.0, 11.0]
    assert portfolio.assets().iloc[-1, 0] == pytest.approx(3.0)


def test_cross_instrument_cash_sharing_respects_account_global_sequence():
    a = _instrument("A", "X")
    b = _instrument("B", "X")
    sell_then_buy = (
        _fill(
            "OPEN-B",
            instrument=b,
            when="2025-01-01 10:00:00+00:00",
            quantity=10,
            price=10,
            fee=0,
        ),
        _fill("SELL-B", instrument=b, sequence=1, side="SELL", fee=0),
        _fill("BUY-A", instrument=a, sequence=2, fee=0),
    )
    frame = canonical_executions_to_frame(sell_then_buy)
    marks = pd.DataFrame(
        {
            a.instrument_id: [10.0, 10.0],
            b.instrument_id: [10.0, 10.0],
        },
        index=pd.to_datetime([frame.event_time.iloc[0], frame.event_time.iloc[1]]),
    )
    successful = replay_canonical_executions(sell_then_buy, marks, init_cash=100)
    assert successful.portfolio.assets().iloc[-1][a.instrument_id] == pytest.approx(10)
    assert successful.portfolio.assets().iloc[-1][b.instrument_id] == pytest.approx(0)

    buy_then_sell = (
        sell_then_buy[0],
        _fill("SELL-B", instrument=b, sequence=2, side="SELL", fee=0),
        _fill("BUY-A", instrument=a, sequence=1, fee=0),
    )
    with pytest.raises(PortfolioReplayError, match="[Nn]ot enough cash"):
        replay_canonical_executions(buy_then_sell, marks, init_cash=100)


def test_same_local_symbol_different_markets_use_distinct_price_columns():
    market_a = _instrument("ABC", "MARKET_A")
    market_b = _instrument("ABC", "MARKET_B")
    fills = (
        _fill("A", instrument=market_a, sequence=1, quantity=1, price=10, fee=0),
        _fill("B", instrument=market_b, sequence=2, quantity=1, price=20, fee=0),
    )
    marks = _marks(
        fills,
        values={market_a.instrument_id: 11.0, market_b.instrument_id: 25.0},
    )
    result = replay_canonical_executions(fills, marks, init_cash=100)
    assert set(result.portfolio.assets().columns) == {
        market_a.instrument_id,
        market_b.instrument_id,
    }
    assert result.portfolio.value().iloc[-1] == pytest.approx(106.0)


def test_market_data_lookup_uses_canonical_instrument_identity_without_fill():
    market_a = _instrument("ABC", "MARKET_A")
    market_b = _instrument("ABC", "MARKET_B")
    fills = (
        _fill("A", instrument=market_a, sequence=1, quantity=1, price=10, fee=0),
        _fill("B", instrument=market_b, sequence=2, quantity=1, price=20, fee=0),
    )
    frame = canonical_executions_to_frame(fills)
    prices = pd.DataFrame(
        [
            {
                "date": "2025-01-02",
                "instrument": instrument.instrument_id,
                "close": close,
                "price_type": "synthetic",
                "data_source": "canonical-v2-test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for instrument, close in ((market_a, 11.0), (market_b, 25.0))
        ]
    )
    context = prepare_behavior_replay(frame, prices, init_cash=100)
    assert context.daily_prices.loc[pd.Timestamp("2025-01-02"), market_a.instrument_id] == 11
    assert context.daily_prices.loc[pd.Timestamp("2025-01-02"), market_b.instrument_id] == 25

    with pytest.raises(BehaviorReplayError, match="Missing market prices"):
        prepare_behavior_replay(
            frame,
            prices[prices.instrument == market_a.instrument_id],
            init_cash=100,
        )


def test_date_only_execution_preserves_date_precision_and_requires_that_exact_daily_mark():
    instrument = _instrument()
    fill = canonical_execution(
        subject_id="SUBJECT",
        account_id="ACCOUNT",
        execution_id="DATE-ONLY",
        source_execution_id="DATE-ONLY",
        source_order_id="ORDER-DATE",
        instrument=instrument,
        event_time=execution_time("2025-01-02", precision="date"),
        execution_sequence=None,
        side="BUY",
        executed_quantity=1,
        executed_price=10,
        fee=fee_fact(0),
        source="test_broker",
        source_record_ref="record:date",
    )
    frame = canonical_executions_to_frame((fill,))
    assert frame.loc[0, "time_precision"] == "date"
    assert frame.loc[0, "canonical_event_time_utc"] is None
    assert frame.loc[0, "event_time"] == pd.Timestamp("2025-01-02")
    prior_only = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "instrument": instrument.instrument_id,
                "close": 9.0,
                "price_type": "synthetic",
                "data_source": "canonical-v2-test",
                "data_version": "v1",
                "is_synthetic": True,
            }
        ]
    )
    with pytest.raises(BehaviorReplayError, match="Missing market prices"):
        prepare_behavior_replay(frame, prior_only, init_cash=100)


def test_flexible_replay_matches_frozen_from_orders_semantics_for_legacy_fixture():
    executions, valuation_series = build_synthetic_case()
    marks = valuation_series.to_frame()
    flexible = replay_multi_asset_executions_with_links(
        executions, marks, init_cash=100_000
    ).portfolio

    indexed = executions.assign(
        signed_size=executions.executed_quantity
        * executions.side.map({"BUY": 1.0, "SELL": -1.0})
    ).set_index(["event_time", "symbol"])
    size = indexed.signed_size.unstack("symbol").reindex(marks.index)
    price = indexed.executed_price.unstack("symbol").reindex(marks.index).fillna(marks)
    fees = indexed.fee.unstack("symbol").reindex(marks.index).fillna(0.0)
    size.columns.name = marks.columns.name
    price.columns.name = marks.columns.name
    fees.columns.name = marks.columns.name
    reference = vbt.Portfolio.from_orders(
        close=marks,
        size=size,
        size_type=SizeType.Amount,
        direction="longonly",
        price=price,
        fees=0.0,
        fixed_fees=fees,
        slippage=0.0,
        reject_prob=0.0,
        allow_partial=False,
        raise_reject=True,
        init_cash=100_000,
        cash_sharing=True,
        group_by=True,
    )

    for accessor in (
        lambda item: item.orders.records_readable,
        lambda item: item.cash(),
        lambda item: item.assets(),
        lambda item: item.asset_flow(),
        lambda item: item.value(),
        lambda item: item.positions.records_readable,
        lambda item: item.exit_trades.records_readable,
    ):
        actual = accessor(flexible)
        expected = accessor(reference)
        if isinstance(actual, pd.Series):
            pd.testing.assert_series_equal(actual, expected)
        else:
            pd.testing.assert_frame_equal(actual, expected)
    assert float(flexible.total_profit()) == pytest.approx(float(reference.total_profit()))
    assert float(flexible.total_return()) == pytest.approx(float(reference.total_return()))
