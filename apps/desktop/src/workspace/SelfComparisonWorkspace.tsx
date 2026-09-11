import { useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, History } from "lucide-react";
import { HistoricalMetricChart } from "@/components/charts/HistoricalMetricChart";
import type { BehaviorHistorySeries } from "@/data/behaviorHistory";
import { useDataMode } from "@/data/DataModeProvider";
import { allWindowsUseSameObservations, type SelfBaselineComparisonView, type SelfBaselineSummaryView, type SelfBaselineWindow } from "@/data/selfBaseline";
import { useLocale } from "@/locales/LocaleProvider";
import { historyWorkspaceData, registeredHistoryStudy } from "./historyWorkspaceData";
import { useLiquidCopy } from "./liquidCopy";
import { selfComparisonCopy } from "./selfComparisonCopy";
import { ResearchComparisonStudy } from "./ResearchComparisonStudy";
import { researchStudyCopy } from "./researchStudyCopy";
import "./self-comparison.css";

type HistorySeries = { hhi: BehaviorHistorySeries; turnover: BehaviorHistorySeries };

const metricOrder = ["portfolio_concentration_hhi", "mean_daily_turnover"] as const;
const windowOrder: readonly SelfBaselineWindow[] = ["rolling_3m", "rolling_12m", "lifetime"];

function formatDate(value: string | null, locale: string) {
  return value ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(value)) : "—";
}

function metricContent(metricId: string, c: typeof selfComparisonCopy["zh-CN"]) {
  return metricId === "portfolio_concentration_hhi"
    ? { label: c.concentration, detail: c.concentrationDetail, series: "hhi" as const }
    : { label: c.turnover, detail: c.turnoverDetail, series: "turnover" as const };
}

function bandExplanation(item: SelfBaselineComparisonView, c: typeof selfComparisonCopy["zh-CN"]) {
  if (item.status !== "complete") return c.insufficient;
  if (item.comparisonBand === "above_historical_iqr") return c.aboveRange;
  if (item.comparisonBand === "below_historical_iqr") return c.belowRange;
  return c.withinRange;
}

function valueFor(metricId: string, value: number | null, formatNumber: (value: number, digits?: number) => string, formatPercent: (value: number, digits?: number) => string) {
  if (value === null) return "—";
  return metricId === "mean_daily_turnover" ? formatPercent(value, 2) : formatNumber(value, 4);
}

export function SelfHistoryComparison({
  summary,
  history,
  periodComparison,
}: {
  summary: SelfBaselineSummaryView;
  history: HistorySeries;
  /** The showcase's two-period view complements, rather than alters, the account's self-history baseline. */
  periodComparison?: ReactNode;
}) {
  const { locale, formatNumber, formatPercent } = useLocale();
  const c = selfComparisonCopy[locale];
  const [window, setWindow] = useState<SelfBaselineWindow>(summary.defaultWindow);
  const date = (value: string | null) => formatDate(value, locale);
  const windowLabel = {
    rolling_3m: c.threeMonths,
    rolling_12m: c.twelveMonths,
    lifetime: c.allHistory,
  } satisfies Record<SelfBaselineWindow, string>;
  const cards = metricOrder.flatMap((metricId) => {
    const metric = summary.metrics.find((item) => item.metricId === metricId);
    const comparison = metric?.windows.find((item) => item.window === window);
    return metric && comparison ? [{ metric, comparison }] : [];
  });

  return <div className="sc-history">
    {periodComparison && <section className="sc-period-slot" aria-labelledby="self-period-heading">
      <header><span className="iw-kicker">{c.periodTitle}</span><h2 id="self-period-heading">{c.periodTitle}</h2><p>{c.periodDetail}</p></header>
      {periodComparison}
    </section>}
    <section className="sc-history__header" aria-labelledby="self-history-heading">
      <div><span className="iw-kicker">{c.currentHistory}</span><h2 id="self-history-heading">{c.currentHistory}</h2></div>
      <p>{c.historyIntro}</p>
    </section>
    <div className="sc-history__switch" role="group" aria-label={c.currentHistory}>
      {windowOrder.map((item) => <button key={item} type="button" aria-pressed={window === item} onClick={() => setWindow(item)}>{windowLabel[item]}</button>)}
    </div>
    <p className="sc-history__as-of">{c.currentAsOf.replace("{date}", date(summary.asOf))}</p>
    <div className="sc-history__cards">
      {cards.map(({ metric, comparison }) => {
        const content = metricContent(metric.metricId, c);
        const format = (value: number | null) => valueFor(metric.metricId, value, formatNumber, formatPercent);
        const distribution = comparison.status === "complete"
          && comparison.p25 !== null
          && comparison.median !== null
          && comparison.p75 !== null
          && comparison.selfHistoricalPercentile !== null
          ? { p25: comparison.p25, median: comparison.median, p75: comparison.p75, percentile: comparison.selfHistoricalPercentile }
          : null;
        return <article className="iw-surface sc-history__card" key={metric.metricId}>
          <header><div><h3>{content.label}</h3><p>{content.detail}</p></div><span>{windowLabel[window]}</span></header>
          <div className="sc-history__result">
            <div><span>{c.current}</span><strong>{format(comparison.currentValue)}</strong><small>{date(comparison.asOf)}</small></div>
            {distribution && <div><span>{c.median}</span><strong>{format(distribution.median)}</strong><small>{c.recordedRange} {date(comparison.observationStart)} – {date(comparison.observationEnd)}</small></div>}
          </div>
          <p className="sc-history__reading">{bandExplanation(comparison, c)}</p>
          {distribution && <div className="sc-history__distribution">
            <div
              className="sc-history__range"
              role="img"
              aria-label={`${content.label}: ${c.current} ${format(comparison.currentValue)}; P25 ${format(distribution.p25)}; ${c.median} ${format(distribution.median)}; P75 ${format(distribution.p75)}; ${c.personalPosition} ${c.percentile.replace("{value}", formatNumber(distribution.percentile, 0))}.`}
              style={{ "--sc-position": `${distribution.percentile}%` } as CSSProperties}
            >
              <span className="sc-history__range-line" aria-hidden="true" />
              <span className="sc-history__range-iqr" aria-hidden="true" />
              <span className="sc-history__range-tick sc-history__range-tick--p25" aria-hidden="true" />
              <span className="sc-history__range-tick sc-history__range-tick--median" aria-hidden="true" />
              <span className="sc-history__range-tick sc-history__range-tick--p75" aria-hidden="true" />
              <span className="sc-history__range-current" aria-hidden="true" />
            </div>
            <dl className="sc-history__distribution-values">
              <div><dt>{c.p25}</dt><dd>{format(distribution.p25)}</dd></div>
              <div><dt>{c.median}</dt><dd>{format(distribution.median)}</dd></div>
              <div><dt>{c.p75}</dt><dd>{format(distribution.p75)}</dd></div>
              <div className="sc-history__percentile"><dt>{c.personalPosition}</dt><dd>{c.percentile.replace("{value}", formatNumber(distribution.percentile, 0))}</dd></div>
            </dl>
          </div>}
          <div className="sc-history__chart"><span>{c.historyChart}</span><HistoricalMetricChart series={history[content.series]} label={content.label} singleValueLabel={format(comparison.currentValue)} percent={metric.metricId === "mean_daily_turnover"} /></div>
        </article>;
      })}
    </div>
    <p className="sc-history__basis">{c.basis}</p>
    {allWindowsUseSameObservations(summary) && <p className="sc-history__note">{c.sameObservations}</p>}
  </div>;
}

export function SelfComparisonWorkspace({ periodComparison }: { periodComparison?: ReactNode }) {
  const { mode, activeAccount, exampleAccount, examples, setExampleAccount, setMode } = useDataMode();
  const { locale } = useLocale();
  const c = selfComparisonCopy[locale]; const l = useLiquidCopy();
  const r = researchStudyCopy[locale];
  const [view, setView] = useState<"periods" | "history">("periods");
  const data = historyWorkspaceData(mode === "demo"
    ? { mode, subjectId: exampleAccount.subjectId, accountId: exampleAccount.accountId }
    : { mode, subjectId: activeAccount?.subject_id ?? null, accountId: activeAccount?.account_id ?? null });
  const study = registeredHistoryStudy();
  const example = examples.find((item) => item.subjectId === study.subjectId && item.accountId === study.accountId);
  const ready = data.availability === "ready" && data.history && data.selfBaseline;
  const unavailableDetail = data.availability === "real_unavailable" ? c.unavailableDetail : c.mismatchDetail;
  return <div className="iw-page research-study-page">
    <Link className="iw-action" to="/analysis"><ArrowLeft size={16} />{l.analysis}</Link>
    <header className="lg-editorial-heading"><span className="iw-kicker">{l.comparison}</span><h1>{l.selfTitle}</h1><p>{l.selfDetail}</p></header>
    <div className="sc-history__switch mb-7" role="group" aria-label={l.selfTitle}>{(["periods", "history"] as const).map(key => <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{r[key]}</button>)}</div>
    {view === "periods" ? (periodComparison ?? <ResearchComparisonStudy kind="self" />) : !ready ? <section className="iw-surface iw-disconnected"><History size={28} /><h2>{c.unavailable}</h2><p>{unavailableDetail}</p>{example && <button className="iw-primary" onClick={() => { setExampleAccount(example); setMode("demo"); }}>{c.example}</button>}</section> : <>
      {mode === "demo" && <p className="sc-demo-context">{c.demoContext}</p>}
      <SelfHistoryComparison summary={data.selfBaseline!} history={data.history!} />
    </>}
  </div>;
}
