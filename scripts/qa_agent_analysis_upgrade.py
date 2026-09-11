"""Bounded live QA for the DSA account-analysis upgrade.

The harness always uses the registered Synthetic showcase account.  Each turn
has one 150-second deadline.  Public
research is limited to explicit listed-security questions.  It never opens a
real account repository, submits an order, or writes a production chat archive.

Examples::

    python scripts/qa_agent_analysis_upgrade.py --case synthetic --keychain
    python scripts/qa_agent_analysis_upgrade.py --case technical600519
    python scripts/qa_agent_analysis_upgrade.py --case all --skip-research --keychain

Without ``--keychain``, ``DEEPSEEK_API_KEY`` and (optionally)
``BOCHA_API_KEY`` are read from the current process environment.  Credentials
remain process-local and are replaced exactly if they ever occur in stdout.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from time import monotonic
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


MODEL_SERVICE = "com.toujing.desktop.model-service"
CASE_TIMEOUT_SECONDS = 150

CASE_ORDER = (
    "episode_result",
    "hypothetical_fee",
    "period_dates",
    "same_stock",
    "technical600519",
    "financial600519",
    "bocha_news",
    "knowledge_followup",
)
GROUPS = {
    "all": CASE_ORDER,
    "synthetic": (
        "episode_result", "hypothetical_fee", "period_dates", "same_stock",
        "knowledge_followup",
    ),
    "owned": ("episode_result", "hypothetical_fee", "period_dates", "same_stock"),
    "research": ("technical600519", "financial600519", "bocha_news"),
    "public": ("technical600519", "financial600519", "bocha_news"),
    "knowledge": ("knowledge_followup",),
}
RESEARCH_CASES = frozenset({"technical600519", "financial600519", "bocha_news"})
EXPECTED_TOOLS = {
    "episode_result": frozenset({"get_investment_details"}),
    "hypothetical_fee": frozenset({"get_hypothetical_trade_impact"}),
    "period_dates": frozenset({"get_owned_period_comparison"}),
    "same_stock": frozenset({"get_owned_same_stock_comparison"}),
    "technical600519": frozenset({"read_public_technical_indicators"}),
    "financial600519": frozenset({"read_public_financials"}),
    "bocha_news": frozenset({"search_public_web"}),
    "knowledge_followup": frozenset({"read_financial_concept"}),
}
PUBLIC_TOOL_NAMES = frozenset({
    "identify_public_security",
    "read_public_daily_ohlcv",
    "read_public_quote_snapshot",
    "read_public_technical_indicators",
    "read_public_financials",
    "search_public_web",
})
QA_FAILURE_CODES = frozenset({
    "fixed_showcase_growth_episode_count_changed",
    "fixed_showcase_growth_episodes_are_not_non_overlapping",
    "fixed_showcase_episode_alias_missing",
    "fixed_showcase_episode_detail_missing",
    "fixed_showcase_episode_expected_result_changed",
    "unknown_qa_case",
    "answer_was_not_grounding_verified",
    "verified_answer_missing",
    "verified_chinese_answer_missing",
    "expected_analysis_tool_not_executed",
    "synthetic_case_used_public_research",
    "episode_answer_did_not_cover_whole_loss_episode",
    "fee_clarification_or_explicit_zero_missing",
    "period_clarification_missing",
    "non_overlapping_same_stock_limitation_missing",
    "public_structured_record_missing",
    "completed_daily_indicators_missing",
    "technical_indicator_value_missing",
    "period_result_missing",
    "episode_price_path_misstated",
    "financial_statement_answer_missing",
    "knowledge_followup_did_not_reread_registered_knowledge",
    "temporary_archive_roundtrip_failed",
})


class QACheckError(RuntimeError):
    """A fixed local QA assertion; its details are deliberately not emitted."""


class QASkip(RuntimeError):
    """A bounded case cannot run because its optional public source is absent."""


def _keychain(account: str) -> str | None:
    result = subprocess.run(
        [
            "/usr/bin/security", "find-generic-password", "-s", MODEL_SERVICE,
            "-a", account, "-w",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _credentials(use_keychain: bool) -> tuple[str | None, str | None]:
    if use_keychain:
        return _keychain("deepseek"), _keychain("bocha")
    return os.environ.get("DEEPSEEK_API_KEY") or None, os.environ.get("BOCHA_API_KEY") or None


def _redacted_json(payload: dict[str, Any], secrets: tuple[str | None, ...]) -> str:
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _emit(
    case: str,
    status: str,
    elapsed: float,
    tools: list[str],
    answer_zh: list[str],
    sources: list[dict[str, Any]],
    secrets: tuple[str | None, ...],
    failure: dict[str, Any] | None = None,
    qa_unverified_candidate: dict[str, Any] | None = None,
    qa_retention_summary: dict[str, Any] | None = None,
) -> None:
    # Keep live stdout deliberately narrow: no prompts, raw records, refs,
    # provider payloads, exceptions, diagnostics, or credentials.
    payload = {
        "case": case,
        "status": status,
        "elapsed_seconds": round(max(0.0, elapsed), 3),
        "tools": sorted(set(tools)),
        "answer_zh": answer_zh,
        "sources": sources,
        "failure": failure,
    }
    if qa_unverified_candidate is not None:
        payload["qa_unverified_candidate"] = qa_unverified_candidate
    if qa_retention_summary is not None:
        payload["qa_retention_summary"] = qa_retention_summary
    print(_redacted_json(payload, secrets), flush=True)


def _safe_failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, QACheckError):
        code = str(exc)
        return {
            "code": code if code in QA_FAILURE_CODES else "qa_assertion_failed",
            "stage": "qa_assertion",
            "correction_attempt": 0,
        }
    from src.agents.review_diagnostics import safe_failure

    diagnostic = safe_failure(exc)
    result = {
        "code": diagnostic["code"],
        "stage": diagnostic["stage"],
        "correction_attempt": diagnostic["correction_attempt"],
    }
    # These fields have already passed the production diagnostic allowlist.
    # Never add exception prose, provider bodies, inputs or candidate text here.
    for field in ("finalizer_failure_kind", "finalizer_failure_fields",
                  "finalizer_failure_paths", "finalizer_failure_types",
                  "finalizer_format_attempt"):
        value = diagnostic.get(field)
        if value is not None and value != []:
            result[field] = value
    return result


def _candidate_summary(answer: Any, records: dict[str, Any], allowed: Any) -> dict[str, Any]:
    allowed_refs = set(allowed) if isinstance(allowed, (list, tuple, set, frozenset)) else set()
    paragraphs = []
    for paragraph in getattr(answer, "paragraphs", ())[:5]:
        refs = getattr(paragraph, "refs", ())
        cited_kinds = sorted({
            str(records[ref].get("kind"))
            for ref in refs
            if ref in allowed_refs and isinstance(records.get(ref), dict)
        })
        text = getattr(getattr(paragraph, "text", None), "zh", "")
        paragraphs.append({
            "zh": text[:600] if isinstance(text, str) else "",
            "kind": str(getattr(paragraph, "kind", ""))[:40],
            "cited_kinds": cited_kinds,
        })
    allowed_kinds = sorted({
        str(records[ref].get("kind"))
        for ref in allowed_refs
        if isinstance(records.get(ref), dict)
    })
    guide_ids = [
        str(getattr(guide, "guide_id", ""))[:80]
        for guide in getattr(answer, "guides", ())[:3]
    ]
    return {"paragraphs": paragraphs, "allowed_kinds": allowed_kinds, "guide_ids": guide_ids}


def _diagnostic_details(exc: Exception) -> dict[str, Any]:
    details = getattr(exc, "details", None)
    issues: list[str] = []
    findings: list[dict[str, Any]] = []
    guide_findings: list[dict[str, Any]] = []
    unbound: set[str] = set()
    if isinstance(details, dict):
        raw_issues = details.get("issues")
        if isinstance(raw_issues, list):
            issues = [item[:80] for item in raw_issues[:8] if isinstance(item, str)]
        for item in details.get("findings", ()) if isinstance(details.get("findings"), list) else ():
            if not isinstance(item, dict):
                continue
            problem = item.get("problem")
            findings.append({
                "paragraph_index": item.get("paragraph_index") if type(item.get("paragraph_index")) is int else None,
                "problem": problem[:320] if isinstance(problem, str) else "",
            })
            if len(findings) == 8:
                break
        for item in details.get("guide_findings", ()) if isinstance(details.get("guide_findings"), list) else ():
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            guide_findings.append({
                "guide_index": item.get("guide_index") if type(item.get("guide_index")) is int else None,
                "reason": reason[:320] if isinstance(reason, str) else "",
            })
            if len(guide_findings) == 3:
                break
    candidates = details if isinstance(details, list) else ()
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get("unbound_number_tokens"), list):
            continue
        for token in item["unbound_number_tokens"]:
            if isinstance(token, str) and len(token) <= 40:
                unbound.add(token)
    return {
        "issues": issues,
        "findings": findings,
        "guide_findings": guide_findings,
        "unbound_number_tokens": sorted(unbound)[:24],
    }


def _diagnostic_reason_code(exc: Exception) -> str:
    code = str(exc)
    return code if re.fullmatch(r"[a-z0-9_]{1,80}", code) else "validation_rejected"


def _retention_summary(capture: dict[str, Any]) -> dict[str, Any] | None:
    rejected = capture.get("rejected_candidates")
    if not isinstance(rejected, list) or not rejected:
        return None
    codes = sorted({item.get("reason_code") for item in rejected if isinstance(item, dict)
                    and isinstance(item.get("reason_code"), str)})[:8]
    return {"rejected_candidate_count": len(rejected), "reason_codes": codes}


def _misstates_explicit_price_path(text: str) -> bool:
    """Reject a monotonic-down claim contradicted by its own explicit 3-point path."""
    if not any(token in text for token in ("逐级走低", "持续走低", "一路走低", "连续走低", "每次都更低")):
        return False
    for match in re.finditer(r"(-?\d+(?:\.\d+)?)\s*(?:→|->)\s*(-?\d+(?:\.\d+)?)\s*(?:→|->)\s*(-?\d+(?:\.\d+)?)", text):
        values = [float(value) for value in match.groups()]
        if not (values[0] > values[1] > values[2]):
            return True
    return False


@contextmanager
def _capture_diagnostics(enabled: bool, capture: dict[str, Any]):
    if not enabled:
        yield
        return
    import src.agents.account_conversation as conversation_module

    original = conversation_module.validate_answer

    def wrapped(answer: Any, records: dict[str, Any], allowed: Any):
        # Candidate text is retained in-process only if this attempt fails, so a
        # later successful repair can report only counts/reason codes. No record
        # values, refs, receipts, prompts, or provider responses are captured.
        candidate = _candidate_summary(answer, records, allowed)
        try:
            outcome = original(answer, records, allowed)
            # Do not let a rejected pre-repair text leak if a later candidate
            # validates and the case subsequently fails at another QA stage.
            capture.pop("candidate", None)
            capture.pop("validation_details", None)
            return outcome
        except Exception as exc:
            capture["candidate"] = candidate
            capture["validation_details"] = _diagnostic_details(exc)
            capture.setdefault("rejected_candidates", []).append({
                "paragraph_count": len(candidate.get("paragraphs", ())),
                "reason_code": _diagnostic_reason_code(exc),
            })
            raise

    conversation_module.validate_answer = wrapped
    try:
        yield
    finally:
        conversation_module.validate_answer = original


def _failure_candidate(capture: dict[str, Any], exc: Exception) -> dict[str, Any] | None:
    candidate = capture.get("candidate")
    if not isinstance(candidate, dict):
        return None
    details = _diagnostic_details(exc)
    validation = capture.get("validation_details")
    if isinstance(validation, dict):
        details = {
            "issues": list(dict.fromkeys([*details["issues"], *validation.get("issues", [])]))[:8],
            "findings": (details["findings"] or validation.get("findings", []))[:8],
            "guide_findings": (details["guide_findings"] or validation.get("guide_findings", []))[:3],
            "unbound_number_tokens": sorted(set(
                [*details["unbound_number_tokens"], *validation.get("unbound_number_tokens", [])]
            ))[:24],
        }
    return {**candidate, "failure_details": details, "trust": "qa_unverified_not_product_output"}


def _selected_cases(values: list[str] | None) -> tuple[str, ...]:
    requested = values or ["all"]
    expanded: set[str] = set()
    for value in requested:
        for token in (item.strip() for item in value.split(",")):
            if token in GROUPS:
                expanded.update(GROUPS[token])
            elif token in CASE_ORDER:
                expanded.add(token)
            else:
                raise ValueError("unknown_qa_case")
    return tuple(item for item in CASE_ORDER if item in expanded)


def _account_params() -> dict[str, str]:
    from src.demo import showcase

    return {
        "scope_kind": "account",
        "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID,
        "data_mode": "synthetic_showcase",
    }


def _growth_episodes(account_context: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve both SYN_GROWTH episodes only from the fixed built context."""
    from src.demo import showcase

    rows: list[dict[str, Any]] = []
    for record in account_context.records.values():
        if record.kind == "episode_index" and isinstance(record.value, dict):
            rows.extend(item for item in record.value.get("episodes", ()) if isinstance(item, dict))
    target_name = showcase.NAMES["SYN_GROWTH"]["en"]
    selected = sorted(
        (item for item in rows if item.get("display_name") == target_name),
        key=lambda item: str(item.get("opened_at", "")),
    )
    if len(selected) != 2:
        raise QACheckError("fixed_showcase_growth_episode_count_changed")
    earlier, later = selected
    if (
        earlier.get("status") != "closed"
        or not isinstance(earlier.get("closed_at"), str)
        or str(earlier["closed_at"]) >= str(later.get("opened_at", ""))
    ):
        raise QACheckError("fixed_showcase_growth_episodes_are_not_non_overlapping")
    resolved = []
    for item in selected:
        canonical = item.get("episode_id")
        display = account_context.episode_display_ids.get(canonical)
        if not isinstance(canonical, str) or not isinstance(display, str):
            raise QACheckError("fixed_showcase_episode_alias_missing")
        # Never amend record.value in place: refs bind the exact registered
        # projection.  The display alias is harness-local query metadata.
        resolved.append({**item, "display_episode_id": display})
    return resolved[0], resolved[1]


def _episode_context(service: Any, account_context: Any, earlier: dict[str, Any]) -> Any:
    params = {
        **_account_params(),
        "scope_kind": "episode",
        "episode_id": earlier["display_episode_id"],
    }
    focused = service._source(params)
    details = [
        record.value for record in focused.conversation_records.values()
        if record.kind == "episode_detail" and isinstance(record.value, dict)
    ]
    if len(details) != 1:
        raise QACheckError("fixed_showcase_episode_detail_missing")
    result = details[0].get("result")
    operations = details[0].get("operation_counts")
    if (
        not isinstance(result, dict)
        or result.get("pnl") != -630.0
        or result.get("result_sign") != "loss"
        or not isinstance(operations, dict)
        or operations.get("open_position") != 1
        or operations.get("close_position") != 1
    ):
        raise QACheckError("fixed_showcase_episode_expected_result_changed")
    return focused


def _questions(case: str, earlier: dict[str, Any], later: dict[str, Any]) -> tuple[str, ...]:
    if case == "episode_result":
        return ("这轮结果是怎样形成的，哪些操作值得回看？",)
    if case == "hypothetical_fee":
        return (
            "假设买入 SYN_GROWTH 300 股，成交价 14.4，账户会怎样变化？",
            "沿用上一笔拟交易，费用明确按 0 元计算。",
        )
    if case == "period_dates":
        return (
            "请比较我前后两个时期的账户表现。",
            "明确比较：较早区间为 2025-01-01 至 2025-06-30，较晚区间为 2025-07-01 至 2025-12-31。",
        )
    if case == "same_stock":
        return (
            "请比较我账户中这两轮同股投资：较早轮次 "
            f"{earlier['display_episode_id']}，较晚轮次 {later['display_episode_id']}。"
            "两轮时间不重叠；只比较我自己的已登记记录，不引入同伴或专业账户。",
        )
    if case == "technical600519":
        return (
            "请读取 SHSE:600519 在 2026-01-01 至 2026-09-09 的已完成日线技术指标，"
            "使用前复权；保留指标参数、预热与数据状态，不给买卖信号。",
        )
    if case == "financial600519":
        return (
            "请读取 SHSE:600519 当前能取得的公开结构化财报，区分利润表、资产负债表、"
            "现金流量表和指标的报告期与单位，不用新闻代替缺失报表。",
        )
    if case == "bocha_news":
        return (
            "请用公开网页搜索贵州茅台最近一个月发生的公司新闻，"
            "注明发布日期和可点来源；"
            "不要把公开新闻说成我的持仓或账户事实。",
        )
    if case == "knowledge_followup":
        return (
            "K线实体和影线分别是什么？",
            "那成交量应该怎样和刚才的实体、影线一起看？",
        )
    raise QACheckError("unknown_qa_case")


def _conversation_history(turns: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    if not turns:
        return None
    return {
        "trust": "untrusted_not_evidence",
        "purpose": "resolve_references_in_current_question_only",
        "history": [
            {"user_question": question, "validated_structured_answer": result["answer"]}
            for question, result in turns[-3:]
        ],
    }


async def _run_turn(question: str, context: Any, runtime: Any, history: dict[str, Any] | None) -> dict[str, Any]:
    from src.agents.dsa_conversation import run_dsa_conversation

    return await asyncio.wait_for(
        run_dsa_conversation(
            question,
            context,
            runtime=runtime,
            conversation_context=history,
        ),
        timeout=CASE_TIMEOUT_SECONDS,
    )


def _verified_zh(result: dict[str, Any]) -> list[str]:
    if result.get("verification") != "receipts_and_grounding_review_v1":
        raise QACheckError("answer_was_not_grounding_verified")
    paragraphs = result.get("answer", {}).get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        raise QACheckError("verified_answer_missing")
    answer = []
    for paragraph in paragraphs:
        zh = paragraph.get("text", {}).get("zh") if isinstance(paragraph, dict) else None
        if not isinstance(zh, str) or not zh.strip():
            raise QACheckError("verified_chinese_answer_missing")
        answer.append(zh.strip())
    return answer


def _public_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = ("title", "url", "site_name", "published_at", "retrieved_at", "provider", "adjust")
    sources, seen = [], set()
    for result in results:
        for source in result.get("public_sources") or []:
            if not isinstance(source, dict):
                continue
            safe = {key: source.get(key) for key in allowed}
            url = safe.get("url")
            if url is not None and not (isinstance(url, str) and url.startswith(("https://", "http://"))):
                safe["url"] = None
            identity = json.dumps(safe, sort_keys=True, ensure_ascii=False)
            if identity not in seen:
                sources.append(safe)
                seen.add(identity)
            if len(sources) == 6:
                return sources
    return sources


def _fallback_source(case: str) -> list[dict[str, Any]]:
    from src.demo import showcase

    if case == "knowledge_followup":
        return [{
            "title": "Toujing registered financial knowledge",
            "url": None,
            "site_name": "local registered method",
            "published_at": None,
            "retrieved_at": None,
            "provider": "toujing_method_knowledge_v1",
            "adjust": None,
        }]
    return [{
        "title": "Toujing Synthetic showcase",
        "url": None,
        "site_name": "fixed local showcase",
        "published_at": (showcase.AS_OF.isoformat()
                         if hasattr(showcase.AS_OF, "isoformat") else str(showcase.AS_OF)),
        "retrieved_at": None,
        "provider": showcase.VERSION,
        "adjust": None,
    }]


def _validate_case(case: str, results: list[dict[str, Any]], answers_by_turn: list[list[str]]) -> None:
    tools = {tool for result in results for tool in result.get("executed_tools", ())}
    if not EXPECTED_TOOLS[case] <= tools:
        raise QACheckError("expected_analysis_tool_not_executed")
    if case not in RESEARCH_CASES and tools & PUBLIC_TOOL_NAMES:
        raise QACheckError("synthetic_case_used_public_research")
    if case == "episode_result":
        text = "".join(answers_by_turn[0])
        if "630" not in text or not any(token in text for token in ("建仓", "买入", "加仓")) or not any(
            token in text for token in ("卖出", "减仓", "清仓", "退出")
        ):
            raise QACheckError("episode_answer_did_not_cover_whole_loss_episode")
        if _misstates_explicit_price_path(text):
            raise QACheckError("episode_price_path_misstated")
    elif case == "hypothetical_fee":
        first, second = "".join(answers_by_turn[0]), "".join(answers_by_turn[1])
        first_tools = set(results[0].get("executed_tools", ()))
        second_tools = set(results[1].get("executed_tools", ()))
        if (
            "get_hypothetical_trade_impact" not in first_tools
            or "get_hypothetical_trade_impact" not in second_tools
            or "费" not in first
            or not any(token in second for token in ("0", "零"))
        ):
            raise QACheckError("fee_clarification_or_explicit_zero_missing")
    elif case == "period_dates":
        first, second = "".join(answers_by_turn[0]), "".join(answers_by_turn[1])
        first_tools = set(results[0].get("executed_tools", ()))
        second_tools = set(results[1].get("executed_tools", ()))
        if (
            "get_owned_period_comparison" in first_tools
            or "get_owned_period_comparison" not in second_tools
            or not any(token in first for token in ("日期", "区间", "期间", "时间"))
        ):
            raise QACheckError("period_clarification_missing")
        # The confirmation turn must contain an actual period result, not just
        # repeat the requested dates or report that comparison is unavailable.
        if not (re.search(r"2025[-年]", second) and re.search(r"[-+]?\d+(?:\.\d+)?\s*%", second)):
            raise QACheckError("period_result_missing")
    elif case == "same_stock":
        text = "".join(answers_by_turn[0])
        limitations = ("不重叠", "没有重叠", "不存在重叠", "不重合", "共同区间", "不可比", "无法比较", "不足", "不能视为同区间")
        if not any(token in text for token in limitations):
            raise QACheckError("non_overlapping_same_stock_limitation_missing")
    elif case in {"technical600519", "financial600519"}:
        if not any(result.get("public_read_refs") for result in results):
            raise QACheckError("public_structured_record_missing")
        text = "".join(answers_by_turn[0])
        if case == "technical600519":
            labels = r"(?:SMA|EMA|MACD|RSI|ATR|量比|均线)"
            # A parameter such as RSI(14) is not an output. Require a result
            # expression with an assignment/separator and a numeric value.
            indicator_value = re.compile(
                labels + r"[^。；;\n]{0,32}?(?:为|是|约|[:：=])\s*[-+]?\d+(?:\.\d+)?%?",
                re.I,
            )
            has_date = bool(re.search(r"20\d{2}[-年]\d{1,2}(?:[-月]\d{1,2})?", text))
            if not ("600519" in text and has_date and indicator_value.search(text)):
                raise QACheckError("technical_indicator_value_missing")
        if case == "financial600519" and not any(
            token in text for token in ("利润表", "资产负债表", "现金流", "报告期")
        ):
            raise QACheckError("financial_statement_answer_missing")
    elif case == "knowledge_followup":
        if any("read_financial_concept" not in set(result.get("executed_tools", ())) for result in results):
            raise QACheckError("knowledge_followup_did_not_reread_registered_knowledge")


def _archive_roundtrip(scope: dict[str, Any], turns: list[tuple[str, dict[str, Any]]]) -> None:
    """Exercise only a temporary validated archive; never discover a real path."""
    from toujing_core_runtime.chat_archive import ChatArchive

    completed: dict[str, dict[str, Any]] = {}
    history: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="toujing-agent-analysis-qa-") as directory:
        archive = ChatArchive(Path(directory) / "synthetic.agent-chat.sqlite3")
        for index, (question, result) in enumerate(turns):
            key = f"account_inference_qa_{index}"
            stored_result = copy.deepcopy(result)
            stored_result.update(scope=copy.deepcopy(scope), inference_id=key, invalidated=False)
            completed[key] = {
                "scope": copy.deepcopy(scope),
                "source_fingerprint": "fixed-synthetic-qa",
                "question": question,
                "history": copy.deepcopy(history),
                "result": stored_result,
            }
            history.append({"user_question": question, "validated_structured_answer": copy.deepcopy(result["answer"])})
        archive.save(scope, completed)
        restored = archive.read(scope)
        last = f"account_inference_qa_{len(turns) - 1}"
        if restored.get(last, {}).get("result", {}).get("answer") != turns[-1][1].get("answer"):
            raise QACheckError("temporary_archive_roundtrip_failed")


async def _run_case(
    case: str,
    runtime: Any,
    bocha_key: str | None,
    diagnostic_capture: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    from src.agents.public_research import attach_public_research, reset_public_caches
    from toujing_core_runtime.account_review import AccountReviewService

    service = AccountReviewService(SimpleNamespace())
    try:
        account_context = service._source(_account_params())
        earlier, later = _growth_episodes(account_context)
        context = _episode_context(service, account_context, earlier) if case == "episode_result" else account_context
    finally:
        service.close()

    reset_public_caches()
    attach_public_research(context, {
        "_desktop_search_enabled": bool(bocha_key) and case == "bocha_news",
        "_desktop_bocha_key": bocha_key if case == "bocha_news" else None,
    })
    turns: list[tuple[str, dict[str, Any]]] = []
    answers_by_turn: list[list[str]] = []
    for question in _questions(case, earlier, later):
        result = await _run_turn(question, context, runtime, _conversation_history(turns))
        turns.append((question, result))
        answers_by_turn.append(_verified_zh(result))
        if diagnostic_capture is not None:
            # Only answers already validated by the product, never raw model
            # candidates. Preserve them for manual review of a QA assertion.
            diagnostic_capture["verified_answers"] = [text for turn in answers_by_turn for text in turn]

    _validate_case(case, [result for _, result in turns], answers_by_turn)
    sources = _public_sources([result for _, result in turns])
    if case == "bocha_news" and not sources:
        raise QASkip("bocha_returned_no_records")
    if not sources:
        sources = _fallback_source(case)
    _archive_roundtrip(context.scope, turns)
    tools = sorted({tool for _, result in turns for tool in result.get("executed_tools", ())})
    answers = [text for turn in answers_by_turn for text in turn]
    return tools, answers, sources


async def _close_runtime(runtime: Any) -> None:
    client_factory = getattr(getattr(runtime, "model", None), "_get_client", None)
    if client_factory:
        await client_factory().close()


async def _main(args: argparse.Namespace) -> int:
    from src.agents.investment_coach import create_model_runtime

    selected = _selected_cases(args.case)
    model_key, bocha_key = _credentials(args.keychain)
    secrets = (model_key, bocha_key)
    failures = 0
    runtime = None
    try:
        if not model_key:
            for case in selected:
                started = monotonic()
                status = "SKIP" if args.skip_research and case in RESEARCH_CASES else "FAIL"
                answer = (["已按要求跳过公开研究案例。"] if status == "SKIP"
                          else ["未配置 DeepSeek，未执行此案例。"])
                failure = ({"code": "qa_model_not_configured", "stage": "configuration", "correction_attempt": 0}
                           if status == "FAIL" else None)
                _emit(case, status, monotonic() - started, [], answer, [], secrets, failure)
                failures += status == "FAIL"
            return 1 if failures else 0

        runtime = create_model_runtime(environment={"DEEPSEEK_API_KEY": model_key})
        for case in selected:
            started = monotonic()
            diagnostic_capture: dict[str, Any] = {}
            if args.skip_research and case in RESEARCH_CASES:
                _emit(case, "SKIP", monotonic() - started, [], ["已按要求跳过公开研究案例。"], [], secrets)
                continue
            if case == "bocha_news" and not bocha_key:
                _emit(
                    case, "SKIP", monotonic() - started, [],
                    ["未配置 Bocha，已跳过公开新闻案例。"], [], secrets,
                )
                continue
            try:
                with _capture_diagnostics(args.diagnostics, diagnostic_capture):
                    tools, answers, sources = await _run_case(
                        case,
                        runtime,
                        bocha_key,
                        diagnostic_capture if args.diagnostics else None,
                    )
                _emit(case, "PASS", monotonic() - started, tools, answers, sources, secrets,
                      qa_retention_summary=_retention_summary(diagnostic_capture) if args.diagnostics else None)
            except QASkip:
                _emit(
                    case, "SKIP", monotonic() - started, [],
                    ["Bocha 未返回可引用记录，已跳过此案例。"], [], secrets,
                )
            except Exception as exc:
                # Never expose SDK exceptions, provider bodies, raw tool payloads,
                # refs, or locally generated diagnostic text on live stdout.
                failures += 1
                failure = _safe_failure(exc)
                _emit(
                    case,
                    "FAIL",
                    monotonic() - started,
                    [],
                    (diagnostic_capture.get("verified_answers")
                     if args.diagnostics and isinstance(exc, QACheckError)
                     and diagnostic_capture.get("verified_answers") else
                     ["此案例未通过有界验证；详细错误未输出。"]),
                    [],
                    secrets,
                    failure,
                    _failure_candidate(diagnostic_capture, exc) if args.diagnostics else None,
                )
        return 1 if failures else 0
    finally:
        if runtime is not None:
            try:
                await _close_runtime(runtime)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        help=("Single case, comma-separated cases, or group: all, synthetic, owned, "
              "research/public, knowledge. May be repeated."),
    )
    parser.add_argument(
        "--keychain",
        action="store_true",
        help="Read existing deepseek/bocha desktop credentials into this process only.",
    )
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip technical, financial-statement, and Bocha cases.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help=("On failed fixed-scope cases only, emit a redacted unverified candidate "
              "summary and allowlisted validation findings."),
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        return asyncio.run(_main(args))
    except Exception:
        # Argument/configuration/setup failures get the same bounded public shape.
        _emit(
            "harness",
            "FAIL",
            0.0,
            [],
            ["QA harness 未能启动；详细错误未输出。"],
            [],
            (None, None),
            {"code": "qa_harness_start_failed", "stage": "configuration", "correction_attempt": 0},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
