import type { ChatTurn } from "@/data/agentChat";
import { chatErrorText } from "./agentChatCopy.ts";

/** Accept the app locale as well as short locale names for standalone consumers. */
export type AgentTurnStatusLocale = "zh" | "en" | "zh-CN" | "en-US";
export type AgentTurnPhase = "researching" | "reading" | "searching" | "quoting" | "writing" | "checking";

export interface AgentTurnStatusContent {
  kind: "running" | "failed" | "stopped" | "none";
  title: string;
  detail: string;
  diagnosticId?: string;
}

const knownPhases = new Set<AgentTurnPhase>(["researching", "reading", "searching", "quoting", "writing", "checking"]);
const diagnosticIdPattern = /^[a-f0-9]{12}$/;

function isChinese(locale: AgentTurnStatusLocale): boolean {
  return locale === "zh" || locale === "zh-CN";
}

export function agentTurnPhase(phase: string | undefined): AgentTurnPhase | undefined {
  return phase && knownPhases.has(phase as AgentTurnPhase) ? phase as AgentTurnPhase : undefined;
}

/** Do not render a backend-provided identifier unless it matches the issued diagnostic format. */
export function safeDiagnosticId(value: string | undefined): string | undefined {
  return value && diagnosticIdPattern.test(value) ? value : undefined;
}

export function agentTurnStatusContent(turn: Pick<ChatTurn, "status" | "phase" | "reason" | "diagnosticId">, locale: AgentTurnStatusLocale): AgentTurnStatusContent {
  const zh = isChinese(locale);
  if (turn.status === "running") {
    const phases: Record<AgentTurnPhase, [string, string]> = {
      researching: zh ? ["正在准备研究", "正在整理与问题相关的资料。"] : ["Preparing research", "Gathering the material needed for your question."],
      reading: zh ? ["正在查阅资料", "正在阅读相关账户记录和概念资料。"] : ["Reading materials", "Reviewing relevant account records and concepts."],
      searching: zh ? ["正在检索公开资料", "正在查找与问题相关的公开信息。"] : ["Searching public sources", "Looking for public information relevant to your question."],
      quoting: zh ? ["正在读取公开行情", "正在获取可核对的公开价格资料。"] : ["Reading public quotes", "Retrieving public price data that can be checked."],
      writing: zh ? ["正在组织回答", "正在把已找到的资料整理成回答。"] : ["Preparing your answer", "Organizing the material found into an answer."],
      checking: zh ? ["正在核对依据", "正在检查回答是否与可用资料一致。"] : ["Checking the evidence", "Checking that the answer matches the available material."],
    };
    const [title, detail] = agentTurnPhase(turn.phase)
      ? phases[agentTurnPhase(turn.phase)!]
      : zh ? ["正在处理请求", "正在准备可核对的回答。"] : ["Working on your request", "Preparing an answer that can be checked."];
    return { kind: "running", title, detail };
  }
  if (turn.status === "failed") {
    return {
      kind: "failed",
      title: zh ? "这次回答未完成" : "This answer did not complete",
      detail: chatErrorText(turn.reason, zh ? "zh-CN" : "en-US"),
      diagnosticId: safeDiagnosticId(turn.diagnosticId),
    };
  }
  if (turn.status === "stopped") {
    return {
      kind: "stopped",
      title: zh ? "已停止等待" : "Waiting stopped",
      detail: zh
        ? "这次请求可能仍在后台完成，未验证的回答不会显示。需要时可使用下方的“重试这条回答”。"
        : "This request may still finish in the background; an unverified answer will not be shown. Use “Retry this answer” below when you are ready.",
    };
  }
  return { kind: "none", title: "", detail: "" };
}
