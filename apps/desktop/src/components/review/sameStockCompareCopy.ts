import type { Locale } from "@/locales/LocaleProvider";

const zh = {
  chooseRecord: "从哪一方的记录开始复盘？",
  chooseRecordDetail: "选择 A 或 B，下方的分析对象会跟随这轮投资。",
  reviewA: "用 A 记录复盘",
  reviewB: "用 B 记录复盘",
  selectedForReview: "当前用于决策复盘",
  fullPeriod: "完整投资期间",
  fullResult: "完整期间结果",
  sharedWindow: "共同观察区间",
  sharedWindowDetail: "共同区间只用于并列查看已记录的价格和操作；不计算共同区间收益。",
  latestPrice: "最近已记录市场价格",
  observedAt: "观察日期",
  operations: "同一行情，不同的操作与持仓",
  positionPath: "持仓路径",
  quantity: "数量",
  averageCost: "平均成本",
  quantityPath: "实际持仓数量",
  averageCostPath: "已记录平均成本",
  exactTime: "精确记录时间",
  dailyLabel: "日度观察日期",
  visibleDifferences: "可核对的操作差异",
  visibleDifferencesDetail: "点选一项，在时间图中回到对应操作。",
  showOnChart: "在时间图中定位",
  noTrend: "仅有一个共同市场观察点，未绘制趋势。",
  commonMarket: "共同已记录市场价格",
  fullPaths: "两侧均保留完整持仓状态路径",
  resultBoundary: "完整期间结果不会被改写为共同区间表现，也不代表能力比较。",
  noAccountWeight: "不含账户权重或风险推断。",
  pricePane: "共同日度市场价格",
  operationPane: "A/B 已记录操作",
  record: "记录",
  marketPriceUnit: "市场价格",
  executionMarkers: "执行标记",
  executionQuantity: "执行数量",
  positionQuantity: "持仓数量",
  selectedOperation: "已选操作",
  selectedOperationDetail: "点击买卖标记，查看是谁在何时操作，以及数量和成本怎样变化。",
  clearSelection: "清除选择",
  identityLegend: "记录身份与图例",
  sharedMarketLine: "共同已记录市场价格线",
  operationKinds: { open_position: "建仓", add_position: "加仓", reduce_position: "减仓", close_position: "清仓" },
} as const;

type SameStockCopy = {
  [Key in keyof typeof zh]: Key extends "operationKinds"
    ? Record<keyof typeof zh.operationKinds, string>
    : string;
};

const en: SameStockCopy = {
  chooseRecord: "Whose record would you like to explore?",
  chooseRecordDetail: "Choose A or B. The analysis below will follow that investment.",
  reviewA: "Review record A",
  reviewB: "Review record B",
  selectedForReview: "Currently used for decision review",
  fullPeriod: "Full investment period",
  fullResult: "Full-period result",
  sharedWindow: "Common observation window",
  sharedWindowDetail: "The common window is only for viewing recorded prices and operations together; no common-window return is calculated.",
  latestPrice: "Latest recorded market price",
  observedAt: "Observation date",
  operations: "One market, different trades and holdings",
  positionPath: "Position path",
  quantity: "Quantity",
  averageCost: "Average cost",
  quantityPath: "Actual position quantity",
  averageCostPath: "Recorded average cost",
  exactTime: "Exact recorded time",
  dailyLabel: "Daily observation date",
  visibleDifferences: "Verifiable operation differences",
  visibleDifferencesDetail: "Select an item to revisit the corresponding operations on the timeline.",
  showOnChart: "Locate on timeline",
  noTrend: "Only one shared market observation exists, so no trend is drawn.",
  commonMarket: "Shared recorded market price",
  fullPaths: "Both sides retain their complete recorded position-state paths",
  resultBoundary: "Full-period results are not rewritten as common-window performance or an ability comparison.",
  noAccountWeight: "No account weight or risk inference is shown.",
  pricePane: "Shared daily market price",
  operationPane: "Recorded A/B operations",
  record: "Record",
  marketPriceUnit: "Market price",
  executionMarkers: "Execution markers",
  executionQuantity: "Execution quantity",
  positionQuantity: "Position quantity",
  selectedOperation: "Selected operation",
  selectedOperationDetail: "Select a trade marker to see who traded, when, and how quantity and cost changed.",
  clearSelection: "Clear selection",
  identityLegend: "Record identity and legend",
  sharedMarketLine: "Shared recorded market-price line",
  operationKinds: { open_position: "Open", add_position: "Add", reduce_position: "Reduce", close_position: "Close" },
};

export function sameStockCopy(locale: Locale) {
  return locale === "zh-CN" ? zh : en;
}

export function differenceLabel(locale: Locale, dimension: string) {
  const labels: Record<string, readonly [string, string]> = {
    add_position: ["加仓次数", "Additions"],
    reduce_position: ["减仓次数", "Reductions"],
    cost_raising_additions: ["抬高平均成本的加仓", "Cost-raising additions"],
    reductions_before_recorded_trough: ["记录低点前的减仓", "Reductions before the recorded trough"],
  };
  return labels[dimension]?.[locale === "zh-CN" ? 0 : 1] ?? dimension;
}
