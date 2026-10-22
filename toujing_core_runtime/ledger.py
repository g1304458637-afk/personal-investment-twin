"""Account-owned ledger RPC: preview, immutable commit, projections and reconciliation."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path

from src.ledger import contracts as c
from src.ledger.engine import project
from src.ledger.reconciliation import reconcile, statement
from src.persistence.repository import _dump, _execution_payload, _price_payload


def scope(params):
    return c.text(params.get("subject_id"), "subject_id"), c.text(params.get("account_id"), "account_id")


def read_csv(path):
    source = Path(c.text(path, "file_path"))
    if source.suffix.lower() != ".csv" or source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("CSV file up to 16 MiB required")
    content = source.read_bytes()
    decoded = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if decoded is None:
        raise ValueError("unsupported CSV encoding")
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("CSV requires unique column names")
    records = []
    for row in reader:
        if None in row:
            raise ValueError("CSV row has extra cells")
        records.append({key.strip(): value.strip() for key, value in row.items() if value is not None and value.strip()})
        if len(records) > 10000:
            raise ValueError("CSV exceeds 10000 rows")
    import hashlib
    return records, hashlib.sha256(content).hexdigest()


class LedgerRuntime:
    def __init__(self, product):
        self.product, self.repo = product, product.repo

    def state_fingerprint(self, subject, account):
        return c.fingerprint({"profile": self.repo.ledger_profile(subject, account),
            "events": self.repo.ledger_events(subject, account),
            "executions": [_execution_payload(x) for x in self.repo.executions(subject, account)],
            "prices": [_price_payload(x) for x in self.repo.prices(subject, account)]})

    def snapshot(self, subject, account, as_of=None, *, profile=None, events=None):
        profile = profile or self.repo.ledger_profile(subject, account)
        if profile is None:
            raise ValueError("请先设置期初日期、币种、现金及持仓，启用真实账本。")
        return project(profile, self.repo.ledger_events(subject, account) if events is None else events,
            self.repo.executions(subject, account), self.repo.prices(subject, account),
            as_of=c.day(as_of, "as_of") if as_of else None)

    def get(self, params):
        subject, account = scope(params)
        profile = self.repo.ledger_profile(subject, account)
        if profile is None:
            return {"subject_id": subject, "account_id": account, "enabled": False,
                "profile": None, "snapshot": None, "events": [], "reconciliations": []}
        fp = self.state_fingerprint(subject, account)
        runs = []
        for run in self.repo.reconciliation_runs(subject, account):
            runs.append({"run_id": run["run_id"], "recorded_at": run["recorded_at"],
                "stale": run["state_fingerprint"] != fp, "statement": json.loads(run["statement_json"]),
                "report": json.loads(run["report_json"])})
        return {"subject_id": subject, "account_id": account, "enabled": True, "profile": profile,
            "state_fingerprint": fp, "snapshot": self.snapshot(subject, account, params.get("as_of")),
            "events": self.repo.ledger_events(subject, account), "reconciliations": runs,
            "journal": [{k:v for k,v in j.items() if k not in {"source_rows", "request"}} for j in self.repo.journal_entries(subject, account)],
            "executions": [{"execution_id": x.execution_id, "date": x.event_time.calendar_date.isoformat(),
                "symbol": x.instrument.local_symbol, "side": x.side, "quantity": str(x.executed_quantity), "price": str(x.executed_price)}
                for x in self.repo.executions(subject, account)]}

    def _prepare(self, params):
        subject, account = scope(params)
        mode = params.get("mode")
        profile = self.repo.ledger_profile(subject, account)
        events = self.repo.ledger_events(subject, account)
        additions, issues, duplicate_count, file_sha = [], [], 0, None
        configuration = {key: value for key, value in params.items()
            if key not in {"expected_preview_fingerprint", "expected_file_sha256", "file_path"}}
        if params.get("file_path"):
            records, file_sha = read_csv(params["file_path"])
        else:
            records = params.get("records", [])
        if not isinstance(records, list) or len(records) > 10000:
            raise ValueError("records must be a list of at most 10000 rows")
        if mode == "opening":
            if profile is not None:
                raise ValueError("期初已设置；持仓可通过作废并重录更正，现金可登记期初现金更正，均保留审计记录。")
            profile = {**c.opening(params.get("opening")), "subject_id": subject, "account_id": account}
            for row in records:
                if not isinstance(row, dict) or row.get("event_type") != "opening_position" or row.get("effective_date") != profile["opening_date"]:
                    raise ValueError("opening preview only accepts opening positions on opening_date")
        elif profile is None:
            raise ValueError("account ledger is not initialized")
        fp = self.state_fingerprint(subject, account)
        if mode in {"opening", "events"}:
            known = {x["event_id"]: {k: v for k, v in x.items() if k != "recorded_at"} for x in events}
            for index, raw in enumerate(records):
                try:
                    item = c.event(raw, profile["currency"])
                    if item["event_id"].startswith(("execution:", "void:")):
                        raise ValueError("reserved event_id prefix")
                    if item["effective_date"] < profile["opening_date"] or item.get("ex_date", item["effective_date"]) < profile["opening_date"]:
                        raise ValueError("ledger event precedes opening_date")
                    previous = known.get(item["event_id"])
                    if previous is not None:
                        if previous != item:
                            raise ValueError("event_id_conflict: original event is immutable")
                        duplicate_count += 1
                        continue
                    known[item["event_id"]] = item
                    additions.append(item)
                except (TypeError, ValueError, AttributeError) as exc:
                    issues.append({"row": index + 1, "message": str(exc)})
            if not records and mode == "events":
                raise ValueError("at least one event required")
        elif mode == "void":
            target = c.text(params.get("target_event_id"), "target_event_id")
            reason = c.text(params.get("reason"), "reason")
            known = {x["event_id"] for x in events if x["event_type"] != "void"}
            known.update("execution:" + x.execution_id for x in self.repo.executions(subject, account))
            if target not in known or any(x.get("target_event_id") == target for x in events):
                raise ValueError("target is missing, foreign, or already voided")
            additions = [{"event_id": "void:" + c.fingerprint([target, reason]), "event_type": "void",
                "effective_date": profile["opening_date"], "target_event_id": target, "reason": reason}]
        elif mode not in {"statement", "plan", "note", "link"}:
            raise ValueError("unsupported ledger operation")
        after = self.snapshot(subject, account, params.get("as_of"), profile=profile, events=events + additions)
        statement_input, report = None, None
        if mode == "statement":
            raw = params.get("statement")
            if params.get("file_path"):
                cash_rows = [r for r in records if r.get("row_type") == "cash"]
                if len(cash_rows) != 1 or any(r.get("row_type") not in {"cash", "position", "execution"} for r in records):
                    raise ValueError("statement CSV requires exactly one cash row and valid row_type")
                if any(r.get("as_of") != cash_rows[0].get("as_of") or r.get("currency") != profile["currency"] for r in records):
                    raise ValueError("statement CSV rows must share the same as_of and currency")
                raw = {**cash_rows[0], "positions_complete": True,
                    "positions": [r for r in records if r.get("row_type") == "position"]}
                refs = [r.get("source_execution_id") for r in records if r.get("row_type") == "execution"]
                if refs or cash_rows[0].get("execution_refs_complete", "").lower() in {"true", "1"}:
                    raw["execution_refs"] = refs
            statement_input = statement(raw, profile["currency"])
            after = self.snapshot(subject, account, statement_input["as_of"])
            refs = [x.source_execution_id or x.execution_id for x in self.repo.executions(subject, account)
                if statement_input["executions_from"] and statement_input["executions_from"] <= x.event_time.calendar_date.isoformat() <= statement_input["as_of"]
                and not any(e.get("target_event_id") == "execution:" + x.execution_id for e in events)]
            report = reconcile(after, statement_input, execution_refs=refs)
        if after["errors"]:
            issues.extend({"row": None, "message": f'{e["event_id"]}: {e["code"]}'} for e in after["errors"])
        preview = {"subject_id": subject, "account_id": account, "mode": mode, "profile": profile,
            "state_fingerprint": fp, "new_events": additions, "duplicates": duplicate_count,
            "issues": issues, "after": after, "report": report, "statement": statement_input,
            "file_sha256": file_sha, "configuration": configuration}
        if mode in {"plan", "note", "link"}:
            from src.ledger.journal import prepare
            preview["journal_entry"] = prepare({**params, "source_fingerprint": fp}, self.repo, subject, account)
        preview["preview_fingerprint"] = c.fingerprint(preview)
        del preview["configuration"]
        return preview

    def preview(self, params):
        return self._prepare(params)

    def commit(self, params):
        preview = self._prepare(params)
        if preview["preview_fingerprint"] != params.get("expected_preview_fingerprint"):
            raise ValueError("预览已失效：数据、账户、参数或文件发生变化，请重新预览。")
        if preview["file_sha256"] and preview["file_sha256"] != params.get("expected_file_sha256"):
            raise ValueError("file changed after preview")
        if preview["issues"]:
            raise ValueError("cannot commit ledger preview containing blocking issues")
        subject, account = scope(params)
        now = datetime.now(timezone.utc).isoformat()
        with self.repo.transaction() as db:
            if self.state_fingerprint(subject, account) != preview["state_fingerprint"]:
                raise ValueError("ledger changed; preview again")
            if params["mode"] == "opening":
                profile = preview["profile"]
                old = next((x for x in self.repo.list_accounts() if x["subject_id"] == subject and x["account_id"] == account), None)
                if old:
                    profile = {**profile, "previous_legacy_initial_cash": old["initial_cash"]}
                self.repo.upsert_account(subject, account, display_name=profile["display_name"],
                    initial_cash=float(profile["initial_cash"]), now=now)
                db.execute("UPDATE accounts SET initial_cash=? WHERE subject_id=? AND account_id=?",
                    (float(profile["initial_cash"]), subject, account))
                db.execute("INSERT INTO account_ledger_profiles VALUES(?,?,?)", (subject, account, _dump(profile)))
            for item in preview["new_events"]:
                db.execute("INSERT INTO account_ledger_events VALUES(?,?,?,?,?,?)",
                    (subject, account, item["event_id"], item["effective_date"], _dump(item), now))
            if "journal_entry" in preview:
                item = preview["journal_entry"]
                db.execute("INSERT INTO account_journal_entries VALUES(?,?,?,?,?,?)",
                    (subject, account, item["entry_id"], item["entry_type"], _dump(item), now))
            if params["mode"] == "statement":
                run_id = c.fingerprint([preview["statement"], preview["state_fingerprint"]])
                db.execute("INSERT OR IGNORE INTO account_reconciliation_runs VALUES(?,?,?,?,?,?,?)",
                    (subject, account, run_id, _dump(preview["statement"]), preview["state_fingerprint"], _dump(preview["report"]), now))
            db.execute("UPDATE accounts SET updated_at=? WHERE subject_id=? AND account_id=?", (now, subject, account))
        return {"subject_id": subject, "account_id": account, "committed": True,
            "inserted_events": len(preview["new_events"]), "state_fingerprint": self.state_fingerprint(subject, account)}

    def instruments(self, subject, account):
        return self.instruments_from_repository(self.repo, subject, account)

    @staticmethod
    def instruments_from_repository(repo, subject, account):
        from src.core.canonical_execution import instrument_ref
        result = {}
        for item in repo.ledger_events(subject, account):
            for key in ("instrument", "new_instrument"):
                raw = item.get(key)
                if raw:
                    result[raw["instrument_id"]] = instrument_ref(local_symbol=raw["symbol"], market=raw["market"],
                        security_type=raw["security_type"], currency=raw["currency"])
        return result
