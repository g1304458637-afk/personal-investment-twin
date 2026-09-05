import { useEffect, useState } from "react";
import type { CompareView } from "@/data/sameStock";
import { SameStockTimeline } from "@/components/charts/SameStockTimeline";
import { useLocale } from "@/locales/LocaleProvider";

export function SameStockComparisonPanel({ view, focusedDecisionId }: { view: CompareView; focusedDecisionId?: string | null }) {
  const { locale, t } = useLocale();
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { setSelected(null); }, [focusedDecisionId]);
  const date = (v: string) => new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(v));
  const money = (v: number, currency: string) => new Intl.NumberFormat(locale, { style: "currency", currency }).format(v);
  return <section className="space-y-5">
    <div className="grid grid-cols-2 gap-5 border-y border-border py-5">{[view.a, view.b].map((s, i) => <div key={i} className="min-w-0">
      <p className="text-sm text-muted">{i === 0 ? "A" : "B"} · {s.symbol} · {t(s.tier === "synthetic" ? "Example account · Synthetic" : i === 0 ? "Your local derived facts" : "Shared derived facts")}</p>
      <p className="mt-2 font-mono text-2xl">{money(s.pnl, s.currency)}</p>
      <p className="text-sm">{t(s.kind === "realized" ? "Final realized result" : "Current marked result")} · {s.returnValue === null ? "—" : new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(s.returnValue)}</p>
      <p className="mt-1 text-xs text-muted">{date(s.start)} — {date(s.end)}</p>
      <p className="mt-1 text-xs text-muted">{t("Recorded entry / exit fees")}: {money(s.entryFees, s.currency)} / {money(s.exitFees, s.currency)}</p>
    </div>)}</div>
    <p className="text-xs text-muted">{t("Full-period results are not common-window performance or a skill ranking.")}</p>
    {view.reasons.map((reason) => <p key={reason} className="text-sm text-warning">{t(reason)}</p>)}
    {view.status !== "unavailable" ? <>
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted"><span>{t("Shared recorded market price")}</span><span>{view.start && view.end ? `${date(view.start)} — ${date(view.end)}` : "—"}</span></div>
      <SameStockTimeline view={view} selected={selected} focusedDecisionId={focusedDecisionId} />
      <p className="text-xs text-muted">● {t("open_position")}　◆ {t("add_position")}　▲ {t("reduce_position")}　■ {t("close_position")} · {t("Position shape (not risk)")}</p>
      <h2 className="text-lg">{t("Observable differences")}</h2>
      {view.differences.length ? view.differences.map((d) => <button key={d.id} className={`block w-full border-b border-border px-2 py-3 text-left text-sm ${selected === d.id ? "bg-white/5" : ""}`} onClick={() => setSelected(selected === d.id ? null : d.id)} aria-pressed={selected === d.id}>
        {t(d.dimension)} · A {d.a} / B {d.b}　<span className="text-muted">{t("Highlight both decision lanes")}</span>
      </button>) : <p className="text-sm text-muted">{t("No difference in recorded decision counts within this window.")}</p>}
    </> : null}
    <details className="border-t border-border pt-3 text-xs text-muted"><summary className="cursor-pointer">{t("Why this comparison / sources")}</summary><p className="mt-3 font-mono">{view.method} · {view.version}</p>{view.limitations.map((s) => <p className="mt-2" key={s}>{t(s)}</p>)}{view.differences.map((d) => <p className="mt-2 break-all font-mono" key={d.id}>{d.refs.join(" · ")}</p>)}</details>
  </section>;
}
