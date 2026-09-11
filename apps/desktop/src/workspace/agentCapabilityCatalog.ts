/** User-facing capability truth: a page link is not an Agent tool. */
export type ServiceState = "checking" | "configured" | "unavailable";
export interface AgentServices {
  desktop: boolean;
  model: ServiceState;
  quotes: ServiceState;
  search: ServiceState;
  wholeAccount: boolean;
  synthetic?: boolean;
}
export const capabilityCatalog = [
  { id: "analyze", title: { zh: "看清我的投资", en: "Understand my investments" },
    benefit: { zh: "找到具体亏损的投资，读懂持仓与交易变化。", en: "Find losing investments and understand holdings and trading changes." },
    includes: { zh: "收益与回撤 · 单轮复盘 · 持仓集中度 · 操作与成本", en: "Returns & drawdown · Investment review · Concentration · Operations & costs" },
    prompt: { zh: "帮我找出亏损的投资，再看看具体操作和成本发生了什么变化。", en: "Find my losing investments and explain their recorded operations and cost changes." },
    needs: "model" },
  { id: "compare", title: { zh: "对照过去的自己", en: "Compare my history" },
    benefit: { zh: "对照两个时期，或同一只股票的两轮投资。", en: "Compare two periods or two investments in the same stock." },
    includes: { zh: "区间表现 · 同股两轮 · 实际日期 · 成本与操作差异", en: "Period results · Same-stock episodes · Actual dates · Cost & action differences" },
    prompt: { zh: "帮我比较两个时间段的账户表现，先告诉我有哪些日期记录、还需要我选择什么。", en: "Compare two periods of my account. First tell me which dates are recorded and what I need to choose." },
    needs: "account" },
  { id: "scenario", title: { zh: "试算一笔交易", en: "Try a trade scenario" },
    benefit: { zh: "先看交易会怎样改变现金、仓位和集中度。", en: "See how a trade would change cash, holdings and concentration." },
    includes: { zh: "示例账户 · 买卖数量与价格 · 显式费用 · 前后状态", en: "Example account · Size & price · Explicit fees · Before / after" },
    prompt: { zh: "在当前示例账户，假设以14.4元买入300股 SYN_GROWTH，费用为0元，对比交易前后的现金、持仓和集中度。", en: "In this example account, simulate buying 300 shares of SYN_GROWTH at CNY 14.4, with CNY 0 fees. Compare cash, holdings and concentration before and after." },
    needs: "scenario" },
  { id: "research", title: { zh: "研究一只股票", en: "Research a stock" },
    benefit: { zh: "把行情、公开事件和经营资料放在一起理解。", en: "Connect public prices, company events and business information." },
    includes: { zh: "A股行情 · MA / MACD / RSI / ATR · 财务报表 · 新闻与来源", en: "A-share prices · MA / MACD / RSI / ATR · Statements · News and sources" },
    prompt: { zh: "综合研究贵州茅台：对照近期价格与成交量、公开事件和经营资料，说明值得继续关注什么。", en: "Research Kweichow Moutai: compare recent price and volume, public events and business information, and explain what to follow." },
    needs: "research" },
  { id: "learn", title: { zh: "学懂股票知识", en: "Learn the essentials" },
    benefit: { zh: "用容易理解的语言解释概念，还可以继续追问。", en: "Get plain-language explanations and ask follow-up questions." },
    includes: { zh: "K线 · 成交量 · 成本与仓位 · 回撤 · 收益口径 · 穿透概念", en: "Candles · Volume · Cost and allocation · Drawdown · Return · Look-through concepts" },
    prompt: { zh: "K线实体和影线有什么区别？我应该先看什么，再看什么？", en: "How do candle bodies and wicks differ? What should I look at first and next?" },
    needs: "model" },
  { id: "chart", title: { zh: "带我看懂图表", en: "Make sense of the charts" },
    benefit: { zh: "解释图里的数字，定位到对应的投资过程。", en: "Understand chart values and open the relevant investment view." },
    includes: { zh: "投资过程 · 成本线与成交 · 交易前后扇形图 · 同股对比读法", en: "Investment timeline · Cost and trades · Allocation charts · Comparison charts" },
    prompt: { zh: "投资过程图里的平均成本线和成交标记怎么一起看？", en: "How do I read the cost line alongside my trade markers?" },
    needs: "guide" },
] as const;

export function capabilityStatus(needs: string, services: AgentServices, zh: boolean) {
  if (needs === "scenario" && !services.synthetic) return zh ? "目前仅支持示例账户试算" : "Currently available for example accounts only";
  if ((needs === "scenario" || needs === "account") && !services.wholeAccount) return zh ? "请切换到整个账户" : "Switch to the whole account";
  if (!services.desktop) return zh ? "网页预览 · 对话需桌面端" : "Preview · Chat requires desktop";
  if (services.model === "checking") return zh ? "正在检查模型配置" : "Checking model configuration";
  if (services.model !== "configured") return needs === "guide"
    ? (zh ? "页面指引可用 · AI讲解待配置" : "Page guides available · AI setup needed")
    : (zh ? "需要配置模型" : "Model setup needed");
  if (needs !== "research") return !services.wholeAccount && needs === "model"
    ? (zh ? "当前轮次可提问 · 全账户计算请切换范围" : "Ask about this investment · Switch scope for account calculations")
    : (zh ? "模型已配置 · 可提问" : "Model configured · Ask a question");
  if (services.quotes === "checking" || services.search === "checking") return zh ? "正在检查研究服务" : "Checking research services";
  if (services.quotes !== "configured") return services.search === "configured"
    ? (zh ? "可检索资料 · 行情库未就绪" : "Search configured · Quotes unavailable")
    : (zh ? "研究数据服务待配置" : "Research data setup needed");
  return services.search === "configured"
    ? (zh ? "行情库就绪 · 搜索已开启" : "Quote library ready · Search enabled")
    : (zh ? "行情库就绪 · 新闻搜索待开启" : "Quote library ready · Enable news search");
}

/** Do not turn an unsupported scope into a misleading ready-to-send example. */
export function capabilityScopeTarget(needs: string, services: AgentServices): "/data" | "/ask" | null {
  if (needs === "scenario" && !services.synthetic) return "/data";
  return (needs === "scenario" || needs === "account") && !services.wholeAccount ? "/ask" : null;
}
