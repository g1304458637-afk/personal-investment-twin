"""Live QA probes only; reuse the existing client, not a second provider runtime."""
import json
import copy

from scripts.qa_decision_review_deepseek import final_text_summary, wire_format_summary, safe_text

MINIMAL_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string", "enum": ["OK"]}},
                  "required": ["answer"], "additionalProperties": False}
TEST_TOOL = {"type": "function", "name": "get_test_fact", "description": "Read a fixed synthetic QA fact.",
             "parameters": {"type": "object", "properties": {"subject": {"type": "string", "enum": ["A"]}},
                            "required": ["subject"], "additionalProperties": False}, "strict": True}


def validate_final(body, schema=MINIMAL_SCHEMA):
    from jsonschema import Draft202012Validator
    parts = [c.get("text", "") for item in body.get("output", []) if item.get("type") == "message"
             for c in item.get("content", []) if c.get("type") == "output_text"]
    text = "".join(parts)
    result = {"exact_json_parse_success": False, "schema_validation_success": False}
    try:
        def reject_constant(value):
            raise ValueError("non_json_constant")
        parsed = json.loads(text, parse_constant=reject_constant)
        result["exact_json_parse_success"] = True
        result["schema_validation_success"] = not list(Draft202012Validator(schema).iter_errors(parsed))
    except (TypeError, ValueError):
        pass
    return result


async def run_probes(secret):
    from src.agents.investment_coach import create_model_runtime
    runtime = create_model_runtime(provider="deepseek", model="deepseek-v4-flash")
    client = runtime.model._client
    common = {"model": runtime.model_name, "reasoning": {"effort": runtime.model_settings.reasoning.effort},
              "text": {"format": {"type": "json_schema", "name": "qa_answer", "strict": True, "schema": MINIMAL_SCHEMA}}}
    observations = []
    label = "A"

    def emit(event, **fields):
        print(json.dumps({"event": event, "probe": label, **fields}, ensure_ascii=False), flush=True)

    def emit_error(exc):
        body = getattr(exc, "body", None)
        error = body.get("error", body) if isinstance(body, dict) else {}
        error = error if isinstance(error, dict) else {}
        emit("probe_error", exception_type=type(exc).__name__,
             http_status=getattr(exc, "status_code", None),
             error_code=safe_text(error.get("code"), secret),
             error_param=safe_text(error.get("param"), secret),
             message_sanitized=safe_text(error.get("message", ""), secret)[:300])

    async def on_request(request):
        body = json.loads(request.content)
        emit("probe_wire_request", reasoning=body.get("reasoning"), tool_choice=body.get("tool_choice"),
             tool_count=len(body.get("tools") or []), previous_response_id_present=bool(body.get("previous_response_id")),
             **wire_format_summary(body))

    async def on_response(response):
        await response.aread()
        observations.append(response.status_code)

    transport = client._client
    saved = {key: list(value) for key, value in transport.event_hooks.items()}
    outcomes = {}

    async def final_check(response):
        body = response.model_dump(mode="json")
        checked = validate_final(body)
        passed = observations[-1] == 200 and response.status == "completed" and all(checked.values())
        emit("probe_final", http_status=observations[-1], response_status=response.status,
             **final_text_summary(body, secret), **checked, passed=passed)
        return passed

    try:
        transport.event_hooks["request"].append(on_request)
        transport.event_hooks["response"].append(on_response)
        try:
            response = await client.responses.create(**common, input="Return exactly the JSON object with answer OK.")
            outcomes["A"] = await final_check(response)
        except Exception as exc:
            outcomes["A"] = False
            emit_error(exc)

        label = "B"
        try:
            prompt = [{"role": "user", "content": "Call get_test_fact for subject A. After its result, return the answer as the required JSON object."}]
            first = await client.responses.create(**common, input=prompt, tools=[TEST_TOOL], tool_choice="required")
            calls = [item for item in first.output if item.type == "function_call"]
            valid = (observations[-1] == 200 and first.status == "completed" and len(calls) == 1
                     and calls[0].name == "get_test_fact" and json.loads(calls[0].arguments) == {"subject": "A"})
            emit("probe_tool_round", http_status=observations[-1], response_status=first.status,
                 call_count=len(calls), expected_tool_and_arguments_valid=valid)
            if not valid:
                outcomes["B"] = False
            else:
                # Full-history chaining matches the current SDK's non-session path.
                # No tools are offered in this standalone finalization probe (like A).
                # This does NOT alter Toujing's required-tool runtime policy.
                history = prompt + [item.model_dump(mode="json", exclude_none=True) for item in first.output]
                history.append({"type": "function_call_output", "call_id": calls[0].call_id,
                                "output": json.dumps({"subject": "SYN_COMPARE_A", "answer": "OK"})})
                emit("probe_tool_result", matching_call_id=True, encoding="function_call_output.output JSON string")
                final = await client.responses.create(**common, input=history)
                outcomes["B"] = await final_check(final)
        except Exception as exc:
            outcomes["B"] = False
            emit_error(exc)
    finally:
        transport.event_hooks = saved
        await client.close()
    print(json.dumps({"event": "probe_summary", "outcomes": outcomes,
                      "business_schema_modified": False, "production_policy_modified": False}))
    return 0 if all(outcomes.values()) else 1


def schema_ladder():
    """QA projections of the real schema, never production output contracts."""
    from agents.agent_output import AgentOutputSchema
    from src.agents.decision_review import ReviewSelection
    original = AgentOutputSchema(ReviewSelection).json_schema()
    props = original["properties"]
    steps = []
    current = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    for field in ("question_kind", "factual_refs", "historical_comparison_refs"):
        current["properties"][field] = copy.deepcopy(props[field])
        current["required"].append(field)
        steps.append((field, copy.deepcopy(current)))
    current["properties"]["possible_explanations"] = {
        "type": "array", "maxItems": props["possible_explanations"]["maxItems"], "items": {"type": "string"}}
    current["required"].append("possible_explanations")
    steps.append(("explanation_strings", copy.deepcopy(current)))
    item = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    current["properties"]["possible_explanations"]["items"] = item
    hypothesis = original["$defs"]["Hypothesis"]
    for field in ("kind", "supporting_evidence_refs", "contradictory_evidence_refs",
                  "alternative_explanations", "missing_information"):
        item["properties"][field] = copy.deepcopy(hypothesis["properties"][field])
        item["required"].append(field)
        steps.append(("explanation_" + field, copy.deepcopy(current)))
    inline = copy.deepcopy(original)
    inline["properties"]["possible_explanations"]["items"] = inline.pop("$defs")["Hypothesis"]
    steps.append(("full_equivalent_inline", inline))
    steps.append(("full_original_ref", original))
    return steps


async def run_ladder(secret, repeats=2):
    """Actual model calls with fixed Synthetic input and unchanged instructions.

    This isolates schema complexity WITHOUT tools. It cannot alone reproduce or
    certify the original tool-context finalization. No production parsing repair.
    """
    import hashlib
    from src.agents.investment_coach import create_model_runtime
    from src.compare.demo import build_pair
    pair = build_pair()
    sample = {"data_tier": "synthetic", "subjects": [
        {"subject_id": side.episode.subject_id, "outcome_ref": side.outcome.outcome_id,
         "result_kind": side.outcome.actual_result.result_kind}
        for side in (pair.a, pair.b)]}
    prompt = (
        "这是 Synthetic schema compatibility probe，不是投资分析。只输出符合本次 schema 的 JSON object。"
        "仅填本次 schema 允许的字段：question_kind 用 need_contemporaneous_records；"
        "factual_refs 使用输入中 A 的 outcome_ref；historical_comparison_refs 用空数组。"
        "如果 possible_explanations 是字符串数组，填一个 unknown；如果是对象数组，填一个对象，"
        "kind=unknown，supporting_evidence_refs 和 contradictory_evidence_refs 为空数组，"
        "alternative_explanations=[unknown]，missing_information=[contemporaneous_plan]。"
        "不存在于本级 schema 的字段不要输出。不添加解释文字，不输出金融数字或心理标签。\n"
        + json.dumps(sample, ensure_ascii=False, sort_keys=True))
    input_sha = hashlib.sha256(prompt.encode()).hexdigest()
    runtime = create_model_runtime(provider="deepseek", model="deepseek-v4-flash")
    client = runtime.model._client
    transport = client._client
    saved = {key: list(value) for key, value in transport.event_hooks.items()}
    active, http_status, wire = {}, None, {}
    results = []

    def emit(event, **fields):
        print(json.dumps({"event": event, **active, **fields}, ensure_ascii=False), flush=True)

    async def request_hook(request):
        nonlocal wire
        body = json.loads(request.content)
        wire = wire_format_summary(body)
        emit("ladder_wire", **wire, reasoning=body.get("reasoning"),
             tool_count=len(body.get("tools") or []), input_sha256=input_sha)

    async def response_hook(response):
        nonlocal http_status
        http_status = response.status_code

    try:
        transport.event_hooks["request"].append(request_hook)
        transport.event_hooks["response"].append(response_hook)
        steps = schema_ladder()
        for trial in range(1, repeats + 1):
            # Reverse the second pass to expose order/time effects, not infer a
            # deterministic complexity threshold from one stochastic response.
            ordered = steps if trial % 2 else list(reversed(steps))
            for name, schema in ordered:
                active = {"stage": name, "trial": trial, "context": "isolated_no_tools"}
                http_status, wire = None, {}
                try:
                    response = await client.responses.create(
                        model=runtime.model_name, reasoning={"effort": runtime.model_settings.reasoning.effort},
                        input=prompt, text={"format": {"type": "json_schema", "name": "final_output",
                                                       "schema": schema, "strict": True}})
                    body = response.model_dump(mode="json")
                    checked = validate_final(body, schema)
                    passed = http_status == 200 and response.status == "completed" and all(checked.values())
                    emit("ladder_result", http_status=http_status, response_status=response.status,
                         **final_text_summary(body, secret), **checked, passed=passed)
                except Exception as exc:
                    passed = False
                    emit("ladder_error", http_status=http_status, exception_type=type(exc).__name__)
                results.append({**active, "schema_sha256": wire.get("schema_sha256"), "passed": passed})
    finally:
        transport.event_hooks = saved
        await client.close()
    first_failed = next((name for name, _ in schema_ladder()
                         if any(r["stage"] == name and not r["passed"] for r in results)), None)
    active = {}
    emit("ladder_summary", results=results, first_stage_with_failure=first_failed,
         conclusion="no_isolated_schema_failure_reproduced" if first_failed is None else "candidate_boundary_requires_context_confirmation",
         production_schema_changed=False, production_policy_changed=False)
    return 0 if first_failed is None else 1
