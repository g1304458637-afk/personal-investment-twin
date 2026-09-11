"""AI teaching explanations with structured citations (no model-computed numbers).

Design (mirrors the repo's existing agent discipline and the vendored
OpenAI Agents SDK's structured-output capability):

1. The model never emits numbers.  It returns a constrained structure —
   explanation segments plus *references* to report fields — via the same
   Pydantic ``output_type`` mechanism the review agents use through
   ``dsa_vendor``.
2. Deterministic code resolves each reference against the
   ``strategy_comparison.v1`` report and renders the final text with the
   report's own values.  An unresolvable reference fails closed per segment.
3. Teaching scope: condition differences only; verdicts, price targets and
   ability scores are prohibited fields in the schema itself.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Mapping

TEACHING_NOTE_MODEL = "strategy_teaching.v1"


class TeachingReferenceError(ValueError):
    """A cited report path does not exist; the segment must be dropped."""


def build_teaching_prompt(report: Mapping[str, Any], *, focus: str | None = None) -> dict[str, str]:
    """Serialize the report as the single source of truth for the model."""
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)
    user = (f"策略对照报告 JSON：\n{serialized}\n\n"
            + (f"请重点解释其中与 {focus} 相关的部分。" if focus else "请给出这份报告的要点解读。")
            + "\n模板占位符必须通过 references 指向报告字段；报告中没有的信息用 kind=no_data。")
    return {"system": _SYSTEM_PROMPT, "user": user}


def resolve_report_path(report: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted path like 'reports.0.window_user_net_cash_flow'."""
    current: Any = report
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                raise TeachingReferenceError(f"unknown report path: {path}")
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise TeachingReferenceError(f"unknown report path: {path}") from exc
        else:
            raise TeachingReferenceError(f"unknown report path: {path}")
    return current


def render_segment(template: str, report: Mapping[str, Any],
                   references: Mapping[str, str]) -> dict[str, Any]:
    """Render one explanation segment by filling {placeholders} from the report.

    Placeholders map to dotted report paths; the rendered value is always the
    report's own value (or an explicit absence statement), never model text.
    """
    resolved: dict[str, str] = {}
    for placeholder, path in references.items():
        try:
            value = resolve_report_path(report, path)
        except TeachingReferenceError:
            return {"accepted": False, "reason": "unknown_reference", "path": path,
                    "text": None}
        resolved[placeholder] = value if isinstance(value, str) else json_number(value)
    return {"accepted": True, "reason": None, "path": None,
            "text": template.format(**resolved)}


def json_number(value: Any) -> str:
    """Keep the report's own numeric representation (no recomputation)."""
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def teaching_output_schema() -> dict[str, Any]:
    """The structured-output schema handed to the Agents SDK ``output_type``.

    Kept declarative so the vendored agent runner can enforce it directly:
    the model may only classify and reference; free numbers are not part of
    the schema at all.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "template", "references"],
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": ["condition_difference", "entry_teaching",
                                          "exit_teaching", "risk_teaching", "no_data"]},
                        "template": {"type": "string", "maxLength": 400},
                        "references": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def forbidden_note() -> str:
    return ("教学解释只描述条件与事实差异；不提供买入/卖出建议、目标价、止损价或能力评价。"
            "报告没有的信息必须回答“报告中无此数据”。")


# --- Model wiring (this module itself is imported only on teaching use) ---

from agents import Agent, ModelSettings, Runner  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

_SYSTEM_PROMPT = (
    "你是投资教学助手。输入是一份由确定性引擎生成的策略对照报告（JSON）。"
    "把报告内容解释成教学语言：\n"
    "1. 每个模板中的占位符都必须通过 references 指向报告中的字段，你不得自行填写数字。\n"
    "2. 报告中没有的信息（大盘、新闻、其他标的），用 kind=no_data 的段落明确说明。\n"
    "3. 只陈述事实与条件差异；kind 枚举之外不得表达任何买卖建议或能力评价。\n"
    "4. 模板为简体中文，不超过 400 字符。"
)


class TeachingSegment(BaseModel):
    kind: Literal["condition_difference", "entry_teaching", "exit_teaching",
                  "risk_teaching", "no_data"]
    template: str = Field(max_length=400)
    references: dict[str, str]


class TeachingAnswer(BaseModel):
    segments: list[TeachingSegment]


def build_teaching_agent(model: Any, model_settings: Any, run_config: Any) -> Any:
    from agents import Agent

    return Agent(name="Strategy Teaching", instructions=_SYSTEM_PROMPT, model=model,
                 tools=[], output_type=TeachingAnswer,
                 model_settings=model_settings if model_settings is not None else ModelSettings())


def render_answer(answer: TeachingAnswer, report: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministically render model segments; unresolvable references drop."""
    texts: list[str] = []
    dropped: list[dict[str, str]] = []
    for segment in answer.segments:
        rendered = render_segment(segment.template, report, segment.references)
        if rendered["accepted"]:
            texts.append(f"[{segment.kind}] {rendered['text']}")
        else:
            dropped.append({"kind": segment.kind, "path": rendered["path"] or ""})
    return {"accepted": bool(texts), "texts": texts, "dropped": dropped,
            "reason": None if texts else "teaching_reference_failed"}


async def run_teaching(runtime: Any, report: Mapping[str, Any], *, focus: str | None = None,
                       timeout: float = 60.0) -> dict[str, Any]:
    import asyncio

    agent = build_teaching_agent(runtime.model, runtime.model_settings, runtime.run_config)
    prompt = build_teaching_prompt(report, focus=focus)
    result = await asyncio.wait_for(Runner.run(agent, prompt["user"], max_turns=1,
                                               run_config=runtime.run_config), timeout=timeout)
    answer = result.final_output
    if not isinstance(answer, TeachingAnswer):
        return {"status": "unavailable", "reason": "teaching_output_invalid", "texts": [], "dropped": []}
    rendered = render_answer(answer, report)
    if not rendered["accepted"]:
        return {"status": "unavailable", "reason": rendered["reason"], "texts": [],
                "dropped": rendered["dropped"]}
    return {"status": "available", "reason": None, "texts": rendered["texts"],
            "dropped": rendered["dropped"], "note": forbidden_note()}


def explain_report(params: Mapping[str, object]) -> dict[str, object]:
    """Protocol entry: {report, focus?, _desktop_model_key} → teaching texts."""
    from toujing_core_runtime.model_service import desktop_runtime

    if not isinstance(params, dict):
        raise ValueError("invalid_teaching_request")
    report = params.get("report")
    if not isinstance(report, Mapping) or report.get("schema_version") not in {
        "strategy_comparison.v1", "strategy_simulation.v1",
    }:
        raise ValueError("invalid_teaching_report")
    key = params.get("_desktop_model_key")
    if not isinstance(key, str) or not key:
        raise ValueError("model_not_configured")
    focus = params.get("focus")
    focus = focus.strip() if isinstance(focus, str) and focus.strip() else None
    runtime = desktop_runtime(key)
    try:
        import asyncio

        return asyncio.run(run_teaching(runtime, report, focus=focus))
    except TimeoutError:
        return {"status": "unavailable", "reason": "model_connection_timeout", "texts": [], "dropped": []}
    except Exception as exc:
        from openai import AuthenticationError, RateLimitError

        if isinstance(exc, AuthenticationError):
            reason = "model_authentication_failed"
        elif isinstance(exc, RateLimitError):
            reason = "model_rate_limited"
        else:
            reason = "model_connection_failed"
        return {"status": "unavailable", "reason": reason, "texts": [], "dropped": []}
