"""Mutable review read models on the EXISTING local repository connection.

Creates no database file. Only review_* tables are written; canonical,
Evidence and Twin facts are not modified. Retrospective notes never become
historical knowledge. The table/payload version is explicitly v1.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from src.evidence.contracts import canonical_json_bytes
from src.compare.sharing import AuthorizedEpisodeShare, _decode
from src.presentation.runtime_episode import json_value


def utc_now():
    return datetime.now(timezone.utc).isoformat()


# Episode tags are short user-authored review labels on CLOSED analysis units.
# Normalization is deterministic and lossy by design: whitespace is stripped,
# blanks are dropped, duplicates collapse to the first occurrence, each tag is
# capped at 24 characters and at most 8 tags are kept per episode.
TAG_MAX_LENGTH = 24
TAG_MAX_COUNT = 8
_EPISODE_TAGS_TABLE = "review_episode_tags_v1"


def normalize_tags(tags) -> tuple[str, ...]:
    if not isinstance(tags, (list, tuple)):
        raise ValueError("invalid_tags")
    normalized: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError("invalid_tags")
        text = tag.strip()[:TAG_MAX_LENGTH]
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= TAG_MAX_COUNT:
            break
    return tuple(normalized)


class ReviewStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS review_notes_v1 (
              note_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
              episode_id TEXT NOT NULL, payload TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS review_inferences_v1 (
              inference_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
              episode_id TEXT NOT NULL, payload TEXT NOT NULL, invalidated INTEGER NOT NULL DEFAULT 0,
              replaced_by TEXT)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS review_shares_v1 (
              share_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, account_id TEXT NOT NULL,
              payload TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)""")
            connection.execute(f"""CREATE TABLE IF NOT EXISTS {_EPISODE_TAGS_TABLE} (
              subject_id TEXT NOT NULL, account_id TEXT NOT NULL, episode_id TEXT NOT NULL,
              payload TEXT NOT NULL, updated_at TEXT NOT NULL,
              PRIMARY KEY(subject_id, account_id, episode_id))""")

    def add_note(self, *, subject_id, account_id, episode_id, text, note_kind, decision_id=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000 or note_kind not in {"plan", "reason"}:
            raise ValueError("invalid_user_note")
        now = utc_now()
        note = {"note_id": "note_" + uuid4().hex, "subject_id": subject_id, "account_id": account_id,
                "episode_id": episode_id, "decision_id": decision_id, "text": text.strip(),
                "note_kind": note_kind, "source": "user", "authored_at": now, "recorded_at": now,
                "temporal_kind": "retrospective"}
        # V1 collects review notes, not a backdatable pre-decision Journal.
        with self.connection:
            self.connection.execute("INSERT INTO review_notes_v1 VALUES(?,?,?,?,?)",
                (note["note_id"], subject_id, account_id, episode_id, json.dumps(note, ensure_ascii=False)))
            self.connection.execute("UPDATE review_inferences_v1 SET invalidated=1 WHERE subject_id=? AND account_id=? AND episode_id=?",
                                    (subject_id, account_id, episode_id))
        return note

    def notes(self, subject_id, account_id, episode_id):
        rows = self.connection.execute("SELECT payload FROM review_notes_v1 WHERE subject_id=? AND account_id=? AND episode_id=? ORDER BY note_id",
                                       (subject_id, account_id, episode_id))
        return tuple(json.loads(row[0]) for row in rows)

    def note_fingerprint(self, subject_id, account_id, episode_id):
        return hashlib.sha256(canonical_json_bytes(self.notes(subject_id, account_id, episode_id))).hexdigest()

    def save_inference(self, result):
        scope = result["scope"]
        identity = (scope["subject_id"], scope["account_id"], scope["episode_id"])
        inference_id = "inference_" + uuid4().hex
        payload = {**result, "inference_id": inference_id, "generated_at": utc_now(),
                   "invalidated": False, "replaced_by": None}
        with self.connection:
            self.connection.execute("UPDATE review_inferences_v1 SET invalidated=1,replaced_by=? WHERE subject_id=? AND account_id=? AND episode_id=? AND replaced_by IS NULL",
                                    (inference_id, *identity))
            self.connection.execute("INSERT INTO review_inferences_v1 VALUES(?,?,?,?,?,0,NULL)",
                (inference_id, *identity, json.dumps(payload, ensure_ascii=False, allow_nan=False)))
        return payload

    def inferences(self, subject_id, account_id, episode_id):
        rows = self.connection.execute("SELECT payload,invalidated,replaced_by FROM review_inferences_v1 WHERE subject_id=? AND account_id=? AND episode_id=? ORDER BY rowid DESC",
                                       (subject_id, account_id, episode_id))
        return tuple(json.loads(row[0]) | {"invalidated": bool(row[1]), "replaced_by": row[2]} for row in rows)

    def save_share(self, share: AuthorizedEpisodeShare):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO review_shares_v1 VALUES(?,?,?,?,0)",
                (share.share_id, share.recipient_subject_id, share.recipient_account_id,
                 json.dumps(json_value(share), ensure_ascii=False, allow_nan=False)))

    def share(self, share_id, subject_id, account_id):
        row = self.connection.execute("SELECT payload FROM review_shares_v1 WHERE share_id=? AND subject_id=? AND account_id=? AND revoked=0",
                                       (share_id, subject_id, account_id)).fetchone()
        if row is None:
            raise ValueError("share_not_authorized_for_account")
        return _decode(AuthorizedEpisodeShare, json.loads(row[0]))

    def shares(self, subject_id, account_id):
        rows = self.connection.execute("SELECT payload FROM review_shares_v1 WHERE subject_id=? AND account_id=? AND revoked=0 ORDER BY share_id",
                                       (subject_id, account_id))
        return tuple(_decode(AuthorizedEpisodeShare, json.loads(row[0])) for row in rows)

    def revoke_share(self, share_id, subject_id, account_id):
        with self.connection:
            self.connection.execute("UPDATE review_shares_v1 SET revoked=1 WHERE share_id=? AND subject_id=? AND account_id=?",
                                    (share_id, subject_id, account_id))

    def set_tags(self, *, subject_id, account_id, episode_id, tags):
        """Replace the full tag list of one episode with a normalized snapshot."""
        for value in (subject_id, account_id, episode_id):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("invalid_scope")
        normalized = list(normalize_tags(tags))
        now = utc_now()
        with self.connection:
            self.connection.execute(
                f"INSERT OR REPLACE INTO {_EPISODE_TAGS_TABLE} VALUES(?,?,?,?,?)",
                (subject_id, account_id, episode_id,
                 json.dumps(normalized, ensure_ascii=False, allow_nan=False), now))
        return normalized

    def list_tags(self, subject_id, account_id, episode_id=None):
        """Return tags as ({episode_id, tags}, ...) ordered by episode_id."""
        if episode_id is None:
            rows = self.connection.execute(
                f"SELECT episode_id,payload FROM {_EPISODE_TAGS_TABLE} WHERE subject_id=? AND account_id=? ORDER BY episode_id",
                (subject_id, account_id))
            return tuple({"episode_id": row[0], "tags": json.loads(row[1])} for row in rows)
        row = self.connection.execute(
            f"SELECT payload FROM {_EPISODE_TAGS_TABLE} WHERE subject_id=? AND account_id=? AND episode_id=?",
            (subject_id, account_id, episode_id)).fetchone()
        return () if row is None else ({"episode_id": episode_id, "tags": json.loads(row[0])},)

    def delete_account_read_models(self, subject_id, account_id):
        with self.connection:
            for table in ("review_notes_v1", "review_inferences_v1", "review_shares_v1", _EPISODE_TAGS_TABLE):
                self.connection.execute(f"DELETE FROM {table} WHERE subject_id=? AND account_id=?", (subject_id, account_id))
