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
        self.semantic_correction_exhausted = False


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


def build_claim_candidates(context, allowed_refs):
    """Constrain claim selection before finalization, separate from comparison access."""
    allowed = set(allowed_refs)
    own_scope = scope_of(context.own.episode)
    keys = ("subject_id", "account_id", "episode_id", "instrument_id")
    claim_scope = dict(zip(keys, own_scope))
    factual = {ref for ref in allowed if ref in context.records
               and scope_of(context.records[ref]) in context.authorized_scopes
               and context.records[ref].kind != "historical_comparison"}
    own_refs = {ref for ref in factual if scope_of(context.records[ref]) == own_scope}
    candidates = {}
    for kind, rule in build_claim_contract(context, allowed).items():
        if not rule["available"]:
            continue
        supports = set(rule["eligible_support_refs"]) if kind != "unknown" else own_refs
        candidates[kind] = {**rule, "claim_scope": claim_scope,
            "eligible_support_refs": sorted(supports),
            "eligible_contradictory_refs": sorted(own_refs - supports if kind != "unknown" else own_refs)}
    return {"claim_scope": claim_scope, "admissible_claim_kinds": sorted(candidates),
        "explanations": candidates,
        "comparison_context": {"comparison_id": context.comparison_id,
            "authorized_scopes": [dict(zip(keys, scope)) for scope in sorted(context.authorized_scopes)],
            "eligible_factual_refs": sorted(factual)},
        "eligible_historical_comparison_refs": sorted(ref for ref in allowed if ref in context.records
            and scope_of(context.records[ref]) == own_scope
            and context.records[ref].kind == "historical_comparison"
            and context.records[ref].availability == "complete")}


def verify_claim_candidates(selection, candidates):
    """An additional narrowing gate; never replaces the authoritative validator."""
    for i, hypothesis in enumerate(selection.possible_explanations):
        path = f"$.possible_explanations[{i}]"
        candidate = candidates["explanations"].get(hypothesis.kind)
        if candidate is None:
            raise ReviewVerificationError("inadmissible_claim_kind", path=path + ".kind",
                kind=hypothesis.kind, expected="Choose a currently admissible kind, or unknown without inventing support.")
        for field, eligible in (("supporting_evidence_refs", "eligible_support_refs"),
                                ("contradictory_evidence_refs", "eligible_contradictory_refs")):
            for j, ref in enumerate(getattr(hypothesis, field)):
                if ref not in candidate[eligible]:
                    raise ReviewVerificationError("ineligible_claim_ref", path=f"{path}.{field}[{j}]",
                        kind=hypothesis.kind, refs=(ref,), expected="Use the same claim's eligible refs for this role.")


SEMANTIC_CORRECTION_CODES = frozenset({
    "inadmissible_claim_kind", "ineligible_claim_ref", "evidence_scope_mismatch",
    "evidence_does_not_support_hypothesis", "support_counter_material_overlap",
    "contrary_plan_not_addressed", "hypothesis_needs_alternatives_and_missing_information",
})


def can_correct_selection(error, selection, allowed_refs):
    """Unknown/unread refs and non-model-correctable failures never authorize retry."""
    refs = set(selection.factual_refs + selection.historical_comparison_refs)
    for h in selection.possible_explanations:
        refs.update(h.supporting_evidence_refs + h.contradictory_evidence_refs)
    return error.issue.code in SEMANTIC_CORRECTION_CODES and refs <= set(allowed_refs)
