"""Finite, receipt-scoped choices; never financial evidence or model-authored refs.

The catalog is immutable for one finalization (including retries). Evidence values
remain in the shared review catalog, not duplicated into every option.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Literal

from pydantic import ConfigDict, Field, create_model

from src.agents.claim_contract import ReviewVerificationError, build_claim_contract, scope_of


def _id(prefix, content):
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + "_" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ClaimOption:
    option_id: str
    claim_scope: tuple[str, str, str, str]
    claim_kind: str
    supporting_evidence_refs: tuple[str, ...]
    contradictory_evidence_refs: tuple[str, ...]
    required_missing_information: tuple[str, ...]
    allowed_alternative_explanations: tuple[str, ...]
    boundary: str

    def __post_init__(self):
        support, contrary = set(self.supporting_evidence_refs), set(self.contradictory_evidence_refs)
        if support & contrary or (self.claim_kind == "unknown" and (support or contrary)):
            raise ReviewVerificationError("invalid_claim_option_roles")
        if self.claim_kind != "unknown" and not support:
            raise ReviewVerificationError("invalid_claim_option_support")

    def hypothesis(self):
        return {"kind": self.claim_kind,
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "contradictory_evidence_refs": list(self.contradictory_evidence_refs),
            "alternative_explanations": list(self.allowed_alternative_explanations),
            "missing_information": list(self.required_missing_information)}


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    option_id: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComparisonContext:
    comparison_id: str | None
    authorized_scopes: tuple[tuple[str, str, str, str], ...]
    # Always retain the own outcome and, when comparing, both outcomes and the
    # registered comparison. Uncertain motives must not erase observed differences.
    factual_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinalizationOptions:
    claim_scope: tuple[str, str, str, str]
    comparison_context: ComparisonContext
    factual_options: tuple[EvidenceBundle, ...]
    historical_options: tuple[EvidenceBundle, ...]
    claim_options: tuple[ClaimOption, ...]

    def model_view(self):
        return asdict(self)

    def choice_type(self, production_type):
        """One dynamic type drives BOTH the wire schema and strict local parsing."""
        limits = production_type.model_json_schema()["properties"]
        def choices(options, maximum, minimum=0):
            ids = tuple(o.option_id for o in options)
            item_type = Literal[ids] if ids else str
            return (list[item_type], Field(min_length=minimum, max_length=min(maximum, len(ids))))
        fact_capacity = limits["factual_refs"]["maxItems"] - len(self.comparison_context.factual_refs)
        if fact_capacity < 0:
            raise ReviewVerificationError("required_facts_exceed_output_capacity")
        return create_model("FinalizationChoice", __config__=ConfigDict(extra="forbid"),
            factual_option_ids=choices(self.factual_options, fact_capacity),
            historical_option_ids=choices(self.historical_options, limits["historical_comparison_refs"]["maxItems"]),
            claim_option_ids=choices(self.claim_options, limits["possible_explanations"]["maxItems"], 1),
            question_kind=(production_type.model_fields["question_kind"].annotation, ...))

    def expand(self, choice):
        """No inferred IDs, field repair, fallback ref search or model-authored facts."""
        def selected(field, options):
            ids = getattr(choice, field)
            by_id = {o.option_id: o for o in options}
            if any(option_id not in by_id for option_id in ids):
                raise ReviewVerificationError("option_not_exposed", path="$." + field)
            if len(ids) != len(set(ids)):
                raise ReviewVerificationError("duplicate_option_selection", path="$." + field,
                    expected="Select each exposed option at most once; do not change the catalog.")
            return [by_id[option_id] for option_id in sorted(ids)]
        facts = selected("factual_option_ids", self.factual_options)
        history = selected("historical_option_ids", self.historical_options)
        claims = selected("claim_option_ids", self.claim_options)
        if len(claims) > 1 and any(c.claim_kind == "unknown" for c in claims):
            raise ReviewVerificationError("uncertainty_option_conflict", path="$.claim_option_ids",
                expected="Choose terminal uncertainty alone, or supported tentative options; keep the same catalog.")
        return self._production(facts=facts, history=history, claims=claims, question_kind=choice.question_kind)

    def _production(self, *, facts=(), history=(), claims=(), question_kind="none"):
        return {"factual_refs": list(self.comparison_context.factual_refs) + [r for b in facts for r in b.evidence_refs],
            "historical_comparison_refs": [r for b in history for r in b.evidence_refs],
            "possible_explanations": [c.hypothesis() for c in claims], "question_kind": question_kind}

    def validation_cases(self):
        """Each generated bundle must pass the existing validator before exposure."""
        yield self._production()
        for bundle in self.factual_options:
            yield self._production(facts=(bundle,))
        for bundle in self.historical_options:
            yield self._production(history=(bundle,))
        for option in self.claim_options:
            yield self._production(claims=(option,))


def build_finalization_options(context):
    own_scope = scope_of(context.own.episode)
    read = context.retrieved
    factual = {ref: r for ref, r in context.records.items() if ref in read
               and scope_of(r) in context.authorized_scopes and r.kind != "historical_comparison"}
    required = [context.own.outcome.outcome_id]
    if context.comparison_id:
        comparison = factual.get(context.comparison_id)
        if comparison is None or comparison.kind != "comparison" or scope_of(comparison) != own_scope:
            raise ReviewVerificationError("authorized_comparison_receipt_required")
        for scope in sorted(context.authorized_scopes - {own_scope}):
            outcomes = sorted(r.ref for r in factual.values() if r.kind == "episode" and scope_of(r) == scope)
            if len(outcomes) != 1:
                raise ReviewVerificationError("counterpart_outcome_receipt_required")
            required.extend(outcomes)
        required.append(context.comparison_id)
    comparison_context = ComparisonContext(context.comparison_id, tuple(sorted(context.authorized_scopes)), tuple(required))
    def bundle(ref, role):
        return EvidenceBundle(_id(role, (scope_of(context.records[ref]), ref)), (ref,))
    facts = tuple(bundle(ref, "fact") for ref in sorted(factual.keys() - set(required)))
    history = tuple(bundle(ref, "history") for ref, r in sorted(context.records.items())
        if ref in read and scope_of(r) == own_scope and r.kind == "historical_comparison" and r.availability == "complete")
    rules = build_claim_contract(context, read)
    claims = []
    for kind, rule in sorted(rules.items()):
        if not rule["available"]:
            continue
        missing = tuple(rule["required_missing_information"])
        if kind == "unknown":
            # Uncertainty is not a hypothesis with support/counter-support. Its
            # observed basis lives in facts, including the A/B comparison above.
            has_testimony = any(rules[k]["available"] for k in ("planned_staging_possible", "user_reported_reason"))
            missing = ("independent_confirmation",) if has_testimony else ("contemporaneous_plan", "reason_for_change")
        content = dict(claim_scope=own_scope, claim_kind=kind,
            supporting_evidence_refs=tuple(rule["eligible_support_refs"]),
            contradictory_evidence_refs=tuple(rule["required_counter_material_refs"]),
            required_missing_information=missing,
            allowed_alternative_explanations=("prior_staged_plan",) if kind == "price_influence_possible" else ("unknown",),
            boundary=rule["boundary"])
        claims.append(ClaimOption(_id("claim", content), **content))
    ids = [o.option_id for o in (*facts, *history, *claims)]
    if len(ids) != len(set(ids)):
        raise ReviewVerificationError("ambiguous_finalization_option_id")
    return FinalizationOptions(own_scope, comparison_context, facts, history, tuple(claims))


def can_correct_choice(error, choice, options):
    """Only combination mistakes over exposed IDs are model-correctable.

    Scope/role/support errors after deterministic expansion indicate invalid
    application state, not a reason to ask the model to repair evidence.
    """
    return error.issue.code in {"duplicate_option_selection", "uncertainty_option_conflict"} and all(
        set(getattr(choice, field)) <= {o.option_id for o in values}
        for field, values in (("factual_option_ids", options.factual_options),
            ("historical_option_ids", options.historical_options), ("claim_option_ids", options.claim_options)))
