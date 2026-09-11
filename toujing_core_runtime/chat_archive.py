"""Local validated chat archive, separate from canonical facts and Evidence.

No model payloads, intermediate research, tool outputs, or credentials are stored.
An atomic scope snapshot preserves the continuation head across process restarts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager


class ChatArchive:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Restrictive mode at creation, not only after SQLite has written data.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS validated_conversations_v1 "
                "(scope_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def key(scope):
        return json.dumps(scope, sort_keys=True, separators=(",", ":"))

    def read(self, scope):
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM validated_conversations_v1 WHERE scope_key=?",
                                     (self.key(scope),)).fetchone()
        if row is None:
            return {}
        data = json.loads(row[0])
        if not isinstance(data, dict) or len(data) > 50 or any(
            not isinstance(item, dict) or item.get("scope") != scope or item.get("result", {}).get("scope") != scope
            for item in data.values()):
            raise ValueError("chat_archive_invalid")
        return data

    def save(self, scope, completed):
        data = {key: {field: item[field] for field in ("scope", "source_fingerprint", "question", "history", "result")}
                for key, item in list(completed.items())[-50:] if item["scope"] == scope}
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
        if len(payload.encode()) > 4_000_000:
            raise ValueError("chat_archive_over_limit")
        with self.connect() as connection:
            connection.execute("INSERT INTO validated_conversations_v1 VALUES (?, ?) "
                "ON CONFLICT(scope_key) DO UPDATE SET payload=excluded.payload", (self.key(scope), payload))

    def drop_account(self, subject_id, account_id):
        with self.connect() as connection:
            rows = connection.execute("SELECT scope_key FROM validated_conversations_v1").fetchall()
            for (key,) in rows:
                scope = json.loads(key)
                if (scope.get("subject_id"), scope.get("account_id")) == (subject_id, account_id):
                    connection.execute("DELETE FROM validated_conversations_v1 WHERE scope_key=?", (key,))
