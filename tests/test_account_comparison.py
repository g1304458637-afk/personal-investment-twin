import json
from dataclasses import asdict, replace

import pandas as pd
import pytest

from src.compare.account_comparison import AccountComparisonError, compare_account_periods
from src.compare.lookthrough import AccountPosition, build_lookthrough
from src.compare.periods import build_period_behavior
from src.performance.account_series import (
    AccountValuationBoundary,
    FlowNeutralReturnInterval,
    build_account_performance_from_intervals,
)


def performance(account_id, values, start="2025-01-01"):
    dates = pd.date_range(start, periods=len(values), freq="D")
    intervals = tuple(
        FlowNeutralReturnInterval(
            AccountValuationBoundary(dates[index], 0, "after_external_flow", values[index], f"{account_id}:start:{index}"),
            AccountValuationBoundary(dates[index + 1], 0, "before_external_flow", values[index + 1], f"{account_id}:end:{index}"),
        )
        for index in range(len(values) - 1)
    )
    return build_account_performance_from_intervals(
        intervals, account_id=account_id, base_currency="CNY", source_refs=(f"source:{account_id}",),
        data_tier="synthetic", as_of=dates[-1],
    )


def behavior(start="2025-01-01", end="2025-01-03"):
    dates = pd.date_range(start, end, freq="D")
    frame = pd.DataFrame({
        "event_time": [dates[0] + pd.Timedelta(hours=10), dates[1] + pd.Timedelta(hours=10)],
        "symbol": ["A", "A"], "side": ["BUY", "BUY"],
        "executed_quantity": [10.0, 1.0], "executed_price": [10.0, 9.0], "fee": [1.0, 2.0],
        "order_id": ["order-1", "order-2"], "execution_id": ["execution-1", "execution-2"],
    })
    prices = pd.DataFrame([
        {"date": date, "instrument": "A", "close": close, "price_type": "synthetic",
         "data_source": "test", "data_version": "v1", "is_synthetic": True}
        for date, close in zip(dates, (10.0, 9.0, 9.5))
    ])
    return build_period_behavior(frame, prices, init_cash=1_000.0, start_date=dates[0], end_date=dates[-1])


def lookup(as_of, aapl, msft):
    return build_lookthrough(
        [
            AccountPosition("AAPL", "security", aapl, as_of, "allocation:aapl"),
            AccountPosition("MSFT", "security", msft, as_of, "allocation:msft"),
        ],
        (), as_of=as_of,
    )


def test_professional_comparison_reports_only_unit_explicit_right_minus_left_values():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0])
    base_behavior = behavior()
    left_behavior = replace(base_behavior, mean_daily_turnover=0.01, hhi_end=0.4, recorded_fee_total=2.0)
    right_behavior = replace(base_behavior, mean_daily_turnover=0.03, hhi_end=0.6, recorded_fee_total=5.0)
    result = compare_account_periods(
        left, right, kind="professional", left_behavior=left_behavior, right_behavior=right_behavior,
        left_lookthrough=lookup(left.period_end, 0.6, 0.4),
        right_lookthrough=lookup(right.period_end, 0.2, 0.8),
    )

    values = {item.metric_id: item for item in result.differences}
    assert values["period_return"].unit == "percentage_points"
    assert values["period_return"].right_minus_left == pytest.approx(15.0)
    assert values["max_drawdown_magnitude"].right_minus_left == pytest.approx(-5.0)
    assert values["mean_daily_turnover"].right_minus_left == pytest.approx(2.0)
    assert values["portfolio_hhi"].right_minus_left == pytest.approx(0.2)
    assert values["recorded_fee_total"].unit == "CNY"
    assert values["recorded_fee_total"].right_minus_left == pytest.approx(3.0)
    assert [(item.asset_id, item.overlap_weight) for item in result.shared_underlying] == [
        ("AAPL", 0.2), ("MSFT", 0.4),
    ]
    assert json.loads(json.dumps(asdict(result)))["kind"] == "professional"


def test_professional_requires_exact_same_observation_date_schedule():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0], start="2025-01-02")
    with pytest.raises(AccountComparisonError, match="matching observation dates"):
        compare_account_periods(
            left, right, kind="professional", left_behavior=behavior(),
            right_behavior=behavior("2025-01-02", "2025-01-04"),
        )


def test_self_periods_require_one_account_and_allow_one_shared_rebasing_boundary():
    left = performance("one-account", [100.0, 110.0, 99.0])
    right = performance("one-account", [99.0, 101.0, 103.0], start="2025-01-03")
    result = compare_account_periods(
        left, right, kind="self_periods", left_behavior=behavior(),
        right_behavior=behavior("2025-01-03", "2025-01-05"),
    )
    assert result.left_period_end == result.right_period_start

    other = performance("another-account", [99.0, 101.0, 103.0], start="2025-01-03")
    with pytest.raises(AccountComparisonError, match="same account_id"):
        compare_account_periods(
            left, other, kind="self_periods", left_behavior=behavior(),
            right_behavior=behavior("2025-01-03", "2025-01-05"),
        )


def test_behavior_and_lookthrough_dates_must_match_their_performance_evidence():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0])
    with pytest.raises(AccountComparisonError, match="behavior start_date"):
        compare_account_periods(
            left, right, kind="professional", left_behavior=behavior("2025-01-02", "2025-01-04"),
            right_behavior=behavior(),
        )
    with pytest.raises(AccountComparisonError, match="lookthrough as_of"):
        compare_account_periods(
            left, right, kind="professional", left_behavior=behavior(), right_behavior=behavior(),
            left_lookthrough=lookup("2025-01-02", 0.5, 0.5),
            right_lookthrough=lookup(right.period_end, 0.5, 0.5),
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"method_version": "2.0.0"}, "method versions"),
        ({"base_currency": "USD"}, "currencies"),
        ({"data_tier": "demo"}, "data tiers"),
    ],
)
def test_comparison_rejects_mismatched_performance_contracts(replacement, message):
    left = performance("self", [100.0, 110.0, 99.0])
    right = replace(performance("professional", [100.0, 120.0, 114.0]), **replacement)
    with pytest.raises(AccountComparisonError, match=message):
        compare_account_periods(
            left, right, kind="professional", left_behavior=behavior(), right_behavior=behavior(),
        )


def test_comparison_rejects_behavior_and_lookthrough_contract_mismatches():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0])
    base_behavior = behavior()
    with pytest.raises(AccountComparisonError, match="behavior method ids"):
        compare_account_periods(
            left, right, kind="professional", left_behavior=base_behavior,
            right_behavior=replace(base_behavior, method_id="another_behavior_method"),
        )
    left_lookthrough = lookup(left.period_end, 0.5, 0.5)
    right_lookthrough = lookup(right.period_end, 0.5, 0.5)
    with pytest.raises(AccountComparisonError, match="lookthrough max_depth"):
        compare_account_periods(
            left, right, kind="professional", left_behavior=base_behavior, right_behavior=base_behavior,
            left_lookthrough=left_lookthrough,
            right_lookthrough=replace(right_lookthrough, max_depth=2),
        )


def test_comparison_id_includes_accepted_contract_references():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0])
    base_behavior = behavior()
    first = compare_account_periods(
        left, right, kind="professional", left_behavior=base_behavior, right_behavior=base_behavior,
    )
    second = compare_account_periods(
        replace(left, method_id="alternative_performance_method"),
        replace(right, method_id="alternative_performance_method"),
        kind="professional", left_behavior=base_behavior, right_behavior=base_behavior,
    )
    assert first.differences == second.differences
    assert first.comparison_id != second.comparison_id


def test_comparison_id_includes_selected_lookthrough_identity():
    left = performance("self", [100.0, 110.0, 99.0])
    right = performance("professional", [100.0, 120.0, 114.0])
    base_behavior = behavior()
    left_lookthrough = lookup(left.period_end, 0.5, 0.5)
    right_lookthrough = lookup(right.period_end, 0.5, 0.5)
    first = compare_account_periods(
        left, right, kind="professional", left_behavior=base_behavior, right_behavior=base_behavior,
        left_lookthrough=left_lookthrough, right_lookthrough=right_lookthrough,
    )
    second = compare_account_periods(
        left, right, kind="professional", left_behavior=base_behavior, right_behavior=base_behavior,
        left_lookthrough=replace(left_lookthrough, lookthrough_id="lookthrough_alternate_version"),
        right_lookthrough=right_lookthrough,
    )
    assert first.differences == second.differences
    assert first.shared_underlying == second.shared_underlying
    assert first.comparison_id != second.comparison_id
