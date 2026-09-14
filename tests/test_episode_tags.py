import sqlite3

import pytest

from src.agents.review_store import TAG_MAX_COUNT, TAG_MAX_LENGTH, ReviewStore, normalize_tags


@pytest.fixture()
def store():
    db = sqlite3.connect(":memory:")
    yield ReviewStore(db)
    db.close()


def test_set_and_list_tags_round_trip(store):
    saved = store.set_tags(subject_id="S", account_id="A", episode_id="E1",
                           tags=["止损太晚", " 按计划执行 "])
    assert saved == ["止损太晚", "按计划执行"]
    rows = store.list_tags("S", "A")
    assert rows == ({"episode_id": "E1", "tags": ["止损太晚", "按计划执行"]},)
    assert store.list_tags("S", "A", episode_id="E1") == rows
    assert store.list_tags("S", "A", episode_id="missing") == ()
    assert store.list_tags("OTHER", "A") == ()


def test_set_tags_overwrites_previous_value(store):
    store.set_tags(subject_id="S", account_id="A", episode_id="E1", tags=["a", "b"])
    store.set_tags(subject_id="S", account_id="A", episode_id="E1", tags=["c"])
    rows = store.list_tags("S", "A")
    assert rows == ({"episode_id": "E1", "tags": ["c"]},)


def test_tags_are_scoped_by_subject_account_and_episode(store):
    store.set_tags(subject_id="S", account_id="A", episode_id="E1", tags=["a"])
    store.set_tags(subject_id="S", account_id="B", episode_id="E1", tags=["b"])
    store.set_tags(subject_id="S", account_id="A", episode_id="E2", tags=["c"])
    assert store.list_tags("S", "A") == (
        {"episode_id": "E1", "tags": ["a"]}, {"episode_id": "E2", "tags": ["c"]})
    assert store.list_tags("S", "B") == ({"episode_id": "E1", "tags": ["b"]},)


def test_normalize_tags_strips_drops_empty_dedupes_and_caps(store):
    assert normalize_tags(["  a  ", "", "b", "a", " ", "c"]) == ("a", "b", "c")
    assert normalize_tags([]) == ()
    long_tag = "x" * (TAG_MAX_LENGTH + 10)
    normalized = normalize_tags([long_tag])
    assert normalized == ("x" * TAG_MAX_LENGTH,)
    overflow = [f"tag{i}" for i in range(TAG_MAX_COUNT + 5)]
    assert len(normalize_tags(overflow)) == TAG_MAX_COUNT
    assert normalize_tags(overflow) == tuple(f"tag{i}" for i in range(TAG_MAX_COUNT))


def test_normalize_tags_rejects_non_string_entries():
    with pytest.raises(ValueError):
        normalize_tags("not-a-list")
    with pytest.raises(ValueError):
        normalize_tags([1, 2])
    with pytest.raises(ValueError):
        normalize_tags(None)


def test_set_tags_validates_scope(store):
    with pytest.raises(ValueError):
        store.set_tags(subject_id=" ", account_id="A", episode_id="E", tags=["a"])
    with pytest.raises(ValueError):
        store.set_tags(subject_id="S", account_id="", episode_id="E", tags=["a"])
    with pytest.raises(ValueError):
        store.set_tags(subject_id="S", account_id="A", episode_id=None, tags=["a"])


def test_delete_account_read_models_removes_tags(store):
    store.set_tags(subject_id="S", account_id="A", episode_id="E1", tags=["a"])
    store.set_tags(subject_id="S", account_id="B", episode_id="E1", tags=["b"])
    store.delete_account_read_models("S", "A")
    assert store.list_tags("S", "A") == ()
    assert store.list_tags("S", "B") == ({"episode_id": "E1", "tags": ["b"]},)
