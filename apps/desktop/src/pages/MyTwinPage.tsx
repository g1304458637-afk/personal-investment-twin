import { ArrowUpRight, CircleCheck, Database, History, Layers3, ShieldCheck } from "lucide-react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { MirrorOrb } from "@/components/common/MirrorOrb";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { behaviorMetrics, decisionMetrics, translateEvidenceText } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";
import {
  demoUser,
  notableChanges,
  twinPeriods,
} from "@/demo/fixture";

export default function MyTwinPage() {
  const { t, formatPercent } = useLocale();

  return (
    <div className="page twin-page">
      <PageHeader
        eyebrow={t("My Twin · Demo Snapshot")}
        title={t("A living evidence profile")}
        description={t("A deterministic product mock—not a production Twin engine or a persistent investor identity.")}
      />

      <GlassPanel className="twin-identity glass-reflection">
        <div className="twin-identity__orb">
          <MirrorOrb size="lg" state="idle" />
        </div>
        <div className="twin-identity__copy">
          <span className="eyebrow">{t("Current snapshot")}</span>
          <h2>{t(demoUser.displayName)}</h2>
          <p>{t(demoUser.profileName)}</p>
          <div>
            <span><CircleCheck /> {t("Deterministic fixture")}</span>
            <span><ShieldCheck /> {t("Synthetic provenance")}</span>
            <span><History /> {t("Updated 31 Mar 2025")}</span>
          </div>
        </div>
        <dl className="twin-identity__quality">
          <div>
            <dt>{t("Evidence coverage")}</dt>
            <dd>82%</dd>
            <span>{t("Recent 3M window")}</span>
          </div>
          <div>
            <dt>{t("Data quality")}</dt>
            <dd>{t("Demo-ready")}</dd>
            <span>{t("2 explicit limitations")}</span>
          </div>
        </dl>
      </GlassPanel>

      <Tabs defaultValue="3m" className="twin-periods">
        <div className="twin-periods__header">
          <SectionHeading
            eyebrow={t("Self history")}
            title={t("What changed across observation windows")}
            description={t("Time windows alter the available sample; absent evidence stays absent.")}
          />
          <TabsList aria-label={t("Twin observation window")}>
            {twinPeriods.map((period) => (
              <TabsTrigger key={period.id} value={period.id}>{t(period.label)}</TabsTrigger>
            ))}
          </TabsList>
        </div>

        {twinPeriods.map((period) => (
          <TabsContent value={period.id} key={period.id}>
            <div className="twin-period-grid">
              <GlassPanel className="twin-period-summary">
                <span className="eyebrow">{t("{period} snapshot", { period: t(period.label) })}</span>
                <h3>{t(period.observationWindow)}</h3>
                <div className="coverage-ring" style={{ "--coverage": period.evidenceCoverage } as React.CSSProperties}>
                  <span>{formatPercent(period.evidenceCoverage, 0)}</span>
                  <small>{t("coverage")}</small>
                </div>
                <dl>
                  <div><dt>{t("Episodes")}</dt><dd>{period.episodeCount}</dd></div>
                  <div><dt>{t("Window")}</dt><dd>{t(period.label)}</dd></div>
                </dl>
              </GlassPanel>

              <GlassPanel className="twin-notes">
                <div className="twin-note-column">
                  <span className="eyebrow">{t("Decision profile")}</span>
                  {period.decisionNotes.map((note) => (
                    <p key={note}><ArrowUpRight aria-hidden="true" />{t(note)}</p>
                  ))}
                </div>
                <div className="twin-note-column">
                  <span className="eyebrow">{t("Behavior profile")}</span>
                  {period.behaviorNotes.map((note) => (
                    <p key={note}><ArrowUpRight aria-hidden="true" />{t(note)}</p>
                  ))}
                </div>
              </GlassPanel>
            </div>
          </TabsContent>
        ))}
      </Tabs>

      <div className="twin-profile-grid">
        <GlassPanel>
          <SectionHeading eyebrow={t("Decision profile")} title={t("Evidence, by question")} />
          <div className="profile-list">
            {decisionMetrics.map((metric) => (
              <div key={metric.id}>
                <span>{t(metric.label)}</span>
                <strong>{translateEvidenceText(t, metric.primary, metric.primaryValues)}</strong>
                <StatusBadge status={metric.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>
        <GlassPanel>
          <SectionHeading eyebrow={t("Behavior profile")} title={t("Observed, not scored")} />
          <div className="profile-list">
            {behaviorMetrics.map((metric) => (
              <div key={metric.id}>
                <span>{t(metric.label)}</span>
                <strong>{translateEvidenceText(t, metric.primary, metric.primaryValues)}</strong>
                <StatusBadge status={metric.status} compact />
              </div>
            ))}
          </div>
        </GlassPanel>
      </div>

      <div className="twin-bottom-grid">
        <GlassPanel>
          <SectionHeading eyebrow={t("Notable changes")} title={t("Latest deterministic observations")} />
          <div className="change-list">
            {notableChanges.map((change) => (
              <div key={change.label}>
                <span>{t(change.label)}</span>
                <strong>{t(change.value)}</strong>
                <p>{t(change.detail)}</p>
              </div>
            ))}
          </div>
        </GlassPanel>
        <GlassPanel>
          <SectionHeading eyebrow={t("Data quality")} title={t("What this snapshot can support")} />
          <div className="quality-list">
            <div><Database /><span><strong>{t("8 unified records")}</strong><small>{t("Backend-generated deterministic evidence")}</small></span></div>
            <div><Layers3 /><span><strong>{t("3M / 12M / lifetime")}</strong><small>{t("Explicitly different sample windows")}</small></span></div>
            <div><ShieldCheck /><span><strong>{t("Demo Snapshot")}</strong><small>{t("Never presented as Production Twin")}</small></span></div>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
