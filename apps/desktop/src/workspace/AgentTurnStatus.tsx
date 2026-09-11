import type { ChatTurn } from "@/data/agentChat";
import { agentTurnStatusContent, type AgentTurnStatusLocale } from "./agentTurnStatusModel.ts";
import "./agent-turn-status.css";

export interface AgentTurnStatusProps {
  turn: ChatTurn;
  /** Supports the app's zh-CN/en-US locale values and concise zh/en callers. */
  locale: AgentTurnStatusLocale;
}

/** A factual activity/failure summary; it deliberately does not expose model reasoning. */
export function AgentTurnStatus({ turn, locale }: AgentTurnStatusProps) {
  const content = agentTurnStatusContent(turn, locale);
  if (content.kind === "none") return null;
  const role = content.kind === "failed" ? "alert" : "status";
  return <div className={`agent-turn-status agent-turn-status--${content.kind}`} role={role} aria-atomic="true">
    {content.kind === "running" && <span className="agent-turn-status__pulse" aria-hidden="true" />}
    <div>
      <strong>{content.title}</strong>
      <p>{content.detail}</p>
      {content.diagnosticId && <small>{locale === "zh" || locale === "zh-CN" ? "诊断编号" : "Diagnostic ID"}：{content.diagnosticId}</small>}
    </div>
  </div>;
}

export default AgentTurnStatus;
