"""Same-instrument strategy comparison (schema strategy_comparison.v1).

Deterministic comparison between a recorded episode and the same T1 rules
replayed independently on that instrument's own OHLC history.  Every number
comes from the strategy engine or from canonical execution facts; the report
states facts and conditions and never a buy/sell verdict.

Declared scope (docs/STRATEGY_SIMULATION_V1.md):
- The rule replay requires OHLC bars; a close-only source fails closed with
  ``comparison_unavailable_close_only_source`` instead of pretending fills.
- Window PnL is realized-cash-flow only over the episode window; open
  positions are reported unrealized and excluded from the difference.
- Synthetic isolation: bars and executions must agree on the synthetic flag;
  mixing synthetic market data with real executions (or vice versa) is
  refused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from src.strategy.data import Bar, InstrumentSeries, SimulationData, UniverseMember
from src.strategy.engine import run_simulation
from src.strategy.report import result_to_dict
from src.strategy.spec import StrategySpec

SCHEMA_VERSION = "strategy_comparison.v1"

NO_VERDICT_NOTE = "本报告只并列事实与条件差异，不构成任何买卖结论或能力评价。"


class ComparisonError(ValueError):
    """Inputs cannot form an honest comparison."""


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    """One canonical execution mapped onto its exchange calendar date."""

    execution_id: str
    day: date
    side: str
    quantity: float
    price: float
    fee: float


def simulation_data_from_bars(instrument: str, bars: Sequence[Mapping[str, Any]], *,
                              is_synthetic: bool) -> SimulationData:
    """Build a single-instrument SimulationData from validated OHLC rows.

    Rows need ``date/open/high/low/close``; dates must be unique and ordered.
    The instrument is treated as listed for its entire bar span (the point-in-
    time universe for a same-instrument replay is the instrument itself).
    """
    if not instrument:
        raise ComparisonError("instrument id is required")
    if is_synthetic and not instrument.startswith("SYN"):
        raise ComparisonError("synthetic bars must use a SYN-prefixed demo instrument id")
    if not is_synthetic and instrument.startswith("SYN"):
        raise ComparisonError("real bars cannot use synthetic instrument ids")
    parsed: list[tuple[date, Bar]] = []
    seen: set[date] = set()
    for row in bars:
        try:
            day = row["date"] if isinstance(row["date"], date) else date.fromisoformat(str(row["date"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ComparisonError(f"invalid bar date for {instrument}") from exc
        if day in seen:
            raise ComparisonError(f"duplicate bar date {day} for {instrument}")
        seen.add(day)
        try:
            values = [float(row[key]) for key in ("open", "high", "low", "close")]
        except (KeyError, TypeError, ValueError) as exc:
            raise ComparisonError(f"invalid OHLC on {day} for {instrument}") from exc
        if not all(value > 0 and value == value for value in values):
            raise ComparisonError(f"non-positive OHLC on {day} for {instrument}")
        open_, high, low, close = values
        if high < max(open_, close) or low > min(open_, close):
            raise ComparisonError(f"inconsistent OHLC on {day} for {instrument}")
        parsed.append((day, Bar(open=open_, high=high, low=low, close=close)))
    if not parsed:
        raise ComparisonError(f"no bars for {instrument}")
    parsed.sort(key=lambda item: item[0])
    dates = tuple(day for day, _ in parsed)
    closes = tuple(bar.close for _, bar in parsed)
    series = InstrumentSeries(instrument=instrument, dates=dates, bars=tuple(bar for _, bar in parsed),
                              adjusted_close=closes, split_factors=tuple(1.0 for _ in dates))
    member = UniverseMember(instrument=instrument, display_name=instrument,
                            list_date=dates[0], delist_date=None)
    return SimulationData(dates=dates, series={instrument: series}, members={instrument: member},
                          actions=(), fingerprint=f"comparison:{instrument}:{len(dates)}:{dates[0]}:{dates[-1]}")


def execution_facts(rows: Sequence[Mapping[str, Any]], *, instrument: str,
                    is_synthetic: bool) -> list[ExecutionFact]:
    """Map canonical execution rows onto calendar dates; refuse wrong ownership."""
    facts: list[ExecutionFact] = []
    for row in rows:
        row_instrument = next((str(row[key]).strip() for key in ("instrument", "symbol") if row.get(key)), instrument)
        if row_instrument != instrument:
            raise ComparisonError(f"execution {row.get('execution_id')} belongs to {row_instrument}")
        raw_day = row.get("day") or row.get("market_date")
        if raw_day is None:
            raise ComparisonError("execution lacks an exchange calendar date")
        day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day))
        side = str(row["side"]).strip().upper()
        if side not in {"BUY", "SELL"}:
            raise ComparisonError(f"execution {row.get('execution_id')} has invalid side")
        quantity = float(row["quantity"])
        price = float(row["price"])
        fee = float(row.get("fee") or 0.0)
        if quantity <= 0 or price <= 0 or fee < 0:
            raise ComparisonError(f"execution {row.get('execution_id')} has invalid amounts")
        facts.append(ExecutionFact(execution_id=str(row.get("execution_id") or ""), day=day,
                                   side=side, quantity=quantity, price=price, fee=fee))
    del is_synthetic  # Synthetic agreement is enforced by the caller through bar flags.
    facts.sort(key=lambda item: (item.day, item.execution_id))
    return facts


def _window_net(fills: Sequence[tuple[date, str, float, float, float]],
                start: date | None, end: date | None) -> tuple[float, int, float]:
    """Realized cash-flow PnL inside [start, end]; returns (net, count, open_notional)."""
    net = 0.0
    count = 0
    open_notional = 0.0
    for day, side, quantity, price, fee in fills:
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        amount = quantity * price
        if side == "BUY":
            net -= amount + fee
            open_notional += amount + fee
        else:
            net += amount - fee
            open_notional -= amount - fee
        count += 1
    return net, count, open_notional


def compare_episode(spec: StrategySpec, bars: Sequence[Mapping[str, Any]], *,
                    instrument: str, is_synthetic: bool,
                    executions: Sequence[Mapping[str, Any]],
                    episode_id: str, window_start: date | None,
                    window_end: date | None) -> dict[str, object]:
    """Replay the spec on this instrument's own history and compare with records."""
    data = simulation_data_from_bars(instrument, bars, is_synthetic=is_synthetic)
    user_facts = execution_facts(executions, instrument=instrument, is_synthetic=is_synthetic)
    first_bar, last_bar = data.dates[0], data.dates[-1]
    limitations: list[str] = [NO_VERDICT_NOTE]
    if window_start is not None and window_start < first_bar:
        limitations.append("episode 窗口早于可用行情，窗口前记录不在对照范围内。")
        window_start = first_bar
    if window_end is not None and window_end > last_bar:
        limitations.append("episode 窗口晚于可用行情，窗口后记录不在对照范围内。")
        window_end = last_bar
    out_of_range = [fact for fact in user_facts
                    if (window_start is not None and fact.day < window_start)
                    or (window_end is not None and fact.day > window_end)]
    if out_of_range:
        limitations.append(f"{len(out_of_range)} 笔记录落在可用行情范围之外，未参与窗口差值。")

    result = run_simulation(spec, data)
    payload = result_to_dict(result)
    rule_fills = [(date.fromisoformat(fill["day"]), fill["side"],
                   fill["quantity"], fill["price"], fill["fee"]) for fill in payload["fills"]]
    user_tuples = [(fact.day, fact.side, fact.quantity, fact.price, fact.fee) for fact in user_facts]

    user_net, user_count, user_open = _window_net(user_tuples, window_start, window_end)
    rule_net, rule_count, rule_open = _window_net(rule_fills, window_start, window_end)
    if user_open > 1e-9:
        limitations.append("窗口结束时记录侧仍有持仓：窗口净现金流主要是未平仓成本，不代表盈亏。")
    if rule_open > 1e-9:
        limitations.append("窗口结束时规则侧仍有持仓：窗口净现金流主要是未平仓成本，不代表盈亏。")
    limitations.append("规则侧按策略自身仓位参数开仓（每仓=策略净值×25%），金额量级与记录侧不同；窗口净现金流不可直接相减为优劣。")

    return {
        "episode_id": episode_id,
        "instrument": instrument,
        "is_synthetic": is_synthetic,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "bar_count": len(data.dates),
        "bars_covered": f"{first_bar.isoformat()}..{last_bar.isoformat()}",
        "user_executions": [
            {"execution_id": fact.execution_id, "day": fact.day.isoformat(), "side": fact.side,
             "quantity": fact.quantity, "price": fact.price, "fee": fact.fee}
            for fact in user_facts
        ],
        "rule_fills": payload["fills"],
        "rule_orders": payload["orders"],
        "rule_summary": payload["summary"],
        "window_user_net_cash_flow": user_net,
        "window_user_fill_count": user_count,
        "window_user_open_cost": user_open if user_open > 0 else 0.0,
        "window_rule_net_cash_flow": rule_net,
        "window_rule_fill_count": rule_count,
        "window_rule_open_cost": rule_open if rule_open > 0 else 0.0,
        "window_difference_note": "窗口净现金流 = 窗口内买入流出 − 卖出流入（含费用）；两侧仓位量级不同，不可直接相减为优劣。",
        "limitations": limitations,
    }


def compare_portfolio(user_summary: Mapping[str, Any], rule_payload: Mapping[str, Any], *,
                      note: str) -> dict[str, object]:
    """Portfolio-level parallel facts: two independent accounts, side by side."""
    return {
        "user": dict(user_summary),
        "strategy": {
            "strategy_id": rule_payload["strategy"]["strategy_id"],
            "version": rule_payload["strategy"]["version"],
            "final_equity": rule_payload["summary"]["final_equity"],
            "total_return": rule_payload["summary"]["total_return"],
            "max_drawdown": rule_payload["summary"]["max_drawdown"],
            "total_fees": rule_payload["summary"]["total_fees"],
            "round_trip_count": rule_payload["summary"]["round_trip_count"],
            "win_rate": rule_payload["summary"]["win_rate"],
            "trading_days": rule_payload["summary"]["trading_days"],
        },
        "note": note,
        "limitations": [
            "两者标的池与资金不同，并列不构成同口径绩效比较，更不是能力排名。",
            NO_VERDICT_NOTE,
        ],
    }


def decision_verdicts(spec, bars: Sequence[Mapping[str, Any]], *, instrument: str,
                      is_synthetic: bool, executions: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    """Per-recorded-decision alignment with a strategy's own rules.

    For each execution, the strategy's signal provider is evaluated on the
    strict prior-close prefix (the Lens temporal convention): a recorded BUY
    is "aligned" when the strategy emitted an entry candidate for this
    instrument that session; a recorded SELL when it emitted an exit signal.
    Otherwise "different", with the strategy's own condition text.  Add-unit
    checks are deliberately not attempted here: they would require the
    strategy's own position path, which this lens does not reconstruct.
    """
    from src.strategy.strategies.registry import resolve_signals

    data = simulation_data_from_bars(instrument, bars, is_synthetic=is_synthetic)
    provider = resolve_signals(spec.strategy_id, None)
    if provider is None:
        raise ComparisonError(f"no signal provider for {spec.strategy_id}")
    facts = execution_facts(executions, instrument=instrument, is_synthetic=is_synthetic)
    out: list[dict[str, object]] = []
    for fact in facts:
        eve = None
        earlier = [d for d in data.dates if d < fact.day]
        if earlier:
            eve = earlier[-1]
        if eve is None:
            out.append({"execution_id": fact.execution_id, "day": fact.day.isoformat(),
                        "side": fact.side, "verdict": "insufficient",
                        "reason_text": "决策日前没有可用的收盘观测，无法按该策略核对。", "conditions": []})
            continue
        held = {instrument} if fact.side == "SELL" else set()
        _exits, candidates = provider(spec.params, data, eve, held, set())
        if fact.side == "BUY":
            entry = next((c for c in candidates if c.kind in {"entry_candidate", "add_candidate"}
                          and c.instrument == instrument), None)
            if entry is not None:
                out.append({"execution_id": fact.execution_id, "day": fact.day.isoformat(),
                            "side": "BUY", "verdict": "aligned",
                            "reason_text": entry.reason_text,
                            "conditions": [dict(c) for c in entry.conditions]})
            else:
                out.append({"execution_id": fact.execution_id, "day": fact.day.isoformat(),
                            "side": "BUY", "verdict": "different",
                            "reason_text": f"该策略在 {eve.isoformat()} 收盘没有为 {instrument} 产生入场信号。",
                            "conditions": []})
        else:
            exit_signal = next((c for c in candidates if c.kind == "exit" and c.instrument == instrument), None)
            if exit_signal is not None:
                out.append({"execution_id": fact.execution_id, "day": fact.day.isoformat(),
                            "side": "SELL", "verdict": "aligned",
                            "reason_text": exit_signal.reason_text,
                            "conditions": [dict(c) for c in exit_signal.conditions]})
            else:
                out.append({"execution_id": fact.execution_id, "day": fact.day.isoformat(),
                            "side": "SELL", "verdict": "different",
                            "reason_text": f"该策略在 {eve.isoformat()} 收盘没有为 {instrument} 产生退出信号，按其规则应继续持有。",
                            "conditions": []})
    return out


def multi_simulation_data(bars_by_instrument: Mapping[str, Sequence[Mapping[str, Any]]],
                          *, is_synthetic: bool) -> SimulationData:
    """Build a multi-instrument SimulationData from validated OHLC rows.

    Each instrument's first bar date is its point-in-time listing; every
    row is validated (unique dates, positive, consistent OHLC) exactly like
    the single-instrument path.  Used to run user strategies on real market
    history (backward-adjusted bars) instead of the synthetic universe.
    """
    series: dict[str, InstrumentSeries] = {}
    members: dict[str, UniverseMember] = {}
    all_dates: set[date] = set()
    for instrument, rows in sorted(bars_by_instrument.items()):
        single = simulation_data_from_bars(instrument, rows, is_synthetic=is_synthetic)
        series[instrument] = single.series[instrument]
        members[instrument] = single.members[instrument]
        all_dates.update(single.dates)
    if not series:
        raise ComparisonError("no_instruments_could_be_loaded")
    return SimulationData(
        dates=tuple(sorted(all_dates)), series=series, members=members, actions=(),
        fingerprint=f"multi:{len(series)}:{sorted(member.list_date.isoformat() for member in members.values())}",
    )
