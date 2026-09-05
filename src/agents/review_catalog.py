"""Scoped facts for review tools; financial values are copied, never recomputed."""

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from src.compare.same_stock import EpisodeCompareFacts, SameStockComparison
from src.presentation.runtime_episode import json_value
from src.self_baseline.core import SELF_BASELINE_METHOD_ID, SELF_BASELINE_METHOD_VERSION
from src.attribution.decision_outcome import COUNTERFACTUAL_SCENARIOS, OUTCOME_METHOD_ID, OUTCOME_METHOD_VERSION
from src.path.counterfactual import PHASE_LOCAL_SCENARIO, PHASE_STRICT_LOCAL_SCENARIO, PHASE_FULL_SCENARIO


@dataclass(frozen=True, slots=True)
class ReviewFact:
    ref: str
    kind: str
    title: str
    subject_id: str
    account_id: str
    episode_id: str
    instrument_id: str
    currency: str
    as_of: str
    method_id: str
    method_version: str
    availability: str
    underlying_refs: tuple[str, ...]
    tags: tuple[str, ...]
    value: object


@dataclass
class ReviewContext:
    own: EpisodeCompareFacts
    records: dict[str, ReviewFact]
    comparison_id: str | None
    authorized_scopes: frozenset[tuple[str, str, str, str]] = frozenset()
    retrieved: set[str] = field(default_factory=set)
    searched: set[str] = field(default_factory=set)
    access_allowed: Callable[[], bool] = field(default=lambda: True, repr=False)


def build_review_catalog(own: EpisodeCompareFacts, *, comparison: SameStockComparison | None = None,
                         self_history: object | None = None, notes: tuple[dict, ...] = (),
                         counterfactuals: tuple[dict, ...] = (), self_history_account_id: str | None = None) -> ReviewContext:
    """Caller must authorize counterpart Agent use BEFORE supplying comparison.

    Source references sharing an execution remain one underlying fact family.
    User notes are source=user, never evidence about knowledge at a past date.
    """
    e = own.episode
    if comparison and (comparison.a.episode != e or comparison.status == "unavailable"):
        raise ValueError("invalid_or_unavailable_agent_comparison")
    records: dict[str, ReviewFact] = {}
    def add(facts, ref, kind, title, value, refs, tags=(), status="complete", method=None, version="1"):
        ep = facts.episode
        if ref in records:
            # Re-importing one's own share can carry the same IDs with redacted
            # execution refs. Keep local canonical facts, never overwrite them
            # with the shared projection. Notes and foreign collisions reject.
            if (facts is not own and kind == records[ref].kind
                and (ep.subject_id, ep.account_id, ep.episode_id, ep.instrument_id)
                    == (e.subject_id, e.account_id, e.episode_id, e.instrument_id)):
                return
            raise ValueError("duplicate_review_ref")
        records[ref] = ReviewFact(ref, kind, title, ep.subject_id, ep.account_id, ep.episode_id,
                                  ep.instrument_id, facts.instrument.currency, facts.as_of.isoformat(),
                                  method or facts.outcome.method_id, version, status, tuple(refs),
                                  tuple(tags), json_value(value))
    for f in (own, comparison.b) if comparison else (own,):
        o = f.outcome
        r = o.actual_result
        add(f, o.outcome_id, "episode", "这轮投资的记录与结果", {
            "episode": json_value(f.episode), "instrument": json_value(f.instrument),
            "result": json_value(r), "pnl_display": f"{r.pnl:,.2f} {f.instrument.currency}",
            "position_return_display": None if r.return_value is None else f"{r.return_value:.2%}",
            "interpretation_boundary": "完整投资期间的 Position Return，不是资产 TWR、能力或归因份额。",
        }, o.execution_refs)
        for d in f.decisions:
            add(f, d.outcome_id, "decision", "一笔操作前后的持仓与成本", d,
                (d.execution_id,), (d.event_type,))
        for phase in f.path.phases:
            add(f, phase.phase_id, "phase", "连续操作的已记录阶段", phase,
                tuple(d.execution_id for d in f.decisions if d.decision_event_id in phase.decision_event_ids),
                (phase.phase_type,), method=f.path.method_id)
        for pattern in f.path.patterns:
            add(f, pattern.pattern_id, "path", "已有确定性路径观察", pattern,
                f.episode.execution_refs, (pattern.pattern_code,), method=f.path.method_id)
        add(f, f"market_path:{f.episode.episode_id}", "market", "记录的价格路径及持仓观察", f.path.market_path,
            f.episode.execution_refs, method=f.path.method_id)
    if comparison:
        add(own, comparison.comparison_id, "comparison", "同股可观察差异", comparison.differences,
            own.episode.execution_refs + comparison.b.episode.execution_refs,
            method=comparison.method_id)
    for cf in counterfactuals:
        registered = {**COUNTERFACTUAL_SCENARIOS, **{s.scenario_id: s for s in (
            PHASE_LOCAL_SCENARIO, PHASE_STRICT_LOCAL_SCENARIO, PHASE_FULL_SCENARIO)}}
        definition = registered.get(cf.get("scenario_id"))
        if (definition is None or cf.get("scenario_version") != definition.scenario_version
            or (cf.get("method_id"), cf.get("method_version")) != (OUTCOME_METHOD_ID, OUTCOME_METHOD_VERSION)):
            raise ValueError("unregistered_counterfactual_method")
        if (cf.get("subject_id"), cf.get("account_id"), cf.get("episode_id")) != (e.subject_id, e.account_id, e.episode_id):
            raise ValueError("counterfactual_scope_mismatch")
        if pd.Timestamp(cf["analysis_as_of"]) > own.as_of:
            raise ValueError("future_counterfactual")
        if cf.get("instrument_id") != e.instrument_id or cf.get("decision_event_id") not in e.decision_refs:
            raise ValueError("counterfactual_decision_or_instrument_mismatch")
        add(own, cf["counterfactual_id"], "historical_comparison", "固定假设下的历史比较", cf,
            e.execution_refs, status=cf["feasibility_status"], method=cf["method_id"], version=cf["method_version"])
    history = json_value(self_history) if self_history is not None else None
    if history is not None and (self_history_account_id != e.account_id or history.get("subject_id") != e.subject_id or pd.Timestamp(history["as_of"]) > own.as_of):
        raise ValueError("self_history_scope_or_time_mismatch")
    add(own, f"self_history:{e.subject_id}:{e.account_id}", "self_history", "和自己的过去相比", {
        "summary": history, "supported_metrics": ["portfolio_concentration_hhi", "mean_daily_turnover"],
        "repeated_sequence_status": "insufficient_evidence",
        "reason": "目前没有反复追涨等长期行为的正式观察合同，不能临时计数或推断长期能力。",
    }, (), status="complete" if history and history.get("available_metric_count", 0) > 0 else "insufficient_evidence",
        method=SELF_BASELINE_METHOD_ID, version=SELF_BASELINE_METHOD_VERSION)
    for note in notes:
        if (note.get("subject_id"), note.get("account_id"), note.get("episode_id")) != (e.subject_id, e.account_id, e.episode_id):
            raise ValueError("note_scope_mismatch")
        if note.get("source") != "user":
            raise ValueError("note_source_invalid")
        if note.get("note_kind") not in {"plan", "reason"}:
            raise ValueError("note_kind_invalid")
        tag = "user_plan" if note.get("note_kind") == "plan" else "user_reason"
        add(own, note["note_id"], "user_note", "用户提供的信息（并非已核实当时事实）", note,
            (note["note_id"],), (tag,), method="user_authored_note_v1")
    scopes = frozenset((f.episode.subject_id, f.episode.account_id, f.episode.episode_id, f.episode.instrument_id)
                       for f in ((own, comparison.b) if comparison else (own,)))
    return ReviewContext(own, records, comparison.comparison_id if comparison else None, scopes)
