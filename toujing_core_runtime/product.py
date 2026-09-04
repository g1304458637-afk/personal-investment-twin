"""Narrow product RPC backed by canonical SQLite facts."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from src.core.canonical_execution import instrument_ref, replay_eligibility
from src.ingestion.contracts import CanonicalImportBundle, ImportPreviewSummary, MarketDataRequirement, sorted_instruments, stable_id
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv
from src.market_data.generic_csv import GenericHistoricalPriceCsvAdapter, GenericPriceCsvConfig
from src.market_data.models import resolve_market_data_requirements
from src.market_data.episode_gate import build_episode_when_market_ready
from src.persistence import LocalRepository
from src.presentation.runtime_episode import episode_entry
from src.core.canonical_execution import canonical_executions_to_frame
from src.market_data.models import facts_to_market_data_frame


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


def _now(params: Mapping[str, object]) -> str:
    value = params.get("imported_at")
    return str(value) if isinstance(value, str) and value else datetime.now(timezone.utc).isoformat()


def _summary_zero(total: int) -> ImportPreviewSummary:
    return ImportPreviewSummary(total, total, total, 0, 0, 0, 0, 0, 0, total, 0, 0, 0)


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

    def close(self) -> None:
        self.repo.close()

    def preview_trade(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _file(params)
        subject = _required_text(params, "subject_id")
        account = _required_text(params, "account_id")
        preview = preview_generic_csv(content, config=_trade_config(params, subject, account),
            existing_executions=self.repo.executions(subject, account),
            existing_file_hashes=self.repo.file_hashes(subject, account, "trade"))
        return {**preview.as_dict(), "filename": path.name}

    def commit_trade(self, params: Mapping[str, object]) -> dict[str, object]:
        preview = self.preview_trade(params)
        expected = _required_text(params, "expected_file_sha256")
        if preview["batch"]["file_sha256"] != expected:  # type: ignore[index]
            raise ValueError("file changed after preview")
        path, content = _file(params)
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        parsed = preview_generic_csv(content, config=_trade_config(params, subject, account),
            existing_executions=self.repo.executions(subject, account), existing_file_hashes=self.repo.file_hashes(subject, account, "trade"))
        choices = params.get("duplicate_choices", {})
        if not isinstance(choices, Mapping):
            raise ValueError("duplicate_choices must be an object")
        accepted = []
        decisions = []
        for row in parsed.rows:
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
        inserted = self.repo.commit_trade_import(
            subject_id=subject, account_id=account,
            display_name=str(params.get("display_name") or account), initial_cash=initial_cash,
            batch_id=parsed.batch.batch_id, file_sha256=parsed.batch.file_sha256, filename=path.name,
            imported_at=imported_at, summary=parsed.summary.as_dict(), executions=accepted,
            decisions=decisions, resolutions=resolutions)
        return {"batch_id": parsed.batch.batch_id, "inserted_executions": inserted, "data_status": self.data_status(params)}

    def preview_market(self, params: Mapping[str, object]) -> dict[str, object]:
        path, content = _file(params)
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        bundle = bundle_from_repository(self.repo, subject, account)
        preview = GenericHistoricalPriceCsvAdapter().preview(content, GenericPriceCsvConfig(
            source_id=_required_text(params, "source_id"), source_version=_required_text(params, "source_version"),
            imported_at=_now(params), known_instruments=bundle.instrument_refs),
            existing=self.repo.prices(subject, account), requirement_bundle=bundle)
        return {"batch_id": preview.batch_id, "file_sha256": preview.file_sha256, "filename": path.name,
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
        path, content = _file(params)
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        bundle = bundle_from_repository(self.repo, subject, account)
        preview = GenericHistoricalPriceCsvAdapter().preview(content, GenericPriceCsvConfig(
            source_id=_required_text(params, "source_id"), source_version=_required_text(params, "source_version"),
            imported_at=_now(params), known_instruments=bundle.instrument_refs), existing=self.repo.prices(subject, account), requirement_bundle=bundle)
        if preview.file_sha256 != _required_text(params, "expected_file_sha256"):
            raise ValueError("file changed after preview")
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
        return {"deleted": self.repo.delete_account(_required_text(params, "subject_id"), _required_text(params, "account_id"))}

    def _lifecycle(self, params: Mapping[str, object]):
        subject, account = _required_text(params, "subject_id"), _required_text(params, "account_id")
        accounts = [x for x in self.repo.list_accounts() if x["subject_id"] == subject and x["account_id"] == account]
        if not accounts:
            raise ValueError("account not found")
        bundle, facts = bundle_from_repository(self.repo, subject, account), self.repo.prices(subject, account)
        if not facts:
            return accounts[0], bundle, facts, None, "unavailable_pending_market_data"
        as_of = pd.Timestamp(max(x.date for x in facts))
        gated = build_episode_when_market_ready(bundle, facts, as_of=as_of,
            init_cash=float(accounts[0]["initial_cash"]), calculation_code_version="runtime_v1")
        return accounts[0], bundle, facts, gated.lifecycle, gated.status

    def investments(self, params: Mapping[str, object]) -> dict[str, object]:
        account, _, facts, lifecycle, status = self._lifecycle(params)
        if lifecycle is None:
            return {"subject_id": account["subject_id"], "account_id": account["account_id"],
                    "as_of": max((x.date.isoformat() for x in facts), default=account["updated_at"]),
                    "data_tier": "authorized_beta", "portfolio_state_status": "unavailable",
                    "portfolio_state_reason": status, "summary": {"open_episode_count": 0, "closed_episode_count": 0, "current_position_count": 0},
                    "episodes": []}
        state_by_id = {x.state_id: x for x in lifecycle.states}
        snapshot_by_episode = {x.episode_id: state_by_id[x.position_state_ref] for x in lifecycle.snapshots}
        closing_state_by_episode = {
            decision.episode_id: state_by_id[decision.state_after_ref]
            for decision in lifecycle.decisions if decision.decision_type == "close_position"
        }
        display_by_instrument = {str(x.instrument.instrument_id): x.instrument.display_name or x.instrument.display_symbol or x.instrument.local_symbol for x in bundle_from_repository(self.repo, str(account["subject_id"]), str(account["account_id"])).accepted_canonical_executions}
        entries = []
        for item in lifecycle.episodes:
            state = snapshot_by_episode.get(item.episode_id) or closing_state_by_episode.get(item.episode_id)
            entries.append({"episode_id": item.episode_id, "instrument_id": item.instrument_id,
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
                            "current_position_count": len(lifecycle.snapshots)}, "episodes": entries}

    def episode(self, params: Mapping[str, object]) -> dict[str, object]:
        account, bundle, facts, lifecycle, status = self._lifecycle(params)
        if lifecycle is None:
            return {"status": status, "reason": "market prices are incomplete", "entry": None}
        episode_id = _required_text(params, "episode_id")
        entry = episode_entry(lifecycle, canonical_executions_to_frame(bundle.accepted_canonical_executions),
            facts_to_market_data_frame(facts), episode_id=episode_id, init_cash=float(account["initial_cash"]),
            display_name=next(x.instrument.display_name or x.instrument.display_symbol or x.instrument.local_symbol
                              for x in bundle.accepted_canonical_executions if x.instrument.instrument_id == next(e.instrument_id for e in lifecycle.episodes if e.episode_id == episode_id)))
        return {"status": "available", "reason": None, "entry": entry}
