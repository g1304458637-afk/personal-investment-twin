import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { useLocale } from "@/locales/LocaleProvider";
import { useDataMode } from "@/data/DataModeProvider";
import { comparisonResearchDemo as study } from "@/data/comparisonResearchDemo";
import type { PeriodKey } from "@/data/comparisonResearch";
import { ResearchPortfolioComparison } from "@/components/comparison/ResearchPortfolioComparison";
import { researchStudyCopy } from "./researchStudyCopy";
import "./research-study.css";

/** The comparison projection is always rooted in the selected showcase account. */
export function ResearchComparisonStudy({ kind }: { kind: "self" | "professional" }) {
  const { mode } = useDataMode();
  const { locale } = useLocale(); const c = researchStudyCopy[locale];
  const [period, setPeriod] = useState<PeriodKey>("full");
  const account = study.accounts.find(a => a.id === study.defaultSubject)!;
  const professional = study.accounts.find(a => a.id !== study.defaultSubject)!;
  const reference = professional.id;
  const name = (id: string) => study.names[id]?.[locale === "zh-CN" ? "zh" : "en"] ?? id;
  if (mode !== "demo") return <section className="iw-surface iw-disconnected"><FlaskConical size={28} /><h2>{c.realTitle}</h2><p>{c.realDetail}</p></section>;
  return <div className="research-study">
    <div className="sc-demo-context"><strong>{c.study}</strong><p>{c.scope}</p></div>
    {kind === "professional" && <div className="research-study__selectors flex flex-wrap items-end gap-6 my-7">
      <p className="max-w-md text-sm text-muted leading-6"><strong>{c.reference}:</strong> {name(reference)}</p>
      <label className="grid gap-2 text-sm text-muted">{c.period}<select className="rounded-xl border border-white/10 bg-slate-900/70 px-4 py-3 text-slate-100" value={period} onChange={e => setPeriod(e.target.value as PeriodKey)}>{(["full", "earlier", "recent"] as const).map(key => <option key={key} value={key}>{c[key]} · {account.periods[key].startDate} — {account.periods[key].endDate}</option>)}</select></label>
      <p className="max-w-md text-sm text-muted leading-6">{c.identity}</p>
    </div>}
    <ResearchPortfolioComparison key={`${kind}:${reference}:${period}`} left={account.periods[kind === "self" ? "earlier" : period]} right={kind === "self" ? account.periods.recent : professional.periods[period]} leftLabel={kind === "self" ? c.earlier : name(account.id)} rightLabel={kind === "self" ? c.recent : name(reference)} names={study.names} samePeriod={kind === "professional"} comparison={kind === "self" ? study.comparisons.self : study.comparisons.professional[reference][period]} />
    <p className="mt-6 text-sm text-muted leading-6">{c.boundary}</p>
  </div>;
}
