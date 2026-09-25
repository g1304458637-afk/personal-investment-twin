"""Known-answer tests for the standard performance-metric suite.

Every expected value below is hand-computed from the definition in
src/strategy/metrics.py — these tests pin the definitions, not just the code.
"""
import math

from src.strategy.metrics import (
    annual_volatility,
    benchmark_stats,
    calmar_ratio,
    daily_returns,
    performance_stats,
    sharpe_ratio,
    sortino_ratio,
    trade_stats,
)


def _close(a: float | None, b: float, tol: float = 1e-12) -> None:
    assert a is not None
    assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), f"{a} != {b}"


def test_daily_returns_basic_and_nonpositive_guard():
    curve = [100.0, 110.0, 99.0]
    assert daily_returns(curve) == [0.10, -0.10]
    # A -100% day is a real return and stays in the series; but a pair whose
    # base is non-positive has no defined return and drops out.
    assert daily_returns([100.0, 0.0, 50.0]) == [-1.0]
    assert daily_returns([100.0, float("nan"), 110.0]) == []


def test_annual_volatility_two_points():
    returns = [0.10, -0.10]
    mean = 0.0
    variance = ((0.10 - mean) ** 2 + (-0.10 - mean) ** 2) / 1
    _close(annual_volatility(returns), math.sqrt(variance) * math.sqrt(252))
    # Fewer than two returns cannot define volatility.
    assert annual_volatility([0.05]) is None
    assert annual_volatility([]) is None


def test_sharpe_and_sortino_known_series():
    returns = [0.01, -0.005, 0.005, 0.005]
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    _close(sharpe_ratio(returns), (mean / std) * math.sqrt(252))
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
    _close(sortino_ratio(returns), (mean / downside) * math.sqrt(252))
    # A never-losing series has zero downside deviation: Sortino undefined.
    assert sortino_ratio([0.01, 0.02, 0.03]) is None
    # A flat series has zero total deviation: Sharpe undefined.
    assert sharpe_ratio([0.0, 0.0, 0.0]) is None
    assert sharpe_ratio([0.01]) is None


def test_calmar_ratio():
    _close(calmar_ratio(0.30, -0.15), 2.0)
    # Zero drawdown (or missing annualized return) cannot define Calmar.
    assert calmar_ratio(0.30, 0.0) is None
    assert calmar_ratio(None, -0.15) is None


def test_trade_stats_known_round_trips():
    trips = [{"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 25.0}, {"pnl": -25.0}]
    stats = trade_stats(trips)
    _close(stats["profit_factor"], 125.0 / 75.0)
    _close(stats["avg_win"], 62.5)
    _close(stats["avg_loss"], -37.5)
    _close(stats["largest_win"], 100.0)
    _close(stats["largest_loss"], -50.0)
    # No losing round trip: profit factor is undefined, not infinite.
    assert trade_stats([{"pnl": 10.0}])["profit_factor"] is None
    assert trade_stats([])["avg_win"] is None
    # Break-even trades are neither win nor loss but do count as extremes.
    stats_zero = trade_stats([{"pnl": 0.0}])
    assert stats_zero["profit_factor"] is None
    _close(stats_zero["largest_win"], 0.0)
    _close(stats_zero["largest_loss"], 0.0)


def test_benchmark_stats_excess():
    curve = [{"equity": 1_000_000.0}, {"equity": 1_100_000.0}]
    bench = benchmark_stats(curve, 1_000_000.0, strategy_annualized=0.50)
    # Each point is one trading day: +10% over 2 days annualizes with the
    # same 252-day convention as the strategy's annualized return.
    expected_bench = (1_100_000.0 / 1_000_000.0) ** (252.0 / 2) - 1.0
    _close(bench["benchmark_annualized_return"], expected_bench)
    _close(bench["excess_annualized_return"], 0.50 - expected_bench)
    # Missing pieces stay None instead of pretending 0.
    assert benchmark_stats([], 1_000_000.0, 0.5)["benchmark_annualized_return"] is None
    assert benchmark_stats(curve, 1_000_000.0, None)["excess_annualized_return"] is None


def test_performance_stats_block_assembly():
    days = [{"equity": 100.0}, {"equity": 110.0}, {"equity": 99.0}]
    benchmark = [{"equity": 100.0}, {"equity": 105.0}, {"equity": 104.0}]
    block = performance_stats(
        days, initial_cash=100.0, max_drawdown=-0.10,
        annualized_return=0.20, sharpe=1.5,
        round_trips=[{"pnl": 20.0}, {"pnl": -10.0}],
        benchmark_curve=benchmark)
    returns = daily_returns([100.0, 110.0, 99.0])
    _close(block["annual_volatility"], annual_volatility(returns))
    _close(block["sortino_ratio"], sortino_ratio(returns))
    _close(block["sharpe_ratio"], 1.5)
    _close(block["calmar_ratio"], 0.20 / 0.10)
    _close(block["profit_factor"], 2.0)
    assert block["count"] == 2
    # Definitions travel with the numbers: the UI never has to invent them.
    assert "calmar" in block["definitions"]
