from dataclasses import asdict
import hashlib
import json

import pandas as pd
import pytest

from src.attribution.decision_outcome import evaluate_historical_counterfactual
from src.presentation.runtime_episode import json_value
from test_decision_outcome import _executions, _prices, _lifecycle, SUBJECT_ID, ACCOUNT_ID, INITIAL_CASH


def case(*, same_time=False):
    trades = _executions([
        ("2025-01-06 09:35", "A", "BUY", 100, 10),
        ("2025-01-13 10:05" if same_time else "2025-01-10 10:00", "A", "BUY", 50, 11),
        ("2025-01-13 10:05", "A", "SELL", 30, 12),
        ("2025-01-20 10:00", "A", "SELL", 120, 12),
    ], fees=[1, 1, 1, 1])
    trades["execution_sequence"] = [1, 2, 3, 4]
    prices = _prices({"A": [10, 11, 12, 12]}, ["2025-01-06", "2025-01-10", "2025-01-13", "2025-01-20"])
    return trades, prices, _lifecycle(trades, prices, as_of="2025-01-20 10:00")


def evaluate(trades, prices, lifecycle, version):
    return evaluate_historical_counterfactual(
        lifecycle, trades, prices, subject_id=SUBJECT_ID, account_id=ACCOUNT_ID,
        decision_event_id=lifecycle.decisions[1].decision_id,
        scenario_id=f"omit_event_until_next_decision_v{version}",
        analysis_as_of=lifecycle.as_of, init_cash=INITIAL_CASH,
    )


def test_v1_frozen_fixture_bytes():
    result = evaluate(*case(), 1)
    payload = json.dumps(json_value(result), sort_keys=True, separators=(",", ":")).encode()
    assert result.actual_result.pnl == pytest.approx(248)
    assert result.counterfactual_result.pnl == pytest.approx(199)
    assert hashlib.sha256(payload).hexdigest() == "f05c16c196837176173aa2f270184dd90f2c5898d654ec6bf83c00662f052462"


@pytest.mark.parametrize("same_time", [False, True])
def test_v2_prior_mark_canonical_scope_and_hand_results(same_time):
    trades, prices, lifecycle = case(same_time=same_time)
    result = evaluate(trades.iloc[::-1], prices, lifecycle, 2)
    assert result.feasibility_status == "complete"
    assert result.scenario_version == "2"
    assert result.next_decision_at == pd.Timestamp("2025-01-13 10:05")
    # Friday is the actual prior observation, not an invented Sunday quote.
    assert result.valuation_observation_date == pd.Timestamp("2025-01-10")
    assert result.actual_result.valuation_price == result.counterfactual_result.valuation_price == 11
    assert result.actual_result.valuation_at == result.counterfactual_result.valuation_at == pd.Timestamp("2025-01-10")
    assert result.actual_result.source.execution_refs == ("EXE-0", "EXE-1")
    assert result.counterfactual_result.source.execution_refs == ("EXE-0",)
    # 150 shares marked 11, recorded buys 1000 + 550, fees 2; omit add: 100 shares, fee 1.
    assert result.actual_result.pnl == pytest.approx(98)
    assert result.counterfactual_result.pnl == pytest.approx(99)
    assert result.comparison.pnl_difference == pytest.approx(1)
    changed = prices.copy()
    changed.loc[changed.date == "2025-01-13", "close"] = 999
    assert asdict(evaluate(trades, changed, lifecycle, 2)) == asdict(result)


def test_v2_missing_prior_is_insufficient():
    trades, prices, lifecycle = case()
    result = evaluate(trades, prices.loc[prices.date >= "2025-01-13"], lifecycle, 2)
    assert result.feasibility_status == "insufficient_counterfactual_data"
    assert result.actual_result is result.counterfactual_result is None


def test_phase_default_v2_same_timestamp_whole_intervention():
    from src.path.analysis import build_episode_path_analysis
    trades, prices, lifecycle = case(same_time=True)
    result = build_episode_path_analysis(lifecycle, trades, prices,
        episode_id=lifecycle.episodes[0].episode_id, init_cash=INITIAL_CASH)
    phase = next(item for item in result.phase_counterfactuals if item.intervention.changed_execution_refs == ("EXE-1",))
    assert phase.scenario_id == "omit_decision_phase_until_next_decision_v2"
    assert phase.actual_result.source.execution_refs == ("EXE-0", "EXE-1")
    assert phase.counterfactual_result.source.execution_refs == ("EXE-0",)
    assert phase.actual_result.pnl == pytest.approx(98)
    assert phase.counterfactual_result.pnl == pytest.approx(99)


def test_historical_context_never_includes_future_post_exit_observation():
    from src.path.analysis import build_episode_path_analysis
    trades, prices, lifecycle = case()
    future = _prices({"A": [20, 30]}, ["2025-01-21", "2025-01-22"])
    def build(rows):
        return build_episode_path_analysis(lifecycle, trades, rows,
            episode_id=lifecycle.episodes[0].episode_id, init_cash=INITIAL_CASH)
    original = build(prices)
    changed = build(pd.concat([prices, future], ignore_index=True))
    assert asdict(original) == asdict(changed)
    assert changed.market_path.post_exit_context.observations == ()
