from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.core.canonical_execution import (
    canonical_executions_to_frame,
    instrument_ref,
    replay_eligibility,
)
from src.core.portfolio_replay import replay_canonical_executions
from src.episodes.position_episode import build_position_episode_lifecycle
from src.ingestion.generic_csv import (
    GenericCsvImportConfig,
    IMPORT_ISSUE_CODES,
    ImportMappingError,
    build_canonical_import_bundle,
    preview_generic_csv,
    resolve_column_mapping,
)


FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"
CONFIG = GenericCsvImportConfig(
    subject_id="SUBJECT-1",
    account_id="ACC-1",
    source_timezone="Asia/Shanghai",
)


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _preview(name: str, **kwargs):
    config = kwargs.pop("config", CONFIG)
    return preview_generic_csv(_read(name), config=config, **kwargs)


def _new(preview):
    return tuple(
        row.candidate
        for row in preview.rows
        if row.status == "new_execution" and row.candidate is not None
    )


def test_row_refs_match_physical_lines_when_blank_rows_are_skipped():
    content = (
        "ticker,exchange,asset_type,execution_time,type,qty,unit_price,commission,trade_id\n"
        "A,X,equity,2025-01-02 09:30:00,buy,10,10,1,T1\n"
        "\n"
        "\n"
        "B,X,equity,2025-01-03 09:30:00,buy,20,20,2,T2\n"
    )
    preview = preview_generic_csv(content, config=CONFIG)

    assert preview.summary.total_rows == 2
    first, second = preview.batch.rows
    # Row refs and numbers must follow physical file lines (header=1, first
    # data row=2, blank lines 3-4 skipped), not the accepted-row index.
    assert first.row_number == 2
    assert second.row_number == 5
    assert first.source_row_identity.endswith(":row:2")
    assert second.source_row_identity.endswith(":row:5")
    assert [row.row_ref.split(":row:")[-1] for row in preview.rows] == ["2", "5"]


def test_generic_csv_happy_path_and_safe_aliases():
    content = (
        "ticker,exchange,asset_type,execution_time,type,qty,unit_price,commission,trade_id\n"
        "A,X,equity,2025-01-02 09:30:00,buy,10,10,1,T1\n"
    )
    preview = preview_generic_csv(content, config=CONFIG)

    assert preview.summary.total_rows == 1
    assert preview.summary.new_executions == 1
    item = _new(preview)[0]
    assert item.side == "BUY"
    assert item.instrument.local_symbol == "A"
    assert item.instrument.market == "X"


def test_chinese_aliases_and_side_are_exact_not_fuzzy():
    content = "证券代码,交易所,证券类型,成交时间,买卖方向,成交数量,成交价格,手续费\n600000,XSHG,equity,2025-01-02 09:30:00,买入,10,10,0\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert _new(preview)[0].side == "BUY"

    fuzzy = content.replace("证券代码", "我的证券代码备注")
    assert preview_generic_csv(fuzzy, config=CONFIG).batch_issues[0].code == "missing_required_field"


def test_explicit_mapping_overrides_alias_ambiguity():
    content = "symbol,ticker,market,security_type,event_time,side,quantity,price\nA,WRONG,X,equity,2025-01-02 09:30:00,BUY,1,10\n"
    preview = preview_generic_csv(
        content,
        config=CONFIG,
        explicit_mapping={"symbol": "symbol"},
    )
    assert _new(preview)[0].instrument.local_symbol == "A"


def test_ambiguous_alias_mapping_fails_closed():
    with pytest.raises(ImportMappingError) as error:
        resolve_column_mapping(
            ["symbol", "ticker", "market", "security_type", "event_time", "side", "quantity", "price"]
        )
    assert error.value.code == "ambiguous_column_mapping"
    assert error.value.field == "symbol"

    duplicate_header = preview_generic_csv(
        "symbol,symbol,market,security_type,event_time,side,quantity,price\nA,A,X,equity,2025-01-02 09:30:00,BUY,1,10\n",
        config=CONFIG,
    )
    assert duplicate_header.batch_issues[0].code == "ambiguous_column_mapping"


def test_missing_required_column_is_batch_issue_not_guess():
    preview = preview_generic_csv(
        "symbol,market,security_type,event_time,side,quantity\nA,X,equity,2025-01-02,BUY,1\n",
        config=CONFIG,
    )
    assert preview.column_mapping is None
    assert preview.batch_issues[0].code == "missing_required_field"
    assert preview.rows[0].status == "invalid"


def test_source_account_must_match_explicit_target_account():
    content = "account,symbol,market,security_type,event_time,side,quantity,price\nOTHER,A,X,equity,2025-01-02 09:30:00,BUY,1,10\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert preview.rows[0].status == "invalid"
    assert preview.rows[0].issues[0].code == "account_mismatch"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("side", "加仓", "invalid_side"),
        ("quantity", "0", "invalid_quantity"),
        ("quantity", "-1", "invalid_quantity"),
        ("price", "0", "invalid_price"),
        ("price", "not-a-number", "invalid_price"),
        ("side", "SHORT", "unsupported_short_or_margin"),
    ],
)
def test_invalid_execution_facts_are_not_canonicalized(field, value, code):
    row = {
        "symbol": "A",
        "market": "X",
        "security_type": "equity",
        "event_time": "2025-01-02 09:30:00",
        "side": "BUY",
        "quantity": "1",
        "price": "10",
    }
    row[field] = value
    content = ",".join(row) + "\n" + ",".join(row.values()) + "\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert preview.rows[0].status == "invalid"
    assert preview.rows[0].issues[0].code == code
    assert not _new(preview)


def test_fee_nonzero_zero_and_blank_keep_three_fact_states():
    preview = _preview("fixture_c_fees.csv")
    assert [row.candidate.fee.status for row in preview.rows] == [
        "known_nonzero",
        "explicit_zero",
        "unknown",
    ]
    assert [row.candidate.fee.amount for row in preview.rows] == [1.25, 0.0, None]
    assert preview.summary.fee_issue_count == 1
    assert preview.summary.replay_blocked_count == 1


def test_negative_fee_is_invalid_not_silently_changed():
    content = "symbol,market,security_type,event_time,side,quantity,price,fee\nA,X,equity,2025-01-02 09:30:00,BUY,1,10,-1\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert preview.rows[0].status == "invalid"
    assert preview.rows[0].issues[0].code == "invalid_fee"


def test_missing_fee_column_is_unknown_not_zero():
    content = "symbol,market,security_type,event_time,side,quantity,price\nA,X,equity,2025-01-02 09:30:00,BUY,1,10\n"
    item = _new(preview_generic_csv(content, config=CONFIG))[0]
    assert item.fee.status == "unknown"
    assert item.fee.amount is None


def test_naive_time_requires_explicit_timezone():
    missing = _preview(
        "fixture_d_naive_time.csv",
        # Override the shared config deliberately.
        config=GenericCsvImportConfig("SUBJECT-1", "ACC-1"),
    )
    assert missing.rows[0].issues[0].code == "timezone_required"
    assert missing.rows[0].candidate is None


def test_naive_time_uses_configured_iana_timezone_not_machine_timezone():
    item = _new(_preview("fixture_d_naive_time.csv"))[0]
    assert item.event_time.instant_utc == pd.Timestamp("2025-01-02 01:30:00+00:00")
    assert item.event_time.source_timezone == "Asia/Shanghai"


def test_aware_timestamp_respects_its_offset():
    content = "symbol,market,security_type,event_time,side,quantity,price,fee\nA,X,equity,2025-01-02 09:30:00+03:00,BUY,1,10,0\n"
    item = _new(preview_generic_csv(content, config=CONFIG))[0]
    assert item.event_time.instant_utc == pd.Timestamp("2025-01-02 06:30:00+00:00")


def test_date_only_retains_date_precision_without_fake_instant():
    preview = _preview("fixture_e_date_only.csv")
    assert all(row.candidate.event_time.precision == "date" for row in preview.rows)
    assert all(row.candidate.event_time.instant_utc is None for row in preview.rows)
    assert preview.summary.replay_eligible_count == 2


def test_date_only_multiple_rows_without_sequence_are_not_given_fake_intraday_order():
    content = "symbol,market,security_type,event_time,time_precision,side,quantity,price,fee\nA,X,equity,2025-01-02,date,BUY,1,10,0\nA,X,equity,2025-01-02,date,BUY,1,11,0\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert all(row.candidate.event_time.instant_utc is None for row in preview.rows)
    assert all(
        any(issue.code == "ambiguous_execution_order" for issue in row.issues)
        for row in preview.rows
    )


@pytest.mark.parametrize(
    "local_time",
    ["2025-03-09 02:30:00", "2025-11-02 01:30:00"],
)
def test_dst_nonexistent_or_ambiguous_time_delegates_to_canonical_v2(local_time):
    content = f"symbol,market,security_type,event_time,side,quantity,price,fee\nA,X,equity,{local_time},BUY,1,10,0\n"
    preview = preview_generic_csv(
        content,
        config=GenericCsvImportConfig("SUBJECT-1", "ACC-1", "America/New_York"),
    )
    assert preview.rows[0].status == "invalid"
    assert preview.rows[0].issues[0].code == "invalid_timestamp"


def test_qualified_instrument_is_canonical_and_currency_is_metadata():
    item = _new(_preview("fixture_a_lifecycle.csv"))[0]
    assert item.instrument.instrument_id is not None
    assert item.instrument.local_symbol == "600000"
    assert item.instrument.market == "XSHG"
    assert item.instrument.security_type == "equity"
    assert item.instrument.currency == "CNY"


def test_missing_market_and_type_remains_unresolved():
    preview = _preview("fixture_f_ambiguous_instrument.csv")
    item = _new(preview)[0]
    assert item.instrument.instrument_id is None
    assert preview.rows[0].issues[0].code == "unresolved_instrument"
    assert preview.summary.replay_blocked_count == 1


def test_multiple_confirmed_instrument_candidates_are_ambiguous_not_guessed():
    config = GenericCsvImportConfig(
        "SUBJECT-1",
        "ACC-1",
        "Asia/Shanghai",
        confirmed_instruments={
            "ABC": (
                instrument_ref(local_symbol="ABC", market="X", security_type="equity"),
                instrument_ref(local_symbol="ABC", market="Y", security_type="equity"),
            )
        },
    )
    preview = preview_generic_csv(_read("fixture_f_ambiguous_instrument.csv"), config=config)
    assert preview.rows[0].issues[0].code == "ambiguous_instrument"
    assert preview.rows[0].candidate.instrument.instrument_id is None


def test_same_time_fills_preserve_two_candidates_ids_and_sequences():
    preview = _preview("fixture_b_same_time.csv")
    items = _new(preview)
    assert len(items) == 2
    assert len({item.execution_id for item in items}) == 2
    assert [item.execution_sequence for item in items] == [1, 2]
    assert [item.executed_price for item in items] == [10.0, 10.01]


def test_field_identical_fills_are_flagged_not_silently_deduped():
    """Two content-identical rows in one file both stay importable, but the
    second requires an explicit keep/skip decision — a pasted-duplicate block
    must never silently double the position (both rows keep distinct ids and
    the bundle still carries both once the user resolves the review)."""
    preview = _preview("fixture_j_identical_fills.csv")
    items = _new(preview)
    assert len(items) == 1
    statuses = [row.status for row in preview.rows]
    assert statuses == ["new_execution", "possible_duplicate"]
    flagged = preview.rows[1].candidate
    assert flagged is not None
    assert len({items[0].execution_id, flagged.execution_id}) == 2
    assert preview.summary.possible_duplicates == 1


def test_same_time_without_order_evidence_is_canonical_but_replay_blocked():
    content = "symbol,market,security_type,event_time,side,quantity,price,fee\nA,X,equity,2025-01-02 10:00:00,BUY,1,10,0\nA,X,equity,2025-01-02 10:00:00,BUY,1,11,0\n"
    preview = preview_generic_csv(content, config=CONFIG)
    assert len(_new(preview)) == 2
    assert preview.summary.replay_blocked_count == 2
    assert all(
        any(issue.code == "ambiguous_execution_order" for issue in row.issues)
        for row in preview.rows
    )


def test_source_row_order_only_becomes_sequence_when_explicitly_configured():
    content = "symbol,market,security_type,event_time,side,quantity,price,fee\nA,X,equity,2025-01-02 10:00:00,BUY,1,10,0\nA,X,equity,2025-01-02 10:00:00,BUY,1,11,0\n"
    config = GenericCsvImportConfig(
        "SUBJECT-1", "ACC-1", "Asia/Shanghai", use_source_row_order_as_sequence=True
    )
    items = _new(preview_generic_csv(content, config=config))
    assert [item.execution_sequence for item in items] == [2, 3]
    assert all(item.provenance.sequence_source == "source_row_order" for item in items)


def test_source_execution_id_is_stable_across_file_presentation_changes():
    first = _new(_preview("fixture_g_reimport.csv"))[0]
    changed = _read("fixture_g_reimport.csv").decode().replace("10.00", "10.000")
    second = _new(preview_generic_csv(changed, config=CONFIG))[0]
    assert first.execution_id == second.execution_id


def test_same_file_reimport_is_file_and_row_level_idempotent():
    first = _preview("fixture_g_reimport.csv")
    second = _preview(
        "fixture_g_reimport.csv",
        existing_executions=_new(first),
        existing_file_hashes=(first.batch.file_sha256,),
    )
    assert second.duplicate_file is True
    assert second.summary.new_executions == 0
    assert second.summary.exact_duplicates == 1


def test_overlapping_export_adds_only_new_tail():
    prior = _preview("fixture_h_jan_jun.csv")
    overlap = _preview("fixture_h_jan_jul.csv", existing_executions=_new(prior))
    assert [row.status for row in overlap.rows] == [
        "exact_duplicate",
        "exact_duplicate",
        "new_execution",
    ]
    assert _new(overlap)[0].source_execution_id == "H-JUL"


def test_source_id_content_change_is_conflicting_revision_not_overwrite():
    prior = _preview("fixture_g_reimport.csv")
    conflict = _preview("fixture_i_source_conflict.csv", existing_executions=_new(prior))
    row = conflict.rows[0]
    assert row.status == "conflicting_revision"
    assert row.existing_execution_id == _new(prior)[0].execution_id
    assert conflict.summary.conflicts == 1
    assert not _new(conflict)


def test_exact_duplicate_uses_stable_no_source_id_fingerprint():
    prior = _preview("fixture_d_naive_time.csv")
    repeated = _preview("fixture_d_naive_time.csv", existing_executions=_new(prior))
    assert repeated.rows[0].status == "exact_duplicate"


def test_similar_no_id_fact_with_changed_fee_is_possible_duplicate():
    prior = _preview("fixture_d_naive_time.csv")
    incoming = _read("fixture_d_naive_time.csv").decode().replace(",0\n", ",1\n")
    preview = preview_generic_csv(incoming, config=CONFIG, existing_executions=_new(prior))
    assert preview.rows[0].status == "possible_duplicate"
    assert preview.summary.possible_duplicates == 1
    assert not _new(preview)


def test_file_sha_is_exact_bytes_and_bom_is_supported():
    content = _read("fixture_g_reimport.csv")
    preview = preview_generic_csv(b"\xef\xbb\xbf" + content, config=CONFIG)
    assert preview.batch.file_sha256 == hashlib.sha256(b"\xef\xbb\xbf" + content).hexdigest()
    assert preview.summary.new_executions == 1


def test_human_formatted_numbers_parse_in_generic_csv():
    # Thousands separators, currency suffixes and full-width digits are human
    # formatting, the same normalization the broker adapter applies — not
    # invalid_quantity/invalid_price rejections.
    content = (
        'symbol,market,security_type,event_time,side,quantity,price,fee\n'
        '600000,XSHG,equity,2025-01-02 09:30:00,BUY,"1,200","12.5元","￥5.50"\n'
        '600000,XSHG,equity,2025-01-03 09:30:00,BUY,"１００","１２.５０",０\n'
    )
    preview = preview_generic_csv(content, config=CONFIG)
    items = _new(preview)
    assert len(items) == 2
    assert items[0].executed_quantity == 1200
    assert items[0].executed_price == 12.5
    assert items[0].fee.amount == 5.5
    assert items[1].executed_quantity == 100
    assert items[1].executed_price == 12.5


def test_quoted_security_name_with_comma_and_crlf_parse_without_entering_canonical():
    content = (
        'symbol,market,security_type,event_time,side,quantity,price,fee,security_name,phone\r\n'
        'A,X,equity,2025-01-02 09:30:00,BUY,1,10,0,"Acme, Inc.",13800000000\r\n'
    )
    preview = preview_generic_csv(content, config=CONFIG)
    assert preview.summary.new_executions == 1
    payload = _new(preview)[0].result_payload()
    assert "security_name" not in payload
    assert "phone" not in payload
    assert dict(preview.batch.rows[0].original_values)["security_name"] == "Acme, Inc."


def test_raw_rows_are_traceable_but_bundle_excludes_original_values():
    preview = _preview("fixture_g_reimport.csv")
    raw = preview.batch.rows[0]
    assert raw.source_file_sha256 == preview.batch.file_sha256
    assert raw.source_row_identity.endswith(":row:2")
    assert raw.mapping_version == "generic_csv_mapping_v1"
    assert "original_values" not in preview.batch.as_dict()
    assert b"original_values" not in build_canonical_import_bundle(preview).canonical_bytes()


def test_preview_totals_and_structured_issue_taxonomy_are_frontend_ready():
    content = (
        "symbol,market,security_type,event_time,side,quantity,price,fee,source_execution_id\n"
        "A,X,equity,2025-01-02 09:30:00,BUY,1,10,0,T1\n"
        "A,X,equity,2025-01-03 09:30:00,BUY,1,10,,T2\n"
        "A,,equity,2025-01-04 09:30:00,BUY,1,10,0,T3\n"
        "A,X,equity,2025-01-05 09:30:00,BUY,0,10,0,T4\n"
    )
    preview = preview_generic_csv(content, config=CONFIG)
    assert preview.summary.as_dict() == {
        "total_rows": 4,
        "accepted_canonical_facts": 3,
        "new_executions": 3,
        "exact_duplicates": 0,
        "possible_duplicates": 0,
        "conflicts": 0,
        "invalid_rows": 1,
        "blocking_rows": 2,
        "warning_rows": 1,
        "replay_eligible_count": 1,
        "replay_blocked_count": 2,
        "instrument_issue_count": 1,
        "fee_issue_count": 1,
    }
    assert all(issue.code and issue.severity for row in preview.rows for issue in row.issues)
    assert preview.date_range == ("2025-01-02", "2025-01-04")
    assert preview.accounts == ("ACC-1",)
    assert {
        "ambiguous_column_mapping",
        "missing_required_field",
        "unknown_fee",
        "unresolved_instrument",
        "replay_ineligible",
        "missing_market_data",
    }.issubset(IMPORT_ISSUE_CODES)
    # The model-facing form is JSON-safe and excludes raw original values.
    assert preview.as_dict()["rows"][0]["candidate"]["fee"]["status"] == "explicit_zero"


def test_hand_calculated_ten_row_fixture_has_independent_expected_counts():
    existing_source = (
        "symbol,market,security_type,event_time,side,quantity,price,fee,source_execution_id\n"
        "A,X,equity,2025-01-01 09:30:00,BUY,1,10,0,E1\n"
        "A,X,equity,2025-01-02 09:30:00,BUY,1,10,0,E2\n"
    )
    no_id_source = (
        "symbol,market,security_type,event_time,side,quantity,price,fee\n"
        "A,X,equity,2025-01-03 09:30:00,BUY,1,10,0\n"
    )
    existing = (
        *_new(preview_generic_csv(existing_source, config=CONFIG)),
        *_new(preview_generic_csv(no_id_source, config=CONFIG)),
    )
    preview = _preview(
        "fixture_hand_calculated_10.csv",
        existing_executions=existing,
    )

    # These expectations are hand-counted from the fixture, not generated by a
    # production helper: 5 accepted new facts, 3 reconciliation holds, 2 invalid.
    assert preview.summary.as_dict() == {
        "total_rows": 10,
        "accepted_canonical_facts": 5,
        "new_executions": 5,
        "exact_duplicates": 1,
        "possible_duplicates": 1,
        "conflicts": 1,
        "invalid_rows": 2,
        "blocking_rows": 6,
        "warning_rows": 2,
        "replay_eligible_count": 1,
        "replay_blocked_count": 4,
        "instrument_issue_count": 1,
        "fee_issue_count": 1,
    }
    assert [row.status for row in preview.rows] == [
        "new_execution",
        "new_execution",
        "new_execution",
        "invalid",
        "invalid",
        "exact_duplicate",
        "conflicting_revision",
        "possible_duplicate",
        "new_execution",
        "new_execution",
    ]


def test_bundle_excludes_invalid_duplicate_conflict_and_possible_duplicate_rows():
    prior = _preview("fixture_g_reimport.csv")
    content = (
        _read("fixture_g_reimport.csv").decode()
        + "600000,XSHG,equity,2025-01-03 09:30:00,BUY,0,10.00,0,G-BAD\n"
    )
    preview = preview_generic_csv(content, config=CONFIG, existing_executions=_new(prior))
    bundle = build_canonical_import_bundle(preview)
    assert bundle.accepted_canonical_executions == ()


def test_unknown_fee_fact_is_retained_in_bundle_but_not_exact_replay_eligible():
    preview = _preview("fixture_c_fees.csv")
    bundle = build_canonical_import_bundle(preview)
    unknown = next(item for item in bundle.accepted_canonical_executions if item.fee.status == "unknown")
    assert unknown.fee.amount is None
    assert replay_eligibility((unknown,)).eligible is False
    assert dict(bundle.replay_eligibility_summary) == {"eligible": 2, "blocked": 1}


def test_bundle_is_deterministic_when_physical_rows_change_but_explicit_order_does_not():
    header, first, second = _read("fixture_b_same_time.csv").decode().splitlines()
    normal = build_canonical_import_bundle(preview_generic_csv("\n".join((header, first, second)) + "\n", config=CONFIG))
    reversed_rows = build_canonical_import_bundle(preview_generic_csv("\n".join((header, second, first)) + "\n", config=CONFIG))
    assert normal.bundle_id == reversed_rows.bundle_id
    assert normal.canonical_bytes() == reversed_rows.canonical_bytes()

    identical_header, identical_first, identical_second = _read(
        "fixture_j_identical_fills.csv"
    ).decode().splitlines()
    identical_normal = build_canonical_import_bundle(
        preview_generic_csv(
            "\n".join((identical_header, identical_first, identical_second)) + "\n",
            config=CONFIG,
        )
    )
    identical_reversed = build_canonical_import_bundle(
        preview_generic_csv(
            "\n".join((identical_header, identical_second, identical_first)) + "\n",
            config=CONFIG,
        )
    )
    assert identical_normal.canonical_bytes() == identical_reversed.canonical_bytes()


def test_bundle_is_deterministic_for_reordered_unique_no_id_facts():
    header = "symbol,market,security_type,event_time,side,quantity,price,fee"
    first = "A,X,equity,2025-01-02 09:30:00,BUY,1,10,0"
    second = "A,X,equity,2025-01-03 09:30:00,BUY,2,11,0"
    left = build_canonical_import_bundle(
        preview_generic_csv("\n".join((header, first, second)) + "\n", config=CONFIG)
    )
    right = build_canonical_import_bundle(
        preview_generic_csv("\n".join((header, second, first)) + "\n", config=CONFIG)
    )
    assert left.bundle_id == right.bundle_id
    assert left.canonical_bytes() == right.canonical_bytes()


def test_market_data_requirements_are_daily_exact_date_no_forward_fill():
    bundle = build_canonical_import_bundle(_preview("fixture_a_lifecycle.csv"))
    requirement = bundle.market_data_requirements[0]
    assert requirement.start_date == "2025-01-02"
    assert requirement.end_date == "2025-01-06"
    assert requirement.price_frequency == "daily"
    assert requirement.exact_date_required is True
    assert requirement.forward_fill_allowed is False


def test_missing_market_data_does_not_remove_imported_execution():
    bundle = build_canonical_import_bundle(_preview("fixture_g_reimport.csv"))
    assert len(bundle.accepted_canonical_executions) == 1
    assert len(bundle.market_data_requirements) == 1
    assert "market_data_not_fetched_exact_daily_prices_required_downstream" in bundle.limitations


def test_fully_eligible_bundle_replays_every_fill_via_existing_vectorbt_core():
    bundle = build_canonical_import_bundle(_preview("fixture_b_same_time.csv"))
    frame = canonical_executions_to_frame(bundle.accepted_canonical_executions)
    instrument_id = bundle.instrument_refs[0].instrument_id
    marks = pd.DataFrame(
        {instrument_id: [10.50]},
        index=pd.DatetimeIndex([frame.event_time.iloc[0]]),
    )
    result = replay_canonical_executions(
        bundle.accepted_canonical_executions,
        marks,
        init_cash=100_000,
    )
    assert len(result.portfolio.orders.records_readable) == 2
    assert [link.execution_id for link in result.execution_links] == [
        item.execution_id for item in bundle.accepted_canonical_executions
    ]


def test_realistic_csv_bundle_builds_position_episode_through_existing_core():
    bundle = build_canonical_import_bundle(_preview("fixture_a_lifecycle.csv"))
    executions = canonical_executions_to_frame(bundle.accepted_canonical_executions)
    instrument_id = bundle.instrument_refs[0].instrument_id
    prices = pd.DataFrame(
        [
            {
                "date": date,
                "instrument": instrument_id,
                "close": close,
                "price_type": "synthetic",
                "data_source": "real_user_ingestion_test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for date, close in zip(
                pd.date_range("2025-01-02", periods=5),
                [10.0, 11.0, 12.0, 13.0, 12.5],
            )
        ]
    )
    lifecycle = build_position_episode_lifecycle(
        executions,
        prices,
        subject_id="SUBJECT-1",
        account_id="ACC-1",
        as_of=pd.Timestamp("2025-01-06 23:59:00"),
        init_cash=100_000,
        data_tier="synthetic",
        calculation_code_version="real-user-ingestion-v1-test",
    )
    assert len(lifecycle.episodes) == 2
    assert [episode.status for episode in lifecycle.episodes] == ["closed", "open"]
    assert [decision.decision_type for decision in lifecycle.decisions] == [
        "open_position",
        "add_position",
        "reduce_position",
        "close_position",
        "open_position",
    ]


def test_importer_has_no_financial_calculation_or_vectorbt_import():
    source = (Path(__file__).parents[1] / "src" / "ingestion" / "generic_csv.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "vectorbt" not in imported
    assert "sqlite3" not in imported
    assert "LocalMarketDataProvider" not in source
    assert not {"pnl", "return", "cost_basis", "average_cost"}.intersection(
        name.id.lower() for name in ast.walk(tree) if isinstance(name, ast.Name)
    )
