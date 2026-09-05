# Agent v1 adversarial semantic stability closure

## Observed failures

The user confirmed the main live DeepSeek E2E PASS after `45b4f98`, but two
adversarial outputs were correctly rejected:

- A-scoped `possible_explanations[0].contradictory_evidence_refs[0]` selected B's
  Episode result (`eo_325…`): `evidence_scope_mismatch`.
- `user_reported_reason` selected with empty support and insufficient user notes:
  `evidence_does_not_support_hypothesis`.

The finalizer had a global read-ref allowlist, prose-derived kind tokens and
eligibility metadata, but no separate constrained claim candidate space.
Retrieval under a `contradict` stance also produced a broad list that could
include B; that list was not semantic authorization. Neither rejection justifies
relaxing the validator. No new API/framework/financial-method investigation.

## Deterministic selection boundary

`build_claim_candidates` derives only from completed, authorized tool receipts:

- `claim_scope`: exact own subject/account/Episode/instrument.
- `admissible_claim_kinds`: only available kinds; no valid own user-reason note
  means `user_reported_reason` is absent, not merely marked unavailable.
- `explanations[kind]`: scoped eligible support/contrary refs, required
  counter-material, required missing-information markers and interpretation boundary.
- `comparison_context`: separately authorized scopes and eligible factual refs.
  B may be a comparison fact, not direct evidence for an A-scoped motive.
- `eligible_historical_comparison_refs`: read, complete, own-scoped registry results.

Kind tokens in untrusted analysis no longer authorize candidates. The provider's
strict wire schema uses the same production shape, narrowed with per-run kind
and ref enums (or empty-array bounds). No new union, field, financial value or
production result schema is introduced. B remains available in factual output.

Schema parsing still validates the unchanged production type. A per-run illegal
choice is classified as semantic, not charged to the format budget. Native enum
constraints reduce invalid choices but do not replace cross-field validation.
The unchanged domain validator and an additional candidate-membership check
both run before acceptance. Facts/possible explanations stay distinct.

## Independent bounded retries

| Layer | Budget / outcome |
| --- | --- |
| Transport | Existing provider/SDK policy, unchanged; errors propagate. No application transport retry loop added. |
| Format/schema | One retry total across Stage 2, including semantic correction. Exhaustion: `finalizer_schema_validation_failed`. Never strip fences or extract trailing JSON. |
| Semantic correction | One correction for allowlisted typed selection errors, same catalog and claim scope, no tools or retrieval. Full receipt and domain/candidate validation rerun. |

Correctable codes are scoped selection/type-role errors, absent support for the
selected kind, omitted counter-material or missing-information markers. The
entire selected ref set must already have been read. Unknown/nonexistent refs,
missing tool receipts, revoked access and other failures are not retryable.
Insufficient evidence may yield `unknown`, never fabricated support.

Second semantic rejection preserves its original typed code/path and sets
`semantic_correction_exhausted=true`. A requested tool in the no-tools finalizer
fails through the SDK. At most three Stage 2 model invocations occur (initial +
one format retry + one semantic correction), excluding SDK transport attempts.
Stage 1 executes once. Failed candidates and free analysis are never returned.

This applies the previously audited output-validation/correction/revalidation
pattern, without migrating frameworks or adding dependencies.

## Tests and live acceptance

Deterministic tests cover candidate construction, A/B scope separation, missing/
unread/incomplete/wrong-scope notes, legitimate user-reason admission, corrected
unknown, invented refs, attempted scope/tool changes, exhausted budgets, and both
format/semantic failure orders. Original schema and financial results are preserved.

Local verification: **92 targeted tests passed; 727 full Python tests passed**
(20 new cases). `git diff --check` passed. AST comparison confirms the original
domain validator, receipt audit, six tools and production output types are unchanged.

The QA harness now retains each rejection and the eventual validation outcome.
`--repeat` is a fixed 1–3 trials, not retry-until-PASS. `--adversarial-suite`
covers the three approved Synthetic intents. A summary retains every failure.

Run from the existing key-loaded Terminal, on the fixed Synthetic A/B only:

```bash
.venv/bin/python scripts/qa_decision_review_deepseek.py --repeat 2
.venv/bin/python scripts/qa_decision_review_deepseek.py --adversarial-suite --repeat 2
```

Inspect meaningful comparison, no copy-trading advice, no unsupported motive,
valid refs, counter-material and missing information. Deterministic gates certify
legality; the repeat matrix is a small stability check, not a statistical claim or
an LLM-judge score. User-reported earlier PASS does not certify this new matrix.

Freeze remains **NOT READY pending post-change main and adversarial stability
acceptance**. Financial methods, Compare, tools, provider and the authoritative
claim validator are unchanged; only candidate constraints and bounded recovery changed.
