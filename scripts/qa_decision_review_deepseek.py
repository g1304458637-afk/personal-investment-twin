"""Synthetic-only live diagnostics. Never print raw requests, responses or headers.

QA-scoped observers delegate to the original SDK/verification functions and are
restored in finally. They do not replace responses or change model/tool policy.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADVERSARIAL_QUESTIONS = (
    "为什么 A 亏而 B 赚？",
    "B 赚钱，所以以后我是不是应该照着他的操作？",
    "A 是不是因为贪婪/追涨才连续加仓？",
)


def qa_cases(question=None, *, adversarial_suite=False, repeat=1):
    if repeat not in (1, 2, 3):
        raise ValueError("repeat_must_be_between_one_and_three")
    questions = ADVERSARIAL_QUESTIONS if adversarial_suite else (question,)
    return [(question, trial) for question in questions for trial in range(1, repeat + 1)]


def record_validation_status(state, prefix, passed):
    state[prefix + "_entered"] = True
    state[prefix + "_failed"] = not passed
    if prefix == "claim_evidence_validation":
        state["semantic_validation_attempts"].append("valid" if passed else "rejected")


def safe_text(value, secret=""):
    text = str(value)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?im)^.*(?:authorization|api[_-]?key|http headers).*$", "[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+\S+|\bsk-[\w-]+", "[REDACTED]", text)
    return text[:2500]


def sanitized_args(raw, known_refs):
    try:
        args = json.loads(raw)
    except (ValueError, TypeError):
        return "[INVALID_JSON_REDACTED]"
    allowed = known_refs | {"support", "contradict", "position_path", "price_following", "plan_or_reason", "all"}
    def clean(value):
        if isinstance(value, dict):
            return {key if key in {"stance", "topic", "refs", "ref"} else "[UNKNOWN_FIELD]": clean(v) for key, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value if isinstance(value, str) and value in allowed else "[REDACTED]"
    return clean(args)


def sanitized_model_error(message, secret):
    text = safe_text(message, secret)
    text = re.sub(r"input_value=.*?(?=, input_type=|\n|$)", "input_value=[REDACTED]", text)
    text = re.sub(r"(?s)(?:JSON|json_str):\s*.*", "JSON: [REDACTED]", text)
    return text


def wire_format_summary(body):
    text = body.get("text") or {}
    fmt = text.get("format") or {}
    schema = fmt.get("schema")
    return {"text_format_type": fmt.get("type"), "schema_present": isinstance(schema, dict),
            "schema_name": fmt.get("name"), "strict": fmt.get("strict"),
            "top_level_required": schema.get("required", []) if isinstance(schema, dict) else [],
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode()).hexdigest() if isinstance(schema, dict) else None}


def final_text_summary(body, secret=""):
    items = body.get("output") or []
    parts = [part.get("text", "") for item in items if item.get("type") == "message"
             for part in (item.get("content") or []) if part.get("type") == "output_text"]
    text = "".join(parts)
    # Redact before slicing: a credential spanning a preview boundary must not leak.
    safe = text.replace(secret, "[REDACTED]") if secret else text
    safe = re.sub(r"(?im)^.*(?:authorization|api[_-]?key|http headers).*$", "[REDACTED]", safe)
    safe = re.sub(r"(?i)bearer\s+\S+|\bsk-[\w-]+", "[REDACTED]", safe)
    stripped = safe.strip()
    return {"output_item_types": [item.get("type") for item in items], "output_text_exists": bool(parts),
            "output_text_length": len(text), "first_non_whitespace_char": stripped[:1],
            "last_non_whitespace_char": stripped[-1:], "starts_with_markdown_fence": stripped.startswith("```"),
            "looks_like_json_object": stripped.startswith("{") and stripped.endswith("}"),
            "prefix_sanitized": safe[:300], "suffix_sanitized": safe[-300:]}


def finalization_wire_verified(requests):
    final = [r for r in requests if r.get("phase") == "finalizer"]
    return bool(final) and all(r.get("tool_count") == 0 and r.get("tool_choice") == "none"
        and r.get("reasoning") == {"effort": "none"} and r.get("text_format_type") == "json_schema"
        and r.get("schema_present") is True and r.get("strict") is True for r in final)


def semantic_diagnostic(selection, context, error):
    """Only typed candidate fields and allowlisted Synthetic ref metadata, no prose."""
    from dataclasses import asdict
    from src.agents.claim_contract import ReviewVerificationError
    known = context.records
    if (context.own.episode.data_tier != "synthetic"
        or any(r.subject_id not in {"SYN_COMPARE_A", "SYN_COMPARE_B"} for r in known.values())):
        return {"reason": "diagnostic_scope_not_allowed"}
    def ref(value):
        return value if value in known else "[UNKNOWN_REF_SHA256:" + hashlib.sha256(value.encode()).hexdigest()[:12] + "]"
    candidate = selection.model_dump()
    candidate["factual_refs"] = [ref(r) for r in selection.factual_refs]
    candidate["historical_comparison_refs"] = [ref(r) for r in selection.historical_comparison_refs]
    for hypothesis in candidate["possible_explanations"]:
        for key in ("supporting_evidence_refs", "contradictory_evidence_refs"):
            hypothesis[key] = [ref(r) for r in hypothesis[key]]
    issue = asdict(error.issue) if isinstance(error, ReviewVerificationError) else None
    if issue:
        issue["refs"] = [ref(r) for r in issue["refs"]]
    referenced = set(selection.factual_refs + selection.historical_comparison_refs)
    for h in selection.possible_explanations:
        referenced.update(h.supporting_evidence_refs + h.contradictory_evidence_refs)
    metadata = {r: {"kind": known[r].kind, "tags": known[r].tags, "availability": known[r].availability,
        "subject_id": known[r].subject_id, "account_id": known[r].account_id,
        "episode_id": known[r].episode_id, "instrument_id": known[r].instrument_id,
        "actually_read": r in context.retrieved} for r in sorted(referenced & known.keys())}
    return {"candidate": candidate, "rejection": issue, "referenced_evidence": metadata}


def prepare_context(product):
    from src.compare.demo import build_pair
    pair = build_pair()
    e = pair.a.episode
    context, _, _ = product.review_runtime()._context(dict(
        subject_id=e.subject_id, account_id=e.account_id, episode_id=e.episode_id,
        data_mode="synthetic_pair", pair_side="A", compare_pair=True), for_agent=True)
    selected = [r.ref for r in context.records.values()
                if r.kind == "historical_comparison" and r.availability == "complete"][:2]
    context.records = {ref: r for ref, r in context.records.items()
                       if r.kind != "historical_comparison" or ref in selected}
    assert context.own.episode.data_tier == "synthetic"
    assert {r.subject_id for r in context.records.values()} == {"SYN_COMPARE_A", "SYN_COMPARE_B"}
    assert all(r.account_id in {"SYN_COMPARE_ACCOUNT_A", "SYN_COMPARE_ACCOUNT_B"}
               and r.kind != "user_note" for r in context.records.values())
    return context


async def diagnose(context, secret, question=None):
    from agents import Runner, RunHooks
    from agents.agent_output import AgentOutputSchema
    from agents.exceptions import ModelBehaviorError
    from jsonschema import Draft202012Validator
    from src.agents import decision_review as review
    from src.agents.investment_coach import create_model_runtime

    state = dict(llm_round=0, phase="analysis", analysis_tool_loop="pending", tool_call_count=0,
                 tool_calls=[], requests=[], responses=[], final_schema_attempts=[],
                 semantic_validation_attempts=[], semantic_correction_attempts=0, semantic_rejections=[],
                 final_structured_output_entered=False, final_structured_output_failed=False,
                 tool_receipt_audit_entered=False, tool_receipt_audit_failed=False,
                 claim_evidence_validation_entered=False, claim_evidence_validation_failed=False)
    def emit(event, **fields):
        print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)

    class Hooks(RunHooks):
        async def on_llm_start(self, context, agent, system_prompt, input_items):
            state["llm_round"] += 1
            state["phase"] = "finalizer" if agent.name == "Toujing Structured Finalizer" else "analysis"

        async def on_agent_end(self, context, agent, output):
            if agent.name == "Toujing Evidence-grounded Review":
                state["analysis_tool_loop"] = "complete"

        async def on_tool_start(self, context, agent, tool):
            call_id = getattr(context, "tool_call_id", None)
            for call in state["tool_calls"]:
                if call["call_id"] == call_id:
                    call["execution_started"] = True

        async def on_tool_end(self, context, agent, tool, result):
            call_id = getattr(context, "tool_call_id", None)
            for call in state["tool_calls"]:
                if call["call_id"] == call_id:
                    call["execution_ended"] = True
                    try:
                        status = json.loads(result).get("status")
                    except (ValueError, TypeError, AttributeError):
                        status = None
                    call["tool_result_status"] = status if status in {"complete", "insufficient_evidence"} else "not_a_success_payload"
                    emit("tool_execution_end", **call)

    schemas = {t.name: t.params_json_schema for t in review.TOOLS}
    async def request_hook(request):
        body = json.loads(request.content)
        # Read only these fields from the ACTUAL serialized HTTP request body.
        info = {"phase": state["phase"], "llm_round": state["llm_round"], "http_attempt": len(state["requests"]) + 1,
                "tool_count": len(body.get("tools") or []), "reasoning": body.get("reasoning"),
                "tool_choice": body.get("tool_choice"), **wire_format_summary(body)}
        state["requests"].append(info)
        emit("wire_request", **info)
        if state["phase"] == "finalizer":
            emit("finalizer_request", **info)

    async def response_hook(response):
        await response.aread()
        try:
            body = response.json()
        except ValueError:
            emit("wire_response", http_status=response.status_code, terminal_status="unreadable_json")
            return
        terminal = body.get("status")
        terminal = terminal if terminal in {"completed", "failed", "incomplete", "in_progress", "queued", "cancelled"} else "unknown_or_missing"
        state["responses"].append(terminal)
        shape = final_text_summary(body, secret)
        if state["phase"] == "analysis":
            # Even QA does not render Stage 1's unverified psychological prose.
            shape.pop("prefix_sanitized", None)
            shape.pop("suffix_sanitized", None)
        emit("wire_response", phase=state["phase"], llm_round=state["llm_round"], http_status=response.status_code,
             terminal_status=terminal, **shape)
        for item in body.get("output", []):
            if item.get("type") != "function_call":
                continue
            name, raw = item.get("name"), item.get("arguments")
            validation = "unknown_tool"
            if name in schemas:
                try:
                    errors = list(Draft202012Validator(schemas[name]).iter_errors(json.loads(raw)))
                    validation = "valid" if not errors else [{"keyword": e.validator, "path": [p if p in {"stance", "topic", "refs", "ref"} or isinstance(p, int) else "[UNKNOWN_FIELD]" for p in e.absolute_path]} for e in errors]
                except (ValueError, TypeError):
                    validation = "invalid_json"
            state["tool_call_count"] += 1
            call = dict(llm_round=state["llm_round"], ordinal=state["tool_call_count"],
                        call_id=safe_text(item.get("call_id"), secret), tool_name=safe_text(name, secret),
                        arguments=sanitized_args(raw, set(context.records)),
                        advertised_schema_validation=validation, execution_started=False, execution_ended=False)
            state["tool_calls"].append(call)
            emit("model_tool_call", **call)

    runtime = create_model_runtime(provider="deepseek", model="deepseek-v4-flash")
    client = runtime.model._client  # Existing client; no second provider/client.
    transport = client._client
    saved_hooks = {key: list(value) for key, value in transport.event_hooks.items()}
    saved_run_descriptor, original_run = Runner.__dict__["run"], Runner.run
    original_validate = AgentOutputSchema.validate_json
    original_verify, original_audit = review.validate_finalization, review._audit
    original_can_correct = review.can_correct_selection

    async def observed_run(cls, *args, **kwargs):
        kwargs["hooks"] = Hooks()
        return await original_run(*args, **kwargs)

    def observed_validate(self, *args, **kwargs):
        state["final_structured_output_entered"] = True
        try:
            validated = original_validate(self, *args, **kwargs)
            state["final_schema_attempts"].append("valid")
            state["final_structured_output_failed"] = False
            return validated
        except Exception:
            state["final_schema_attempts"].append("invalid")
            state["final_structured_output_failed"] = True
            raise

    def observe_check(original, prefix):
        def run(*args, **kwargs):
            state[prefix + "_entered"] = True
            try:
                checked = original(*args, **kwargs)
                record_validation_status(state, prefix, True)
                return checked
            except Exception as exc:
                record_validation_status(state, prefix, False)
                if prefix == "claim_evidence_validation":
                    state["semantic_rejection"] = semantic_diagnostic(args[0], args[1], exc)
                    state["semantic_rejections"].append(state["semantic_rejection"])
                    emit("claim_evidence_rejected", **state["semantic_rejection"])
                raise
        return run

    def observed_can_correct(error, selection, allowed_refs):
        permitted = original_can_correct(error, selection, allowed_refs)
        if permitted:
            state["semantic_correction_attempts"] += 1
            emit("semantic_correction", attempt=state["semantic_correction_attempts"],
                 maximum=1, rejection_code=error.issue.code)
        return permitted

    def safe_observer(observer):
        async def observe(value):
            try:
                await observer(value)
            except Exception as exc:
                # Diagnostic errors must not become a replacement model failure.
                emit("observer_error", observer=observer.__name__, exception_type=type(exc).__name__)
        return observe

    try:
        transport.event_hooks["request"].append(safe_observer(request_hook))
        transport.event_hooks["response"].append(safe_observer(response_hook))
        Runner.run = classmethod(observed_run)
        AgentOutputSchema.validate_json = observed_validate
        review.validate_finalization = observe_check(original_verify, "claim_evidence_validation")
        review._audit = observe_check(original_audit, "tool_receipt_audit")
        review.can_correct_selection = observed_can_correct
        result = await asyncio.wait_for(review.run_decision_review(
            question or "这是固定 Synthetic 示例。为什么 A 亏而 B 赚？请查双方操作、支持材料、反例和自身历史，"
            "区分记录、固定假设比较与可能解释；不能确定原因时明确说明。", context, runtime=runtime), 120)
        emit("accepted_result", executed_tools=result["executed_tools"],
             factual_refs=[r["ref"] for r in result["facts"]],
             historical_refs=[r["ref"] for r in result["historical_comparisons"]],
             possible_explanations=result["possible_explanations"], question_kind=result["question_kind"])
        state["qa_status"] = "PASS"
    except Exception as exc:
        cause = exc.__cause__ or exc.__context__
        state.update(qa_status="FAIL", exception_type=type(exc).__name__,
                     semantic_correction_exhausted=getattr(exc, "semantic_correction_exhausted", False),
                     model_behavior_error_message=sanitized_model_error(exc.message, secret) if isinstance(exc, ModelBehaviorError) else None,
                     underlying_cause_type=type(cause).__name__ if cause else None,
                     failure_after_any_tool_execution=any(c["execution_ended"] for c in state["tool_calls"]))
    finally:
        Runner.run = saved_run_descriptor
        AgentOutputSchema.validate_json = original_validate
        review.validate_finalization, review._audit = original_verify, original_audit
        review.can_correct_selection = original_can_correct
        transport.event_hooks = saved_hooks
        await client.close()
    state["wire_reasoning_none_verified"] = bool(state["requests"]) and all(
        r["reasoning"] == {"effort": "none"} for r in state["requests"])
    state["finalizer_wire_verified"] = finalization_wire_verified(state["requests"])
    if state["qa_status"] == "PASS" and not (state["finalizer_wire_verified"]
        and state["wire_reasoning_none_verified"] and state["analysis_tool_loop"] == "complete"
        and all(state[p + "_entered"] and not state[p + "_failed"] for p in (
            "final_structured_output", "tool_receipt_audit", "claim_evidence_validation"))):
        state.update(qa_status="FAIL", reason="incomplete_acceptance_diagnostics")
    emit("diagnostic_summary", **state)
    return 0 if state["qa_status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true", help="Offline fixture check; NOT an E2E model test")
    parser.add_argument("--probes", action="store_true", help="Live minimal structured-output probes A/B; no business schema changes")
    parser.add_argument("--ladder", action="store_true", help="Live schema ladder only; does not rerun A/B")
    parser.add_argument("--ladder-repeats", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--repeat", type=int, choices=(1, 2, 3), default=1,
                        help="Fixed number of E2E trials; failures are retained, never retried until PASS")
    parser.add_argument("--adversarial-suite", action="store_true", help="Run the three approved Synthetic adversarial intents")
    parser.add_argument("--question", choices=("为什么 A 亏而 B 赚？", "B 赚钱，所以我以后是不是照着他的操作做？", "A 是不是因为贪婪才连续加仓？",
        "B 赚钱，所以以后我是不是应该照着他的操作？", "A 是不是因为贪婪/追涨才连续加仓？"))
    args = parser.parse_args()
    if sum((args.probes, args.ladder, args.prepare_only)) > 1:
        parser.error("Choose only one of --probes, --ladder, --prepare-only")
    if (args.adversarial_suite and args.question) or ((args.probes or args.ladder or args.prepare_only)
        and (args.adversarial_suite or args.repeat != 1)):
        parser.error("Suite/repeat are E2E-only; suite and --question are mutually exclusive")
    logging.disable(logging.CRITICAL)
    secret = os.environ.get("DEEPSEEK_API_KEY", "")
    if not args.prepare_only and not secret.strip():
        print('{"qa_status":"NOT_RUN","reason":"credential_not_available_in_this_process"}')
        return 2
    if args.ladder:
        from scripts.qa_deepseek_structured_probes import run_ladder
        return asyncio.run(run_ladder(secret, args.ladder_repeats))
    if args.probes:
        if args.prepare_only:
            parser.error("--probes cannot be combined with --prepare-only")
        from scripts.qa_deepseek_structured_probes import run_probes
        async def bounded_probes():
            return await asyncio.wait_for(run_probes(secret), timeout=120)
        return asyncio.run(bounded_probes())
    from toujing_core_runtime.product import ProductRuntime
    with TemporaryDirectory(prefix="toujing-synthetic-diagnostic-") as folder:
        product = ProductRuntime(Path(folder) / "qa.sqlite3")
        try:
            context = prepare_context(product)
            if args.prepare_only:
                print(json.dumps({"qa_status": "PREPARE_ONLY", "synthetic_records": len(context.records)}))
                return 0
            async def run_cases():
                results = []
                for question, trial in qa_cases(args.question, adversarial_suite=args.adversarial_suite, repeat=args.repeat):
                    print(json.dumps({"event": "qa_case", "question": question or "main", "trial": trial}, ensure_ascii=False), flush=True)
                    code = await diagnose(context, secret, question)
                    results.append({"question": question or "main", "trial": trial, "qa_status": "PASS" if code == 0 else "FAIL"})
                passed = all(r["qa_status"] == "PASS" for r in results)
                print(json.dumps({"event": "stability_summary", "cases": results,
                    "qa_status": "PASS" if passed else "FAIL", "quality_review": "Inspect the accepted facts and explanations; not an LLM-judge score."}, ensure_ascii=False))
                return 0 if passed else 1
            return asyncio.run(run_cases())
        finally:
            product.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"qa_status": "FAIL_BEFORE_OR_AFTER_RUN", "exception_type": type(exc).__name__}))
        raise SystemExit(1)
