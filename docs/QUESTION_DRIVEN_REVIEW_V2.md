# Question-driven Review v2 — first implementation

## What changed

The existing six SDK tools, required tool use, receipt audit, ownership checks,
registered financial scenarios and motive ClaimOptions remain unchanged.
The original analysis loop and isolated no-tools strict finalizer remain two
stages, with the original shared formatting retry and one semantic correction.

`evidence_grounded_review_v2` adds a `question_driven_review_answer_v2` presentation
payload. V1 stored results are not migrated or rewritten. Persistence continues
to store the existing inference payload; no new database or Evidence schema.

The finalizer chooses `answer_focus` and up to three ordered
`finding_option_ids` in addition to the original selection fields. The finding
catalog is made only from actually completed own-Episode tool receipts. It
contains recorded quantity changes, registered single-event local v2 comparisons,
full v1 comparisons, and explicit downstream-infeasibility explanations.
Phase scenarios remain in the existing tools; this first presentation does not
add new phase-specific finding templates.

## Important product honesty

The model chooses relevant findings and their order. Numerical statements,
comparison relationships and qualifications are programmatically composed from
those records. This is **not unrestricted LLM-authored financial prose**. It
replaces the motive-only answer with question-directed evidence composition,
without claiming to have solved open-ended narrative entailment verification.
The original bounded motive text remains available for actual motive questions.

There is no handwritten Demo H result in production. Golden values remain QA
expectations only. A local comparison's difference is not a final-loss share.
The first implementation covers result formation and operation impact. It does
not add account-weight / full-risk / industry look-through tools. Exposure
targets from REVIEW_ANSWER_TARGETS_V1 remain a future integration gate, not an
advertised capability. A share comparison retains required counterpart outcomes
with their own periods; neither returns nor operations are ranked as skill.

## Enforcement

- Wire schema allows only IDs/focus, no free claim or amount fields.
- Finding IDs bind scope, source ref and composed content. Rebuild at rendering
  checks that selected options still match the authorized, read records.
- Complete finding refs are merged into and checked by the original ref gate.
- Infeasibility admits only a non-numeric limitation, not a valid hypothetical result.
- Result-formation selections must include both signs when existing local
  comparisons contain both; this is counter-material coverage, not causal decomposition.
- Operation selections need a comparison when available. A selected local
  operation with an infeasible full scenario must retain that boundary.
- Missing comparison coverage permits one bounded reselection of the SAME
  catalog; scope, invalid value or changed-record errors cannot be repaired by a model.
- UI only displays versioned answers matching current scope; no technical JSON,
  evidence IDs, provider names or tool lists in the answer. Qualifications remain visible.
- Browser still has no live model path. Real use requires native runtime and
  explicit existing model consent. No credentials are written or logged.

## Verification and rollout

`tests/test_review_answer_v2.py` uses the real runtime's Synthetic Demo H facts
and an offline scripted SDK model. It tests factual grounding, scope, anti-cherry-
picking coverage, full-horizon infeasibility, strict parsing, no psychological
prose leakage and original receipt enforcement. These tests do not measure a
live model's relevance or a user's understanding.

The existing Synthetic A/B QA command now prints `accepted_answer` after all
production gates. In the terminal with an already configured key:

```sh
cd /Users/cccc/Projects/personal-investment-twin
.venv/bin/python scripts/qa_decision_review_deepseek.py --adversarial-suite
```

No provider switch, new credentials mechanism or schema ladder is needed. Inspect
the actual answer, not just `qa_status`. This change has not itself run paid QA.
Native debug launches the existing `.venv` Python runtime; an already running
runtime needs a restart from its existing configured environment to load changes.
Production packaged sidecars require the normal rebuild; no claim of deployment
or packaged-binary recertification is made by a frontend build.

Reference: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
Strict structure is a format boundary, not a guarantee of answer relevance; the
separate receipt, claim and finding gates remain necessary.
