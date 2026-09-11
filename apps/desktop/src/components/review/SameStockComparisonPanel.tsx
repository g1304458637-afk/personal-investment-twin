import { useEffect, useMemo, useState } from "react";
import type { CompareView } from "@/data/sameStock";
import { SameStockTimeline } from "@/components/charts/SameStockTimeline";
import { InvestmentChartWorkspace } from "@/components/charts/InvestmentChartWorkspace";
import { matchingComparisonChart } from "@/components/charts/sameStockStandardModel";
import { TimeSeriesFrame } from "@/components/charts/TimeSeriesFrame";
import { useDailyTimeNavigation } from "@/components/charts/useDailyTimeNavigation";
import { comparedDecision, sameStockParties, sameStockPartyLabel, sameStockTimelineTimes } from "@/components/charts/sameStockTimelineModel";
import { useLocale } from "@/locales/LocaleProvider";
import { showcaseInstrumentName, showcaseCharts, showcaseDemo } from "@/data/showcaseDemo";
import { differenceLabel, sameStockCopy } from "./sameStockCompareCopy";

export function SameStockComparisonPanel({ view, reviewSide = "A", onReviewSideChange, focusedDecisionId }: { view: CompareView; reviewSide?: "A" | "B"; onReviewSideChange?: (side: "A" | "B") => void; focusedDecisionId?: string | null }) {
  const { locale, t } = useLocale();
  const [selected, setSelected] = useState<string | null>(null);
  const [pathMode, setPathMode] = useState<"quantity" | "cost">("quantity");
  const [selectedOperationId, setSelectedOperationId] = useState<string | null>(null);
  const standardChart = useMemo(() => matchingComparisonChart(view, showcaseCharts), [view]);
  const comparison = useMemo(() => ({ view,
    highlightedIds: [...(view.differences.find(item => item.id === selected)?.aRefs ?? []), ...(view.differences.find(item => item.id === selected)?.bRefs ?? []), ...(focusedDecisionId ? [focusedDecisionId] : [])],
    labelA: view.a.subjectId === showcaseDemo.showcase.subject_id ? (locale === "zh-CN" ? "我的年度投资 · 示例账户" : "My annual investments · Example") : (locale === "zh-CN" ? "记录 A" : "Record A"),
    labelB: view.b.subjectId === `${showcaseDemo.showcase.subject_id}_REFERENCE` ? (locale === "zh-CN" ? "对照账户 · 模拟记录" : "Reference account · Simulated") : (locale === "zh-CN" ? "记录 B" : "Record B"),
  }), [view, locale, selected, focusedDecisionId]);
  const chartFocus = useMemo(() => {
    const difference = view.differences.find(item => item.id === selected);
    if (difference) return { id: difference.id, startAt: difference.start, endAt: difference.end };
    const decision = [...view.a.decisions, ...view.b.decisions].find(item => item.id === focusedDecisionId);
    if (decision) return { id: decision.id, startAt: decision.at, endAt: decision.at };
    return { id: view.id, startAt: view.a.start < view.b.start ? view.a.start : view.b.start, endAt: view.a.end > view.b.end ? view.a.end : view.b.end };
  }, [view, selected, focusedDecisionId]);
  const { observationTimes, boundaryTimes } = useMemo(() => sameStockTimelineTimes(view), [view]);
  const timeNavigation = useDailyTimeNavigation(view.id, observationTimes, boundaryTimes);
  useEffect(() => { setSelected(null); setSelectedOperationId(focusedDecisionId ?? null); }, [focusedDecisionId]);
  const c = sameStockCopy(locale);
  const displaySymbol = (symbol: string) => showcaseInstrumentName(symbol, locale, symbol);
  const partyLabel = (party: ReturnType<typeof sameStockParties>[number]) => sameStockPartyLabel(party, c.record, displaySymbol(party.symbol));
  const operationLabel = (kind: string) => c.operationKinds[kind as keyof typeof c.operationKinds] ?? t(kind);
  const date = (v: string) => v.slice(0, 10);
  const timestamp = (v: string) => v.replace("T", " ");
  const money = (v: number, currency: string) => new Intl.NumberFormat(locale, { style: "currency", currency }).format(v);
  const latestPrice = view.prices.at(-1);
  const selectedOperation = comparedDecision(view, selectedOperationId);
  const parties = sameStockParties(view);
  return <section className="space-y-5 lg-compare-panel">
    {onReviewSideChange ? <div className="iw-inset space-y-3 p-4">
      <p className="text-sm">{c.chooseRecord}</p><p className="text-xs text-muted">{c.chooseRecordDetail}</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label={c.chooseRecord}>{(["A", "B"] as const).map((side) => <button type="button" key={side} className={`rounded-full border px-3 py-1.5 text-sm ${reviewSide === side ? "border-primary bg-white/10" : "border-border text-muted"}`} aria-pressed={reviewSide === side} onClick={() => onReviewSideChange(side)}>{side === "A" ? c.reviewA : c.reviewB}</button>)}</div>
      <p className="text-xs text-muted">{c.selectedForReview}: {reviewSide}</p>
    </div> : null}
    <div className="lg-compare-results grid grid-cols-1 gap-5 border-y border-border py-5 md:grid-cols-2">{[view.a, view.b].map((s, i) => <div key={i} className="min-w-0 iw-inset">
      <p className="text-sm text-muted">{i === 0 ? `A · ${comparison.labelA}` : `B · ${comparison.labelB}`} · {displaySymbol(s.symbol)} · {t(s.tier === "synthetic" ? "Example account · Synthetic" : i === 0 ? "Your local derived facts" : "Shared derived facts")}</p>
      <p className="mt-2 font-mono text-2xl">{money(s.pnl, s.currency)}</p>
      <p className="text-sm">{c.fullResult} · {t(s.kind === "realized" ? "Final realized result" : "Current marked result")} · {s.returnValue === null ? "—" : new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(s.returnValue)}</p>
      <p className="mt-1 text-xs text-muted">{c.fullPeriod}: {timestamp(s.start)} — {timestamp(s.end)}</p>
      <p className="mt-1 text-xs text-muted">{t("Recorded entry / exit fees")}: {money(s.entryFees, s.currency)} / {money(s.exitFees, s.currency)}</p>
    </div>)}</div>
    <p className="text-xs text-muted">{c.resultBoundary}</p>
    {view.reasons.map((reason) => <p key={reason} className="text-sm text-warning">{t(reason)}</p>)}
    {view.status !== "unavailable" ? <>
      <div data-guide="same-stock-price" className="iw-inset grid gap-3 p-4 sm:grid-cols-2"><div><p className="text-xs text-muted">{c.sharedWindow}</p><p className="mt-1 font-mono text-sm">{view.start && view.end ? `${timestamp(view.start)} — ${timestamp(view.end)}` : "—"}</p><p className="mt-1 text-xs text-muted">{c.sharedWindowDetail}</p></div>{latestPrice ? <div><p className="text-xs text-muted">{c.latestPrice}</p><p className="mt-1 font-mono text-xl">{money(latestPrice.value, view.a.currency)}</p><p className="mt-1 text-xs text-muted">{c.observedAt}: {date(latestPrice.at)} · {c.dailyLabel}</p></div> : null}</div>
      {view.prices.length <= 1 ? <p className="text-sm text-warning">{c.noTrend}</p> : null}
      {standardChart ? <InvestmentChartWorkspace entry={standardChart.entry} market={standardChart.market} comparison={comparison} focus={chartFocus} onSelectDecision={setSelectedOperationId} /> : <TimeSeriesFrame title={c.operations} subtitle={`${c.fullPaths} ${c.noAccountWeight}`} navigation={timeNavigation} toolbar={<div data-guide="same-stock-quantity" className="flex rounded-full border border-border p-1" role="group" aria-label={c.positionPath}>{(["quantity", "cost"] as const).map((mode) => <button type="button" key={mode} aria-pressed={pathMode === mode} className={`rounded-full px-3 py-1 text-xs ${pathMode === mode ? "bg-white/10" : "text-muted"}`} onClick={() => setPathMode(mode)}>{mode === "quantity" ? c.quantity : c.averageCost}</button>)}</div>}>
        <div className="mb-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted" aria-label={c.identityLegend}>
          <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 rounded-full bg-[#a4b9c9]" aria-hidden="true" />{c.sharedMarketLine}</span>
          {parties.map((party) => <span className="inline-flex items-center gap-2" key={party.id}><span className="size-2.5 rounded-full" style={{ backgroundColor: party.color }} aria-hidden="true" />{partyLabel(party)}</span>)}
          <span>● {operationLabel("open_position")}　◆ {operationLabel("add_position")}　▲ {operationLabel("reduce_position")}　■ {operationLabel("close_position")}</span>
        </div>
        <div data-guide="same-stock-trades"><SameStockTimeline view={view} selected={selected} pathMode={pathMode} focusedDecisionId={focusedDecisionId} selectedDecisionId={selectedOperationId} timeNavigation={timeNavigation} onSelectDecision={setSelectedOperationId} /></div>
        {selectedOperation ? <div className="mt-3 rounded-xl border border-border/80 bg-black/10 p-3" data-selected-operation={selectedOperation.decision.id}>
          <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-xs text-muted">{c.selectedOperation}</p><p className="mt-1 text-sm">{partyLabel(selectedOperation.party)} · {operationLabel(selectedOperation.decision.kind)}</p></div><button type="button" className="text-xs text-muted hover:text-foreground" onClick={() => setSelectedOperationId(null)}>{c.clearSelection}</button></div>
          <p className="mt-2 font-mono text-xs text-muted">{c.exactTime}: {timestamp(selectedOperation.decision.at)}</p>
          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-3"><p>{c.executionQuantity}: <span className="font-mono">{selectedOperation.decision.quantity}</span></p><p>{c.positionQuantity}: <span className="font-mono">{selectedOperation.decision.before} → {selectedOperation.decision.after}</span></p><p>{t("Execution price")}: <span className="font-mono">{money(selectedOperation.decision.price, selectedOperation.party.currency)}</span></p><p className="sm:col-span-3">{c.averageCost}: <span className="font-mono">{selectedOperation.decision.costBefore === null ? "—" : money(selectedOperation.decision.costBefore, selectedOperation.party.currency)} → {selectedOperation.decision.costAfter === null ? "—" : money(selectedOperation.decision.costAfter, selectedOperation.party.currency)}</span></p></div>
        </div> : <p className="mt-3 text-xs text-muted">{c.selectedOperationDetail}</p>}
      </TimeSeriesFrame>}
      <h2 className="text-lg">{c.visibleDifferences}</h2><p className="text-xs text-muted">{c.visibleDifferencesDetail}</p>
      {view.differences.length ? view.differences.slice(0, 3).map((d) => <button type="button" key={d.id} className={`block w-full border-b border-border px-2 py-3 text-left text-sm ${selected === d.id ? "bg-white/5" : ""}`} onClick={() => setSelected(selected === d.id ? null : d.id)} aria-pressed={selected === d.id}>
        <span>{differenceLabel(locale, d.dimension)} · A {d.a} / B {d.b}</span><span className="ml-2 text-muted">{c.showOnChart}</span><span className="mt-1 block font-mono text-xs text-muted">{timestamp(d.start)} — {timestamp(d.end)}</span>
      </button>) : <p className="text-sm text-muted">{t("No difference in recorded decision counts within this window.")}</p>}
    </> : null}
    <details className="border-t border-border pt-3 text-xs text-muted"><summary className="cursor-pointer">{t("Why this comparison / sources")}</summary><p className="mt-3 font-mono">{view.method} · {view.version}</p>{view.limitations.map((s) => <p className="mt-2" key={s}>{t(s)}</p>)}{view.differences.map((d) => <p className="mt-2 break-all font-mono" key={d.id}>{d.refs.join(" · ")}</p>)}</details>
  </section>;
}
