from __future__ import annotations

import pandas as pd
import pytest

from src.core.canonical_execution import (
    CanonicalExecutionError,
    LegacyExecutionAdapter,
    canonical_execution,
    canonical_executions_to_frame,
    execution_time,
    fee_fact,
    instrument_ref,
    replay_eligibility,
)


def _execution(
    *,
    execution_id: str = "EX-1",
    market: str | None = "MARKET_A",
    time=None,
    sequence: int | None = 0,
    fee=1.25,
    side: str = "BUY",
    display_name: str | None = None,
):
    return canonical_execution(
        subject_id="SUBJECT-1",
        account_id="ACCOUNT-1",
        execution_id=execution_id,
        source_execution_id=f"SRC-{execution_id}",
        source_order_id="ORDER-1",
        instrument=instrument_ref(
            local_symbol="abc",
            market=market,
            security_type="equity" if market is not None else None,
            currency="USD",
            display_name=display_name,
        ),
        event_time=time
        or execution_time(
            "2025-01-02 10:00:00", precision="second", source_timezone="Asia/Shanghai"
        ),
        execution_sequence=sequence,
        sequence_source="broker_sequence" if sequence is not None else None,
        side=side,
        executed_quantity=20,
        executed_price=10,
        fee=fee_fact(fee),
        source="broker_csv",
        source_record_ref=f"record:{execution_id}",
    )


def test_qualified_instrument_identity_is_not_display_symbol_or_currency():
    first = instrument_ref(
        local_symbol="abc", market="market_a", security_type="EQUITY", currency="USD"
    )
    same = instrument_ref(
        local_symbol="ABC",
        market="MARKET_A",
        security_type="equity",
        currency="CNY",
        display_name="Renamed display label",
    )
    other_market = instrument_ref(
        local_symbol="ABC", market="MARKET_B", security_type="equity"
    )
    assert first.instrument_id == same.instrument_id
    assert first.instrument_id != other_market.instrument_id
    assert first.instrument_id != first.local_symbol


def test_missing_market_remains_canonical_but_replay_ineligible():
    item = _execution(market=None)
    eligibility = replay_eligibility((item,))
    assert item.instrument.instrument_id is None
    assert eligibility.eligible is False
    assert eligibility.block_reasons == ("blocked_unresolved_instrument",)


@pytest.mark.parametrize(
    ("amount", "status", "eligible"),
    [(1.25, "known_nonzero", True), (0.0, "explicit_zero", True), (None, "unknown", False)],
)
def test_fee_availability_is_distinct_from_amount(amount, status, eligible):
    item = _execution(fee=amount)
    assert item.fee.status == status
    assert replay_eligibility((item,)).eligible is eligible
    if amount is None:
        assert item.fee.amount is None
        with pytest.raises(CanonicalExecutionError, match="blocked_unknown_fee"):
            canonical_executions_to_frame((item,))


def test_nan_fee_is_unknown_and_never_coerced_to_zero():
    item = _execution(fee=float("nan"))
    assert item.fee.status == "unknown"
    assert item.fee.amount is None
    assert replay_eligibility((item,)).block_reasons == ("blocked_unknown_fee",)


def test_execution_identity_is_independent_of_timestamp_and_sequence():
    base = canonical_execution(
        subject_id="S",
        account_id="A",
        instrument=instrument_ref(
            local_symbol="ABC", market="X", security_type="equity"
        ),
        event_time=execution_time(
            "2025-01-01 10:00", precision="minute", source_timezone="UTC"
        ),
        execution_sequence=0,
        sequence_source="broker_sequence",
        side="BUY",
        executed_quantity=1,
        executed_price=1,
        fee=fee_fact(0),
        source="broker",
        source_record_ref="moved-file-line-ref",
        source_execution_id="BROKER-FILL-1",
    )
    changed_order = canonical_execution(
        subject_id="S",
        account_id="A",
        instrument=base.instrument,
        event_time=execution_time(
            "2025-01-01 11:00", precision="minute", source_timezone="UTC"
        ),
        execution_sequence=9,
        sequence_source="reconciled_sequence",
        side="BUY",
        executed_quantity=1,
        executed_price=1,
        fee=fee_fact(0),
        source="broker",
        source_record_ref="line-stable-ref",
        source_execution_id="BROKER-FILL-1",
    )
    assert base.execution_id == changed_order.execution_id
    assert base.result_payload() != changed_order.result_payload()


def test_timed_naive_source_requires_explicit_iana_timezone():
    with pytest.raises(CanonicalExecutionError, match="source_timezone"):
        execution_time("2025-01-02 10:00", precision="minute")
    with pytest.raises(CanonicalExecutionError, match="IANA"):
        execution_time(
            "2025-01-02 10:00", precision="minute", source_timezone="Mars/Olympus"
        )


def test_offset_aware_source_wins_over_import_timezone():
    value = execution_time(
        "2025-01-02T10:00:00+08:00",
        precision="second",
        source_timezone="America/New_York",
    )
    assert value.instant_utc == pd.Timestamp("2025-01-02T02:00:00Z")


def test_source_calendar_date_is_not_replaced_by_utc_calendar_date():
    value = execution_time(
        "2025-01-02 00:30:00", precision="second", source_timezone="Asia/Shanghai"
    )
    assert value.instant_utc == pd.Timestamp("2025-01-01T16:30:00Z")
    assert value.calendar_date.isoformat() == "2025-01-02"


def test_dst_winter_and_summer_are_normalized_without_machine_timezone():
    winter = execution_time(
        "2025-01-15 10:00", precision="minute", source_timezone="Europe/Madrid"
    )
    summer = execution_time(
        "2025-07-15 10:00", precision="minute", source_timezone="Europe/Madrid"
    )
    assert winter.instant_utc == pd.Timestamp("2025-01-15T09:00:00Z")
    assert summer.instant_utc == pd.Timestamp("2025-07-15T08:00:00Z")


@pytest.mark.parametrize("value", ["2025-10-26 02:30", "2025-03-30 02:30"])
def test_ambiguous_and_nonexistent_dst_times_fail_closed(value):
    with pytest.raises(CanonicalExecutionError, match="ambiguous or nonexistent"):
        execution_time(value, precision="minute", source_timezone="Europe/Madrid")


def test_date_only_retains_precision_without_asserting_an_instant():
    value = execution_time("2025-01-02", precision="date")
    assert value.instant_utc is None
    assert value.calendar_date.isoformat() == "2025-01-02"
    assert value.ordering_key == "date:2025-01-02"


@pytest.mark.parametrize(
    ("value", "precision"),
    [
        ("2025-01-02 10:00:01", "minute"),
        ("2025-01-02 10:00:00.001", "second"),
        ("2025-01-02 10:00:00.000001", "millisecond"),
    ],
)
def test_declared_time_precision_cannot_hide_finer_source_data(value, precision):
    with pytest.raises(CanonicalExecutionError, match="finer precision"):
        execution_time(value, precision=precision, source_timezone="UTC")


def test_same_time_order_requires_unique_explicit_sequence():
    first = _execution(execution_id="EX-1", sequence=None)
    second = _execution(execution_id="EX-2", sequence=None)
    eligibility = replay_eligibility((first, second))
    assert eligibility.eligible is False
    assert eligibility.block_reasons == ("blocked_ambiguous_order",)

    duplicate = _execution(execution_id="EX-2", sequence=0)
    explicit_first = _execution(execution_id="EX-1", sequence=0)
    assert replay_eligibility((explicit_first, duplicate)).eligible is False


def test_complete_execution_is_replay_eligible_and_deterministic():
    item = _execution()
    assert replay_eligibility((item,)).eligible is True
    assert item.result_payload() == _execution().result_payload()


def test_unsupported_direction_is_a_canonical_fact_but_not_replayable():
    item = _execution(side="SHORT")
    assert replay_eligibility((item,)).block_reasons == (
        "blocked_unsupported_direction",
    )


def test_legacy_adapter_uses_an_explicit_demo_namespace_and_preserves_fill_ids():
    frame = pd.DataFrame(
        {
            "event_time": pd.to_datetime(["2025-01-02 10:00", "2025-01-02 10:00"]),
            "symbol": ["SYNTH_A", "SYNTH_A"],
            "side": ["BUY", "BUY"],
            "executed_quantity": [1.0, 2.0],
            "executed_price": [10.0, 10.1],
            "fee": [0.0, 1.0],
            "order_id": ["ORDER-1", "ORDER-1"],
            "execution_id": ["FILL-1", "FILL-2"],
        }
    )
    items = LegacyExecutionAdapter.adapt(
        frame, subject_id="SUBJECT", account_id="ACCOUNT"
    )
    assert [item.execution_id for item in items] == ["FILL-1", "FILL-2"]
    assert [item.execution_sequence for item in items] == [0, 1]
    assert all(item.provenance.sequence_source == "source_row_order" for item in items)
    assert all(item.instrument.market == "LEGACY_DEMO" for item in items)
    assert items[0].instrument.instrument_id != "SYNTH_A"
