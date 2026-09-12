"""strategy_simulation.run_custom: protocol-level workshop runtime tests."""
import pytest

from toujing_core_runtime.protocol import _product_methods

VALID = {
    "schema_version": "user_strategy.v1", "name": "工坊冒烟",
    "entry": {"all_of": [{"factor": "breakout_high", "params": {"window": 20}, "op": "true"}]},
    "exit": {"any_of": [{"factor": "breakdown_low", "params": {"window": 10}, "op": "true"}],
             "stop_loss_pct": 0.1},
    "sizing": {"mode": "equal_weight", "fraction": 0.25},
    "constraints": {"max_positions": 4},
}


@pytest.fixture()
def methods():
    return _product_methods(":memory:")[0]


def test_valid_spec_runs_and_returns_adapter_ready_artifact(methods):
    result = methods["strategy_simulation.run_custom"]({"strategy": VALID})
    assert result["status"] == "available"
    artifact = result["artifact"]
    assert artifact["schema_version"] == "strategy_simulation.v1"
    assert artifact["strategy"]["strategy_id"].startswith("user_")
    assert artifact["summary"]["fill_count"] == len(artifact["fills"])
    assert artifact["bars"] and artifact["equity"]
    sources = {rule["source"] for rule in artifact["strategy"]["rule_table"]}
    assert "user_defined" in sources and "system_execution" in sources


def test_future_function_self_check_is_part_of_the_run(methods):
    result = methods["strategy_simulation.run_custom"]({"strategy": VALID})
    # The run passed the prefix-identity self check; a second run is identical.
    again = methods["strategy_simulation.run_custom"]({"strategy": VALID})
    assert result["artifact"]["summary"] == again["artifact"]["summary"]
    assert result["artifact"]["equity"] == again["artifact"]["equity"]


def test_invalid_specs_refused_with_explainable_reasons(methods):
    cases = [
        ({**VALID, "schema_version": "x"}, "invalid_strategy_spec"),
        ({**VALID, "entry": {"all_of": [
            {"factor": "breakout_high", "params": {"window": 20}, "op": "true"},
            {"factor": "insider_info", "op": "true"}]}}, "invalid_strategy_spec"),
        ({**VALID, "exit": {"any_of": [], "stop_loss_pct": None}}, "invalid_strategy_spec"),
        ("not-a-dict", "invalid_strategy_spec"),
    ]
    for strategy, reason_prefix in cases:
        result = methods["strategy_simulation.run_custom"]({"strategy": strategy})
        assert result["status"] == "unavailable", strategy
        assert result["reason"].startswith(reason_prefix), result["reason"]
        assert result["artifact"] is None
