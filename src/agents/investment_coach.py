"""Investment Coach Agent V0 backed only by deterministic financial facts."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

import pandas as pd
from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from agents import (
    Agent,
    ModelSettings,
    RunContextWrapper,
    RunConfig,
    RunResult,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    function_tool,
)
from agents.models import get_default_model
from agents.models.openai_responses import OpenAIResponsesModel

from src.attribution.selection_evidence import (
    SelectionEvidence,
    build_selection_evidence,
)
from src.core.vectorbt_validation import replay_single_symbol_executions
from src.data.csv_importer import load_normalized_csv
from src.data.local_market_data_provider import LocalMarketDataProvider
from src.episodes.investment_episode import (
    InvestmentEpisode,
    from_vectorbt_position_record,
)


DEFAULT_QUESTION: Final = "帮我分析一下这次投资。"
DEMO_INITIAL_CASH: Final = 100_000.0
PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
ProviderName = Literal["deepseek", "openai"]
DEFAULT_PROVIDER: Final[ProviderName] = "deepseek"
DEEPSEEK_BASE_URL: Final = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL: Final = "deepseek-v4-flash"
REQUIRED_COACH_TOOLS: Final = frozenset(
    {
        "get_current_investment_episode",
        "get_current_selection_evidence",
    }
)

COACH_INSTRUCTIONS: Final = """
你是 Personal Investment Twin 的 Investment Coach Agent V0。

当用户要求分析当前选中的 Investment Episode 时，必须先调用
get_current_investment_episode 和 get_current_selection_evidence 两个工具，再解释事实。

严格遵守以下规则：
1. 所有 PnL、Return、Asset Episode TWR、benchmark TWR 和 comparison 必须逐字依据工具结果。
   不得自行计算、换算、重算、补值、插值或从原始成交推导任何金融数字。需要百分比时只引用工具提供的
   *_display 字段；字段为 None 时必须说明不可用。
2. Position Return 是用户实际成交路径对应的 vectorbt Position Return；Asset Episode TWR 是 Episode
   期间资产价格路径的累计表现。必须分别使用这两个名称解释，绝不能混为一谈。
3. SelectionEvidence 只是单个 Episode 的相对表现证据，不是 skill、alpha、选股贡献率或长期能力评分。
   不得由单个 Episode 推断用户具有或不具有长期选股能力。
4. evidence_status 为 insufficient_evidence 时，明确说明证据不足及 evidence_reason；不得猜测、补数据
   或自行计算替代结果。
5. synthetic_provenance_present 为 true 时，必须明确说明这是 synthetic/demo 数据，不是真实历史市场表现。
6. 不荐股、不预测未来涨跌、不自动交易，也不给出确定性的买入或卖出指令。
7. 可以报告 Position Return 与 Asset Episode TWR 的大小关系，但不得仅依据这一大小关系自行解释或归因
   差异。只有当相应的 deterministic Attribution Tool 已注册为当前 Agent tool、在本次 run 中实际成功
   调用并返回有效 attribution evidence 时，才允许严格依据该工具结果解释差异来源。没有对应 Attribution
   Tool 或任一条件未满足时，必须说明当前证据不足以判断差异来自 Entry / Exit / Sizing / Scaling /
   Friction 中的哪一项，不得猜测。
8. 当前 V0 已注册的 tools 只有 get_current_investment_episode 和 get_current_selection_evidence。Agent
   只能声称拥有当前已注册且可成功调用的 tools 所支持的能力。Behavior Analytics、Investor DNA、
   Personal Memory 和 Pre-Decision Intervention 不是永久禁止的能力；没有对应工具时才说明当前尚未接入，
   不得假装拥有。

回答应简洁、清楚，并明确区分确定性事实、证据限制与非结论。
""".strip()


@dataclass(frozen=True, slots=True)
class InvestmentEpisodeFacts:
    episode_id: str
    symbol: str
    status: str
    position_id: int
    direction: str
    size: float
    entry_time: str
    end_time: str | None
    end_time_kind: str | None
    pnl: float
    position_return: float
    position_return_display: str
    position_return_semantics: str


@dataclass(frozen=True, slots=True)
class ProvenanceFacts:
    record_type: str
    record_id: str
    record_name: str
    data_source: str
    data_version: str
    as_of: str
    price_type: str | None
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class SelectionEvidenceFacts:
    episode_id: str
    symbol: str
    start_time: str
    end_time: str | None
    evidence_status: str
    evidence_reason: str | None
    asset_episode_twr: float | None
    asset_episode_twr_display: str | None
    asset_episode_twr_semantics: str
    market_benchmark_id: str
    market_benchmark_name: str | None
    market_benchmark_twr: float | None
    market_benchmark_twr_display: str | None
    market_comparison: str | None
    industry_id: str | None
    industry_name: str | None
    industry_benchmark_id: str | None
    industry_benchmark_name: str | None
    industry_benchmark_twr: float | None
    industry_benchmark_twr_display: str | None
    industry_comparison: str | None
    synthetic_provenance_present: bool
    synthetic_notice: str | None
    provenance: tuple[ProvenanceFacts, ...]


@dataclass(frozen=True, slots=True)
class InvestmentCoachContext:
    episode: InvestmentEpisode
    selection_evidence: SelectionEvidence

    def __post_init__(self) -> None:
        if self.episode.episode_id != self.selection_evidence.episode_id:
            raise ValueError("Episode and SelectionEvidence IDs must match")


@dataclass(frozen=True, slots=True)
class CoachModelRuntime:
    """One explicit Agents SDK model/client configuration for a coach run."""

    provider: ProviderName
    model_name: str
    model: OpenAIResponsesModel = field(repr=False)
    model_settings: ModelSettings = field(repr=False)
    run_config: RunConfig = field(repr=False)


def _timestamp_text(value: object | None) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(value).isoformat()


def _percent_display(value: float | None) -> str | None:
    """Format an existing deterministic return without deriving a new metric."""

    if value is None:
        return None
    return format(value, ".4%")


def _episode_facts(episode: InvestmentEpisode) -> InvestmentEpisodeFacts:
    if episode.status == "Closed":
        end_time = episode.exit_time
        end_time_kind = "exit_time"
    elif episode.status == "Open":
        end_time = episode.valuation_time
        end_time_kind = "valuation_time"
    else:
        end_time = None
        end_time_kind = None

    return InvestmentEpisodeFacts(
        episode_id=episode.episode_id,
        symbol=episode.symbol,
        status=episode.status,
        position_id=episode.position_id,
        direction=episode.direction,
        size=episode.size,
        entry_time=_timestamp_text(episode.entry_time) or "",
        end_time=_timestamp_text(end_time),
        end_time_kind=end_time_kind,
        pnl=episode.pnl,
        position_return=episode.return_value,
        position_return_display=_percent_display(episode.return_value) or "",
        position_return_semantics=(
            "vectorbt Position Return for the user's actual executed trade path"
        ),
    )


def _selection_provenance(
    evidence: SelectionEvidence,
) -> tuple[ProvenanceFacts, ...]:
    records = []
    if evidence.asset_provenance is not None:
        asset = evidence.asset_provenance
        records.append(
            ProvenanceFacts(
                record_type="asset_price",
                record_id=asset.instrument,
                record_name=asset.instrument,
                data_source=asset.data_source,
                data_version=asset.data_version,
                as_of=_timestamp_text(asset.as_of) or "",
                price_type=asset.price_type,
                is_synthetic=asset.is_synthetic,
            )
        )

    records.extend(
        ProvenanceFacts(
            record_type=item.benchmark_type,
            record_id=item.benchmark_id,
            record_name=item.benchmark_name,
            data_source=item.data_source,
            data_version=item.data_version,
            as_of=_timestamp_text(item.as_of) or "",
            price_type=item.price_type,
            is_synthetic=item.is_synthetic,
        )
        for item in evidence.benchmark_provenance
    )

    if evidence.industry_provenance is not None:
        industry = evidence.industry_provenance
        records.append(
            ProvenanceFacts(
                record_type="industry_membership",
                record_id=industry.industry_id,
                record_name=industry.industry_name,
                data_source=industry.data_source,
                data_version=industry.data_version,
                as_of=_timestamp_text(industry.as_of) or "",
                price_type=None,
                is_synthetic=industry.is_synthetic,
            )
        )

    return tuple(records)


def _selection_evidence_facts(
    evidence: SelectionEvidence,
) -> SelectionEvidenceFacts:
    provenance = _selection_provenance(evidence)
    synthetic_present = any(item.is_synthetic for item in provenance)
    synthetic_notice = (
        "This SelectionEvidence contains synthetic/demo data and is not real "
        "historical market performance."
        if synthetic_present
        else None
    )

    return SelectionEvidenceFacts(
        episode_id=evidence.episode_id,
        symbol=evidence.symbol,
        start_time=_timestamp_text(evidence.start_time) or "",
        end_time=_timestamp_text(evidence.end_time),
        evidence_status=evidence.evidence_status,
        evidence_reason=evidence.evidence_reason,
        asset_episode_twr=evidence.asset_return,
        asset_episode_twr_display=_percent_display(evidence.asset_return),
        asset_episode_twr_semantics=(
            "Asset Episode TWR from the asset price path over the Episode window; "
            "not the user's Position Return"
        ),
        market_benchmark_id=evidence.market_benchmark_id,
        market_benchmark_name=evidence.market_benchmark_name,
        market_benchmark_twr=evidence.market_benchmark_return,
        market_benchmark_twr_display=_percent_display(
            evidence.market_benchmark_return
        ),
        market_comparison=evidence.market_comparison,
        industry_id=evidence.industry_id,
        industry_name=evidence.industry_name,
        industry_benchmark_id=evidence.industry_benchmark_id,
        industry_benchmark_name=evidence.industry_benchmark_name,
        industry_benchmark_twr=evidence.industry_benchmark_return,
        industry_benchmark_twr_display=_percent_display(
            evidence.industry_benchmark_return
        ),
        industry_comparison=evidence.industry_comparison,
        synthetic_provenance_present=synthetic_present,
        synthetic_notice=synthetic_notice,
        provenance=provenance,
    )


@function_tool(output_type=InvestmentEpisodeFacts)
def get_current_investment_episode(
    context: RunContextWrapper[InvestmentCoachContext],
) -> InvestmentEpisodeFacts:
    """Return authoritative facts for the currently selected Investment Episode.

    The PnL and Position Return are copied from InvestmentEpisode, which maps
    vectorbt Position records. Never recompute them from executions.
    """

    return _episode_facts(context.context.episode)


@function_tool(output_type=SelectionEvidenceFacts)
def get_current_selection_evidence(
    context: RunContextWrapper[InvestmentCoachContext],
) -> SelectionEvidenceFacts:
    """Return authoritative SelectionEvidence for the selected Episode.

    Returns, comparisons, evidence status, reasons, and provenance are copied
    from the deterministic SelectionEvidence result. Missing evidence stays
    missing and must not be replaced by model calculations.
    """

    return _selection_evidence_facts(context.context.selection_evidence)


class ProviderConfigurationError(ValueError):
    """Raised when the selected model provider cannot be configured safely."""


def create_model_runtime(
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> CoachModelRuntime:
    """Build a per-run OpenAI-compatible client without changing SDK globals."""

    env = os.environ if environment is None else environment
    if provider == "deepseek":
        api_key = env.get("DEEPSEEK_API_KEY")
        if api_key is None or not api_key.strip():
            raise ProviderConfigurationError(
                "Set DEEPSEEK_API_KEY in the environment for the DeepSeek provider."
            )
        model_name = model or DEFAULT_DEEPSEEK_MODEL
        client = AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        reasoning = Reasoning(effort="none")
        tracing_disabled = True
    elif provider == "openai":
        api_key = env.get("OPENAI_API_KEY")
        if api_key is None or not api_key.strip():
            raise ProviderConfigurationError(
                "Set OPENAI_API_KEY in the environment for the OpenAI provider."
            )
        model_name = model or get_default_model()
        client = AsyncOpenAI(api_key=api_key)
        reasoning = None
        tracing_disabled = False
    else:
        raise ProviderConfigurationError(
            f"Unsupported provider: {provider}. Expected deepseek or openai."
        )

    return CoachModelRuntime(
        provider=provider,
        model_name=model_name,
        model=OpenAIResponsesModel(model=model_name, openai_client=client),
        model_settings=ModelSettings(
            tool_choice="required",
            reasoning=reasoning,
        ),
        run_config=RunConfig(tracing_disabled=tracing_disabled),
    )


def create_investment_coach_agent(
    *,
    model: str | OpenAIResponsesModel | None = None,
    model_settings: ModelSettings | None = None,
) -> Agent[InvestmentCoachContext]:
    """Create the single bounded Investment Coach Agent V0."""

    settings = model_settings or ModelSettings(tool_choice="required")
    if settings.tool_choice != "required":
        raise ValueError("Investment Coach requires tool_choice='required'")

    return Agent(
        name="Investment Coach Agent V0",
        instructions=COACH_INSTRUCTIONS,
        tools=[
            get_current_investment_episode,
            get_current_selection_evidence,
        ],
        model=model,
        model_settings=settings,
    )


class RequiredToolUseError(RuntimeError):
    """Raised when a run did not execute both deterministic fact tools."""


def validate_required_tool_use(result: RunResult) -> str:
    """Return final output only after both fact tools completed successfully."""

    calls_by_id = {
        item.call_id: item.tool_name
        for item in result.new_items
        if isinstance(item, ToolCallItem)
        and item.call_id is not None
        and item.tool_name is not None
    }
    expected_output_types = {
        "get_current_investment_episode": InvestmentEpisodeFacts,
        "get_current_selection_evidence": SelectionEvidenceFacts,
    }
    executed_tools = {
        calls_by_id[item.call_id]
        for item in result.new_items
        if isinstance(item, ToolCallOutputItem)
        and item.call_id in calls_by_id
        and isinstance(
            item.output,
            expected_output_types.get(calls_by_id[item.call_id], ()),
        )
    }
    missing = sorted(REQUIRED_COACH_TOOLS.difference(executed_tools))
    if missing:
        raise RequiredToolUseError(
            "Investment Coach run rejected because required deterministic tools did "
            f"not complete successfully: {', '.join(missing)}"
        )
    if not isinstance(result.final_output, str):
        raise RequiredToolUseError("Investment Coach run produced no text final output")
    return result.final_output


def run_investment_coach(
    question: str,
    context: InvestmentCoachContext,
    *,
    agent: Agent[InvestmentCoachContext] | None = None,
    run_config: RunConfig | None = None,
) -> str:
    """Run once and expose output only after required tool-use validation."""

    active_agent = agent or create_investment_coach_agent()
    result = Runner.run_sync(
        active_agent,
        question,
        context=context,
        run_config=run_config,
    )
    return validate_required_tool_use(result)


def load_synthetic_demo_context(
    project_root: str | Path = PROJECT_ROOT,
) -> InvestmentCoachContext:
    """Load the existing local synthetic fixture through deterministic modules."""

    root = Path(project_root)
    executions = load_normalized_csv(
        root / "data" / "sample" / "synthetic_executions.csv"
    )
    symbol = str(executions["symbol"].iat[0])
    valuation_prices = executions.set_index("event_time")["executed_price"].rename(
        symbol
    )
    portfolio = replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=DEMO_INITIAL_CASH,
    )
    position_records = portfolio.positions.records_readable
    if len(position_records) != 1:
        raise ValueError("Synthetic demo must produce exactly one Position")

    episode = from_vectorbt_position_record(position_records.iloc[0])
    provider = LocalMarketDataProvider(root / "data" / "reference")
    evidence = build_selection_evidence(episode, provider)
    return InvestmentCoachContext(
        episode=episode,
        selection_evidence=evidence,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic demo against the selected OpenAI-compatible provider."""

    parser = argparse.ArgumentParser(description="Run Investment Coach Agent V0")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--provider",
        choices=("deepseek", "openai"),
        default=DEFAULT_PROVIDER,
        help="Model provider (default: deepseek).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional model override. DeepSeek defaults to deepseek-v4-flash; "
            "OpenAI uses the Agents SDK default."
        ),
    )
    args = parser.parse_args(argv)

    try:
        runtime = create_model_runtime(args.provider, args.model)
    except ProviderConfigurationError as exc:
        raise SystemExit(str(exc)) from exc

    context = load_synthetic_demo_context()
    agent = create_investment_coach_agent(
        model=runtime.model,
        model_settings=runtime.model_settings,
    )
    final_output = run_investment_coach(
        args.question,
        context,
        agent=agent,
        run_config=runtime.run_config,
    )
    print(final_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
