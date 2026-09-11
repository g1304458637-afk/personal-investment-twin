"""V2 read projections over existing outcome/replay builders; no new formulas.

Knowledge entries describe registered Toujing methods, not market predictions.
They are deliberately separate from the user's account facts.
"""
from dataclasses import asdict
from collections import Counter

from src.agents.account_review_sources import _record, _last_scalar
from src.attribution.decision_outcome import build_actual_outcomes
from src.presentation.runtime_episode import json_value


KNOWLEDGE = {
    "technical_indicators": {
        "title": "均线、MACD、RSI与ATR / Moving averages, MACD, RSI and ATR",
        "content": "MA是市场收盘价的移动平均，不是用户的持仓成本。SMA对窗口内收盘价等权；"
        "这里EMA以首个完整窗口SMA初始化后递推。MACD使用EMA12减EMA26，信号线是其EMA9，"
        "这里柱值为差值减信号线，不乘2；与使用两倍柱值的图表比较时必须先统一口径。"
        "RSI14使用Wilder平滑涨跌幅，描述相对强弱；ATR14使用Wilder平滑真实波幅，单位为价格。"
        "这里的量比是最新完整日成交量除以前5个完整日均量，不是盘中实时量比。"
        "这些是历史行情的描述，数值和参数要一起看，不能仅凭交叉或高低值保证后续涨跌。"
        "预热期不足、停牌缺值或未收盘时，需要保留数据状态，不能填零或假装已有完整指标。",
        "method_refs": ["public_ohlcv_indicators_v1"],
    },
    "financial_statements": {
        "title": "财务报表与经营指标 / Financial statements and business metrics",
        "content": "利润表描述一个期间的收入和利润，资产负债表描述报告期末的资产和负债，"
        "现金流量表描述期间现金的流入流出。净利润不等于经营现金流，归母净利润也不等于含少数股东损益的净利润。"
        "ROE、毛利率、净利率需说明报告期和百分比口径；资产负债率使用同一张资产负债表的负债除以资产。"
        "季度累计值不能直接当单季值，万元与元不可混算。当前取得的最新或修订财报，不证明投资当时已经披露。"
        "缺失字段要区分未披露和服务未返回，不能用新闻摘录或价格走势替代报表数字。",
        "method_refs": ["akshare_structured_financials_v1"],
    },
    "concentration": {
        "title": "持仓比例、现金与集中度 / Holdings, cash and concentration",
        "content": "账户权重的分母包含现金；风险资产权重的分母排除现金。"
        "同一持仓用两个分母会得到不同百分比，不是矛盾。HHI是风险资产权重平方之和，"
        "描述资金在持仓之间的集中程度，不是收益、亏损概率或投资能力。"
        "可以描述最大持仓超过一半，但不能仅凭比例断言风险很低、暴露不极端或过度集中。"
        "资金权重不等于实际波动贡献：各产品涨跌幅和相关性不同，仅凭最大权重不能说它实际带来了最多波动或收益。"
        "基金是一个持仓产品，基金占比不等于某一家底层公司的占比；穿透需要基金成分数据。",
        "method_refs": ["hhi_security_weights_v1", "vectorbt_account_state_v1"],
    },
    "performance": {
        "title": "账户收益与单轮亏损 / Account return and investment losses",
        "content": "账户时间加权收益、单轮投资损益和回撤是不同问题。全年盈利可以同时存在"
        "部分投资亏损或期间回撤。已结束投资的实现结果与未结束投资的账面结果应分开说。"
        "找亏损来源先看各轮实际结果和具体期间，再读操作前后记录。操作与价格先后相邻"
        "不证明因果或动机；注册历史假设只解释指定条件下的结果差异，各场景差额不能相加。",
        "method_refs": ["account_fixed_cash_twr_empyrical_v1", "historical_decision_outcome_v1"],
    },
    "chart": {
        "title": "看懂投资过程图 / Reading an investment chart",
        "content": "K线描述同一周期的开盘、最高、最低、收盘价；蜡烛实体是开收之间，影线延伸到高低。"
        "折线只展示已提供的价格序列，不能当作完整K线。平均成本线来自用户持仓，"
        "不是市场移动平均线。成交标记对应实际操作，持仓数量阶梯的跳变对应操作后的数量变化。"
        "先看价格和成本，再对照成交标记及数量；图形本身不是未来方向的保证。",
        "method_refs": ["position_episode_lifecycle_v1"],
    },
    "turnover": {
        "title": "换手与自己的过去 / Turnover and personal history",
        "content": "这里的日换手描述双边成交额相对账户价值，平均日换手是有效日观察的平均。"
        "换手变化描述交易活动变化，不自动等于过度交易。与自己的过去比较必须保持同一指标、"
        "单位和时间口径；历史四分位区间描述分布，不是考试分数，也不能单凭它解释亏损。",
        "method_refs": ["self_historical_distribution_v1"],
    },
    "candlestick": {
        "title": "K线实体与影线 / Candlestick body and wicks",
        "content": "一根K线描述同一周期的开盘、最高、最低、收盘。实体是开盘到收盘的区间："
        "收盘高于开盘通常画为阳线，收盘低于开盘通常画为阴线。上影线从实体上沿到最高价，"
        "下影线从实体下沿到最低价。影线表示该周期内曾到达但未被收盘保留的价格。"
        "OHLC只保留这四个价格，不记录最高价与最低价出现的先后、完整盘中路径，"
        "也不能给出盘中峰值之后的最大回撤。因此长实体、短影线不能推出‘中途回撤小’。"
        "单根K线不能单独证明趋势、反转或买卖时机；要与前后K线、成交量和自己的成本对照。"
        "图形本身不是未来方向的保证，也不构成交易指令。",
        "method_refs": ["position_episode_lifecycle_v1"],
    },
    "volume": {
        "title": "成交量怎么看 / Reading volume",
        "content": "成交量是该周期内的成交数量，描述交易活跃程度，不是涨跌原因。"
        "价涨量增只说明该周期成交更活跃，不能单独证明有人在吸筹或出货。"
        "周期成交总量没有说明成交发生在哪些价格；长影线加放量不能证明高低点附近换手较多，"
        "那需要逐笔或按价格分布的成交资料。也不能只凭缩量给K线的可信度或代表性打分。"
        "成交额是金额，成交量是数量，二者不能混用。账户里的成交标记来自你自己的操作，"
        "不是市场全部成交。没有对应方法时，不能把放量、缩量说成买卖信号。",
        "method_refs": ["position_episode_lifecycle_v1"],
    },
    "cost_position": {
        "title": "成本、仓位与加减仓 / Cost, position size and later trades",
        "content": "平均成本来自你自己的持仓与成交，不是市场均线。加仓会改变数量和平均成本，"
        "减仓或清仓按当时卖出价与对应成本结算已实现部分。仓位是持有数量或它占账户的资金比例，"
        "两种说法分母不同。建仓是第一次买入，不是加仓；清仓与减仓要分开计数。"
        "成本线穿过价格只描述关系，不是自动的对错判决。",
        "method_refs": ["historical_decision_outcome_v1", "vectorbt_account_state_v1"],
    },
    "drawdown": {
        "title": "回撤 / Drawdown",
        "content": "回撤描述一段净值从阶段性高点到随后低点的下落幅度，不是全年亏损，也不是单轮投资结果。"
        "最大回撤是观察期内最大的一段下落；max_drawdown_peak_at是这段回撤的起点，不是全年最高账户价值。"
        "账户可以全年盈利，同时经历过回撤，也可以有单轮投资亏损。回撤不是能力打分，"
        "也不能单独指出“主要因为哪一笔”。",
        "method_refs": ["account_fixed_cash_twr_empyrical_v1"],
    },
    "lookthrough": {
        "title": "分散与穿透 / Diversification and look-through",
        "content": "账户持仓分散看的是资金如何分布在不同产品上。基金是一个产品，基金权重不等于某一家"
        "底层公司的权重；要看底层暴露需要基金披露或穿透数据。产品集中与公司集中不是同一句话。"
        "HHI描述风险资产之间的集中程度，分母不含现金。仅凭最大权重不能说它带来了最多波动或收益，"
        "更不能据此给投资能力打分。",
        "method_refs": ["hhi_security_weights_v1"],
    },
}


def knowledge_record(context, topic):
    if topic not in KNOWLEDGE:
        raise ValueError("unknown_account_knowledge_topic")
    return _record(kind="knowledge", subject_id=context.subject_id, account_id=context.account_id,
        currency=context.currency, as_of=context.as_of, method_id="toujing_method_knowledge_v1",
        method_version="1", availability="complete", underlying_refs=tuple(KNOWLEDGE[topic]["method_refs"]),
        tags=(topic, "general_knowledge_not_account_fact"), value=KNOWLEDGE[topic],
        identity_extra=topic)


def compact_performance_path(performance):
    """Lossless source-table encoding; retain every observation and financial value.

    Daily points repeat the same execution provenance hundreds of times. This
    conversational read view interns only those arrays, not the financial data.
    The registered performance series and its provenance are never modified.
    """
    value = performance.as_dict()
    source_sets = {}
    keys = {}
    for point in value["points"]:
        sources = tuple(point.pop("source_refs"))
        if sources not in keys:
            key = f"sources_{len(keys)}"
            keys[sources] = key
            source_sets[key] = list(sources)
        point["source_set_key"] = keys[sources]
    value["point_source_sets"] = source_sets
    return value


def extend_conversation_context(context, *, lifecycle, executions, market, init_cash,
                                display_names, performance, source_refs, replay):
    actual = build_actual_outcomes(lifecycle, executions, market,
        subject_id=context.subject_id, account_id=context.account_id,
        analysis_as_of=lifecycle.as_of, init_cash=init_cash)
    outcomes = {item.episode_id: item for item in actual.episode_outcomes}
    rows = []
    def add(kind, value, *, episode_id=None, instrument_id=None):
        record = _record(kind=kind, subject_id=context.subject_id, account_id=context.account_id,
            currency=context.currency, as_of=context.as_of,
            method_id=("vectorbt_account_state_v1" if kind == "allocation" else
                       performance.method_id if kind == "performance_path" else actual.method_id),
            method_version=performance.method_version if kind == "performance_path" else "1",
            availability="complete", underlying_refs=source_refs, tags=("owned_account_projection",),
            value=value, episode_id=episode_id, instrument_id=instrument_id)
        context.conversation_records[record.ref] = record
    add("allocation", {
        "risk_asset_value": _last_scalar(replay.portfolio.asset_value(), "risk_asset_value"),
        "semantics": "Existing grouped vectorbt asset_value, excludes cash. Not a new sum by the agent.",
    })
    for episode in lifecycle.episodes:
        outcome = outcomes[episode.episode_id]
        operations = [asdict(item) for item in actual.decision_outcomes if item.episode_id == episode.episode_id]
        row = {"episode_id": episode.episode_id, "instrument_id": episode.instrument_id,
            "display_name": display_names.get(episode.instrument_id, episode.instrument_id),
            "opened_at": episode.opened_at, "closed_at": episode.closed_at,
            "status": episode.status, "result": asdict(outcome.actual_result),
            "operation_counts": dict(sorted(Counter(item["event_type"] for item in operations).items())),
            "trade_counts": dict(sorted(Counter(item["side"] for item in operations).items())),
            "operation_semantics": "open_position=建仓; add_position=加仓; reduce_position=减仓; close_position=清仓. First purchase is opening, not an add."}
        rows.append(row)
        add("episode_detail", {**row, "operations": operations}, episode_id=episode.episode_id,
            instrument_id=episode.instrument_id)
    add("episode_results", {"episodes": rows,
        "semantics": "Each result uses its own investment period; not additive counterfactual attribution."})
    if performance is not None:
        add("performance_path", compact_performance_path(performance))
    # Fail before a model call if any projection is not serializable.
    json_value([asdict(record) for record in context.conversation_records.values()])
