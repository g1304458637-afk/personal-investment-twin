"""Contract tests for the staging-only Decision Lens implementation."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pandas as pd


MODULE = Path(__file__).parents[1] / "src/lenses/history.py"
SPEC = importlib.util.spec_from_file_location("staged_decision_lenses", MODULE)
assert SPEC and SPEC.loader
LENSES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LENSES)
evaluate = LENSES.evaluate_episode_lenses


def _inputs(*, side="BUY", quantity_before=0.0, average_cost=None, price=120.0, market_date="2025-02-01"):
    days = pd.bdate_range("2025-01-02", periods=25)
    closes = list(range(100, 125))
    prices = pd.DataFrame(dict(date=days, instrument="AAA", close=closes,
        price_type="unadjusted_close", data_source="fixture", data_version="1", is_synthetic=True))
    entry = {"episode": {"episode_id": "ep", "subject_id": "subject", "account_id": "account",
             "instrument_id": "AAA", "data_tier": "synthetic"},
        "states_by_ref": {"before": {"state_id": "before", "subject_id": "subject", "account_id": "account",
                           "instrument_id": "AAA", "boundary": "before_execution", "execution_id": "x1",
                           "quantity": quantity_before, "average_cost": average_cost}},
        "decisions": [{"decision_id": "d1", "episode_id": "ep", "execution_id": "x1",
                        "state_before_ref": "before", "occurred_at": "2025-02-01T09:30:00+08:00",
                        "side": side, "executed_quantity": 2, "execution_price": price}]}
    executions = pd.DataFrame([dict(execution_id="x1", market_date=market_date, side=side,
        quantity=2, price=price, instrument="AAA", subject_id="subject", account_id="account")])
    return entry, prices, executions


def _checks(report, method):
    return next(item for item in report["methods"] if item["id"] == method)["checks"]


def test_report_contract_and_determinism_do_not_mutate_inputs():
    entry, prices, executions = _inputs()
    entry_before, prices_before, executions_before = copy.deepcopy(entry), prices.copy(deep=True), executions.copy(deep=True)
    first = evaluate(entry, prices, executions)
    second = evaluate(entry, prices, executions)
    assert first == second
    assert first["schema_version"] == "decision_lens.v1"
    assert [m["id"] for m in first["methods"]] == ["trend_ma20", "closing_breakout20", "cost_addition"]
    assert all(len(m["checks"]) == 1 for m in first["methods"])
    assert entry == entry_before and prices.equals(prices_before) and executions.equals(executions_before)
    assert len(_checks(first, "trend_ma20")[0]["input_fingerprint"]) == 64


def test_prior_daily_window_and_future_changes_cannot_change_a_past_check():
    entry, prices, executions = _inputs()
    report = evaluate(entry, prices, executions)
    check = _checks(report, "trend_ma20")[0]
    assert check["observed_through"] == "2025-01-31"
    changed = prices.copy()
    # Future invalid values, duplicate dates and changed basis cannot taint a
    # past decision because validation begins after the strict date cutoff.
    changed.loc[len(changed)] = ["2030-01-01", "AAA", -1, "adjusted_close", "other", "2", False]
    changed.loc[len(changed)] = ["2030-01-01", "AAA", float("nan"), "total_return", "other", "2", False]
    changed_report = evaluate(entry, changed, executions)
    assert _checks(changed_report, "trend_ma20")[0] == check


def test_breakout_requires_twenty_strictly_preceding_closes_and_exact_scope():
    entry, prices, executions = _inputs()
    prices.loc[prices["date"] >= pd.Timestamp("2025-01-30"), "instrument"] = "OTHER"  # exact instrument filtering removes prefix bars
    check = _checks(evaluate(entry, prices, executions), "closing_breakout20")[0]
    assert check["verdict"] == "insufficient"
    entry, prices, executions = _inputs()
    prices.loc[prices["date"] < pd.Timestamp("2025-02-01").tz_localize(None), "close"] = list(range(100, 122))
    prices.loc[prices["date"] == pd.Timestamp("2025-01-31"), "close"] = 200
    check = _checks(evaluate(entry, prices, executions), "closing_breakout20")[0]
    assert check["verdict"] == "aligned"
    assert check["conditions"][0]["passed"] is True


def test_missing_duplicate_and_mixed_price_basis_fail_closed_per_decision():
    entry, prices, executions = _inputs()
    no_calendar = executions.drop(columns=["market_date"])
    assert _checks(evaluate(entry, prices, no_calendar), "trend_ma20")[0]["verdict"] == "insufficient"
    duplicate = pd.concat([prices, prices.loc[prices["date"] == pd.Timestamp("2025-01-31")]], ignore_index=True)
    assert _checks(evaluate(entry, duplicate, executions), "trend_ma20")[0]["verdict"] == "insufficient"
    mixed = prices.copy(); mixed.loc[mixed.index[0], "price_type"] = "adjusted_close"
    assert _checks(evaluate(entry, mixed, executions), "trend_ma20")[0]["verdict"] == "insufficient"


def test_cost_lens_uses_execution_price_only_and_is_action_specific():
    entry, prices, executions = _inputs(quantity_before=5, average_cost=100, price=101)
    prices.loc[:, "close"] = 1  # cost rule must not inspect market prices
    check = _checks(evaluate(entry, prices, executions), "cost_addition")[0]
    assert check["verdict"] == "aligned" and check["conditions"][0]["actual"] == 101
    entry, prices, executions = _inputs(side="SELL", quantity_before=5, average_cost=100)
    assert _checks(evaluate(entry, prices, executions), "cost_addition")[0]["verdict"] == "not_applicable"


def test_market_date_is_taken_from_canonical_frame_not_utc_event_date():
    entry, prices, executions = _inputs(market_date="2025-01-31")
    entry["decisions"][0]["occurred_at"] = "2025-02-01T00:30:00+08:00"
    check = _checks(evaluate(entry, prices, executions), "trend_ma20")[0]
    assert check["market_date"] == "2025-01-31"
    assert check["observed_through"] == "2025-01-30"


def test_trend_sell_condition_displays_exit_rule_not_buy_rule():
    entry, prices, executions = _inputs(side="SELL", quantity_before=5, average_cost=100)
    prices["close"] = list(range(125, 100, -1))
    check = _checks(evaluate(entry, prices, executions), "trend_ma20")[0]
    assert check["verdict"] == "aligned" and check["expected_action"] == "减仓或退出"
    assert check["conditions"][0]["operator"] == "<"
    assert check["conditions"][0]["passed"] is True
    assert "退出条件" in check["conditions"][0]["label"]


def test_bad_ownership_and_duplicate_execution_mapping_are_insufficient_not_crash():
    entry, prices, executions = _inputs()
    entry["decisions"][0]["episode_id"] = "not-this-episode"
    duplicate = pd.concat([executions, executions], ignore_index=True)
    report = evaluate(entry, prices, duplicate)
    assert all(_checks(report, method)[0]["verdict"] == "insufficient"
               for method in ("trend_ma20", "closing_breakout20", "cost_addition"))


def test_state_boundary_scope_and_canonical_transaction_mismatches_fail_closed():
    entry, prices, executions = _inputs(quantity_before=5, average_cost=100)
    entry["states_by_ref"]["before"]["boundary"] = "after_execution"
    assert all(_checks(evaluate(entry, prices, executions), method)[0]["verdict"] == "insufficient"
               for method in ("trend_ma20", "closing_breakout20", "cost_addition"))
    entry, prices, executions = _inputs()
    executions.loc[0, "instrument"] = "OTHER"
    assert _checks(evaluate(entry, prices, executions), "trend_ma20")[0]["verdict"] == "insufficient"
    entry, prices, executions = _inputs(quantity_before=5, average_cost=100)
    executions.loc[0, "price"] = 999
    assert _checks(evaluate(entry, prices, executions), "cost_addition")[0]["verdict"] == "insufficient"


def test_duplicate_decision_ids_and_equal_ma_are_not_silently_accepted():
    entry, prices, executions = _inputs()
    entry["decisions"].append(copy.deepcopy(entry["decisions"][0]))
    report = evaluate(entry, prices, executions)
    assert all(all(check["verdict"] == "insufficient" for check in _checks(report, method))
               for method in ("trend_ma20", "closing_breakout20", "cost_addition"))
    entry, prices, executions = _inputs()
    prior = prices[prices["date"] < pd.Timestamp("2025-02-01")].index[-20:]
    prices.loc[prior, "close"] = 100
    check = _checks(evaluate(entry, prices, executions), "trend_ma20")[0]
    assert check["verdict"] == "different" and check["expected_action"] == "等待"
    assert "SMA20" in check["explanation"]


def test_cost_fingerprint_does_not_depend_on_market_prefix_or_future_rows():
    entry, prices, executions = _inputs(quantity_before=5, average_cost=100, price=101)
    before = _checks(evaluate(entry, prices, executions), "cost_addition")[0]
    changed = prices.copy()
    changed.loc[:, "close"] = 1
    changed.loc[len(changed)] = ["2030-01-01", "AAA", -2, "adjusted_close", "other", "2", False]
    after = _checks(evaluate(entry, changed, executions), "cost_addition")[0]
    assert before["input_fingerprint"] == after["input_fingerprint"]
    assert after["observed_through"] is None and after["observation_count"] == 0


def test_mixed_offset_market_dates_keep_declared_days_and_bad_dates_fail_closed():
    entry, prices, executions = _inputs()
    plain = evaluate(entry, prices, executions)
    offset = prices.copy()
    offset["date"] = [
        f"{pd.Timestamp(day).date().isoformat()}T17:00:00+08:00" if index % 2 else
        f"{pd.Timestamp(day).date().isoformat()}T09:00:00-05:00"
        for index, day in enumerate(offset["date"])
    ]
    # A same-day and a future bad/duplicate observation are outside the strict
    # prefix and must have no effect on the already completed decision check.
    offset.loc[len(offset)] = ["2025-02-01T23:00:00+08:00", "AAA", -1, "adjusted_close", "other", "2", False]
    offset.loc[len(offset)] = ["2030-01-01T09:00:00-05:00", "AAA", float("nan"), "adjusted_close", "other", "2", False]
    assert evaluate(entry, offset, executions) == plain
    bad = prices.astype({"date": "object"}).copy()
    bad.loc[0, "date"] = "not-a-market-date"
    report = evaluate(entry, bad, executions)
    assert all(_checks(report, method)[0]["verdict"] == "insufficient"
               for method in ("trend_ma20", "closing_breakout20"))
