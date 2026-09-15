"""Narrow product RPC backed by canonical SQLite facts."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import hashlib
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from src.core.canonical_execution import instrument_ref, replay_eligibility
from src.ingestion.broker_csv import convert_to_generic_csv, detect_broker_format
from src.ingestion.contracts import CanonicalImportBundle, ImportPreviewSummary, MarketDataRequirement, sorted_instruments, stable_id
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv
from src.market_data.generic_csv import GenericHistoricalPriceCsvAdapter, GenericPriceCsvConfig
from src.market_data.models import resolve_market_data_requirements
from src.persistence import LocalRepository
from src.core.canonical_execution import canonical_executions_to_frame
from src.market_data.models import facts_to_market_data_frame


def build_episode_when_market_ready(*args, **kwargs):
    # Defer the heavy replay import until an analytics request actually needs it.
    from src.market_data.episode_gate import build_episode_when_market_ready as build
    return build(*args, **kwargs)


def _required_text(params: Mapping[str, object], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _file(params: Mapping[str, object]) -> tuple[Path, bytes]:
    path = Path(_required_text(params, "file_path"))
    if not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError("file_path must identify a readable CSV file")
    return path, path.read_bytes()


def _confirmed_file(params: Mapping[str, object]) -> tuple[Path, bytes]:
    """Validate and return the exact immutable bytes that commit will parse."""
    path, content = _file(params)
    if hashlib.sha256(content).hexdigest() != _required_text(params, "expected_file_sha256"):
        raise ValueError("file changed after preview")
    return path, content


def _now(params: Mapping[str, object]) -> str:
    value = params.get("imported_at")
    return str(value) if isinstance(value, str) and value else datetime.now(timezone.utc).isoformat()


def _preview_fingerprint(params: Mapping[str, object], content: bytes, kind: str) -> str:
    # Bind every supplied interpretation option, excluding only transport,
    # confirmation and post-preview row choices. No paths/raw bytes are stored.
    excluded = {"file_path", "expected_file_sha256", "expected_preview_fingerprint", "duplicate_choices", "imported_at"}
    payload = {"kind": kind, "file_sha256": hashlib.sha256(content).hexdigest(),
               "configuration": {key: value for key, value in params.items() if key not in excluded}}
    return stable_id("preview", payload)


def _confirm_preview(params: Mapping[str, object], content: bytes, kind: str) -> None:
    if _required_text(params, "expected_preview_fingerprint") != _preview_fingerprint(params, content, kind):
        raise ValueError("preview configuration changed; preview again before confirmation")


def _summary_zero(total: int) -> ImportPreviewSummary:
    return ImportPreviewSummary(total, total, total, 0, 0, 0, 0, 0, 0, total, 0, 0, 0)


def _currency_context(bundle, facts):
    """Listing/fee/source metadata only; no FX conversion or inferred currency."""
    currencies = {value.upper() for item in bundle.accepted_canonical_executions
                  for value in (item.instrument.currency, item.fee.currency) if value}
    currencies.update(item.currency.upper() for item in facts if item.currency)
    mixed = len(currencies) > 1
    unknown = any(not item.instrument.currency for item in bundle.accepted_canonical_executions)
    return (None if mixed or unknown or not currencies else next(iter(currencies))), mixed


def _trade_config(params: Mapping[str, object], subject: str, account: str) -> GenericCsvImportConfig:
    confirmed = None
    symbol = params.get("resolution_symbol")
    market = params.get("resolution_market")
    security_type = params.get("resolution_security_type")
    if all(isinstance(value, str) and value.strip() for value in (symbol, market, security_type)):
        confirmed = {str(symbol).strip().upper(): (instrument_ref(local_symbol=str(symbol), market=str(market), security_type=str(security_type)),)}
    return GenericCsvImportConfig(subject, account,
        params.get("source_timezone") if isinstance(params.get("source_timezone"), str) else None,
        use_source_row_order_as_sequence=bool(params.get("use_source_row_order_as_sequence", False)),
        confirmed_instruments=confirmed)


def _bundled_universe_dir():
    """Synthetic strategy-universe fixtures, packaged or in-repo."""
    return Path(__file__).resolve().parents[1] / "data" / "sample" / "strategy_universe"


def bundle_from_repository(repo: LocalRepository, subject_id: str, account_id: str) -> CanonicalImportBundle:
    items = repo.executions(subject_id, account_id)
    requirements = tuple(
        MarketDataRequirement(
            instrument_id=instrument.instrument_id, local_symbol=instrument.local_symbol,
            market=instrument.market, security_type=instrument.security_type,
            start_date=min(x.event_time.calendar_date for x in items if x.instrument.instrument_id == instrument.instrument_id).isoformat(),
            end_date=max(x.event_time.calendar_date for x in items if x.instrument.instrument_id == instrument.instrument_id).isoformat(),
        ) for instrument in sorted_instruments(items)
    )
    return CanonicalImportBundle(
        bundle_id=stable_id("persisted_bundle", [x.execution_id for x in items]), schema_version="1",
        subject_id=subject_id, account_id=account_id, source_metadata_refs=repo.file_hashes(subject_id, account_id, "trade"),
        accepted_canonical_executions=items, instrument_refs=sorted_instruments(items),
        data_quality_summary=_summary_zero(len(items)), duplicate_summary=(), replay_eligibility_summary=(),
        market_data_requirements=requirements, limitations=("rebuilt_from_local_canonical_facts",),
    )


class ProductRuntime:
    def __init__(self, db_path: str | Path) -> None:
        self.repo = LocalRepository(db_path)
        self._review_runtime = None

    def review_pack(self, params: Mapping[str, object]) -> dict[str, object]:
        subject = _required_text(params, "subject_id")
        account = _required_text(params, "account_id")
        # Deferred import: the analytics replay stack is heavy and only this
        # product method needs it.
        from src.review_pack import build_review_pack
        return build_review_pack(self.repo, subject, account)

    def review_runtime(self):
        if self._review_runtime is None:
            from .review import ReviewRuntime
            self._review_runtime = ReviewRuntime(self)
        return self._review_runtime

    def close(self) -> None:
        if self._review_runtime is not None:
            self._review_runtime.close()
        self.repo.close()

    def _trade_preview(self, params, content, subject, account):
        original = content
        broker = detect_broker_format(content)
        if broker is not None:
            # Known broker export (eastmoney/ths): convert deterministically to
            # generic_csv_v1 bytes first, so preview and commit parse identical
            # facts. Unrecognized files keep the original generic_csv path.
            content = convert_to_generic_csv(content, broker).encode("utf-8")
        config = _trade_config(params, subject, account)
        raw = self.repo.executions(subject, account, resolve_instruments=False)
        raw_by_id = {item.execution_id: item for item in raw}
        current = {item.execution_id: item for item in self.repo.executions(subject, account)}
        if params.get("column_mapping") is not None and not isinstance(params["column_mapping"], Mapping):
            raise ValueError("column_mapping must be an object")
        options = dict(explicit_mapping=params.get("column_mapping"), existing_executions=raw,
                       existing_file_hashes=self.repo.file_hashes(subject, account, "trade"))
        parsed = preview_generic_csv(content, config=config, **options)
        source = preview_generic_csv(content, config=replace(config, confirmed_instruments=None), **options) if config.confirmed_instruments else parsed
        payload = parsed.as_dict()
        if broker is not None:
            # The tamper guard (_confirmed_file) and the hash shown in preview
            # both refer to the user's original file bytes; the conversion is
            # an internal parsing step the user never sees.
            payload["batch"]["file_sha256"] = hashlib.sha256(original).hexdigest()
        reconciled = {}
        for row, original, view in zip(parsed.rows, source.rows, payload["rows"]):
            if row.candidate is None or original.candidate is None:
                continue
            old = raw_by_id.get(original.candidate.execution_id)
            if old is None or old.instrument.instrument_id is not None or row.candidate.instrument.instrument_id is None:
                continue
            excluded = {"instrument_id", "execution_id", "source_record_ref"}
            same_facts = lambda item: {key: value for key, value in item.result_payload().items() if key not in excluded}
            if same_facts(old) != same_facts(row.candidate):
                raise ValueError("instrument resolution cannot change execution facts")
            qualified = replace(old, instrument=replace(row.candidate.instrument,
                currency=row.candidate.instrument.currency or old.instrument.currency))
            previous = current[old.execution_id]
            if previous.instrument.instrument_id is not None and previous.instrument != qualified.instrument:
                raise ValueError("conflicting instrument resolution requires explicit reconciliation")
            needed = previous.instrument.instrument_id is None
            reconciled[row.row_ref] = qualified if needed else None
            view["status"] = "instrument_resolution" if needed else "exact_duplicate"
            view["candidate"] = {**view["candidate"], "execution_id": old.execution_id,
                                 "source_record_ref": old.provenance.source_record_ref}
            view["existing_execution_id"] = old.execution_id
            if row.status == "new_execution":
                payload["summary"]["new_executions"] -= 1
                payload["summary"]["accepted_canonical_facts"] -= 1
            key = "instrument_resolutions" if needed else "exact_duplicates"
            payload["summary"][key] = payload["summary"].get(key, 0) + 1
        return parsed, reconciled, payload

    def preview_trade(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _file(params)
        subject = _required_text(params, "subject_id")
        account = _required_text(params, "account_id")
        _, _, preview = self._trade_preview(params, content, subject, account)
        return {**preview, "filename": path.name, "preview_fingerprint": _preview_fingerprint(params, content, "trade")}

    def commit_trade(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _confirmed_file(params)
        _confirm_preview(params, content, "trade")
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        parsed, reconciled, preview_payload = self._trade_preview(params, content, subject, account)
        choices = params.get("duplicate_choices", {})
        if not isinstance(choices, Mapping):
            raise ValueError("duplicate_choices must be an object")
        accepted = []
        decisions = []
        for row in parsed.rows:
            if row.row_ref in reconciled:
                continue
            if row.status == "new_execution" and row.candidate is not None:
                accepted.append(row.candidate)
            elif row.status == "possible_duplicate":
                choice = choices.get(row.row_ref)
                if choice not in {"keep", "skip"}:
                    raise ValueError("every possible duplicate requires keep or skip")
                decisions.append((row.row_ref, str(choice), row.existing_execution_id))
                if choice == "keep" and row.candidate is not None:
                    accepted.append(row.candidate)
        imported_at = _now(params)
        initial_cash = float(params.get("initial_cash", 100000))
        if not math.isfinite(initial_cash) or initial_cash <= 0:
            raise ValueError("initial_cash must be finite and positive")
        existing_account = next(
            (item for item in self.repo.list_accounts()
             if item["subject_id"] == subject and item["account_id"] == account),
            None,
        )
        if existing_account is not None and float(existing_account["initial_cash"]) != initial_cash:
            raise ValueError("initial_cash cannot change after an account is created")
        resolutions = []
        config = _trade_config(params, subject, account)
        for source_symbol, candidates in (config.confirmed_instruments or {}).items():
            for instrument in candidates:
                resolutions.append((source_symbol, instrument.instrument_id, {
                    "source_symbol": source_symbol,
                    "instrument": {
                        "local_symbol": instrument.local_symbol,
                        "market": instrument.market,
                        "security_type": instrument.security_type,
                        "currency": instrument.currency,
                    },
                    "resolution_source": "user_confirmed_import",
                }))
        resolution_rows = [(item.execution_id, row_ref, {
            "instrument": {"local_symbol": item.instrument.local_symbol, "market": item.instrument.market,
                "security_type": item.instrument.security_type, "currency": item.instrument.currency},
            "reason": "confirmed_instrument_resolution", "preview_fingerprint": params["expected_preview_fingerprint"],
        }) for row_ref, item in reconciled.items() if item is not None]
        inserted = self.repo.commit_trade_import(
            subject_id=subject, account_id=account,
            display_name=str(params.get("display_name") or account), initial_cash=initial_cash,
            batch_id=parsed.batch.batch_id, file_sha256=parsed.batch.file_sha256, filename=path.name,
            imported_at=imported_at, summary=preview_payload["summary"], executions=accepted,
            decisions=decisions, resolutions=resolutions, execution_resolutions=resolution_rows)
        return {"batch_id": parsed.batch.batch_id, "inserted_executions": inserted,
                "resolved_executions": len(resolution_rows), "data_status": self.data_status(params)}

    def preview_market(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _file(params)
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        bundle = bundle_from_repository(self.repo, subject, account)
        preview = GenericHistoricalPriceCsvAdapter().preview(content, GenericPriceCsvConfig(
            source_id=_required_text(params, "source_id"), source_version=_required_text(params, "source_version"),
            imported_at=_now(params), known_instruments=bundle.instrument_refs),
            existing=self.repo.prices(subject, account), requirement_bundle=bundle)
        return {"batch_id": preview.batch_id, "file_sha256": preview.file_sha256, "filename": path.name,
            "preview_fingerprint": _preview_fingerprint(params, content, "market"),
            "summary": {"total_observations": preview.total_observations, "new_observations": preview.new_observations,
                "existing_observations": preview.existing_observations, "duplicate_rows": preview.duplicate_rows,
                "conflicts": preview.conflicts, "invalid_rows": preview.invalid_rows},
            "instruments": list(preview.instruments), "date_range": list(preview.date_range) if preview.date_range else None,
            "missing_required_dates": [[key, list(values)] for key, values in preview.missing_required_dates],
            "rows": [{"row_number": row.row_number, "status": row.status,
                      "candidate": ({"date": row.candidate.date.isoformat(),
                                     "symbol": row.candidate.instrument.display_symbol or row.candidate.instrument.local_symbol,
                                     "close": row.candidate.close, "price_type": row.candidate.price_type}
                                    if row.candidate else None),
                      "issues": [{"code": issue.code, "field": issue.field} for issue in row.issues]} for row in preview.rows]}

    def commit_market(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _confirmed_file(params)
        _confirm_preview(params, content, "market")
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        bundle = bundle_from_repository(self.repo, subject, account)
        preview = GenericHistoricalPriceCsvAdapter().preview(content, GenericPriceCsvConfig(
            source_id=_required_text(params, "source_id"), source_version=_required_text(params, "source_version"),
            imported_at=_now(params), known_instruments=bundle.instrument_refs), existing=self.repo.prices(subject, account), requirement_bundle=bundle)
        if preview.conflicts or preview.invalid_rows:
            raise ValueError("market import contains conflicts or invalid rows")
        facts = [row.candidate for row in preview.rows if row.status == "new_observation" and row.candidate]
        inserted = self.repo.commit_market_import(subject_id=subject, account_id=account, batch_id=preview.batch_id,
            file_sha256=preview.file_sha256, filename=path.name, imported_at=_now(params),
            summary={"new_observations": preview.new_observations, "duplicate_rows": preview.duplicate_rows}, facts=facts)
        return {"batch_id": preview.batch_id, "inserted_observations": inserted, "data_status": self.data_status(params)}

    def accounts(self, params: Mapping[str, object]) -> dict[str, object]:
        if params:
            raise ValueError("params must be empty")
        return {"accounts": self.repo.list_accounts(), "data_mode": "real_user"}

    def data_status(self, params: Mapping[str, object]) -> dict[str, object]:
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        items, facts = self.repo.executions(subject, account), self.repo.prices(subject, account)
        if items:
            bundle = bundle_from_repository(self.repo, subject, account)
            coverage = resolve_market_data_requirements(bundle, facts)
            eligibility = replay_eligibility(items)
            market = {"status": coverage.status, "required": coverage.required_observation_count,
                      "available": coverage.available_observation_count,
                      "missing": [[key, list(values)] for key, values in coverage.missing]}
            review_status = "available" if eligibility.eligible and coverage.status == "complete" else (
                "waiting_for_market_data" if coverage.status != "complete" else "replay_ineligible")
        else:
            market, review_status = {"status": "missing", "required": 0, "available": 0, "missing": []}, "no_trades"
        unknown_fees = sum(x.fee.status == "unknown" for x in items)
        history = self.repo.import_history(subject, account)
        return {"subject_id": subject, "account_id": account, "execution_count": len(items),
            "instrument_status": "complete" if items and all(x.instrument.instrument_id for x in items) else "incomplete",
            "fee_status": "complete" if not unknown_fees else "partial", "unknown_fee_count": unknown_fees,
            "market_data": market, "review_status": review_status,
            "last_trade_import": next((x["imported_at"] for x in history if x["kind"] == "trade"), None),
            "last_market_import": next((x["imported_at"] for x in history if x["kind"] == "market"), None),
            "latest_market_date": max((x.date.isoformat() for x in facts), default=None),
            "import_history": history}

    def delete_account(self, params: Mapping[str, object]) -> dict[str, object]:
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        deleted = self.repo.delete_account(subject, account)
        if deleted:
            self.review_runtime().drop_account(subject, account)
        return {"deleted": deleted}

    def _lifecycle(self, params: Mapping[str, object]):
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        accounts = [x for x in self.repo.list_accounts() if x["subject_id"] == subject and x["account_id"] == account]
        if not accounts:
            raise ValueError("account not found")
        bundle, facts = bundle_from_repository(self.repo, subject, account), self.repo.prices(subject, account)
        if _currency_context(bundle, facts)[1]:
            return accounts[0], bundle, facts, None, "unavailable_mixed_currency_without_fx"
        if not facts:
            return accounts[0], bundle, facts, None, "unavailable_pending_market_data"
        valuation_date = pd.Timestamp(max(x.date for x in facts))
        execution_cutoff = valuation_date
        # A daily observation date is not a midnight execution cutoff. Include
        # the exact canonical instants belonging to supported calendar dates;
        # keep their UTC mapping/sequence and the daily market observations
        # unchanged. This cutoff does not assert intraday price availability.
        if bundle.accepted_canonical_executions and replay_eligibility(bundle.accepted_canonical_executions).eligible:
            frame = canonical_executions_to_frame(bundle.accepted_canonical_executions)
            supported_times = frame.loc[frame["market_date"] <= valuation_date, "event_time"]
            if not supported_times.empty:
                execution_cutoff = max(execution_cutoff, supported_times.max())
        gated = build_episode_when_market_ready(bundle, facts, as_of=execution_cutoff,
            init_cash=float(accounts[0]["initial_cash"]), calculation_code_version="runtime_v1")
        return accounts[0], bundle, facts, gated.lifecycle, gated.status

    def investments(self, params: Mapping[str, object]) -> dict[str, object]:
        from src.presentation.allocation import allocation_block
        from src.presentation.investment_archive import outcome_summaries
        account, bundle, facts, lifecycle, status = self._lifecycle(params)
        currency, _ = _currency_context(bundle, facts)
        if lifecycle is None:
            return {"subject_id": account["subject_id"], "account_id": account["account_id"],
                    "as_of": max((x.date.isoformat() for x in facts), default=account["updated_at"]),
                    "data_tier": "authorized_beta", "portfolio_state_status": "unavailable",
                    "portfolio_state_reason": status, "summary": {"open_episode_count": 0, "closed_episode_count": 0, "current_position_count": 0},
                    "allocation": allocation_block([]),
                    "episodes": []}
        state_by_id = {x.state_id: x for x in lifecycle.states}
        snapshot_by_episode = {x.episode_id: state_by_id[x.position_state_ref] for x in lifecycle.snapshots}
        closing_state_by_episode = {
            decision.episode_id: state_by_id[decision.state_after_ref]
            for decision in lifecycle.decisions if decision.decision_type == "close_position"
        }
        display_by_instrument = {str(x.instrument.instrument_id): x.instrument.display_name or x.instrument.display_symbol or x.instrument.local_symbol for x in bundle_from_repository(self.repo, str(account["subject_id"]), str(account["account_id"])).accepted_canonical_executions}
        summaries = outcome_summaries(lifecycle,
            canonical_executions_to_frame(bundle.accepted_canonical_executions),
            facts_to_market_data_frame(facts), subject_id=str(account["subject_id"]),
            account_id=str(account["account_id"]), init_cash=float(account["initial_cash"]))
        entries = []
        for item in lifecycle.episodes:
            state = snapshot_by_episode.get(item.episode_id) or closing_state_by_episode.get(item.episode_id)
            entries.append({"episode_id": item.episode_id, "instrument_id": item.instrument_id, "currency": currency,
                "outcome_summary": summaries[item.episode_id],
                "display_name": display_by_instrument.get(item.instrument_id, item.instrument_id), "status": item.status,
                "opened_at": item.opened_at.isoformat(), "closed_at": item.closed_at.isoformat() if item.closed_at else None,
                "duration_days": item.duration_days, "duration_kind": item.duration_kind,
                "quantity": state.quantity if state else None, "average_cost": state.average_cost if state else None,
                "valuation_at": state.valuation_at.isoformat() if state and state.valuation_at else None,
                "valuation_price": state.valuation_price if state else None, "market_value": state.market_value if state else None})
        return {"subject_id": account["subject_id"], "account_id": account["account_id"], "as_of": lifecycle.as_of.isoformat(),
                "data_tier": "authorized_beta", "portfolio_state_status": "available", "portfolio_state_reason": None,
                "summary": {"open_episode_count": sum(x.status == "open" for x in lifecycle.episodes),
                            "closed_episode_count": sum(x.status == "closed" for x in lifecycle.episodes),
                            "current_position_count": len(lifecycle.snapshots)},
                "allocation": allocation_block(entries), "episodes": entries}

    _LIFECYCLE_UNAVAILABLE_REASONS = {
        "unavailable_pending_market_data": "exact required daily market observations are incomplete",
        "unavailable_replay_ineligible": "recorded executions are not replay-eligible",
        "unavailable_mixed_currency_without_fx": "mixed-currency accounting without FX conversion is unsupported",
    }

    def episode(self, params: Mapping[str, object]) -> dict[str, object]:
        from src.presentation.runtime_episode import episode_entry
        account, bundle, facts, lifecycle, status = self._lifecycle(params)
        if lifecycle is None:
            # Echo the gate's actual cause instead of a generic (and often
            # wrong) market-data message.
            reason = self._LIFECYCLE_UNAVAILABLE_REASONS.get(status, "market prices are incomplete")
            return {"status": status, "reason": reason, "entry": None}
        episode_id = _required_text(params, "episode_id")
        if not any(item.episode_id == episode_id for item in lifecycle.episodes):
            return {"status": "unavailable", "reason": "episode does not belong to this account", "entry": None}
        target_instrument = next(
            (e.instrument_id for e in lifecycle.episodes if e.episode_id == episode_id), None)
        display_name = next(
            (x.instrument.display_name or x.instrument.display_symbol or x.instrument.local_symbol
             for x in bundle.accepted_canonical_executions
             if target_instrument is not None and x.instrument.instrument_id == target_instrument),
            target_instrument)
        entry = episode_entry(lifecycle, canonical_executions_to_frame(bundle.accepted_canonical_executions),
            facts_to_market_data_frame(facts), episode_id=episode_id, init_cash=float(account["initial_cash"]),
            currency=_currency_context(bundle, facts)[0],
            display_name=display_name)
        return {"status": "available", "reason": None, "entry": entry}

    def strategy_simulation_run_custom(self, params: Mapping[str, object]) -> dict[str, object]:
        """Run a user-composed strategy spec on the bundled synthetic universe.

        Deterministic, isolated from user accounts, and self-checked: the run
        on full history must reproduce an identical prefix on truncated
        history (no future functions), or the strategy is refused.
        """
        from src.strategy.composite import (
            FORMULA_SCHEMA,
            UserStrategyError,
            build_formula_strategy_spec,
            build_user_strategy_spec,
            make_formula_provider,
            make_provider,
        )
        from src.strategy.compare import multi_simulation_data
        from src.strategy.data import load_simulation_data, truncate_simulation_data
        from src.strategy.report import desktop_payload, enrich_summary, result_to_dict
        from src.strategy.engine import run_simulation

        raw = params.get("strategy") if isinstance(params, Mapping) else None
        if not isinstance(raw, Mapping):
            return {"status": "unavailable", "reason": "invalid_strategy_spec", "artifact": None}
        try:
            if raw.get("schema_version") == FORMULA_SCHEMA:
                spec, normalized = build_formula_strategy_spec(raw)
                provider = make_formula_provider(normalized)
            else:
                spec, normalized = build_user_strategy_spec(raw)
                provider = make_provider(normalized)
        except UserStrategyError as exc:
            return {"status": "unavailable", "reason": f"invalid_strategy_spec: {exc}", "artifact": None}
        universe = params.get("universe", "synthetic")
        limitations_extra: list[str] = []
        if universe == "own_account":
            subject_id = params.get("subject_id")
            account_id = params.get("account_id")
            if not isinstance(subject_id, str) or not isinstance(account_id, str) or not subject_id or not account_id:
                return {"status": "unavailable", "reason": "own_account_requires_account", "artifact": None}
            bundle = bundle_from_repository(self.repo, subject_id, account_id)
            # Collect per-instrument raw symbol and date span.
            grouped2: dict[str, dict] = {}
            for execution in bundle.accepted_canonical_executions:
                instrument_id = execution.instrument.instrument_id
                raw_symbol = execution.instrument.local_symbol or execution.instrument.display_symbol
                day = execution.event_time.calendar_date
                entry = grouped2.setdefault(instrument_id, {"raw": raw_symbol, "min": day, "max": day})
                entry["min"] = min(entry["min"], day)
                entry["max"] = max(entry["max"], day)
            from src.data.akshare_client import AkshareUnavailable, fetch_ohlc
            from datetime import timedelta
            bars_by: dict[str, list] = {}
            skipped: list[str] = []
            for instrument_id, entry in sorted(grouped2.items()):
                fetch_start = (entry["min"] - timedelta(days=400)).isoformat()
                fetch_end = (entry["max"] + timedelta(days=7)).isoformat()
                try:
                    bars_by[instrument_id] = fetch_ohlc(entry["raw"], fetch_start, fetch_end, adjust="hfq")
                except Exception:
                    skipped.append(instrument_id)
            if not bars_by:
                return {"status": "unavailable", "reason": "no_real_instruments_could_be_loaded", "artifact": None}
            from src.strategy.compare import multi_simulation_data
            data = multi_simulation_data(bars_by, is_synthetic=False)
            limitations_extra = [
                "运行范围：你在本账户中真实交易过、且可识别为 A 股的标的（" + str(len(bars_by)) + " 只" +
                (f"；另有 {len(skipped)} 只非 A 股或不可识别标的已跳过" if skipped else "") + "）。",
                "行情使用 akshare 公开后复权日线（连续序列），成交价即复权价，与盘面价格不同。",
                "只包含你自己交易过的标的——结论存在幸存者偏差，不代表全市场。",
            ]
            data_full = data
        else:
            data_full = load_simulation_data(_bundled_universe_dir())
            limitations_extra = []
        data = data_full
        try:
            result = run_simulation(spec, data, signal_provider=provider)
            cutoff = data.dates[len(data.dates) // 2]
            prefix = run_simulation(spec, truncate_simulation_data(data, cutoff),
                                    signal_provider=provider)
        except (ValueError, KeyError) as exc:
            return {"status": "unavailable", "reason": f"strategy_run_failed: {exc}", "artifact": None}
        base = result_to_dict(result)
        prefix_dict = result_to_dict(prefix)
        # The truncated run's final day legitimately creates no new orders
        # (there is no next open), and the full run's first post-cutoff day is
        # out of scope: compare the strict common prefix of both.
        common = [day for day in base["days"] if day["date"] < cutoff.isoformat()]
        if common[:-1] != prefix_dict["days"][:-1]:
            return {"status": "unavailable", "reason": "future_function_self_check_failed", "artifact": None}
        enriched = enrich_summary(base, data)
        artifact = desktop_payload(enriched, data)
        if limitations_extra:
            artifact["limitations"] = limitations_extra
        return {"status": "available", "reason": None,
                "artifact": artifact}

    def strategy_sensitivity_run(self, params: Mapping[str, object]) -> dict[str, object]:
        """Parameter sensitivity: one strategy, one parameter, several values.

        Accepts {"strategy_id"} for a built-in strategy or {"strategy": spec}
        for a user-composed one, plus {"parameter", "values"}.  Runs each
        variant on the bundled synthetic universe.  Rows keep the caller's
        order; the report never ranks or marks a best value.
        """
        from src.strategy.composite import UserStrategyError, build_user_strategy_spec, make_provider
        from src.strategy.data import load_simulation_data
        from src.strategy.sensitivity import SensitivityError, sensitivity_report
        from src.strategy.strategies.dual_ma import build_dual_ma_spec
        from src.strategy.strategies.rsi_mr import build_rsi_mr_spec
        from src.strategy.strategies.turtle import build_turtle_spec
        from src.strategy.strategies.t1 import build_t1_spec

        if not isinstance(params, Mapping):
            return {"status": "unavailable", "reason": "invalid_params", "report": None}
        builders = {
            "toujing_t1_breakout_trend": build_t1_spec,
            "toujing_dual_ma": build_dual_ma_spec,
            "toujing_rsi_mean_reversion": build_rsi_mr_spec,
            "toujing_turtle_s2_long": build_turtle_spec,
        }
        provider = None
        raw_strategy = params.get("strategy")
        if isinstance(raw_strategy, Mapping):
            try:
                spec, normalized = build_user_strategy_spec(raw_strategy)
            except UserStrategyError as exc:
                return {"status": "unavailable", "reason": f"invalid_strategy_spec: {exc}", "report": None}
            provider = make_provider(normalized)
        else:
            strategy_id = params.get("strategy_id")
            builder = builders.get(strategy_id) if isinstance(strategy_id, str) else None
            if builder is None:
                return {"status": "unavailable", "reason": "unknown_strategy", "report": None}
            spec = builder()
        try:
            report = sensitivity_report(
                spec, load_simulation_data(_bundled_universe_dir()),
                parameter=params.get("parameter"), values=params.get("values"),
                signal_provider=provider)
        except SensitivityError as exc:
            return {"status": "unavailable", "reason": str(exc), "report": None}
        return {"status": "available", "reason": None, "report": report}

    def strategy_comparison(self, params: Mapping[str, object]) -> dict[str, object]:
        """Same-instrument T1 replay comparison for one real-account episode.

        OHLC bars come from the akshare public source (cache-first; declared
        limitation: the imported close-only market contract cannot drive a
        rule replay).  Failures are explainable statuses, never guesses, and
        the method is read-only for user accounts.
        """
        from src.data.akshare_client import AkshareUnavailable, fetch_ohlc
        from src.strategy.compare import ComparisonError, compare_episode
        from src.strategy.strategies.t1 import build_t1_spec

        account, bundle, facts, lifecycle, status = self._lifecycle(params)
        if lifecycle is None:
            return {"status": "unavailable", "reason": "market prices are incomplete", "report": None}
        episode_id = _required_text(params, "episode_id")
        episode = next((item for item in lifecycle.episodes if item.episode_id == episode_id), None)
        if episode is None:
            return {"status": "unavailable", "reason": "episode does not belong to this account", "report": None}
        instrument = str(episode.instrument_id)
        # The canonical instrument id is a qualified hash; the public market
        # source needs the raw local code recorded on the executions.
        raw_symbol = next((x.instrument.local_symbol or x.instrument.display_symbol or x.instrument.instrument_id
                           for x in bundle.accepted_canonical_executions
                           if x.instrument.instrument_id == instrument), instrument)
        frame = canonical_executions_to_frame(bundle.accepted_canonical_executions)
        scoped = frame.loc[frame["symbol"] == instrument] if "symbol" in frame.columns else frame.iloc[0:0]
        if scoped.empty:
            return {"status": "unavailable", "reason": "comparison_unavailable_no_executions", "report": None}
        execution_rows = [{
            "execution_id": str(item["execution_id"]),
            "day": pd.Timestamp(item["market_date"]).date().isoformat(),
            "side": str(item["side"]), "quantity": float(item["executed_quantity"]),
            "price": float(item["executed_price"]), "fee": float(item["fee"]),
        } for _, item in scoped.iterrows()]
        first_execution = min(row["day"] for row in execution_rows)
        last_execution = max(row["day"] for row in execution_rows)
        window_start = pd.Timestamp(episode.opened_at).date().isoformat()
        window_end = pd.Timestamp(episode.closed_at).date().isoformat() if episode.closed_at else None
        fetch_start = (pd.Timestamp(min(first_execution, window_start)) - pd.Timedelta(days=120)).date().isoformat()
        fetch_end = (pd.Timestamp(max(last_execution, window_end or last_execution)) + pd.Timedelta(days=7)).date().isoformat()
        try:
            bars = fetch_ohlc(raw_symbol, fetch_start, fetch_end)
        except AkshareUnavailable as exc:
            return {"status": "unavailable", "reason": str(exc), "report": None}
        try:
            report = compare_episode(build_t1_spec(), bars, instrument=instrument, is_synthetic=False,
                executions=execution_rows, episode_id=episode_id,
                window_start=pd.Timestamp(window_start).date(),
                window_end=pd.Timestamp(window_end).date() if window_end else None)
        except ComparisonError as exc:
            return {"status": "unavailable", "reason": f"comparison_invalid_market_data: {exc}", "report": None}
        report["limitations"] = [*report["limitations"],
            "行情来自 akshare 公开数据（不复权日线，本地缓存）；与导入的规范成交并列，仅用于教学对照。",
            "对照在真实账户上按只读方式运行，不会修改任何记录。"]
        return {"status": "available", "reason": None, "report": report}
