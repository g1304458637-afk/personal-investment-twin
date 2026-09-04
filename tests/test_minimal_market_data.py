from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src.attribution.decision_outcome import build_actual_outcomes
from src.core.canonical_execution import canonical_executions_to_frame, instrument_ref
from src.ingestion.generic_csv import (
    GenericCsvImportConfig,
    build_canonical_import_bundle,
    preview_generic_csv,
)
from src.market_data import (
    GenericHistoricalPriceCsvAdapter,
    GenericPriceCsvConfig,
    build_episode_when_market_ready,
    facts_to_market_data_frame,
    resolve_market_data_requirements,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "market_data" / "historical_prices_65.csv"
SUBJECT = "REAL-SUBJECT"
ACCOUNT = "REAL-ACCOUNT"
IMPORTED_AT = "2026-09-04T12:00:00+08:00"


def trade_bundle():
    content = (
        "symbol,market,security_type,event_time,side,quantity,price,fee,source_execution_id\n"
        "SAMPLE,X,equity,2025-01-02 10:00:00,BUY,100,10.00,1,E1\n"
        "SAMPLE,X,equity,2025-01-06 10:00:00,SELL,40,10.20,1,E2\n"
        "SAMPLE,X,equity,2025-01-07 10:00:00,BUY,20,10.10,1,E3\n"
    )
    preview = preview_generic_csv(
        content,
        config=GenericCsvImportConfig(
            subject_id=SUBJECT,
            account_id=ACCOUNT,
            source_timezone="Asia/Shanghai",
        ),
    )
    return build_canonical_import_bundle(preview)


def config(*, known=()):
    return GenericPriceCsvConfig(
        source_id="user_csv",
        source_version="statement-v1",
        imported_at=IMPORTED_AT,
        known_instruments=tuple(known),
    )


def preview(content=None, *, existing=(), requirement_bundle=None, known=()):
    return GenericHistoricalPriceCsvAdapter().preview(
        FIXTURE.read_bytes() if content is None else content,
        config(known=known),
        existing=existing,
        requirement_bundle=requirement_bundle,
    )


def facts(result=None):
    result = result or preview()
    return tuple(row.candidate for row in result.rows if row.status == "new_observation" and row.candidate)


def test_happy_path_imports_realistic_daily_fixture() -> None:
    result = preview()
    assert result.total_observations == 65
    assert result.new_observations == 65
    assert result.invalid_rows == result.conflicts == 0
    assert result.date_range == ("2025-01-02", "2025-04-02")


def test_import_is_deterministic() -> None:
    assert preview() == preview()


def test_qualified_instrument_matches_canonical_v2() -> None:
    item = facts()[0]
    expected = instrument_ref(local_symbol="SAMPLE", market="X", security_type="equity")
    assert item.instrument.instrument_id == expected.instrument_id


def test_same_symbol_on_two_markets_remains_isolated() -> None:
    content = (
        "local_symbol,market,security_type,date,price,price_type\n"
        "ABC,X,equity,2025-01-02,10,adjusted_close\n"
        "ABC,Y,equity,2025-01-02,20,adjusted_close\n"
    )
    items = facts(preview(content))
    assert len({item.instrument.instrument_id for item in items}) == 2


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("date", "not-a-date", "Invalid isoformat string: 'not-a-date'"),
        ("price", "0", "invalid_price"),
        ("price", "nan", "invalid_price"),
        ("price_type", "raw_close", "unsupported_price_type"),
        ("price_type", "synthetic", "unsupported_price_type"),
    ],
)
def test_invalid_market_fact_fails_closed(field: str, value: str, code: str) -> None:
    row = {
        "date": "2025-01-02",
        "price": "10",
        "price_type": "adjusted_close",
    }
    row[field] = value
    content = (
        "local_symbol,market,security_type,date,price,price_type\n"
        f"SAMPLE,X,equity,{row['date']},{row['price']},{row['price_type']}\n"
    )
    result = preview(content)
    assert result.invalid_rows == 1
    assert code in result.rows[0].issues[0].code


def test_duplicate_row_is_not_a_second_fact() -> None:
    line = "SAMPLE,X,equity,2025-01-02,10,adjusted_close"
    result = preview(
        "local_symbol,market,security_type,date,price,price_type\n" + line + "\n" + line + "\n"
    )
    assert result.new_observations == 1
    assert result.duplicate_rows == 1
    assert result.existing_observations == 0


def test_existing_observation_is_detected() -> None:
    first = facts(preview("local_symbol,market,security_type,date,price,price_type\nSAMPLE,X,equity,2025-01-02,10,adjusted_close\n"))
    result = preview(
        "local_symbol,market,security_type,date,price,price_type\nSAMPLE,X,equity,2025-01-02,10,adjusted_close\n",
        existing=first,
    )
    assert result.existing_observations == 1
    assert result.new_observations == 0


def test_conflicting_price_never_overwrites() -> None:
    first = facts(preview("local_symbol,market,security_type,date,price,price_type\nSAMPLE,X,equity,2025-01-02,10,adjusted_close\n"))
    result = preview(
        "local_symbol,market,security_type,date,price,price_type\nSAMPLE,X,equity,2025-01-02,11,adjusted_close\n",
        existing=first,
    )
    assert result.conflicts == 1
    assert result.rows[0].candidate.close == 11
    assert result.rows[0].existing_observation_id == first[0].observation_id


def test_instrument_id_input_resolves_only_through_known_registry() -> None:
    known = instrument_ref(local_symbol="SAMPLE", market="X", security_type="equity")
    content = (
        "instrument_id,date,price,price_type\n"
        f"{known.instrument_id},2025-01-02,10,adjusted_close\n"
    )
    assert preview(content, known=(known,)).new_observations == 1
    assert preview(content).invalid_rows == 1


def test_market_contract_projection_preserves_frozen_semantics() -> None:
    frame = facts_to_market_data_frame(facts()[:2])
    assert tuple(frame.columns) == (
        "date", "instrument", "close", "price_type", "data_source", "data_version", "is_synthetic"
    )
    assert set(frame["price_type"]) == {"adjusted_close"}
    assert not frame["is_synthetic"].any()


def test_requirement_resolution_complete_partial_and_missing() -> None:
    bundle = trade_bundle()
    all_facts = facts()
    complete = resolve_market_data_requirements(bundle, all_facts)
    assert complete.status == "complete"
    assert complete.required_observation_count == 3
    required_dates = {"2025-01-02", "2025-01-06", "2025-01-07"}
    partial_facts = tuple(item for item in all_facts if item.date.isoformat() in required_dates - {"2025-01-07"})
    assert resolve_market_data_requirements(bundle, partial_facts).status == "partial"
    assert resolve_market_data_requirements(bundle, ()).status == "missing"


def test_missing_required_date_is_reported_without_forward_fill() -> None:
    bundle = trade_bundle()
    all_facts = tuple(item for item in facts() if item.date.isoformat() != "2025-01-06")
    availability = resolve_market_data_requirements(bundle, all_facts)
    assert availability.missing == ((bundle.instrument_refs[0].instrument_id, ("2025-01-06",)),)
    gated = build_episode_when_market_ready(
        bundle,
        all_facts,
        as_of=pd.Timestamp("2025-04-02 23:59:00"),
        init_cash=100_000,
        calculation_code_version="market-data-test",
    )
    assert gated.status == "unavailable_pending_market_data"
    assert gated.lifecycle is None


def test_real_account_requirement_never_uses_synthetic_demo_price() -> None:
    bundle = trade_bundle()
    real = facts()[0]
    synthetic = replace(
        real,
        price_type="synthetic",
        source_tier="synthetic_demo",
        source_id="product_demo",
        source_version="demo-v1",
    )
    availability = resolve_market_data_requirements(bundle, (synthetic,))
    assert availability.status == "missing"
    assert availability.available_observation_count == 0


def test_preview_reports_market_requirement_coverage() -> None:
    result = preview(requirement_bundle=trade_bundle())
    assert result.missing_required_dates == ()


def test_episode_builds_only_from_complete_imported_real_prices() -> None:
    bundle = trade_bundle()
    result = build_episode_when_market_ready(
        bundle,
        facts(),
        as_of=pd.Timestamp("2025-04-02 23:59:00"),
        init_cash=100_000,
        calculation_code_version="market-data-test",
    )
    assert result.status == "available"
    assert result.lifecycle is not None
    assert result.lifecycle.data_tier == "authorized_beta"


def test_outcome_consumes_the_same_imported_market_contract() -> None:
    bundle = trade_bundle()
    imported = facts()
    gated = build_episode_when_market_ready(
        bundle,
        imported,
        as_of=pd.Timestamp("2025-04-02 23:59:00"),
        init_cash=100_000,
        calculation_code_version="market-data-test",
    )
    analysis = build_actual_outcomes(
        gated.lifecycle,
        canonical_executions_to_frame(bundle.accepted_canonical_executions),
        facts_to_market_data_frame(imported),
        subject_id=SUBJECT,
        account_id=ACCOUNT,
        analysis_as_of=pd.Timestamp("2025-04-02 23:59:00"),
        init_cash=100_000,
    )
    assert analysis.episode_outcomes
    assert all(
        not provenance.is_synthetic
        for outcome in analysis.episode_outcomes
        for provenance in outcome.provenance
    )


def test_imported_at_metadata_does_not_change_market_identity() -> None:
    first = facts()[0]
    later = replace(first, imported_at="2026-09-05T12:00:00+08:00")
    assert first.identity_key == later.identity_key
    assert first.observation_id == later.observation_id


def test_adapter_has_no_network_or_financial_engine_dependency() -> None:
    source = (ROOT / "src" / "market_data" / "generic_csv.py").read_text()
    assert "requests" not in source
    assert "http" not in source
    assert "vectorbt" not in source
    assert "Portfolio" not in source
