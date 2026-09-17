"""Hostile-protocol fuzz: the sidecar must answer every malformed request and
survive.  Checks two properties per corpus request:

1. The process boundary holds — handle_request/run never raises out.
2. NaN/Infinity payloads (accepted by json.loads by default!) never reach
   json.dumps(allow_nan=False) inside run(): a result containing NaN would
   raise OUTSIDE the per-request try/except and kill the sidecar process.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toujing_core_runtime.protocol import handle_request, _product_methods, run

BASE = {"protocol_version": "1", "request_id": "fuzz", "method": "", "params": {}}

HUGE = "A" * 100_000


def hostile_params() -> list[tuple[str, object]]:
    cases: list[tuple[str, object]] = [
        ("empty", {}),
        ("null", None),
        ("list", [1, 2, 3]),
        ("string", "x"),
        ("nan_cash", {"subject_id": "f", "account_id": "f", "display_name": "f", "initial_cash": float("nan")}),
        ("inf_cash", {"subject_id": "f", "account_id": "f", "display_name": "f", "initial_cash": float("inf")}),
        ("neg_cash", {"subject_id": "f", "account_id": "f", "display_name": "f", "initial_cash": -5}),
        ("numeric_subject", {"subject_id": 123, "account_id": ["x"], "display_name": None, "initial_cash": "abc"}),
        ("traversal_path", {"file_path": "/etc/passwd", "subject_id": "f", "account_id": "f"}),
        ("dotdot_path", {"file_path": "../../secret.csv", "subject_id": "f", "account_id": "f"}),
        ("huge_string", {"subject_id": HUGE, "account_id": HUGE, "display_name": HUGE}),
        ("deep_nest", {"a": {"b": {"c": {"d": [1, 2, {"e": "f"}]}}}}),
        ("bool_params", {"subject_id": True, "account_id": False}),
        ("episode_id_injection", {"subject_id": "f", "account_id": "f", "episode_id": "../../x"}),
        ("tags_wrong_type", {"subject_id": "f", "account_id": "f", "episode_id": "e", "tags": "not-a-list"}),
        ("tags_nan", {"subject_id": "f", "account_id": "f", "episode_id": "e", "tags": [1.5, None]}),
        ("strategy_nan", {"strategy": {"stop_loss_pct": float("nan")}, "universe": "synthetic"}),
        ("sensitivity_nan", {"strategy_id": "toujing_t1_breakout_trend", "parameter": "stop_loss_pct", "values": [float("nan"), float("inf"), -1]}),
        ("sensitivity_junk", {"strategy_id": "nope", "parameter": "nope", "values": "abc"}),
        ("compare_nan", {"subject_id": "f", "account_id": "f", "episode_id": "e"}),
        ("mismatched", {"subject_id": None, "account_id": 3.14, "episode_id": ["e"]}),
    ]
    out: list[tuple[str, object]] = []
    for method in (
        "ingestion.preview_trade_csv", "ingestion.commit_trade_import",
        "market.preview_price_csv", "market.commit_price_import",
        "account.list", "account.get_data_status", "investments.list", "episode.get",
        "strategy_comparison.get", "strategy_simulation.run_custom",
        "strategy_sensitivity.run", "data.delete_account",
        "review.context", "review.start", "review.poll", "review.add_note",
        "review_pack.get", "episode_tags.set",
        "compare.export_share", "compare.import_share", "compare.list_shares", "compare.revoke_share",
    ):
        for name, params in cases:
            out.append((f"{method}:{name}", params))
    return out


def run_suite() -> tuple[int, int, int]:
    failures = 0
    total = 0
    core_errors = 0
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "fuzz.sqlite3")
        methods, product = _product_methods(db_path)
        try:
            for name, params in hostile_params():
                total += 1
                request = {**BASE, "request_id": f"r{total}", "method": name.split(":", 1)[0], "params": params}
                try:
                    response, _ = handle_request(request, methods)
                except Exception as exc:
                    print(f"ESCAPED HANDLER {name}: {type(exc).__name__}: {exc}")
                    failures += 1
                    continue
                if response.get("ok"):
                    continue
                code = (response.get("error") or {}).get("code")
                if code == "core_error":
                    core_errors += 1
                    message = (response.get("error") or {}).get("message", "")
                    print(f"core_error (untyped) {name}: {message[:120]}")
            # NaN must also survive the full run() serialization path.
            lines = []
            for index, (name, params) in enumerate(hostile_params()[:40]):
                lines.append(json.dumps({**BASE, "request_id": f"s{index}", "method": name.split(":", 1)[0], "params": params}))
            stdin = io.StringIO("\n".join(lines) + "\n")
            stdout = io.StringIO()
            try:
                run(stdin, stdout, db_path=db_path)
            except ValueError as exc:
                # json.dumps(allow_nan=False) raising outside the handler is
                # exactly the sidecar-killer this check exists for.
                print(f"PROCESS KILLED BY RESULT SERIALIZATION: {exc}")
                failures += 1
        finally:
            if product is not None and hasattr(product, "close"):
                product.close()
    print(f"{total} hostile requests, {failures} boundary escapes, {core_errors} untyped core_error responses")
    return total, failures, core_errors


def main() -> int:
    _, failures, _ = run_suite()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
