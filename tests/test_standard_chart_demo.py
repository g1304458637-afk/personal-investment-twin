from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from scripts.export_standard_chart_demo import (
    ACCOUNT_ID,
    EXPECTED_NET_PNL,
    EXECUTIONS_CSV,
    INITIAL_CASH,
    REPLAY_INSTRUMENT_ID,
    SOURCE_CSV,
    SOURCE_METADATA,
    SUBJECT_ID,
    _adjusted_market_frame,
    _read_metadata,
    _simulated_executions,
    _verified_source_frame,
    build_export,
    export_bytes,
)
from scripts.export_desktop_demo_evidence import _json_value
from src.attribution.decision_outcome import build_actual_outcomes
from src.episodes.position_episode import build_position_episode_lifecycle


def test_pinned_source_checksum_and_adjusted_ohlc_are_preserved():
    metadata = _read_metadata()
    assert hashlib.sha256(SOURCE_CSV.read_bytes()).hexdigest() == metadata["source_sha256"]
    assert metadata["license"] == "MIT"
    source = _verified_source_frame(metadata)
    market, bars = _adjusted_market_frame(source, metadata)

    assert len(source) == len(market) == len(bars) == 252
    assert [item["date"] for item in bars] == sorted(item["date"] for item in bars)
    assert source["Date"].is_unique
    assert source[["AAPL.Open", "AAPL.High", "AAPL.Low", "AAPL.Close", "AAPL.Adjusted"]].gt(0).all().all()
    assert source["AAPL.Volume"].ge(0).all()
    assert market["close"].tolist() == source["AAPL.Adjusted"].tolist()
    source_row = source.iloc[0]
    bar = bars[0]
    adjustment = source_row["AAPL.Adjusted"] / source_row["AAPL.Close"]
    assert bar["close"] == pytest.approx(source_row["AAPL.Adjusted"])
    assert bar["open"] == pytest.approx(source_row["AAPL.Open"] * adjustment)
    assert bar["high"] == pytest.approx(source_row["AAPL.High"] * adjustment)
    assert bar["low"] == pytest.approx(source_row["AAPL.Low"] * adjustment)
    assert bar["volume"] == int(source_row["AAPL.Volume"])
    assert bar["amount"] is None
    assert market["is_synthetic"].eq(False).all()
    assert market["price_type"].eq("adjusted_close").all()


def test_simulated_ledger_is_ordered_closed_and_uses_only_source_adjusted_marks():
    metadata = _read_metadata()
    market, _ = _adjusted_market_frame(_verified_source_frame(metadata), metadata)
    executions = _simulated_executions(market)

    assert tuple(executions["side"]) == ("BUY", "BUY", "BUY", "SELL", "SELL", "SELL")
    assert executions["event_time"].is_monotonic_increasing
    assert executions["event_time"].dt.strftime("%H:%M:%S").eq("16:00:00").all()
    assert executions["subject_id"].eq(SUBJECT_ID).all()
    assert executions["account_id"].eq(ACCOUNT_ID).all()
    assert executions["symbol"].eq(REPLAY_INSTRUMENT_ID).all()
    assert executions["executed_quantity"].iloc[:3].sum() == executions["executed_quantity"].iloc[3:].sum()
    marks = market.set_index("date")["close"]
    assert all(
        row.executed_price == pytest.approx(marks.loc[row.market_date])
        for row in executions.itertuples(index=False)
    )


def test_export_is_deterministic_and_delegates_episode_outcome_to_existing_builders():
    first = export_bytes()
    second = export_bytes()
    assert first == second
    payload = json.loads(first)
    assert payload["schema_version"] == "1"
    assert payload["market"]["instrument_id"] == "AAPL"
    assert payload["market"]["replay_instrument_id"] == REPLAY_INSTRUMENT_ID
    assert payload["market"]["price_basis"] == "source_adjusted"
    assert "simulated" in payload["market"]["provenance"].lower()
    entry = payload["position_episode_demo"]["entries"][0]
    assert entry["instrument"] == {
        "instrument_id": REPLAY_INSTRUMENT_ID,
        "display_name": "Apple · AAPL",
        "currency": "USD",
        "is_synthetic": True,
        "data_tier": "synthetic",
    }
    assert entry["episode"]["status"] == "closed"
    assert [item["decision_type"] for item in entry["decisions"]] == [
        "open_position", "add_position", "add_position", "reduce_position", "reduce_position", "close_position"
    ]

    metadata = _read_metadata()
    market, _ = _adjusted_market_frame(_verified_source_frame(metadata), metadata)
    executions = _simulated_executions(market)
    lifecycle = build_position_episode_lifecycle(
        executions, market, subject_id=SUBJECT_ID, account_id=ACCOUNT_ID,
        as_of=pd.Timestamp(market["date"].max()) + pd.Timedelta(hours=23, minutes=59),
        init_cash=INITIAL_CASH, data_tier="synthetic", calculation_code_version="standard-chart-demo-v1",
    )
    actual = build_actual_outcomes(
        lifecycle, executions, market, subject_id=SUBJECT_ID, account_id=ACCOUNT_ID,
        analysis_as_of=lifecycle.as_of, init_cash=INITIAL_CASH,
    )
    assert entry["outcome_story"]["episode_outcome"]["actual_result"] == _json_value(
        actual.episode_outcomes[0].actual_result
    )
    assert actual.episode_outcomes[0].actual_result.pnl == pytest.approx(EXPECTED_NET_PNL)
    assert entry["outcome_story"]["episode_outcome"]["actual_result"]["source"]["source_kind"] == "vectorbt_position"


def test_export_has_no_future_market_observations_in_episode_story():
    payload = build_export()
    entry = payload["position_episode_demo"]["entries"][0]
    analysis_as_of = entry["outcome_story"]["episode_outcome"].analysis_as_of.normalize()
    assert all(point["observed_at"].normalize() <= analysis_as_of for point in entry["price_points"])
    post_exit = [point for point in entry["price_points"] if point["segment"] == "post_exit"]
    assert post_exit
    assert all(
        point["observed_at"].normalize() > entry["episode"].closed_at.normalize()
        for point in post_exit
    )
    assert EXECUTIONS_CSV.parent == SOURCE_CSV.parent == SOURCE_METADATA.parent
