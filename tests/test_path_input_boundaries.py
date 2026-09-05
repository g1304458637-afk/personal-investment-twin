from dataclasses import asdict
import hashlib
import json

import pandas as pd
import pytest

from src.attribution.decision_outcome import OutcomeAttributionError, evaluate_omit_executions_counterfactual
from src.path.counterfactual import PHASE_LOCAL_SCENARIO, evaluate_phase_full_counterfactual
from src.path.analysis import build_episode_path_analysis
from src.path.market_path import instrument_observations, EpisodePathError
from src.path.market_path import DailyMarketObservation, build_market_path_segments
from src.presentation.runtime_episode import json_value
from test_episode_path_analysis import _complex_path, _lifecycle, _prices, _executions, SUBJECT, ACCOUNT, CASH


@pytest.mark.parametrize("mutation", ["duplicate", "conflicting_value", "source", "version", "type", "null_source"])
def test_market_series_rejects_conflicts_instead_of_inventing_movement(mutation):
    rows = _prices(["2025-01-02", "2025-01-03"], [10, 11])
    if mutation in {"duplicate", "conflicting_value"}:
        rows.loc[1, "date"] = "2025-01-02"
        rows.loc[1, "close"] = 10 if mutation == "duplicate" else 20
    elif mutation == "source":
        rows.loc[1, "data_source"] = "different_source"
    elif mutation == "version":
        rows.loc[1, "data_version"] = "v2"
    elif mutation == "type":
        rows["price_type"] = "unknown"
    else:
        rows.loc[1, "data_source"] = None
    with pytest.raises(EpisodePathError):
        instrument_observations(rows, instrument_id="A")


def test_invalid_pre_entry_context_is_insufficient_not_100_percent():
    trades = _executions([("2025-01-06", "A", "BUY", 100, 10), ("2025-01-10", "A", "SELL", 100, 11)])
    valid = _prices(["2025-01-06", "2025-01-10"], [10, 11])
    lifecycle = _lifecycle(trades, valid, as_of="2025-01-10")
    rows = pd.concat([_prices(["2025-01-02", "2025-01-02"], [10, 20]), valid])
    result = build_episode_path_analysis(lifecycle, trades, rows,
        episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH, include_phase_counterfactuals=False)
    assert result.market_path.pre_entry_context_status == "insufficient"
    assert result.market_path.pre_entry_context.price_return is None
    assert any("conflict" in item.lower() for item in result.market_path.limitations)


@pytest.mark.parametrize("refs", [(), ("NONEXISTENT",), ("EXE-1", "EXE-1"), ("EXE-5",)])
def test_multi_omit_unknown_duplicate_and_beyond_horizon_fail_closed(refs):
    trades, prices = _complex_path()
    lifecycle = _lifecycle(trades, prices, as_of="2025-06-11")
    with pytest.raises(OutcomeAttributionError):
        evaluate_omit_executions_counterfactual(lifecycle, trades, prices,
            subject_id=SUBJECT, account_id=ACCOUNT, analysis_as_of=lifecycle.as_of,
            init_cash=CASH, episode_id=lifecycle.episodes[0].episode_id,
            anchor_decision_event_id=lifecycle.decisions[1].decision_id,
            changed_execution_refs=refs, scenario=PHASE_LOCAL_SCENARIO,
            evaluation_end=lifecycle.decisions[2].occurred_at,
            include_evaluation_end_executions=False)


def test_phase_full_omit_reports_exact_conflicting_downstream_execution():
    trades, prices = _complex_path()
    lifecycle = _lifecycle(trades, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(lifecycle, trades, prices,
        episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH)
    phase = next(item for item in analysis.phases if item.phase_type == "scaling_in")
    result = evaluate_phase_full_counterfactual(lifecycle, trades, prices,
        episode=lifecycle.episodes[0], phase=phase, analysis_as_of=lifecycle.as_of, init_cash=CASH)
    assert result.feasibility_status == "infeasible_downstream_execution"
    # Removing both adds leaves 400 shares: sell 300 legal, next sell 400 illegal.
    assert result.first_conflicting_execution_id == "EXE-4"
    assert result.actual_result is result.counterfactual_result is None


@pytest.mark.parametrize("n,size,digest", [
    (1000, 443438, "073e71d7690e15cbdc95d44bad45a1eb50df808bbf0f79602eb486a5202cc019"),
    (2000, 888437, "706e53967594ca0c06a9db3bb82562448ab9905a24efbd9991998fc079b056c4"),
    (4000, 1778437, "d59b1351437a00957ee91a950488a497f03937415a789ee8e8a165ed963eece8"),
])
def test_segment_scan_matches_preoptimization_bytes_and_actual_serialized_size(n, size, digest):
    observations = tuple(DailyMarketObservation(t, 10.0 if i % 2 == 0 else 20.0,
        "A", "synthetic", "bench", "v1") for i, t in enumerate(pd.date_range("2000-01-01", periods=n)))
    result = build_market_path_segments(observations, episode_id="bench")
    raw = json.dumps(json_value(result), sort_keys=True, separators=(",", ":")).encode()
    assert len(raw) == size
    assert hashlib.sha256(raw).hexdigest() == digest


@pytest.mark.parametrize("subject,account", [("other-subject", ACCOUNT), (SUBJECT, "other-account")])
def test_multi_omit_foreign_owner_fails_closed(subject, account):
    trades, prices = _complex_path()
    lifecycle = _lifecycle(trades, prices, as_of="2025-06-11")
    with pytest.raises(OutcomeAttributionError):
        evaluate_omit_executions_counterfactual(lifecycle, trades, prices,
            subject_id=subject, account_id=account, analysis_as_of=lifecycle.as_of,
            init_cash=CASH, episode_id=lifecycle.episodes[0].episode_id,
            anchor_decision_event_id=lifecycle.decisions[1].decision_id,
            changed_execution_refs=("EXE-1",), scenario=PHASE_LOCAL_SCENARIO,
            evaluation_end=lifecycle.decisions[2].occurred_at,
            include_evaluation_end_executions=False)


def test_multi_omit_cannot_move_registered_horizon_to_include_future_ref():
    trades, prices = _complex_path()
    lifecycle = _lifecycle(trades, prices, as_of="2025-06-11")
    with pytest.raises(OutcomeAttributionError, match="horizon"):
        evaluate_omit_executions_counterfactual(lifecycle, trades, prices,
            subject_id=SUBJECT, account_id=ACCOUNT, analysis_as_of=lifecycle.as_of,
            init_cash=CASH, episode_id=lifecycle.episodes[0].episode_id,
            anchor_decision_event_id=lifecycle.decisions[1].decision_id,
            changed_execution_refs=("EXE-1", "EXE-2"), scenario=PHASE_LOCAL_SCENARIO,
            evaluation_end=lifecycle.decisions[2].occurred_at,
            include_evaluation_end_executions=False)
