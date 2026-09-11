"""Bounded, backend-owned conversation context for review follow-ups.

Only a saved, validated review answer may enter this context. Conversation
turns help resolve references in a new question; they are never canonical
records, evidence receipts, or additions to the claim allowlist.
"""

from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd


VERSION = "review_conversation_v1"
ANSWER_VERSION = "question_driven_review_answer_v2"
MAX_HISTORY = 3
MAX_ANSWER_BYTES = 20_000


def normalize_request_scope(params):
    """Return the exact review source/authorization scope, with no secrets."""
    scope = {}
    for key in ("subject_id", "account_id", "episode_id"):
        value = params.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key}_required")
        scope[key] = value.strip()
    mode = params.get("data_mode", "real_user")
    if not isinstance(mode, str) or not mode:
        raise ValueError("unsupported_review_data_mode")
    share_id = params.get("share_id")
    if share_id is not None and (not isinstance(share_id, str) or not share_id.strip()):
        raise ValueError("share_id_required")
    scope.update({
        "scope_kind": "episode",
        "data_mode": mode,
        "compare_pair": params.get("compare_pair") is True,
        "pair_side": params.get("pair_side", "A"),
        "share_id": share_id.strip() if isinstance(share_id, str) else None,
    })
    return scope


def _bilingual(value):
    return (isinstance(value, dict) and set(value) == {"zh", "en"}
            and all(isinstance(value[key], str) for key in ("zh", "en")))


def sanitize_answer(answer):
    """Validate and copy the deterministic structured answer projection."""
    if not isinstance(answer, dict) or set(answer) != {
        "version", "focus", "summary", "comparison_summary", "findings", "qualification"
    }:
        raise ValueError("review_previous_inference_legacy")
    if answer["version"] != ANSWER_VERSION or answer["focus"] not in {
        "result_formation", "operation_impact", "decision_reason", "available_facts"
    }:
        raise ValueError("review_previous_inference_legacy")
    if not _bilingual(answer["summary"]) or not _bilingual(answer["qualification"]):
        raise ValueError("review_previous_inference_legacy")
    comparisons = answer["comparison_summary"]
    findings = answer["findings"]
    if (not isinstance(comparisons, list) or len(comparisons) > 4
            or not all(_bilingual(item) for item in comparisons)
            or not isinstance(findings, list) or len(findings) > 3):
        raise ValueError("review_previous_inference_legacy")
    finding_keys = {"option_id", "kind", "evidence_ref", "decision_id", "title", "body",
                    "qualification", "difference_direction"}
    for item in findings:
        if (not isinstance(item, dict) or set(item) != finding_keys
                or not all(isinstance(item[key], str) for key in ("option_id", "kind", "evidence_ref"))
                or item["decision_id"] is not None and not isinstance(item["decision_id"], str)
                or item["difference_direction"] is not None
                    and item["difference_direction"] not in {"positive", "negative", "zero"}
                or not all(_bilingual(item[key]) for key in ("title", "body", "qualification"))):
            raise ValueError("review_previous_inference_legacy")
    try:
        copied = json.loads(json.dumps(answer, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise ValueError("review_previous_inference_legacy") from None
    if len(json.dumps(copied, ensure_ascii=False).encode()) > MAX_ANSWER_BYTES:
        raise ValueError("review_previous_inference_legacy")
    return copied


def _validated_history(history, *, source_fingerprint, note_fingerprint):
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("review_previous_inference_legacy")
    validated = []
    for turn in history:
        if not isinstance(turn, dict) or set(turn) != {
            "inference_id", "question", "answer", "source_fingerprint", "note_fingerprint"
        }:
            raise ValueError("review_previous_inference_legacy")
        if (not isinstance(turn["inference_id"], str) or not turn["inference_id"].startswith("inference_")
                or not isinstance(turn["question"], str) or not turn["question"].strip()
                or len(turn["question"]) > 2000
                or turn["source_fingerprint"] != source_fingerprint
                or turn["note_fingerprint"] != note_fingerprint):
            raise ValueError("review_previous_inference_legacy")
        validated.append({**turn, "answer": sanitize_answer(turn["answer"])})
    return validated


def resolve_previous_inference(store, *, previous_inference_id, request_scope,
                               source_fingerprint, note_fingerprint, now):
    """Resolve only the latest owned inference and return safe persisted turns."""
    if (not isinstance(previous_inference_id, str) or not previous_inference_id.startswith("inference_")
            or len(previous_inference_id) > 128):
        raise ValueError("review_previous_inference_invalid")
    identity = tuple(request_scope[key] for key in ("subject_id", "account_id", "episode_id"))
    row = store.connection.execute(
        "SELECT payload,invalidated,replaced_by FROM review_inferences_v1 "
        "WHERE inference_id=? AND subject_id=? AND account_id=? AND episode_id=?",
        (previous_inference_id, *identity),
    ).fetchone()
    if row is None:  # Unknown and non-owned IDs intentionally have one public result.
        raise ValueError("review_previous_inference_unavailable")
    if bool(row[1]) or row[2] is not None:
        raise ValueError("review_previous_inference_not_latest")
    try:
        payload = json.loads(row[0])
    except (TypeError, ValueError):
        raise ValueError("review_previous_inference_legacy") from None
    conversation = payload.get("conversation") if isinstance(payload, dict) else None
    if (not isinstance(conversation, dict) or conversation.get("version") != VERSION
            or payload.get("inference_id") != previous_inference_id):
        raise ValueError("review_previous_inference_legacy")
    if conversation.get("model_data_consent") is not True:
        raise ValueError("review_previous_inference_unconsented")
    if conversation.get("request_scope") != request_scope:
        raise ValueError("review_conversation_scope_mismatch")
    if (conversation.get("source_fingerprint") != source_fingerprint
            or conversation.get("note_fingerprint") != note_fingerprint
            or payload.get("source_fingerprint") != source_fingerprint
            or payload.get("note_fingerprint") != note_fingerprint):
        raise ValueError("review_conversation_stale")
    if payload.get("authorization_share_id") != request_scope["share_id"]:
        raise ValueError("review_conversation_scope_mismatch")
    share_id = request_scope["share_id"]
    if share_id:
        try:
            share = store.share(share_id, *identity[:2])
        except ValueError:
            raise ValueError("review_conversation_share_unavailable") from None
        if not share.allow_agent_review or share.expires_at <= pd.Timestamp(now):
            raise ValueError("review_conversation_share_unavailable")
    question = conversation.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("review_previous_inference_legacy")
    history = _validated_history(conversation.get("history"),
        source_fingerprint=source_fingerprint, note_fingerprint=note_fingerprint)
    expected_previous = conversation.get("previous_inference_id")
    if history:
        if expected_previous != history[-1]["inference_id"]:
            raise ValueError("review_previous_inference_legacy")
    elif expected_previous is not None:
        raise ValueError("review_previous_inference_legacy")
    history.append({
        "inference_id": previous_inference_id,
        "question": question,
        "answer": sanitize_answer(payload.get("answer")),
        "source_fingerprint": source_fingerprint,
        "note_fingerprint": note_fingerprint,
    })
    return history[-MAX_HISTORY:]


def build_conversation_metadata(*, question, previous_inference_id, request_scope,
                                source_fingerprint, note_fingerprint, history):
    return {
        "version": VERSION,
        "model_data_consent": True,
        "question": question,
        "previous_inference_id": previous_inference_id,
        "request_scope": deepcopy(request_scope),
        "source_fingerprint": source_fingerprint,
        "note_fingerprint": note_fingerprint,
        "history": deepcopy(list(history)[-MAX_HISTORY:]),
    }


def conversation_for_model(history):
    """Strip persistence metadata before sending the untrusted transcript view."""
    if not history:
        return None
    return {
        "trust": "untrusted_not_evidence",
        "purpose": "resolve_references_in_current_question_only",
        "history": [{"user_question": turn["question"],
                     "validated_structured_answer": deepcopy(turn["answer"])}
                    for turn in history[-MAX_HISTORY:]],
    }


def validate_model_conversation(value):
    """Reject arbitrary caller transcript text at the runner boundary."""
    if value is None:
        return None
    if (not isinstance(value, dict) or value.get("trust") != "untrusted_not_evidence"
            or value.get("purpose") != "resolve_references_in_current_question_only"
            or set(value) != {"trust", "purpose", "history"}
            or not isinstance(value["history"], list)
            or not 1 <= len(value["history"]) <= MAX_HISTORY):
        raise ValueError("invalid_review_conversation_context")
    safe = []
    for turn in value["history"]:
        if (not isinstance(turn, dict) or set(turn) != {"user_question", "validated_structured_answer"}
                or not isinstance(turn["user_question"], str) or not turn["user_question"].strip()
                or len(turn["user_question"]) > 2000):
            raise ValueError("invalid_review_conversation_context")
        safe.append({"user_question": turn["user_question"],
                     "validated_structured_answer": sanitize_answer(turn["validated_structured_answer"])})
    return {"trust": value["trust"], "purpose": value["purpose"], "history": safe}
