from __future__ import annotations

import io
import json

import pytest

from toujing_core_runtime import protocol


def request(method: str, *, request_id: str = "req-1", params=None):
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "request_id": request_id,
        "method": method,
        "params": {} if params is None else params,
    }


def test_handshake_describes_versioned_runtime() -> None:
    response, stop = protocol.handle_request(request("runtime.handshake"))
    assert response["ok"] is True
    assert response["request_id"] == "req-1"
    assert response["result"]["protocol_version"] == "1"
    assert response["result"]["runtime_version"] == protocol.RUNTIME_VERSION
    assert response["result"]["core_version"] == protocol.CORE_VERSION
    assert set(response["result"]["supported_methods"]) == set(protocol.SUPPORTED_METHODS)
    assert stop is False


def test_health_is_small_and_deterministic() -> None:
    first, _ = protocol.handle_request(request("runtime.health"))
    second, _ = protocol.handle_request(request("runtime.health"))
    assert first == second
    assert first["result"] == {"status": "ok", "runtime_version": "1.0.0"}


def test_core_smoke_calls_existing_financial_core_deterministically() -> None:
    first, _ = protocol.handle_request(request("runtime.core_smoke"))
    second, _ = protocol.handle_request(request("runtime.core_smoke"))
    assert first == second
    assert first["ok"] is True
    assert first["result"]["position_count"] == 1
    assert first["result"]["final_cash"] == pytest.approx(103_855.9)
    assert first["result"]["position_pnl"] == pytest.approx(3_855.9)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"not": "a request"}, "invalid_request"),
        (request("runtime.nope"), "unknown_method"),
        (request("runtime.health", params={"extra": True}), "invalid_params"),
    ],
)
def test_invalid_requests_are_structured(payload, code: str) -> None:
    response, stop = protocol.handle_request(payload)
    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert stop is False


def test_request_id_is_preserved() -> None:
    response, _ = protocol.handle_request(request("runtime.health", request_id="stable-id"))
    assert response["request_id"] == "stable-id"


def test_core_failure_is_structured(monkeypatch, capsys) -> None:
    def fail(params):
        raise RuntimeError("synthetic core failure")

    monkeypatch.setitem(protocol._METHODS, "runtime.core_smoke", fail)
    response, _ = protocol.handle_request(request("runtime.core_smoke"))
    assert response["error"]["code"] == "core_error"
    assert "synthetic core failure" in capsys.readouterr().err


def test_persistent_protocol_handles_bad_json_then_health_and_shutdown() -> None:
    stdin = io.StringIO(
        "{bad-json}\n"
        + json.dumps(request("runtime.health", request_id="health"))
        + "\n"
        + json.dumps(request("runtime.shutdown", request_id="stop"))
        + "\n"
    )
    stdout = io.StringIO()
    assert protocol.run(stdin, stdout) == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [item["request_id"] for item in responses] == [None, "health", "stop"]
    assert responses[0]["error"]["code"] == "malformed_json"
    assert responses[-1]["result"]["status"] == "shutting_down"
