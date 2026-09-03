import { ArrowUpRight, CircleCheck, Database, History, Layers3, ShieldCheck } from "lucide-react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { MirrorOrb } from "@/components/common/MirrorOrb";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { twinState } from "@/data/backendEvidence";
import type { TwinMetricComparisonView, TwinMetricStateView } from "@/data/twinState";
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
  const { currentSnapshot, historicalSnapshots, comparisons } = twinState;
  const date = (value: string) => new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
  const metricState = (metricId: string) =>
    currentSnapshot.behaviorState.find((item) => item.metricId === metricId);
  const hhi = metricState("portfolio_concentration_hhi");
  const turnover = metricState("mean_daily_turnover");
  const metricValue = (metric: TwinMetricStateView) => {
    if (metric.value === null) return t("Not available");
    if (metric.metricId === "portfolio_concentration_hhi") return formatNumber(metric.value, 4);
    return formatPercent(metric.value, metric.metricId === "mean_daily_turnover" ? 2 : 1);
  };
  const comparisonValue = (comparison: TwinMetricComparisonView, value: number | null) => {
    if (value === null) return t("Not available");
    return comparison.metricId === "portfolio_concentration_hhi"
      ? formatNumber(value, 4)
      : formatPercent(value, 2);
  };
  const absoluteChange = (comparison: TwinMetricComparisonView) => {
    if (comparison.absoluteChange === null) return t("Not available");
    return comparison.metricId === "portfolio_concentration_hhi"
      ? formatNumber(comparison.absoluteChange, 4)
      : `${formatNumber(comparison.absoluteChange * 100, 2)} pp`;
  };
  const statusText = (status: TwinMetricStateView["status"]) => {
    const labels = {
      complete: "Complete",
      partial: "Partial",
      insufficient_evidence: "Insufficient evidence",
      experimental: "Experimental",
    } as const;
    return t(labels[status]);
  };

  return (
    <div className="page twin-page">
      <PageHeader
        eyebrow={t("My Twin · Demo Snapshot")}
        title={t("A living evidence profile")}
        description={t("A deterministic point-in-time view of registered evidence—not a score, prediction, or persistent investor identity.")}
      />

      <GlassPanel className="twin-identity glass-reflection">
        <div className="twin-identity__orb"><MirrorOrb size="lg" state="idle" /></div>
        <div className="twin-identity__copy">
          <span className="eyebrow">{t("Current snapshot")}</span>
          <h2>{currentSnapshot.subjectId}</h2>
          <p>{t("Deterministic point-in-time evidence view")}</p>
          <div>
            <span><CircleCheck /> {t("Deterministic backend export")}</span>
            <span><ShieldCheck /> {t("Synthetic provenance")}</span>
            <span><History /> {t("Snapshot date {date}", { date: date(currentSnapshot.snapshotAt) })}</span>
          </div>
        </div>
        <dl className="twin-identity__quality">
          <div>
            <dt>HHI</dt>
            <dd>{hhi ? metricValue(hhi) : "—"}</dd>
            <span>{hhi ? t("as of {date}", { date: date(hhi.asOf) }) : t("Not available")}</span>
          </div>
          <div>
            <dt>{t("Latest daily turnover")}</dt>
            <dd>{turnover ? metricValue(turnover) : "—"}</dd>
            <span>{turnover ? t("as of {date}", { date: date(turnover.asOf) }) : t("Not available")}</span>
          </div>
        </dl>
      </GlassPanel>

      <section className="twin-periods">
        <div className="twin-periods__header">
          <SectionHeading
            eyebrow={t("Self history")}
            title={t("Rebuildable point-in-time snapshots")}
            description={t("Only HHI and Turnover currently have registered historical series; later evidence is excluded from earlier snapshots.")}
          />
        </div>
        <div className="twin-period-grid">
          <GlassPanel className="twin-period-summary">
            <span className="eyebrow">{t("Historical coverage")}</span>
            <h3>{historicalSnapshots.length > 0 ? `${date(historicalSnapshots[0].snapshotAt)} – ${date(historicalSnapshots.at(-1)!.snapshotAt)}` : t("Not available")}</h3>
            <dl>
              <div><dt>{t("Snapshots")}</dt><dd>{historicalSnapshots.length}</dd></div>
              <div><dt>{t("Historical metrics")}</dt><dd>2</dd></div>
            </dl>
          </GlassPanel>
          <GlassPanel className="twin-notes">
            {comparisons.map((comparison) => (
              <div className="twin-note-column" key={comparison.metricId}>
                <span className="eyebrow">{t(metricLabels[comparison.metricId])}</span>
                <p><ArrowUpRight aria-hidden="true" />{t("{past} on {pastDate} → {current} on {currentDate}", {
                  past: comparisonValue(comparison, comparison.pastValue),
                  pastDate: comparison.referenceDate ? date(comparison.referenceDate) : "—",
                  current: comparisonValue(comparison, comparison.currentValue),
                  currentDate: comparison.currentDate ? date(comparison.currentDate) : "—",
                })}</p>
                <p>{t("Absolute change {change}; relative change {relative}.", {
                  change: absoluteChange(comparison),
                  relative: comparison.relativeChange === null ? "—" : formatPercent(comparison.relativeChange, 1),
                })}</p>
              </div>
            ))}
          </GlassPanel>
        </div>
      </section>

      <div className="twin-profile-grid">
        <GlassPanel>
          <SectionHeading eyebrow={t("Decision profile")} title={t("Current evidence references")} />
          <div className="profile-list">
            {currentSnapshot.decisionEvidenceRefs.map((reference) => (
              <div key={reference.evidenceId}>
                <span>{t(metricLabels[reference.metricId])}</span>
                <strong className="font-mono" title={reference.evidenceId}>{shortEvidenceId(reference.evidenceId)}</strong>
                <StatusBadge status={reference.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>
        <GlassPanel>
          <SectionHeading eyebrow={t("Behavior profile")} title={t("Current evidence references")} />
          <div className="profile-list">
            {currentSnapshot.behaviorEvidenceRefs.map((reference) => (
              <div key={reference.evidenceId}>
                <span>{t(metricLabels[reference.metricId])}</span>
                <strong className="font-mono" title={reference.evidenceId}>{shortEvidenceId(reference.evidenceId)}</strong>
                <StatusBadge status={reference.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>
      </div>

      <div className="twin-bottom-grid">
        <GlassPanel>
          <SectionHeading eyebrow={t("Behavior state")} title={t("Observed, not scored")} />
          <div className="change-list">
            {currentSnapshot.behaviorState.map((metric) => (
              <div key={metric.metricId}>
                <span>{t(metricLabels[metric.metricId])}</span>
                <strong>{metricValue(metric)}</strong>
                <p>{t("as of {date}", { date: date(metric.asOf) })} · N={metric.observationCount ?? "—"} · {statusText(metric.status)}</p>
              </div>
            ))}
          </div>
        </GlassPanel>
        <GlassPanel>
          <SectionHeading eyebrow={t("Data quality")} title={t("Evidence coverage and limitations")} />
          <div className="quality-list">
            <div><Database /><span><strong>{currentSnapshot.dataQuality.referencedEvidenceCount} / {currentSnapshot.dataQuality.expectedEvidenceCount} {t("evidence references")}</strong><small>{currentSnapshot.dataQuality.completeEvidenceCount} {t("Complete")}</small></span></div>
            <div><Layers3 /><span><strong>{currentSnapshot.dataQuality.availableBehaviorMetricCount} / 4 {t("behavior metrics available")}</strong><small>{currentSnapshot.dataQuality.missingBehaviorMetrics.length === 0 ? t("No missing behavior state") : currentSnapshot.dataQuality.missingBehaviorMetrics.join(", ")}</small></span></div>
            <div><ShieldCheck /><span><strong>{t("Synthetic / Demo")}</strong><small>{currentSnapshot.limitations.length} {t("registered limitations")}</small></span></div>
          </div>
          <p className="mt-3 text-xs leading-5 text-muted">{currentSnapshot.limitations.slice(0, 2).map((item) => t(item)).join(" ")}</p>
        </GlassPanel>
      </div>
    </div>
  );
}
