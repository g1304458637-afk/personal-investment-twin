import { ArrowRight, Database, FlaskConical, LockKeyhole, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { HistoricalMetricChart } from "@/components/charts/HistoricalMetricChart";
import { PeerRangeChart } from "@/components/charts/PeerRangeChart";
import { useDataMode } from "@/data/DataModeProvider";
import { isCompletePeerBenchmarkMetric } from "@/data/peerBenchmark";
import { useLocale } from "@/locales/LocaleProvider";

import { historyWorkspaceData, registeredHistoryStudy } from "./historyWorkspaceData";
import { useHistoryCopy } from "./historyCopy";
import "./history-workspace.css";

export type HistoryWorkspaceSection = "history" | "comparison";

const dateText = (value: string | null, locale: string) => value
  ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(value))
  : "—";


export function HistoryWorkspace({
  initialSection = "history",
  view,
}: {
  initialSection?: HistoryWorkspaceSection;
  /** Route-friendly alias used by the workspace router. */
  view?: HistoryWorkspaceSection;
}) {
  const { mode, activeAccount, exampleAccount, examples, setExampleAccount, setMode } = useDataMode();
  const { formatNumber, formatPercent, locale, t } = useLocale();
  const c = useHistoryCopy();
  const [section, setSection] = useState<HistoryWorkspaceSection>(view ?? initialSection);
  const scope = mode === "demo"
    ? { mode, subjectId: exampleAccount.subjectId, accountId: exampleAccount.accountId }
    : { mode, subjectId: activeAccount?.subject_id ?? null, accountId: activeAccount?.account_id ?? null };
  const data = useMemo(() => historyWorkspaceData(scope), [scope.mode, scope.subjectId, scope.accountId]);

  if (data.availability !== "ready" || !data.twin || !data.history || !data.selfBaseline) {
    const real = data.availability === "real_unavailable";
    const study = registeredHistoryStudy();
    const registeredExample = examples.find((item) => item.subjectId === study.subjectId && item.accountId === study.accountId);
    return <div className="iw-history-workspace"><section className="iw-hero"><span className="iw-eyebrow">{c.kicker}</span><h1 className="iw-title">{c.studyRequired}</h1><p className="iw-copy">{real ? c.realMissing : c.mismatch}</p><div className="iw-context"><span className="iw-chip"><Database size={14} /> {real ? c.unavailable : c.synthetic}</span>{data.subjectId && <span className="iw-chip">subject: {data.subjectId}</span>}</div></section>{real && (view ?? initialSection) === "comparison" ? <section className="iw-empty"><strong>{c.sameStock}</strong><p>{c.sameStockDetail}</p><Link className="iw-action" to="/ask">{c.ask} <ArrowRight size={15} /></Link><Link className="iw-action" to="/investments/compare-example">{c.openExample} <ArrowRight size={15} /></Link></section> : !real && registeredExample ? <section className="iw-empty"><strong>{c.studyAvailable}</strong><p>{c.studyDetail} ({study.subjectId} · {study.accountId} · {dateText(study.asOf, locale)})</p><button className="iw-tab" type="button" onClick={() => { setExampleAccount(registeredExample); setMode("demo"); }}>{c.openStudy} <ArrowRight size={15} /></button></section> : <div className="iw-empty">{c.noStudy}</div>}</div>;
  }

  const twin = data.twin.currentSnapshot;
  const hhi = data.history.hhi;
  const turnover = data.history.turnover;
  const behaviorState = twin.behaviorState;
  const metricValue = (id: string, value: number | null) => value === null ? c.unavailableState : id === "portfolio_concentration_hhi" ? formatNumber(value, 4) : formatPercent(value, 2);
  const statusText = (status: string) => ({ complete: c.complete, partial: c.partial, insufficient_evidence: c.insufficient_evidence, experimental: c.experimental }[status] ?? c.unavailable);
  const hhiCurrent = behaviorState.find((item) => item.metricId === "portfolio_concentration_hhi");
  const turnoverCurrent = behaviorState.find((item) => item.metricId === "mean_daily_turnover");
  const selfMetrics = data.selfBaseline.metrics.flatMap((metric) => metric.windows.filter((window) => window.window === data.selfBaseline!.defaultWindow));
  const peerMetrics = data.peer?.metrics.filter(isCompletePeerBenchmarkMetric) ?? [];
  const behavior = data.behaviorMetrics ?? [];
  const disposition = behavior.find((metric) => metric.id === "disposition");
  const lossAveraging = behavior.find((metric) => metric.id === "loss-averaging");

  return <div className="iw-history-workspace">
    <section className="iw-hero">
      <span className="iw-eyebrow">{c.kicker}</span>
      <h1 className="iw-title">{c.title}</h1>
      <p className="iw-copy">{c.intro}</p>
      <div className="iw-context"><span className="iw-chip"><FlaskConical size={14} /> {c.synthetic}</span><span className="iw-chip">{c.asOf} {dateText(data.asOf, locale)}</span><span className="iw-chip">subject: {data.subjectId}</span><span className="iw-chip">account: {data.accountId}</span></div>
    </section>
    <nav className="iw-tabs" aria-label={c.title}>
      <button className="iw-tab" type="button" role="tab" aria-selected={section === "history"} onClick={() => setSection("history")}>{c.history}</button>
      <button className="iw-tab" type="button" role="tab" aria-selected={section === "comparison"} onClick={() => setSection("comparison")}>{c.compare}</button>
    </nav>
    {section === "history" ? <>
      <section className="iw-grid iw-grid--two ih-summary-grid">
        <article className="iw-card iw-card--glow"><span className="iw-eyebrow">TWIN / TRACEABLE</span><h2>{c.currentSlice}</h2><p>{c.currentSliceDetail}</p><dl className="iw-list"><div><dt>{c.open}</dt><dd>{twin.dataQuality.openEpisodeCount}</dd></div><div><dt>{c.closed}</dt><dd>{twin.dataQuality.closedEpisodeCount}</dd></div><div><dt>{c.state}</dt><dd>{twin.portfolioState.status === "available" ? c.available : c.unavailableState}</dd></div><div><dt>{c.evidence}</dt><dd>{twin.evidenceSummary.complete} / {twin.evidenceSummary.insufficient}</dd></div></dl><details className="iw-provenance"><summary>{c.historyMethod}</summary><dl className="iw-list"><div><dt>Snapshot</dt><dd>{twin.snapshotId}</dd></div><div><dt>Projection</dt><dd>{twin.projectionMethodId} v{twin.projectionMethodVersion}</dd></div></dl></details></article>
        <article className="iw-card"><span className="iw-eyebrow">{c.behavior}</span><h2>{c.behavior}</h2><p>{c.behaviorDetail}</p><dl className="iw-list"><div><dt>{c.hhi}</dt><dd>{metricValue("portfolio_concentration_hhi", hhiCurrent?.value ?? null)}</dd></div><div><dt>{c.turnover}</dt><dd>{metricValue("mean_daily_turnover", turnoverCurrent?.value ?? null)}</dd></div><div><dt>{c.disposition}</dt><dd>{disposition ? t(disposition.primary, disposition.primaryValues) : "—"}</dd></div><div><dt>{c.loss}</dt><dd>{lossAveraging ? t(lossAveraging.primary, lossAveraging.primaryValues) : "—"}</dd></div></dl><p className="iw-notice">{disposition ? t(disposition.description, disposition.descriptionValues) : c.currentOnly} {lossAveraging ? t(lossAveraging.description, lossAveraging.descriptionValues) : ""}</p></article>
      </section>
      <section className="iw-grid iw-grid--two ih-chart-grid" style={{ marginTop: 16 }}>
        <article className="iw-card"><span className="iw-eyebrow">{c.registered}</span><h2>{c.hhi}</h2><p>{c.hhiDetail}</p><div className="iw-chart"><HistoricalMetricChart series={hhi} label={c.hhi} singleValueLabel={hhiCurrent ? metricValue(hhiCurrent.metricId, hhiCurrent.value) : c.unavailableState} /></div><div className="iw-notice">{c.historyMethod}: {hhi.methodId} v{hhi.methodVersion}</div></article>
        <article className="iw-card"><span className="iw-eyebrow">{c.registered}</span><h2>{c.turnover}</h2><p>{c.turnoverDetail}</p><div className="iw-chart"><HistoricalMetricChart series={turnover} label={c.turnover} singleValueLabel={turnoverCurrent ? metricValue(turnoverCurrent.metricId, turnoverCurrent.value) : c.unavailableState} percent /></div><div className="iw-notice">{c.historyMethod}: {turnover.methodId} v{turnover.methodVersion}</div></article>
      </section>
      <section className="iw-card" style={{ marginTop: 16 }}><span className="iw-eyebrow">SELF / HISTORY</span><h2>{c.myPast}</h2><p>{c.myPastDetail}</p><div className="iw-grid iw-grid--two" style={{ marginTop: 13 }}>{selfMetrics.map((metric) => <div className="iw-metric" key={metric.comparisonId}><div><strong>{metric.metricId === "portfolio_concentration_hhi" ? c.hhi : c.turnover}</strong><span className="iw-label">{dateText(metric.observationStart, locale)} → {dateText(metric.observationEnd, locale)} · N={metric.validN}</span></div><div className="iw-meta">{metric.selfHistoricalPercentile === null ? c.historyInsufficient : `${c.personalPercentile} ${formatNumber(metric.selfHistoricalPercentile, 0)}`}<br />{statusText(metric.status)}</div></div>)}</div><div className="iw-notice">{c.historyMethod}: {data.selfBaseline.defaultWindow}</div></section>
      <section className="iw-card" style={{ marginTop: 16 }}><span className="iw-eyebrow">EPISODES / SNAPSHOT</span><h2>{c.investmentExperiences}</h2><p>{c.investmentDetail}</p>{[...twin.episodes.open, ...twin.episodes.closed].map((episode) => <Link key={episode.episodeId} className="iw-episode" to={`/investments/episodes/${episode.episodeId}`}><span><strong>{episode.instrumentId} · {episode.status === "open" ? c.ongoing : c.ended}</strong><span>{dateText(episode.openedAt, locale)} → {episode.closedAt ? dateText(episode.closedAt, locale) : c.ongoing}</span></span><ArrowRight size={16} /></Link>)}</section>
    </> : <>
      <section className="iw-grid iw-grid--two"><article className="iw-card iw-card--glow"><span className="iw-eyebrow">SELF / PAST</span><h2>{c.selfPast}</h2><p>{c.selfPastDetail}</p>{data.twin.comparisons.map((comparison) => <div className="iw-metric" key={comparison.metricId}><div><strong>{comparison.metricId === "portfolio_concentration_hhi" ? c.hhi : c.turnover}</strong><span className="iw-label">{dateText(comparison.referenceDate, locale)} → {dateText(comparison.currentDate, locale)}</span></div><div className="iw-meta">{metricValue(comparison.metricId, comparison.pastValue)} → {metricValue(comparison.metricId, comparison.currentValue)}<br />{statusText(comparison.status)}</div></div>)}</article>
      <article className="iw-card"><span className="iw-eyebrow">SAME STOCK / CONSENT</span><h2>{c.sameStock}</h2><p>{c.sameStockDetail}</p><Link className="iw-action" to="/investments/compare-example">{c.openExample} <ArrowRight size={15} /></Link><div className="iw-preview"><b>{c.unavailable}</b><span><LockKeyhole size={14} style={{ display: "inline", verticalAlign: "-2px" }} /> {c.consent}</span></div></article></section>
      {data.peer ? <section className="iw-card" style={{ marginTop: 16 }}><span className="iw-eyebrow">COHORT / SYNTHETIC</span><h2>{c.cohort}</h2><p>{c.cohortDetail}</p><div className="iw-context" style={{ marginTop: 14 }}><span className="iw-chip"><UsersRound size={14} /> N={formatNumber(data.peer.cohortN)}</span><span className="iw-chip">{dateText(data.peer.cohort.observationStart, locale)} → {dateText(data.peer.cohort.observationEnd, locale)}</span><span className="iw-chip">{data.peer.cohort.id}</span></div><div className="iw-grid iw-grid--two" style={{ marginTop: 15 }}>{peerMetrics.map((metric) => <article className="iw-card" key={metric.id}><h3>{metric.label}</h3><PeerRangeChart metric={metric.chartMetric} /><dl className="iw-list"><div><dt>{c.current}</dt><dd>{metric.valueFormat === "percent" ? formatPercent(metric.chartMetric.user, 2) : formatNumber(metric.chartMetric.user, metric.valueFormat === "integer" ? 0 : 4)}</dd></div><div><dt>P25 / P50 / P75</dt><dd>{metric.valueFormat === "percent" ? [metric.chartMetric.p25, metric.chartMetric.median, metric.chartMetric.p75].map((value) => formatPercent(value, 2)).join(" / ") : [metric.chartMetric.p25, metric.chartMetric.median, metric.chartMetric.p75].map((value) => formatNumber(value, metric.valueFormat === "integer" ? 0 : 4)).join(" / ")}</dd></div><div><dt>{c.percentile}</dt><dd>{formatNumber(metric.chartMetric.percentile, 0)}</dd></div><div><dt>{c.metricN}</dt><dd>{metric.metricN}</dd></div></dl><div className="iw-notice">{metric.quantileMethod} · {metric.percentileMethod}</div></article>)}</div><div className="iw-notice">{c.cohortDefinition}: {data.peer.cohort.description} {c.sourceLimits}: {data.peer.cohort.limitations.join(" ")}</div></section> : null}
      <section className="iw-card" style={{ marginTop: 16 }}><span className="iw-eyebrow">{c.unavailable}</span><h2>{c.unavailable}</h2><div className="iw-grid iw-grid--two" style={{ marginTop: 12 }}><div className="iw-preview"><b>{c.realCohort}</b><span>{c.realCohortDetail}</span></div><div className="iw-preview"><b>{c.noHistory}</b><span>{c.noHistoryDetail}</span></div></div></section>
    </>}
  </div>;
}
