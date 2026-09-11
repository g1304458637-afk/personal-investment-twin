"""Read-only research lenses adapted from pinned DSA strategies (MIT).

These are research questions, not computed signals or evidence about a stock.
See docs/STOCK_RESEARCH_CAPABILITIES.md for upstream provenance and differences.
"""
from __future__ import annotations

from agents import RunContextWrapper, function_tool
from typing import Literal

from src.agents.account_review_sources import _record
import json
from datetime import datetime, timezone
from src.agents.public_research import _complete

UPSTREAM = "https://github.com/ZhuLinsen/daily_stock_analysis/blob/089d9d26d68f8b839ea5a74a3784e4402925f8b7/strategies/"
METHODS = {
    "overview": {
        "title": "股票研究：先结论，再对照价格、事件与经营依据",
        "questions": ["确认证券、市场、研究期间与资料时间。", "对照价格与成交量，再梳理近期已公开事件。",
                      "用户关心经营时，查公告或财报原始来源，分清报告期。", "主动找与初步解释冲突的资料，给出可继续跟踪的条件。"],
        "sources": [UPSTREAM + "event_driven.yaml", UPSTREAM + "growth_quality.yaml", UPSTREAM + "volume_breakout.yaml"],
    },
    "price_volume": {
        "title": "价格与成交量：对照走势，而不是只看一根K线",
        "questions": ["同一复权口径、同一期间读取日线开高低收与成交量。", "对照前后交易日价格与量能的方向，说明具体日期。",
                      "突破解释需要已计算的阻力位、均量和后续验证，缺少这些不能声称信号成立。", "放量不等于吸筹，价格变化与事件相邻不证明因果。"],
        "sources": [UPSTREAM + "volume_breakout.yaml"],
    },
    "events": {
        "title": "事件研究：发生了什么，可能通过什么路径影响公司",
        "questions": ["按业绩、政策、订单或产品、资本运作、监管或诉讼整理事件。", "区分事件发生日、网页发布日期与检索日，优先公司和交易所公告。",
                      "解释影响收入、成本、融资或业务的路径，并区分已发生事实和待兑现条件。", "查找澄清、延期、负面或相反报道；价格反应不能证明市场已充分定价。"],
        "sources": [UPSTREAM + "event_driven.yaml"],
    },
    "business": {
        "title": "经营研究：增长、盈利与现金流是否互相支持",
        "questions": ["优先同一报告期的收入、净利润、经营现金流与ROE；核对单位及同比口径。", "对照收入与利润方向，区分持续经营与一次性因素。",
                      "对照现金流与利润，查找回款、应收或存货相关说明。", "估值与增长需对应期间和数据；新闻摘录不等于完整财报，不凭缺失字段给成长评分。"],
        "sources": [UPSTREAM + "growth_quality.yaml"],
    },
}


def research_method_record(context, method):
    value = {**METHODS[method], "method": method,
             "usage": "General research method only. Not evidence that any signal, financial fact, or event applies to a security. Cite separately read public records for every stock-specific claim.",
             "implementation": "Toujing adapted checklist; no upstream scoring, trading levels or trend calculator executed."}
    return _record(kind="knowledge", subject_id=context.subject_id, account_id=context.account_id,
        currency=context.currency, as_of=context.as_of, method_id="dsa_research_checklist_adapted_v1",
        method_version="1", availability="complete", underlying_refs=tuple(value["sources"]),
        tags=(method, "general_knowledge_not_account_fact", "research_method_not_signal"),
        value=value, identity_extra=method)


@function_tool
def read_stock_research_method(ctx: RunContextWrapper,
        method: Literal["overview", "price_volume", "events", "business"]) -> str:
    """Read a DSA-adapted stock research checklist. Use for comprehensive public stock research, price/volume, events or business questions. Not a signal calculation or stock fact."""
    # Availability is a separate runtime fact, never inferred from a method.
    # This also lets the writer explain disabled search with a real receipt.
    access = getattr(ctx.context, "public_research", None)
    status = _record(kind="research_status", subject_id=ctx.context.subject_id,
        account_id=ctx.context.account_id, currency=ctx.context.currency, as_of=access.now() if access else datetime.now(timezone.utc),
        method_id="research_service_configuration_v1", method_version="1", availability="complete",
        underlying_refs=("runtime_configuration_not_market_fact",), tags=("service_configuration",),
        value={"search_enabled": bool(access and access.search_enabled),
               "search_configured": bool(access and access.search_key),
               "quotes_library_available": bool(access and access.quotes_available),
               "meaning": "Local configuration at this request, not a successful provider connection. Disabled/unconfigured search cannot retrieve news. The user can enable news search in AI and data service settings; it is independent of quotes."})
    knowledge = json.loads(_complete(ctx, research_method_record(ctx.context, method)))
    availability = json.loads(_complete(ctx, status))
    return json.dumps({"status": "complete", "records": [*knowledge["records"], *availability["records"]]}, ensure_ascii=False)


RESEARCH_POLICY = """
用户要求综合研究某只公开股票，而非只查一个数时，先读 read_stock_research_method(overview)。
按问题选 price_volume/events/business 方法，不必全读；方法不是个股证据，必须继续读实际公开资料。
研究综合路线：确认证券 -> 日线与报价/技术指标 -> 相关公开事件及反向信息 -> 经营报表 -> 按已有依据回答。
技术指标用 read_public_technical_indicators，不能从价格数组自己计算；预热不足的字段不要当作零。
经营研究先用 read_public_financials 取结构化报表，必要时用公告检索补充；保留报告期、单位和来源。
财报是当前读取的最新披露，不能冒充当年投资时可得的数据；不同报表期间不可混算。
当前日期使用请求中的 research_date，不用示例账户估值日期推断今天。用户未给期间时用近一个月，明确期间。
不把方法库内的规则当作已满足信号；没有工具结果的均线、量比、阻力位、评分不能自己生成。
纯概念提问仍读 read_financial_concept，不启动整套研究。某轮投资问题继续沿用账户工具。
整个账户范围可调用 get_hypothetical_trade_impact 计算拟交易；缺费用或其他必需输入时先澄清。
get_owned_period_comparison / get_owned_same_stock_comparison 只比较当前授权账户，先核对区间或轮次。
工具未注册（例如单轮范围）或返回不可用时再给对应页面入口；不得把当前仓位当作交易后结果。
""".strip()

RESEARCH_WRITER = """
按用户问题决定长度：简单追问保留简短回答；综合公开股票研究可用3至5个自然段，
依次组织核心观察、价格与量能、公开事件、经营资料、后续关注条件，只展示有依据的部分。
每段开头用短的自然语言主题句，不输出Markdown标题、表格或固定免责声明。
方法记录只支持concept段；实际行情、事件、经营数字必须在该段引用对应public记录。
运行时research_status记录可用于说明搜索开关状态，不把此类状态与纯方法混在同一个fact段。
未配置搜索时仍可回答取得的行情，具体提示开启新闻搜索，不把缺少搜索写成没有新闻。
没有趋势或财务计算结果时不编造信号、概率、估值或买卖点位。未执行的拟交易计算只提供页面入口。
不自造整数支撑位、阻力位或波动区间。若描述单日高低点，使用记录内的实际日期和价格，不把它改称支撑阻力。
最新日线可能尚未收盘时，不把该日成交量与完整交易日比较后称为缩量、资金退潮或量能不延续。
latest_bar_may_be_in_progress=true时，最新close字段称“最新日线记录价（当日尚未确认收盘）”，
不能称“最新收盘价”；过去已完成日期的收盘价仍可正常描述。
""".strip()
