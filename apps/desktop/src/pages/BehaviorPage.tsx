import { CircleHelp, FlaskConical, Hash } from "lucide-react";
import { useState } from "react";

import { HistoricalMetricChart } from "@/components/charts/HistoricalMetricChart";
import { GlassPanel } from "@/components/common/GlassPanel";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import {
  behaviorHistory,
  behaviorMetrics,
  evidenceRecords,
  explainabilityForConcept,
  explainabilityForEvidence,
  translateEvidenceText,
} from "@/data/backendEvidence";
import type { DemoEvidenceRecord, EvidenceMetric } from "@/demo/types";
import { cn } from "@/lib/utils";
import { useLocale, type TranslationValues } from "@/locales/LocaleProvider";

const methodExplanations: Record<string, string> = {
  hhi: "HHI sums squared portfolio weights at each observed snapshot. It describes concentration in this fixture; it does not prescribe diversification.",
  turnover: "Turnover intensity summarizes observed position changes across complete windows. It does not estimate unrecorded costs or future activity.",
  disposition: "PGR and PLR compare the registered realized-outcome categories. Their difference is descriptive evidence; it is experimental because the synthetic sample is limited and does not establish a trait.",
  "loss-averaging": "Loss averaging counts observed additions below the recorded prior cost basis. An event is descriptive evidence, not a claim about intent or decision quality.",
};

function evidenceFor(metric: EvidenceMetric): DemoEvidenceRecord {
  const record = evidenceRecords.find((item) => item.evidence_id === metric.evidenceId);
  if (!record) throw new Error(`Missing deterministic fixture evidence for ${metric.id}.`);
  return record;
}

function BehaviorDetail({ metric, record, t }: { metric: EvidenceMetric; record: DemoEvidenceRecord; t: (value: string, values?: TranslationValues) => string }) {
  const conceptIds: Record<string, string> = {
    hhi: "portfolio_concentration_hhi",
    turnover: "turnover_intensity",
    disposition: "disposition_effect",
    "loss-averaging": "loss_state_addition",
  };
  const view = explainabilityForEvidence(record.evidence_id)
    ?? explainabilityForConcept(conceptIds[metric.id]);
  return (
    <div className="border-t border-border/70 pt-3">
      <div className="grid grid-cols-2 gap-2 text-xs text-muted">
        <span><strong className="mr-1 font-medium text-foreground">N</strong>{metric.observationCount ?? t("Not available")}</span>
        <span><strong className="mr-1 font-medium text-foreground">{t("Range / CI")}</strong>{metric.confidence ? t(metric.confidence) : t("Not available")}</span>
      </div>
      <EvidenceExplainButton
        view={view}
        className="mt-2 -ml-3"
        context={{ label: t("Behavior evidence"), title: t(metric.label), detail: t("Synthetic offline fixture") }}
      />
    </div>
  );
}

function BehaviorModule({ metric, selected, onSelect, t }: { metric: EvidenceMetric; selected: boolean; onSelect: () => void; t: (value: string, values?: TranslationValues) => string }) {
  const record = evidenceFor(metric);
  return (
    <article className={cn("rounded-lg border p-4 transition-colors", selected ? "border-accent/45 bg-accent/[0.07]" : "border-border/75 bg-white/[0.025] hover:bg-white/[0.045]")}>
      <button type="button" onClick={onSelect} aria-pressed={selected} className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas">
        <div className="flex items-start justify-between gap-3"><div><p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{t(metric.eyebrow)}</p><h3 className="mt-1 text-[15px] font-semibold text-foreground">{t(metric.label)}</h3></div><StatusBadge status={metric.status} compact /></div>
        <p className="mt-4 font-mono text-[23px] font-semibold tracking-tight text-foreground tabular-nums">{translateEvidenceText(t, metric.primary, metric.primaryValues)}</p>
        <p className="mt-2 text-sm leading-5 text-muted">{translateEvidenceText(t, metric.description, metric.descriptionValues)}</p>
      </button>
      <div className="mt-4"><BehaviorDetail metric={metric} record={record} t={t} /></div>
    </article>
  );
}

export function BehaviorPage() {
  const { t } = useLocale();
  const [selectedId, setSelectedId] = useState(behaviorMetrics[0].id);
  const selectedMetric = behaviorMetrics.find((metric) => metric.id === selectedId) ?? behaviorMetrics[0];
  const selectedHistory = selectedMetric.id === "hhi"
    ? behaviorHistory.hhi
    : selectedMetric.id === "turnover"
      ? behaviorHistory.turnover
      : null;

  return (
    <div className="space-y-6 pb-8">
      <PageHeader eyebrow={t("Behavior observations")} title={t("Patterns in the recorded fixture")} description={t("A transparent view of deterministic, synthetic observations—not an investor personality label or predictive behavior score.")} actions={<DemoBadge />} />

      <GlassPanel className="p-5 md:p-6">
        <SectionHeading eyebrow={t("Four descriptive measures")} title={t("Read the method with the metric")} description={t("Each measure exposes its observation count, evidence status, uncertainty boundary, and expandable method explanation.")} />
        <div className="mt-5 grid gap-3 lg:grid-cols-2">
          {behaviorMetrics.map((metric) => <BehaviorModule key={metric.id} metric={metric} t={t} selected={metric.id === selectedId} onSelect={() => setSelectedId(metric.id)} />)}
        </div>
      </GlassPanel>

      <GlassPanel className="p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{t("Selected synthetic history")}</p><h2 className="mt-2 text-lg font-semibold text-foreground">{t(selectedMetric.label)}</h2><p className="mt-1 text-sm leading-5 text-muted">{t(methodExplanations[selectedMetric.id])}</p></div>
          <StatusBadge status={selectedMetric.status} />
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px] lg:items-end">
          {selectedHistory ? (
            <HistoricalMetricChart
              series={selectedHistory}
              label={t(selectedMetric.label)}
              singleValueLabel={translateEvidenceText(t, selectedMetric.primary, selectedMetric.primaryValues)}
              percent={selectedMetric.id === "turnover"}
            />
          ) : (
            <StateNotice
              state="insufficient"
              title={translateEvidenceText(t, selectedMetric.primary, selectedMetric.primaryValues)}
              detail={t("Historical series is not available for this metric in v1.")}
            />
          )}
          <div className="rounded-md border border-border/70 bg-white/[0.025] p-4 text-xs leading-5">
            <p className="text-muted">{t("Displayed metric")}</p><p className="mt-1 font-mono text-xl font-semibold text-foreground tabular-nums">{translateEvidenceText(t, selectedMetric.primary, selectedMetric.primaryValues)}</p>
            <p className="mt-4 text-muted">{t("Evidence coverage")}</p><p className="text-foreground">N={selectedMetric.observationCount ?? "—"} · {selectedMetric.confidence ? t(selectedMetric.confidence) : t("No CI / range registered")}</p>
            <p className="mt-4 text-muted">{t("Data context")}</p><p className="flex items-center gap-1 text-foreground"><FlaskConical className="size-3.5 text-accent" aria-hidden="true" />{t("Demo / Synthetic")} · {t("as of 31 Mar 2025")}</p>
          </div>
        </div>
      </GlassPanel>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex gap-3 rounded-lg border border-border/70 bg-white/[0.025] p-4 text-xs leading-5 text-muted"><CircleHelp className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" /><p><strong className="font-medium text-foreground">{t("Method boundary.")}</strong> {t("A behavior observation describes the recorded fixture only. It does not infer motivation, quality, risk tolerance, or a future action.")}</p></div>
        <div className="flex gap-3 rounded-lg border border-border/70 bg-white/[0.025] p-4 text-xs leading-5 text-muted"><Hash className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" /><p><strong className="font-medium text-foreground">{t("Traceability.")}</strong> {t("Values are linked to a fixed method version and evidence ID. Missing CI values remain explicit rather than being modeled or filled.")}</p></div>
      </div>
    </div>
  );
}
