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

from typing import Any, Literal, Mapping

TEACHING_NOTE_MODEL = "strategy_teaching.v1"


class TeachingReferenceError(ValueError):
    """A cited report path does not exist; the segment must be dropped."""


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
