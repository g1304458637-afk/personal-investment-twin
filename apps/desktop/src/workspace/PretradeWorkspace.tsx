import { useState } from "react";
import { ArrowRight, FlaskConical, Layers3 } from "lucide-react";
import { useDataMode } from "@/data/DataModeProvider";
import { pretradeDemo } from "@/data/backendEvidence";
import { exampleAccountLabel } from "@/data/accountContext";
import { DecisionCheckPage } from "@/pages/DecisionCheckPage";
import { useWorkspaceCopy } from "./copy";
import { useLocale } from "@/locales/LocaleProvider";
import { pretradeCopy } from "@/locales/pretrade";

export function PretradeWorkspace() {
  const data = useDataMode(); const c = useWorkspaceCopy();
  const { locale } = useLocale(); const p = pretradeCopy[locale];
  const [entered, setEntered] = useState(false);
  const preview = data.mode === "demo" || entered;
  const selectedDemoScenario = data.mode === "demo" && data.exampleAccount.subjectId === pretradeDemo.subjectId;
  const scenarioAccountName = exampleAccountLabel(data.exampleAccount, locale);
  return <div className="iw-page iw-pretrade" data-scenario-subject={preview ? pretradeDemo.subjectId : undefined}><header className="iw-page-heading"><span className="iw-kicker">PRE-TRADE / SCENARIO LAB</span><h1>{c.pretradeTitle}</h1><p>{c.pretradeDetail}</p></header>
    {!preview ? <section className="iw-surface iw-disconnected"><Layers3 size={32} /><h2>{c.realPretrade}</h2><p>{c.realPretradeDetail}</p><button className="iw-primary" onClick={() => setEntered(true)}>{c.enterScenario}<ArrowRight size={16} /></button></section> : <><div className="iw-context-banner"><FlaskConical size={18} /><div><strong>{selectedDemoScenario ? scenarioAccountName : p.example}</strong><p>Synthetic · {pretradeDemo.proposedTime.slice(0, 10)}</p></div></div><DecisionCheckPage /></>}
    <section className="iw-surface iw-supplement"><span className="iw-kicker">HISTORICAL CONTEXT</span><h2>{c.similar}</h2><p>{c.similarDetail}</p><span className="iw-badge">{c.unavailable}</span></section>
  </div>;
}
