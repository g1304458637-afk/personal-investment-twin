"""Limited live QA: Synthetic facts + public quotes/search. Never prints credentials."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SERVICE = "com.toujing.desktop.model-service"


def _keychain(account):
    result = subprocess.run(["/usr/bin/security", "find-generic-password",
                             "-s", SERVICE, "-a", account, "-w"],
                            capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _emit(payload, secrets):
    text = json.dumps(payload, ensure_ascii=False)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    print(text, flush=True)


def quote_smoke():
    import time
    from src.agents.public_research import AkshareQuoteClient, quotes_status, reset_public_caches
    reset_public_caches()
    status = quotes_status()
    client = AkshareQuoteClient()
    matches = client.identify("贵州茅台")
    ids = [item["security_id"] for item in matches]
    ohlcv = {"ok": False}
    snapshot = {"ok": False, "reason": None}
    for attempt in range(3):
        try:
            bars = client.daily_ohlcv("600519", "2026-09-01", "2026-09-05", "qfq")
            ohlcv = {"ok": True, "rows": int(len(bars)), "last_date": str(bars.iloc[-1]["日期"]),
                     "adjust": "qfq", "timezone": "Asia/Shanghai"}
            break
        except Exception as exc:
            ohlcv = {"ok": False, "error_type": type(exc).__name__}
            time.sleep(1.2)
    for attempt in range(3):
        try:
            raw = client.snapshot("600519")
            snapshot = {"ok": raw is not None and getattr(raw, "empty", False) is False,
                        "type": type(raw).__name__}
            if snapshot["ok"]:
                break
        except Exception as exc:
            snapshot = {"ok": False, "error_type": type(exc).__name__, "reason": "quotes_unavailable"}
            time.sleep(1.2)
    return {
        "quotes_status": status,
        "identify_moutai": ids,
        "listed_not_synthetic": "SHSE:600519" in ids and not any("SYN_" in item for item in ids),
        "ohlcv": ohlcv,
        "snapshot": snapshot,
    }


def search_probe(key):
    from src.agents.public_research import probe_search_connection
    return probe_search_connection({"_desktop_bocha_key": key})


async def conversation_qa(model_key, search_key):
    import src.agents.account_conversation as conversation_module
    from src.agents.dsa_conversation import run_dsa_conversation
    from src.agents.investment_coach import create_model_runtime
    from src.agents.public_research import attach_public_research, reset_public_caches
    from src.demo import showcase
    from toujing_core_runtime.account_review import AccountReviewService
    from toujing_core_runtime.chat_archive import ChatArchive

    service = AccountReviewService(SimpleNamespace())
    try:
        context = service._source({"scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
                                   "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase"})
    finally:
        service.close()
    reset_public_caches()
    attach_public_research(context, {
        "_desktop_search_enabled": bool(search_key),
        "_desktop_bocha_key": search_key,
    })
    runtime = create_model_runtime(environment={"DEEPSEEK_API_KEY": model_key})
    questions = ["K线实体、影线、成交量怎么看？",
                 "SHSE:600519 最近几个交易日的公开日线收盘是怎样的？不要把它说成我的持仓。"]
    if search_key:
        questions.append("贵州茅台最近公开发生了什么？请列出可点来源。")
    history, results = [], []
    try:
        for question in questions:
            conversation = None if not history else {"trust": "untrusted_not_evidence",
                "purpose": "resolve_references_in_current_question_only", "history": history[-3:]}
            result = await asyncio.wait_for(run_dsa_conversation(
                question, context, runtime=runtime, conversation_context=conversation), timeout=150)
            public = {
                "question": question,
                "answer": [paragraph["text"]["zh"] for paragraph in result["answer"]["paragraphs"]],
                "executed_tools": result["executed_tools"],
                "public_read_refs": result.get("public_read_refs") or [],
                "public_sources": result.get("public_sources") or [],
                "verification": result["verification"],
                "engine": result.get("engine"),
            }
            results.append(public)
            history.append({"user_question": question,
                            "validated_structured_answer": result["answer"]})
        follow = await asyncio.wait_for(run_dsa_conversation(
            "刚才说的实体和影线有什么区别？", context, runtime=runtime,
            conversation_context={"trust": "untrusted_not_evidence",
                                  "purpose": "resolve_references_in_current_question_only",
                                  "history": history[-3:]}), timeout=150)
        results.append({
            "question": "刚才说的实体和影线有什么区别？",
            "answer": [paragraph["text"]["zh"] for paragraph in follow["answer"]["paragraphs"]],
            "executed_tools": follow["executed_tools"],
            "verification": follow["verification"],
        })
        with tempfile.TemporaryDirectory(prefix="toujing-public-qa-") as directory:
            archive = ChatArchive(Path(directory) / "synthetic.agent-chat.sqlite3")
            product = SimpleNamespace(repo=SimpleNamespace(path=Path(directory) / "synthetic.sqlite3"))
            stored = AccountReviewService(product)
            stored.archive = archive
            stored.completed["account_inference_qa"] = {
                "scope": context.scope, "source_fingerprint": "qa",
                "question": questions[0], "history": [],
                "result": {**results[0], "inference_id": "account_inference_qa",
                           "invalidated": False, "scope": context.scope, "answer": history[0]["validated_structured_answer"]},
            }
            archive.save(context.scope, stored.completed)
            restored = AccountReviewService(product)
            restored.archive = ChatArchive(Path(directory) / "synthetic.agent-chat.sqlite3")
            loaded = restored.archive.read(context.scope)
            restore_ok = (loaded["account_inference_qa"]["result"]["answer"]
                          == history[0]["validated_structured_answer"])
            restored.close()
            stored.close()
        return results, restore_ok
    finally:
        await runtime.model._get_client().close()


def main():
    logging.disable(logging.CRITICAL)
    secrets = []
    model_key = _keychain("deepseek")
    search_key = _keychain("bocha")
    secrets.extend([item for item in (model_key, search_key) if item])
    try:
        quotes = quote_smoke()
        _emit({"public_quotes": quotes, "not_mixed_with_synthetic_fills": True}, secrets)
        if search_key:
            probe = search_probe(search_key)
            _emit({"bocha_test_query": "上海证券交易所", "connected": probe.get("connected"),
                   "reason": probe.get("reason")}, secrets)
        else:
            _emit({"bocha": "not_configured_in_keychain", "search_skipped": True}, secrets)
        if not model_key:
            _emit({"qa_status": "FAIL", "reason": "qa_model_not_configured"}, secrets)
            return 1
        if not quotes["listed_not_synthetic"] or not quotes["ohlcv"].get("ok"):
            _emit({"qa_status": "FAIL", "reason": "public_quotes_unavailable"}, secrets)
            return 1
        results, restore_ok = asyncio.run(conversation_qa(model_key, search_key))
        _emit({"conversation": results, "restart_restore_without_model_call": restore_ok,
               "qa_status": "PASS" if restore_ok else "FAIL"}, secrets)
        return 0 if restore_ok else 1
    except Exception as exc:
        safe = str(exc) if type(exc).__module__.startswith("src.agents") else type(exc).__name__
        _emit({"qa_status": "FAIL", "reason": safe}, secrets)
        return 1


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.exit(main())
