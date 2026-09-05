import sqlite3

from src.agents.review_store import ReviewStore


def test_retrospective_note_invalidates_previous_inference_without_touching_financial_facts():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE canonical_facts(id TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO canonical_facts VALUES('execution', 'immutable')")
    store = ReviewStore(db)
    scope = {"subject_id": "S", "account_id": "A", "episode_id": "E"}
    first = store.save_inference({"scope": scope, "possible_explanations": [{"claim": "possible", "supporting_refs": []}]})
    note = store.add_note(**scope, text="事后补充：原定分批计划", note_kind="plan")
    assert note["source"] == "user"
    assert note["temporal_kind"] == "retrospective"
    assert note["authored_at"] == note["recorded_at"]
    assert store.inferences("S", "A", "E")[0]["invalidated"] is True
    second = store.save_inference({"scope": scope, "possible_explanations": [{"claim": "revised"}]})
    rows = store.inferences("S", "A", "E")
    assert rows[0]["inference_id"] == second["inference_id"]
    assert rows[1]["inference_id"] == first["inference_id"]
    assert rows[1]["replaced_by"] == second["inference_id"]
    assert store.notes("S", "OTHER", "E") == ()
    assert db.execute("SELECT value FROM canonical_facts").fetchone()[0] == "immutable"
    assert store.note_fingerprint("S", "A", "E") == store.note_fingerprint("S", "A", "E")
    db.close()
