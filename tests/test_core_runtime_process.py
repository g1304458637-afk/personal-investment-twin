from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from toujing_core_runtime import protocol

ROOT = Path(__file__).resolve().parents[1]


def _request(request_id: str, method: str) -> str:
    return json.dumps(
        {
            "protocol_version": protocol.PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "params": {},
        },
        separators=(",", ":"),
    )


def test_development_runtime_is_persistent_and_protocol_clean() -> None:
    input_text = "\n".join(
        [
            _request("handshake", "runtime.handshake"),
            _request("health", "runtime.health"),
            _request("smoke", "runtime.core_smoke"),
            _request("shutdown", "runtime.shutdown"),
        ]
    ) + "\n"
    completed = subprocess.run(
        [sys.executable, "-m", "toujing_core_runtime"],
        input=input_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=45,
        check=True,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [item["request_id"] for item in responses] == [
        "handshake",
        "health",
        "smoke",
        "shutdown",
    ]
    assert all(item["ok"] for item in responses)
    assert completed.stderr == ""
    assert responses[2]["result"]["final_value"] == 103_855.9
