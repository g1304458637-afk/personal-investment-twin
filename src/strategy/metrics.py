"""Standard performance-metric suite for strategy simulations.

Every metric is a deterministic function of the daily equity curve and the
closed round trips.  All annualization uses the same 252 trading-day factor
as the pre-existing annualized return / Sharpe in report.py.  Metrics that
cannot be defined from the available data return None (honest missing value)
rather than 0 — an undefined ratio must never read as a good or bad result.

Definitions (kept alongside the code because the UI transports them verbatim):

  annual_volatility   sample std of daily simple returns × √252
  sortino_ratio       mean daily return ÷ downside deviation × √252, where
                      downside deviation = √( mean( min(r, 0)² ) ) with a
                      per-period target of 0
  calmar_ratio        annualized return ÷ |max drawdown|
  profit_factor       gross wins ÷ |gross losses| over closed round trips;
                      undefined (None) when there is no losing round trip
  avg_win/avg_loss    mean positive / mean negative round-trip PnL
  largest_win/loss    best / worst round-trip PnL
  excess_annualized_return  strategy annualized return − equal-weight
                      buy-and-hold benchmark annualized return; a descriptive
                      difference, not a risk-adjusted alpha
"""
from __future__ import annotations

import math

TRADING_DAYS_PER_YEAR = 252.0


def daily_returns(equity_curve: list[float]) -> list[float]:
    """Simple daily returns.

    A pair contributes a return only when both points are finite and the
    base is positive: a -100% day is a real return and stays, but no return
    is defined from a zero/negative/NaN base, and a NaN current point would
    poison every downstream mean and std.
    """
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        previous, current = equity_curve[i - 1], equity_curve[i]
        if (math.isfinite(previous) and previous > 0
                and math.isfinite(current)):
            returns.append((current - previous) / previous)
    return returns


def annual_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return (variance ** 0.5) * (TRADING_DAYS_PER_YEAR ** 0.5)


def sharpe_ratio(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = variance ** 0.5
    if std == 0:
        return None
    return (mean / std) * (TRADING_DAYS_PER_YEAR ** 0.5)


def sortino_ratio(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
    if downside == 0:
        return None
    return (mean / downside) * (TRADING_DAYS_PER_YEAR ** 0.5)


def calmar_ratio(annualized_return: float | None, max_drawdown: float) -> float | None:
    if annualized_return is None or not math.isfinite(annualized_return):
        return None
    if max_drawdown >= 0:
        return None
    return annualized_return / abs(max_drawdown)


def trade_stats(round_trips: list[dict[str, object]]) -> dict[str, object]:
    """Win/loss aggregates over closed round trips (pnl key required)."""
    pnls = [float(trip["pnl"]) for trip in round_trips if trip.get("pnl") is not None]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    return {
        "profit_factor": (gross_win / abs(gross_loss)) if gross_loss < 0 else None,
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "largest_win": max(pnls) if pnls else None,
        "largest_loss": min(pnls) if pnls else None,
    }


def benchmark_stats(benchmark_curve: list[dict], initial_cash: float,
                    strategy_annualized: float | None) -> dict[str, object]:
    """Benchmark annualized return and the descriptive excess over it."""
    equities = [float(point["equity"]) for point in benchmark_curve]
    final_equity = equities[-1] if equities else 0.0
    trading_days = max(len(equities), 1)
    if initial_cash <= 0 or final_equity <= 0:
        benchmark_annualized = None
    else:
        benchmark_annualized = (final_equity / initial_cash) ** (TRADING_DAYS_PER_YEAR / trading_days) - 1.0
    excess = (strategy_annualized - benchmark_annualized
              if strategy_annualized is not None and benchmark_annualized is not None else None)
    return {"benchmark_annualized_return": benchmark_annualized,
            "excess_annualized_return": excess}


def performance_stats(days: list[dict], initial_cash: float, max_drawdown: float,
                      annualized_return: float | None, sharpe: float | None,
                      round_trips: list[dict],
                      benchmark_curve: list[dict]) -> dict[str, object]:
    """Assemble the nested summary block transported as performance_stats."""
    equity_curve = [float(day.get("equity", initial_cash)) for day in days]
    returns = daily_returns(equity_curve)
    stats: dict[str, object] = {
        "annual_volatility": annual_volatility(returns),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino_ratio(returns),
        "calmar_ratio": calmar_ratio(annualized_return, max_drawdown),
    }
    stats.update(trade_stats(round_trips))
    stats.update(benchmark_stats(benchmark_curve, initial_cash, annualized_return))
    stats["count"] = len(returns)
    stats["definitions"] = {
        "annualization": "年化因子为 252 个交易日；波动率与比率基于日净值简单收益率。",
        "sortino": "Sortino = 日均收益 ÷ 下行波动 × √252；下行波动只计入负收益（目标收益为 0）。",
        "calmar": "Calmar = 年化收益 ÷ |最大回撤|；无回撤时无法定义。",
        "profit_factor": "盈亏比 = 总盈利 ÷ |总亏损|，基于已闭合回合；没有亏损回合时无法定义。",
        "excess": "超额年化 = 策略年化 − 等权买入持有基准年化，仅为描述性对比，不是风险调整 alpha。",
    }
    return stats
