"""Deterministic, account-scoped facts and display findings for review.

This module is a projection over the existing replay, performance, behavior,
self-history and Position Episode builders.  It deliberately contains no
alternative financial formulas and never loads another account.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Callable

import pandas as pd

from src.agents.review_sources import (
    SELF_HISTORY_CALCULATION_CODE_VERSION,
    build_owned_self_history_with_hhi_history,
)
from src.behavior.portfolio_concentration import build_portfolio_concentration_evidence
from src.behavior.replay_state import prepare_behavior_replay
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.evidence.contracts import canonical_json_bytes
from src.history.metric_series import HistoricalMetricPoint, HistoricalMetricSeries
from src.performance.account_series import (
    AccountPerformanceSeriesError,
    DailyRiskPolicy,
    build_account_performance_from_replay,
)
from src.presentation.runtime_episode import json_value


ACCOUNT_CONTEXT_VERSION = "account_review_context_v1"
ACCOUNT_ANSWER_VERSION = "account_review_answer_v1"
PREPARED_HHI_HISTORY_ATTRIBUTE = "_account_review_hhi_history_v1"


@dataclass(frozen=True, slots=True)
class _PreparedHhiHistory:
    """Ephemeral series bound to the exact account-review replay inputs."""

    subject_id: str
    account_id: str
    data_tier: str
    as_of: pd.Timestamp
    init_cash: float
    calculation_code_version: str
    input_identity: str
    history: HistoricalMetricSeries


def _frame_identity(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(canonical_json_bytes({
        "columns": [str(item) for item in frame.columns],
        "dtypes": [str(item) for item in frame.dtypes],
        "index_names": [str(item) if item is not None else None for item in frame.index.names],
    }))
    digest.update(pd.util.hash_pandas_object(frame, index=True, categorize=False).values.tobytes())
    return digest.hexdigest()


def _hhi_input_identity(executions: pd.DataFrame, market_prices: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_json_bytes({
        "executions": _frame_identity(executions),
        "market_prices": _frame_identity(market_prices),
    })).hexdigest()


def _pretrade_hhi_view(history: HistoricalMetricSeries) -> HistoricalMetricSeries:
    """Keep only the immutable fields consumed by pre-trade self context."""
    return HistoricalMetricSeries(
        subject_id=history.subject_id,
        metric_id=history.metric_id,
        method_id=history.method_id,
        method_version=history.method_version,
        points=tuple(HistoricalMetricPoint(
            as_of=point.as_of,
            value=point.value,
            evidence_status=point.evidence_status,
            source_evidence_id=point.source_evidence_id,
            observation_count=point.observation_count,
        ) for point in history.points),
        data_tier=history.data_tier,
        limitations=history.limitations,
    )


def _text(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def _date(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("account_review_missing_date")
    return timestamp.strftime("%Y-%m-%d")


def _money(value: object, currency: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("account_review_invalid_financial_value")
    return f"{float(value):,.2f} {currency}"


def _percent(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("account_review_invalid_financial_value")
    return f"{float(value):.2%}"


def _stable_id(prefix: str, value: object) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class AccountReviewRecord:
    """One immutable tool record within exactly one owned account."""

    ref: str
    kind: str
    title: str
    subject_id: str
    account_id: str
    episode_id: str | None
    instrument_id: str | None
    currency: str
    as_of: str
    method_id: str
    method_version: str
    availability: str
    underlying_refs: tuple[str, ...]
    tags: tuple[str, ...]
    value: object


@dataclass(frozen=True, slots=True)
class AccountFindingOption:
    """Backend-authored answer fragment; the model may select only its ID."""

    id: str
    title: dict[str, str]
    body: dict[str, str]
    episode_id: str | None
    record_ref: str = field(repr=False)
    relevant_guide_ids: tuple[str, ...] = field(default=(), repr=False)

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": dict(self.title),
            "body": dict(self.body),
            "episode_id": self.episode_id,
        }


@dataclass
class AccountReviewContext:
    version: str
    subject_id: str
    account_id: str
    data_mode: str
    as_of: str
    data_tier: str
    currency: str
    records: dict[str, AccountReviewRecord]
    finding_options: tuple[AccountFindingOption, ...]
    retrieved: set[str] = field(default_factory=set)
    access_allowed: Callable[[], bool] = field(default=lambda: True, repr=False)
    # V2-only read model. Legacy V1 records/options and their hashes stay intact.
    conversation_records: dict[str, AccountReviewRecord] = field(default_factory=dict)
    # Navigation metadata only; canonical records/Evidence retain their IDs.
    episode_display_ids: dict[str, str] = field(default_factory=dict)
    # Ephemeral public-research access for one job. Never Evidence and never archived.
    public_research: object | None = field(default=None, repr=False)
    # Request identity is retained for navigation/cache isolation. Records keep
    # their canonical owned Episode IDs; never broaden a focused conversation.
    focus_episode_id: str | None = None

    @property
    def scope(self) -> dict[str, str]:
        return {
            "scope_kind": "episode" if self.focus_episode_id else "account",
            "subject_id": self.subject_id,
            "account_id": self.account_id,
            "data_mode": self.data_mode,
            **({"episode_id": self.focus_episode_id} if self.focus_episode_id else {}),
        }


def _record(*, kind: str, subject_id: str, account_id: str, currency: str,
            as_of: object, method_id: str, method_version: str, availability: str,
            underlying_refs: tuple[str, ...], tags: tuple[str, ...], value: object,
            episode_id: str | None = None, instrument_id: str | None = None,
            identity_extra: object | None = None) -> AccountReviewRecord:
    identity = {
        "kind": kind, "subject_id": subject_id, "account_id": account_id,
        "episode_id": episode_id, "instrument_id": instrument_id,
        "as_of": pd.Timestamp(as_of).isoformat(), "method_id": method_id,
        "method_version": method_version, "underlying_refs": list(underlying_refs),
    }
    if identity_extra is not None:
        identity["identity_extra"] = identity_extra
    return AccountReviewRecord(
        ref=_stable_id("account_fact_", identity), kind=kind,
        title={
            "snapshot": "当前账户估值",
            "performance": "账户表现序列",
            "behavior": "集中度与换手",
            "self_history": "和自己的过去相比",
            "episode_index": "投资 Episode 索引",
            "episode_detail": "这轮投资的实际结果与操作",
            "episode_results": "各轮投资的实际结果",
            "performance_path": "账户实际日表现路径",
            "knowledge": "金融概念与图表读法",
            "allocation": "当前账户现金与风险资产估值",
            "public_security": "公开证券识别",
            "public_ohlcv": "公开日线行情",
            "public_snapshot": "公开行情快照",
            "public_technical": "公开技术指标",
            "public_financials": "公开财务报表与指标",
            "public_search": "公开网页检索",
            "research_status": "本轮研究服务配置",
        }[kind],
        subject_id=subject_id, account_id=account_id, episode_id=episode_id,
        instrument_id=instrument_id, currency=currency,
        as_of=pd.Timestamp(as_of).isoformat(), method_id=method_id,
        method_version=method_version, availability=availability,
        underlying_refs=underlying_refs, tags=tags, value=json_value(value),
    )


def _option(record: AccountReviewRecord, *, title: dict[str, str], body: dict[str, str],
            episode_id: str | None = None, guides: tuple[str, ...] = ()) -> AccountFindingOption:
    public = {"title": title, "body": body, "episode_id": episode_id}
    return AccountFindingOption(
        id=_stable_id("account_finding_", {"record_ref": record.ref, **public}),
        title=title, body=body, episode_id=episode_id, record_ref=record.ref,
        relevant_guide_ids=guides,
    )


def _last_scalar(value: object, name: str) -> float:
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise ValueError(f"account_review_{name}_not_account_scoped")
        value = value.iloc[:, 0]
    if not isinstance(value, pd.Series) or value.empty:
        raise ValueError(f"account_review_{name}_unavailable")
    result = float(value.iloc[-1])
    if not math.isfinite(result):
        raise ValueError(f"account_review_{name}_invalid")
    return result


def _snapshot(replay, *, display_names: dict[str, str], currency: str, as_of: object):
    portfolio = replay.portfolio
    value = _last_scalar(portfolio.value(), "portfolio_value")
    cash = _last_scalar(portfolio.cash(), "cash")
    asset_values = portfolio.asset_value(group_by=False)
    if not isinstance(asset_values, pd.DataFrame) or asset_values.empty:
        raise ValueError("account_review_holdings_unavailable")
    latest = asset_values.iloc[-1].astype(float)
    if not all(math.isfinite(float(item)) and float(item) >= -1e-9 for item in latest):
        raise ValueError("account_review_holdings_invalid")
    holdings = [
        {
            "instrument_id": str(instrument_id),
            "display_name": display_names.get(str(instrument_id), str(instrument_id)),
            "market_value": float(asset_value),
            "portfolio_weight": float(asset_value) / value,
        }
        for instrument_id, asset_value in latest.items() if float(asset_value) > 1e-12
    ]
    holdings.sort(key=lambda item: (-float(item["portfolio_weight"]), str(item["instrument_id"])))
    return {
        "valuation_date": _date(as_of),
        "observation_semantics": "daily_eod_last_actual_replay_observation_no_fill",
        "portfolio_value": value,
        "cash": cash,
        "cash_weight": cash / value,
        "holdings": holdings,
    }


def _snapshot_option(record: AccountReviewRecord) -> AccountFindingOption:
    value = record.value
    holdings = value["holdings"]
    if holdings:
        top = holdings[:3]
        zh_positions = "、".join(f"{item['display_name']} {_percent(item['portfolio_weight'])}" for item in top)
        en_positions = ", ".join(f"{item['display_name']} {_percent(item['portfolio_weight'])}" for item in top)
        zh_tail = f"；前三项当前持仓为 {zh_positions}"
        en_tail = f"; the first three current holdings are {en_positions}"
    else:
        zh_tail, en_tail = "；当前没有风险资产持仓", "; there are no current risky-asset holdings"
    return _option(record,
        title=_text(f"{value['valuation_date']} · 当前账户", f"{value['valuation_date']} · Current account"),
        body=_text(
            f"按最后一条实际日估值记录，账户价值为 {_money(value['portfolio_value'], record.currency)}，"
            f"现金为 {_money(value['cash'], record.currency)}（{_percent(value['cash_weight'])}）{zh_tail}。",
            f"At the last actual daily valuation, account value is {_money(value['portfolio_value'], record.currency)} "
            f"and cash is {_money(value['cash'], record.currency)} ({_percent(value['cash_weight'])}){en_tail}.",
        ))


def _performance_option(record: AccountReviewRecord) -> AccountFindingOption:
    value = record.value
    recovery_zh = "尚未记录恢复日" if value["max_drawdown_recovered_at"] is None else f"记录的恢复日为 {_date(value['max_drawdown_recovered_at'])}"
    recovery_en = "no recovery date is recorded" if value["max_drawdown_recovered_at"] is None else f"the recorded recovery date is {_date(value['max_drawdown_recovered_at'])}"
    return _option(record,
        title=_text("账户实际表现路径", "Actual account performance path"),
        body=_text(
            f"{_date(value['period_start'])} 至 {_date(value['period_end'])} 的账户时间加权收益率（TWR）为 {_percent(value['period_return'])}；"
            f"最大回撤幅度为 {_percent(value['max_drawdown_magnitude'])}，{recovery_zh}。",
            f"Account TWR from {_date(value['period_start'])} to {_date(value['period_end'])} was {_percent(value['period_return'])}; "
            f"maximum drawdown magnitude was {_percent(value['max_drawdown_magnitude'])}, and {recovery_en}.",
        ), guides=("episode-process",))


def _behavior_options(record: AccountReviewRecord) -> tuple[AccountFindingOption, ...]:
    value = record.value
    options: list[AccountFindingOption] = []
    concentration = value["concentration"]
    if concentration["evidence_status"] == "complete":
        options.append(_option(record,
            title=_text("当前持仓集中度", "Current holdings concentration"),
            body=_text(
                f"当前风险资产 HHI 为 {concentration['hhi']:.4f}，最大单一风险资产权重为 {_percent(concentration['top1_weight'])}。"
                "权重按风险资产归一化并排除现金；这里不套用高低阈值，也不评价好坏。",
                f"Current risky-asset HHI is {concentration['hhi']:.4f}, and the largest risky-asset weight is {_percent(concentration['top1_weight'])}. "
                "Weights are normalized across risky assets and exclude cash; no high/low threshold or quality judgment is applied.",
            ), guides=("pretrade-allocation",)))
    turnover = value["turnover"]
    if turnover["evidence_status"] == "complete":
        options.append(_option(record,
            title=_text("账户换手观察", "Account turnover observation"),
            body=_text(
                f"现有 {turnover['observation_days']} 个实际日估值观察中的平均日换手为 {_percent(turnover['mean_daily_turnover'])}。"
                "它是双边成交额相对账户价值的描述，不是过度交易标签。",
                f"Mean daily turnover across {turnover['observation_days']} actual daily valuation observations is {_percent(turnover['mean_daily_turnover'])}. "
                "This describes double-sided traded value relative to account value; it is not an overtrading label.",
            )))
    return tuple(options)


def _self_history_options(record: AccountReviewRecord) -> tuple[AccountFindingOption, ...]:
    if record.availability != "complete":
        return ()
    labels = {
        "portfolio_concentration_hhi": ("集中度", "Concentration"),
        "mean_daily_turnover": ("日换手", "Daily turnover"),
    }
    bands = {
        "below_historical_iqr": ("低于自己的历史四分位区间", "below your historical interquartile range"),
        "within_historical_iqr": ("位于自己的历史四分位区间内", "within your historical interquartile range"),
        "above_historical_iqr": ("高于自己的历史四分位区间", "above your historical interquartile range"),
    }
    result = []
    for metric in record.value["metrics"]:
        default = next((item for item in metric["windows"] if item["window"] == record.value["default_window"]), None)
        if default is None or default["status"] != "complete" or metric["metric_id"] not in labels:
            continue
        zh_name, en_name = labels[metric["metric_id"]]
        zh_band, en_band = bands[default["comparison_band"]]
        current_display = (f"{default['current_value']:.4f}"
                           if metric["metric_id"] == "portfolio_concentration_hhi"
                           else _percent(default["current_value"]))
        result.append(_option(record,
            title=_text(f"{zh_name}与自己的过去", f"{en_name} versus your own history"),
            body=_text(
                f"在滚动 12 个月口径下，当前{zh_name}为 {current_display}，{zh_band}；"
                f"比较使用 {default['valid_n']} 个较早的有效观察。这是描述性自我比较，不是能力评分。",
                f"On the rolling 12-month basis, current {en_name.lower()} is {current_display}, {en_band}; "
                f"the comparison uses {default['valid_n']} earlier valid observations. This is descriptive self-comparison, not a skill score.",
            )))
    return tuple(result)


def _episode_options(record: AccountReviewRecord) -> tuple[AccountFindingOption, ...]:
    result = []
    for episode in record.value["episodes"]:
        opened = _date(episode["opened_at"])
        if episode["status"] == "closed":
            zh_state = f"已于 {_date(episode['closed_at'])} 结束"
            en_state = f"closed on {_date(episode['closed_at'])}"
        else:
            zh_state, en_state = "截至估值日仍未结束", "still open at the valuation date"
        result.append(_option(record,
            title=_text(f"{opened} · {episode['display_name']}", f"{opened} · {episode['display_name']}"),
            body=_text(
                f"这轮投资于 {opened} 开始，{zh_state}。可打开投资过程，查看已记录操作与结果形成过程。",
                f"This investment opened on {opened} and was {en_state}. Open its chart to inspect the recorded operations and result formation.",
            ), episode_id=episode["episode_id"], guides=("episode-process", "same-stock")))
    return tuple(result)


def build_account_review_context(executions: pd.DataFrame, market_prices: pd.DataFrame, *,
                                 subject_id: str, account_id: str, data_mode: str,
                                 as_of: object, init_cash: float, data_tier: str,
                                 currency: str, lifecycle: object,
                                 display_names: dict[str, str], source_refs: tuple[str, ...],
                                 include_conversation: bool = False,
                                 risk_policy: DailyRiskPolicy | None = None) -> AccountReviewContext:
    """Build one exact account projection without peers or synthetic fallback."""
    if not isinstance(executions, pd.DataFrame) or executions.empty:
        raise ValueError("account_review_no_executions")
    if "subject_id" not in executions or not executions["subject_id"].eq(subject_id).all():
        raise ValueError("account_review_subject_scope_mismatch")
    if "account_id" not in executions or not executions["account_id"].eq(account_id).all():
        raise ValueError("account_review_account_scope_mismatch")
    cutoff = pd.Timestamp(as_of)
    if pd.isna(cutoff):
        raise ValueError("account_review_as_of_invalid")
    if (getattr(lifecycle, "subject_id", None) != subject_id
            or pd.Timestamp(getattr(lifecycle, "as_of", None)) != cutoff
            or getattr(lifecycle, "data_tier", None) != data_tier
            or any((item.subject_id, item.account_id) != (subject_id, account_id)
                   for item in getattr(lifecycle, "episodes", ()))):
        raise ValueError("account_review_lifecycle_scope_or_time_mismatch")
    try:
        execution_times = pd.to_datetime(executions["event_time"], errors="raise")
        price_dates = pd.to_datetime(market_prices["date"], errors="raise")
        # Keep exact execution timestamps. Daily market rows use their contract
        # calendar dates and remain otherwise unchanged; no value is filled.
        frame = executions.loc[execution_times <= cutoff].copy()
        market = market_prices.loc[price_dates.dt.normalize() <= pd.Timestamp(cutoff.date())].copy()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("account_review_as_of_boundary_invalid") from exc
    if frame.empty or market.empty:
        raise ValueError("account_review_source_unavailable_at_as_of")
    replay = prepare_behavior_replay(frame, market, init_cash=init_cash)
    valuation_date = pd.Timestamp(cutoff.date())
    snapshot = _snapshot(replay, display_names=display_names, currency=currency, as_of=valuation_date)
    try:
        performance = build_account_performance_from_replay(
            replay.portfolio, account_id=account_id, base_currency=currency,
            source_refs=source_refs, data_tier=data_tier, as_of=valuation_date,
            risk_policy=risk_policy,
        )
    except AccountPerformanceSeriesError as exc:
        performance = None
        performance_unavailable_reason = str(exc)
    concentration = build_portfolio_concentration_evidence(frame, market, init_cash=init_cash)
    turnover = build_turnover_intensity_evidence(frame, market, init_cash=init_cash)
    self_history, hhi_history = build_owned_self_history_with_hhi_history(
        frame, market, subject_id=subject_id, account_id=account_id,
        as_of=cutoff, init_cash=init_cash, data_tier=data_tier,
    )
    episodes = tuple({
        "episode_id": item.episode_id,
        "instrument_id": item.instrument_id,
        "display_name": display_names.get(item.instrument_id, item.instrument_id),
        "status": item.status,
        "opened_at": item.opened_at,
        "closed_at": item.closed_at,
    } for item in lifecycle.episodes)
    refs = tuple(dict.fromkeys(str(item) for item in source_refs))
    records = {}
    snapshot_record = _record(kind="snapshot", subject_id=subject_id, account_id=account_id,
        currency=currency, as_of=as_of, method_id="vectorbt_account_state_v1", method_version="1",
        availability="complete", underlying_refs=refs, tags=("current_account",), value=snapshot)
    records[snapshot_record.ref] = snapshot_record
    performance_record = _record(kind="performance", subject_id=subject_id, account_id=account_id,
        currency=currency, as_of=as_of,
        method_id=performance.method_id if performance else "account_fixed_cash_twr_empyrical_v1",
        method_version=performance.method_version if performance else "1.0.0",
        availability="complete" if performance else "insufficient_evidence",
        underlying_refs=performance.source_refs if performance else refs,
        tags=("account_twr", "max_drawdown"),
        value=({key: value for key, value in performance.as_dict().items() if key != "points"}
               if performance else {"reason": performance_unavailable_reason}))
    records[performance_record.ref] = performance_record
    behavior_record = _record(kind="behavior", subject_id=subject_id, account_id=account_id,
        currency=currency, as_of=as_of, method_id="registered_account_behavior_evidence_v1", method_version="1",
        availability="complete" if (concentration.evidence_status == "complete" or turnover.evidence_status == "complete") else "insufficient_evidence",
        underlying_refs=refs, tags=("portfolio_concentration_hhi", "mean_daily_turnover"),
        value={"concentration": asdict(concentration), "turnover": asdict(turnover)})
    records[behavior_record.ref] = behavior_record
    history_record = _record(kind="self_history", subject_id=subject_id, account_id=account_id,
        currency=currency, as_of=as_of, method_id="self_historical_distribution_v1", method_version="1",
        availability="complete" if self_history.available_metric_count else "insufficient_evidence",
        underlying_refs=refs, tags=("portfolio_concentration_hhi", "mean_daily_turnover"), value=self_history)
    records[history_record.ref] = history_record
    episode_record = _record(kind="episode_index", subject_id=subject_id, account_id=account_id,
        currency=currency, as_of=as_of, method_id="position_episode_lifecycle_v1", method_version="1",
        availability="complete", underlying_refs=refs, tags=("owned_episode_index",),
        value={"episodes": episodes})
    records[episode_record.ref] = episode_record
    options = (
        _snapshot_option(snapshot_record),
        *((_performance_option(performance_record),) if performance else ()),
        *_behavior_options(behavior_record), *_self_history_options(history_record),
        *_episode_options(episode_record),
    )
    if len({item.id for item in options}) != len(options):
        raise ValueError("duplicate_account_finding_option")
    # Keep this projection JSON-safe now, before any tool or model sees it.
    json.dumps([item.public() for item in options], ensure_ascii=False, allow_nan=False)
    context = AccountReviewContext(
        version=ACCOUNT_CONTEXT_VERSION, subject_id=subject_id, account_id=account_id,
        data_mode=data_mode, as_of=pd.Timestamp(as_of).isoformat(), data_tier=data_tier,
        currency=currency, records=records, finding_options=tuple(options),
    )
    # Ephemeral replay input for the owned hypothetical tool.  It is kept out
    # of the dataclass so public/asdict projections cannot serialize it, then
    # consumed by attach_owned_analysis_sources after account scoping checks.
    setattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE, _PreparedHhiHistory(
        subject_id=subject_id,
        account_id=account_id,
        data_tier=data_tier,
        as_of=cutoff,
        init_cash=float(init_cash),
        calculation_code_version=SELF_HISTORY_CALCULATION_CODE_VERSION,
        input_identity=_hhi_input_identity(frame, market),
        history=_pretrade_hhi_view(hhi_history),
    ))
    if include_conversation:
        from src.agents.account_conversation_sources import extend_conversation_context
        extend_conversation_context(context, lifecycle=lifecycle, executions=frame,
            market=market, init_cash=init_cash, display_names=display_names,
            performance=performance, source_refs=refs, replay=replay)
    return context


def compose_account_answer(selected_ids: list[str], guide_ids: list[str],
                           context: AccountReviewContext) -> dict[str, object]:
    """Rebuild and copy selected backend options after receipt verification."""
    if len(selected_ids) != len(set(selected_ids)) or not 1 <= len(selected_ids) <= 3:
        raise ValueError("invalid_account_finding_selection")
    by_id = {item.id: item for item in context.finding_options}
    if any(item_id not in by_id for item_id in selected_ids):
        raise ValueError("invalid_account_finding_selection")
    selected = [by_id[item_id] for item_id in selected_ids]
    if any(item.record_ref not in context.retrieved for item in selected):
        raise ValueError("account_finding_option_not_read")
    if len(guide_ids) != len(set(guide_ids)) or any(item not in {
        "episode-process", "pretrade-allocation", "same-stock"} for item in guide_ids):
        raise ValueError("invalid_account_guide_selection")
    relevant = {guide for item in selected for guide in item.relevant_guide_ids}
    if not set(guide_ids) <= relevant:
        raise ValueError("irrelevant_account_guide_selection")
    snapshot = next(record for record in context.records.values() if record.kind == "snapshot")
    if snapshot.ref not in context.retrieved:
        raise ValueError("account_summary_not_read")
    value = snapshot.value
    summary = _text(
        f"截至 {value['valuation_date']} 的最后一条实际日估值，账户价值为 {_money(value['portfolio_value'], context.currency)}；以下发现只来自当前账户的已读取记录。",
        f"At the last actual daily valuation on {value['valuation_date']}, account value was {_money(value['portfolio_value'], context.currency)}; the findings below use only read records from this account.",
    )
    return {
        "version": ACCOUNT_ANSWER_VERSION,
        "summary": summary,
        "findings": [item.public() for item in selected],
        "guide_ids": list(guide_ids),
    }
