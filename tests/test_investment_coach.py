import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from agents import FunctionTool, ToolCallItem, ToolCallOutputItem
from agents.tool_context import ToolContext

import src.agents.investment_coach as coach_module
from src.agents.investment_coach import (
    COACH_INSTRUCTIONS,
    InvestmentCoachContext,
    InvestmentEpisodeFacts,
    REQUIRED_COACH_TOOLS,
    RequiredToolUseError,
    SelectionEvidenceFacts,
    create_investment_coach_agent,
    get_current_investment_episode,
    get_current_selection_evidence,
    load_synthetic_demo_context,
    main,
    run_investment_coach,
)
from src.data.local_market_data_provider import LocalMarketDataProvider


@pytest.fixture(scope="module")
def coach_context() -> InvestmentCoachContext:
    return load_synthetic_demo_context()


def _invoke_tool(
    tool: FunctionTool,
    context: InvestmentCoachContext,
) -> object:
    tool_context = ToolContext(
        context,
        tool_name=tool.name,
        tool_call_id="test-call",
        tool_arguments="{}",
    )
    return asyncio.run(tool.on_invoke_tool(tool_context, "{}"))


def _run_result_with_tool_outputs(
    agent,
    context: InvestmentCoachContext,
    executed_tools: set[str] | frozenset[str],
    *,
    final_output: str = "accepted coach response",
    output_overrides: dict[str, object] | None = None,
):
    outputs = {
        "get_current_investment_episode": coach_module._episode_facts(
            context.episode
        ),
        "get_current_selection_evidence": coach_module._selection_evidence_facts(
            context.selection_evidence
        ),
    }
    if output_overrides is not None:
        outputs.update(output_overrides)

    items = []
    for index, tool_name in enumerate(sorted(REQUIRED_COACH_TOOLS)):
        call_id = f"call-{index}"
        items.append(
            ToolCallItem(
                agent=agent,
                raw_item={
                    "type": "function_call",
                    "name": tool_name,
                    "call_id": call_id,
                },
            )
        )
        if tool_name in executed_tools:
            items.append(
                ToolCallOutputItem(
                    agent=agent,
                    raw_item={
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": "{}",
                    },
                    output=outputs[tool_name],
                )
            )
    return SimpleNamespace(new_items=items, final_output=final_output)


def test_agent_has_exactly_two_structured_function_tools():
    agent = create_investment_coach_agent()

    assert agent.name == "Investment Coach Agent V0"
    assert agent.handoffs == []
    assert agent.tools == [
        get_current_investment_episode,
        get_current_selection_evidence,
    ]
    assert all(isinstance(tool, FunctionTool) for tool in agent.tools)
    assert [tool.name for tool in agent.tools] == [
        "get_current_investment_episode",
        "get_current_selection_evidence",
    ]
    assert all(tool.params_json_schema["properties"] == {} for tool in agent.tools)
    assert all(tool.output_json_schema["type"] == "object" for tool in agent.tools)
    assert agent.model_settings.tool_choice == "required"


def test_instructions_enforce_deterministic_financial_boundaries():
    agent = create_investment_coach_agent()

    assert agent.instructions == COACH_INSTRUCTIONS
    assert "必须先调用" in COACH_INSTRUCTIONS
    assert "不得自行计算、换算、重算" in COACH_INSTRUCTIONS
    assert "Position Return" in COACH_INSTRUCTIONS
    assert "Asset Episode TWR" in COACH_INSTRUCTIONS
    assert "insufficient_evidence" in COACH_INSTRUCTIONS
    assert "synthetic/demo" in COACH_INSTRUCTIONS
    assert "不得由单个 Episode 推断" in COACH_INSTRUCTIONS
    assert "不荐股" in COACH_INSTRUCTIONS


def test_tools_return_existing_deterministic_facts(
    coach_context: InvestmentCoachContext,
):
    episode_facts = _invoke_tool(
        get_current_investment_episode,
        coach_context,
    )
    evidence_facts = _invoke_tool(
        get_current_selection_evidence,
        coach_context,
    )

    assert isinstance(episode_facts, InvestmentEpisodeFacts)
    assert episode_facts.symbol == "600000.SH"
    assert episode_facts.status == "Closed"
    assert episode_facts.pnl == coach_context.episode.pnl
    assert episode_facts.position_return == coach_context.episode.return_value
    assert episode_facts.position_return == pytest.approx(0.217361, abs=1e-6)

    assert isinstance(evidence_facts, SelectionEvidenceFacts)
    evidence = coach_context.selection_evidence
    assert evidence_facts.evidence_status == "complete"
    assert evidence_facts.asset_episode_twr == evidence.asset_return
    assert evidence_facts.market_benchmark_twr == evidence.market_benchmark_return
    assert evidence_facts.industry_benchmark_twr == evidence.industry_benchmark_return
    assert evidence_facts.asset_episode_twr == pytest.approx(0.30)
    assert evidence_facts.market_benchmark_twr == pytest.approx(0.08)
    assert evidence_facts.industry_benchmark_twr == pytest.approx(0.25)
    assert evidence_facts.market_comparison == "outperformed"
    assert evidence_facts.industry_comparison == "outperformed"


def test_position_return_and_asset_episode_twr_are_not_conflated(
    coach_context: InvestmentCoachContext,
):
    episode_facts = _invoke_tool(get_current_investment_episode, coach_context)
    evidence_facts = _invoke_tool(get_current_selection_evidence, coach_context)

    assert isinstance(episode_facts, InvestmentEpisodeFacts)
    assert isinstance(evidence_facts, SelectionEvidenceFacts)
    assert episode_facts.position_return != evidence_facts.asset_episode_twr
    assert episode_facts.position_return_display == "21.7361%"
    assert evidence_facts.asset_episode_twr_display == "30.0000%"
    assert "actual executed trade path" in episode_facts.position_return_semantics
    assert "not the user's Position Return" in evidence_facts.asset_episode_twr_semantics


def test_synthetic_provenance_and_notice_are_preserved(
    coach_context: InvestmentCoachContext,
):
    facts = _invoke_tool(get_current_selection_evidence, coach_context)

    assert isinstance(facts, SelectionEvidenceFacts)
    assert facts.synthetic_provenance_present is True
    assert facts.synthetic_notice is not None
    assert "not real historical market performance" in facts.synthetic_notice
    assert {item.data_source for item in facts.provenance} == {"local_fixture"}
    assert {item.data_version for item in facts.provenance} == {"v1"}
    assert all(item.is_synthetic is True for item in facts.provenance)

    asset = coach_context.selection_evidence.asset_provenance
    assert asset is not None
    asset_facts = next(
        item for item in facts.provenance if item.record_type == "asset_price"
    )
    assert asset_facts.record_id == asset.instrument
    assert asset_facts.data_source == asset.data_source
    assert asset_facts.data_version == asset.data_version
    assert asset_facts.price_type == asset.price_type
    assert asset_facts.is_synthetic is asset.is_synthetic


def test_selection_tool_does_not_read_provider_to_derive_asset_provenance(
    monkeypatch: pytest.MonkeyPatch,
    coach_context: InvestmentCoachContext,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent tool must not read market data for provenance")

    monkeypatch.setattr(LocalMarketDataProvider, "get_prices", fail_if_called)

    facts = _invoke_tool(get_current_selection_evidence, coach_context)

    assert isinstance(facts, SelectionEvidenceFacts)
    assert any(item.record_type == "asset_price" for item in facts.provenance)
    assert not hasattr(coach_module, "_asset_price_provenance")


def test_asset_only_synthetic_provenance_still_triggers_notice(
    coach_context: InvestmentCoachContext,
):
    assert coach_context.selection_evidence.asset_provenance is not None
    non_synthetic_evidence = replace(
        coach_context.selection_evidence,
        benchmark_provenance=tuple(
            replace(item, is_synthetic=False)
            for item in coach_context.selection_evidence.benchmark_provenance
        ),
        industry_provenance=replace(
            coach_context.selection_evidence.industry_provenance,
            is_synthetic=False,
        ),
    )
    context = InvestmentCoachContext(
        episode=coach_context.episode,
        selection_evidence=non_synthetic_evidence,
    )

    facts = _invoke_tool(get_current_selection_evidence, context)

    assert isinstance(facts, SelectionEvidenceFacts)
    synthetic_records = [item for item in facts.provenance if item.is_synthetic]
    assert [(item.record_type, item.record_id) for item in synthetic_records] == [
        ("asset_price", "600000.SH")
    ]
    assert facts.synthetic_provenance_present is True
    assert facts.synthetic_notice is not None


def test_insufficient_evidence_is_preserved_without_fallback_calculation(
    coach_context: InvestmentCoachContext,
):
    reason = "Price data for CSI300 does not cover the episode end date"
    insufficient = replace(
        coach_context.selection_evidence,
        asset_return=None,
        market_benchmark_return=None,
        market_comparison=None,
        industry_benchmark_return=None,
        industry_comparison=None,
        evidence_status="insufficient_evidence",
        evidence_reason=reason,
    )
    context = InvestmentCoachContext(
        episode=coach_context.episode,
        selection_evidence=insufficient,
    )

    facts = _invoke_tool(get_current_selection_evidence, context)

    assert isinstance(facts, SelectionEvidenceFacts)
    assert facts.evidence_status == "insufficient_evidence"
    assert facts.evidence_reason == reason
    assert facts.asset_episode_twr is None
    assert facts.asset_episode_twr_display is None
    assert facts.market_benchmark_twr is None
    assert facts.market_benchmark_twr_display is None
    assert facts.market_comparison is None
    assert facts.industry_benchmark_twr is None
    assert facts.industry_benchmark_twr_display is None
    assert facts.industry_comparison is None


def test_run_accepts_output_only_after_both_tools_execute(
    monkeypatch: pytest.MonkeyPatch,
    coach_context: InvestmentCoachContext,
):
    agent = create_investment_coach_agent()
    result = _run_result_with_tool_outputs(
        agent,
        coach_context,
        REQUIRED_COACH_TOOLS,
    )
    monkeypatch.setattr(
        coach_module.Runner,
        "run_sync",
        lambda *args, **kwargs: result,
    )

    output = run_investment_coach("帮我分析一下这次投资。", coach_context, agent=agent)

    assert output == "accepted coach response"


@pytest.mark.parametrize("missing_tool", sorted(REQUIRED_COACH_TOOLS))
def test_run_rejects_final_output_when_a_required_tool_did_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    coach_context: InvestmentCoachContext,
    missing_tool: str,
):
    agent = create_investment_coach_agent()
    executed = set(REQUIRED_COACH_TOOLS) - {missing_tool}
    result = _run_result_with_tool_outputs(agent, coach_context, executed)
    monkeypatch.setattr(
        coach_module.Runner,
        "run_sync",
        lambda *args, **kwargs: result,
    )

    with pytest.raises(RequiredToolUseError, match=missing_tool):
        run_investment_coach("帮我分析一下这次投资。", coach_context, agent=agent)


@pytest.mark.parametrize("failed_tool", sorted(REQUIRED_COACH_TOOLS))
def test_run_rejects_final_output_when_a_tool_returns_an_error(
    monkeypatch: pytest.MonkeyPatch,
    coach_context: InvestmentCoachContext,
    failed_tool: str,
):
    agent = create_investment_coach_agent()
    result = _run_result_with_tool_outputs(
        agent,
        coach_context,
        REQUIRED_COACH_TOOLS,
        output_overrides={failed_tool: "An error occurred while running the tool."},
    )
    monkeypatch.setattr(
        coach_module.Runner,
        "run_sync",
        lambda *args, **kwargs: result,
    )

    with pytest.raises(RequiredToolUseError, match=failed_tool):
        run_investment_coach("帮我分析一下这次投资。", coach_context, agent=agent)


def test_demo_requires_api_key_before_any_model_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="Set OPENAI_API_KEY"):
        main([])
