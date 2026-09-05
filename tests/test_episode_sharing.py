import json

import pandas as pd
import pytest

from src.compare.demo import build_pair
from src.compare.sharing import accept_episode_share, authorized_comparison, create_episode_share


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def export(pair, *, agent=False, consent=True):
    return create_episode_share(pair.b, recipient_subject_id=pair.a.episode.subject_id,
                                recipient_account_id=pair.a.episode.account_id,
                                expires_at=pd.Timestamp("2027-01-01"),
                                allow_agent_review=agent, owner_confirmed=consent)


def accept(pair, content, key, **kwargs):
    params = dict(recipient_subject_id=pair.a.episode.subject_id,
                  recipient_account_id=pair.a.episode.account_id, now=pd.Timestamp("2026-09-05"))
    return accept_episode_share(content, key, **(params | kwargs))


def test_explicit_limited_share_roundtrip_and_raw_ids_redacted(pair):
    content, key = export(pair)
    shared = accept(pair, content, key)
    result = authorized_comparison(pair.a, shared, now=pd.Timestamp("2026-09-05"))
    assert result.b.outcome.actual_result.pnl == pair.b.outcome.actual_result.pnl
    assert result.status == pair.status
    assert key.encode() not in content
    assert all(ref.encode() not in content for ref in pair.b.episode.execution_refs)
    assert all(ref.startswith("shared_execution_") for ref in shared.facts.episode.execution_refs)
    assert shared.verification == "sender_secret_integrity_only_not_identity_or_independent_replay"


def test_derived_permission_does_not_grant_agent_or_cohort_or_raw(pair):
    content, key = export(pair)
    shared = accept(pair, content, key)
    with pytest.raises(ValueError, match="agent_access_not_granted"):
        authorized_comparison(pair.a, shared, now=pd.Timestamp("2026-09-05"), for_agent=True)
    payload = json.loads(content)["payload"]
    assert payload["allow_raw_executions"] is False
    assert payload["allow_cohort_contribution"] is False
    with pytest.raises(ValueError, match="consent"):
        export(pair, consent=False)


def test_wrong_recipient_expiry_and_mutated_payload_fail_closed(pair):
    content, key = export(pair)
    with pytest.raises(ValueError, match="recipient"):
        accept(pair, content, key, recipient_account_id="OTHER")
    with pytest.raises(ValueError, match="expired"):
        accept(pair, content, key, now=pd.Timestamp("2027-01-02"))
    envelope = json.loads(content)
    envelope["payload"]["facts"]["outcome"]["actual_result"]["pnl"] = 999999
    with pytest.raises(ValueError, match="signature"):
        accept(pair, json.dumps(envelope).encode(), key)
    with pytest.raises(ValueError, match="signature"):
        accept(pair, content, "x" * 40)


def test_explicit_agent_consent_is_checked_before_counterpart_use(pair):
    content, key = export(pair, agent=True)
    shared = accept(pair, content, key)
    result = authorized_comparison(pair.a, shared, now=pd.Timestamp("2026-09-05"), for_agent=True)
    assert result.b.episode.episode_id == pair.b.episode.episode_id
    with pytest.raises(ValueError, match="recipient"):
        authorized_comparison(pair.b, shared, now=pd.Timestamp("2026-09-05"), for_agent=True)
