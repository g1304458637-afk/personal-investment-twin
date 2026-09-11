"""Owned-account comparison and hypothetical-trade tool projections.

The private materializer is the only boundary that receives replay inputs.  It
copies and time-bounds one explicitly selected account once; tool responses
contain only :class:`AccountReviewRecord` projections.  No execution or market
row is returned to a model and no canonical source is mutated.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Mapping

import pandas as pd
from agents import RunContextWrapper, function_tool

from src.agents.account_review_sources import (
    PREPARED_HHI_HISTORY_ATTRIBUTE,
    _PreparedHhiHistory,
    _hhi_input_identity,
    AccountReviewContext,
    AccountReviewRecord,
)
from src.agents.review_sources import SELF_HISTORY_CALCULATION_CODE_VERSION
from src.behavior.portfolio_concentration import METHOD_ID as HHI_METHOD_ID
from src.behavior.replay_state import prepare_behavior_replay
from src.cohort.synthetic import synthetic_cohort_definition
from src.compare.account_comparison import compare_account_periods
from src.compare.periods import build_period_behavior
from src.compare.same_stock import build_episode_compare_facts, compare_same_stock
from src.core.canonical_execution import InstrumentRef
from src.evidence.contracts import canonical_json_bytes
from src.history.metric_series import HistoricalMetricSeries, build_portfolio_hhi_history
from src.performance.account_series import build_account_performance_from_replay
from src.presentation.runtime_episode import json_value
from src.pretrade.impact import ProposedTrade, simulate_trade_impact


MATERIALIZER_ATTRIBUTE = "_owned_analysis_sources_v1"
MATERIALIZER_VERSION = "owned_analysis_sources_v1"
RECORD_METHOD_VERSION = "1"


class OwnedAnalysisError(ValueError):
    """The requested read cannot cross the registered account boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _OwnedAnalysisSources:
    version: str
    subject_id: str
    account_id: str
    data_tier: str
    currency: str
    as_of: pd.Timestamp
    init_cash: float
    source_refs: tuple[str, ...]
    calculation_code_version: str
    executions: pd.DataFrame
    market_prices: pd.DataFrame
    instruments: tuple[InstrumentRef, ...]
    aliases: tuple[tuple[str, str], ...]
    canonical_episode_ids: tuple[str, ...]
    display_episode_ids: tuple[tuple[str, str], ...]
    hhi_history: HistoricalMetricSeries | None


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OwnedAnalysisError(code)
    return value.strip()


def _finite_positive(value: object, code: str) -> float:
    if isinstance(value, bool):
        raise OwnedAnalysisError(code)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise OwnedAnalysisError(code) from exc
    if not math.isfinite(result) or result <= 0:
        raise OwnedAnalysisError(code)
    return result


def _finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _registered_episode_ids(context: AccountReviewContext) -> tuple[str, ...]:
    found: list[str] = []
    for record in context.records.values():
        if record.kind != "episode_index" or not isinstance(record.value, dict):
            continue
        episodes = record.value.get("episodes")
        if not isinstance(episodes, (list, tuple)):
            continue
        for item in episodes:
            if isinstance(item, dict) and isinstance(item.get("episode_id"), str):
                found.append(item["episode_id"])
    return tuple(dict.fromkeys(found))


def _instrument_aliases(
    executed_symbols: tuple[str, ...],
    instruments: Mapping[str, InstrumentRef] | None,
) -> tuple[tuple[InstrumentRef, ...], tuple[tuple[str, str], ...]]:
    refs_by_id: dict[str, InstrumentRef] = {}
    candidates: dict[str, set[str]] = {symbol: {symbol} for symbol in executed_symbols}
    if instruments is not None:
        if not isinstance(instruments, Mapping):
            raise OwnedAnalysisError("owned_analysis_instruments_invalid")
        for supplied_alias, instrument in instruments.items():
            if not isinstance(instrument, InstrumentRef):
                raise OwnedAnalysisError("owned_analysis_instrument_ref_invalid")
            instrument_id = instrument.instrument_id
            if not isinstance(instrument_id, str) or instrument_id not in executed_symbols:
                raise OwnedAnalysisError("owned_analysis_instrument_outside_account")
            previous = refs_by_id.get(instrument_id)
            if previous is not None and previous != instrument:
                raise OwnedAnalysisError("owned_analysis_instrument_identity_conflict")
            refs_by_id[instrument_id] = instrument
            names = (
                supplied_alias,
                instrument_id,
                instrument.local_symbol,
                instrument.display_symbol,
            )
            for name in names:
                if isinstance(name, str) and name.strip():
                    candidates.setdefault(name.strip(), set()).add(instrument_id)
    aliases = tuple(
        sorted(
            (alias, next(iter(ids)))
            for alias, ids in candidates.items()
            if len(ids) == 1
        )
    )
    return tuple(refs_by_id[key] for key in sorted(refs_by_id)), aliases


def attach_owned_analysis_sources(
    context: AccountReviewContext,
    *,
    executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    init_cash: float,
    instruments: Mapping[str, InstrumentRef] | None = None,
    source_refs: tuple[str, ...] = (),
    calculation_code_version: str = MATERIALIZER_VERSION,
) -> None:
    """Attach one detached, cutoff account source to an ephemeral review context.

    The attachment is intentionally not a dataclass field, so ``asdict`` and
    public context projections cannot serialize the raw frames.  It remains a
    plain deepcopy-safe value because account-conversation runs copy contexts.
    """
    if not isinstance(context, AccountReviewContext):
        raise OwnedAnalysisError("owned_analysis_context_invalid")
    if hasattr(context, MATERIALIZER_ATTRIBUTE):
        raise OwnedAnalysisError("owned_analysis_sources_already_attached")
    if not isinstance(executions, pd.DataFrame) or executions.empty:
        raise OwnedAnalysisError("owned_analysis_executions_unavailable")
    if not isinstance(market_prices, pd.DataFrame) or market_prices.empty:
        raise OwnedAnalysisError("owned_analysis_prices_unavailable")
    required_execution_columns = {"subject_id", "account_id", "event_time", "symbol"}
    if not required_execution_columns.issubset(executions.columns) or not {
        "date", "instrument"
    }.issubset(market_prices.columns):
        raise OwnedAnalysisError("owned_analysis_source_schema_invalid")
    if not executions["subject_id"].eq(context.subject_id).all():
        raise OwnedAnalysisError("owned_analysis_subject_scope_mismatch")
    if not executions["account_id"].eq(context.account_id).all():
        raise OwnedAnalysisError("owned_analysis_account_scope_mismatch")
    cutoff = pd.Timestamp(context.as_of)
    if pd.isna(cutoff) or cutoff.tz is not None:
        raise OwnedAnalysisError("owned_analysis_as_of_invalid")
    cash = _finite_positive(init_cash, "owned_analysis_init_cash_invalid")
    try:
        event_times = pd.to_datetime(executions["event_time"], errors="raise", format="mixed")
        price_dates = pd.to_datetime(market_prices["date"], errors="raise", format="mixed")
    except (TypeError, ValueError) as exc:
        raise OwnedAnalysisError("owned_analysis_source_time_invalid") from exc
    if event_times.dt.tz is not None or price_dates.dt.tz is not None:
        raise OwnedAnalysisError("owned_analysis_timezone_not_supported")
    frame = executions.loc[event_times <= cutoff].copy(deep=True)
    market = market_prices.loc[price_dates.dt.normalize() <= cutoff.normalize()].copy(deep=True)
    if frame.empty or market.empty:
        raise OwnedAnalysisError("owned_analysis_source_unavailable_at_as_of")
    executed_symbols = tuple(sorted(set(frame["symbol"].astype(str).str.strip())))
    if any(not item for item in executed_symbols):
        raise OwnedAnalysisError("owned_analysis_instrument_invalid")
    known_prices = set(market["instrument"].astype(str).str.strip())
    if not set(executed_symbols).issubset(known_prices):
        raise OwnedAnalysisError("owned_analysis_registered_prices_missing")
    refs, aliases = _instrument_aliases(executed_symbols, instruments)
    canonical_episode_ids = _registered_episode_ids(context)
    if not canonical_episode_ids:
        raise OwnedAnalysisError("owned_analysis_episode_index_unavailable")
    display_map = tuple(sorted((str(key), str(value)) for key, value in context.episode_display_ids.items()))
    prepared = getattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE, None)
    hhi_history = None
    if prepared is not None:
        if (
            not isinstance(prepared, _PreparedHhiHistory)
            or prepared.subject_id != context.subject_id
            or prepared.account_id != context.account_id
            or prepared.data_tier != context.data_tier
            or prepared.as_of != cutoff
            or prepared.init_cash != cash
            or prepared.calculation_code_version != SELF_HISTORY_CALCULATION_CODE_VERSION
            or prepared.input_identity != _hhi_input_identity(frame, market)
            or not isinstance(prepared.history, HistoricalMetricSeries)
            or prepared.history.subject_id != context.subject_id
            or prepared.history.data_tier != context.data_tier
            or prepared.history.metric_id != "portfolio_concentration_hhi"
            or prepared.history.method_id != HHI_METHOD_ID
            or prepared.history.method_version != "1"
        ):
            raise OwnedAnalysisError("owned_analysis_prepared_history_invalid")
        hhi_history = prepared.history
    materialized = _OwnedAnalysisSources(
        MATERIALIZER_VERSION,
        context.subject_id,
        context.account_id,
        context.data_tier,
        context.currency,
        cutoff,
        cash,
        tuple(dict.fromkeys(str(item) for item in source_refs)),
        _required_text(calculation_code_version, "owned_analysis_calculation_version_invalid"),
        frame,
        market,
        refs,
        aliases,
        canonical_episode_ids,
        display_map,
        hhi_history,
    )
    setattr(context, MATERIALIZER_ATTRIBUTE, materialized)
    if hasattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE):
        delattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE)


def _sources(context: AccountReviewContext) -> _OwnedAnalysisSources:
    if not context.access_allowed():
        raise OwnedAnalysisError("account_review_cancelled")
    source = getattr(context, MATERIALIZER_ATTRIBUTE, None)
    if not isinstance(source, _OwnedAnalysisSources):
        raise OwnedAnalysisError("owned_analysis_sources_not_attached")
    if (
        source.subject_id != context.subject_id
        or source.account_id != context.account_id
        or source.data_tier != context.data_tier
        or source.currency != context.currency
        or source.as_of != pd.Timestamp(context.as_of)
    ):
        raise OwnedAnalysisError("owned_analysis_context_scope_changed")
    return source


def _stable_ref(kind: str, context: AccountReviewContext, value: object) -> str:
    identity = {
        "kind": kind,
        "subject_id": context.subject_id,
        "account_id": context.account_id,
        "as_of": context.as_of,
        "value": value,
    }
    return "account_fact_" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:24]


def _record(
    context: AccountReviewContext,
    source: _OwnedAnalysisSources,
    *,
    kind: str,
    title: str,
    method_id: str,
    availability: str,
    value: object,
    tags: tuple[str, ...],
    episode_id: str | None = None,
    instrument_id: str | None = None,
    underlying_refs: tuple[str, ...] = (),
) -> AccountReviewRecord:
    safe = json_value(value)
    record = AccountReviewRecord(
        ref=_stable_ref(kind, context, safe),
        kind=kind,
        title=title,
        subject_id=context.subject_id,
        account_id=context.account_id,
        episode_id=episode_id,
        instrument_id=instrument_id,
        currency=context.currency,
        as_of=context.as_of,
        method_id=method_id,
        method_version=RECORD_METHOD_VERSION,
        availability=availability,
        underlying_refs=tuple(dict.fromkeys((*source.source_refs, *underlying_refs))),
        tags=tags,
        value=safe,
    )
    existing = context.records.get(record.ref)
    if existing is not None and existing != record:
        raise OwnedAnalysisError("owned_analysis_record_identity_collision")
    context.records[record.ref] = record
    context.retrieved.add(record.ref)
    return record


def _response(record: AccountReviewRecord, status: str) -> str:
    return json.dumps(
        {"status": status, "records": [asdict(record)]},
        ensure_ascii=False,
        allow_nan=False,
    )


def _unavailable(
    context: AccountReviewContext,
    source: _OwnedAnalysisSources,
    *,
    kind: str,
    title: str,
    method_id: str,
    reason_code: str,
    message: str,
    clarification: bool = False,
    instrument_id: str | None = None,
    episode_id: str | None = None,
    requested_parameters: dict[str, object] | None = None,
) -> str:
    availability = "clarification_required" if clarification else "insufficient_evidence"
    record = _record(
        context,
        source,
        kind=kind,
        title=title,
        method_id=method_id,
        availability=availability,
        value={"reason_code": reason_code, "message": message,
               **({"requested_parameters": requested_parameters,
                   "parameter_semantics": "Inputs to the requested check, not executed trades or calculated financial results."}
                  if requested_parameters is not None else {})},
        tags=("owned_account", availability),
        instrument_id=instrument_id,
        episode_id=episode_id,
    )
    # The shared receipt verifier recognizes these two transport statuses.
    # The more precise state remains on AccountReviewRecord.availability.
    return _response(record, "insufficient_evidence")


def _resolve_symbol(source: _OwnedAnalysisSources, requested: str) -> str | None:
    value = requested.strip()
    matches = {instrument_id for alias, instrument_id in source.aliases if alias == value}
    return next(iter(matches)) if len(matches) == 1 else None


def hypothetical_trade_impact(
    context: AccountReviewContext,
    *,
    symbol: str,
    side: str,
    quantity: float,
    execution_price: float,
    fees: float | None,
) -> str:
    """Project one explicit hypothetical trade from the registered current state."""
    source = _sources(context)
    kind = "hypothetical_trade_impact"
    title = "当前账户假设交易前后变化"
    requested_symbol = _required_text(symbol, "hypothetical_trade_symbol_required")
    canonical_symbol = _resolve_symbol(source, requested_symbol)
    if canonical_symbol is None:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="pretrade_hhi_impact_v1",
            reason_code="instrument_not_registered_in_owned_scope",
            message="该证券不能唯一解析为当前账户已登记的持仓证券。",
        )
    if fees is None:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="pretrade_hhi_impact_v1",
            reason_code="fees_required",
            message="请提供这笔假设交易的费用；如需零费用情景，请明确填写 0。",
            clarification=True,
            instrument_id=canonical_symbol,
            requested_parameters={
                "symbol": requested_symbol,
                "side": side if side in {"BUY", "SELL"} else None,
                "quantity": float(quantity) if _finite_number(quantity) else None,
                "execution_price": float(execution_price) if _finite_number(execution_price) else None,
                "fees": None,
            },
        )
    if source.data_tier != "synthetic":
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="pretrade_hhi_impact_v1",
            reason_code="registered_pretrade_method_data_tier_unsupported",
            message="现有假设交易方法不能用于该账户的数据层级。",
            instrument_id=canonical_symbol,
        )
    if not all(_finite_number(item) for item in (quantity, execution_price, fees)):
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="pretrade_hhi_impact_v1",
            reason_code="hypothetical_trade_inputs_invalid",
            message="数量、成交价和费用必须是有限数值。",
            instrument_id=canonical_symbol,
        )
    try:
        trade = ProposedTrade(
            subject_id=context.subject_id,
            proposed_time=source.as_of,
            symbol=canonical_symbol,
            side=side,
            quantity=quantity,
            execution_price=execution_price,
            fees=fees,
        )
        history = source.hhi_history
        if history is None:
            history = build_portfolio_hhi_history(
                source.executions,
                source.market_prices,
                init_cash=source.init_cash,
                subject_id=context.subject_id,
                data_tier=source.data_tier,
                calculation_code_version=source.calculation_code_version,
            )
        impact = simulate_trade_impact(
            trade,
            source.executions,
            source.market_prices,
            init_cash=source.init_cash,
            hhi_history=history,
            cohort_definition=synthetic_cohort_definition(),
            peer_members=(),
            peer_metric_values=(),
            calculation_code_version=source.calculation_code_version,
            include_peer_context=False,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="pretrade_hhi_impact_v1",
            reason_code="hypothetical_trade_inputs_invalid",
            message=str(exc),
            instrument_id=canonical_symbol,
        )
    availability = "complete" if impact.simulation_status == "complete" else (
        "rejected" if impact.simulation_status == "rejected" else "insufficient_evidence"
    )
    record = _record(
        context,
        source,
        kind=kind,
        title=title,
        method_id=impact.method_id,
        availability=availability,
        instrument_id=canonical_symbol,
        underlying_refs=tuple(
            item
            for item in (impact.before_hhi_evidence_id, impact.after_hhi_evidence_id)
            if item is not None
        ),
        tags=("owned_account", "hypothetical_only", "no_order_submission", "no_peer_context"),
        value={
            "hypothetical_only": True,
            "canonical_records_mutated": False,
            "requested_at": source.as_of.isoformat(),
            "current_state_basis": "registered account snapshot immediately before requested_at",
            "execution_price_basis": "user supplied hypothetical execution price",
            "valuation_price_basis": "last registered market observation strictly before requested_at",
            "fees_basis": "explicit user supplied hypothetical fees",
            "impact": impact,
        },
    )
    return _response(
        record,
        "complete" if availability in {"complete", "rejected"} else "insufficient_evidence",
    )


def _calendar_date(value: object, code: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise OwnedAnalysisError(code) from exc
    if pd.isna(stamp) or stamp.tz is not None or stamp != stamp.normalize():
        raise OwnedAnalysisError(code)
    return stamp


@dataclass(frozen=True, slots=True)
class _EffectivePeriod:
    requested_start: pd.Timestamp
    requested_end: pd.Timestamp
    effective_start: pd.Timestamp
    effective_end: pd.Timestamp
    available_start: pd.Timestamp
    available_end: pd.Timestamp
    observation_count: int

    def public(self) -> dict[str, object]:
        return {
            "requested_start": self.requested_start.date().isoformat(),
            "requested_end": self.requested_end.date().isoformat(),
            "effective_start": self.effective_start.date().isoformat(),
            "effective_end": self.effective_end.date().isoformat(),
            "available_observation_start": self.available_start.date().isoformat(),
            "available_observation_end": self.available_end.date().isoformat(),
            "observation_count": self.observation_count,
            "start_clipped": self.effective_start != self.requested_start,
            "end_clipped": self.effective_end != self.requested_end,
        }


class _PeriodBoundaryError(OwnedAnalysisError):
    def __init__(self, code: str, details: dict[str, object]):
        super().__init__(code)
        self.details = details


def _iso_bounds(days: pd.Series) -> dict[str, str | None]:
    valid = tuple(sorted(set(days.dropna())))
    return {
        "source_observation_start": valid[0].date().isoformat() if valid else None,
        "source_observation_end": valid[-1].date().isoformat() if valid else None,
    }


def _effective_period(
    source: _OwnedAnalysisSources,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    label: str,
) -> _EffectivePeriod:
    event_days = pd.to_datetime(source.executions["event_time"], errors="raise", format="mixed").dt.normalize()
    price_days = pd.to_datetime(source.market_prices["date"], errors="raise", format="mixed").dt.normalize()
    details: dict[str, object] = {
        "period": label,
        "requested_start": start.date().isoformat(),
        "requested_end": end.date().isoformat(),
        **_iso_bounds(price_days),
    }
    prefix = source.executions.loc[event_days <= end]
    symbols = set(prefix["symbol"].astype(str).str.strip())
    if not symbols:
        details.update(
            available_observation_start=None,
            available_observation_end=None,
            effective_start=None,
            effective_end=None,
            observation_count=0,
        )
        raise _PeriodBoundaryError("owned_period_no_executions_through_end", details)
    relevant = source.market_prices.loc[
        source.market_prices["instrument"].astype(str).str.strip().isin(symbols)
    ]
    relevant_days = price_days.loc[relevant.index]
    instruments_by_day: dict[pd.Timestamp, set[str]] = {}
    for day, instrument in zip(
        relevant_days,
        relevant["instrument"].astype(str).str.strip(),
    ):
        instruments_by_day.setdefault(day, set()).add(instrument)
    complete = tuple(sorted(day for day, found in instruments_by_day.items() if symbols <= found))
    details.update(
        available_observation_start=complete[0].date().isoformat() if complete else None,
        available_observation_end=complete[-1].date().isoformat() if complete else None,
    )
    selected = tuple(day for day in complete if start <= day <= end)
    details.update(
        effective_start=selected[0].date().isoformat() if selected else None,
        effective_end=selected[-1].date().isoformat() if selected else None,
        observation_count=len(selected),
    )
    if not selected:
        raise _PeriodBoundaryError("owned_period_no_complete_observations", details)
    if len(selected) < 2:
        raise _PeriodBoundaryError("owned_period_insufficient_complete_observations", details)
    return _EffectivePeriod(start, end, selected[0], selected[-1], complete[0], complete[-1], len(selected))


def _period(source: _OwnedAnalysisSources, window: _EffectivePeriod):
    event_days = pd.to_datetime(source.executions["event_time"], errors="raise", format="mixed").dt.normalize()
    price_days = pd.to_datetime(source.market_prices["date"], errors="raise", format="mixed").dt.normalize()
    frame = source.executions.loc[event_days <= window.effective_end].copy(deep=True)
    market = source.market_prices.loc[price_days <= window.effective_end].copy(deep=True)
    replay = prepare_behavior_replay(frame, market, init_cash=source.init_cash)
    period_ref = (
        f"owned-period-requested:{window.requested_start.date().isoformat()}:"
        f"{window.requested_end.date().isoformat()}:effective:"
        f"{window.effective_start.date().isoformat()}:{window.effective_end.date().isoformat()}"
    )
    performance = build_account_performance_from_replay(
        replay.portfolio,
        account_id=source.account_id,
        base_currency=source.currency,
        source_refs=(*source.source_refs, period_ref),
        data_tier=source.data_tier,
        start_at=window.effective_start,
        as_of=window.effective_end,
        # AccountComparison does not compare volatility/Sharpe.  Omitting a
        # cadence proof keeps those fields unavailable instead of fabricating
        # a period-specific risk policy from a whole-account policy.
        risk_policy=None,
    )
    behavior = build_period_behavior(
        frame,
        market,
        init_cash=source.init_cash,
        start_date=window.effective_start,
        end_date=window.effective_end,
    )
    return performance, behavior


_PERIOD_SEMANTICS = (
    "Requested calendar bounds are preserved separately from effective calculation bounds. "
    "Each effective bound is the first or last complete registered valuation observation inside "
    "the requested range; no missing boundary is filled or inferred. Behavior counts use the "
    "registered (effective_start, effective_end] convention, so an execution on the effective "
    "start date is part of the valuation baseline rather than a counted in-period action."
)


def _display_value(value: float | None, digits: int, suffix: str, *, delta: bool = False) -> str | None:
    if value is None:
        return None
    numeric = float(value)
    prefix = "+" if delta and numeric > 0 else ""
    return f"{prefix}{numeric:.{digits}f}{suffix}"


def _period_display_metrics(comparison: object) -> list[dict[str, object]]:
    """Format existing comparison values without deriving or rescaling them."""
    displayed = []
    for metric in comparison.differences:
        if metric.unit == "percentage_points":
            left = _display_value(metric.left_value, 2, "%")
            right = _display_value(metric.right_value, 2, "%")
            difference = _display_value(
                metric.right_minus_left, 2, " pp（个百分点）", delta=True,
            )
        elif metric.metric_id == "portfolio_hhi":
            left = _display_value(metric.left_value, 4, "")
            right = _display_value(metric.right_value, 4, "")
            difference = _display_value(metric.right_minus_left, 4, "", delta=True)
        elif metric.metric_id == "recorded_fee_total":
            suffix = f" {metric.unit}"
            left = _display_value(metric.left_value, 2, suffix)
            right = _display_value(metric.right_value, 2, suffix)
            difference = _display_value(metric.right_minus_left, 2, suffix, delta=True)
        else:
            suffix = f" {metric.unit}" if metric.unit else ""
            left = _display_value(metric.left_value, 4, suffix)
            right = _display_value(metric.right_value, 4, suffix)
            difference = _display_value(metric.right_minus_left, 4, suffix, delta=True)
        displayed.append({
            "metric_id": metric.metric_id,
            "left": left,
            "right": right,
            "right_minus_left": difference,
            "source_unit": metric.unit,
        })
    return displayed


def _period_unavailable(
    context: AccountReviewContext,
    source: _OwnedAnalysisSources,
    *,
    kind: str,
    title: str,
    reason_code: str,
    message: str,
    requested_periods: dict[str, dict[str, str]],
    boundary: dict[str, object] | None = None,
) -> str:
    record = _record(
        context,
        source,
        kind=kind,
        title=title,
        method_id="account_period_factual_comparison_v1",
        availability="insufficient_evidence",
        value={
            "reason_code": reason_code,
            "message": message,
            "requested_periods": requested_periods,
            "period_semantics": _PERIOD_SEMANTICS,
            **({"unavailable_period_boundary": boundary} if boundary is not None else {}),
        },
        tags=("owned_account", "insufficient_evidence", "self_periods"),
    )
    return _response(record, "insufficient_evidence")


def owned_period_comparison(
    context: AccountReviewContext,
    *,
    earlier_start: str,
    earlier_end: str,
    later_start: str,
    later_end: str,
) -> str:
    """Compare two explicit chronological, non-overlapping owned periods."""
    source = _sources(context)
    kind = "owned_period_comparison"
    title = "同一账户较早与较晚期间比较"
    try:
        left_start = _calendar_date(earlier_start, "earlier_start_invalid")
        left_end = _calendar_date(earlier_end, "earlier_end_invalid")
        right_start = _calendar_date(later_start, "later_start_invalid")
        right_end = _calendar_date(later_end, "later_end_invalid")
        if not left_start < left_end <= right_start < right_end:
            raise OwnedAnalysisError("owned_periods_must_be_chronological_and_non_overlapping")
        if right_end > source.as_of.normalize():
            raise OwnedAnalysisError("owned_period_comparison_exceeds_account_as_of")
    except (TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, OwnedAnalysisError) else "owned_period_comparison_unavailable"
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="account_period_factual_comparison_v1",
            reason_code=code,
            message=str(exc),
        )
    requested_periods = {
        "earlier": {"start": left_start.date().isoformat(), "end": left_end.date().isoformat()},
        "later": {"start": right_start.date().isoformat(), "end": right_end.date().isoformat()},
    }
    left_window = right_window = None
    try:
        left_window = _effective_period(source, left_start, left_end, label="earlier")
        right_window = _effective_period(source, right_start, right_end, label="later")
        left, left_behavior = _period(source, left_window)
        right, right_behavior = _period(source, right_window)
        comparison = compare_account_periods(
            left,
            right,
            kind="self_periods",
            left_behavior=left_behavior,
            right_behavior=right_behavior,
        )
    except _PeriodBoundaryError as exc:
        messages = {
            "owned_period_no_executions_through_end": "请求区间结束前没有已登记账户执行，无法建立该区间状态。",
            "owned_period_no_complete_observations": "请求日历范围内没有覆盖相关账户证券的完整估值观察。",
            "owned_period_insufficient_complete_observations": "请求日历范围内不足两个完整估值观察日，不能建立期间表现。",
        }
        return _period_unavailable(
            context,
            source,
            kind=kind,
            title=title,
            reason_code=exc.code,
            message=messages[exc.code],
            requested_periods=requested_periods,
            boundary=exc.details,
        )
    except (KeyError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, OwnedAnalysisError) else "owned_period_comparison_unavailable"
        effective = {
            **({"earlier": left_window.public()} if left_window is not None else {}),
            **({"later": right_window.public()} if right_window is not None else {}),
        }
        return _period_unavailable(
            context,
            source,
            kind=kind,
            title=title,
            reason_code=code,
            message="已登记引擎无法在解析后的实际观察边界上完成期间比较。",
            requested_periods=requested_periods,
            boundary={"effective_periods": effective},
        )
    record = _record(
        context,
        source,
        kind=kind,
        title=title,
        method_id=comparison.method_id,
        availability="complete",
        underlying_refs=(comparison.comparison_id,),
        tags=("owned_account", "self_periods", "descriptive_not_skill_score", "no_professional_data"),
        value={
            "requested_periods": requested_periods,
            "effective_periods": {
                "earlier": left_window.public(),
                "later": right_window.public(),
            },
            "period_semantics": _PERIOD_SEMANTICS,
            "comparison": comparison,
            "display_metrics": _period_display_metrics(comparison),
            "display_metrics_semantics": (
                "Formatting-only copies of comparison.differences. Percentage left/right values "
                "are already percentages and are not multiplied by 100 again; right_minus_left "
                "uses percentage points (pp). Copy these strings without recalculation."
            ),
            "semantics": "right_minus_left compares the later period with the earlier period; it is not causal attribution or a skill score.",
        },
    )
    return _response(record, "complete")


def _resolve_episode(source: _OwnedAnalysisSources, requested: str) -> str | None:
    value = requested.strip()
    if value in source.canonical_episode_ids:
        return value
    matches = {
        canonical
        for canonical, display in source.display_episode_ids
        if display == value and canonical in source.canonical_episode_ids
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _instrument_ref(source: _OwnedAnalysisSources, instrument_id: str) -> InstrumentRef | None:
    matches = tuple(item for item in source.instruments if item.instrument_id == instrument_id)
    return matches[0] if len(matches) == 1 else None


def _compact_episode(facts: object) -> dict[str, object]:
    """Select registered episode facts without returning replay/path internals."""
    episode = facts.episode
    result = facts.outcome.actual_result
    return {
        "episode_id": episode.episode_id,
        "opened_at": episode.opened_at,
        "closed_at": episode.closed_at,
        "status": episode.status,
        "actual_result": result,
        "operations": tuple(
            {
                "decision_event_id": item.decision_event_id,
                "event_type": item.event_type,
                "event_time": item.event_time,
                "side": item.side,
                "executed_quantity": item.executed_quantity,
                "execution_price": item.execution_price,
                "execution_fee": item.execution_fee,
            }
            for item in facts.decisions
        ),
    }


def _compact_same_stock(comparison: object) -> dict[str, object]:
    return {
        "comparison_id": comparison.comparison_id,
        "method_id": comparison.method_id,
        "method_version": comparison.method_version,
        "status": comparison.status,
        "reasons": comparison.reasons,
        "as_of": comparison.as_of,
        "common_start": comparison.common_start,
        "common_end": comparison.common_end,
        "earlier": _compact_episode(comparison.a),
        "later": _compact_episode(comparison.b),
        "differences": comparison.differences,
        "limitations": comparison.limitations,
    }


def owned_same_stock_comparison(
    context: AccountReviewContext,
    *,
    earlier_episode_id: str,
    later_episode_id: str,
) -> str:
    """Compare two explicitly selected owned episodes of the same listing."""
    source = _sources(context)
    kind = "owned_same_stock_comparison"
    title = "同一账户两轮同股投资比较"
    earlier = _resolve_episode(
        source, _required_text(earlier_episode_id, "earlier_episode_id_required")
    )
    later = _resolve_episode(source, _required_text(later_episode_id, "later_episode_id_required"))
    if earlier is None or later is None or earlier == later:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="same_stock_descriptive_comparison_v1",
            reason_code="owned_episode_selection_invalid",
            message="需要明确选择当前账户中两轮不同且已登记的投资。",
        )
    episode_instruments: dict[str, str] = {}
    for record in context.records.values():
        if record.kind != "episode_index" or not isinstance(record.value, dict):
            continue
        for item in record.value.get("episodes", ()):
            if isinstance(item, dict) and item.get("episode_id") in {earlier, later}:
                episode_instruments[str(item["episode_id"])] = str(item.get("instrument_id", ""))
    instrument_ids = {episode_instruments.get(earlier), episode_instruments.get(later)}
    if len(instrument_ids) != 1 or None in instrument_ids or "" in instrument_ids:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="same_stock_descriptive_comparison_v1",
            reason_code="episodes_are_not_same_registered_instrument",
            message="所选两轮投资不是当前账户中同一已登记证券。",
        )
    instrument_id = next(iter(instrument_ids))
    instrument = _instrument_ref(source, instrument_id)
    if instrument is None:
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="same_stock_descriptive_comparison_v1",
            reason_code="instrument_identity_not_registered",
            message="缺少该证券明确的市场、类型和币种身份，不能进行同股比较。",
            instrument_id=instrument_id,
        )
    try:
        a = build_episode_compare_facts(
            source.executions,
            source.market_prices,
            subject_id=source.subject_id,
            account_id=source.account_id,
            instrument=instrument,
            as_of=source.as_of,
            init_cash=source.init_cash,
            data_tier=source.data_tier,
            episode_id=earlier,
        )
        b = build_episode_compare_facts(
            source.executions,
            source.market_prices,
            subject_id=source.subject_id,
            account_id=source.account_id,
            instrument=instrument,
            as_of=source.as_of,
            init_cash=source.init_cash,
            data_tier=source.data_tier,
            episode_id=later,
        )
        if a.episode.opened_at >= b.episode.opened_at:
            raise OwnedAnalysisError("owned_episodes_not_in_earlier_later_order")
        comparison = compare_same_stock(a, b)
    except (KeyError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, OwnedAnalysisError) else "owned_same_stock_comparison_unavailable"
        return _unavailable(
            context,
            source,
            kind=kind,
            title=title,
            method_id="same_stock_descriptive_comparison_v1",
            reason_code=code,
            message=str(exc),
            instrument_id=instrument_id,
        )
    availability = (
        "complete"
        if comparison.status == "comparable"
        else "partial"
        if comparison.status == "partially_comparable"
        else "insufficient_evidence"
    )
    record = _record(
        context,
        source,
        kind=kind,
        title=title,
        method_id=comparison.method_id,
        availability=availability,
        episode_id=earlier,
        instrument_id=instrument_id,
        underlying_refs=(earlier, later, comparison.comparison_id),
        tags=("owned_account", "same_stock", "owned_episodes_only", "descriptive_not_skill_score"),
        value={
            "earlier_episode_id": earlier,
            "later_episode_id": later,
            "comparison": _compact_same_stock(comparison),
            "professional_or_peer_data_used": False,
        },
    )
    return _response(
        record,
        "complete" if availability in {"complete", "partial"} else "insufficient_evidence",
    )


@function_tool
def get_hypothetical_trade_impact(
    ctx: RunContextWrapper[AccountReviewContext],
    symbol: str,
    side: str,
    quantity: float,
    execution_price: float,
    fees: float | None = None,
) -> str:
    """Read current-account changes for an explicit hypothetical BUY/SELL; fees are required, and no order is sent."""
    return hypothetical_trade_impact(
        ctx.context,
        symbol=symbol,
        side=side,
        quantity=quantity,
        execution_price=execution_price,
        fees=fees,
    )


@function_tool
def get_owned_period_comparison(
    ctx: RunContextWrapper[AccountReviewContext],
    earlier_start: str,
    earlier_end: str,
    later_start: str,
    later_end: str,
) -> str:
    """Compare explicit earlier/later periods of this owned account; never read a professional or peer account."""
    return owned_period_comparison(
        ctx.context,
        earlier_start=earlier_start,
        earlier_end=earlier_end,
        later_start=later_start,
        later_end=later_end,
    )


@function_tool
def get_owned_same_stock_comparison(
    ctx: RunContextWrapper[AccountReviewContext],
    earlier_episode_id: str,
    later_episode_id: str,
) -> str:
    """Compare two explicitly selected owned episodes of one registered listing; never use a professional account."""
    return owned_same_stock_comparison(
        ctx.context,
        earlier_episode_id=earlier_episode_id,
        later_episode_id=later_episode_id,
    )


OWNED_ANALYSIS_TOOLS = (
    get_hypothetical_trade_impact,
    get_owned_period_comparison,
    get_owned_same_stock_comparison,
)
