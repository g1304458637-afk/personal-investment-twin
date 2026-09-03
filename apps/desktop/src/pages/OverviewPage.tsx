import { ArrowRight, Braces, CircleCheck, Database, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { PortfolioTrendChart } from "@/components/charts/PortfolioTrendChart";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { GlassPanel } from "@/components/common/GlassPanel";
import { MetricRail } from "@/components/common/MetricRail";
import { MiniTrend } from "@/components/common/MiniTrend";
import { MirrorOrb } from "@/components/common/MirrorOrb";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useWorkspace } from "@/components/layout/useWorkspace";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/locales/LocaleProvider";
import {
  behaviorMetrics,
  decisionMetrics,
  demoUser,
  evidenceRecords,
  portfolioSummary,
  recentEvidenceIds,
} from "@/demo/fixture";

const recentEvidence = recentEvidenceIds
  .map((id) => evidenceRecords.find((record) => record.evidence_id === id))
  .filter((record): record is (typeof evidenceRecords)[number] => Boolean(record));

export default function OverviewPage() {
  const { openAgent } = useWorkspace();
  const { t, formatCurrency, formatNumber } = useLocale();

  return (
    <div className="page overview-page">
      <PageHeader
        eyebrow={t("Personal Investment Twin")}
        title={t("Your investment twin")}
        description={`${t(demoUser.profileName)} · ${t(demoUser.updatedLabel)}`}
        actions={
          <div className="data-quality-chip">
            <ShieldCheck aria-hidden="true" />
            <span>
              {t("Deterministic fixture")}
              <small>{t("9 evidence records")}</small>
            </span>
          </div>
        }
      />

      <GlassPanel className="portfolio-overview glass-reflection">
        <SectionHeading
          eyebrow={t("Portfolio overview")}
          title={t("A precise snapshot, without a composite score")}
          description={t("Fixed offline values from ui-demo-v1. No live account or market connection.")}
          action={<span className="as-of-label">{t("As of 31 Mar 2025")}</span>}
        />
        <MetricRail
          items={[
            {
              label: t("Total value"),
              value: (
                <AnimatedNumber value={portfolioSummary.totalValue} format={formatCurrency} />
              ),
              detail: t("CNY · synthetic"),
            },
            {
              label: t("Cash"),
              value: <AnimatedNumber value={portfolioSummary.cash} format={formatCurrency} />,
              detail: t("17.24% of demo value"),
            },
            {
              label: t("Active positions"),
              value: (
                <AnimatedNumber
                  value={portfolioSummary.activePositions}
                  format={(value) => formatNumber(Math.round(value))}
                />
              ),
              detail: t("Long-only fixture"),
            },
            {
              label: t("Investment episodes"),
              value: (
                <AnimatedNumber
                  value={portfolioSummary.episodeCount}
                  format={(value) => formatNumber(Math.round(value))}
                />
              ),
              detail: t("28 observed · 25 closed"),
            },
          ]}
        />
      </GlassPanel>

      <div className="overview-hero-grid">
        <GlassPanel className="chart-panel">
          <SectionHeading
            eyebrow={t("Portfolio path")}
            title={t("Value history")}
            description={t("Demo portfolio and a synthetic reference baseline · CNY")}
            action={
              <span className="chart-legend-note">
                <CircleCheck aria-hidden="true" /> {t("Real ECharts surface")}
              </span>
            }
          />
          <PortfolioTrendChart />
          <div className="chart-footer">
            <span>{t("06 Jan 2025")}</span>
            <span>{t("Deterministic · no random points")}</span>
            <span>{t("31 Mar 2025")}</span>
          </div>
        </GlassPanel>

        <GlassPanel tone="floating" className="ask-twin-entry glass-reflection">
          <div className="ask-twin-entry__orb">
            <MirrorOrb size="lg" state="active" />
            <span>{t("Evidence context ready")}</span>
          </div>
          <div>
            <span className="eyebrow">{t("Ask Twin")}</span>
            <h2>{t("Reflect on one episode, with facts attached.")}</h2>
            <p>
              {t("The future Agent Panel will receive structured evidence—not raw records to recalculate.")}
            </p>
          </div>
          <div className="ask-twin-entry__facts">
            <span>
              <Braces aria-hidden="true" /> {t("Position Return kept distinct")}
            </span>
            <span>
              <Database aria-hidden="true" /> {t("Synthetic provenance retained")}
            </span>
          </div>
          <Button variant="primary" size="lg" onClick={openAgent}>
            {t("Open reflection space")} <ArrowRight />
          </Button>
        </GlassPanel>
      </div>

      <div className="overview-evidence-grid">
        <GlassPanel className="evidence-snapshot">
          <SectionHeading
            eyebrow={t("Decision evidence")}
            title={t("Four questions, kept separate")}
            action={
              <Button asChild size="sm" variant="ghost">
                <Link to="/decisions">{t("View details")} <ArrowRight /></Link>
              </Button>
            }
          />
          <div className="snapshot-list">
            {decisionMetrics.map((metric) => (
              <div className="snapshot-row" key={metric.id}>
                <div>
                  <span>{t(metric.label)}</span>
                  <strong>{t(metric.primary)}</strong>
                </div>
                <MiniTrend values={metric.trend} label={t("{metric} observations", { metric: t(metric.label) })} />
                <StatusBadge status={metric.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel className="evidence-snapshot">
          <SectionHeading
            eyebrow={t("Behavior snapshot")}
            title={t("Observed patterns, not identity labels")}
            action={
              <Button asChild size="sm" variant="ghost">
                <Link to="/behavior">{t("View details")} <ArrowRight /></Link>
              </Button>
            }
          />
          <div className="snapshot-list">
            {behaviorMetrics.map((metric) => (
              <div className="snapshot-row" key={metric.id}>
                <div>
                  <span>{t(metric.label)}</span>
                  <strong>{t(metric.primary)}</strong>
                </div>
                <MiniTrend values={metric.trend} label={t("{metric} observations", { metric: t(metric.label) })} />
                <StatusBadge status={metric.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>
      </div>

      <GlassPanel className="recent-evidence">
        <SectionHeading
          eyebrow={t("Recent evidence")}
          title={t("Traceable facts")}
          description={t("Method, sample and status stay visible before interpretation.")}
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/evidence">{t("Explore all evidence")} <ArrowRight /></Link>
            </Button>
          }
        />
        <div className="recent-evidence__grid">
          {recentEvidence.map((record) => (
            <Link to={`/evidence?selected=${record.evidence_id}`} key={record.evidence_id}>
              <div className="recent-evidence__topline">
                <span>{t(record.metric_id)}</span>
                <StatusBadge status={record.evidence_status} compact />
              </div>
              <strong>{t(String(record.attributes.display_value ?? record.value ?? t("Not available")))}</strong>
              <dl>
                <div>
                  <dt>N</dt>
                  <dd>{record.observation_count ?? "—"}</dd>
                </div>
                <div>
                  <dt>{t("Method")}</dt>
                  <dd>{record.method_id}</dd>
                </div>
              </dl>
              <code>{record.evidence_id.slice(0, 19)}…</code>
            </Link>
          ))}
        </div>
      </GlassPanel>
    </div>
  );
}
