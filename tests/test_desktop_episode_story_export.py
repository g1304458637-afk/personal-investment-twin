from scripts.export_desktop_demo_evidence import _json_value, build_export


def _entries():
    payload = _json_value(build_export())
    return {
        item["instrument"]["instrument_id"]: item
        for item in payload["position_episode_demo"]["entries"]
    }


def test_product_demo_primary_episode_has_a_mature_unsmoothed_daily_path():
    entry = _entries()["SYN_PRODUCT"]
    assert 60 <= len(entry["price_points"]) <= 100
    assert [item["decision_type"] for item in entry["decisions"]] == [
        "open_position",
        "add_position",
        "add_position",
        "reduce_position",
        "reduce_position",
        "close_position",
    ]
    assert {item["segment"] for item in entry["price_points"]} >= {
        "pre_entry",
        "episode",
    }
    phases = [item["phase_type"] for item in entry["path_analysis"]["phases"]]
    assert phases == ["entry", "scaling_in", "scaling_out", "exit"]
    assert 3 <= len(entry["path_analysis"]["presentation_items"]) <= 6
    assert any(
        item["scenario_id"] == "omit_decision_phase_until_next_decision_v2"
        for item in entry["path_analysis"]["phase_counterfactuals"]
    )
    assert entry["instrument"]["is_synthetic"] is True
    dates = [item["observed_at"][:10] for item in entry["price_points"]]
    assert all(date <= entry["outcome_story"]["episode_outcome"]["analysis_as_of"][:10] for date in dates)
    assert not any(item["segment"] == "post_exit" for item in entry["price_points"])
    assert len(set(dates)) == len(dates)
    assert 60 <= len(set(dates)) <= 100
    prices = [item["price"] for item in entry["price_points"]]
    deltas = [later - earlier for earlier, later in zip(prices, prices[1:])]
    assert sum(1 for item in deltas if item > 0) >= 20
    assert sum(1 for item in deltas if item < 0) >= 20
    signs = [1 if item > 0 else -1 if item < 0 else 0 for item in deltas]
    flips = 0
    previous = 0
    for sign in signs:
        if sign != 0 and previous != 0 and sign != previous:
            flips += 1
        if sign != 0:
            previous = sign
    assert flips >= 15
    assert any(item["segment"] == "pre_entry" for item in entry["price_points"])


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
        item["scenario_id"] == "omit_event_until_next_decision_v2"
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


def test_long_horizon_fixtures_are_exported_without_replacing_product_demo():
    payload = _json_value(build_export())
    demo = payload["position_episode_demo"]
    entries = {
        item["instrument"]["instrument_id"]: item
        for item in demo["entries"]
    }
    assert demo["default_episode_id"] == entries["SYN_PRODUCT"]["episode"]["episode_id"]
    closed = entries["SYN_LONG_CLOSED"]
    opened = entries["SYN_LONG_OPEN"]
    holding = [
        item for item in closed["price_points"] if item["segment"] == "episode"
    ]
    assert closed["episode"]["status"] == "closed"
    assert opened["episode"]["status"] == "open"
    assert opened["episode"]["closed_at"] is None
    assert len(holding) >= 750
    assert len(opened["price_points"]) >= 1000
    assert closed["path_analysis"]["market_path"]["pre_entry_context"]["valid_observation_count"] <= 20
    assert closed["path_analysis"]["market_path"]["post_exit_context"]["valid_observation_count"] <= 20
    assert opened["path_analysis"]["market_path"]["post_exit_context"]["valid_observation_count"] == 0
    assert any(
        item["pattern_code"] == "long_no_execution_interval"
        for item in closed["path_analysis"]["patterns"]
    )
    assert 1 <= len(closed["path_analysis"]["presentation_items"]) <= 6
    assert all(
        item["phase_type"] in {"entry", "scaling_in", "scaling_out", "exit"}
        for item in closed["path_analysis"]["phases"]
    )
    assert opened["outcome_story"]["episode_outcome"]["actual_result"]["result_kind"] == "marked"
    assert closed["outcome_story"]["episode_outcome"]["actual_result"]["result_kind"] == "realized"
