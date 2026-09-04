import { ArrowRight, Braces, CircleCheck, Database, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { GlassPanel } from "@/components/common/GlassPanel";
import { MirrorOrb } from "@/components/common/MirrorOrb";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelfBaselineSection } from "@/components/twin/SelfBaselineSection";
import {
  explainabilityForConcept,
  explainabilityForEvidence,
  getEvidenceRecordById,
  selfBaseline,
  twinState,
} from "@/data/backendEvidence";
import type { TwinEpisodeRefView, TwinEvidenceRefView, TwinMetricStateView } from "@/data/twinState";
import type { DemoEvidenceRecord } from "@/demo/types";
import { useLocale } from "@/locales/LocaleProvider";

const metricLabels: Record<string, string> = {
  selection_episode_asset_return: "Selection",
  sizing_equal_weight_comparison: "Sizing",
  exit_timing_post_exit_asset_return: "Exit",
  recorded_trading_friction_comparison: "Friction",
  portfolio_concentration_hhi: "HHI",
  mean_daily_turnover: "Turnover",
  disposition_effect: "Disposition",
  loss_averaging_event_rate: "Loss Averaging",
};

function shortEvidenceId(value: string) {
  return `${value.slice(0, 11)}…${value.slice(-6)}`;
}

export default function MyTwinPage() {
  const { locale, t, formatNumber, formatPercent } = useLocale();
  const { currentSnapshot } = twinState;
  const date = (value: string) => new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));

  const metricValue = (metric: TwinMetricStateView) => {
    if (metric.value === null) return t("Not available");
    if (metric.metricId === "portfolio_concentration_hhi") return formatNumber(metric.value, 4);
    return formatPercent(metric.value, metric.metricId === "mean_daily_turnover" ? 2 : 1);
  };

  const evidenceValue = (reference: TwinEvidenceRefView, record: DemoEvidenceRecord | null) => {
    const state = currentSnapshot.behaviorState.find((item) => item.sourceEvidenceId === reference.evidenceId);
    if (state) return metricValue(state);
    if (!record || record.value === null) return t("Not available");
    if (typeof record.value === "number") return formatNumber(record.value, 4);
    const labels: Record<string, string> = {
      outperformed_baseline: "Above registered baseline",
      underperformed_baseline: "Below registered baseline",
      matched_baseline: "Matched registered baseline",
    };
    return t(labels[String(record.value)] ?? String(record.value));
  };

  const episodeRow = (episode: TwinEpisodeRefView) => {
    const state = episode.currentPositionState;
    return (
      <Link className="twin-episode-row" key={episode.episodeId} to={`/decisions/episodes/${episode.episodeId}`}>
        <div className="twin-episode-row__identity">
          <strong>{episode.instrumentId}</strong>
          <span>{date(episode.openedAt)} → {episode.closedAt ? date(episode.closedAt) : t("Present")}</span>
        </div>
        <dl className="twin-episode-row__facts">
          <div><dt>{t("Quantity")}</dt><dd>{state ? formatNumber(state.quantity, 2) : t("Not available")}</dd></div>
          <div><dt>{t("Average cost")}</dt><dd>{state?.averageCost === null || !state ? t("Not available") : formatNumber(state.averageCost, 2)}</dd></div>
          <div><dt>{t("Valuation price")}</dt><dd>{state?.valuationPrice === null || !state ? t("Not available") : formatNumber(state.valuationPrice, 2)}</dd></div>
        </dl>
        <span className="twin-episode-row__status">{t(episode.status === "open" ? "In progress" : "Closed")}<ArrowRight aria-hidden="true" /></span>
      </Link>
    );
  };

  return (
    <div className="page twin-page">
      <GlassPanel className="twin-archive-hero glass-reflection">
        <div className="twin-archive-hero__orb"><MirrorOrb size="lg" state="idle" /></div>
        <div className="twin-archive-hero__copy">
          <span className="eyebrow">{t("My Twin · Point-in-time archive")}</span>
          <h1>{t("What the evidence can say about me now")}</h1>
          <p>{t("This is the state formed from facts available by {date}. It is not an investor type, score, or prediction.", { date: date(currentSnapshot.snapshotAt) })}</p>
        </div>
        <div className="twin-archive-hero__asof">
          <span>{t("As of")}</span>
          <strong>{date(currentSnapshot.snapshotAt)}</strong>
          <small><ShieldCheck aria-hidden="true" /> {t("Synthetic / Demo")}</small>
        </div>
      </GlassPanel>

      <section className="twin-section" aria-labelledby="twin-now-heading">
        <header className="twin-section__heading">
          <div><span className="eyebrow">01</span><h2 id="twin-now-heading">{t("My state now")}</h2></div>
          <p>{t("A point-in-time summary copied from the deterministic TwinSnapshot.")}</p>
        </header>
        <dl className="twin-fact-strip twin-fact-strip--primary">
          <div><dt>{t("Active investment experiences")}</dt><dd>{currentSnapshot.dataQuality.openEpisodeCount}</dd></div>
          <div><dt>{t("Closed investment experiences")}</dt><dd>{currentSnapshot.dataQuality.closedEpisodeCount}</dd></div>
          <div><dt>{t("Portfolio state")}</dt><dd className="twin-fact-strip__status">{t(currentSnapshot.portfolioState.status === "available" ? "Available" : currentSnapshot.portfolioState.status === "not_started" ? "Not started" : "Not available")}</dd></div>
        </dl>
        <p className="twin-evidence-health">{t("System evidence health: {complete} complete · {insufficient} still maturing", { complete: currentSnapshot.evidenceSummary.complete, insufficient: currentSnapshot.evidenceSummary.insufficient })}</p>
      </section>

      <SelfBaselineSection summary={selfBaseline} />

      <section className="twin-section" aria-labelledby="twin-open-heading">
        <header className="twin-section__heading">
          <div><span className="eyebrow">03</span><h2 id="twin-open-heading">{t("Investment experiences in progress")}</h2></div>
          <p>{t("Open marks are current valuation facts, not exits.")}</p>
        </header>
        <div className="twin-row-list">
          {currentSnapshot.episodes.open.length > 0
            ? currentSnapshot.episodes.open.map(episodeRow)
            : <div className="twin-empty-row"><CircleCheck aria-hidden="true" /><span>{t("No open investment experiences at this snapshot.")}</span></div>}
        </div>
      </section>

      <section className="twin-section" aria-labelledby="twin-closed-heading">
        <header className="twin-section__heading">
          <div><span className="eyebrow">04</span><h2 id="twin-closed-heading">{t("Recently completed investment experiences")}</h2></div>
          <p>{t("Only Episodes referenced by this snapshot are shown.")}</p>
        </header>
        <div className="twin-row-list">
          {currentSnapshot.episodes.closed.length > 0
            ? currentSnapshot.episodes.closed.slice(0, 3).map(episodeRow)
            : <div className="twin-empty-row"><CircleCheck aria-hidden="true" /><span>{t("No closed investment experiences are available for this subject at this snapshot.")}</span></div>}
        </div>
      </section>

      <section className="twin-section" aria-labelledby="twin-evidence-heading">
        <header className="twin-section__heading">
          <div><span className="eyebrow">05</span><h2 id="twin-evidence-heading">{t("Observations supported by evidence")}</h2></div>
          <p>{t("These are observations, not scores, diagnoses, or permanent traits.")}</p>
        </header>
        <div className="twin-evidence-list">
          {[...currentSnapshot.decisionEvidenceRefs, ...currentSnapshot.behaviorEvidenceRefs].map((reference) => {
            const record = getEvidenceRecordById(reference.evidenceId);
            const view = explainabilityForEvidence(reference.evidenceId) ?? explainabilityForConcept(reference.metricId);
            return (
              <article className="twin-evidence-row" key={reference.evidenceId}>
                <div><span>{t(reference.evidenceKind === "decision_evidence" ? "Decision evidence" : "Behavior evidence")}</span><h3>{t(metricLabels[reference.metricId] ?? reference.metricId)}</h3></div>
                <strong>{evidenceValue(reference, record)}</strong>
                <div className="twin-evidence-row__meta"><StatusBadge status={reference.status} compact /><span>{t("N={count}", { count: record?.observation_count ?? "—" })}</span></div>
                <EvidenceExplainButton
                  view={view}
                  context={{ label: t("Evidence"), title: t(metricLabels[reference.metricId] ?? reference.metricId), detail: shortEvidenceId(reference.evidenceId) }}
                  label="View evidence"
                />
              </article>
            );
          })}
        </div>
      </section>

      <div className="twin-detail-grid">
        <section className="twin-section twin-section--compact" aria-labelledby="twin-quality-heading">
          <header className="twin-section__heading"><div><span className="eyebrow">06</span><h2 id="twin-quality-heading">{t("Evidence maturity")}</h2></div></header>
          <dl className="twin-quality-rows">
            <div><dt>{t("Evidence coverage")}</dt><dd>{currentSnapshot.dataQuality.referencedEvidenceCount} / {currentSnapshot.dataQuality.expectedEvidenceCount}</dd></div>
            <div><dt>{t("Complete")}</dt><dd>{currentSnapshot.evidenceSummary.complete}</dd></div>
            <div><dt>{t("Partial")}</dt><dd>{currentSnapshot.evidenceSummary.partial}</dd></div>
            <div><dt>{t("Insufficient evidence")}</dt><dd>{currentSnapshot.evidenceSummary.insufficient}</dd></div>
            <div><dt>{t("Data quality issues")}</dt><dd>{currentSnapshot.dataQuality.issueCount}</dd></div>
          </dl>
          {currentSnapshot.dataQuality.missingEvidenceMetrics.length > 0 ? <p className="twin-section__note">{t("Unavailable evidence: {metrics}", { metrics: currentSnapshot.dataQuality.missingEvidenceMetrics.map((item) => t(metricLabels[item] ?? item)).join(" · ") })}</p> : null}
        </section>

        <section className="twin-section twin-section--compact" aria-labelledby="twin-unknown-heading">
          <header className="twin-section__heading"><div><span className="eyebrow">07</span><h2 id="twin-unknown-heading">{t("Not formed yet")}</h2></div></header>
          <div className="twin-unknown-list">
            <div><span>{t("Position among comparable accounts")}</span><small>{t("Comparable-account context is not connected yet")}</small></div>
            <div><span>{t("Long-term notable changes")}</span><small>{t("No registered notable-change evidence yet")}</small></div>
          </div>
        </section>
      </div>

      <details className="twin-technical-details">
        <summary><Braces aria-hidden="true" />{t("Method and snapshot details")}</summary>
        <dl>
          <div><dt>{t("Snapshot ID")}</dt><dd>{currentSnapshot.snapshotId}</dd></div>
          <div><dt>{t("Subject ID")}</dt><dd>{currentSnapshot.subjectId}</dd></div>
          <div><dt>{t("Schema version")}</dt><dd>{currentSnapshot.schemaVersion}</dd></div>
          <div><dt>{t("Projection method")}</dt><dd>{currentSnapshot.projectionMethodId} · v{currentSnapshot.projectionMethodVersion}</dd></div>
          <div><dt>{t("Calculation code")}</dt><dd>{currentSnapshot.calculationCodeVersion}</dd></div>
          <div><dt>{t("Replay method")}</dt><dd>{currentSnapshot.portfolioState.replayMethodId ?? t("Not available")}</dd></div>
        </dl>
        <div className="twin-technical-details__limitations"><Database aria-hidden="true" /><p>{currentSnapshot.limitations.map((item) => t(item)).join(" ")}</p></div>
      </details>
    </div>
  );
}
