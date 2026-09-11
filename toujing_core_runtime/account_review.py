"""Whole-account review jobs, with a separate validated chat archive."""

from __future__ import annotations

import asyncio
import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4
from time import monotonic

import pandas as pd

from src.agents.account_review import run_account_review
from src.agents.account_review_sources import ACCOUNT_CONTEXT_VERSION, build_account_review_context
from src.agents.episode_conversation import focus_episode_context
from src.agents.owned_analysis_tools import attach_owned_analysis_sources
from src.core.canonical_execution import canonical_executions_to_frame
from src.demo import showcase
from src.demo.showcase_runtime import (
    DATA_MODE as SHOWCASE_DATA_MODE,
    _episode_mapping as showcase_episode_mapping,
    _lifecycle as showcase_lifecycle,
    is_showcase_scope,
    source_fingerprint as showcase_source_fingerprint,
)
from src.evidence.contracts import canonical_json_bytes
from src.market_data.models import facts_to_market_data_frame
from src.performance.account_series import DailyRiskPolicy
from src.presentation.runtime_episode import json_value


def _text(params, key):
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return value.strip()


def _scope(params) -> dict[str, str]:
    kind = params.get("scope_kind")
    if kind not in {"account", "episode"}:
        raise ValueError("account_review_scope_kind_required")
    if kind == "account" and params.get("episode_id") is not None and params.get("episode_id") != "":
        raise ValueError("account_review_does_not_accept_episode_id")
    subject, account = _text(params, "subject_id"), _text(params, "account_id")
    mode = params.get("data_mode", "real_user")
    if not isinstance(mode, str) or mode not in {"real_user", SHOWCASE_DATA_MODE}:
        raise ValueError("unsupported_account_review_data_mode")
    if any(params.get(key) is not None and params.get(key) is not False and params.get(key) != ""
           for key in ("share_id", "compare_pair", "pair_side")):
        raise ValueError("account_review_external_scope_not_allowed")
    return {
        "scope_kind": kind, "subject_id": subject,
        "account_id": account, "data_mode": str(mode),
        **({"episode_id": _text(params, "episode_id")} if kind == "episode" else {}),
    }


class AccountReviewService:
    """Session-local jobs with completed turns in a separate local archive."""

    def __init__(self, product):
        self.product = product
        from .chat_archive import ChatArchive
        path = getattr(getattr(product, "repo", None), "path", None)
        self.archive = ChatArchive(path.with_name(path.name + ".agent-chat.sqlite3")) if path else None
        self._loaded_scopes = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="toujing-account-review")
        self.jobs: dict[str, dict[str, object]] = {}
        self.completed: dict[str, dict[str, object]] = {}
        self._source_cache = {}
        self._lock = Lock()
        self._starting = False
        self._closed = False

    def close(self):
        with self._lock:
            self._closed = True
            for job in self.jobs.values():
                job["cancelled"].set()
            self.executor.shutdown(wait=False, cancel_futures=True)

    def drop_account(self, subject_id: str, account_id: str):
        """Forget jobs, results and the separate chat archive for a deleted account."""
        with self._lock:
            if self.archive:
                self.archive.drop_account(subject_id, account_id)
            for key in list(self._source_cache):
                if key[:2] == (subject_id, account_id):
                    del self._source_cache[key]
            for key, job in list(self.jobs.items()):
                scope = job["scope"]
                if (scope["subject_id"], scope["account_id"]) == (subject_id, account_id):
                    job["cancelled"].set()
                    job["future"].cancel()
                    del self.jobs[key]
            for key, item in list(self.completed.items()):
                scope = item["scope"]
                if (scope["subject_id"], scope["account_id"]) == (subject_id, account_id):
                    del self.completed[key]

    def _source_fingerprint(self, params) -> str:
        scope = _scope(params)
        subject, account, mode = scope["subject_id"], scope["account_id"], scope["data_mode"]
        if mode == SHOWCASE_DATA_MODE:
            source = showcase_source_fingerprint(subject, account)
        else:
            # Canonical repository values, not a UI projection or generated assistant text.
            account_rows = [
                item for item in self.product.repo.list_accounts()
                if item["subject_id"] == subject and item["account_id"] == account
            ]
            source = json_value((
                account_rows,
                self.product.repo.executions(subject, account),
                self.product.repo.prices(subject, account),
            ))
        return hashlib.sha256(canonical_json_bytes({"scope": scope, "source": source})).hexdigest()

    def _source_with_fingerprint(self, params):
        """Bind a built context to one stable valuation-driving source state."""
        before = self._source_fingerprint(params)
        scope = _scope(params)
        key = (scope["subject_id"], scope["account_id"], scope["data_mode"],
               scope["scope_kind"], scope.get("episode_id"))
        with self._lock:
            cached = self._source_cache.get(key)
        context = (copy.deepcopy(cached[1]) if cached and cached[0] == before
                   else self._source(params))
        after = self._source_fingerprint(params)
        if before != after:
            raise ValueError("account_facts_changed_during_review_context")
        if not cached or cached[0] != after:
            with self._lock:
                self._source_cache[key] = (after, copy.deepcopy(context))
                while len(self._source_cache) > 4:
                    del self._source_cache[next(iter(self._source_cache))]
        return context, after

    def _source(self, params):
        scope = _scope(params)
        subject, account, mode = scope["subject_id"], scope["account_id"], scope["data_mode"]
        if mode == SHOWCASE_DATA_MODE:
            if not is_showcase_scope(subject, account):
                raise ValueError("unregistered_showcase_scope")
            identities, frame, market, instruments = showcase_episode_mapping(subject)
            lifecycle = showcase_lifecycle(frame, market, subject_id=subject)
            display_names = {
                str(item.instrument_id): showcase.NAMES.get(item.local_symbol, {}).get("en", item.display_name or item.local_symbol)
                for item in instruments.values()
            }
            # The registered showcase declares its own complete weekday schedule.
            # Do not infer completeness from observed rows or reuse this calendar
            # for real accounts. The existing performance builder checks exact dates.
            risk_policy = DailyRiskPolicy(
                expected_observation_dates=tuple(pd.bdate_range(showcase.START, showcase.END).date),
                annualization_factor=252,
            )
            schedule_ref = (
                f"{showcase.VERSION}:declared_synthetic_weekdays_not_exchange_calendar:"
                f"{showcase.START}:{showcase.END}"
            )
            source_refs = tuple(dict.fromkeys((
                showcase.VERSION, schedule_ref,
                *(str(value) for value in frame["execution_id"].tolist()),
                *(f"{row.data_source}:{row.data_version}:{row.instrument}" for row in
                  market[["data_source", "data_version", "instrument"]].drop_duplicates().itertuples(index=False)),
            )))
            context = build_account_review_context(
                frame, market, subject_id=subject, account_id=account, data_mode=mode,
                as_of=lifecycle.as_of, init_cash=showcase.INITIAL_CASH,
                data_tier="synthetic", currency="CNY", lifecycle=lifecycle,
                display_names=display_names, source_refs=source_refs,
                include_conversation=True, risk_policy=risk_policy,
            )
            context.episode_display_ids = {
                episode.episode_id: str(identities[episode.episode_id]["display_episode_id"])
                for episode in lifecycle.episodes
            }
            if scope["scope_kind"] == "episode":
                return focus_episode_context(context, scope["episode_id"])
            attach_owned_analysis_sources(context, executions=frame, market_prices=market,
                init_cash=showcase.INITIAL_CASH, instruments=instruments,
                source_refs=source_refs)
            return context

        account_row, bundle, price_facts, lifecycle, status = self.product._lifecycle(params)
        if lifecycle is None:
            raise ValueError(f"account_review_unavailable:{status}")
        currencies = {
            str(item.instrument.currency).upper()
            for item in bundle.accepted_canonical_executions if item.instrument.currency
        }
        if len(currencies) != 1:
            raise ValueError("account_review_unavailable:base_currency_not_established")
        currency = next(iter(currencies))
        frame = canonical_executions_to_frame(bundle.accepted_canonical_executions)
        market = facts_to_market_data_frame(price_facts)
        display_names = {
            str(item.instrument.instrument_id): (
                item.instrument.display_name or item.instrument.display_symbol or item.instrument.local_symbol
            )
            for item in bundle.accepted_canonical_executions
        }
        source_refs = tuple(dict.fromkeys((
            *bundle.source_metadata_refs,
            *(item.execution_id for item in bundle.accepted_canonical_executions),
            *(item.observation_id for item in price_facts),
        )))
        context = build_account_review_context(
            frame, market, subject_id=subject, account_id=account, data_mode=mode,
            as_of=lifecycle.as_of, init_cash=float(account_row["initial_cash"]),
            data_tier="authorized_beta", currency=currency, lifecycle=lifecycle,
            display_names=display_names, source_refs=source_refs,
            include_conversation=True,
        )
        if scope["scope_kind"] == "episode":
            return focus_episode_context(context, scope["episode_id"])
        instruments = {str(item.instrument.instrument_id): item.instrument
                       for item in bundle.accepted_canonical_executions}
        attach_owned_analysis_sources(context, executions=frame, market_prices=market,
            init_cash=float(account_row["initial_cash"]), instruments=instruments, source_refs=source_refs)
        return context

    def _load_archive(self, scope):
        key = tuple(sorted(scope.items()))
        if self.archive and key not in self._loaded_scopes:
            self.completed.update(self.archive.read(scope))
            self._loaded_scopes.add(key)

    def context(self, params):
        context, fingerprint = self._source_with_fingerprint(params)
        self._load_archive(context.scope)
        from src.agents.account_conversation_sources import KNOWLEDGE, knowledge_record
        from src.agents.public_research import quotes_status
        inferences = []
        for item in reversed(tuple(self.completed.values())):
            if item["scope"] != context.scope:
                continue
            result = copy.deepcopy(item["result"])
            if item["source_fingerprint"] != fingerprint:
                result.update(invalidated=True, invalidation_reason="account_facts_changed")
            inferences.append(result)
        return {
            "version": ACCOUNT_CONTEXT_VERSION,
            "scope": context.scope,
            "as_of": context.as_of,
            "as_of_semantics": "daily_eod_last_actual_replay_observation_no_fill",
            "source_fingerprint": fingerprint,
            "data_tier": context.data_tier,
            "finding_options": [item.public() for item in context.finding_options],
            "conversation_version": "account_conversation_answer_v2",
            "episode_display_ids": dict(context.episode_display_ids),
            "record_refs": sorted({*context.records, *context.conversation_records,
                *(knowledge_record(context, topic).ref for topic in KNOWLEDGE)}),
            "episode_ids": [item["episode_id"] for record in context.records.values()
                if record.kind == "episode_index" for item in record.value["episodes"]],
            "capabilities": [
                {"kind": record.kind, "status": record.availability}
                for record in context.records.values()
            ],
            "inferences": inferences[:16],
            "conversation_turns": [{"id": key, "question": item["question"],
                "status": "complete", "result": {**copy.deepcopy(item["result"]),
                    "invalidated": item["source_fingerprint"] != fingerprint}}
                for key, item in self.completed.items() if item["scope"] == context.scope][-50:],
            "session_only": self.archive is None,
            "research": {"quotes": quotes_status(), "search": "configured_in_desktop_settings"},
        }

    def _history(self, previous_inference_id, *, scope, source_fingerprint):
        self._load_archive(scope)
        if previous_inference_id is None:
            return []
        if (not isinstance(previous_inference_id, str)
                or not previous_inference_id.startswith("account_inference_")
                or len(previous_inference_id) > 128):
            raise ValueError("account_previous_inference_invalid")
        previous = self.completed.get(previous_inference_id)
        if previous is None:
            raise ValueError("account_previous_inference_unavailable")
        if previous["scope"] != scope:
            raise ValueError("account_previous_inference_unavailable")
        if previous["result"].get("invalidated") is True or previous["result"].get("replaced_by") is not None:
            raise ValueError("account_previous_inference_not_latest")
        if previous["source_fingerprint"] != source_fingerprint:
            raise ValueError("account_conversation_stale")
        history = [*previous["history"], {
            "user_question": previous["question"],
            "validated_structured_answer": copy.deepcopy(previous["result"]["answer"]),
        }]
        return history[-3:]

    def start(self, params):
        scope = _scope(params)
        answer_version = params.get("answer_version", "account_review_answer_v1")
        engine = params.get("conversation_engine", "legacy")
        if engine not in {"legacy", "dsa"}:
            raise ValueError("unsupported_conversation_engine")
        if engine == "dsa" and answer_version != "account_conversation_answer_v2":
            raise ValueError("dsa_conversation_requires_v2_answer")
        if scope["scope_kind"] == "episode" and (engine != "dsa" or answer_version != "account_conversation_answer_v2"):
            raise ValueError("episode_conversation_requires_dsa_v2")
        if answer_version not in {"account_review_answer_v1", "account_conversation_answer_v2"}:
            raise ValueError("unsupported_account_answer_version")
        if params.get("allow_model_review") is not True:
            raise ValueError("explicit_model_data_consent_required")
        question = _text(params, "question")
        if len(question) > 2000:
            raise ValueError("question_too_long")
        # Resolve every account boundary and build deterministic facts before a
        # credential is inspected or a model client can be created.
        context, source_fingerprint = self._source_with_fingerprint(params)
        from src.agents.public_research import attach_public_research
        attach_public_research(context, params)
        history = self._history(params.get("previous_inference_id"),
                                scope=scope, source_fingerprint=source_fingerprint)
        with self._lock:
            if self._closed:
                raise ValueError("account_review_service_closed")
            if self._starting or any(not job["future"].done() for job in self.jobs.values()):
                raise ValueError("account_review_already_running")
            self._starting = True
        from .model_service import desktop_runtime
        try:
            model_runtime = desktop_runtime(params.get("_desktop_model_key"))
            cancelled = Event()
            context.access_allowed = lambda: not cancelled.is_set()
            conversation = None if not history else {
                "trust": "untrusted_not_evidence",
                "purpose": "resolve_references_in_current_question_only",
                "history": copy.deepcopy(history),
            }

            async def bounded():
                if answer_version == "account_conversation_answer_v2":
                    from src.agents.account_conversation import run_account_conversation
                    if engine == "dsa":
                        from src.agents.dsa_conversation import run_dsa_conversation as run_account_conversation
                    operation = run_account_conversation(question, context, runtime=model_runtime,
                        conversation_context=conversation, progress=lambda phase: progress.update(phase=phase))
                else:
                    operation = run_account_review(question, context, runtime=model_runtime,
                        conversation_context=conversation)
                task = asyncio.create_task(operation)
                try:
                    async with asyncio.timeout(150):
                        while not task.done():
                            if cancelled.is_set():
                                raise ValueError("account_review_cancelled")
                            await asyncio.wait({task}, timeout=0.1)
                        return await task
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    client_factory = getattr(getattr(model_runtime, "model", None), "_get_client", None)
                    if client_factory:
                        await client_factory().close()

            job_id = "account_review_job_" + uuid4().hex
            progress = {"phase": "researching"}
            source_params = dict(scope)
            job = {
                "future": self.executor.submit(lambda: asyncio.run(bounded())),
                "scope": scope, "question": question, "history": history,
                "previous_inference_id": params.get("previous_inference_id"),
                "source_fingerprint": source_fingerprint, "source_params": source_params,
                "cancelled": cancelled, "result": None,
                "progress": progress, "started_at": monotonic(),
            }
            with self._lock:
                self.jobs[job_id] = job
                for key in list(self.jobs)[:-16]:
                    if self.jobs[key]["future"].done():
                        del self.jobs[key]
        finally:
            with self._lock:
                self._starting = False
        return {"job_id": job_id, "status": "running"}

    def poll(self, params):
        requested_scope = _scope(params)
        job = self.jobs.get(_text(params, "job_id"))
        if job is None or job["scope"] != requested_scope:
            raise ValueError("account_review_job_not_owned")
        if params.get("cancel") is True:
            job["cancelled"].set()
            job["terminal"] = {"status": "stale", "reason": "account_review_cancelled", "result": None}
        with self._lock:
            if job.get("terminal") is not None:
                return copy.deepcopy(job["terminal"])
            if self._source_fingerprint(job["source_params"]) != job["source_fingerprint"]:
                job["cancelled"].set()
                job["terminal"] = {
                    "status": "stale", "reason": "account_facts_changed", "result": None,
                }
                return copy.deepcopy(job["terminal"])
        if not job["future"].done():
            return {"status": "running", "result": None, "phase": job.get("progress", {}).get("phase", "researching")}
        try:
            raw = job["future"].result()
        except Exception as exc:
            with self._lock:
                if job.get("terminal") is not None:
                    return copy.deepcopy(job["terminal"])
                if job["cancelled"].is_set():
                    job["terminal"] = {
                        "status": "stale", "reason": "account_review_cancelled", "result": None,
                    }
                    return copy.deepcopy(job["terminal"])
            if "failure" not in job:
                from src.agents.review_diagnostics import STAGES, persist_failure, safe_failure
                diagnostic = safe_failure(exc)
                diagnostic["diagnostic_id"] = uuid4().hex[:12]
                if diagnostic["stage"] == "unclassified":
                    phase = job.get("progress", {}).get("phase")
                    if phase in STAGES:
                        diagnostic["stage"] = phase
                if diagnostic["elapsed_ms"] is None and "started_at" in job:
                    diagnostic["elapsed_ms"] = min(600_000, max(0, int((monotonic() - job["started_at"]) * 1000)))
                job["failure"] = {
                    "status": "failed", "reason": "account_review_analysis_failed",
                    "result": None, "diagnostic": diagnostic,
                }
                path = getattr(getattr(self.product, "repo", None), "path", None)
                if path is not None:
                    persist_failure(path.parent / "review-diagnostics.jsonl", diagnostic)
            return copy.deepcopy(job["failure"])
        with self._lock:
            if job.get("terminal") is not None:
                return copy.deepcopy(job["terminal"])
            if self._source_fingerprint(job["source_params"]) != job["source_fingerprint"]:
                job["cancelled"].set()
                job["terminal"] = {
                    "status": "stale", "reason": "account_facts_changed", "result": None,
                }
                return copy.deepcopy(job["terminal"])
            if job["cancelled"].is_set():
                job["terminal"] = {
                    "status": "stale", "reason": "account_review_cancelled", "result": None,
                }
                return copy.deepcopy(job["terminal"])
            if job["result"] is None:
                inference_id = "account_inference_" + uuid4().hex
                result = {
                    **raw,
                    "inference_id": inference_id,
                    "invalidated": False,
                    "replaced_by": None,
                    "session_only": self.archive is None,
                    "source_fingerprint": job["source_fingerprint"],
                }
                # One exact account scope has one continuation head. Historical
                # answers remain visible, but an old branch cannot be resumed.
                updated = copy.deepcopy(self.completed)
                for previous in updated.values():
                    if (previous["scope"] == job["scope"]
                            and previous["result"].get("replaced_by") is None):
                        previous["result"].update(invalidated=True, replaced_by=inference_id)
                updated[inference_id] = {
                    "scope": copy.deepcopy(job["scope"]),
                    "source_fingerprint": job["source_fingerprint"],
                    "question": job["question"],
                    "history": copy.deepcopy(job["history"]),
                    # Shared internally with the job so later polling reflects
                    # head replacement; every public return is still copied.
                    "result": result,
                }
                owned_keys = [key for key, item in updated.items() if item["scope"] == job["scope"]]
                for key in owned_keys[:-50]:
                    del updated[key]
                if self.archive:
                    self.archive.save(job["scope"], {key: updated[key] for key in owned_keys[-50:]})
                self.completed = updated
                job["result"] = result
            response = copy.deepcopy(self.completed.get(job["result"]["inference_id"], {}).get("result", job["result"]))
        return {"status": "complete", "result": response}
