"""Reconciled product scenario inputs; no alternative financial engine."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_showcase_demo import export_bytes
from src.behavior.replay_state import prepare_behavior_replay
from src.demo import showcase
from src.demo.showcase_runtime import load_showcase_review
from src.episodes.position_episode import build_position_episode_lifecycle
from toujing_core_runtime.product import ProductRuntime


@pytest.fixture(scope="module")
def payload_bytes():
    return export_bytes()


@pytest.fixture(scope="module")
def payload(payload_bytes):
    return json.loads(payload_bytes)


def test_complete_market_inputs_are_simulated_deterministic_and_not_mutated():
    trades, prices = showcase.showcase_inputs()
    old_trades, old_prices = trades.copy(deep=True), prices.copy(deep=True)
    again, market_again = showcase.showcase_inputs()
    pd.testing.assert_frame_equal(trades, again)
    pd.testing.assert_frame_equal(prices, market_again)
    assert len(trades) == 20
    assert len(prices.date.unique()) == 260
    assert prices.is_synthetic.all()
    assert prices.data_source.eq(showcase.VERSION).all()
    assert (prices.low <= prices[["open", "close"]].min(axis=1)).all()
    assert (prices.high >= prices[["open", "close"]].max(axis=1)).all()
    assert prices.volume.gt(0).all()
    for execution in trades.itertuples():
        bar = prices[(prices.instrument == execution.symbol) & (prices.date == execution.event_time.normalize())].iloc[0]
        assert bar.low <= execution.executed_price <= bar.high
    prepare_behavior_replay(trades, prices, init_cash=showcase.INITIAL_CASH)
    pd.testing.assert_frame_equal(trades, old_trades)
    pd.testing.assert_frame_equal(prices, old_prices)


def test_ledger_hand_expected_values_and_all_pages_have_one_source(payload):
    entries = payload["position_episode_demo"]["entries"]
    assert len(entries) == 5
    assert {e["episode"]["subject_id"] for e in entries} == {showcase.SUBJECT_ID}
    assert {e["episode"]["account_id"] for e in entries} == {showcase.ACCOUNT_ID}
    assert [e["episode"]["status"] for e in entries].count("closed") == 2
    closed = {e["episode"]["instrument_id"]: e["outcome_story"]["episode_outcome"]["actual_result"]["pnl"] for e in entries if e["episode"]["status"] == "closed"}
    # Explicit ledger arithmetic, independently specified in the source design:
    # growth sells 11640 - buys 12240 - fees30 = -630;
    # industrial sells20200 - buys16200 - fees20 = 3980.
    assert closed == pytest.approx({"SYN_GROWTH": -630.0, "SYN_VALUE": 3980.0})
    before = payload["pretrade_demo"]["before"]
    after = payload["pretrade_demo"]["after"]
    assert before["cash"] == pytest.approx(58170)
    assert before["portfolio_value"] == pytest.approx(114330)
    assert before["symbol_quantity"] == 900
    assert after["cash"] == pytest.approx(53845)
    assert after["portfolio_value"] == pytest.approx(114325)
    assert after["symbol_quantity"] == 1200
    assert payload["pretrade_demo"]["peer_context"] is None
    comparison = payload["comparison_research"]
    main = next(a for a in comparison["accounts"] if a["account_id"] == showcase.ACCOUNT_ID)
    assert main["periods"]["full"]["allocation"]["cash"] == before["cash"]
    assert main["periods"]["full"]["allocation"]["portfolio_value"] == before["portfolio_value"]
    assert payload["twin"]["current_snapshot"]["subject_id"] == showcase.SUBJECT_ID
    assert {r["subject_id"] for r in payload["evidence_records"]} == {showcase.SUBJECT_ID}
    assert len(payload["evidence_records"]) == 8
    assert all(r["evidence_status"] == "complete" for r in payload["evidence_records"])


def test_every_episode_has_matching_ohlcv_not_an_unrelated_market(payload):
    entries = payload["position_episode_demo"]["entries"]
    charts = {c["position_episode_demo"]["default_episode_id"]: c for c in payload["charts"]}
    assert set(charts) == {e["episode"]["episode_id"] for e in entries}
    for entry in entries:
        chart = charts[entry["episode"]["episode_id"]]
        assert chart["market"]["replay_instrument_id"] == entry["episode"]["instrument_id"]
        assert chart["market"]["price_basis"] == "synthetic_unadjusted"
        assert chart["position_episode_demo"]["entries"][0] == entry
        closes = {b["date"]: b["close"] for b in chart["market"]["bars"]}
        for point in entry["price_points"]:
            assert point["price"] == closes[point["observed_at"][:10]]


def test_showcase_reference_is_same_account_in_both_comparison_modes(payload):
    pair = payload["same_stock_compare_demo"]
    assert pair["a"]["episode"]["subject_id"] == showcase.SUBJECT_ID
    assert pair["b"]["episode"]["subject_id"] == showcase.REFERENCE_SUBJECT
    assert pair["a"]["outcome"]["actual_result"]["pnl"] == pytest.approx(-630)
    assert pair["b"]["outcome"]["actual_result"]["pnl"] == pytest.approx(525)
    assert set(payload["comparison_research"]["comparisons"]["professional"]) == {showcase.REFERENCE_SUBJECT}
    for point in pair["market_observations"]:
        assert point["data_source"] == showcase.VERSION


def test_all_main_episode_agent_contexts_resolve_only_their_owned_execution_refs(payload):
    for entry in payload["position_episode_demo"]["entries"]:
        episode = entry["episode"]
        own, frame, _, identity = load_showcase_review(showcase.SUBJECT_ID, showcase.ACCOUNT_ID, episode["episode_id"])
        assert own.episode.execution_refs == tuple(episode["execution_refs"])
        assert own.outcome.actual_result.pnl == pytest.approx(entry["outcome_story"]["episode_outcome"]["actual_result"]["pnl"])
        assert len(frame) == 20  # full account replay, not a cropped symbol engine
        assert identity["display_episode_id"] == episode["episode_id"]
        with pytest.raises(ValueError, match="scope"):
            load_showcase_review(showcase.REFERENCE_SUBJECT, showcase.REFERENCE_SUBJECT, episode["episode_id"])


def test_export_byte_deterministic_and_published_artifact_matches(payload_bytes):
    assert export_bytes() == payload_bytes
    assert (Path(__file__).resolve().parents[1] / "apps/desktop/src/generated/showcase-demo.json").read_bytes() == payload_bytes


def test_runtime_context_accepts_both_registered_comparison_sides_without_real_accounts(payload, tmp_path):
    product = ProductRuntime(tmp_path / "showcase-review.sqlite3")
    try:
        service = product.review_runtime()
        for side in ("A", "B"):
            episode = payload["same_stock_compare_demo"][side.lower()]["episode"]
            params = {key: episode[key] for key in ("subject_id", "account_id", "episode_id")}
            params.update(data_mode="synthetic_showcase", compare_pair=True, pair_side=side)
            context = service.context(params)
            assert context["scope"]["subject_id"] == episode["subject_id"]
            assert context["scope"]["account_id"] == episode["account_id"]
            assert context["scope"]["episode_id"] == episode["episode_id"]
            assert context["comparison"]["a"]["episode"]["subject_id"] == episode["subject_id"]
            assert context["identity_mapping"]["canonical_episode_id"] == episode["episode_id"]
            assert context["records"]
            with pytest.raises(ValueError):
                service.context(params | {"episode_id": "foreign-episode"})
        assert product.repo.list_accounts() == []
    finally:
        product.close()
