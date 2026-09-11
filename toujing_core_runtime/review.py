"""Narrow local review/share RPC. No arbitrary code, SQL or counterpart reads."""

import asyncio
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from threading import Event
from uuid import uuid4

import pandas as pd

from src.agents.decision_review import run_decision_review
from src.agents.desktop_demo_source import load_demo_review, source_fingerprint as demo_source_fingerprint
from src.demo import showcase
from src.demo.showcase_runtime import (
    DATA_MODE as SHOWCASE_DATA_MODE,
    build_showcase_pair,
    load_showcase_review,
    source_fingerprint as showcase_source_fingerprint,
)
from src.agents.investment_coach import create_model_runtime
from src.agents.review_catalog import build_review_catalog
from src.agents.review_conversation import (
    build_conversation_metadata,
    conversation_for_model,
    normalize_request_scope,
    resolve_previous_inference,
)
from src.agents.review_sources import build_owned_self_history
from src.agents.review_store import ReviewStore, utc_now
from src.compare.demo import build_pair, pair_inputs
from src.compare.same_stock import build_episode_compare_facts
from src.compare.sharing import (MAX_SHARE_BYTES, accept_episode_share, authorized_comparison, create_episode_share)
from src.core.canonical_execution import canonical_executions_to_frame
from src.evidence.contracts import canonical_json_bytes
from src.episodes.position_episode import build_position_episode_lifecycle
from src.market_data.models import facts_to_market_data_frame
from src.presentation.runtime_episode import episode_entry, json_value


@lru_cache(maxsize=1)
def _pair():
    return build_pair()


def _text(params, key):
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return value.strip()


class ReviewRuntime:
    def __init__(self, product):
        self.product = product
        self.store = ReviewStore(product.repo.connection)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="toujing-review")
        self.jobs = {}
        self.demo_sources = {}
        self._context_cache = {}
        self._account_service = None

    def _account(self):
        if self._account_service is None:
            from .account_review import AccountReviewService
            self._account_service = AccountReviewService(self.product)
        return self._account_service

    def _demo(self, params):
        scope = tuple(_text(params, k) for k in ("subject_id", "account_id", "episode_id"))
        mode = params.get("data_mode")
        if mode == "synthetic_episode":
            fingerprint, loader = demo_source_fingerprint(*scope[:2]), load_demo_review
        elif mode == SHOWCASE_DATA_MODE:
            fingerprint, loader = showcase_source_fingerprint(*scope[:2]), load_showcase_review
        else:  # This helper must never become a fallback source resolver.
            raise ValueError("unregistered_synthetic_review_source")
        key = (*scope, fingerprint)
        if key not in self.demo_sources:
            self.demo_sources[key] = loader(*scope)
            while len(self.demo_sources) > 8:
                del self.demo_sources[next(iter(self.demo_sources))]
        return self.demo_sources[key]

    def close(self):
        if self._account_service is not None:
            self._account_service.close()
        for job in self.jobs.values():
            job["cancelled"].set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _own(self, params, cutoff=None):
        subject, account, episode = (_text(params, key) for key in ("subject_id", "account_id", "episode_id"))
        mode = params.get("data_mode", "real_user")
        if mode == "synthetic_episode":
            if cutoff is not None or params.get("share_id") or params.get("compare_pair"):
                raise ValueError("synthetic_episode_review_only")
            own, frame, market, _ = self._demo(params)
            return own, frame.copy(deep=True), market.copy(deep=True), 100_000.0
        if mode == SHOWCASE_DATA_MODE:
            if cutoff is not None or params.get("share_id"):
                raise ValueError("synthetic_showcase_review_only")
            own, frame, market, _ = self._demo(params)
            return own, frame.copy(deep=True), market.copy(deep=True), 100_000.0
        if mode == "synthetic_pair":
            who = params.get("pair_side", "A")
            if who not in {"A", "B"}:
                raise ValueError("invalid_pair_side")
            own = _pair().a if who == "A" else _pair().b
            if (subject, account, episode) != (own.episode.subject_id, own.episode.account_id, own.episode.episode_id):
                raise ValueError("synthetic_scope_mismatch")
            frames, market = pair_inputs()
            return own, frames[who], market, 100_000.0
        if mode != "real_user":
            raise ValueError("unsupported_review_data_mode")
        info, bundle, prices, lifecycle, status = self.product._lifecycle(params)
        if lifecycle is None:
            raise ValueError(f"review_unavailable:{status}")
        selected = next((e for e in lifecycle.episodes if e.episode_id == episode), None)
        if selected is None:
            raise ValueError("episode_not_owned_by_selected_account")
        when = pd.Timestamp(cutoff) if cutoff is not None else lifecycle.as_of
        if when > lifecycle.as_of:
            raise ValueError("requested_as_of_not_available")
        inst = next(x.instrument for x in bundle.accepted_canonical_executions if x.instrument.instrument_id == selected.instrument_id)
        frame, market = canonical_executions_to_frame(bundle.accepted_canonical_executions), facts_to_market_data_frame(prices)
        own = build_episode_compare_facts(frame, market, subject_id=subject, account_id=account,
            instrument=inst, as_of=when, init_cash=float(info["initial_cash"]), data_tier="authorized_beta", episode_id=episode)
        return own, frame, market, float(info["initial_cash"])

    def _context(self, params, *, for_agent=False):
        own, frame, market, cash = self._own(params)
        comparison = None
        share_id = params.get("share_id")
        # Reuse the exact deterministic projection between preparation/start.
        # Never cache grants: shared contexts still run authorization/expiry on
        # every access. Every caller receives fresh tool receipts/access state.
        cache_key = None
        if not share_id:
            identity = (own.episode.subject_id, own.episode.account_id, own.episode.episode_id)
            cache_key = (canonical_json_bytes(normalize_request_scope(params)),
                         self._source_fingerprint(params), self.store.note_fingerprint(*identity),
                         own.as_of.isoformat(), cash, "review_context_cache_v1")
            if cache_key in self._context_cache:
                return copy.deepcopy(self._context_cache[cache_key])
        if share_id:
            share = self.store.share(_text(params, "share_id"), own.episode.subject_id, own.episode.account_id)
            own, frame, market, cash = self._own(params, share.facts.as_of)
            comparison = authorized_comparison(own, share, now=pd.Timestamp(utc_now()), for_agent=for_agent)
            if comparison.status == "unavailable":
                raise ValueError("comparison_unavailable:" + ";".join(comparison.reasons))
        elif params.get("data_mode") == "synthetic_pair" and params.get("compare_pair") is True:
            from src.compare.same_stock import compare_same_stock
            other = _pair().b if params.get("pair_side", "A") == "A" else _pair().a
            comparison = compare_same_stock(own, other)
        elif params.get("data_mode") == SHOWCASE_DATA_MODE and params.get("compare_pair") is True:
            from src.compare.same_stock import compare_same_stock
            side = params.get("pair_side", "A")
            if side not in {"A", "B"}:
                raise ValueError("invalid_pair_side")
            comparison, _ = build_showcase_pair()
            if side == "B":
                comparison = compare_same_stock(comparison.b, comparison.a)
            expected = comparison.a
            if expected.episode != own.episode:
                raise ValueError("showcase_comparison_requires_first_growth_episode")
        history = build_owned_self_history(frame, market, subject_id=own.episode.subject_id,
            account_id=own.episode.account_id, as_of=own.as_of, init_cash=cash, data_tier=own.episode.data_tier)
        lifecycle = build_position_episode_lifecycle(frame, market, subject_id=own.episode.subject_id,
            account_id=own.episode.account_id, as_of=own.as_of, init_cash=cash,
            data_tier=own.episode.data_tier, calculation_code_version="review_sources_v1")
        entry = episode_entry(lifecycle, frame, market, episode_id=own.episode.episode_id,
            init_cash=cash, display_name=own.instrument.display_name or own.instrument.local_symbol,
            currency=own.instrument.currency)
        counterfactuals = (*entry["outcome_story"]["counterfactuals"], *entry["path_analysis"]["phase_counterfactuals"])
        e = own.episode
        notes = self.store.notes(e.subject_id, e.account_id, e.episode_id)
        context = build_review_catalog(own, comparison=comparison, self_history=history,
            self_history_account_id=e.account_id, notes=notes, counterfactuals=counterfactuals)
        if cache_key is not None:
            self._context_cache[cache_key] = copy.deepcopy((context, comparison, entry))
            while len(self._context_cache) > 8:
                del self._context_cache[next(iter(self._context_cache))]
        return context, comparison, entry

    def context(self, params):
        if params.get("scope_kind") in {"account", "episode"}:
            return self._account().context(params)
        context, comparison, _ = self._context(params)
        fingerprint = self._source_fingerprint(params)
        inferences = self.store.inferences(context.own.episode.subject_id, context.own.episode.account_id, context.own.episode.episode_id)
        # An old inference is not evidence for the newly imported account state.
        inferences = [r if r.get("source_fingerprint") == fingerprint else
                      {**r, "invalidated": True, "invalidation_reason": "account_facts_changed"} for r in inferences]
        for record in inferences:
            if record.get("authorization_share_id"):
                try:
                    grant = self.store.share(record["authorization_share_id"], context.own.episode.subject_id, context.own.episode.account_id)
                    permitted = grant.allow_agent_review and grant.expires_at > pd.Timestamp(utc_now())
                except ValueError:
                    permitted = False
                if not permitted:
                    record.update(invalidated=True, invalidation_reason="share_permission_expired_or_revoked")
        return {"scope": {"subject_id": context.own.episode.subject_id, "account_id": context.own.episode.account_id,
                          "episode_id": context.own.episode.episode_id},
                "request_scope": normalize_request_scope(params),
                "source_fingerprint": fingerprint,
                "note_fingerprint": self.store.note_fingerprint(context.own.episode.subject_id, context.own.episode.account_id, context.own.episode.episode_id),
                "as_of": context.own.as_of.isoformat(), "data_tier": context.own.episode.data_tier,
                "records": [asdict(r) for r in context.records.values()], "comparison": json_value(comparison),
                "inferences": inferences,
                "identity_mapping": self._demo(params)[3]
                if params.get("data_mode") in {"synthetic_episode", SHOWCASE_DATA_MODE} else None}

    def _source_fingerprint(self, params):
        if params.get("data_mode") == "synthetic_episode":
            return demo_source_fingerprint(_text(params, "subject_id"), _text(params, "account_id"))
        if params.get("data_mode") == SHOWCASE_DATA_MODE:
            subject, account = (_text(params, key) for key in ("subject_id", "account_id"))
            own = showcase_source_fingerprint(subject, account)
            if params.get("compare_pair") is not True:
                return own
            # The registered showcase comparison always contains both exact
            # synthetic accounts; a reference change must stale an A-side job.
            paired = {
                showcase.SUBJECT_ID: showcase_source_fingerprint(
                    showcase.SUBJECT_ID, showcase.SUBJECT_ID
                ),
                showcase.REFERENCE_SUBJECT: showcase_source_fingerprint(
                    showcase.REFERENCE_SUBJECT, showcase.REFERENCE_SUBJECT
                ),
            }
            if subject not in paired or account != subject:
                raise ValueError("unregistered_showcase_scope")
            return hashlib.sha256(canonical_json_bytes({"own": own, "pair": paired})).hexdigest()
        if params.get("data_mode") == "synthetic_pair":
            source = _pair().comparison_id
        else:
            subject, account = (_text(params, k) for k in ("subject_id", "account_id"))
            source = json_value((self.product.repo.executions(subject, account), self.product.repo.prices(subject, account)))
        return hashlib.sha256(canonical_json_bytes(source)).hexdigest()

    def add_note(self, params):
        own, _, _, _ = self._own(params)
        decision = params.get("decision_id")
        if decision is not None and decision not in own.episode.decision_refs:
            raise ValueError("decision_not_in_episode")
        return {"note": self.store.add_note(subject_id=own.episode.subject_id, account_id=own.episode.account_id,
            episode_id=own.episode.episode_id, text=params.get("text"), note_kind=params.get("note_kind"), decision_id=decision)}

    def start(self, params):
        if params.get("scope_kind") in {"account", "episode"}:
            return self._account().start(params)
        if params.get("allow_model_review") is not True:
            raise ValueError("explicit_model_data_consent_required")
        if any(not j["future"].done() for j in self.jobs.values()):
            raise ValueError("review_already_running")
        question = _text(params, "question")
        if len(question) > 2000:
            raise ValueError("question_too_long")
        request_metadata = normalize_request_scope(params)
        identity = tuple(request_metadata[key] for key in ("subject_id", "account_id", "episode_id"))
        source_fingerprint = self._source_fingerprint(params)
        note_fingerprint = self.store.note_fingerprint(*identity)
        previous_inference_id = params.get("previous_inference_id")
        history = []
        if previous_inference_id is not None:
            history = resolve_previous_inference(self.store,
                previous_inference_id=previous_inference_id,
                request_scope=request_metadata,
                source_fingerprint=source_fingerprint,
                note_fingerprint=note_fingerprint,
                now=utc_now())
        context, _, _ = self._context(params, for_agent=True)
        # Desktop IPC credentials are ephemeral; CLI callers keep their existing env path.
        from .model_service import desktop_runtime
        model_runtime = (desktop_runtime(params["_desktop_model_key"], factory=create_model_runtime)
                         if "_desktop_model_key" in params else create_model_runtime())
        e = context.own.episode
        job_id = "review_job_" + uuid4().hex
        cancelled = Event()
        expires = None
        if params.get("share_id"):
            expires = self.store.share(params["share_id"], e.subject_id, e.account_id).expires_at
        context.access_allowed = lambda: not cancelled.is_set() and (expires is None or pd.Timestamp(utc_now()) < expires)
        async def bounded():
            return await asyncio.wait_for(run_decision_review(question, context, runtime=model_runtime,
                conversation_context=conversation_for_model(history)), timeout=90)
        scope = (e.subject_id, e.account_id, e.episode_id)
        # The worker uses immutable projections, never this SQLite connection.
        self.jobs[job_id] = {"future": self.executor.submit(lambda: asyncio.run(bounded())),
            "scope": scope, "note_fingerprint": note_fingerprint,
            "request_scope": tuple(_text(params, k) for k in ("subject_id", "account_id", "episode_id")),
            "request_metadata": request_metadata, "question": question,
            "previous_inference_id": previous_inference_id, "conversation_history": history,
            "source_params": {k: params[k] for k in ("subject_id", "account_id", "data_mode", "compare_pair", "pair_side") if k in params},
            "source_fingerprint": source_fingerprint,
            "share_id": params.get("share_id"), "result": None, "cancelled": cancelled}
        # Bound completed receipts without cancelling a running request.
        for key in list(self.jobs)[:-16]:
            if self.jobs[key]["future"].done():
                del self.jobs[key]
        return {"job_id": job_id, "status": "running"}

    def poll(self, params):
        if params.get("scope_kind") in {"account", "episode"}:
            return self._account().poll(params)
        scope = tuple(_text(params, key) for key in ("subject_id", "account_id", "episode_id"))
        job = self.jobs.get(_text(params, "job_id"))
        if not job or job.get("request_scope", job["scope"]) != scope:
            raise ValueError("review_job_not_owned")
        scope = job["scope"]
        if self.store.note_fingerprint(*scope) != job["note_fingerprint"]:
            job["cancelled"].set()
            return {"status": "stale", "reason": "new_user_information_requires_new_review", "result": None}
        if self._source_fingerprint(job["source_params"]) != job["source_fingerprint"]:
            job["cancelled"].set()
            return {"status": "stale", "reason": "account_facts_changed", "result": None}
        if job["share_id"]:
            share = self.store.share(job["share_id"], *scope[:2])
            if share.expires_at <= pd.Timestamp(utc_now()) or not share.allow_agent_review:
                raise ValueError("agent_share_permission_expired_or_revoked")
        if not job["future"].done():
            return {"status": "running", "result": None}
        try:
            result = job["future"].result()
        except Exception as exc:
            # Capture once per job, with an explicit metadata allowlist. No raw exception.
            if "failure" not in job:
                from src.agents.review_diagnostics import safe_failure, failure_reason
                from pathlib import Path
                diagnostic = safe_failure(exc)
                diagnostic["diagnostic_id"] = uuid4().hex[:12]
                diagnostic["error_type"] = type(exc).__name__ if type(exc).__name__ in {
                    "ReviewVerificationError", "StructuredFinalizationUnavailable", "TimeoutError"} else "ReviewRuntimeError"
                job["failure"] = {"status": "failed", "reason": failure_reason(exc), "result": None,
                                  "diagnostic": diagnostic}
                database = self.store.connection.execute("PRAGMA database_list").fetchone()[2]
                if database:
                    try:
                        with (Path(database).parent / "review-diagnostics.jsonl").open("a", encoding="utf-8") as log:
                            log.write(json.dumps(diagnostic, ensure_ascii=True) + "\n")
                    except OSError:
                        pass  # Reporting a failure must not depend on writable logging.
            return job["failure"]
        if job["result"] is None:
            conversation = build_conversation_metadata(
                question=job["question"], previous_inference_id=job["previous_inference_id"],
                request_scope=job["request_metadata"], source_fingerprint=job["source_fingerprint"],
                note_fingerprint=job["note_fingerprint"], history=job["conversation_history"])
            job["result"] = self.store.save_inference({**result,
                "source_fingerprint": job["source_fingerprint"],
                "note_fingerprint": job["note_fingerprint"],
                "authorization_share_id": job["share_id"], "conversation": conversation})
        return {"status": "complete", "result": job["result"]}

    def export_share(self, params):
        own, _, _, _ = self._own(params)
        content, fingerprint = create_episode_share(own,
            recipient_subject_id=_text(params, "recipient_subject_id"),
            recipient_account_id=_text(params, "recipient_account_id"),
            expires_at=pd.Timestamp(_text(params, "expires_at")),
            allow_agent_review=params.get("allow_agent_review", False), owner_confirmed=params.get("owner_confirmed"))
        path = Path(_text(params, "file_path"))
        if not path.name.endswith(".toujing-share.json"):
            raise ValueError("share_filename_must_end_with_toujing_share_json")
        # Exclusive create prevents arbitrary overwrites through an RPC path.
        with path.open("xb") as output:
            output.write(content)
        return {"filename": path.name, "signer_fingerprint": fingerprint,
                "warning": "通过独立渠道核对发送方公钥指纹；它不证明真实身份，私钥不会导出。"}

    def import_share(self, params):
        subject, account = (_text(params, k) for k in ("subject_id", "account_id"))
        if not any((a["subject_id"], a["account_id"]) == (subject, account) for a in self.product.repo.list_accounts()):
            raise ValueError("recipient_account_not_found")
        path = Path(_text(params, "file_path"))
        if not path.name.endswith(".toujing-share.json") or path.stat().st_size > MAX_SHARE_BYTES:
            raise ValueError("invalid_share_file")
        with path.open("rb") as source:
            content = source.read(MAX_SHARE_BYTES + 1)
        share = accept_episode_share(content, _text(params, "trusted_sender_fingerprint"),
            recipient_subject_id=subject, recipient_account_id=account, now=pd.Timestamp(utc_now()))
        self.store.save_share(share)  # only validated derived facts, never a private signing key
        return {"share_id": share.share_id, "verification": share.verification}

    def list_shares(self, params):
        shares = self.store.shares(_text(params, "subject_id"), _text(params, "account_id"))
        return {"shares": [{"share_id": s.share_id, "instrument": json_value(s.facts.instrument),
                            "subject_id": s.facts.episode.subject_id, "episode_id": s.facts.episode.episode_id,
                            "as_of": s.facts.as_of.isoformat(), "expires_at": s.expires_at.isoformat(),
                            "allow_agent_review": s.allow_agent_review, "verification": s.verification} for s in shares]}

    def revoke_share(self, params):
        self.store.revoke_share(_text(params, "share_id"), _text(params, "subject_id"), _text(params, "account_id"))
        for job in self.jobs.values():
            if job["share_id"] == params["share_id"] and job["scope"][:2] == (params["subject_id"], params["account_id"]):
                job["cancelled"].set()
        return {"revoked": True}

    def drop_account(self, subject_id, account_id):
        if self._account_service is not None:
            self._account_service.drop_account(subject_id, account_id)
        self.store.delete_account_read_models(subject_id, account_id)
        for key, job in list(self.jobs.items()):
            if job["scope"][:2] == (subject_id, account_id):
                job["cancelled"].set()
                job["future"].cancel()
                del self.jobs[key]
