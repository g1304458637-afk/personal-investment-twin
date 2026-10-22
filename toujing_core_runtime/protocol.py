"""Small, versioned NDJSON protocol for the bundled deterministic core."""

from __future__ import annotations

import json
import platform
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TextIO

PROTOCOL_VERSION = "1"
RUNTIME_VERSION = "1.0.0"
CORE_VERSION = "1.0.0"
BASE_METHODS = (
    "runtime.handshake",
    "runtime.health",
    "runtime.core_smoke",
    "runtime.shutdown",
)
PRODUCT_METHODS = (
    "ledger.get", "ledger.preview", "ledger.commit", "ledger.research",
    "backup.create", "backup.preview_restore", "backup.restore", "backup.pending_preferences", "backup.ack_preferences",
    "ingestion.preview_trade_csv", "ingestion.commit_trade_import",
    "market.preview_price_csv", "market.commit_price_import",
    "account.list", "account.get_data_status", "investments.list", "episode.get",
    "strategy_comparison.get",
    "strategy_simulation.run_custom",
    "strategy_sensitivity.run",
    "strategy_teaching.explain",
    "data.delete_account",
    "review.context", "review.start", "review.poll", "review.add_note",
    "review_pack.get", "episode_tags.set",
    "compare.export_share", "compare.import_share", "compare.list_shares", "compare.revoke_share",
)
SUPPORTED_METHODS = (*BASE_METHODS, *PRODUCT_METHODS)


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


def _model_test(params):
    from .model_service import test_connection
    # Private stdio method: deliberately not in the frontend product allowlist.
    return test_connection(params)


def _search_test(params):
    # Startup connectivity checks must not import the Agent or analytics runtime.
    from .search_service import probe_search_connection
    return probe_search_connection(params)


def _quotes_status(params):
    # Keep this private status endpoint independent of the Agent runtime: it
    # runs during desktop startup before any review or analytics request.
    from .quote_status import quotes_status
    if params is None:
        params = {}
    if not isinstance(params, dict) or params:
        raise ValueError("invalid_quotes_status_request")
    return quotes_status()


def _strategy_teaching(params):
    # Keep the model SDK out of startup and ordinary account reads.
    from src.agents.strategy_teaching import explain_report
    return explain_report(params)


_METHODS: dict[str, Callable[[object], Mapping[str, object]]] = {
    "runtime.handshake": _handshake,
    "runtime.health": _health,
    "runtime.core_smoke": _core_smoke,
    "runtime.shutdown": _shutdown,
    "model.test_connection": _model_test,
    "search.test_connection": _search_test,
    "quotes.status": _quotes_status,
}


def _product_methods(db_path: str | None) -> tuple[dict[str, Callable[[object], Mapping[str, object]]], object | None]:
    if db_path is None:
        return {}, None
    from .product import ProductRuntime
    product = ProductRuntime(db_path)
    def checked(fn: Callable[[Mapping[str, object]], Mapping[str, object]]) -> Callable[[object], Mapping[str, object]]:
        def call(params: object) -> Mapping[str, object]:
            if not isinstance(params, Mapping):
                raise RuntimeRequestError("invalid_params", "params must be an object")
            try:
                return fn(params)
            except (TypeError, ValueError) as exc:
                raise RuntimeRequestError("invalid_params", str(exc)) from exc
            except (OSError, sqlite3.Error) as exc:
                # Infrastructure failures (missing file, locked/failed sqlite)
                # must not leak absolute paths or raw sqlite text through
                # core_error.
                raise RuntimeRequestError("storage_unavailable", "local storage operation failed") from exc
        return call
    from .backup import BackupRuntime
    from .research import run as research_run
    backup = BackupRuntime(product)
    methods = {
        "ledger.research": checked(lambda p: research_run(product, p)),
        "backup.create": checked(backup.create),
        "backup.preview_restore": checked(backup.preview),
        "backup.restore": checked(backup.restore),
        "backup.pending_preferences": checked(backup.pending),
        "backup.ack_preferences": checked(backup.ack),
        "ledger.get": checked(product.ledger_runtime().get),
        "ledger.preview": checked(product.ledger_runtime().preview),
        "ledger.commit": checked(product.ledger_runtime().commit),
        "ingestion.preview_trade_csv": checked(product.preview_trade),
        "ingestion.commit_trade_import": checked(product.commit_trade),
        "market.preview_price_csv": checked(product.preview_market),
        "market.commit_price_import": checked(product.commit_market),
        "account.list": checked(product.accounts),
        "account.get_data_status": checked(product.data_status),
        "investments.list": checked(product.investments),
        "episode.get": checked(product.episode),
        "strategy_comparison.get": checked(product.strategy_comparison),
        "strategy_simulation.run_custom": checked(product.strategy_simulation_run_custom),
        "strategy_sensitivity.run": checked(product.strategy_sensitivity_run),
        "strategy_teaching.explain": checked(_strategy_teaching),
        "data.delete_account": checked(product.delete_account),
        "review.context": checked(lambda p: product.review_runtime().context(p)),
        "review.start": checked(lambda p: product.review_runtime().start(p)),
        "review.poll": checked(lambda p: product.review_runtime().poll(p)),
        "review.add_note": checked(lambda p: product.review_runtime().add_note(p)),
        "review_pack.get": checked(product.review_pack),
        "episode_tags.set": checked(lambda p: product.review_runtime().set_episode_tags(p)),
        "compare.export_share": checked(lambda p: product.review_runtime().export_share(p)),
        "compare.import_share": checked(lambda p: product.review_runtime().import_share(p)),
        "compare.list_shares": checked(lambda p: product.review_runtime().list_shares(p)),
        "compare.revoke_share": checked(lambda p: product.review_runtime().revoke_share(p)),
    }
    return methods, product


def _validate_request(request: object, handlers: Mapping[str, Callable]) -> dict[str, object] | None:
    """Validate transport only: safe on the reader, never calls a product method."""
    if not isinstance(request, Mapping):
        return _error(None, "invalid_request", "request must be a JSON object")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return _error(request_id, "invalid_request", "request_id must be non-empty")
    required = {"protocol_version", "request_id", "method", "params"}
    if not required <= set(request) or set(request) - required - {"deadline_unix_ms"}:
        return _error(
            request_id,
            "invalid_request",
            "request must contain protocol_version, request_id, method, params and optional deadline_unix_ms",
        )
    if request.get("protocol_version") != PROTOCOL_VERSION:
        return _error(request_id, "protocol_incompatible", "unsupported protocol_version")
    method = request.get("method")
    if not isinstance(method, str) or method not in handlers:
        return _error(request_id, "unknown_method", "method is not supported")
    if "deadline_unix_ms" in request:
        deadline = request["deadline_unix_ms"]
        if isinstance(deadline, bool) or not isinstance(deadline, int) or deadline <= 0:
            return _error(request_id, "invalid_request", "deadline_unix_ms must be a positive integer")
        if time.time_ns() // 1_000_000 >= deadline:
            return _error(request_id, "request_expired", "request expired before execution; no action was performed")
    if method in BASE_METHODS and (not isinstance(request["params"], Mapping) or request["params"]):
        return _error(request_id, "invalid_params", "params must be an empty object")
    if method in PRODUCT_METHODS and not isinstance(request["params"], Mapping):
        return _error(request_id, "invalid_params", "params must be an object")
    return None


def handle_request(request: object, methods: Mapping[str, Callable[[object], Mapping[str, object]]] | None = None) -> tuple[dict[str, object], bool]:
    handlers = methods if methods is not None else _METHODS
    error = _validate_request(request, handlers)
    if error is not None:
        return error, False
    request_id, method = request["request_id"], request["method"]
    try:
        result = handlers[method](request.get("params"))
    except RuntimeRequestError as exc:
        return _error(request_id, exc.code, str(exc)), False
    except Exception as exc:  # process boundary: never leak a traceback to stdout
        print(f"runtime method {method} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return _error(request_id, "core_error", str(exc)), False
    return _response(request_id, result), method == "runtime.shutdown"


def run(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout, *, db_path: str | None = None) -> int:
    """Serve RPC with a responsive control lane and one ordered data worker.

    SQLite is created, used and closed on the same worker. Account mutations
    remain FIFO; only handshake/health bypass that queue. Shutdown and EOF
    drain accepted work before closing storage. Responses are request-id
    addressed and may arrive out of order (health may overtake a replay).
    """
    write_lock = threading.Lock()
    # Bound queued work without blocking the reader that serves health.
    capacity = threading.BoundedSemaphore(64)

    def emit(response):
        try:
            line = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            # A result that cannot serialize (NaN/non-JSON type) must fail THIS
            # request, never kill the process: outside this guard the exception
            # would escape run() and every later request would die with it.
            line = json.dumps(
                _error(response.get("request_id"), "serialization_error", f"response is not serializable: {exc}"),
                ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with write_lock:
            stdout.write(line + "\n")
            stdout.flush()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="toujing-data") as worker:
        product_methods, product = worker.submit(_product_methods, db_path).result()
        methods = {**_METHODS, **product_methods}

        def dispatch(request):
            try:
                response, _ = handle_request(request, methods)
                emit(response)
            finally:
                capacity.release()

        try:
            for raw_line in stdin:
                try:
                    request = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    emit(_error(None, "malformed_json", f"invalid JSON request: {exc.msg}"))
                    continue
                method = request.get("method") if isinstance(request, Mapping) else None
                error = _validate_request(request, methods)
                if error is not None:
                    emit(error)
                    continue
                if isinstance(method, str) and method in {"runtime.handshake", "runtime.health"}:
                    response, _ = handle_request(request, methods)
                    emit(response)
                elif method == "runtime.shutdown":
                    # Also validate malformed shutdown envelopes. An invalid
                    # shutdown must not stop the worker or drop queued writes.
                    response, should_stop = worker.submit(handle_request, request, methods).result()
                    emit(response)
                    if should_stop:
                        break
                elif capacity.acquire(blocking=False):
                    worker.submit(dispatch, request)
                else:
                    request_id = request.get("request_id") if isinstance(request, Mapping) else None
                    emit(_error(request_id, "runtime_busy", "runtime work queue is full; retry after pending work completes"))
        finally:
            if product is not None:
                worker.submit(product.close).result()  # type: ignore[attr-defined]
    return 0
