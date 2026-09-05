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
    original_verify, original_audit = review.verify_selection, review._audit

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
                return original(*args, **kwargs)
            except Exception:
                state[prefix + "_failed"] = True
                raise
        return run

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
        review.verify_selection = observe_check(original_verify, "claim_evidence_validation")
        review._audit = observe_check(original_audit, "tool_receipt_audit")
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
                     model_behavior_error_message=sanitized_model_error(exc.message, secret) if isinstance(exc, ModelBehaviorError) else None,
                     underlying_cause_type=type(cause).__name__ if cause else None,
                     failure_after_any_tool_execution=any(c["execution_ended"] for c in state["tool_calls"]))
    finally:
        Runner.run = saved_run_descriptor
        AgentOutputSchema.validate_json = original_validate
        review.verify_selection, review._audit = original_verify, original_audit
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
    parser.add_argument("--question", choices=("为什么 A 亏而 B 赚？", "B 赚钱，所以我以后是不是照着他的操作做？", "A 是不是因为贪婪才连续加仓？",
        "B 赚钱，所以以后我是不是应该照着他的操作？", "A 是不是因为贪婪/追涨才连续加仓？"))
    args = parser.parse_args()
    if sum((args.probes, args.ladder, args.prepare_only)) > 1:
        parser.error("Choose only one of --probes, --ladder, --prepare-only")
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
            return asyncio.run(diagnose(context, secret, args.question))
        finally:
            product.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"qa_status": "FAIL_BEFORE_OR_AFTER_RUN", "exception_type": type(exc).__name__}))
        raise SystemExit(1)
