"""JSON-safe serialization of simulation results (schema strategy_simulation.v1)."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from src.strategy.data import SimulationData
from src.strategy.engine import SimulationResult

SCHEMA_VERSION = "strategy_simulation.v1"

# This descriptive benchmark deliberately keeps the historical gross,
# fractional-share convention.  Its cash and corporate-action bookkeeping is
# real, but it does not pretend to obey the strategy engine's fee/lot/slippage
# execution model.  Keep this alongside the serialized curve for consumers.
BUY_HOLD_POLICY = {
    "allocation": "equal fixed initial cash sleeve per predeclared dataset instrument, including later listings",
    "entry": "first observed close on or after listing; uninvested sleeve stays cash",
    "shares": "fractional shares allowed; no lot rounding",
    "fees_and_slippage": "excluded (gross benchmark)",
    "split": "held shares multiplied by split ratio at ex-date open",
    "suspension": "held shares valued at last observed raw close",
    "delisting": "liquidate at last observed raw close on delist_date; proceeds stay cash",
}


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
    """Gross equal-sleeve buy-and-hold with chronological cash accounting.

    The dataset instrument roster defines sleeves up front.  A sleeve buys
    fractional shares only at its first observed listed close, so a later
    listing remains cash until its own first bar.  Only actions on or before
    the current day affect the position; raw prices are never back-adjusted.
    """
    instruments = sorted(data.members)
    if not instruments:
        return []
    allocation = initial_cash / len(instruments)
    cash = {instrument: allocation for instrument in instruments}
    shares = {instrument: 0.0 for instrument in instruments}
    entered: set[str] = set()
    actions_by_day: dict[date, list] = {}
    for action in data.actions:
        if action.action == "split":
            actions_by_day.setdefault(action.ex_date, []).append(action)
    curve = []
    for day in data.dates:
        # Match the engine's event ordering: split at open, then delisting
        # liquidation at the last real close.  Never synthesize a new price.
        for action in actions_by_day.get(day, ()):
            if action.instrument in shares and shares[action.instrument] > 0:
                shares[action.instrument] *= action.ratio
        listed = set(data.listed_on(day))
        for inst in instruments:
            member = data.members[inst]
            series = data.series.get(inst)
            if member.delist_date == day and shares[inst] > 0:
                if series is None:
                    raise ValueError(f"held {inst} has no price series on delisting day")
                last = series.raw_close_on_or_before(day)
                if last is None:
                    raise ValueError(f"delisted {inst} has no historical close")
                cash[inst] += shares[inst] * last
                shares[inst] = 0.0
            if inst not in entered and inst in listed and series is not None:
                bar = series.bar_on(day)
                if bar is not None:
                    shares[inst] = cash[inst] / bar.close
                    cash[inst] = 0.0
                    entered.add(inst)
        total = sum(cash.values())
        for inst in instruments:
            if shares[inst] > 0:
                series = data.series.get(inst)
                last = series.raw_close_on_or_before(day) if series is not None else None
                if last is None:
                    raise ValueError(f"held {inst} has no historical close on or before {day}")
                total += shares[inst] * last
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
    summary["benchmark_buy_hold_policy"] = dict(BUY_HOLD_POLICY)
    summary["performance_stats"] = performance_stats(
        days, initial_cash, float(summary.get("max_drawdown", 0.0)),
        ann, sharpe, summary.get("round_trips", []), benchmark_curve)
    return payload
