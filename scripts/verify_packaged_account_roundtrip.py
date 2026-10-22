"""Strict offline account round trip through the packaged Toujing sidecar.

This uses only the two checked-in CSV fixtures and a disposable database/cache.
No Python runtime implementation, Keychain helper, provider, quote endpoint, or
real account is imported or called. Each JSON line printed is a small summary;
raw account responses and fixture rows are never logged.

Run from any directory::

    python scripts/verify_packaged_account_roundtrip.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY = ROOT / "apps/desktop/src-tauri/binaries/toujing-core-aarch64-apple-darwin"
TRADE_FIXTURE = ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv"
PRICE_FIXTURE = ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv"
STARTUP_TIMEOUT_S = 90.0
PRODUCT_BUDGET_S = 300.0
REPORT_MARGIN_S = 30.0
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class VerificationError(RuntimeError):
    """Safe, summary-only verification failure."""


def log(step: str, elapsed_s: float, **summary: object) -> None:
    print(json.dumps({"step": step, "elapsed_s": round(elapsed_s, 3), **summary},
                     ensure_ascii=False, sort_keys=True), flush=True)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise VerificationError(reason)


class PackagedClient:
    def __init__(self, binary: Path, workdir: Path, database: Path, cache: Path) -> None:
        # A narrow environment guarantees this proof never inherits an API key
        # or the user's regular app/cache path. The binary may read the two
        # absolute fixture paths explicitly passed in later requests.
        env = {
            "HOME": str(workdir), "TMPDIR": str(workdir),
            "TOUJING_CACHE_DIR": str(cache), "PATH": "/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
            "OPENAI_AGENTS_DONT_LOG_MODEL_DATA": "1",
            "OPENAI_AGENTS_DONT_LOG_TOOL_DATA": "1",
        }
        self._stderr = tempfile.TemporaryFile()
        self.process = subprocess.Popen(
            [str(binary), "--db-path", str(database)], cwd=workdir, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            start_new_session=True,
        )
        require(self.process.stdin is not None and self.process.stdout is not None,
                "sidecar_stdio_missing")
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        self._buffer = bytearray()
        self._next_id = 0
        self.last_elapsed_s = 0.0
        self._closed = False

    def _kill_group(self) -> None:
        # The onefile bootloader can leave a child after its direct process
        # exits. Always signal the session group, including that case.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._kill_group()
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self._stderr.close()

    def _write(self, payload: bytes, deadline: float, method: str) -> None:
        view = memoryview(payload)
        fd = self.process.stdin.fileno()  # type: ignore[union-attr]
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_WRITE)
            while view:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise VerificationError(f"{method}: request_write_timeout")
                try:
                    written = os.write(fd, view)
                except (BrokenPipeError, OSError) as exc:
                    raise VerificationError(f"{method}: request_write_failed") from exc
                view = view[written:]

    def _read(self, deadline: float, method: str) -> dict[str, Any]:
        fd = self.process.stdout.fileno()  # type: ignore[union-attr]
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while True:
                newline = self._buffer.find(b"\n")
                if newline >= 0:
                    line = bytes(self._buffer[:newline])
                    del self._buffer[:newline + 1]
                    try:
                        response = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise VerificationError(f"{method}: non_json_response") from exc
                    require(isinstance(response, dict), f"{method}: non_object_response")
                    return response
                require(len(self._buffer) <= MAX_RESPONSE_BYTES,
                        f"{method}: response_line_too_large")
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise VerificationError(f"{method}: response_timeout")
                try:
                    chunk = os.read(fd, 65536)
                except OSError as exc:
                    raise VerificationError(f"{method}: response_read_failed") from exc
                if not chunk:
                    raise VerificationError(f"{method}: sidecar_exited_{self.process.poll()}")
                self._buffer.extend(chunk)

    def call(self, method: str, params: dict[str, Any], *, startup: bool = False,
             expired: bool = False, error_code: str | None = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = f"verify-{self._next_id}"
        budget = STARTUP_TIMEOUT_S if startup else PRODUCT_BUDGET_S
        deadline_unix_ms = (int(time.time() * 1000) - 1000 if expired
                            else int(time.time() * 1000 + budget * 1000))
        frame = {
            "protocol_version": "1", "request_id": request_id,
            "method": method, "params": params,
            "deadline_unix_ms": deadline_unix_ms,
        }
        payload = (json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        started = time.monotonic()
        deadline = started + (STARTUP_TIMEOUT_S if startup else budget + REPORT_MARGIN_S)
        try:
            self._write(payload, deadline, method)
            response = self._read(deadline, method)
        except Exception:
            self._kill_group()  # Includes the PyInstaller onefile child.
            raise
        self.last_elapsed_s = time.monotonic() - started
        require(response.get("request_id") == request_id, f"{method}: mismatched_request_id")
        if error_code is not None:
            require(response.get("ok") is False and
                    isinstance(response.get("error"), dict) and
                    response["error"].get("code") == error_code,
                    f"{method}: expected_{error_code}")
            return response["error"]
        require(response.get("ok") is True and response.get("error") is None and
                isinstance(response.get("result"), dict), f"{method}: rpc_failed_{_error_code(response)}")
        return response["result"]

    def shutdown(self) -> None:
        result = self.call("runtime.shutdown", {})
        require(result.get("status") == "shutting_down", "shutdown_not_acknowledged")
        try:
            code = self.process.wait(timeout=REPORT_MARGIN_S)
        except subprocess.TimeoutExpired as exc:
            self._kill_group()
            raise VerificationError("shutdown_process_timeout") from exc
        require(code == 0, f"shutdown_exit_{code}")


def _error_code(response: dict[str, Any]) -> str:
    error = response.get("error")
    return str(error.get("code", "unknown")) if isinstance(error, dict) else "unknown"


def _assert_financial_result(investments: dict[str, Any], pack: dict[str, Any]) -> dict[str, object]:
    require(investments.get("portfolio_state_status") == "available", "portfolio_unavailable")
    require(investments.get("summary") == {
        "open_episode_count": 1, "closed_episode_count": 1, "current_position_count": 1,
    }, "episode_counts_unexpected")
    episodes = investments.get("episodes")
    require(isinstance(episodes, list) and len(episodes) == 2, "episode_list_unexpected")
    by_status = {item["status"]: item for item in episodes}
    require(set(by_status) == {"open", "closed"}, "episode_status_unexpected")
    closed_pnl = by_status["closed"]["outcome_summary"]["pnl"]
    open_pnl = by_status["open"]["outcome_summary"]["pnl"]
    require(isinstance(closed_pnl, (int, float)) and math.isclose(closed_pnl, 366.0, abs_tol=1e-6),
            "closed_pnl_mismatch")
    require(isinstance(open_pnl, (int, float)) and math.isclose(open_pnl, -1.0, abs_tol=1e-6),
            "open_pnl_mismatch")
    require(pack.get("schema_version") == "review_pack.v1", "review_pack_schema_mismatch")
    require(pack.get("coverage", {}).get("execution_count") == 5, "review_pack_execution_count_mismatch")
    require(any(item.get("episode_id") == by_status["closed"]["episode_id"]
                for item in pack.get("exit_quality", {}).get("episodes", [])),
            "review_pack_closed_episode_missing")
    require(any(math.isclose(item.get("realized_pnl", float("nan")), 366.0, abs_tol=1e-6)
                for item in pack.get("calendar", {}).get("days", [])),
            "review_pack_realized_pnl_mismatch")
    return {"episode_count": 2, "closed_pnl": closed_pnl, "open_pnl": open_pnl}


def verify(binary: Path) -> dict[str, object]:
    binary = binary.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK), "packaged_binary_missing_or_not_executable")
    require(TRADE_FIXTURE.is_file() and PRICE_FIXTURE.is_file(), "fixture_missing")
    with binary.open("rb") as binary_file:
        binary_sha256 = hashlib.file_digest(binary_file, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix="toujing-packaged-roundtrip-") as temporary:
        workdir = Path(temporary)
        database, cache = workdir / "account.sqlite3", workdir / "cache"
        scope = {"subject_id": "packaged-fixture-only", "account_id": "ACC-1"}
        trade = {**scope, "file_path": str(TRADE_FIXTURE), "display_name": "Packaged Fixture",
                 "source_timezone": "Asia/Shanghai", "use_source_row_order_as_sequence": True,
                 "initial_cash": 100000, "imported_at": "2026-09-04T12:00:00Z"}
        market = {**scope, "file_path": str(PRICE_FIXTURE), "source_id": "user_csv",
                  "source_version": "v1", "imported_at": "2026-09-04T12:01:00Z"}
        process_started = time.monotonic()
        client = PackagedClient(binary, workdir, database, cache)
        try:
            handshake = client.call("runtime.handshake", {}, startup=True)
            cold_handshake_s = time.monotonic() - process_started
            required = {"account.list", "ingestion.preview_trade_csv", "ingestion.commit_trade_import",
                        "market.preview_price_csv", "market.commit_price_import", "investments.list",
                        "review_pack.get", "data.delete_account", "runtime.shutdown"}
            require(handshake.get("protocol_version") == "1" and
                    required <= set(handshake.get("supported_methods", [])), "handshake_contract_mismatch")
            log("handshake", cold_handshake_s, protocol_version="1", supported_count=len(handshake["supported_methods"]))

            accounts = client.call("account.list", {})
            require(accounts.get("accounts") == [], "temporary_database_not_empty")
            log("account.empty", client.last_elapsed_s, account_count=0)

            preview = client.call("ingestion.preview_trade_csv", trade)
            require(preview.get("summary", {}).get("new_executions") == 5,
                    "trade_preview_count_mismatch")
            log("trade.preview", client.last_elapsed_s, new_executions=5)
            confirmed_trade = {**trade, "expected_file_sha256": preview["batch"]["file_sha256"],
                               "expected_preview_fingerprint": preview["preview_fingerprint"],
                               "duplicate_choices": {}}
            imported = client.call("ingestion.commit_trade_import", confirmed_trade)
            require(imported.get("inserted_executions") == 5, "trade_commit_count_mismatch")
            log("trade.commit", client.last_elapsed_s, inserted_executions=5)

            market_preview = client.call("market.preview_price_csv", market)
            require(market_preview.get("summary", {}).get("new_observations") == 5,
                    "market_preview_count_mismatch")
            log("market.preview", client.last_elapsed_s, new_observations=5)
            confirmed_market = {**market, "expected_file_sha256": market_preview["file_sha256"],
                                "expected_preview_fingerprint": market_preview["preview_fingerprint"]}
            market_imported = client.call("market.commit_price_import", confirmed_market)
            require(market_imported.get("inserted_observations") == 5, "market_commit_count_mismatch")
            log("market.commit", client.last_elapsed_s, inserted_observations=5)

            before_accounts = client.call("account.list", {})
            require(len(before_accounts.get("accounts", [])) == 1, "account_missing_after_import")
            before_status = client.call("account.get_data_status", scope)
            require(before_status.get("execution_count") == 5, "stored_execution_count_mismatch")
            log("account.status", client.last_elapsed_s, account_count=1, execution_count=5)
            before_investments = client.call("investments.list", scope)
            cold_investments_s = client.last_elapsed_s
            before_pack = client.call("review_pack.get", scope)
            first_pack_s = client.last_elapsed_s
            finance = _assert_financial_result(before_investments, before_pack)
            log("investments", cold_investments_s, **finance)
            log("review_pack", first_pack_s, execution_count=5, closed_episode_present=True)
            closed_episode_id = next(item["episode_id"] for item in before_investments["episodes"]
                                     if item["status"] == "closed")
            before_episode = client.call("episode.get", {**scope, "episode_id": closed_episode_id})
            require(before_episode.get("status") == "available", "episode_detail_unavailable")
            log("episode.get", client.last_elapsed_s, available=True)

            deletion = client.call("data.delete_account", scope, expired=True,
                                   error_code="request_expired")
            require(deletion.get("code") == "request_expired", "expired_delete_not_rejected")
            log("delete.expired", client.last_elapsed_s, rejected_without_action=True)
            require(client.call("account.get_data_status", scope).get("execution_count") == 5,
                    "expired_delete_changed_account")
            require(len(client.call("account.list", {}).get("accounts", [])) == 1,
                    "expired_delete_removed_account")
            log("delete.unchanged", client.last_elapsed_s, account_count=1, execution_count=5)

            client.shutdown()
            log("shutdown", client.last_elapsed_s, exit_code=0)
        finally:
            client.close()

        restart_started = time.monotonic()
        client = PackagedClient(binary, workdir, database, cache)
        try:
            second_handshake = client.call("runtime.handshake", {}, startup=True)
            restart_handshake_s = time.monotonic() - restart_started
            require(second_handshake.get("protocol_version") == "1", "restart_handshake_failed")
            log("restart.handshake", restart_handshake_s, protocol_version="1")
            after_accounts = client.call("account.list", {})
            after_status = client.call("account.get_data_status", scope)
            after_investments = client.call("investments.list", scope)
            after_pack = client.call("review_pack.get", scope)
            after_episode = client.call("episode.get", {**scope, "episode_id": closed_episode_id})
            require(after_accounts == before_accounts, "account_changed_after_restart")
            require(after_status == before_status and after_status.get("execution_count") == 5,
                    "executions_changed_after_restart")
            require(after_investments == before_investments, "episodes_or_pnl_changed_after_restart")
            require(after_pack == before_pack, "review_pack_changed_after_restart")
            require(after_episode == before_episode, "episode_detail_changed_after_restart")
            _assert_financial_result(after_investments, after_pack)
            log("restart.verified", client.last_elapsed_s, account_count=1,
                execution_count=5, episode_count=2, pnl_unchanged=True)
            client.shutdown()
            log("restart.shutdown", client.last_elapsed_s, exit_code=0)
        finally:
            client.close()

    return {"status": "passed", "binary_sha256": binary_sha256,
            "cold_handshake_s": round(cold_handshake_s, 3),
            "restart_handshake_s": round(restart_handshake_s, 3),
            "cold_investments_s": round(cold_investments_s, 3),
            "first_review_pack_s": round(first_pack_s, 3),
            "account_count": 1, "execution_count": 5, "episode_count": 2,
            "closed_pnl": 366.0, "open_pnl": -1.0, "restart_equal": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY,
                        help="packaged Toujing sidecar executable")
    args = parser.parse_args()
    try:
        log("result", 0.0, **verify(args.binary))
    except (OSError, VerificationError, subprocess.SubprocessError) as exc:
        print(json.dumps({"step": "result", "status": "failed",
                          "error_type": type(exc).__name__, "reason": str(exc)},
                         ensure_ascii=False, sort_keys=True), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
