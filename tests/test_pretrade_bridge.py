from __future__ import annotations

import io
import json

import pytest

from scripts import pretrade_bridge


def _request(**payload_changes):
    payload = {
        "subject_id": pretrade_bridge.SUBJECT_ID,
        "proposed_time": "2025-01-08T23:59:00",
        "symbol": "SYN_PAPER_WIN",
        "side": "BUY",
        "quantity": 200.0,
        "execution_price": 13.0,
        "fees": 5.0,
    }
    payload.update(payload_changes)
    return {
        "request_id": "request-001",
        "action": "pretrade_check",
        "payload": payload,
    }


@pytest.fixture(scope="module")
def complete_response():
    return pretrade_bridge.handle_request(_request())


def test_valid_request_returns_deterministic_engine_result(complete_response) -> None:
    assert complete_response["request_id"] == "request-001"
    assert complete_response["ok"] is True
    assert complete_response["error"] is None
    result = complete_response["result"]
    assert result["simulation_status"] == "complete"
    assert result["proposed_trade"]["quantity"] == 200.0
    assert result["before"]["hhi"] == pytest.approx(0.4817677368)
    assert result["after"]["hhi"] == pytest.approx(0.5767483750)


def test_same_request_serializes_identically(complete_response) -> None:
    second = pretrade_bridge.handle_request(_request())

    assert json.dumps(complete_response, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_unknown_action_is_rejected_without_running_engine(monkeypatch) -> None:
    monkeypatch.setattr(
        pretrade_bridge,
        "_run_engine",
        lambda trade: pytest.fail("engine must not run for an unknown action"),
    )
    request = _request()
    request["action"] = "run_python"

    response = pretrade_bridge.handle_request(request)

    assert response["ok"] is False
    assert response["error"]["code"] == "unsupported_action"
    assert response["request_id"] == request["request_id"]


def test_invalid_trade_is_returned_as_deterministic_rejection() -> None:
    response = pretrade_bridge.handle_request(_request(quantity=0.0))

    assert response["ok"] is True
    assert response["result"]["simulation_status"] == "rejected"
    assert "quantity" in response["result"]["simulation_reason"].lower()


def test_bridge_stdout_is_one_json_line_and_stderr_is_clean(
    monkeypatch, complete_response
) -> None:
    monkeypatch.setattr(pretrade_bridge, "handle_request", lambda request: complete_response)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = pretrade_bridge.main(
        io.StringIO(json.dumps(_request()) + "\n"), stdout, stderr
    )

    lines = stdout.getvalue().splitlines()
    assert exit_code == 0
    assert len(lines) == 1
    assert json.loads(lines[0])["ok"] is True
    assert stderr.getvalue() == ""


def test_malformed_json_returns_protocol_error_on_stdout() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    pretrade_bridge.main(io.StringIO("{not-json}\n"), stdout, stderr)

    response = json.loads(stdout.getvalue())
    assert response == {
        "request_id": None,
        "ok": False,
        "result": None,
        "error": {
            "code": "malformed_json",
            "message": "invalid JSON request: Expecting property name enclosed in double quotes",
        },
    }
    assert stderr.getvalue() == ""


def test_payload_cannot_select_command_arguments_or_environment(monkeypatch) -> None:
    monkeypatch.setattr(
        pretrade_bridge,
        "_run_engine",
        lambda trade: pytest.fail("engine must not run for extra fields"),
    )
    request = _request(command="python", args=["-c", "print('unsafe')"], cwd="/tmp")

    response = pretrade_bridge.handle_request(request)

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_trade_request"
    assert "unsupported fields" in response["error"]["message"]
