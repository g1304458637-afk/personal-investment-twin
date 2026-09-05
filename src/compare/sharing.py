"""Limited Episode sharing, not remote account access or identity certification.

The sender signs an exact derived payload with an ephemeral Ed25519 private
key that is NEVER exported. The recipient separately verifies the public-key
fingerprint with the sender. A recipient holding that fingerprint cannot
re-sign altered permissions. This does not certify legal identity, brokerage
truth or independent replay. HMAC v1 packages are deliberately rejected.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pandas as pd
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from src.compare.same_stock import EpisodeCompareFacts, compare_same_stock
from src.evidence.contracts import canonical_json_bytes
from src.presentation.runtime_episode import json_value

SHARE_VERSION = "episode_derived_share_v2"
VERIFICATION = "pinned_sender_ed25519_signature_not_identity_or_independent_replay"
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
    signer_fingerprint: str
    verification: str = VERIFICATION


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
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    signature = private_key.sign(canonical_json_bytes(payload)).hex()
    encoded = canonical_json_bytes({"payload": payload, "public_key": public_key.hex(), "signature": signature})
    if len(encoded) > MAX_SHARE_BYTES:
        raise ValueError("share_too_large")
    return encoded, hashlib.sha256(public_key).hexdigest()


def accept_episode_share(content: bytes, trusted_sender_fingerprint: str, *, recipient_subject_id: str,
                         recipient_account_id: str, now: pd.Timestamp) -> AuthorizedEpisodeShare:
    if not isinstance(content, bytes) or len(content) > MAX_SHARE_BYTES or not isinstance(trusted_sender_fingerprint, str):
        raise ValueError("invalid_share")
    try:
        envelope = json.loads(content)
        if set(envelope) != {"payload", "public_key", "signature"}:
            raise ValueError("invalid_share_envelope")
        p = envelope["payload"]
        public_bytes = bytes.fromhex(envelope["public_key"])
        fingerprint = hashlib.sha256(public_bytes).hexdigest()
        if not hmac.compare_digest(fingerprint, trusted_sender_fingerprint):
            raise ValueError("share_signature_fingerprint_mismatch")
        try:
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(
                bytes.fromhex(envelope["signature"]), canonical_json_bytes(p))
        except InvalidSignature as exc:
            raise ValueError("share_signature_mismatch") from exc
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
                                      recipient_account_id, facts, p["allow_agent_review"], expires, fingerprint)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_share") from exc


def authorized_comparison(own: EpisodeCompareFacts, shared: AuthorizedEpisodeShare, *,
                          now: pd.Timestamp, for_agent: bool = False):
    if shared.verification != VERIFICATION:
        raise ValueError("legacy_share_requires_signed_reexport")
    if (own.episode.subject_id, own.episode.account_id) != (shared.recipient_subject_id, shared.recipient_account_id):
        raise ValueError("share_recipient_mismatch")
    if pd.Timestamp(now) >= shared.expires_at:
        raise ValueError("share_expired")
    if for_agent and not shared.allow_agent_review:
        raise ValueError("agent_access_not_granted")
    return compare_same_stock(own, shared.facts)
