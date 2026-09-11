import json
from dataclasses import FrozenInstanceError

import empyrical
import numpy as np
import pandas as pd
import pytest

from src.core.portfolio_replay import replay_multi_asset_executions_with_links
from src.performance.account_series import (
    ACCOUNT_FLOW_TWR_METHOD_ID,
    ACCOUNT_FIXED_CASH_METHOD_ID,
    AccountPerformanceSeriesError,
    AccountValuationBoundary,
    DailyRiskPolicy,
    ExternalCashFlow,
    FlowNeutralReturnInterval,
    RiskFreeReturnSeries,
    build_account_performance_from_intervals,
    build_account_performance_from_replay,
)


class _PortfolioValues:
    def __init__(self, values: pd.Series):
        self._values = values

    def value(self) -> pd.Series:
        return self._values


def _boundary(
    when: str,
    sequence: int,
    stage: str,
    value: float,
    source_ref: str,
) -> AccountValuationBoundary:
    return AccountValuationBoundary(
        observed_at=pd.Timestamp(when),
        event_sequence=sequence,
        stage=stage,  # type: ignore[arg-type]
        value=value,
        source_ref=source_ref,
    )


def _build_intervals(
    values: list[float],
    *,
    start: str = "2026-01-01",
) -> tuple[FlowNeutralReturnInterval, ...]:
    dates = pd.date_range(start, periods=len(values), freq="D")
    intervals = []
    for index, (left, right) in enumerate(zip(values, values[1:])):
        intervals.append(
            FlowNeutralReturnInterval(
                start_after_flow=AccountValuationBoundary(
                    dates[index], 0, "after_external_flow", left, f"valuation-{index}"
                ),
                end_before_flow=AccountValuationBoundary(
                    dates[index + 1],
                    0,
                    "before_external_flow",
                    right,
                    f"valuation-{index + 1}",
                ),
            )
        )
    return tuple(intervals)


def _interval_series(
    intervals: tuple[FlowNeutralReturnInterval, ...],
    *,
    as_of: object | None = None,
    risk_policy: DailyRiskPolicy | None = None,
):
    latest_end = max(item.end_before_flow.observed_at for item in intervals)
    return build_account_performance_from_intervals(
        intervals,
        account_id="acct-1",
        base_currency="CNY",
        source_refs=("account-ledger-v1",),
        data_tier="synthetic",
        as_of=as_of or latest_end,
        risk_policy=risk_policy,
    )


def test_fixed_cash_series_uses_actual_vectorbt_replay_values():
    dates = pd.date_range("2026-01-01", periods=3, freq="D", name="event_time")
    executions = pd.DataFrame(
        {
            "event_time": [dates[0]],
            "symbol": ["600000.SH"],
            "side": ["BUY"],
            "executed_quantity": [10.0],
            "executed_price": [10.0],
            "fee": [0.0],
            "order_id": ["order-1"],
            "execution_id": ["execution-1"],
        }
    )
    marks = pd.DataFrame({"600000.SH": [10.0, 11.0, 9.0]}, index=dates)
    replay = replay_multi_asset_executions_with_links(executions, marks, init_cash=1_000.0)

    result = build_account_performance_from_replay(
        replay,
        account_id="acct-1",
        base_currency="CNY",
        source_refs=("execution-fixture", "price-fixture"),
        data_tier="synthetic",
        start_at="2026-01-01",
        as_of="2026-01-03",
    )

    np.testing.assert_allclose(
        [point.account_value for point in result.points],
        replay.portfolio.value().to_numpy(),
    )
    np.testing.assert_allclose(
        [point.cumulative_nav for point in result.points],
        [100.0, 101.0, 99.0],
    )
    assert result.period_return == pytest.approx(-0.01)
    assert result.method_id == ACCOUNT_FIXED_CASH_METHOD_ID
    assert result.annualized_volatility is None
    assert result.sharpe_ratio is None

    study_window = build_account_performance_from_replay(
        replay,
        account_id="acct-1",
        base_currency="CNY",
        source_refs=("execution-fixture", "price-fixture"),
        data_tier="synthetic",
        start_at="2026-01-02",
        as_of="2026-01-03",
    )
    # The purchase before the selected period remains in the full replay.  The
    # study window rebases authoritative values; it does not reset cash/holdings.
    assert [point.account_value for point in study_window.points] == [1010.0, 990.0]
    assert study_window.period_return == pytest.approx(990.0 / 1010.0 - 1.0)


def test_replay_window_takes_last_real_observation_per_date_without_mutation():
    index = pd.to_datetime(
        [
            "2025-01-01 16:00",
            "2025-01-02 10:00",
            "2025-01-02 16:00",
            "2025-01-03 16:00",
            "2025-01-04 09:00",
        ]
    )
    values = pd.Series([90.0, 99.0, 100.0, 110.0, 999.0], index=index)
    original = values.copy(deep=True)

    result = build_account_performance_from_replay(
        _PortfolioValues(values),
        account_id="acct-1",
        base_currency="CNY",
        source_refs=("replay-v1",),
        data_tier="synthetic",
        start_at=pd.Timestamp("2025-01-02"),
        as_of=pd.Timestamp("2025-01-03"),
    )

    assert [point.observed_at for point in result.points] == [index[2], index[3]]
    assert [point.account_value for point in result.points] == [100.0, 110.0]
    assert result.period_return == pytest.approx(0.10)
    pd.testing.assert_series_equal(values, original)


@pytest.mark.parametrize(("flow_amount", "after_value"), [(50.0, 150.0), (-50.0, 50.0)])
def test_external_deposit_or_withdrawal_does_not_create_performance(
    flow_amount: float,
    after_value: float,
):
    first = FlowNeutralReturnInterval(
        _boundary("2026-01-01", 0, "after_external_flow", 100.0, "v-start"),
        _boundary("2026-01-02", 10, "before_external_flow", 100.0, "v-before"),
    )
    flow = ExternalCashFlow(
        flow_id="flow-1",
        account_id="acct-1",
        occurred_at=pd.Timestamp("2026-01-02"),
        event_sequence=20,
        amount=flow_amount,
        currency="CNY",
        source_ref="cash-ledger-row-1",
    )
    second = FlowNeutralReturnInterval(
        _boundary("2026-01-02", 30, "after_external_flow", after_value, "v-after"),
        _boundary("2026-01-03", 0, "before_external_flow", after_value, "v-end"),
        preceding_flows=(flow,),
    )

    result = _interval_series((first, second))

    assert [point.cumulative_nav for point in result.points] == [100.0, 100.0, 100.0]
    assert result.period_return == pytest.approx(0.0)
    assert result.max_drawdown_magnitude == pytest.approx(0.0)
    assert result.method_id == ACCOUNT_FLOW_TWR_METHOD_ID
    assert "cash-ledger-row-1" in result.source_refs


def test_exact_flow_boundaries_chain_segment_returns_and_drawdown_dates():
    first = FlowNeutralReturnInterval(
        _boundary("2026-01-01", 0, "after_external_flow", 100.0, "v1"),
        _boundary("2026-01-02", 10, "before_external_flow", 110.0, "v2-before"),
    )
    deposit = ExternalCashFlow(
        "flow-1", "acct-1", pd.Timestamp("2026-01-02"), 20, 90.0, "CNY", "flow-src"
    )
    second = FlowNeutralReturnInterval(
        _boundary("2026-01-02", 30, "after_external_flow", 200.0, "v2-after"),
        _boundary("2026-01-03", 0, "before_external_flow", 160.0, "v3"),
        (deposit,),
    )
    third = FlowNeutralReturnInterval(
        _boundary("2026-01-03", 0, "after_external_flow", 160.0, "v3"),
        _boundary("2026-01-04", 0, "before_external_flow", 176.0, "v4"),
    )
    fourth = FlowNeutralReturnInterval(
        _boundary("2026-01-04", 0, "after_external_flow", 176.0, "v4"),
        _boundary("2026-01-05", 0, "before_external_flow", 200.0, "v5"),
    )

    result = _interval_series((first, second, third, fourth))

    np.testing.assert_allclose(
        [point.cumulative_nav for point in result.points],
        [100.0, 110.0, 88.0, 96.8, 110.0],
    )
    assert result.period_return == pytest.approx(0.10)
    assert result.max_drawdown_magnitude == pytest.approx(0.20)
    assert result.max_drawdown_peak_at == pd.Timestamp("2026-01-02")
    assert result.max_drawdown_trough_at == pd.Timestamp("2026-01-03")
    assert result.max_drawdown_recovered_at == pd.Timestamp("2026-01-05")
    assert all(point.drawdown <= 0 for point in result.points)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda flow: ExternalCashFlow(
            flow.flow_id,
            "wrong-account",
            flow.occurred_at,
            flow.event_sequence,
            flow.amount,
            flow.currency,
            flow.source_ref,
        ),
        lambda flow: ExternalCashFlow(
            flow.flow_id,
            flow.account_id,
            flow.occurred_at,
            flow.event_sequence,
            49.0,
            flow.currency,
            flow.source_ref,
        ),
        lambda flow: ExternalCashFlow(
            flow.flow_id,
            flow.account_id,
            flow.occurred_at,
            5,
            flow.amount,
            flow.currency,
            flow.source_ref,
        ),
    ],
)
def test_external_flow_ownership_reconciliation_and_order_are_mandatory(mutator):
    first = FlowNeutralReturnInterval(
        _boundary("2026-01-01", 0, "after_external_flow", 100.0, "v1"),
        _boundary("2026-01-02", 10, "before_external_flow", 100.0, "v2-before"),
    )
    valid_flow = ExternalCashFlow(
        "flow-1", "acct-1", pd.Timestamp("2026-01-02"), 20, 50.0, "CNY", "flow-src"
    )
    second = FlowNeutralReturnInterval(
        _boundary("2026-01-02", 30, "after_external_flow", 150.0, "v2-after"),
        _boundary("2026-01-03", 0, "before_external_flow", 150.0, "v3"),
        (mutator(valid_flow),),
    )

    with pytest.raises(AccountPerformanceSeriesError):
        _interval_series((first, second))


def test_value_change_between_intervals_without_flow_is_rejected():
    intervals = (
        FlowNeutralReturnInterval(
            _boundary("2026-01-01", 0, "after_external_flow", 100.0, "v1"),
            _boundary("2026-01-02", 0, "before_external_flow", 100.0, "v2"),
        ),
        FlowNeutralReturnInterval(
            _boundary("2026-01-02", 0, "after_external_flow", 150.0, "v2-changed"),
            _boundary("2026-01-03", 0, "before_external_flow", 150.0, "v3"),
        ),
    )

    with pytest.raises(AccountPerformanceSeriesError, match="without an external flow"):
        _interval_series(intervals)


def test_shuffled_intervals_are_deterministic_and_future_prefix_is_unchanged():
    intervals = _build_intervals([100.0, 105.0, 99.75, 109.725])
    prefix = _interval_series(intervals[:2])
    full = _interval_series((intervals[2], intervals[0], intervals[1]))
    shuffled = _interval_series((intervals[1], intervals[2], intervals[0]))

    assert full == shuffled
    assert full.points[: len(prefix.points)] == prefix.points


def test_daily_risk_metrics_require_exact_cadence_adequate_sample_and_risk_free():
    values = [100.0]
    returns = np.asarray([0.01, -0.005, 0.002, 0.004] * 5, dtype=float)
    for value in returns:
        values.append(values[-1] * (1.0 + value))
    intervals = _build_intervals(values)
    dates = tuple(pd.date_range("2026-01-01", periods=len(values), freq="D").date)
    risk_free_values = tuple(0.0001 for _ in returns)
    risk_free = RiskFreeReturnSeries(
        currency="CNY",
        source_ref="rf-cny-daily",
        as_of=pd.Timestamp(dates[-1]),
        period_returns=risk_free_values,
    )
    policy = DailyRiskPolicy(dates, annualization_factor=252, risk_free=risk_free)

    result = _interval_series(intervals, risk_policy=policy)

    assert result.annualized_volatility == pytest.approx(
        empyrical.annual_volatility(returns, annualization=252)
    )
    assert result.sharpe_ratio == pytest.approx(
        empyrical.sharpe_ratio(
            returns,
            risk_free=np.asarray(risk_free_values),
            annualization=252,
        )
    )
    assert result.annualization_factor == 252
    assert "rf-cny-daily" in result.source_refs


def test_short_daily_sample_and_zero_excess_volatility_do_not_emit_sharpe():
    short = _build_intervals([100.0, 101.0, 102.0])
    short_dates = tuple(pd.date_range("2026-01-01", periods=3, freq="D").date)
    short_result = _interval_series(
        short,
        risk_policy=DailyRiskPolicy(short_dates, 252),
    )
    assert short_result.annualized_volatility is None
    assert short_result.sharpe_ratio is None

    flat_intervals = _build_intervals([100.0] * 21)
    flat_dates = tuple(pd.date_range("2026-01-01", periods=21, freq="D").date)
    flat_rf = RiskFreeReturnSeries(
        "CNY", "rf-flat", pd.Timestamp(flat_dates[-1]), tuple(0.0 for _ in range(20))
    )
    flat_result = _interval_series(
        flat_intervals,
        risk_policy=DailyRiskPolicy(flat_dates, 252, flat_rf),
    )
    assert flat_result.annualized_volatility == pytest.approx(0.0)
    assert flat_result.sharpe_ratio is None


def test_daily_policy_must_exactly_match_observation_dates():
    intervals = _build_intervals([100.0, 101.0, 102.0])
    wrong_dates = tuple(pd.date_range("2026-01-01", periods=3, freq="2D").date)

    with pytest.raises(AccountPerformanceSeriesError, match="exactly match"):
        _interval_series(intervals, risk_policy=DailyRiskPolicy(wrong_dates, 252))


def test_outputs_are_frozen_slotted_and_json_safe():
    result = _interval_series(_build_intervals([100.0, 101.0]))

    with pytest.raises(FrozenInstanceError):
        result.period_return = 999.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.points[0].drawdown = -1.0  # type: ignore[misc]
    assert not hasattr(result, "__dict__")
    assert not hasattr(result.points[0], "__dict__")
    assert json.loads(json.dumps(result.as_dict()))["period_return"] == pytest.approx(0.01)


@pytest.mark.parametrize(
    ("start_at", "as_of", "message"),
    [
        ("2026-01-01", "2026-01-03", "start_at requires an exact"),
        ("2026-01-02", "2026-01-04", "as_of requires an exact"),
    ],
)
def test_replay_window_never_slides_missing_boundary_dates(start_at, as_of, message):
    values = pd.Series(
        [100.0, 101.0],
        index=pd.to_datetime(["2026-01-02 16:00", "2026-01-03 16:00"]),
    )

    with pytest.raises(AccountPerformanceSeriesError, match=message):
        build_account_performance_from_replay(
            _PortfolioValues(values),
            account_id="acct-1",
            base_currency="CNY",
            source_refs=("replay-v1",),
            data_tier="synthetic",
            start_at=start_at,
            as_of=as_of,
        )


@pytest.mark.parametrize(
    ("start_at", "as_of", "field_name"),
    [
        ("2026-01-02 09:00", "2026-01-03", "start_at"),
        ("2026-01-02", "2026-01-03 09:00", "as_of"),
    ],
)
def test_replay_window_rejects_intraday_bounds(start_at, as_of, field_name):
    values = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime(
            ["2026-01-02 16:00", "2026-01-03 09:00", "2026-01-03 16:00"]
        ),
    )

    with pytest.raises(
        AccountPerformanceSeriesError,
        match=rf"{field_name} must be a timezone-free date-only value",
    ):
        build_account_performance_from_replay(
            _PortfolioValues(values),
            account_id="acct-1",
            base_currency="CNY",
            source_refs=("replay-v1",),
            data_tier="synthetic",
            start_at=start_at,
            as_of=as_of,
        )
