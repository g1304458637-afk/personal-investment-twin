"""Offline answer-target grounding, NOT model quality or live Agent acceptance.

Golden numbers are QA-only. Every actual value comes from existing builders;
no production prompt, answer renderer, financial formula or model is introduced.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.attribution.decision_outcome import (
    build_actual_outcomes,
    evaluate_historical_counterfactual,
)
from src.behavior.portfolio_concentration import build_portfolio_concentration_evidence
from src.data.csv_importer import load_normalized_csv
from src.episodes.position_episode import build_position_episode_lifecycle

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / "tests/fixtures/review_answer_targets_v1.json").read_text())


@pytest.fixture(scope="module")
def episode_inputs():
    source = TARGETS["sources"]["episode"]
    frame = load_normalized_csv(ROOT / source["executions"])
    market = pd.read_csv(ROOT / source["prices"])
    assert frame.symbol.eq(source["instrument"]).all()
    assert market.instrument.eq(source["market_instrument_in_csv"]).all()
    # Same explicit Synthetic identity mapping as the existing demo exporter.
    market = market.assign(instrument=source["instrument"])
    common = dict(subject_id=source["subject_id"], account_id=source["account_id"],
                  init_cash=source["init_cash"])
    cutoff = pd.Timestamp(source["as_of"])
    lifecycle = build_position_episode_lifecycle(
        frame, market, **common, as_of=cutoff, data_tier="synthetic",
        calculation_code_version="review_answer_targets_v1")
    return lifecycle, frame, market, common | {"analysis_as_of": cutoff}


def test_result_target_is_existing_replay_result(episode_inputs):
    lifecycle, frame, market, kwargs = episode_inputs
    result = build_actual_outcomes(lifecycle, frame, market, **kwargs)
    assert len(result.episode_outcomes) == 1
    actual = result.episode_outcomes[0].actual_result
    for key, expected in TARGETS["sources"]["episode"]["expected"].items():
        assert getattr(actual, key) == (pytest.approx(expected) if isinstance(expected, float) else expected)
    assert actual.source.source_kind == "vectorbt_position"


@pytest.mark.parametrize("target", TARGETS["comparisons"], ids=lambda c: c["id"])
def test_comparison_targets_replay_registered_scenarios(episode_inputs, target):
    lifecycle, frame, market, kwargs = episode_inputs
    decision, = [d for d in lifecycle.decisions if d.occurred_at == pd.Timestamp(target["decision_at"])]
    result = evaluate_historical_counterfactual(
        lifecycle, frame, market, **kwargs, decision_event_id=decision.decision_id,
        scenario_id=target["scenario_id"])
    assert result.feasibility_status == target["status"]
    assert result.scenario_id == target["scenario_id"]
    if target["status"] != "complete":
        assert result.first_conflicting_execution_id == target["conflicting_execution_id"]
        assert result.counterfactual_result is None
        assert result.comparison.pnl_difference is None
        return
    assert result.scenario_version == "2"
    assert result.valuation_observation_date == pd.Timestamp(target["valuation_date"])
    assert result.next_decision_at == pd.Timestamp(target["next_decision_at"])
    assert result.actual_result.valuation_at == result.counterfactual_result.valuation_at
    assert result.actual_result.valuation_at == pd.Timestamp(target["valuation_date"])
    assert result.actual_result.result_kind == "marked"
    assert result.actual_result.pnl == pytest.approx(target["actual_pnl"])
    assert result.counterfactual_result.pnl == pytest.approx(target["alternative_pnl"])
    assert result.comparison.pnl_difference == pytest.approx(target["pnl_difference"])
    assert result.downstream_order_policy == "exclude_next_and_later_episode_decisions"


def test_exposure_target_uses_separate_existing_multisecurity_fixture():
    source = TARGETS["sources"]["concentration"]
    result = build_portfolio_concentration_evidence(
        load_normalized_csv(ROOT / source["executions"]), pd.read_csv(ROOT / source["prices"]),
        init_cash=source["init_cash"])
    for key, expected in source["expected"].items():
        actual = getattr(result, key)
        if key == "as_of_time":
            actual = actual.isoformat()
        assert actual == (pytest.approx(expected) if isinstance(expected, float) else expected)
    assert result.synthetic_provenance_present
    assert "Cash is excluded" in result.limitation
    assert source["denominator"] == "risky_security_value_excluding_cash"
    assert TARGETS["sources"]["episode"]["instrument"] not in {c.symbol for c in result.weight_components}


def test_flat_episode_does_not_become_zero_hhi(episode_inputs):
    _, frame, market, kwargs = episode_inputs
    result = build_portfolio_concentration_evidence(frame, market, init_cash=kwargs["init_cash"])
    assert result.evidence_status == "insufficient_evidence"
    assert result.hhi is None
    assert result.top1_weight is None


@pytest.mark.parametrize("case", TARGETS["cases"], ids=lambda c: c["id"])
def test_manual_semantic_cases_have_valid_scope_and_explicit_rubrics(case):
    # Corpus integrity only: these assertions do NOT judge an Agent response.
    assert case["prompt"] and case["required_meanings"] and case["forbidden_claims"]
    assert case["source"] in TARGETS["sources"]
    assert set(case["comparison_ids"]) <= {c["id"] for c in TARGETS["comparisons"]}
    if case["category"] == "exposure":
        assert case["source"] == "concentration"
        assert not case["comparison_ids"]
    else:
        assert case["source"] == "episode"


def test_targets_are_qa_only_and_cover_three_question_families():
    assert TARGETS["purpose"] == "offline_reference_not_production_answer"
    assert TARGETS["data_tier"] == "synthetic"
    assert TARGETS["model_qa_status"] == "not_run"
    assert {c["category"] for c in TARGETS["cases"]} == {"result", "operation", "exposure"}
    assert len({c["id"] for c in TARGETS["cases"]}) == len(TARGETS["cases"])
