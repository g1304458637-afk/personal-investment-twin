"""Verify dev and packaged runtimes expose identical protocol/core facts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUESTS = tuple(
    {
        "protocol_version": "1",
        "request_id": request_id,
        "method": method,
        "params": {},
    }
    for request_id, method in (
        ("handshake", "runtime.handshake"),
        ("health", "runtime.health"),
        ("smoke", "runtime.core_smoke"),
        ("shutdown", "runtime.shutdown"),
    )
)


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None):
    completed = subprocess.run(
        command,
        input="".join(json.dumps(item, separators=(",", ":")) + "\n" for item in REQUESTS),
        text=True,
        capture_output=True,
        cwd=cwd,
        env=environment,
        timeout=90,
        check=True,
    )
    if completed.stderr:
        raise SystemExit(f"runtime wrote diagnostics during valid smoke: {completed.stderr}")
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    if len(responses) != len(REQUESTS) or not all(item.get("ok") for item in responses):
        raise SystemExit(f"runtime smoke failed: {responses}")
    return responses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"packaged runtime missing: {binary}")

    dev = _run([sys.executable, "-m", "toujing_core_runtime"], cwd=ROOT)
    with tempfile.TemporaryDirectory() as directory:
        package_env = {"PATH": "", "HOME": directory, "TMPDIR": directory}
        packaged = _run([str(binary)], cwd=Path(directory), environment=package_env)
    if dev[0]["result"]["protocol_version"] != packaged[0]["result"]["protocol_version"]:
        raise SystemExit("dev/package protocol versions differ")
    if dev[2]["result"] != packaged[2]["result"]:
        raise SystemExit("dev/package deterministic core smoke differs")
    print(json.dumps(packaged[2]["result"], sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
