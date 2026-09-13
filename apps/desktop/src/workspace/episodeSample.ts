/** Presentation-only routing. Never changes account, evidence or calculation scope. */
export const episodeSections = ["process", "executions", "evidence"] as const;
export type EpisodeSection = typeof episodeSections[number];
export function episodeSection(search: URLSearchParams): EpisodeSection {
  const value = search.get("section");
  return episodeSections.includes(value as EpisodeSection) ? value as EpisodeSection : "process";
}
export function episodeAnalysisTarget(episodeId: string): string {
  return `/investments/episodes/${encodeURIComponent(episodeId)}?section=analysis`;
}
export function isVisibleReviewPattern(code: string | undefined): boolean {
  return code === "consecutive_scaling_in" || code === "consecutive_scaling_out";
}
// Retired layout links preserve scope but always use the approved review.
export const isEpisodeSample = (_search: URLSearchParams) => true;
export function episodeSampleSearch(search: URLSearchParams, _enabled: boolean) {
  const next = new URLSearchParams(search);
  next.delete("layout");
  return next;
}
export const episodeSampleCopy = {
  "zh-CN": {
    enter: "投资复盘", leave: "旧版详情", label: "投资复盘",
    process: "投资过程", executions: "全部操作", evidence: "依据与来源",
    guide: "先看过程，再回看值得留意的操作。", factHint: "来自已有记录，不是决策评分。点击一项，图表会定位到对应区间。",
    focus: "查看这段操作", clear: "恢复完整投资期间", selected: "正在回看所选区间",
    analyzeTitle: "围绕这一轮，继续理解", analyzeHint: "分析、历史比较和事后备注都使用当前投资范围，不需要重新选择对象。",
    demoTitle: "本轮分析尚未连接", demoHint: "当前示例没有接通本轮投资的 Agent 分析。投资过程与历史依据仍可查看，不会用其他示例的答案替代。",
    nativeHint: "真实账户需在桌面端连接本地运行环境，并明确授权模型使用；网页展示不调用模型。",
    analysisBoundary: "不会根据结果好坏评价投资能力，也不会预测未来或推荐买卖。",
    operationsHint: "点击一笔操作，查看已有的前后状态、结果与历史比较。", sourceHint: "这里保留原始证据入口、方法和来源；它们不替代数据不足时的限制。",
  },
  "en-US": {
    enter: "Investment review", leave: "Legacy detail", label: "Investment review",
    process: "Investment journey", executions: "All actions", evidence: "Evidence & sources",
    guide: "Start with the journey. Revisit the recorded actions.", factHint: "Recorded facts, not a decision score. Select one to focus its interval in the chart.",
    focus: "Explore these actions", clear: "Show full investment period", selected: "Focused on the selected interval",
    analyzeTitle: "Understand this investment further", analyzeHint: "Analysis, historical comparisons and retrospective notes retain this investment’s scope.",
    demoTitle: "Analysis is not connected for this investment", demoHint: "Agent analysis is not connected for this example. Recorded history and evidence remain available; another example’s answers will not be substituted.",
    nativeHint: "Real accounts require the desktop runtime and explicit model consent. This browser preview does not call a model.",
    analysisBoundary: "Outcomes do not establish investment skill. No predictions or trading recommendations.",
    operationsHint: "Select an action for its recorded before/after state, outcome and historical comparison.", sourceHint: "Original evidence, methods and sources remain accessible. They do not override insufficient-data boundaries.",
  },
} as const;
/** Availability hint only; native runtime validates the exact registered Episode. */
export function hasDemoReviewSource(subject: string, account: string | null | undefined, episodeId?: string): boolean {
  void episodeId;
  return subject === "SYN_STUDY_SHOWCASE" && account === "SYN_STUDY_SHOWCASE";
}
