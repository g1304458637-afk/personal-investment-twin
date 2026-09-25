import pandas as pd
import pytest

from src.compare.periods import PeriodBehaviorUnavailable, build_period_behavior


def executions(rows):
    frame = pd.DataFrame(
        rows,
        columns=("event_time", "symbol", "side", "executed_quantity", "executed_price", "fee"),
    )
    frame["order_id"] = [f"order-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"execution-{index}" for index in range(len(frame))]
    return frame


def prices(symbols, dates):
    rows = []
    for symbol, values in symbols.items():
        for date, close in zip(dates, values):
            rows.append({
                "date": date, "instrument": symbol, "close": close,
                "price_type": "synthetic", "data_source": "test", "data_version": "v1",
                "is_synthetic": True,
            })
    return pd.DataFrame(rows)


def stateful_case():
    return (
        executions([
            ("2025-01-02 10:00", "A", "BUY", 10.0, 10.0, 1.0),
            ("2025-01-03 10:00", "A", "BUY", 5.0, 8.0, 2.0),
            ("2025-01-04 10:00", "A", "SELL", 5.0, 9.0, 3.0),
        ]),
        prices({"A": [10.0, 8.0, 9.0, 9.5]}, ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"]),
    )


def test_start_is_exclusive_end_is_inclusive_and_prefix_state_is_retained():
    frame, market = stateful_case()

    result = build_period_behavior(
        frame, market, init_cash=1_000.0, start_date="2025-01-02", end_date="2025-01-03",
    )

    assert result.start_date == pd.Timestamp("2025-01-02")
    assert result.end_date == pd.Timestamp("2025-01-03")
    assert result.observation_count == 1
    assert [item.observation_date for item in result.daily_turnover] == [pd.Timestamp("2025-01-03")]
    assert result.action_count == 1
    assert result.total_traded_value == pytest.approx(40.0)
    assert result.recorded_fee_total == pytest.approx(2.0)
    # The Jan 3 BUY is an addition to the Jan 2 position, not a new position.
    assert result.loss_averaging.eligible_add_events == 1
    assert result.loss_averaging.loss_averaging_events == 1
    assert result.loss_averaging.event_rate == pytest.approx(1.0)


def test_future_executions_and_prices_cannot_change_past_period_result():
    frame, market = stateful_case()
    original = build_period_behavior(
        frame, market, init_cash=1_000.0, start_date="2025-01-02", end_date="2025-01-03",
    )
    future_execution = executions([("2025-05-01", "A", "SELL", 10.0, 100.0, 99.0)])
    future_prices = prices({"A": [100.0]}, ["2025-05-01"])

    changed = build_period_behavior(
        pd.concat([frame, future_execution], ignore_index=True),
        pd.concat([market, future_prices], ignore_index=True),
        init_cash=1_000.0, start_date="2025-01-02", end_date="2025-01-03",
    )

    assert changed == original


@pytest.mark.parametrize("removed", ["2025-01-02", "2025-01-03"])
def test_exact_start_and_end_daily_snapshots_are_required_without_forward_fill(removed):
    frame, market = stateful_case()
    incomplete = market[market["date"] != removed]

    with pytest.raises(PeriodBehaviorUnavailable, match="exact start_date and end_date"):
        build_period_behavior(
            frame, incomplete, init_cash=1_000.0, start_date="2025-01-02", end_date="2025-01-03",
        )


def test_period_disposition_subtracts_whole_start_calendar_day_and_keeps_zero_denominators():
    frame, market = stateful_case()
    result = build_period_behavior(
        frame, market, init_cash=1_000.0, start_date="2025-01-03", end_date="2025-01-04",
    )

    # Only the Jan 4 sale belongs to the period. Its PGR denominator is zero,
    # so the existing _result contract keeps PGR as None rather than inventing 0.
    # The Jan 4 sale is PARTIAL (5 of 15 shares): the residual position still
    # counts as the day's paper opportunity (loss vs the Jan 4 close), so the
    # PLR denominator has two observations.
    assert result.disposition.eligible_sale_events == 1
    assert result.disposition.realized_gains == 0
    assert result.disposition.realized_losses == 1
    assert result.disposition.paper_gains == 0
    assert result.disposition.paper_losses == 1
    assert result.disposition.pgr is None
    assert result.disposition.plr == pytest.approx(0.5)
    assert result.disposition.disposition_effect is None
    assert result.disposition.observation_count == 2


def test_start_day_sale_is_not_split_into_a_following_period_paper_opportunity():
    frame = executions([
        ("2025-01-02", "A", "BUY", 10.0, 10.0, 0.0),
        ("2025-01-03", "A", "SELL", 10.0, 11.0, 0.0),
    ])
    market = prices({"A": [10.0, 11.0, 12.0]}, ["2025-01-02", "2025-01-03", "2025-01-04"])

    result = build_period_behavior(
        frame, market, init_cash=1_000.0, start_date="2025-01-03", end_date="2025-01-04",
    )

    assert result.action_count == 0
    assert result.disposition.eligible_sale_events == 0
    assert result.disposition.observation_count == 0
    assert result.disposition.pgr is None
    assert result.disposition.plr is None


def test_invalid_period_boundaries_fail_closed():
    frame, market = stateful_case()
    with pytest.raises(PeriodBehaviorUnavailable, match="before"):
        build_period_behavior(
            frame, market, init_cash=1_000.0, start_date="2025-01-03", end_date="2025-01-03",
        )


def test_period_boundaries_reject_intraday_inputs_instead_of_silently_normalizing():
    frame, market = stateful_case()
    with pytest.raises(PeriodBehaviorUnavailable, match="midnight"):
        build_period_behavior(
            frame, market, init_cash=1_000.0,
            start_date="2025-01-02 09:00", end_date="2025-01-03",
        )
