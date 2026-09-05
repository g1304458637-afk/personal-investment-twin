"""Agent claim legality, not financial evidence generation or an LLM judge."""
from dataclasses import dataclass

from src.presentation.runtime_episode import json_value


@dataclass(frozen=True, slots=True)
class ClaimRejection:
    code: str
    json_path: str
    claim_kind: str | None
    refs: tuple[str, ...]
    expected_rule: str


class ReviewVerificationError(ValueError):
    def __init__(self, code, *, path="$", kind=None, refs=(), expected=""):
        super().__init__(code)  # Production errors never contain model prose.
        self.issue = ClaimRejection(code, path, kind, tuple(refs), expected)


@dataclass(frozen=True, slots=True)
class ClaimRule:
    evidence_kind: str
    tag: str
    missing: str
    boundary: str


CLAIM_RULES = {
    "price_influence_possible": ClaimRule("path", "add_after_positive_market_move", "contemporaneous_plan",
        "Recorded temporal association permits a tentative interpretation, not chasing, motive or causation."),
    "planned_staging_possible": ClaimRule("user_note", "user_plan", "contemporaneous_plan",
        "User-reported plan, not independently verified knowledge before execution."),
    "user_reported_reason": ClaimRule("user_note", "user_reason", "independent_confirmation",
        "User testimony about a reason, not a system-established motive."),
}


def scope_of(record):
    return (record.subject_id, record.account_id, record.episode_id, record.instrument_id)


def supports_claim(record, kind, context):
    """Reuse authoritative Path records; no returns, time relations or tags are inferred."""
    rule = CLAIM_RULES[kind]
    own = context.own.episode
    if (record.kind != rule.evidence_kind or record.availability != "complete"
        or scope_of(record) != scope_of(own) or rule.tag not in record.tags):
        return False
    value = record.value
    if not isinstance(value, dict):
        return False
    if record.kind == "path":
        return (value.get("episode_id") == own.episode_id and value.get("pattern_code") == rule.tag
            and any(p.pattern_id == record.ref and json_value(p) == value for p in context.own.path.patterns))
    note_kind = "plan" if rule.tag == "user_plan" else "reason"
    return (value.get("source") == "user" and value.get("note_kind") == note_kind
        and (value.get("subject_id"), value.get("account_id"), value.get("episode_id"))
            == (own.subject_id, own.account_id, own.episode_id))


def counter_material_refs(context, kind):
    # A plan can be an alternative, not logical negation. Preserve the legacy
    # field without pretending retrieval stance establishes evidence polarity.
    if kind != "price_influence_possible":
        return set()
    return {r.ref for r in context.records.values() if supports_claim(r, "planned_staging_possible", context)}


def build_claim_contract(context, allowed_refs):
    """Model-facing eligibility and application validation share the same rules.

    No unread identifiers are transmitted. Missing required counter-material
    makes this interpretation unavailable; no additional retrieval is performed.
    """
    allowed = set(allowed_refs)
    result = {}
    for kind, rule in CLAIM_RULES.items():
        supports = sorted(ref for ref in allowed if ref in context.records
                          and supports_claim(context.records[ref], kind, context))
        counter = counter_material_refs(context, kind)
        result[kind] = {"eligible_support_refs": supports,
            "required_counter_material_refs": sorted(counter & allowed),
            "required_missing_information": [rule.missing],
            "available": bool(supports) and counter <= allowed,
            "boundary": rule.boundary}
    result["unknown"] = {"eligible_support_refs": [], "required_counter_material_refs": [],
        "required_missing_information": [], "available": True,
        "boundary": "Abstention about motives does not erase observed facts or descriptive relations."}
    return result
