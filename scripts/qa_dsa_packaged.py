"""Live packaged DSA smoke and restart QA, fixed Synthetic account only.

No real repository paths, raw receipts or credential output. Uses the existing
desktop Keychain item; temporary answer storage is destroyed after verification.
"""
import argparse
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.demo.showcase import SUBJECT_ID, ACCOUNT_ID


def request_timeout(method):
    # Match the desktop's distinct bootstrap, context and ordinary IPC budgets.
    return {"runtime.handshake": 90, "review.context": 300}.get(method, 30)


def decode_response(line, request_id):
    response = json.loads(line)
    if not isinstance(response, dict) or response.get("request_id") != request_id:
        raise RuntimeError("packaged_response_mismatch")
    return response


def main(binary):
    key_read = subprocess.run(["/usr/bin/security", "find-generic-password", "-s",
        "com.toujing.desktop.model-service", "-a", "deepseek", "-w"],
        capture_output=True, text=True, timeout=20)
    search_read = subprocess.run(["/usr/bin/security", "find-generic-password", "-s",
        "com.toujing.desktop.model-service", "-a", "bocha", "-w"],
        capture_output=True, text=True, timeout=20)
    if key_read.returncode or not key_read.stdout.strip():
        raise RuntimeError("keychain_unavailable")
    key = key_read.stdout.strip()
    search_key = search_read.stdout.strip() if search_read.returncode == 0 else None
    scope = {"scope_kind": "account", "subject_id": SUBJECT_ID, "account_id": ACCOUNT_ID,
             "data_mode": "synthetic_showcase"}
    with tempfile.TemporaryDirectory(prefix="toujing-dsa-package-qa-") as directory:
        database = str(Path(directory) / "synthetic.sqlite3")
        def launch():
            return subprocess.Popen([str(binary.resolve()), "--db-path", database],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, cwd=directory)
        request_sequence = 0
        def call(process, method, params):
            nonlocal request_sequence
            request_sequence += 1
            request_id = f"qa-{request_sequence}"
            started = time.monotonic()
            process.stdin.write(json.dumps({"protocol_version": "1", "request_id": request_id,
                "method": method, "params": params}) + "\n")
            process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=request_timeout(method)):
                    print(json.dumps({"failed_method": method,
                        "timeout_seconds": request_timeout(method)}), flush=True)
                    raise RuntimeError("packaged_protocol_timeout")
            line = process.stdout.readline()
            response = decode_response(line, request_id)
            if not response.get("ok"):
                print(json.dumps({"failed_method": method,
                    "error_code": response.get("error", {}).get("code")}), flush=True)
                raise RuntimeError("packaged_request_failed")
            if method == "review.start" and time.monotonic() - started >= 30:
                raise RuntimeError("packaged_start_exceeds_desktop_deadline")
            if method != "review.poll":
                print(json.dumps({"method": method, "seconds": round(time.monotonic() - started, 2)}), flush=True)
            return response["result"]
        def stop(process):
            try:
                try:
                    call(process, "runtime.shutdown", {})
                    process.wait(timeout=15)
                except (RuntimeError, subprocess.TimeoutExpired, BrokenPipeError, ValueError):
                    # Cleanup must not hide the original timed-out method or
                    # mistake a late earlier response for a shutdown receipt.
                    pass
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdin.close()
                process.stdout.close()
        process = launch()
        try:
            handshake = call(process, "runtime.handshake", {})
            assert handshake.get("protocol_version") == "1"
            quotes = call(process, "quotes.status", {})
            assert quotes.get("available") is True, "packaged_quotes_unavailable"
            assert quotes.get("provider") == "akshare"
            print(json.dumps({"quotes_status": "PASS", "provider": quotes.get("provider")}), flush=True)
            if search_key:
                probe = call(process, "search.test_connection", {"_desktop_bocha_key": search_key})
                print(json.dumps({"bocha_test_query": "上海证券交易所",
                                  "connected": probe.get("connected"),
                                  "reason": probe.get("reason")}).replace(search_key, "[REDACTED]"), flush=True)
            else:
                print(json.dumps({"bocha": "not_configured_in_keychain", "search_skipped": True}), flush=True)
            context = call(process, "review.context", scope)
            assert not context["conversation_turns"]
            job = call(process, "review.start", {**scope, "allow_model_review": True,
                "_desktop_model_key": key, "conversation_engine": "dsa",
                "answer_version": "account_conversation_answer_v2",
                "question": "你认为我为什么会有亏损？"})
            deadline = time.monotonic() + 170
            while time.monotonic() < deadline:
                reply = call(process, "review.poll", {**scope, "job_id": job["job_id"]})
                if reply["status"] != "running":
                    break
                time.sleep(1)
            assert reply["status"] == "complete", "packaged_analysis_not_complete"
            result = reply["result"]
            assert result["engine"] == "dsa_react_toujing_v1"
            assert result["grounding_adapter"] == "explicit_paragraph_verdict_v1"
            assert result["verification"] == "receipts_and_grounding_review_v1"
            assert not result["session_only"]
            assert set(result["read_refs"]).issubset(context["record_refs"])
            assert result["source_fingerprint"] == context["source_fingerprint"]
            text = json.dumps({"packaged_dsa": "PASS", "answer": [p["text"]["zh"]
                for p in result["answer"]["paragraphs"]]}, ensure_ascii=False).replace(key, "[REDACTED]")
            if search_key:
                text = text.replace(search_key, "[REDACTED]")
            print(text, flush=True)
        finally:
            stop(process)
        process = launch()
        try:
            call(process, "runtime.handshake", {})
            restored = call(process, "review.context", scope)
            turns = restored["conversation_turns"]
            assert len(turns) == 1 and turns[0]["result"]["answer"] == result["answer"]
            assert turns[0]["result"]["inference_id"] == result["inference_id"]
            assert not turns[0]["result"]["invalidated"]
            print(json.dumps({"restart_restore_without_model_call": "PASS", "qa_status": "PASS"}), flush=True)
        finally:
            stop(process)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    try:
        main(args.binary)
    except Exception as exc:
        reason = str(exc) if str(exc) in {"keychain_unavailable", "packaged_protocol_timeout",
            "packaged_response_mismatch",
            "packaged_request_failed", "packaged_analysis_not_complete",
            "packaged_start_exceeds_desktop_deadline", "packaged_quotes_unavailable"} else None
        print(json.dumps({"qa_status": "FAIL", "error_type": type(exc).__name__, "reason": reason}), flush=True)
        sys.exit(1)
