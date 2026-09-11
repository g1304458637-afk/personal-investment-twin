export const chartGuideIds = ["episode-process", "pretrade-allocation", "same-stock"] as const;

export type ChartGuideId = typeof chartGuideIds[number];

export type ChartGuideText = { zh: string; en: string };

export type ChartGuideStep = {
  anchor: string;
  title: ChartGuideText;
  detail: ChartGuideText;
};

export type ChartGuide = {
  id: ChartGuideId;
  title: ChartGuideText;
  steps: readonly ChartGuideStep[];
};

/**
 * These are presentation-only descriptions for already-rendered chart areas.
 * Anchor values are an allowlist consumed by ChartGuide, never model-provided
 * selectors or navigation targets.
 */
export const chartGuideCatalog: Record<ChartGuideId, ChartGuide> = {
  "episode-process": {
    id: "episode-process",
    title: { zh: "看懂这次投资过程", en: "Read this investment path" },
    steps: [
      { anchor: "episode-price-cost", title: { zh: "先定位实际成交", en: "Start with recorded executions" }, detail: { zh: "图中的标记对应已记录的实际成交；引导只会定位当前已加载投资中的成交。", en: "The markers are recorded executions. This guide only focuses an execution belonging to the Episode already on screen." } },
      { anchor: "episode-price-cost", title: { zh: "价格与成本分开看", en: "Compare market price and average cost" }, detail: { zh: "主图展示已记录的市场价格：K 线看开高低收，折线看价格路径。平均成本是你的持仓成本，对照它与市场价格的位置。", en: "The main chart shows recorded market prices: candles show open, high, low and close; a line shows the price path. Compare this with your average holding cost, which is a separate measure." } },
      { anchor: "episode-quantity", title: { zh: "再看持仓数量", en: "Then read held quantity" }, detail: { zh: "阶梯线表示页面已记录的持仓数量；每一次跳变都对应实际成交后的持仓变化。", en: "The stepped line shows the recorded held quantity. Each change follows an actual recorded execution." } },
    ],
  },
  "pretrade-allocation": {
    id: "pretrade-allocation",
    title: { zh: "查看交易前后的配置变化", en: "Read the allocation change" },
    steps: [
      { anchor: "pretrade-input", title: { zh: "先填写并检查", en: "Fill in the trade, then check it" }, detail: { zh: "先确认标的、方向、数量、价格和费用，再主动运行“检查变化”。引导不会替你提交或模拟。", en: "Confirm symbol, side, quantity, price, and fees, then choose Check changes yourself. The guide never submits or simulates a trade." } },
      { anchor: "pretrade-allocation", title: { zh: "对比已有结果", en: "Compare an existing result" }, detail: { zh: "检查完成后，这里才会显示已有结果中的交易前后配置；没有结果时，请先填写并检查，再看前后变化。", en: "After a completed check, this area shows the existing before-and-after allocation. Without a result, fill in the trade and check it before comparing changes." } },
    ],
  },
  "same-stock": {
    id: "same-stock",
    title: { zh: "同一标的，比较两条记录路径", en: "Compare two recorded paths" },
    steps: [
      { anchor: "same-stock-price", title: { zh: "先看共同价格区间", en: "Start with the shared price window" }, detail: { zh: "这里是当前已加载的共同市场价格区间；它只为比较两条已记录路径提供背景，不代表投资授权或建议。", en: "This is the currently loaded shared market-price window. It is context for comparing recorded paths, not an authorization or recommendation." } },
      { anchor: "same-stock-trades", title: { zh: "再看实际操作", en: "Then compare recorded operations" }, detail: { zh: "操作标记和详情来自页面已有记录；选择一笔操作可查看成交价、数量与前后持仓。", en: "Operation markers and details come from the records already on the page. Select one to see its execution price, quantity, and before-and-after holding." } },
      { anchor: "same-stock-quantity", title: { zh: "切换数量或平均成本", en: "Switch quantity or average cost" }, detail: { zh: "这里可以切换页面已有的持仓数量与平均成本路径，用来比较记录差异。", en: "Use this existing control to switch between held quantity and average-cost paths when comparing the recorded differences." } },
    ],
  },
};

export function isChartGuideId(value: unknown): value is ChartGuideId {
  return typeof value === "string" && (chartGuideIds as readonly string[]).includes(value);
}

export function chartGuideFor(value: unknown): ChartGuide | null {
  return isChartGuideId(value) ? chartGuideCatalog[value] : null;
}

function safeRouteId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(value);
}

/** Returns only registered relative routes; all caller supplied identifiers are encoded and allowlisted. */
export function chartGuideTarget(id: unknown, episodeId?: unknown, decisionId?: unknown): string | null {
  if (!isChartGuideId(id)) return null;
  if (id === "episode-process") {
    if (!safeRouteId(episodeId) || (decisionId !== undefined && !safeRouteId(decisionId))) return null;
    const query = new URLSearchParams({ section: "process", guide: id });
    if (typeof decisionId === "string") query.set("decision", decisionId);
    return `/investments/episodes/${encodeURIComponent(episodeId)}?${query.toString()}`;
  }
  if (episodeId !== undefined || decisionId !== undefined) return null;
  return id === "pretrade-allocation"
    ? "/pretrade?guide=pretrade-allocation"
    : "/investments/compare-example?guide=same-stock";
}
