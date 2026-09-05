"""Toujing-specific, descriptive same-listing comparison over existing engines.

This is a trusted backend projection, not an authorization mechanism. Callers
must resolve consent before constructing a counterpart's facts. Full-period
outcomes are never relabeled as common-window performance or investor skill.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.attribution.decision_outcome import (
    DecisionImmediateOutcome, EpisodeOutcome, build_actual_outcomes,
)
from src.core.canonical_execution import InstrumentRef
from src.episodes.position_episode import PositionEpisode, build_position_episode_lifecycle
from src.evidence.contracts import canonical_json_bytes
from src.path.analysis import EpisodePathAnalysis, build_episode_path_analysis
from src.path.market_path import DailyMarketObservation
from src.presentation.runtime_episode import json_value

METHOD_ID = "same_stock_descriptive_comparison_v1"
METHOD_VERSION = "1"
LIMITATIONS = (
    "各自完整投资期间的结果，不是共同区间收益，也不是能力排名。",
    "标准化持仓仅显示各自加减仓形状，不等于账户风险暴露。",
    "共同价格仅使用双方一致的已记录日观察；不补齐缺失日期，不代表盘中已知价格。",
    "操作差异与结果并列存在，不构成因果归因或复制对方交易的可行性结论。",
)


@dataclass(frozen=True, slots=True)
class EpisodeCompareFacts:
    instrument: InstrumentRef
    episode: PositionEpisode
    as_of: pd.Timestamp
    outcome: EpisodeOutcome
    decisions: tuple[DecisionImmediateOutcome, ...]
    path: EpisodePathAnalysis


@dataclass(frozen=True, slots=True)
class ShapePoint:
    as_of: pd.Timestamp
    state_ref: str
    decision_ref: str | None
    boundary: str
    quantity: float
    average_cost: float | None
    normalized_quantity: float


@dataclass(frozen=True, slots=True)
class FactualDifference:
    fact_id: str
    dimension: str
    a_value: int
    b_value: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    fact_refs: tuple[str, ...]
    a_decision_refs: tuple[str, ...]
    b_decision_refs: tuple[str, ...]
    market_observation_refs: tuple[str, ...]
    interpretation_boundary: str


@dataclass(frozen=True, slots=True)
class SameStockComparison:
    comparison_id: str
    method_id: str
    method_version: str
    status: Literal["comparable", "partially_comparable", "unavailable"]
    reasons: tuple[str, ...]
    as_of: pd.Timestamp
    a: EpisodeCompareFacts
    b: EpisodeCompareFacts
    common_start: pd.Timestamp | None
    common_end: pd.Timestamp | None
    market_observations: tuple[DailyMarketObservation, ...]
    a_position_shape: tuple[ShapePoint, ...]
    b_position_shape: tuple[ShapePoint, ...]
    differences: tuple[FactualDifference, ...]
    limitations: tuple[str, ...] = LIMITATIONS


def build_episode_compare_facts(
    executions: pd.DataFrame, market_prices: pd.DataFrame, *,
    subject_id: str, account_id: str, instrument: InstrumentRef,
    as_of: pd.Timestamp, init_cash: float, data_tier: str,
    episode_id: str | None = None,
) -> EpisodeCompareFacts:
    """Replay all allowed account facts, then select exactly one owned Episode.

    No cropped-period replay, execution sorting, cost/PnL formula, price filling
    or counterpart access is implemented here. Explicit ownership columns are
    required at this new boundary rather than inferred from an Episode ID.
    """
    if not instrument.instrument_id or not instrument.currency:
        raise ValueError("需要完整证券身份和币种")
    for name, expected in (("subject_id", subject_id), ("account_id", account_id)):
        if name not in executions or executions.empty or not executions[name].eq(expected).all():
            raise ValueError("成交归属与所选主体/账户不一致")
    lifecycle = build_position_episode_lifecycle(
        executions, market_prices, subject_id=subject_id, account_id=account_id,
        as_of=pd.Timestamp(as_of), init_cash=init_cash, data_tier=data_tier,
        calculation_code_version=METHOD_ID,
    )
    candidates = tuple(item for item in lifecycle.episodes
                       if item.instrument_id == instrument.instrument_id
                       and (episode_id is None or item.episode_id == episode_id))
    if len(candidates) != 1:
        raise ValueError("需要明确选择一轮属于该账户和证券的投资")
    episode = candidates[0]
    outcomes = build_actual_outcomes(
        lifecycle, executions, market_prices, subject_id=subject_id,
        account_id=account_id, analysis_as_of=lifecycle.as_of, init_cash=init_cash,
    )
    path = build_episode_path_analysis(
        lifecycle, executions, market_prices, episode_id=episode.episode_id,
        init_cash=init_cash, include_phase_counterfactuals=False,
    )
    return EpisodeCompareFacts(
        instrument, episode, lifecycle.as_of,
        next(item for item in outcomes.episode_outcomes if item.episode_id == episode.episode_id),
        tuple(item for item in outcomes.decision_outcomes if item.episode_id == episode.episode_id),
        path,
    )


def observation_ref(item: DailyMarketObservation) -> str:
    return "market_" + hashlib.sha256(canonical_json_bytes(json_value(item))).hexdigest()


def _shape(facts: EpisodeCompareFacts) -> tuple[ShapePoint, ...]:
    # A display normalization of existing replay quantities, NOT risk or return.
    maximum = facts.path.position_path.max_quantity
    if maximum <= 0:
        raise ValueError("无法标准化没有正持仓的投资路径")
    return tuple(ShapePoint(p.as_of, p.state_id, p.decision_event_id, p.boundary,
                            p.quantity, p.average_cost, p.quantity / maximum)
                 for p in facts.path.position_path.points)


def compare_same_stock(a: EpisodeCompareFacts, b: EpisodeCompareFacts) -> SameStockComparison:
    """Compare already-authorized facts; no raw row access or permission inference.

    Only exactly matching daily provenance AND prices may form one shared path.
    Observation-set differences are preserved and make the result partial.
    No calendar is invented, so a weekend alone is not classified as missing.
    """
    reasons: list[str] = []
    fatal = False
    identity = lambda x: (x.instrument_id, x.local_symbol, x.market, x.security_type)
    if identity(a.instrument) != identity(b.instrument):
        reasons.append("并非同一交易市场和证券类型的同一证券")
        fatal = True
    if not a.instrument.currency or a.instrument.currency != b.instrument.currency:
        reasons.append("币种缺失或不一致；不进行汇率换算")
        fatal = True
    if a.episode.data_tier != b.episode.data_tier:
        reasons.append("数据层级不同，不能混用真实账户与示例")
        fatal = True
    if a.as_of != b.as_of:
        reasons.append("分析截止时间不一致，需要在相同截止时间重建")
        fatal = True
    for f in (a, b):
        e, o = f.episode, f.outcome
        if ((e.subject_id, e.account_id, e.episode_id, e.instrument_id)
                != (o.subject_id, o.account_id, o.episode_id, o.instrument_id)
                or e.instrument_id != f.instrument.instrument_id or o.analysis_as_of != f.as_of
                or any(d.event_time > f.as_of for d in f.decisions)):
            reasons.append("生命周期、结果或时间归属不一致")
            fatal = True
    start = max(a.episode.opened_at, b.episode.opened_at)
    end = min(a.episode.closed_at or a.as_of, b.episode.closed_at or b.as_of)
    observations: tuple[DailyMarketObservation, ...] = ()
    if start >= end:
        reasons.append("没有重叠的投资期间")
        fatal = True
    else:
        def daily(f):
            return {p.observed_at: p for p in f.path.market_path.episode_market_path.observations
                    if start.normalize() <= p.observed_at <= end.normalize()}
        ad, bd = daily(a), daily(b)
        shared = sorted(ad.keys() & bd.keys())
        if any(ad[d] != bd[d] for d in shared):
            reasons.append("共同日价格或来源、价格类型、版本冲突")
            fatal = True
        else:
            observations = tuple(ad[d] for d in shared)
        if not shared:
            reasons.append("没有双方共同可验证的市场观察")
            fatal = True
        elif len(shared) == 1:
            reasons.append("仅一个共同日观察，不能形成共同市场趋势")
        if ad.keys() != bd.keys():
            reasons.append("双方记录日期不完整一致；缺失日不补齐")
    if a.episode.status != b.episode.status:
        reasons.append("一方为已实现结果，另一方为持有中的估值结果")
    if (a.episode.opened_at, a.episode.closed_at) != (b.episode.opened_at, b.episode.closed_at):
        reasons.append("完整投资期间不同，结果不能视为同区间绩效")

    differences: list[FactualDifference] = []
    if not fatal:
        # Counts describe canonical decisions only. Zero denotes checked absence
        # in this window; no raw-share cross-account risk comparison is made.
        for kind in ("open_position", "add_position", "reduce_position", "close_position"):
            selected = [tuple(d for d in f.decisions if d.event_type == kind and start <= d.event_time <= end)
                        for f in (a, b)]
            left, right = selected
            if len(left) == len(right):
                continue
            refs = tuple(d.outcome_id for group in selected for d in group)
            # Full-scope outcomes establish that the absent side was searched.
            fact_refs = (a.outcome.outcome_id, b.outcome.outcome_id, *refs)
            digest = hashlib.sha256(canonical_json_bytes(json_value((kind, start, end, fact_refs)))).hexdigest()
            differences.append(FactualDifference(
                "difference_" + digest, kind, len(left), len(right), start, end,
                fact_refs, tuple(d.decision_event_id for d in left),
                tuple(d.decision_event_id for d in right),
                tuple(observation_ref(p) for p in observations),
                "仅陈述共同时间范围内的操作次数；不解释意图、优劣或收益归因份额。",
            ))
    status = "unavailable" if fatal else "partially_comparable" if reasons else "comparable"
    digest = hashlib.sha256(canonical_json_bytes(json_value((METHOD_ID, a, b)))).hexdigest()
    return SameStockComparison(
        "compare_" + digest, METHOD_ID, METHOD_VERSION, status, tuple(reasons), min(a.as_of, b.as_of),
        a, b, None if fatal else start, None if fatal else end,
        () if fatal else observations, () if fatal else _shape(a), () if fatal else _shape(b),
        tuple(differences),
    )
