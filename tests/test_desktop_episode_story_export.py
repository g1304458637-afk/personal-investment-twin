from scripts.export_desktop_demo_evidence import _json_value, build_export


def _entries():
    payload = _json_value(build_export())
    return {
        item["instrument"]["instrument_id"]: item
        for item in payload["position_episode_demo"]["entries"]
    }


def test_product_demo_primary_episode_has_a_mature_unsmoothed_daily_path():
    entry = _entries()["SYN_PRODUCT"]
    assert 60 <= len(entry["price_points"]) <= 90
    assert [item["decision_type"] for item in entry["decisions"]] == [
        "open_position", "add_position", "add_position", "reduce_position",
        "add_position", "close_position",
    ]
    assert entry["instrument"]["is_synthetic"] is True


def test_episode_story_exports_authoritative_actual_outcomes_for_every_lifecycle():
    entries = _entries()

    assert entries["600000.SH"]["outcome_story"]["episode_outcome"][
        "actual_result"
    ]["pnl"] == 3369.1
    assert entries["600000.SH"]["outcome_story"]["episode_outcome"][
        "actual_result"
    ]["result_kind"] == "realized"
    assert entries["SYN_PAPER_LOSS"]["outcome_story"]["episode_outcome"][
        "actual_result"
    ]["result_kind"] == "marked"
    assert all(
        item["outcome_story"]["episode_outcome"]["actual_result"]["source"][
            "source_kind"
        ]
        == "vectorbt_position"
        for item in entries.values()
    )


def test_episode_story_buy_has_no_realized_result_and_sell_uses_exit_trade():
    stories = [item["outcome_story"] for item in _entries().values()]
    outcomes = [item for story in stories for item in story["decision_outcomes"]]

    assert all(item["immediate_result"] is None for item in outcomes if item["side"] == "BUY")
    assert all(
        item["immediate_result"]["source"]["source_kind"] == "vectorbt_exit_trade"
        for item in outcomes
        if item["side"] == "SELL"
    )
    partial_profit = next(
        item
        for item in _entries()["SYN_WIN_SOLD"]["outcome_story"]["decision_outcomes"]
        if item["side"] == "SELL"
    )
    partial_loss = next(
        item
        for item in _entries()["SYN_LOSS_SOLD"]["outcome_story"]["decision_outcomes"]
        if item["side"] == "SELL"
    )
    assert partial_profit["immediate_result"]["pnl"] == 100.0
    assert partial_loss["immediate_result"]["pnl"] == -200.0


def test_episode_story_exports_registered_feasible_and_fail_closed_scenarios():
    selected = _entries()["600000.SH"]["outcome_story"]["counterfactuals"]

    assert any(
        item["scenario_id"] == "omit_event_until_next_decision_v1"
        and item["feasibility_status"] == "complete"
        for item in selected
    )
    assert any(
        item["scenario_id"] == "omit_event_preserve_later_executions_v1"
        and item["feasibility_status"] == "complete"
        for item in selected
    )
    infeasible = next(
        item
        for item in selected
        if item["feasibility_status"] == "infeasible_downstream_execution"
    )
    assert infeasible["counterfactual_result"] is None
    assert infeasible["comparison"]["pnl_difference"] is None
    assert infeasible["first_conflicting_execution_id"]


def test_episode_story_reuses_existing_exit_evidence_and_separate_price_bases():
    story = _entries()["SYN_EXIT_UP"]["outcome_story"]
    followup = story["exit_followup"]
    baseline = next(
        item
        for item in story["counterfactuals"]
        if item["scenario_id"] == "existing_exit_evidence_reuse_v1"
    )

    assert baseline["baseline_evidence_ref"] == followup["evidence_id"]
    assert baseline["feasibility_status"] == "complete"
    assert followup["actual_exit_price"] == 99.5
    assert followup["exit_session_market_price"] == 100.0
    assert followup["post_exit_asset_return"] == 0.19999999999999973
