from dataclasses import replace

import pandas as pd
import pytest

from src.compare.demo import AS_OF, INSTRUMENT, build_pair, pair_inputs
from src.compare.same_stock import build_episode_compare_facts, compare_same_stock
from src.core.canonical_execution import instrument_ref
from src.evidence.contracts import canonical_json_bytes
from src.presentation.runtime_episode import json_value


@pytest.fixture(scope="module")
def pair():
    return build_pair()


def build(frame, prices, *, who="A", as_of=AS_OF, cash=100_000):
    return build_episode_compare_facts(
        frame, prices, subject_id=f"SYN_COMPARE_{who}", account_id=f"SYN_COMPARE_ACCOUNT_{who}",
        instrument=INSTRUMENT, as_of=as_of, init_cash=cash, data_tier="synthetic",
    )


def test_pair_hand_calculation_and_authoritative_results(pair):
    # A: sales 950 + 2200, buys 1000 + 1200 + 1300, five explicit fees.
    # B: sales 520 + 460 + 660, buys 1000 + 440, five explicit fees.
    assert pair.status == "comparable"
    assert pair.a.outcome.actual_result.pnl == pytest.approx(-355)
    assert pair.b.outcome.actual_result.pnl == pytest.approx(195)
    assert pair.a.outcome.actual_result.result_kind == "realized"
    assert pair.b.outcome.actual_result.result_kind == "realized"
    assert pair.a.outcome.actual_result.source.source_kind == "vectorbt_position"
    assert len(pair.a.decisions) == len(pair.b.decisions) == 5
    assert pair.a.episode.subject_id != pair.b.episode.subject_id
    assert pair.a.instrument == pair.b.instrument
    assert pair.a.episode.data_tier == pair.b.episode.data_tier == "synthetic"


def test_deterministic_and_input_immutable(pair):
    frames, prices = pair_inputs()
    saved, saved_prices = frames["A"].copy(deep=True), prices.copy(deep=True)
    rebuilt = build(frames["A"].sample(frac=1, random_state=42), prices)
    assert rebuilt == pair.a
    pd.testing.assert_frame_equal(frames["A"], saved)
    pd.testing.assert_frame_equal(prices, saved_prices)
    assert canonical_json_bytes(json_value(compare_same_stock(rebuilt, pair.b))) == canonical_json_bytes(json_value(pair))


def test_identity_swap_and_identical_facts(pair):
    swapped = compare_same_stock(pair.b, pair.a)
    assert swapped.status == pair.status
    assert swapped.market_observations == pair.market_observations
    assert [(x.dimension, x.a_value, x.b_value) for x in swapped.differences] == [
        (x.dimension, x.b_value, x.a_value) for x in pair.differences]
    assert compare_same_stock(pair.a, pair.a).differences == ()


def test_currency_market_and_scope_fail_closed(pair):
    wrong_currency = replace(pair.b, instrument=replace(pair.b.instrument, currency="USD"))
    assert compare_same_stock(pair.a, wrong_currency).status == "unavailable"
    other_market = instrument_ref(local_symbol=INSTRUMENT.local_symbol, market="OTHER",
                                  security_type="equity", currency="CNY")
    assert compare_same_stock(pair.a, replace(pair.b, instrument=other_market)).status == "unavailable"
    forged = replace(pair.b, outcome=replace(pair.b.outcome, account_id="OTHER"))
    assert compare_same_stock(pair.a, forged).status == "unavailable"
    frames, prices = pair_inputs()
    frames["A"].loc[0, "subject_id"] = "OTHER"
    with pytest.raises(ValueError, match="归属"):
        build(frames["A"], prices)


def test_conflicting_provenance_and_missing_shared_observations(pair):
    market = pair.b.path.market_path
    window = market.episode_market_path
    def with_observations(obs):
        return replace(pair.b, path=replace(pair.b.path, market_path=replace(
            market, episode_market_path=replace(window, observations=obs))))
    conflict = with_observations(tuple(replace(p, data_version="2") for p in window.observations))
    assert compare_same_stock(pair.a, conflict).status == "unavailable"
    gap = compare_same_stock(pair.a, with_observations(window.observations[::2]))
    assert gap.status == "partially_comparable"
    assert gap.market_observations == window.observations[::2]
    assert compare_same_stock(pair.a, with_observations(())).status == "unavailable"
    assert compare_same_stock(pair.a, with_observations(window.observations[:1])).status == "partially_comparable"


def test_non_overlap_and_analysis_cutoff(pair):
    late = replace(pair.b, episode=replace(pair.b.episode, opened_at=AS_OF + pd.Timedelta(days=1)))
    assert compare_same_stock(pair.a, late).status == "unavailable"
    assert compare_same_stock(pair.a, replace(pair.b, as_of=AS_OF - pd.Timedelta(days=1))).status == "unavailable"


def test_normalized_shape_is_not_risk_and_copies_authoritative_states(pair):
    for facts, shape in ((pair.a, pair.a_position_shape), (pair.b, pair.b_position_shape)):
        assert max(p.normalized_quantity for p in shape) == 1
        for p, source in zip(shape, facts.path.position_path.points):
            assert (p.quantity, p.average_cost, p.state_ref) == (source.quantity, source.average_cost, source.state_id)
        assert len(shape) == len(facts.path.position_path.points)
    assert any("不等于账户风险" in s for s in pair.limitations)
    frames, prices = pair_inputs()
    assert build(frames["A"], prices, cash=200_000).path.position_path == pair.a.path.position_path


def test_open_closed_and_both_open(pair):
    frames, prices = pair_inputs()
    a = build(frames["A"].iloc[:-1], prices)
    b = build(frames["B"].iloc[:-1], prices, who="B")
    assert a.outcome.actual_result.result_kind == b.outcome.actual_result.result_kind == "marked"
    assert compare_same_stock(a, b).status == "comparable"
    assert compare_same_stock(a, pair.b).status == "partially_comparable"
    assert compare_same_stock(a, pair.b).b.outcome.actual_result.result_kind == "realized"


def test_same_timestamp_preserves_canonical_sequence():
    frames, prices = pair_inputs()
    rows = frames["A"].copy()
    rows.loc[2, "event_time"] = rows.loc[1, "event_time"]
    result = build(rows.sample(frac=1, random_state=2), prices)
    assert [d.execution_id for d in result.decisions] == frames["A"].execution_id.tolist()
    assert result.decisions[1].after.quantity == 200
    assert result.decisions[2].before.quantity == 200
    assert result.decisions[2].after.quantity == 300


def test_missing_execution_day_price_is_not_filled():
    frames, prices = pair_inputs()
    with pytest.raises(ValueError):
        build(frames["A"], prices.iloc[1:])


def test_future_facts_do_not_change_past():
    frames, prices = pair_inputs()
    cutoff = pd.Timestamp("2025-01-07 16:00")
    past = build(frames["A"], prices, as_of=cutoff)
    future = prices.copy()
    future.loc[future.date > cutoff, "close"] = 99.0
    assert build(frames["A"], future, as_of=cutoff) == past
    assert build(frames["A"].iloc[:3], prices, as_of=cutoff) == past


def test_differences_resolve_to_both_scopes_and_market(pair):
    assert {d.dimension for d in pair.differences} == {"add_position", "reduce_position"}
    for fact in pair.differences:
        assert fact.a_decision_refs or fact.b_decision_refs
        assert pair.a.outcome.outcome_id in fact.fact_refs
        assert pair.b.outcome.outcome_id in fact.fact_refs
        assert fact.market_observation_refs
        assert set(fact.a_decision_refs) <= set(pair.a.episode.decision_refs)
        assert set(fact.b_decision_refs) <= set(pair.b.episode.decision_refs)
