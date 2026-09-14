from __future__ import annotations

import pandas as pd
import pytest

from src.evidence.contracts import create_evidence_record
from src.episodes.position_episode import (
    PositionEpisodeError,
    build_position_episode_lifecycle,
)


INITIAL_CASH = 100_000.0
SUBJECT_ID = "test-subject"


def _executions(rows: list[tuple], *, accounts: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=(
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
        ),
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    frame["fee"] = [float(index + 1) for index in range(len(frame))]
    frame["order_id"] = [f"ORD-{index}" for index in range(len(frame))]
    frame["execution_id"] = [f"EXE-{index}" for index in range(len(frame))]
    if accounts is not None:
        frame["account_id"] = accounts
    return frame


def _prices(values: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date,
                "instrument": symbol,
                "close": close,
                "price_type": "synthetic",
                "data_source": "position_episode_test",
                "data_version": "v1",
                "is_synthetic": True,
            }
            for symbol, closes in values.items()
            for date, close in zip(dates, closes)
        ]
    )


def _build(
    executions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    as_of: str,
    account_id: str | None = "BROKER-A",
    **kwargs,
):
    return build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=SUBJECT_ID,
        account_id=account_id,
        as_of=pd.Timestamp(as_of),
        init_cash=INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version="position-episode-test-v1",
        **kwargs,
    )


def _full_lifecycle() -> tuple[pd.DataFrame, pd.DataFrame]:
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 09:30", "A", "BUY", 50.0, 11.0),
            ("2025-01-04 09:30", "A", "SELL", 30.0, 12.0),
            ("2025-01-05 09:30", "A", "SELL", 120.0, 13.0),
        ]
    )
    prices = _prices(
        {"A": [10.0, 11.0, 12.0, 13.0]},
        ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
    )
    return executions, prices


def _state(lifecycle, reference: str):
    return next(item for item in lifecycle.states if item.state_id == reference)


def test_full_lifecycle_has_one_closed_episode_and_all_four_decisions():
    executions, prices = _full_lifecycle()

    lifecycle = _build(executions, prices, as_of="2025-01-05 23:59")

    assert len(lifecycle.episodes) == 1
    episode = lifecycle.episodes[0]
    assert episode.status == "closed"
    assert episode.opened_at == pd.Timestamp("2025-01-02 09:30")
    assert episode.closed_at == pd.Timestamp("2025-01-05 09:30")
    assert episode.opening_execution_id == "EXE-0"
    assert episode.closing_execution_id == "EXE-3"
    assert episode.execution_refs == ("EXE-0", "EXE-1", "EXE-2", "EXE-3")
    assert [item.decision_type for item in lifecycle.decisions] == [
        "open_position",
        "add_position",
        "reduce_position",
        "close_position",
    ]
    assert _state(lifecycle, lifecycle.decisions[0].state_before_ref).quantity == 0
    assert _state(lifecycle, lifecycle.decisions[0].state_after_ref).quantity == 100
    assert _state(lifecycle, lifecycle.decisions[1].state_after_ref).quantity == 150
    assert _state(lifecycle, lifecycle.decisions[2].state_after_ref).quantity == 120
    assert _state(lifecycle, lifecycle.decisions[3].state_after_ref).quantity == 0


def test_timezone_aware_as_of_is_aligned_instead_of_type_error():
    executions, prices = _full_lifecycle()

    naive = _build(executions, prices, as_of="2025-01-05 23:59")
    aware_utc = _build(executions, prices, as_of="2025-01-05 23:59+00:00")
    # The same instant expressed in +08:00 is 2025-01-05 15:59 naive UTC.
    aware_cst = _build(executions, prices, as_of="2025-01-06 07:59+08:00")

    assert aware_utc == naive
    assert aware_cst == naive
    # A non-UTC as_of cuts off at its UTC instant: 2025-01-03 23:59+08:00 is
    # 2025-01-03 15:59 naive, so the 01-04/01-05 executions are excluded.
    earlier_cst = _build(executions, prices, as_of="2025-01-03 23:59+08:00")
    assert earlier_cst.as_of == pd.Timestamp("2025-01-03 15:59")
    assert len(earlier_cst.episodes) == 1
    assert earlier_cst.episodes[0].status == "open"


def test_timezone_aware_source_frames_are_normalized_to_naive_utc():
    executions, prices = _full_lifecycle()
    naive = _build(executions, prices, as_of="2025-01-05 23:59")

    aware_executions = executions.copy()
    aware_executions["event_time"] = aware_executions["event_time"].dt.tz_localize(
        "Asia/Shanghai"
    )
    aware_prices = prices.copy()
    aware_prices["date"] = pd.to_datetime(aware_prices["date"]).dt.tz_localize(
        "Asia/Shanghai"
    )

    # Mixed aware/naive inputs must not raise bare TypeErrors; facts are
    # aligned to the naive UTC replay axes before filtering and pivoting.
    from_aware_executions = _build(
        aware_executions, prices, as_of="2025-01-05 23:59"
    )
    from_aware_prices = _build(
        executions, aware_prices, as_of="2025-01-05 23:59"
    )

    assert [
        item.decision_type for item in from_aware_executions.decisions
    ] == [item.decision_type for item in naive.decisions]
    assert from_aware_executions.episodes[0].closed_at == pd.Timestamp(
        "2025-01-05 01:30"
    )
    assert from_aware_prices == naive


def test_open_episode_is_first_class_and_partial_sell_is_not_final_exit():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 09:30", "A", "BUY", 50.0, 11.0),
            ("2025-01-04 09:30", "A", "SELL", 80.0, 12.0),
        ]
    )
    prices = _prices(
        {"A": [10.0, 11.0, 12.0, 15.0]},
        ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-08"],
    )

    lifecycle = _build(executions, prices, as_of="2025-01-08 23:59")
    episode = lifecycle.episodes[0]
    snapshot = lifecycle.snapshots[0]
    current = _state(lifecycle, snapshot.position_state_ref)

    assert episode.status == "open"
    assert episode.closed_at is None
    assert episode.closing_execution_id is None
    assert episode.duration_kind == "so_far"
    assert [item.decision_type for item in lifecycle.decisions] == [
        "open_position",
        "add_position",
        "reduce_position",
    ]
    assert current.quantity == pytest.approx(70.0)
    assert current.average_cost == pytest.approx(10.3333333333)
    assert current.valuation_at == pd.Timestamp("2025-01-08")
    assert current.valuation_price == pytest.approx(15.0)
    assert current.market_value == pytest.approx(1_050.0)


def test_two_round_trips_create_two_episodes():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 10:00", "A", "SELL", 100.0, 11.0),
            ("2025-01-04 09:30", "A", "BUY", 50.0, 12.0),
            ("2025-01-05 10:00", "A", "SELL", 50.0, 13.0),
        ]
    )
    prices = _prices(
        {"A": [10.0, 11.0, 12.0, 13.0]},
        ["2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
    )

    lifecycle = _build(executions, prices, as_of="2025-01-05 23:59")

    assert len(lifecycle.episodes) == 2
    assert lifecycle.episodes[0].episode_id != lifecycle.episodes[1].episode_id
    assert [item.status for item in lifecycle.episodes] == ["closed", "closed"]
    assert [item.execution_refs for item in lifecycle.episodes] == [
        ("EXE-0", "EXE-1"),
        ("EXE-2", "EXE-3"),
    ]


def test_same_calendar_day_close_then_reopen_remains_two_episodes():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-03 10:00", "A", "SELL", 100.0, 11.0),
            ("2025-01-03 14:00", "A", "BUY", 40.0, 11.5),
        ]
    )
    prices = _prices({"A": [10.0, 11.25]}, ["2025-01-02", "2025-01-03"])

    lifecycle = _build(executions, prices, as_of="2025-01-03 23:59")

    assert len(lifecycle.episodes) == 2
    assert lifecycle.episodes[0].closed_at == pd.Timestamp("2025-01-03 10:00")
    assert lifecycle.episodes[1].opened_at == pd.Timestamp("2025-01-03 14:00")
    assert lifecycle.episodes[1].status == "open"
    assert [item.decision_type for item in lifecycle.decisions] == [
        "open_position",
        "close_position",
        "open_position",
    ]


def test_same_timestamp_close_then_reopen_uses_execution_sequence():
    executions = _executions(
        [
            ("2025-01-02 10:00", "A", "BUY", 100.0, 10.0),
            ("2025-01-02 10:00", "A", "SELL", 100.0, 11.0),
            ("2025-01-02 10:00", "A", "BUY", 50.0, 12.0),
        ]
    )
    executions["execution_sequence"] = [1, 2, 3]
    executions["sequence_source"] = "broker_sequence"
    prices = _prices({"A": [12.5]}, ["2025-01-02"])

    lifecycle = _build(executions, prices, as_of="2025-01-02 23:59")

    assert [item.status for item in lifecycle.episodes] == ["closed", "open"]
    assert [item.decision_type for item in lifecycle.decisions] == [
        "open_position",
        "close_position",
        "open_position",
    ]
    assert lifecycle.episodes[0].execution_refs == ("EXE-0", "EXE-1")
    assert lifecycle.episodes[1].execution_refs == ("EXE-2",)
    assert lifecycle.episodes[0].vectorbt_position_record_id == 0
    assert lifecycle.episodes[1].vectorbt_position_record_id == 1


def test_same_timestamp_buy_buy_is_open_then_add_and_row_order_is_irrelevant():
    executions = _executions(
        [
            ("2025-01-02 10:00", "A", "BUY", 30.0, 10.0),
            ("2025-01-02 10:00", "A", "BUY", 20.0, 11.0),
        ]
    )
    executions["execution_sequence"] = [1, 2]
    executions["sequence_source"] = "broker_sequence"
    prices = _prices({"A": [12.0]}, ["2025-01-02"])

    first = _build(executions, prices, as_of="2025-01-02 23:59")
    reordered = _build(
        executions.iloc[::-1].reset_index(drop=True),
        prices,
        as_of="2025-01-02 23:59",
    )

    assert [item.decision_type for item in first.decisions] == [
        "open_position",
        "add_position",
    ]
    assert first == reordered
    current = _state(first, first.snapshots[0].position_state_ref)
    assert current.quantity == pytest.approx(50.0)
    assert current.average_cost == pytest.approx(10.4)


def test_multiple_partial_sells_keep_one_episode_open():
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 1_000.0, 10.0),
            ("2025-01-03", "A", "SELL", 200.0, 11.0),
            ("2025-01-04", "A", "SELL", 300.0, 12.0),
        ]
    )
    prices = _prices(
        {"A": [10.0, 11.0, 12.0]},
        ["2025-01-02", "2025-01-03", "2025-01-04"],
    )

    lifecycle = _build(executions, prices, as_of="2025-01-04")

    assert len(lifecycle.episodes) == 1
    assert lifecycle.episodes[0].status == "open"
    assert [item.decision_type for item in lifecycle.decisions] == [
        "open_position",
        "reduce_position",
        "reduce_position",
    ]
    assert all(item.decision_type != "close_position" for item in lifecycle.decisions)
    assert _state(lifecycle, lifecycle.snapshots[0].position_state_ref).quantity == 500


def test_multi_account_same_symbol_produces_separate_episode_ids():
    executions = _executions(
        [
            ("2025-01-02 09:30", "A", "BUY", 100.0, 10.0),
            ("2025-01-02 09:30", "A", "BUY", 200.0, 10.0),
        ],
        accounts=["BROKER-A", "BROKER-B"],
    )
    prices = _prices({"A": [10.0]}, ["2025-01-02"])

    lifecycle = _build(
        executions,
        prices,
        as_of="2025-01-02 23:59",
        account_id=None,
    )

    assert len(lifecycle.episodes) == 2
    assert {item.account_id for item in lifecycle.episodes} == {"BROKER-A", "BROKER-B"}
    assert len({item.episode_id for item in lifecycle.episodes}) == 2
    quantities = {
        episode.account_id: _state(
            lifecycle,
            next(
                snapshot.position_state_ref
                for snapshot in lifecycle.snapshots
                if snapshot.episode_id == episode.episode_id
            ),
        ).quantity
        for episode in lifecycle.episodes
    }
    assert quantities == {"BROKER-A": 100.0, "BROKER-B": 200.0}


def test_same_input_has_deterministic_ids_ordering_and_classification():
    executions, prices = _full_lifecycle()

    first = _build(executions, prices, as_of="2025-01-05 23:59")
    second = _build(executions.copy(deep=True), prices.copy(deep=True), as_of="2025-01-05 23:59")

    assert first == second


def test_future_execution_and_price_do_not_change_past_lifecycle():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100.0, 10.0)]
    )
    prices = _prices({"A": [10.0, 11.0]}, ["2025-01-02", "2025-01-03"])
    baseline = _build(executions, prices, as_of="2025-01-03")
    future_execution = _executions(
        [("2025-01-04", "A", "SELL", 100.0, 999.0)]
    )
    future_execution["order_id"] = "FUTURE-ORDER"
    future_execution["execution_id"] = "FUTURE-EXECUTION"
    future_price = _prices({"A": [999.0]}, ["2025-01-04"])

    extended = _build(
        pd.concat([executions, future_execution], ignore_index=True),
        pd.concat([prices, future_price], ignore_index=True),
        as_of="2025-01-03",
    )

    assert extended == baseline
    current = _state(extended, extended.snapshots[0].position_state_ref)
    assert current.valuation_price == pytest.approx(11.0)
    assert current.valuation_at == pd.Timestamp("2025-01-03")


def test_future_unsupported_event_does_not_change_past_lifecycle():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100.0, 10.0)]
    )
    executions["event_type"] = "execution"
    prices = _prices({"A": [10.0]}, ["2025-01-02"])
    baseline = _build(executions, prices, as_of="2025-01-02 23:59")

    future_transfer = _executions(
        [("2025-01-03", "A", "BUY", 1.0, 10.0)]
    )
    future_transfer["order_id"] = "FUTURE-TRANSFER-ORDER"
    future_transfer["execution_id"] = "FUTURE-TRANSFER"
    future_transfer["event_type"] = "transfer"

    extended = _build(
        pd.concat([executions, future_transfer], ignore_index=True),
        prices,
        as_of="2025-01-02 23:59",
    )

    assert extended == baseline


def test_missing_execution_date_price_is_rejected_without_forward_fill():
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 100.0, 10.0),
            ("2025-01-03", "A", "BUY", 50.0, 11.0),
        ]
    )
    prices = _prices({"A": [10.0]}, ["2025-01-02"])

    with pytest.raises(PositionEpisodeError, match="Missing market prices for execution dates"):
        _build(executions, prices, as_of="2025-01-03")


def test_non_execution_event_is_not_classified_as_a_decision():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100.0, 10.0)]
    )
    executions["event_type"] = "transfer"
    prices = _prices({"A": [10.0]}, ["2025-01-02"])

    with pytest.raises(PositionEpisodeError, match="Corporate actions, transfers"):
        _build(executions, prices, as_of="2025-01-02")


def test_insufficient_decision_evidence_is_preserved_without_invalidating_episode():
    executions = _executions(
        [
            ("2025-01-02", "A", "BUY", 100.0, 10.0),
            ("2025-01-03", "A", "BUY", 50.0, 11.0),
        ]
    )
    prices = _prices({"A": [10.0, 11.0]}, ["2025-01-02", "2025-01-03"])
    evidence = create_evidence_record(
        subject_id=SUBJECT_ID,
        metric_id="test_follow_up",
        evidence_kind="decision_evidence",
        method_id="test_follow_up_v1",
        method_version="1",
        observation_start=pd.Timestamp("2025-01-03"),
        observation_end=pd.Timestamp("2025-01-03"),
        as_of=pd.Timestamp("2025-01-03"),
        value=None,
        numerator=None,
        denominator=None,
        observation_count=0,
        ci_lower=None,
        ci_upper=None,
        evidence_status="insufficient_evidence",
        evidence_reason="Follow-up window has not matured",
        provenance=(),
        data_tier="synthetic",
        calculation_code_version="position-episode-test-v1",
        limitations=("No mature follow-up yet.",),
        attributes={},
        identity_attributes={},
    )

    lifecycle = _build(
        executions,
        prices,
        as_of="2025-01-03",
        decision_evidence={"EXE-1": (evidence,)},
    )

    assert lifecycle.episodes[0].status == "open"
    add = lifecycle.decisions[1]
    assert add.evidence_refs == (evidence.evidence_id,)
    reference = lifecycle.evidence_references[0]
    assert reference.evidence_status == "insufficient_evidence"
    assert reference.evidence_reason == "Follow-up window has not matured"


def test_future_evidence_is_not_linked_to_historical_lifecycle():
    executions = _executions(
        [("2025-01-02", "A", "BUY", 100.0, 10.0)]
    )
    prices = _prices({"A": [10.0]}, ["2025-01-02"])
    future = create_evidence_record(
        subject_id=SUBJECT_ID,
        metric_id="future_metric",
        evidence_kind="decision_evidence",
        method_id="future_method",
        method_version="1",
        observation_start=pd.Timestamp("2025-01-04"),
        observation_end=pd.Timestamp("2025-01-04"),
        as_of=pd.Timestamp("2025-01-04"),
        value=1.0,
        numerator=None,
        denominator=None,
        observation_count=1,
        ci_lower=None,
        ci_upper=None,
        evidence_status="complete",
        evidence_reason=None,
        provenance=(),
        data_tier="synthetic",
        calculation_code_version="position-episode-test-v1",
        limitations=("Test only.",),
        attributes={},
        identity_attributes={},
    )

    lifecycle = _build(
        executions,
        prices,
        as_of="2025-01-02",
        decision_evidence={"EXE-0": (future,)},
    )

    assert lifecycle.decisions[0].evidence_refs == ()
    assert lifecycle.evidence_references == ()
