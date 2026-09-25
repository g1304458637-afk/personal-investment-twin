"""Hostile-protocol gate: every runtime method must answer malformed params
with a typed error — never an escaping exception, and a NaN payload must
never reach the allow_nan=False serializer outside the handler (that would
kill the sidecar process for every later request)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fuzz_protocol import run_suite


def test_hostile_protocol_corpus_stays_inside_the_boundary():
    total, failures, core_errors = run_suite()
    assert total > 400
    assert failures == 0
    # Handlers either accept or raise typed errors; a bare core_error means a
    # malformed param reached an unguarded code path.
    assert core_errors == 0


def test_nan_result_fails_one_request_without_killing_the_process(monkeypatch):
    """The regression the serialization guard exists for: a handler that
    returns NaN must produce one serialization_error response, and the serve
    loop must keep answering later requests."""
    import io
    import json

    import toujing_core_runtime.protocol as protocol_module
    from toujing_core_runtime.protocol import run

    def nan_method(params: object) -> dict[str, object]:
        return {"value": float("nan")}

    def healthy_method(params: object) -> dict[str, object]:
        return {"value": 1.0}

    # run() builds its own method map from the module-level _METHODS.
    monkeypatch.setattr(protocol_module, "_METHODS", {
        "runtime.nan": nan_method, "runtime.healthy": healthy_method,
    })
    requests = "\n".join([
        json.dumps({"protocol_version": "1", "request_id": "r1", "method": "runtime.nan", "params": {}}),
        json.dumps({"protocol_version": "1", "request_id": "r2", "method": "runtime.healthy", "params": {}}),
    ]) + "\n"
    stdout = io.StringIO()
    run(io.StringIO(requests), stdout, db_path=None)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert len(lines) == 2, "the serve loop must survive and answer the next request"
    assert lines[0]["ok"] is False
    assert lines[0]["error"]["code"] == "serialization_error"
    assert lines[0]["request_id"] == "r1"
    assert lines[1]["ok"] is True
    assert lines[1]["result"] == {"value": 1.0}
