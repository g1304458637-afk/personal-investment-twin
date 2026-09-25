"""JSON-safe serialization of simulation results (schema strategy_simulation.v1)."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from src.strategy.data import SimulationData
from src.strategy.engine import SimulationResult

SCHEMA_VERSION = "strategy_simulation.v1"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def result_to_dict(result: SimulationResult) -> dict[str, object]:
    """Full journal: every day keeps candidates, signals, events, ledger and equity."""
    return _safe({
        "schema_version": SCHEMA_VERSION,
        "strategy": result.spec.as_dict(),
        "data_fingerprint": result.data_fingerprint,
        "summary": dict(result.summary),
        "days": [
            {
                "date": day.day,
                "universe_count": day.universe_count,
                "candidates": day.candidates,
                "signals": day.signals,
                "events": day.events,
                "orders_created": day.orders_created,
                "cash": day.cash,
                "holdings": day.holdings,
                "equity": day.equity,
                "invested_fraction": day.invested_fraction,
                "drawdown_from_peak": day.drawdown_from_peak,
            }
            for day in result.days
        ],
        "orders": [
            {
                "order_id": order.order_id, "signal_date": order.signal_date,
                "instrument": order.instrument, "side": order.side,
                "intended_quantity": order.intended_quantity, "reason_code": order.reason_code,
                "reason_text": order.reason_text, "rank": order.rank, "status": order.status,
                "resolution_date": order.resolution_date,
                "resolution_reason": order.resolution_reason,
            }
            for order in result.orders
        ],
        "fills": [
            {
                "fill_id": fill.fill_id, "order_id": fill.order_id, "trigger": fill.trigger,
                "instrument": fill.instrument, "side": fill.side, "quantity": fill.quantity,
                "price": fill.price, "fee": fill.fee, "fee_detail": fill.fee_detail,
                "day": fill.day, "note": fill.note,
            }
            for fill in result.fills
        ],
    })


def desktop_payload(payload: dict, data: SimulationData) -> dict:
    """Trimmed artifact for desktop consumers (no per-day event journal).

    Carries every instrument's OHLC so the page can draw per-instrument
    charts; the full journal stays in the data-directory result file.
    """
    bars = [
        {"instrument": instrument, "date": day.isoformat(),
         "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        for instrument in sorted(data.series)
        for day, bar in zip(data.series[instrument].dates, data.series[instrument].bars)
    ]
    return {
        "schema_version": payload["schema_version"],
        "strategy": payload["strategy"],
        "data_fingerprint": payload["data_fingerprint"],
        "summary": payload["summary"],
        "bars": bars,
        "equity": [
            {"date": day["date"], "cash": day["cash"], "equity": day["equity"],
             "invested_fraction": day["invested_fraction"],
             "drawdown_from_peak": day["drawdown_from_peak"]}
            for day in payload["days"]
        ],
        "orders": payload["orders"],
        "fills": payload["fills"],
    }


def _annualized_return(final_equity: float, initial_cash: float, trading_days: int) -> float | None:
    if trading_days <= 0 or initial_cash <= 0 or final_equity <= 0:
        return None
    return (final_equity / initial_cash) ** (252.0 / trading_days) - 1.0


def _sharpe(daily_equity: list[float], initial_cash: float) -> float | None:
    if len(daily_equity) < 2 or initial_cash <= 0:
        return None
    returns = [(daily_equity[i] - daily_equity[i - 1]) / daily_equity[i - 1]
               for i in range(1, len(daily_equity)) if daily_equity[i - 1] > 0]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = variance ** 0.5
    if std == 0:
        return None
    return (mean / std) * (252 ** 0.5)


def buy_and_hold_curve(data: SimulationData, initial_cash: float) -> list[dict]:
    """Equal-weight buy-and-hold across all instruments, hold to the end."""
    instruments = sorted(data.series.keys())
    if not instruments:
        return []
    allocation = initial_cash / len(instruments)
    share_counts: dict[str, float] = {}
    all_dates = sorted({d for inst in instruments for d in data.series[inst].dates})
    date_to_idx = {inst: {d: i for i, d in enumerate(data.series[inst].dates)} for inst in instruments}
    for inst in instruments:
        first_close = data.series[inst].bars[0].close
        share_counts[inst] = allocation / first_close if first_close > 0 else 0.0
    curve = []
    for day in all_dates:
        total = 0.0
        for inst in instruments:
            idx_map = date_to_idx[inst]
            if day in idx_map:
                close = data.series[inst].bars[idx_map[day]].close
                total += share_counts.get(inst, 0.0) * close
            else:
                last = data.series[inst].raw_close_on_or_before(day)
                if last is not None:
                    total += share_counts.get(inst, 0.0) * last
        curve.append({"date": day.isoformat(), "equity": round(total, 2)})
    return curve


def enrich_summary(payload: dict, data: SimulationData) -> dict:
    """Add annualized return, Sharpe, and buy-and-hold benchmark to the artifact.

    Also assembles the standard performance-metrics block (volatility,
    Sortino, Calmar, trade aggregates, benchmark excess) from
    src.strategy.metrics into summary["performance_stats"].
    """
    from src.strategy.metrics import performance_stats

    summary = payload.get("summary", {})
    days = payload.get("days", [])
    initial_cash = float(summary.get("initial_cash", 1_000_000))
    trading_days = len(days)
    final_equity = float(summary.get("final_equity", 0))
    equity_series = [day.get("equity", initial_cash) for day in days]
    ann = _annualized_return(final_equity, initial_cash, trading_days)
    sharpe = _sharpe(equity_series, initial_cash)
    summary["annualized_return"] = ann
    summary["sharpe_ratio"] = sharpe
    benchmark_curve = buy_and_hold_curve(data, initial_cash)
    summary["benchmark_buy_hold"] = benchmark_curve
    summary["performance_stats"] = performance_stats(
        days, initial_cash, float(summary.get("max_drawdown", 0.0)),
        ann, sharpe, summary.get("round_trips", []), benchmark_curve)
    return payload
