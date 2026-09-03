"""Narrow JSON bridge from the desktop runtime to Pre-trade Impact Engine v1.

The bridge accepts exactly one ``pretrade_check`` request on stdin and writes
exactly one JSON response to stdout.  It performs no financial calculation:
all portfolio, HHI, self-history, and peer facts come from the existing
deterministic engine.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INITIAL_CASH = 100_000.0
SUBJECT_ID = "demo-user:synthetic-behavior"
CALCULATION_CODE_VERSION = "desktop-demo-evidence-v1"
ALLOWED_ACTION = "pretrade_check"
PAYLOAD_FIELDS = {
    "subject_id",
    "proposed_time",
    "symbol",
    "side",
    "quantity",
    "execution_price",
    "fees",
}

sys.path.insert(0, str(PROJECT_ROOT))

from src.data.csv_importer import load_normalized_csv  # noqa: E402
from src.history.metric_series import build_portfolio_hhi_history  # noqa: E402
from src.pretrade.impact import ProposedTrade, simulate_synthetic_trade_impact  # noqa: E402


def _json_value(value: object) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def _error(request_id: object, code: str, message: str) -> dict[str, object]:
    return {
        "request_id": request_id if isinstance(request_id, str) else None,
        "ok": False,
        "result": None,
        "error": {"code": code, "message": message},
    }


def _required_request_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("request_id must be a non-empty string")
    return value


def _required_payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("payload must be a JSON object")
    keys = set(value)
    if keys != PAYLOAD_FIELDS:
        missing = sorted(PAYLOAD_FIELDS - keys)
        extra = sorted(keys - PAYLOAD_FIELDS)
        detail = []
        if missing:
            detail.append(f"missing fields: {', '.join(missing)}")
        if extra:
            detail.append(f"unsupported fields: {', '.join(extra)}")
        raise ValueError("payload has invalid fields (" + "; ".join(detail) + ")")
    return value


def _numeric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _build_trade(payload: Mapping[str, object]) -> ProposedTrade:
    for name in ("subject_id", "proposed_time", "symbol", "side"):
        if not isinstance(payload[name], str) or not str(payload[name]).strip():
            raise ValueError(f"{name} must be a non-empty string")
    if payload["subject_id"] != SUBJECT_ID:
        raise ValueError("subject_id is not available in the local synthetic demo")
    return ProposedTrade(
        subject_id=str(payload["subject_id"]),
        proposed_time=pd.Timestamp(payload["proposed_time"]),
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        quantity=_numeric(payload["quantity"], "quantity"),
        execution_price=_numeric(payload["execution_price"], "execution_price"),
        fees=_numeric(payload["fees"], "fees"),
    )


def _run_engine(trade: ProposedTrade):
    executions = load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
    )
    prices = pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )
    hhi_history = build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=INITIAL_CASH,
        subject_id=SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    return simulate_synthetic_trade_impact(
        trade,
        executions,
        prices,
        init_cash=INITIAL_CASH,
        hhi_history=hhi_history,
        calculation_code_version=CALCULATION_CODE_VERSION,
    )


def handle_request(request: object) -> dict[str, object]:
    if not isinstance(request, Mapping):
        return _error(None, "invalid_request", "request must be a JSON object")
    raw_request_id = request.get("request_id")
    try:
        request_id = _required_request_id(raw_request_id)
    except ValueError as exc:
        return _error(raw_request_id, "invalid_request", str(exc))

    if set(request) != {"request_id", "action", "payload"}:
        return _error(
            request_id,
            "invalid_request",
            "request must contain only request_id, action, and payload",
        )
    if request.get("action") != ALLOWED_ACTION:
        return _error(
            request_id,
            "unsupported_action",
            f"only action '{ALLOWED_ACTION}' is supported",
        )
    try:
        trade = _build_trade(_required_payload(request.get("payload")))
    except (TypeError, ValueError) as exc:
        return _error(request_id, "invalid_trade_request", str(exc))

    try:
        result = _run_engine(trade)
    except Exception as exc:  # defensive process boundary; no traceback on stdout
        return _error(request_id, "engine_failure", str(exc))
    return {
        "request_id": request_id,
        "ok": True,
        "result": _json_value(result),
        "error": None,
    }


def main(
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    del stderr  # Reserved for diagnostics; normal protocol handling remains silent.
    raw = stdin.readline()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        response = _error(None, "malformed_json", f"invalid JSON request: {exc.msg}")
    else:
        if stdin.read().strip():
            response = _error(
                request.get("request_id") if isinstance(request, Mapping) else None,
                "invalid_request",
                "exactly one JSON request is accepted",
            )
        else:
            response = handle_request(request)
    stdout.write(
        json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
