"""Offline packaged-process acceptance. No credentials or live provider calls.

Uses only the registered Synthetic showcase in a new temporary database. Checks
bootstrap, local quote-library readiness and repeated account-context access.
Does not synthesize a model response or claim live-model answer acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import selectors
import subprocess
import tempfile
import time


def check(binary: Path) -> None:
    if not binary.is_file():
        raise ValueError("packaged_binary_missing")
    with tempfile.TemporaryDirectory(prefix="toujing-agent-ui-offline-") as folder:
        process = subprocess.Popen([str(binary.resolve()), "--db-path", str(Path(folder) / "synthetic.sqlite3")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=folder)
        sequence = 0

        def call(method: str, params: dict, seconds: int = 30):
            nonlocal sequence
            sequence += 1
            request_id = f"offline-ui-{sequence}"
            start = time.monotonic()
            process.stdin.write(json.dumps({"protocol_version": "1", "request_id": request_id,
                "method": method, "params": params}) + "\n")
            process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(seconds):
                    raise RuntimeError(f"{method}:timeout")
            line = process.stdout.readline()
            if not line:
                # This process has only a fresh Synthetic database and no keys.
                # Keep loader diagnostics distinguishable from protocol errors.
                process.wait(timeout=5)
                raise RuntimeError(f"{method}:process_exited:{process.returncode}:"
                    f"{process.stderr.read()[-5000:]}")
            reply = json.loads(line)
            if reply.get("request_id") != request_id or reply.get("ok") is not True:
                raise RuntimeError(f"{method}:invalid_reply")
            print(json.dumps({"method": method, "seconds": round(time.monotonic() - start, 3), "ok": True}), flush=True)
            return reply["result"]

        try:
            assert call("runtime.handshake", {}, 90)["protocol_version"] == "1"
            quotes = call("quotes.status", {})
            assert quotes.get("available") is True and quotes.get("provider") == "akshare"
            scope = {"scope_kind": "account", "subject_id": "SYN_STUDY_SHOWCASE",
                "account_id": "SYN_STUDY_SHOWCASE", "data_mode": "synthetic_showcase"}
            first = call("review.context", scope, 300)
            second = call("review.context", scope, 300)
            assert first["scope"] == second["scope"] == scope
            assert first["source_fingerprint"] == second["source_fingerprint"]
            assert first["conversation_turns"] == second["conversation_turns"] == []
            assert first["record_refs"] and second["record_refs"] == first["record_refs"]
            assert "_owned_analysis" not in json.dumps(first)
            call("runtime.shutdown", {})
            process.wait(timeout=15)
            assert process.returncode == 0
            print(json.dumps({"offline_packaged_acceptance": "PASS", "live_model_calls": 0}), flush=True)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    check(parser.parse_args().binary)
