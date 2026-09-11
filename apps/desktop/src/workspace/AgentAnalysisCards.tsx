import { ChevronDown, Table2 } from "lucide-react";
import type { AgentAnalysisCard } from "@/data/agentAnalysisCards";
import "./agent-analysis-cards.css";

/** Values and explanations are supplied by the deterministic runtime projector. */
export function AgentAnalysisCards({ cards, locale }: { cards: AgentAnalysisCard[]; locale: string }) {
  const zh = locale === "zh-CN", lang = zh ? "zh" : "en";
  if (!cards.length) return null;
  return <div className="agent-analysis-cards" aria-label={zh ? "计算明细" : "Calculation details"}>
    {cards.map((card, index) => <details className="agent-analysis-card" key={card.id} open={index === 0}>
      <summary><Table2 size={16} aria-hidden="true"/><span>{card.title[lang]}</span><small>{zh ? "来自已引用记录" : "From cited records"}</small><ChevronDown size={15} aria-hidden="true"/></summary>
      <p className="agent-analysis-card__subtitle">{card.subtitle[lang]}</p>
      <div className="agent-analysis-card__scroll" tabIndex={0} role="region" aria-label={card.title[lang]}>
        <table><caption className="sr-only">{card.title[lang]} · {card.subtitle[lang]}</caption>
          <thead><tr><th scope="col">{zh ? "指标" : "Metric"}</th>{card.columns.map((column, i) => <th scope="col" key={i}>{column[lang]}</th>)}</tr></thead>
          <tbody>{card.rows.map((row, i) => <tr key={i}><th scope="row">{row.label[lang]}</th>{row.cells.map((cell, j) => <td key={j}>{cell[lang]}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <details className="agent-analysis-card__method"><summary>{zh ? "这些数字怎么看 · 计算口径与依据" : "Reading these numbers · Basis & evidence"}<ChevronDown size={13} aria-hidden="true"/></summary>
        <dl>{card.rows.map((row, i) => <div key={i}><dt>{row.label[lang]}</dt><dd>{row.explanation[lang]}</dd></div>)}</dl>
        {card.notes.length > 0 && <ul>{card.notes.map((note, i) => <li key={i}>{note[lang]}</li>)}</ul>}
        <p className="agent-analysis-card__ref">{zh ? "已引用记录" : "Cited record"}：<code>{card.source_ref}</code></p>
      </details>
    </details>)}
  </div>;
}
