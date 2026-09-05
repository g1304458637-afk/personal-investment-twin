import { useState } from "react";
import { ArrowRight, FlaskConical, Layers3 } from "lucide-react";
import { useDataMode } from "@/data/DataModeProvider";
import { pretradeDemo } from "@/data/backendEvidence";
import { DecisionCheckPage } from "@/pages/DecisionCheckPage";
import { useWorkspaceCopy } from "./copy";

export function PretradeWorkspace() {
  const data = useDataMode(); const c = useWorkspaceCopy();
  const [entered, setEntered] = useState(false);
  const preview = data.mode === "demo" || entered;
  return <div className="iw-page iw-pretrade"><header className="iw-page-heading"><span className="iw-kicker">PRE-TRADE / SCENARIO LAB</span><h1>{c.pretradeTitle}</h1><p>{c.pretradeDetail}</p></header>
    {!preview ? <section className="iw-surface iw-disconnected"><Layers3 size={32} /><h2>{c.realPretrade}</h2><p>{c.realPretradeDetail}</p><button className="iw-primary" onClick={() => setEntered(true)}>{c.enterScenario}<ArrowRight size={16} /></button></section> : <><div className="iw-context-banner"><FlaskConical size={18} /><div><strong>{c.pretradeScope}</strong><p>{pretradeDemo.subjectId} · {pretradeDemo.proposedTime} · Synthetic</p></div><span className="iw-badge">{c.noPrediction}</span></div><DecisionCheckPage /></>}
    <section className="iw-surface iw-supplement"><span className="iw-kicker">HISTORICAL CONTEXT</span><h2>{c.similar}</h2><p>{c.similarDetail}</p><span className="iw-badge">{c.unavailable}</span></section>
  </div>;
}
