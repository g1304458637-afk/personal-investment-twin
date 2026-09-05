"""Isolated Real User Loop certification through the actual NDJSON process.

No user DB is opened. All CSVs are deterministic test fixtures, never real data.
Run with --binary to exercise the freshly packaged runtime instead of .venv.
"""
from __future__ import annotations

import argparse
import json
import selectors
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, command, db):
        self.process = subprocess.Popen([*command, "--db-path", str(db)], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.serial = 0

    def call(self, method, params, *, ok=True):
        self.serial += 1
        request_id = str(self.serial)
        self.process.stdin.write(json.dumps({"protocol_version": "1", "request_id": request_id,
            "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(90):
                self.process.terminate()
                raise AssertionError(f"runtime timeout: {method}")
        response = json.loads(self.process.stdout.readline())
        assert response["request_id"] == request_id
        assert response["ok"] is ok, response
        return response["result"] if ok else response["error"]

    def import_file(self, kind, params):
        preview_method, commit_method = (("ingestion.preview_trade_csv", "ingestion.commit_trade_import")
            if kind == "trade" else ("market.preview_price_csv", "market.commit_price_import"))
        preview = self.call(preview_method, params)
        confirmed = {**params, "expected_file_sha256": preview.get("file_sha256") or preview["batch"]["file_sha256"],
                     "expected_preview_fingerprint": preview["preview_fingerprint"]}
        return preview, confirmed, commit_method

    def close(self):
        self.call("runtime.shutdown", {})
        _, stderr = self.process.communicate(timeout=15)
        assert self.process.returncode == 0 and not stderr, stderr


def verify(command):
    with tempfile.TemporaryDirectory(prefix="toujing-loop-qa-") as directory:
        root, db = Path(directory), Path(directory) / "qa.sqlite3"
        file = root / "trades.csv"
        raw = (ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv").read_text().replace(",CNY,", ",USD,")
        raw = raw.replace("2025-01-06 09:30:00", "2025-01-06 15:00:00")
        raw += "ACC-1,600000,XSHG,equity,2025-01-06 15:00:00,BUY,30,12.50,1.00,USD,A-6,AO-6,2\n"
        raw += "ACC-1,600000,XSHG,equity,2025-01-06 15:00:00,SELL,10,12.50,1.00,USD,A-7,AO-7,3\n"
        file.write_text(raw)
        price = root / "prices.csv"
        price.write_text((ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv").read_text().replace(",CNY,", ",USD,"))
        params = dict(subject_id="isolated-qa", account_id="ACC-1", file_path=str(file),
            initial_cash=100000, source_timezone="Asia/Shanghai", use_source_row_order_as_sequence=True,
            imported_at="2026-09-05T00:00:00Z")
        client = Client(command, db)
        assert client.call("account.list", {})["accounts"] == []
        _, confirmed, commit = client.import_file("trade", params)
        assert client.call(commit, confirmed)["inserted_executions"] == 7
        assert client.call(commit, confirmed)["inserted_executions"] == 0
        assert client.call("investments.list", params)["episodes"] == [], "no synthetic fallback before prices"
        _, market_confirmed, market_commit = client.import_file("market", {**params, "file_path": str(price), "source_id": "qa_csv", "source_version": "1"})
        client.call(market_commit, market_confirmed)
        listing = client.call("investments.list", params)
        assert listing["summary"] == dict(open_episode_count=1, closed_episode_count=1, current_position_count=1)
        opened = next(item for item in listing["episodes"] if item["status"] == "open")
        assert opened["quantity"] == 40 and opened["currency"] == "USD"
        episode = client.call("episode.get", {**params, "episode_id": opened["episode_id"]})
        assert episode["entry"]["instrument"]["is_synthetic"] is False
        with sqlite3.connect(db) as conn:
            facts = [json.loads(row[0]) for row in conn.execute("SELECT payload_json FROM canonical_executions")]
        by_source = {x["source_execution_id"]: x["execution_id"] for x in facts}
        assert len(facts) == 7
        assert episode["entry"]["episode"]["execution_refs"] == [by_source[x] for x in ("A-5", "A-6", "A-7")]
        client.close()
        client = Client(command, db)
        assert client.call("investments.list", params) == listing
        assert client.call("episode.get", {**params, "episode_id": opened["episode_id"]}) == episode
        assert client.call("data.delete_account", params)["deleted"] is True
        assert client.call("account.list", {})["accounts"] == []

        # Fifteen ambiguous rows: the first twelve decisions are not sufficient.
        header = "symbol,market,security_type,event_time,side,quantity,price,fee,execution_sequence\n"
        rows = [f"600000,XSHG,equity,2025-01-02 10:{i:02}:00,BUY,10,10.00,1,{i+1}\n" for i in range(15)]
        file.write_text(header + "".join(rows))
        _, conf, method = client.import_file("trade", params)
        assert client.call(method, conf)["inserted_executions"] == 15
        file.write_text(header + "".join(row.replace(",10.00,1,", ",10.00,2,") for row in rows))
        preview, conf, method = client.import_file("trade", params)
        assert preview["summary"]["possible_duplicates"] == 15
        choices = {row["row_ref"]: "skip" for row in preview["rows"][:12]}
        error = client.call(method, {**conf, "duplicate_choices": choices}, ok=False)
        assert "every possible duplicate" in error["message"]
        assert client.call("account.get_data_status", params)["execution_count"] == 15
        choices = {row["row_ref"]: "skip" for row in preview["rows"]}
        choices[preview["rows"][13]["row_ref"]] = "keep"
        assert client.call(method, {**conf, "duplicate_choices": choices})["inserted_executions"] == 1
        assert client.call("account.get_data_status", params)["execution_count"] == 16
        client.call("data.delete_account", params)

        # Qualification is a separate audit record, not a duplicate fill.
        file.write_text((ROOT / "tests/fixtures/ingestion/fixture_f_ambiguous_instrument.csv").read_text())
        _, conf, method = client.import_file("trade", params)
        assert client.call(method, conf)["inserted_executions"] == 1
        with sqlite3.connect(db) as conn:
            original = conn.execute("SELECT execution_id,payload_json FROM canonical_executions").fetchall()
        resolved = {**params, "resolution_symbol": "ABC", "resolution_market": "XNAS", "resolution_security_type": "equity"}
        preview, conf, method = client.import_file("trade", resolved)
        assert preview["rows"][0]["status"] == "instrument_resolution"
        result = client.call(method, conf)
        assert result["resolved_executions"] == 1 and result["inserted_executions"] == 0
        client.close(); client = Client(command, db)
        preview, conf, method = client.import_file("trade", resolved)
        assert preview["rows"][0]["status"] == "exact_duplicate"
        assert client.call(method, conf)["resolved_executions"] == 0
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT execution_id,payload_json FROM canonical_executions").fetchall() == original
            assert conn.execute("SELECT COUNT(*) FROM execution_instrument_resolutions").fetchone()[0] == 1
        client.call("data.delete_account", params)
        client.close()
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM canonical_executions").fetchone()[0] == 0
        return {"stored_executions": 7, "open": 1, "closed": 1, "current_quantity": 40,
                "currency": "USD", "same_time_sources": ["A-5", "A-6", "A-7"],
                "restart_identical": True, "delete_cascade": True, "synthetic_fallback": False,
                "ambiguous_rows_reviewed": 15, "unresolved_resolution_restart": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    command = [str(args.binary.resolve())] if args.binary else [sys.executable, "-m", "toujing_core_runtime"]
    print(json.dumps(verify(command), sort_keys=True))
