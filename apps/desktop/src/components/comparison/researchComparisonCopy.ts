import type { Locale } from "@/locales/LocaleProvider";

const zh = {
  fundDisclosure: "基金成分披露", holdingsAsOf: "成分截至",
  differenceDirection: "数值差额", pp: "个百分点", viewChange: "查看对应图表",
  result: "期间结果", return: "期间收益", drawdown: "最大回撤", volatility: "年化波动率", hhi: "直接持仓集中度 HHI", turnover: "日均换手强度",
  performance: "净值与回撤", nav: "净值", drawdownPath: "回撤", benchmark: "显示 Synthetic 市场基准", market: "Synthetic 市场基准",
  navExplanation: "双方净值从 100 起步，便于在不同资金规模下看清涨跌过程。", drawdownExplanation: "回撤表示净值相对此前高点的下降幅度；数值越接近 0，越接近此前高点。",
  behaviorExplanation: "PGR / PLR 分别描述盈利、亏损机会中已卖出的比例。亏损状态追加按“低于平均成本时的追加次数 / 全部合格追加次数”展示。它们描述操作，不给投资者打分。",
  benchmarkExplanation: "虚构市场价格指数，仅作同期背景；未计入交易费或分红。账户收益已反映期间内记录的费用。",
  samePeriod: "同期观察", separatePeriods: "两个独立期间", observation: "有效观测", noValue: "—", unavailable: "该指标没有足够的后端有效观测，未显示数值。",
  allocation: "期间末配置", direct: "直接持仓", underlying: "穿透后持仓", allocationDate: "配置日期", cashIncluded: "包含现金", selectedHolding: "选中的持仓",
  directWeight: "直接权重", indirectWeight: "间接权重", fundPath: "基金路径", noPath: "没有穿透路径记录", notHeld: "未持有", operations: "已记录操作", operationsDetail: "点击查看当日数量和平均成本的记录变化。",
  beforeAfterQuantity: "数量", beforeAfterCost: "平均成本", executionPrice: "成交价格", fee: "记录费用", date: "日期", operationKinds: { open_position: "建仓", add_position: "加仓", reduce_position: "减仓", close_position: "平仓" },
  noOperations: "该期间没有可展示的已记录操作。", behavior: "已记录的操作与集中度", hhiExplanation: "HHI 不含现金，描述风险资产在持仓间的集中程度；数值越高表示越集中。", turnoverExplanation: "日均换手以双边成交金额除以含现金的日末账户价值，再对有效观测日取平均。", fees: "记录费用", actionCount: "操作数", pgr: "PGR", plr: "PLR", pgrMinusPlr: "PGR − PLR", lossAdds: "亏损状态追加", noEligibleLossObservations: "本期没有合格的亏损观测，因此 PLR 未显示。", recovery: "回撤日期", peak: "此前高点", trough: "回撤低点", recovered: "恢复日期", notRecovered: "截至期末尚未恢复",
} as const;

const en: Record<keyof typeof zh, string | Record<string, string>> = {
  fundDisclosure: "Fund disclosure", holdingsAsOf: "Holdings as of",
  differenceDirection: "Difference", pp: "pp", viewChange: "View chart",
  result: "Period results", return: "Period return", drawdown: "Maximum drawdown", volatility: "Annualized volatility", hhi: "Direct-holdings HHI", turnover: "Mean daily turnover",
  performance: "NAV and drawdown", nav: "NAV", drawdownPath: "Drawdown", benchmark: "Show Synthetic market benchmark", market: "Synthetic market benchmark",
  navExplanation: "Both NAV paths start at 100 so the changes can be viewed independently of initial account size.", drawdownExplanation: "Drawdown is the fall in NAV from its prior high; a value nearer 0 is nearer that prior high.",
  behaviorExplanation: "PGR / PLR describe the proportion of gain/loss opportunities realized. Loss-state additions show additions below average cost / all eligible additions. These describe activity, not investor ability.",
  benchmarkExplanation: "A fictional price index for context, excluding transaction fees and dividends. Account returns reflect recorded fees within each period.",
  samePeriod: "Same observation period", separatePeriods: "Two independent periods", observation: "Valid observations", noValue: "—", unavailable: "This metric has insufficient valid backend observations, so no value is shown.",
  allocation: "End-period allocation", direct: "Direct holdings", underlying: "Look-through holdings", allocationDate: "Allocation date", cashIncluded: "Cash included", selectedHolding: "Selected holding",
  directWeight: "Direct weight", indirectWeight: "Indirect weight", fundPath: "Fund path", noPath: "No recorded look-through path", notHeld: "Not held", operations: "Recorded operations", operationsDetail: "Select an operation to see the recorded same-day quantity and average-cost change.",
  beforeAfterQuantity: "Quantity", beforeAfterCost: "Average cost", executionPrice: "Execution price", fee: "Recorded fee", date: "Date", operationKinds: { open_position: "Open", add_position: "Add", reduce_position: "Reduce", close_position: "Close" },
  noOperations: "There are no recorded operations to show for this period.", behavior: "Recorded activity and concentration", hhiExplanation: "HHI excludes cash and describes concentration across risky holdings; a higher value means more concentration.", turnoverExplanation: "Mean daily turnover is two-sided traded value divided by end-of-day account value including cash, averaged across valid observation days.", fees: "Recorded fees", actionCount: "Operations", pgr: "PGR", plr: "PLR", pgrMinusPlr: "PGR − PLR", lossAdds: "Loss-state additions", noEligibleLossObservations: "There were no qualifying loss observations in this period, so PLR is not shown.", recovery: "Drawdown dates", peak: "Prior high", trough: "Drawdown trough", recovered: "Recovery date", notRecovered: "Not recovered by period end",
};

export type ResearchComparisonCopy = typeof zh;
export function researchComparisonCopy(locale: Locale): ResearchComparisonCopy {
  return (locale === "zh-CN" ? zh : en) as ResearchComparisonCopy;
}
