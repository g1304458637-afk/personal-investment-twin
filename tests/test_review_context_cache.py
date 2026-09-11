"""Scoped context cache: fresh facts/notes and independent Agent receipts."""
from types import SimpleNamespace
import pandas as pd
import pytest
from toujing_core_runtime import review


@pytest.fixture
def service(monkeypatch):
    runtime = object.__new__(review.ReviewRuntime)
    runtime._context_cache = {}
    runtime.version = "source-v1"
    runtime.note_version = "notes-v1"
    runtime.store = SimpleNamespace(note_fingerprint=lambda *args: runtime.note_version, notes=lambda *args: ())
    def own(params):
        episode = SimpleNamespace(subject_id=params["subject_id"], account_id=params["account_id"], episode_id=params["episode_id"], data_tier="synthetic")
        return SimpleNamespace(episode=episode, as_of=pd.Timestamp("2025-12-31"), instrument=SimpleNamespace(display_name="Demo",local_symbol="SYN",currency="CNY")), None, None, 100_000
    runtime._own = own
    runtime._source_fingerprint = lambda params: runtime.version
    calls = []
    monkeypatch.setattr(review, "build_owned_self_history", lambda *args, **kwargs: calls.append(kwargs) or {})
    monkeypatch.setattr(review, "build_position_episode_lifecycle", lambda *args, **kwargs: None)
    monkeypatch.setattr(review, "episode_entry", lambda *args, **kwargs: {"outcome_story":{"counterfactuals":[]},"path_analysis":{"phase_counterfactuals":[]}})
    monkeypatch.setattr(review, "build_review_catalog", lambda *args, **kwargs: SimpleNamespace(records={"fact":{"value":1}}, retrieved=set(), access_allowed=lambda:True))
    return runtime, calls


SCOPE = dict(subject_id="owner", account_id="account", episode_id="episode", data_mode="real_user")


def test_repeated_context_and_agent_start_reuse_projection_with_clean_receipts(service):
    runtime, calls = service
    first, _, _ = runtime._context(SCOPE)
    first.retrieved.add("fact")
    first.records["fact"]["value"] = 999
    first.access_allowed = lambda: False
    second, _, _ = runtime._context(SCOPE, for_agent=True)
    assert len(calls) == 1
    assert second.retrieved == set()
    assert second.records["fact"]["value"] == 1
    assert second.access_allowed()


def test_source_and_note_updates_rebuild(service):
    runtime, calls = service
    runtime._context(SCOPE)
    runtime.version = "source-v2"
    runtime._context(SCOPE)
    runtime.note_version = "notes-v2"
    runtime._context(SCOPE)
    assert len(calls) == 3


@pytest.mark.parametrize("patch", [{"subject_id":"other"}, {"account_id":"other"}, {"episode_id":"other"}, {"data_mode":"synthetic_episode"}])
def test_complete_scope_is_part_of_cache_identity(service, patch):
    runtime, calls = service
    runtime._context(SCOPE)
    runtime._context(SCOPE | patch)
    assert len(calls) == 2


def test_share_access_never_uses_an_owned_cache_hit(service):
    runtime, calls = service
    runtime._context(SCOPE)
    def revoked(*args):
        raise ValueError("share_not_authorized_for_account")
    runtime.store.share = revoked
    with pytest.raises(ValueError, match="not_authorized"):
        runtime._context(SCOPE | {"share_id":"revoked"}, for_agent=True)
    assert len(calls) == 1


def test_cache_is_bounded(service):
    runtime, _ = service
    for i in range(12):
        runtime._context(SCOPE | {"episode_id":f"episode-{i}"})
    assert len(runtime._context_cache) == 8
