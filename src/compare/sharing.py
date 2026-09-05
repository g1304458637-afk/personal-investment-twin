"""Limited Episode sharing, not remote account access or identity certification.

The sender explicitly exports derived facts and separately gives a recipient a
bearer secret. HMAC binds the exact scope/payload to that secret. It verifies
integrity and possession of the sender-provided secret, NOT the sender's legal
identity, brokerage records, or independent replay correctness. Never send the
secret to a model, store it in a share file, or treat it as cohort consent.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import secrets
import types
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pandas as pd

from src.compare.same_stock import EpisodeCompareFacts, compare_same_stock
from src.evidence.contracts import canonical_json_bytes
from src.presentation.runtime_episode import json_value

SHARE_VERSION = "episode_derived_share_v1"
MAX_SHARE_BYTES = 2_000_000


def _decode(kind, value):
    """Decode only the statically declared projection types; no dynamic imports."""
    origin, args = get_origin(kind), get_args(kind)
    if kind in (Any, object):
        canonical_json_bytes(value)
        return value
    if origin in (Union, types.UnionType):
        for candidate in args:
            try:
                return _decode(candidate, value)
            except (TypeError, ValueError):
                pass
        raise ValueError("invalid_share_field")
    if kind is type(None):
        if value is not None:
            raise ValueError("invalid_share_null")
        return None
    if origin is Literal:
        if value not in args:
            raise ValueError("invalid_share_enum")
        return value
    if kind is pd.Timestamp:
        if not isinstance(value, str):
            raise ValueError("invalid_share_time")
        result = pd.Timestamp(value)
        if pd.isna(result):
            raise ValueError("invalid_share_time")
        return result
    if dataclasses.is_dataclass(kind):
        fields = dataclasses.fields(kind)
        if not isinstance(value, dict) or set(value) != {f.name for f in fields}:
            raise ValueError("invalid_share_schema")
        hints = get_type_hints(kind)
        return kind(**{f.name: _decode(hints[f.name], value[f.name]) for f in fields})
    if origin in (tuple, list, Sequence):
        if not isinstance(value, list):
            raise ValueError("invalid_share_array")
        if origin is tuple and len(args) > 1 and args[-1] is not Ellipsis:
            if len(value) != len(args):
                raise ValueError("invalid_share_tuple")
            return tuple(_decode(t, v) for t, v in zip(args, value))
        items = [_decode(args[0], v) for v in value]
        return tuple(items) if origin is not list else items
    if origin in (dict, Mapping):
        if not isinstance(value, dict):
            raise ValueError("invalid_share_mapping")
        return {_decode(args[0], k): _decode(args[1], v) for k, v in value.items()}
    if kind is float and type(value) in (int, float) and math.isfinite(value):
        return float(value)
    if kind in (str, int, bool) and type(value) is kind:
        return value
    raise ValueError("invalid_share_type")


@dataclasses.dataclass(frozen=True, slots=True)
class AuthorizedEpisodeShare:
    share_id: str
    recipient_subject_id: str
    recipient_account_id: str
    facts: EpisodeCompareFacts
    allow_agent_review: bool
    expires_at: pd.Timestamp
    verification: str = "sender_secret_integrity_only_not_identity_or_independent_replay"


def create_episode_share(facts: EpisodeCompareFacts, *, recipient_subject_id: str,
                         recipient_account_id: str, expires_at: pd.Timestamp,
                         allow_agent_review: bool, owner_confirmed: bool) -> tuple[bytes, str]:
    if owner_confirmed is not True or not recipient_subject_id.strip() or not recipient_account_id.strip():
        raise ValueError("explicit_owner_consent_and_recipient_required")
    if not isinstance(allow_agent_review, bool) or pd.isna(expires_at):
        raise ValueError("invalid_share_permission")
    if compare_same_stock(facts, facts).status == "unavailable":
        raise ValueError("invalid_episode_facts")
    payload = {"version": SHARE_VERSION, "scope": "specified_episode_derived_comparison",
               "recipient_subject_id": recipient_subject_id, "recipient_account_id": recipient_account_id,
               "allow_agent_review": allow_agent_review, "allow_raw_executions": False,
               "allow_cohort_contribution": False, "expires_at": pd.Timestamp(expires_at).isoformat(),
               "facts": json_value(facts)}
    # Replace original execution identifiers everywhere, preserving resolvable
    # internal links without exposing broker identifiers through a derived share.
    replacements = {ref: "shared_execution_" + hashlib.sha256(ref.encode()).hexdigest()
                    for ref in facts.episode.execution_refs}
    def redact(v):
        if isinstance(v, str):
            return replacements.get(v, v)
        if isinstance(v, list):
            return [redact(x) for x in v]
        if isinstance(v, dict):
            return {k: redact(x) for k, x in v.items()}
        return v
    payload = redact(payload)
    secret = secrets.token_urlsafe(32)
    signature = hmac.new(secret.encode(), canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    encoded = canonical_json_bytes({"payload": payload, "signature": signature})
    if len(encoded) > MAX_SHARE_BYTES:
        raise ValueError("share_too_large")
    return encoded, secret


def accept_episode_share(content: bytes, secret: str, *, recipient_subject_id: str,
                         recipient_account_id: str, now: pd.Timestamp) -> AuthorizedEpisodeShare:
    if not isinstance(content, bytes) or len(content) > MAX_SHARE_BYTES or len(secret) < 32:
        raise ValueError("invalid_share")
    try:
        envelope = json.loads(content)
        if set(envelope) != {"payload", "signature"}:
            raise ValueError("invalid_share_envelope")
        p = envelope["payload"]
        expected = hmac.new(secret.encode(), canonical_json_bytes(p), hashlib.sha256).hexdigest()
        if not isinstance(envelope["signature"], str) or not hmac.compare_digest(expected, envelope["signature"]):
            raise ValueError("share_signature_mismatch")
        expected_keys = {"version", "scope", "recipient_subject_id", "recipient_account_id",
                         "allow_agent_review", "allow_raw_executions", "allow_cohort_contribution",
                         "expires_at", "facts"}
        if set(p) != expected_keys or p["version"] != SHARE_VERSION or p["scope"] != "specified_episode_derived_comparison":
            raise ValueError("invalid_share_scope")
        if (p["recipient_subject_id"], p["recipient_account_id"]) != (recipient_subject_id, recipient_account_id):
            raise ValueError("share_recipient_mismatch")
        if p["allow_raw_executions"] is not False or p["allow_cohort_contribution"] is not False or type(p["allow_agent_review"]) is not bool:
            raise ValueError("unsupported_share_permission")
        expires = _decode(pd.Timestamp, p["expires_at"])
        if expires <= pd.Timestamp(now):
            raise ValueError("share_expired")
        facts = _decode(EpisodeCompareFacts, p["facts"])
        if compare_same_stock(facts, facts).status == "unavailable":
            raise ValueError("invalid_episode_facts")
        return AuthorizedEpisodeShare("share_" + hashlib.sha256(content).hexdigest(), recipient_subject_id,
                                      recipient_account_id, facts, p["allow_agent_review"], expires)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_share") from exc


def authorized_comparison(own: EpisodeCompareFacts, shared: AuthorizedEpisodeShare, *,
                          now: pd.Timestamp, for_agent: bool = False):
    if (own.episode.subject_id, own.episode.account_id) != (shared.recipient_subject_id, shared.recipient_account_id):
        raise ValueError("share_recipient_mismatch")
    if pd.Timestamp(now) >= shared.expires_at:
        raise ValueError("share_expired")
    if for_agent and not shared.allow_agent_review:
        raise ValueError("agent_access_not_granted")
    return compare_same_stock(own, shared.facts)
