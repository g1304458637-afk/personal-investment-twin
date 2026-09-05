# Agent v1: deterministic claim options / evidence bundles

This checkpoint supersedes the finalization selection surface in `d532f5e`.
The user's post-`d532f5e` live main test was **1/2 PASS**, so it did not qualify
for freeze. This change is not a claim of post-change live stability.

## Focused reference decisions

| Reference inspected | KEEP / ADOPT | LATER / REJECT |
| --- | --- | --- |
| [Guidance select](https://guidance.readthedocs.io/en/latest/generated/guidance.select.html) | ADOPT selection among application-defined legal choices. | REJECT adding its generation runtime or assuming a remote API enforces local token constraints. |
| [Outlines Choice source](https://dottxt-ai.github.io/outlines/latest/api_reference/types/dsl/#outlines.types.dsl.Choice) and [Literal/Enum output types](https://dottxt-ai.github.io/outlines/1.0.0/features/core/output_types/) | ADOPT finite typed output choices; make illegal ref combinations unrepresentable in accepted output. | REJECT another runtime dependency or a decoder/framework migration. |
| [PydanticAI dynamic output tools / output validators](https://pydantic.dev/docs/ai/core-concepts/output/), [prepare_tools](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/), [retry budgets](https://pydantic.dev/docs/ai/core-concepts/retries/) | ADOPT per-context output filtering, typed rejection and bounded revalidation. Toujing derives the output type once from completed receipts, not on each retry. | REJECT migration. No output-tool call is needed: the existing finalizer remains native structured output with zero tools. |
| [LangGraph routing example](https://docs.langchain.com/oss/python/langgraph/workflows-agents#routing) | ADOPT model chooses an identifier, deterministic code executes its meaning. | LATER durable graph/checkpoint machinery if needed; REJECT adding it to this two-stage flow. |
| [OpenAI output/tool guardrail boundaries](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals), [structured output](https://developers.openai.com/api/docs/guides/structured-outputs) | KEEP SDK tool lifecycle, strict typed parsing and native Responses mapping. KEEP independent domain checks after finalization. | REJECT treating JSON validity or guardrail success as proof of financial support. |
| [Guardrails validation / reask](https://guardrailsai.com/guardrails/docs/how-to-guides/use_on_fail_actions) | KEEP explicit rejection and capped reask. | REJECT automatic value fixing, dropping invalid financial fields, warning-only release or retry-until-PASS. |

Installed source checked: `openai-agents 0.22.0`, `openai 3.7.0`, `pydantic
2.13.5`. `agents/agent_output.py` derives its schema and strict, non-partial
parser from a Pydantic type. `agent.py:get_all_tools` filters enabled function
tools; `run_internal/turn_resolution.py` invokes output validation;
`run_internal/guardrails.py` raises output tripwires. None is reimplemented.
No new dependency, model, client, financial method or tool schema is introduced.

## Exact weakness in d532f5e

The old restriction was **partly schema-level**, not merely a prompt:

1. `FinalizerOutputSchema.json_schema()` advertised scoped ref enums, but its
   `validate_json()` parsed the original `ReviewSelection`, whose ref fields were
   unrestricted strings. A provider response violating the advertised enum
   therefore reached the semantic gate. B was **not** authorized by that wire
   enum; it was correctly rejected by the domain validator.
2. Support and contrary arrays were independent, with role enums unioned across
   kinds. A JSON schema of individual arrays did not encode each kind's exact
   legal bundle, disjointness, mandatory counter-material or missing markers.
3. `unknown` admitted all own refs to both roles. This unnecessarily represented
   “supporting uncertainty” and “contradicting uncertainty” as if uncertainty were
   a normal hypothesis, inviting overlap.

The observed overlap and B-scope correction failures are not evidence that
the validator is too strict. The application gave the model unnecessary ref
assembly responsibilities. No provider, schema-ladder or tool-loop re-diagnosis.

## Finalization architecture

```text
unchanged Stage 1 tool/retrieval loop
    → paired completed receipts + authorized canonical catalog
    → deterministic immutable options
    → preflight each bundle through existing claim validator
    → Stage 2 selects IDs under a per-run typed schema (zero tools)
    → original receipt audit + deterministic ID expansion
    → unchanged production type + original claim/evidence validator
    → existing renderer
```

`src/agents/claim_options.py` contains four small frozen/slots dataclasses:

- `ClaimOption`: option_id, exact subject/account/Episode/instrument scope,
  claim_kind, supporting_evidence_refs, contradictory_evidence_refs,
  required_missing_information, allowed_alternative_explanations, boundary.
- `EvidenceBundle`: option_id and exact evidence_refs. Optional factual/history
  bundles are singleton refs; full values stay in the shared catalog.
- `ComparisonContext`: comparison_id, authorized_scopes, required factual_refs.
- `FinalizationOptions`: claim_scope, comparison_context, factual_options,
  historical_options, claim_options.

IDs are canonical-content SHA-256 prefixes with a collision check. They are
internal selection identifiers, not new Evidence IDs or persisted financial facts.
Input order does not change IDs or expansion. The catalog remains identical
through all formatting and semantic attempts.

The internal model output has only:

```json
{
  "factual_option_ids": [],
  "historical_option_ids": [],
  "claim_option_ids": ["<one of this run's exposed claim IDs>"],
  "question_kind": "need_contemporaneous_records"
}
```

A per-run Pydantic `Literal` type constrains each category. Both SDK wire schema
and local strict parser use that **same dynamic type**, not separately edited
wire enums. A singleton Literal is represented as JSON Schema `const`, equivalent
to a one-member enum. Empty option sets allow only an empty array. Public field
capacity limits are reused. Unknown/unexposed/cross-category IDs and extra raw-ref,
scope or financial fields reject; the application never guesses their meaning.

After ID lookup, Python fills the existing production `ReviewSelection` fields.
That public type, its `Hypothesis` fields, wording templates and all financial
values remain unchanged. The model no longer fills raw refs, roles, mandatory
missing fields or alternatives in Stage 2. Stage 1 may discuss candidate refs
in internal analysis, but its prose does not authorize an output relationship.

## Evidence roles, comparison and uncertainty

Claim admission still reuses `build_claim_contract` / `supports_claim`:

- Price influence requires an actual, complete, exact-scoped authoritative Path
  pattern, not a convenient tag on an outcome or a price calculation here.
- A reported reason requires a complete own-scoped, actually-read user-reason
  note. Insufficient/unread/wrong-scope testimony generates no such option.
- Price support is the eligible Path bundle. Known valid own plan notes are
  mandatory counter-material. If a required plan has not been read, that option
  is unavailable. Retrieval stance alone never assigns a relationship.
- Each non-unknown option includes the contract-required missing marker and
  fixed allowed alternatives. The model cannot omit them. Counter-material
  retains the legacy field name; a plan is not necessarily logical negation.

All direct claim refs have the claim's four-part scope; support and contrary
sets are disjoint. Every generated bundle is checked before model exposure,
then the final expanded object is independently checked again. Invalid generated
bundles fail as application errors, not as requests for the model to repair data.

Comparison context retains the own outcome and, when a comparison is active,
the authorized counterpart outcome and registered comparison. Those must have
completed receipts. Optional A/B descriptive facts remain selectable separately.
B decisions, phases and market/path records never enter A explanation options.
Historical comparisons use their own category and cannot become actual facts
or direct motive evidence. No copying of counterpart actions is suggested.

`unknown` is now a **terminal uncertainty option** with empty support/contrary
arrays. Observed factual basis remains in the fact section, so uncertainty about
motives does not erase a meaningful A/B comparison. Without admitted testimony,
it requests contemporaneous plan/reason information; with testimony, independent
confirmation remains missing. Its alternative is `unknown`. It cannot be combined
with supported explanation options in the same selection. The public schema
stays compatible; this stricter meaning is internal option construction.

Supported inference options still exist when real evidence permits them. The
default Synthetic A does not acquire a positive Path tag merely to avoid unknown.
The existing positive-Path fixture verifies that a legal limited inference passes.
“上涨后追加”, possible price influence, reported reason and a proven psychological
motive remain different levels; no new “贪婪/追涨/FOMO” fact can be authored here.

## Retry and failure boundaries

| Layer | Budget / behavior |
| --- | --- |
| Transport | Existing SDK/provider behavior unchanged. No application transport loop. |
| Format/schema | At most one retry across the entire finalizer instance. No fence stripping, substring extraction or partial acceptance. Invalid option IDs are also strict typed output failures. |
| Semantic correction | At most one correction, only for duplicate selections or terminal-uncertainty/other-option conflicts. Same catalog/type/scope, no tools or retrieval. |

Neither budget resets the other. Maximum Stage 2 model invocations remain three
(initial + one format + one semantic), excluding SDK transport attempts. An
exhausted budget returns unavailable, never Stage 1 prose. Every attempt audits
the same Stage 1 receipts; the expanded result must pass the original validator.
Scope/role/support failures after deterministic expansion are not repairable by
model reselection: they fail closed as a corrupted bundle/application boundary.
`verify_selection`, `_audit`, `CLAIM_RULES` and support predicates were not relaxed.

## Cost and safe observability

Fixed Synthetic QA context: 31 records, 29 total selection options (including
one uncertainty option). With the same receipts and offline analysis text:

| Serialized component | d532f5e | This implementation |
| --- | ---: | ---: |
| Stage 2 input JSON bytes | 34,323 | 33,484 |
| Stage 2 schema JSON bytes | 6,652 | 1,748 |

These are byte counts, **not** measured live tokens, latency or paid usage.
No N-options × full-evidence duplication. Existing analysis/input bounds remain.
Preflight validation costs a small linear pass over bundles, accepted here for
correctness; caching/large-catalog budgeting belongs to later hardening.

Synthetic-only QA reports prevalidated scope/options/kinds, sanitized selected
IDs, exact expansion, typed rejection, format retry usage and semantic correction
usage. Accepted quality facts copy outcomes and compact registered differences
so humans can assess substance, not just IDs/PASS. Unknown IDs are fingerprinted;
real subject/account contexts refuse these diagnostics. No key/header/environment
dump, raw Stage 1 text, note body or full model response persistence is added.
Probe/ladder diagnostics are retained, not used by production or rerun here.

## Verification and live acceptance

Tests cover scope dimensions, foreign comparison material, disjoint/uncertainty
roles, option preflight, all supported claim combinations, valid limited inference,
missing/unread/incomplete testimony, dynamic wire/local agreement, invented IDs,
raw-ref injection, deterministic expansion, required missing data, historical
category separation, independent retries, tool/retrieval attempts, corrupted
expansion and original validator failures. QA observer cleanup and counters are
tested offline; fake/no HTTP evidence cannot qualify as a real QA PASS.

Local verification: **118 targeted tests passed** (19.51s); **751 full Python
tests passed** (365.50s), versus the 727-test baseline. No warnings were reported.
`git diff --check` passed. The CLI help and `--prepare-only` entry were checked;
the latter prepared 31 fixed Synthetic records and is explicitly not live E2E.
No Desktop/runtime response contract changed, so no frontend changes or builds
were needed for this Agent-only checkpoint.

Public production schema and Stage 1/tool/validator/audit AST are unchanged.
Financial semantics changed = **NO**. Analysis strategy changed = **NO**.
Only finalization authorization/selection and QA presentation changed.

Real post-change DeepSeek: **NOT RUN / awaiting user Terminal**. Do not request
or persist credentials. Run first in the existing key-loaded Terminal:

```bash
cd /Users/cccc/Projects/personal-investment-twin
.venv/bin/python scripts/qa_decision_review_deepseek.py --repeat 2
```

Only after main **2/2 PASS**, run:

```bash
.venv/bin/python scripts/qa_decision_review_deepseek.py --adversarial-suite --repeat 2
```

Require **6/6 PASS**, plus human review of actual grounded comparison, no
copy-trading advice, no unsupported psychological fact, valid refs and explicit
missing information. Inspect both retry counts; repeated reliance on correction
is not “fully stable”. Preserve all trials, never run until a favorable sample.
This small acceptance matrix is not a statistical reliability guarantee.

**Freeze = NOT READY** until those new live results and quality checks are supplied.
The previous 1/2 main outcome cannot certify this checkpoint. Stop at this boundary;
no UI, runtime sidecar, other product capability or framework work follows.
