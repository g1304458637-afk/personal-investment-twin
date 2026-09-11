const zh = {
  periods: "两个时期", history: "当前在我的历史中", study: "年度投资示例 · Synthetic",
  scope: "以下以同一个合成示例账户的完整记录计算；不会替代或读取你的真实账户。",
  realTitle: "真实账户比较尚不可用", realDetail: "完整期间比较只在年度投资示例中提供。真实账户仍保持独立的本地授权范围。", openStudy: "",
  self: "我的年度投资", earlier: "前一个时期", recent: "后一个时期", full: "完整年度",
  selfIntro: "同一账户，两个连续时期。先看结果，再看钱的配置与操作如何变化。",
  professionalIntro: "在同一段时间，对照整个账户的结果、资金配置和操作。",
  balanced: "参照投资组合", focused: "参照投资组合", reference: "参照组合", period: "共同期间",
  identity: "参照组合是固定 Synthetic 场景，不代表真实专业人士，也不按收益筛选赢家。",
  earlierWindow: "2025/01/02 — 2025/07/02", recentWindow: "2025/07/02 — 2025/12/31", fullWindow: "2025/01/02 — 2025/12/31",
  boundary: "期间从起始日收盘状态开始，计入其后至结束日的成交；两期沿用完整历史持仓。",
};
const en: Record<keyof typeof zh, string> = {
  periods: "Two periods", history: "My current historical position", study: "My investment year · Synthetic",
  scope: "Calculated from the complete synthetic showcase account. It never substitutes for or reads your real account.",
  realTitle: "Real-account comparison is unavailable", realDetail: "Full-period comparison is available only for the investment-year showcase. Real accounts retain their separate local authorization scope.", openStudy: "",
  self: "My investment year", earlier: "Earlier period", recent: "Later period", full: "Full year",
  selfIntro: "One account, two consecutive periods. Start with outcomes, then explore allocation and decisions.",
  professionalIntro: "Compare whole-account outcomes, allocation and decisions over the same period.",
  balanced: "Reference portfolio", focused: "Reference portfolio", reference: "Reference portfolio", period: "Common period",
  identity: "Fixed synthetic scenarios, not real professionals or portfolios selected by winning outcomes.",
  earlierWindow: "2025/01/02 — 2025/07/02", recentWindow: "2025/07/02 — 2025/12/31", fullWindow: "2025/01/02 — 2025/12/31",
  boundary: "Each period starts at its opening date's closing state and includes subsequent trades through its end. Both retain the full earlier position history.",
};
export const researchStudyCopy = { "zh-CN": zh, "en-US": en };
