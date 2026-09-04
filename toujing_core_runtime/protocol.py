"""Small, versioned NDJSON protocol for the bundled deterministic core."""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Callable, Mapping
from typing import Any, TextIO

PROTOCOL_VERSION = "1"
RUNTIME_VERSION = "1.0.0"
CORE_VERSION = "1.0.0"
SUPPORTED_METHODS = (
    "runtime.handshake",
    "runtime.health",
    "runtime.core_smoke",
    "runtime.shutdown",
)


class RuntimeRequestError(ValueError):
    """A request is invalid at the process boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _error(request_id: object, code: str, message: str) -> dict[str, object]:
    return {
        "request_id": request_id if isinstance(request_id, str) else None,
        "ok": False,
        "result": None,
        "error": {"code": code, "message": message},
    }


def _response(request_id: str, result: Mapping[str, object]) -> dict[str, object]:
    return {"request_id": request_id, "ok": True, "result": dict(result), "error": None}


def _empty_params(params: object) -> None:
    if not isinstance(params, Mapping) or params:
        raise RuntimeRequestError("invalid_params", "params must be an empty object")


def _handshake(params: object) -> Mapping[str, object]:
    _empty_params(params)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "python_version": platform.python_version(),
        "core_version": CORE_VERSION,
        "supported_methods": list(SUPPORTED_METHODS),
    }


def _health(params: object) -> Mapping[str, object]:
    _empty_params(params)
    return {"status": "ok", "runtime_version": RUNTIME_VERSION}


def _core_smoke(params: object) -> Mapping[str, object]:
    _empty_params(params)
    # This fixture and all financial results are produced by the existing replay
    # adapter.  The runtime owns only dispatch and serialization.
    from src.core.vectorbt_validation import (
        build_synthetic_case,
        replay_single_symbol_executions,
    )

    executions, prices = build_synthetic_case()
    portfolio = replay_single_symbol_executions(
        executions,
        prices,
        init_cash=100_000.0,
    )
    positions = portfolio.positions.records_readable
    return {
        "fixture": "vectorbt_feasibility_synthetic_v1",
        "final_cash": float(portfolio.cash().iloc[-1, 0]),
        "final_value": float(portfolio.value().iloc[-1, 0]),
        "position_count": int(len(positions)),
        "position_pnl": float(positions.iloc[0]["PnL"]),
        "position_return": float(positions.iloc[0]["Return"]),
    }


def _shutdown(params: object) -> Mapping[str, object]:
    _empty_params(params)
    return {"status": "shutting_down"}


_METHODS: dict[str, Callable[[object], Mapping[str, object]]] = {
    "runtime.handshake": _handshake,
    "runtime.health": _health,
    "runtime.core_smoke": _core_smoke,
    "runtime.shutdown": _shutdown,
}


def handle_request(request: object) -> tuple[dict[str, object], bool]:
    if not isinstance(request, Mapping):
        return _error(None, "invalid_request", "request must be a JSON object"), False
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return _error(request_id, "invalid_request", "request_id must be non-empty"), False
    if set(request) != {"protocol_version", "request_id", "method", "params"}:
        return _error(
            request_id,
            "invalid_request",
            "request must contain only protocol_version, request_id, method, and params",
        ), False
    if request.get("protocol_version") != PROTOCOL_VERSION:
        return _error(request_id, "protocol_incompatible", "unsupported protocol_version"), False
    method = request.get("method")
    if not isinstance(method, str) or method not in _METHODS:
        return _error(request_id, "unknown_method", "method is not supported"), False
    try:
        result = _METHODS[method](request.get("params"))
    except RuntimeRequestError as exc:
        return _error(request_id, exc.code, str(exc)), False
    except Exception as exc:  # process boundary: never leak a traceback to stdout
        print(f"runtime method {method} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return _error(request_id, "core_error", str(exc)), False
    return _response(request_id, result), method == "runtime.shutdown"


def run(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    """Serve requests until EOF or an acknowledged shutdown request."""

    for raw_line in stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            response, should_stop = (
                _error(None, "malformed_json", f"invalid JSON request: {exc.msg}"),
                False,
            )
        else:
            response, should_stop = handle_request(request)
        stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        stdout.flush()
        if should_stop:
            return 0
    return 0
