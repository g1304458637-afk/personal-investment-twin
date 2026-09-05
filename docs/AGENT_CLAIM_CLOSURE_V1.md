# Evidence-grounded Agent v1: claim closure review

2026-09-05. No financial method, final output schema, provider, tool schema,
Compare, or two-stage workflow migration. Live acceptance remains separate.

## Focused references and decisions

| Reference | KEEP / ADOPT | LATER / REJECT |
| --- | --- | --- |
| [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/) and [runner lifecycle](https://openai.github.io/openai-agents-python/running_agents/) | KEEP native function execution, strict schema validation, hooks and bounded runs. ADOPT structured failure details and an explicit final validation boundary. | Do not move working domain rules into decorators merely for appearance. Tripwires halt; they do not establish financial support or automatically repair semantic output. |
| [PydanticAI output validators](https://pydantic.dev/docs/ai/core-concepts/output/#output-validators) and [retries](https://pydantic.dev/docs/ai/core-concepts/retries/) | ADOPT the separation of tool, transport, format and semantic validation concerns. Our typed output then deterministic validator fits this pattern. | Framework migration not justified. `ModelRetry` is useful only when a correction can be proven safe; it cannot make insufficient evidence sufficient. Native output is required for a genuinely no-tools finalizer. |
| [LangGraph state](https://docs.langchain.com/oss/python/langgraph/graph-api), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance) | KEEP explicit analysis → finalization → receipt → domain validation boundaries. | Durable graph/checkpointer/HITL infrastructure waits for resumable workflow requirements. Two sequential model stages do not justify it. |
| [DeepEval Faithfulness](https://deepeval.com/docs/metrics-faithfulness), [Tool Correctness](https://deepeval.com/docs/metrics-tool-correctness), [Argument Correctness](https://deepeval.com/docs/metrics-argument-correctness), [Task Completion](https://deepeval.com/docs/metrics-task-completion), [Step Efficiency](https://deepeval.com/docs/metrics-step-efficiency) | ADOPT an eval taxonomy: tool/argument validity, retrieval completeness, provenance, claim legality, policy compliance, task completion and step cost. | LLM-judged faithfulness/arguments/task/efficiency are offline quality signals, not production truth gates. No eval dependency added. |

Installed runtime inspected: `openai-agents 0.22.0`, `openai 3.7.0`,
`pydantic 2.13.5`. `agents/agent_output.py` uses strict, non-partial typed JSON
validation. `run_internal/guardrails.py` halts on output tripwires; function-tool
input/output guards run around actual execution. `run_internal/model_retry.py`
handles model operational retries, not Toujing domain support. Current official
docs and installed code agree on these boundaries; no newer API was assumed.

Toujing uses no SDK session here. It persists only its accepted, rendered result,
after domain validation. Moving validation inside SDK output guardrails would
not remove the need to audit Stage 1 receipts, nor improve this bounded flow.

## What is known, and what is not

User-supplied live evidence confirms Stage 1, Stage 2 strict output and receipt
audit PASS, followed by `ReviewVerificationError`. It does **not** include the
rejected structured candidate or exception code. Therefore the exact historical
live JSON path/kind/refs cannot honestly be reconstructed from that evidence.
This review does not label a locally constructed candidate as the live output.

An exact offline reproduction on the unchanged default pair is:

- path: `$.possible_explanations[0].supporting_evidence_refs`
- kind: `price_influence_possible`
- supporting ref: `do_c2fae39f3f4ccfce62c217f712238a3586fdca9c352e4adb56580eb0d7d858fe`
- contradictory refs: `[]`; alternatives: `[prior_staged_plan]`
- missing information: `[contemporaneous_plan]`
- rejection: `evidence_does_not_support_hypothesis`

That ref is an add-position **decision**, not an authoritative positive-move
**Path relation**. The default pair does not emit the required Path tag under
the frozen observation-window contract. This rejection is correct. The existing
alternate-timestamp fixture does emit the real relation and passes; no tag or
financial formula is invented to make the default pair pass.

Proven local defects, distinct from the unobserved live candidate:

1. Support validation checked tag + subject/account but omitted type, complete
   availability, exact Episode/instrument and embedded authoritative Path identity.
2. Duplicate catalog refs could let a note overwrite the required outcome.
   Unknown note kinds were automatically classified as reasons.
3. Finalizer and validator had no shared machine-readable eligibility view.
4. Failure reporting omitted the rejected JSON path and semantic relationship.

These are validator/catalog/contract-boundary gaps, not a provider failure or
evidence that the strict final schema needs changing.

## Minimal correction and claim hierarchy

`src/agents/claim_contract.py` shares predicates between model-facing eligibility
and final validation. Eligibility includes only actually-read refs. Validation
independently checks them again. No new retrieval or financial computation.

| Layer | Permitted interpretation |
| --- | --- |
| Episode / decision facts | Copy authoritative recorded results and operations. |
| Path / same-stock descriptions | Describe existing deterministic observations, not motives. |
| `price_influence_possible` | Requires a complete, exact own-scoped authoritative positive-move Path record; remains tentative with alternatives and missing contemporaneous plan. |
| Reported plan / reason | Requires the corresponding scoped user testimony; never verifies past knowledge or a psychological cause. |
| Motive / causality / long-term skill | Not expressible as an established claim in the current schema. |

The legacy `contradictory_evidence_refs` also holds counter-material/alternative
plans, not necessarily logical negation. Required plans cannot vanish; support
and counter-material cannot be the same ref. Search stance is retrieval intent,
not a verdict about polarity. There is no new free-text motive classification.

Catalog collisions reject. Re-importing one's own same-scope share is explicitly
deduplicated in favor of local canonical facts, not allowed to overwrite them.
Unknown note kinds reject. The output schema and financial Evidence contract
remain unchanged; the Agent-level interpretation gate is stricter.

SDK transport retry remains SDK-owned. Existing finalizer format retry is still
at most one, without new tools. **No semantic retry** was added: the absent live
candidate does not establish a safely repairable mapping error, and unsupported
relationships must not be polished into apparent support.

## Acceptance and freeze

Local verification: 72 focused Agent/runtime/QA tests passed; full Python
regression **707 passed** (19 new semantic/diagnostic cases); `git diff --check`
passed. AST comparison confirmed tools, final schema and receipt audit unchanged.
Financial/Path/Compare/provider/Desktop source directories have no changes.

QA now prints a Synthetic-only `claim_evidence_rejected` event with the typed
candidate, exact path, kind, supporting/contrary refs, missing fields, rule and
allowlisted metadata. Unknown refs are fingerprinted; real-subject contexts
refuse diagnostic output. Stage 1 prose, keys and headers are never printed.

Run in the existing key-loaded Terminal:

```bash
.venv/bin/python scripts/qa_decision_review_deepseek.py
```

Then use `--question` for the three approved loss/profit, copy-trading and
greed/chasing prompts. Receipt/claim legality is deterministic; meaningful
explanation and task completeness still need inspection of the real outputs.

Freeze recommendation: **NOT READY pending exact live semantic acceptance and
the three adversarial runs**. Architecture direction is sound: domain support,
ownership and rendering stay custom; SDK execution/schema/hooks stay reused.
No graph framework, giant ontology or LLM judge belongs in the current hard gate.
Stage 1 kind-token presence remains an untrusted hint, not proof of a proposed
or supported claim; final financial/claim truth never relies on that hint.
