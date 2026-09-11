"""Versioned, receipt-scoped answer composition; no new financial computation.

The model selects focus and ordered findings, not numbers or causal assertions.
Each finding carries its exact horizon and immutable supporting record. V1
ClaimOptions and verification remain authoritative for motive interpretations.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Literal

import pandas as pd
from pydantic import Field, create_model

from src.agents.claim_contract import ReviewVerificationError, scope_of

VERSION = "question_driven_review_answer_v2"
Focus = Literal["result_formation", "operation_impact", "decision_reason", "available_facts"]
LOCAL = "omit_event_until_next_decision_v2"
FULL = "omit_event_preserve_later_executions_v1"


def text(zh, en):
    return {"zh": zh, "en": en}


def money(value, currency):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReviewVerificationError("answer_invalid_financial_value")
    return f"{value:,.2f} {currency}"


def date(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ReviewVerificationError("answer_missing_observation_date")
    return timestamp.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Finding:
    option_id: str
    kind: str
    evidence_ref: str
    decision_id: str | None
    title: dict
    body: dict
    qualification: dict
    # Direction of the existing CF-minus-actual field; no new attribution score.
    difference_direction: str | None = None


def finding(record, kind, title, body, qualification, decision_id=None, direction=None):
    content = [VERSION, scope_of(record), record.ref, kind, title, body, qualification, decision_id]
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return Finding("finding_" + digest, kind, record.ref, decision_id, title, body, qualification, direction)


def build_answer_options(context):
    """Only completed receipts within the own Episode admit answer findings.

    An infeasible scenario admits an explanation of infeasibility, never a PnL.
    Unread, foreign, unsupported and incomplete results cannot become findings.
    """
    own = scope_of(context.own.episode)
    records = {r.ref: r for r in context.records.values()
               if r.ref in context.retrieved and scope_of(r) == own}
    decisions = {r.value["decision_event_id"]: r for r in records.values()
                 if r.kind == "decision" and r.availability == "complete"}
    findings = []
    for r in sorted(records.values(), key=lambda r: r.ref):
        v = r.value
        if r.kind == "decision" and r.availability == "complete":
            action = {"open_position": ("建仓", "Opening"), "add_position": ("加仓", "Addition"),
                      "reduce_position": ("减仓", "Reduction"), "close_position": ("退出", "Exit")}.get(v["event_type"])
            if action is None:
                continue
            before, after = v["before"]["quantity"], v["after"]["quantity"]
            when = date(v["event_time"])
            findings.append(finding(r, "operation", text(f"{when} · {action[0]}", f"{when} · {action[1]}"),
                text(f"记录持仓从 {before:g} 股变为 {after:g} 股。", f"Recorded quantity changed from {before:g} to {after:g} shares."),
                text("这是持仓数量变化，不是账户权重或操作动机。", "This is quantity, not account weight or a motive."),
                v["decision_event_id"]))
        if r.kind != "historical_comparison" or v.get("scenario_id") not in {LOCAL, FULL}:
            continue
        decision_id = v.get("decision_event_id")
        if decision_id not in decisions:
            continue  # A comparison must navigate to a successfully read operation.
        when = date(v["decision_at"])
        if r.availability == "infeasible_downstream_execution" and v["scenario_id"] == FULL:
            findings.append(finding(r, "infeasible_comparison",
                text(f"{when} · 保留后续操作的假设不成立", f"{when} · Keeping later executions is infeasible"),
                text("取消这次操作后，后续原数量成交无法全部合法重放，因此没有这个假设的整轮结果。",
                     "Omitting this operation makes the unchanged later executions infeasible, so this alternative has no full-period result."),
                text("不会自动缩减或删除后续成交来生成结果。", "Later executions are not resized or removed to manufacture a result."), decision_id))
            continue
        if r.availability != "complete":
            continue
        actual, alternative = v.get("actual_result"), v.get("counterfactual_result")
        comparison = v.get("comparison", {})
        if not actual or not alternative or comparison.get("comparison_status") != "complete":
            raise ReviewVerificationError("answer_incomplete_comparison")
        a, b = money(actual["pnl"], r.currency), money(alternative["pnl"], r.currency)
        diff = comparison["pnl_difference"]
        delta = money(diff, r.currency)
        relation = text("在这项固定假设中，取消操作的结果更高。" if diff > 0 else "在这项固定假设中，保留操作的实际结果更高。" if diff < 0 else "在这项固定假设中，两种结果一致。",
                        "In this fixed alternative, omitting the operation gives the higher result." if diff > 0 else "In this fixed alternative, keeping the operation gives the higher result." if diff < 0 else "The two results match in this fixed alternative.")
        if v["scenario_id"] == LOCAL:
            mark = v.get("valuation_observation_date")
            end = v.get("next_decision_at") or v["evaluation_end"]
            if (v.get("scenario_version") != "2" or not mark
                or actual.get("valuation_at") != mark or alternative.get("valuation_at") != mark
                or pd.Timestamp(mark).normalize() >= pd.Timestamp(end).normalize()):
                raise ReviewVerificationError("answer_invalid_prior_mark")
            horizon = date(end)
            boundary = "下一次操作" if v.get("next_decision_at") else "分析截止"
            boundary_en = "next execution" if v.get("next_decision_at") else "analysis cutoff"
            title = text(f"{when} · 取消这次操作的局部对比", f"{when} · Local omission comparison")
            body = text(f"{relation['zh']}截至 {horizon} {boundary}边界前，统一按 {date(mark)} 市场价估值：实际结果 {a}；取消这次操作为 {b}；假设减实际的差额为 {delta}。",
                        f"{relation['en']} Before the {horizon} {boundary_en} boundary, both use the {date(mark)} daily mark: actual {a}; omitting this operation {b}; alternative minus actual {delta}.")
            qualification = text("这是截至该点的局部账面比较，不是从该操作日起的损益，也不是整轮损益拆分。取消该笔及其记录费用，下一次及后续操作不纳入；前序日价格不是盘中报价。",
                                 "These are results marked at that cutoff, not PnL since this operation or a decomposition of the final outcome. The operation and its recorded fee are omitted; next and later operations are excluded. The prior daily mark is not an intraday quote.")
            kind = "local_comparison"
        else:
            title = text(f"{when} · 保留后续成交的历史对比", f"{when} · Historical comparison keeping later executions")
            a_kind = "已实现" if actual["result_kind"] == "realized" else "账面估值"
            a_kind_en = "realized" if actual["result_kind"] == "realized" else "marked"
            b_kind = "已平仓" if alternative["position_status"] == "closed" else "未平仓估值"
            b_kind_en = "closed" if alternative["position_status"] == "closed" else "open, marked"
            body = text(f"截至 {date(v['evaluation_end'])}：实际{a_kind}结果 {a}；取消该操作并保留后续原成交，假设结果 {b}（{b_kind}）；假设减实际为 {delta}。",
                        f"At {date(v['evaluation_end'])}: actual {a_kind_en} result {a}; omitting this operation with later executions unchanged gives {b} ({b_kind_en}); alternative minus actual {delta}.")
            qualification = text("后续成交的时间、方向、数量、价格与记录费用保持不变。这是注册历史假设，不代表当时应该这样做，也不是未来预测。",
                                 "Later times, sides, quantities, prices and recorded fees remain unchanged. This is a registered historical alternative, not advice or a forecast.")
            kind = "full_comparison"
        findings.append(finding(r, kind, title, body, qualification, decision_id,
                                "positive" if diff > 0 else "negative" if diff < 0 else "zero"))
    return tuple(findings)


def required_answer_focus(question):
    """Keep the product's explicit whole-Episode starter on its stated task.

    This is not a general keyword classifier: free-form and specific-operation
    questions retain the existing model selection. Normalize punctuation/space
    only, so a known starter cannot accidentally become an unrelated focus.
    """
    def normalized(value):
        return "".join(c for c in value.casefold() if c.isalnum())
    starters = (
        "这轮结果是怎样形成的，哪些操作值得回看？",
        "How did this result develop, and which operations deserve a closer look?",
        "这轮结果是怎样形成的？",
    )
    return "result_formation" if normalized(question) in {normalized(s) for s in starters} else None


def answer_choice_type(base, options, *, required_focus=None):
    if required_focus not in {None, "result_formation"}:
        raise ValueError("unsupported_required_answer_focus")
    ids = tuple(o.option_id for o in options)
    return create_model("ReviewAnswerChoiceV2", __base__=base,
        answer_focus=(Literal["result_formation"] if required_focus else Focus, ...),
        finding_option_ids=(list[Literal[ids]] if ids else list[str],
                            Field(min_length=1 if ids else 0, max_length=min(3, len(ids)))))


def compose_answer(choice, options, selection, context):
    """Strict versioned projection after the original receipt and claim gates.

    Scope is checked again at rendering; no free prose or caller-supplied amounts
    are accepted. Preserve model ordering (relevance), not hash ordering.
    """
    by_id = {o.option_id: o for o in options}
    ids = choice.finding_option_ids
    if len(ids) != len(set(ids)) or any(i not in by_id for i in ids):
        raise ReviewVerificationError("invalid_answer_option_selection")
    selected = [by_id[i] for i in ids]
    # Rebuild to ensure immutable options still match the authorized facts.
    fresh = {o.option_id: o for o in build_answer_options(context)}
    if any(fresh.get(o.option_id) != o for o in selected):
        raise ReviewVerificationError("answer_option_changed_or_unread")
    local = [o for o in options if o.kind == "local_comparison"]
    if choice.answer_focus == "result_formation" and local:
        directions = {o.difference_direction for o in local} & {"positive", "negative"}
        picked = {o.difference_direction for o in selected if o.kind == "local_comparison"}
        if not directions <= picked:
            raise ReviewVerificationError("answer_relevant_comparison_or_counterexample_missing")
    if choice.answer_focus == "operation_impact" and any(o.kind.endswith("comparison") for o in options):
        if not any(o.kind.endswith("comparison") for o in selected):
            raise ReviewVerificationError("answer_comparison_required")
        selected_decisions = {o.decision_id for o in selected if o.kind == "local_comparison"}
        needed = {o.option_id for o in options if o.kind == "infeasible_comparison" and o.decision_id in selected_decisions}
        if not needed <= set(ids):
            raise ReviewVerificationError("answer_full_horizon_infeasibility_missing")
    summary_record = context.records[context.own.outcome.outcome_id]
    if summary_record.ref not in context.retrieved or summary_record.ref not in selection.factual_refs:
        raise ReviewVerificationError("answer_summary_not_audited")
    result = summary_record.value["result"]
    amount = money(result["pnl"], summary_record.currency)
    marked = result["result_kind"] == "marked"
    when = (result.get("valuation_at") if marked else context.own.episode.closed_at) or context.own.as_of
    summary = text(f"截至 {date(when)}，本轮{'账面估值' if marked else '最终实现'}结果为 {amount}。",
                   f"At {date(when)}, this investment's {'marked' if marked else 'realized'} result is {amount}.")
    comparison_summary = []
    if context.comparison_id:
        # Required counterpart outcomes remain visible, without treating their
        # own full-period returns as a common-window ranking or own-account facts.
        for ref in selection.factual_refs:
            r = context.records[ref]
            if r.kind != "episode" or scope_of(r) == scope_of(context.own.episode):
                continue
            if scope_of(r) not in context.authorized_scopes or ref not in context.retrieved:
                raise ReviewVerificationError("answer_counterpart_not_authorized")
            ep, value = r.value["episode"], r.value["result"]
            other_amount = money(value["pnl"], r.currency)
            start = date(ep["opened_at"])
            end = date(value.get("valuation_at") or ep.get("closed_at") or r.as_of)
            kind = "账面估值" if value["result_kind"] == "marked" else "已实现"
            kind_en = "marked" if value["result_kind"] == "marked" else "realized"
            comparison_summary.append(text(
                f"获授权对方这轮（{start} 至 {end}）的{kind}结果为 {other_amount}。双方数值对应各自投资期间，不是共同区间的收益排名，也不构成复制操作的依据。",
                f"The authorized counterpart's {start}–{end} investment has a {kind_en} result of {other_amount}. These are each investment's own periods, not a common-window return ranking or a basis for copying trades."))
    # Findings add references to existing audit payloads, not alternative results
    # to factual_refs. Infeasibility remains separate, with no numerical result.
    qualification = text("以下是本次选出的相关记录与历史假设，不是完整的损益归因；不同区间的差额不能相加。",
                         "These are selected records and historical alternatives, not a complete PnL attribution; differences across horizons cannot be added.")
    if choice.answer_focus == "available_facts":
        qualification = text("本轮可核对的是操作记录与注册历史对比；不据此推断账户权重、行业穿透或完整风险。",
                             "This review supports recorded operations and registered alternatives, not account weights, industry look-through or total risk.")
    return {"version": VERSION, "focus": choice.answer_focus, "summary": summary,
            "comparison_summary": comparison_summary,
            "findings": [asdict(o) for o in selected], "qualification": qualification}


def can_correct_answer(error):
    # Only selection completeness/duplication: never financial or scope repair.
    return error.issue.code in {"answer_relevant_comparison_or_counterexample_missing",
        "answer_comparison_required", "answer_full_horizon_infeasibility_missing"}


def include_answer_refs(choice, options, selection, context):
    """Union all supporting refs without truncating evidence to a display budget.

    The caller still runs validate_finalization and compose_answer afterwards:
    receipt, scope, type, counter-material and canonical-content checks remain.
    """
    by_id = {o.option_id: o for o in options}
    facts, history = list(dict.fromkeys(selection.factual_refs)), list(dict.fromkeys(selection.historical_comparison_refs))
    if len(choice.finding_option_ids) != len(set(choice.finding_option_ids)):
        raise ReviewVerificationError("invalid_answer_option_selection")
    for option_id in choice.finding_option_ids:
        if option_id not in by_id:
            raise ReviewVerificationError("invalid_answer_option_selection")
        ref = by_id[option_id].evidence_ref
        if ref not in context.retrieved or ref not in context.records:
            raise ReviewVerificationError("unretrieved_or_unknown_evidence")
        r = context.records[ref]
        if scope_of(r) != scope_of(context.own.episode):
            raise ReviewVerificationError("evidence_scope_mismatch")
        if r.kind == "historical_comparison" and r.availability != "complete":
            continue
        refs = history if r.kind == "historical_comparison" else facts
        if r.ref not in refs:
            refs.append(r.ref)
    return type(selection).model_validate(selection.model_dump() | {
        "factual_refs": facts, "historical_comparison_refs": history})
