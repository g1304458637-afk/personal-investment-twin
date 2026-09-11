import { useLocale } from "@/locales/LocaleProvider";
const zh = {
  title: "看清每一次投资，", titleEnd: "理解每一个决定。",
  eyebrow: "YOUR INVESTMENTS. IN PERSPECTIVE.",
  detail: "把成交记录还原成完整的投资经历。回看操作、比较不同路径，在事实与证据中，重新理解自己的选择。",
  enter: "进入投镜", example: "先看一个示例", about: "投镜能做什么", brand: "投镜介绍页",
  skip: "下次直接进入工作区", preferenceError: "浏览器无法保存此偏好，本次仍可正常进入。",
  sample: "Synthetic 示例 · 非真实账户", cardIntro: "一轮投资，一段完整经历", cardAction: "打开这轮复盘",
  cardNote: "来自已登记示例的确定性结果，不是收益预测。", footer: "让记录成为理解的起点，而不是给决策打分。",
  features: [
    { title: "还原投资过程", detail: "从建仓到退出，把价格、持仓与每笔成交放回同一条时间线。" },
    { title: "回看关键操作", detail: "查看已记录的变化，以及固定历史假设下的比较；不把结果好坏等同于决策能力。" },
    { title: "有依据地理解差异", detail: "分清确认的事实、可能的解释与仍缺少的信息。模型分析需运行环境与明确授权。" },
  ],
};
const en: typeof zh = {
  title: "See every investment.", titleEnd: "Understand each decision.",
  eyebrow: "YOUR INVESTMENTS. IN PERSPECTIVE.",
  detail: "Turn recorded executions into a complete investment journey. Revisit decisions, compare paths, and understand your choices through facts and evidence.",
  enter: "Enter Toujing", example: "Explore an example", about: "What Toujing does", brand: "About Toujing",
  skip: "Open my workspace next time", preferenceError: "This browser could not save the preference. You can still enter.",
  sample: "Synthetic example · Not a real account", cardIntro: "One investment. A complete journey.", cardAction: "Open this review",
  cardNote: "Deterministic results from a registered example. Not a return forecast.", footer: "A starting point for understanding, not a score for your decisions.",
  features: [
    { title: "Reconstruct the journey", detail: "From entry to exit, see prices, holdings and recorded executions on one timeline." },
    { title: "Revisit the decisions", detail: "Explore recorded changes and fixed historical alternatives. Outcomes are not a measure of investment skill." },
    { title: "Understand with evidence", detail: "Separate facts, possible explanations and missing information. Model analysis requires the runtime and explicit consent." },
  ],
};
export function useWelcomeCopy() { return useLocale().locale === "zh-CN" ? zh : en; }
