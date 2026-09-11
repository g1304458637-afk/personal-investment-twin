"""Live Synthetic-only conversational QA; never loads a real account repository.

Uses the existing provider factory. --keychain reads the existing desktop key
in memory, never prints it, and never writes prompts/responses/credentials.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(use_keychain, engine="legacy", question_override=None, public_research=False):
    import src.agents.account_conversation as conversation_module
    from src.agents.account_conversation import run_account_conversation
    if engine == "dsa":
        from src.agents.dsa_conversation import run_dsa_conversation as run_account_conversation
    from src.agents.investment_coach import create_model_runtime
    from src.demo import showcase
    from toujing_core_runtime.account_review import AccountReviewService
    # Resolve Synthetic facts before credentials. No user-controlled scope/path.
    service = AccountReviewService(SimpleNamespace())
    try:
        context = service._source({"scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
            "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase"})
    finally:
        service.close()
    if public_research:
        # Public market reads only; no Bocha key or real account is loaded.
        from src.agents.public_research import attach_public_research
        attach_public_research(context, {"_desktop_search_enabled": False})
    if use_keychain:
        key_result = subprocess.run(["/usr/bin/security", "find-generic-password",
            "-s", "com.toujing.desktop.model-service", "-a", "deepseek", "-w"],
            capture_output=True, text=True, timeout=20)
        if key_result.returncode:
            raise RuntimeError("qa_keychain_unavailable")
        key = key_result.stdout.strip()
    else:
        key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("qa_model_not_configured")
    runtime = create_model_runtime(environment={"DEEPSEEK_API_KEY": key})
    original_validate = conversation_module.validate_answer
    original_structured = conversation_module._structured
    import src.agents.dsa_conversation as dsa_module
    original_dsa_structured = dsa_module._structured

    async def diagnose_structured(runtime, instructions, payload, schema, access_allowed):
        verdict = await original_structured(runtime, instructions, payload, schema, access_allowed)
        if schema.__name__ == "GroundingVerdict" and not verdict.guides_valid:
            # Fixed Synthetic-only harness: emit only generated navigation,
            # never records, transport bodies, prompts or credentials.
            print(json.dumps({"synthetic_diagnostic": "guide_verdict",
                "candidate_guides": payload.get("candidate", {}).get("guides", []),
                "allowed_guides": payload.get("allowed_guides", {}),
                "question_answered": verdict.question_answered},
                ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
        return verdict

    dsa_module._structured = diagnose_structured
    from src.agents.structured_finalizer import FinalizerOutputSchema
    original_json = FinalizerOutputSchema.validate_json
    def diagnose_json(self, value):
        try:
            return original_json(self, value)
        except Exception:
            shape = {"synthetic_diagnostic": "strict_schema", "schema": self.output_type.__name__,
                "length": len(value), "first": value.lstrip()[:1], "last": value.rstrip()[-1:]}
            try:
                self.output_type.model_validate_json(value)
            except Exception as validation:
                if hasattr(validation, "errors"):
                    shape["errors"] = [{"type": item["type"], "loc": item["loc"]}
                        for item in validation.errors(include_input=False, include_url=False)][:8]
            print(json.dumps(shape, ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
            raise
    def diagnose(answer, records, allowed):
        try:
            return original_validate(answer, records, allowed)
        except conversation_module.ConversationError as exc:
            if str(exc) == "account_fact_source_required":
                print(json.dumps({"synthetic_diagnostic": "fact_binding", "details": exc.details,
                    "paragraphs": [{"kind": p.kind, "cited_kinds": [records[r]["kind"] for r in p.refs if r in records],
                        "text": p.text.zh[:500]} for p in answer.paragraphs]}, ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
            if str(exc) == "account_answer_number_not_in_sources":
                for paragraph in answer.paragraphs:
                    available = conversation_module._numbers([records[r]["value"] for r in paragraph.refs if r in records])
                    missing = conversation_module._numbers(paragraph.text.model_dump()) - available
                    if missing:
                        print(json.dumps({"synthetic_diagnostic": "number_binding", "missing_tokens": sorted(missing),
                            "paragraph": paragraph.text.zh[:500]}, ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
            raise
    conversation_module.validate_answer = diagnose
    FinalizerOutputSchema.validate_json = diagnose_json
    questions = ("为什么最大单一风险资产权重为61.97%，这代表了什么？",
                 "那你认为我为什么会有亏损？", "带我看看刚才提到的那轮投资，图应该怎么看？")
    if question_override:
        questions = (question_override,)
    history = []
    try:
        for question in questions:
            conversation = None if not history else {"trust": "untrusted_not_evidence",
                "purpose": "resolve_references_in_current_question_only", "history": history[-3:]}
            try:
                result = await asyncio.wait_for(run_account_conversation(question, context, runtime=runtime,
                    conversation_context=conversation), timeout=150)
            except conversation_module.ConversationError as exc:
                if str(exc).startswith("account_grounding:") and isinstance(exc.details, dict):
                    print(json.dumps({"synthetic_diagnostic": "grounding", "issues": exc.details.get("issues"),
                        "findings": [{"paragraph_index": f.get("paragraph_index"), "problem": f.get("problem", "")[:300]}
                            for f in exc.details.get("findings", [])[:5]]}, ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
                raise
            public = {"question": question, "answer": [p["text"]["zh"] for p in result["answer"]["paragraphs"]],
                "engine": result.get("engine", "legacy"),
                "guides": result["answer"]["guides"], "executed_tools": result["executed_tools"],
                "verification": result["verification"], "status": "PASS"}
            # Synthetic output only; defense-in-depth redaction of exact secret.
            print(json.dumps(public, ensure_ascii=False).replace(key, "[REDACTED]"), flush=True)
            history.append({"user_question": question, "validated_structured_answer": result["answer"]})
    finally:
        conversation_module.validate_answer = original_validate
        dsa_module._structured = original_dsa_structured
        FinalizerOutputSchema.validate_json = original_json
        await runtime.model._get_client().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keychain", action="store_true", help="Use the existing desktop credential, in memory only")
    parser.add_argument("--engine", choices=("legacy", "dsa"), default="legacy")
    parser.add_argument("--question", help="One question, still using only the fixed Synthetic account")
    parser.add_argument("--public-research", action="store_true", help="Enable public quotes; no web search credential is loaded")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(main(args.keychain, args.engine, args.question, args.public_research))
    except Exception as exc:
        # Only our own fixed validation codes; never SDK errors/HTTP bodies.
        safe = str(exc) if type(exc).__module__ == "src.agents.account_conversation" else type(exc).__name__
        print(json.dumps({"qa_status": "FAIL", "reason": safe}), flush=True)
        sys.exit(1)
