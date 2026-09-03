import { ArrowRight, ChevronDown, ChevronUp, Database, Hash, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EvidenceTrendChart } from "@/components/charts/EvidenceTrendChart";
import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { decisionMetrics, evidenceRecords, positionEpisodeDemo, translateEvidenceText } from "@/data/backendEvidence";
import type { DemoEvidenceRecord, EvidenceMetric } from "@/demo/types";
import { cn } from "@/lib/utils";
import { useLocale, type TranslationValues } from "@/locales/LocaleProvider";

function findEvidence(metric: EvidenceMetric): DemoEvidenceRecord {
  const record = evidenceRecords.find((item) => item.evidence_id === metric.evidenceId);
  if (!record) throw new Error(`Missing deterministic fixture evidence for ${metric.id}.`);
  return record;
}

function EvidenceDetail({ record, metric, t }: { record: DemoEvidenceRecord; metric: EvidenceMetric; t: (value: string, values?: TranslationValues) => string }) {
  const [open, setOpen] = useState(false);
  const confidence = t(metric.confidence ?? "CI not available for this registered method");

  return (
    <div className="border-t border-border/70 pt-3">
      <div className="grid gap-2 text-xs text-muted sm:grid-cols-3">
        <span><strong className="mr-1 font-medium text-foreground">N</strong>{metric.observationCount ?? t("Not available")}</span>
        <span><strong className="mr-1 font-medium text-foreground">{t("Uncertainty")}</strong>{confidence}</span>
        <span><strong className="mr-1 font-medium text-foreground">{t("As of")}</strong>{t("31 Mar 2025")}</span>
      </div>
      <Button
        type="button"
        variant="quiet"
        size="sm"
        className="mt-2 -ml-3"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <ChevronUp /> : <ChevronDown />}
        {t(open ? "Hide evidence details" : "Show evidence details")}
      </Button>
      {open ? (
        <div className="mt-2 grid gap-3 border-l border-accent/35 pl-3 text-xs leading-5 text-muted md:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <div>
            <p className="text-foreground">{t("Method")}</p>
            <p className="font-mono text-[11px]">{record.method_id} · v{record.method_version}</p>
            <p className="mt-2 text-foreground">{t("Evidence ID")}</p>
            <p className="break-all font-mono text-[11px]">{record.evidence_id}</p>
          </div>
          <div>
            <p className="text-foreground">{t("Boundary")}</p>
            <p>{t(record.evidence_reason ?? record.limitations[0])}</p>
            {record.limitations.length > 1 ? <p className="mt-1">{t("Also excludes")}: {record.limitations.slice(1).map((item) => t(item)).join(" ")}</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DecisionModule({ metric, selected, onSelect, t }: { metric: EvidenceMetric; selected: boolean; onSelect: () => void; t: (value: string, values?: TranslationValues) => string }) {
  const record = findEvidence(metric);
  return (
    <article className={cn("rounded-lg border p-4 transition-colors", selected ? "border-accent/45 bg-accent/[0.07]" : "border-border/75 bg-white/[0.025] hover:bg-white/[0.045]")}>
      <button type="button" className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas" onClick={onSelect} aria-pressed={selected}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{t(metric.eyebrow)}</p>
            <h3 className="mt-1 text-[15px] font-semibold text-foreground">{t(metric.label)}</h3>
          </div>
          <StatusBadge status={metric.status} compact />
        </div>
        <p className="mt-4 font-mono text-[23px] font-semibold tracking-tight text-foreground tabular-nums">{translateEvidenceText(t, metric.primary, metric.primaryValues)}</p>
        <p className="mt-2 text-sm leading-5 text-muted">{translateEvidenceText(t, metric.description, metric.descriptionValues)}</p>
      </button>
      <div className="mt-4">
        <EvidenceDetail record={record} metric={metric} t={t} />
      </div>
    </article>
  );
}

export function DecisionsPage() {
  const { t } = useLocale();
  const [selectedId, setSelectedId] = useState(decisionMetrics[0].id);
  const selectedMetric = decisionMetrics.find((metric) => metric.id === selectedId) ?? decisionMetrics[0];
  const selectedRecord = findEvidence(selectedMetric);

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        eyebrow={t("Decision evidence")}
        title={t("What the observed decisions show")}
        description={t("Deterministic evidence from a synthetic offline fixture. These observations are not a trading score, prediction, or recommendation.")}
        actions={<DemoBadge />}
      />

      <GlassPanel className="p-5 md:p-6">
        <SectionHeading
          eyebrow={t("Position Episode v1")}
          title={t("Follow one position from opening to its current state")}
          description={t("Actual executions are organized into a lifecycle; quantities, average cost, and valuation facts come from deterministic vectorbt replay.")}
        />
        <div className="mt-4 divide-y divide-border/70 rounded-lg border border-border/70 bg-white/[0.025]">
          {positionEpisodeDemo.entries.map((entry) => (
            <Link
              key={entry.episode.episodeId}
              to={`/decisions/episodes/${entry.episode.episodeId}`}
              className="flex items-center justify-between gap-4 px-4 py-3 text-sm transition-colors first:rounded-t-lg last:rounded-b-lg hover:bg-white/[0.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            >
              <span className="min-w-0">
                <strong className="block truncate font-medium text-foreground">{entry.episode.instrumentId}</strong>
                <span className="mt-0.5 block text-xs text-muted">
                  {t(entry.episode.status === "open" ? "Holding" : "Closed position")} · {t("{count} executions", { count: entry.episode.executionRefs.length })}
                </span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-accent">
                {t("View episode")}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </span>
            </Link>
          ))}
        </div>
      </GlassPanel>

      <GlassPanel className="p-5 md:p-6">
        <SectionHeading eyebrow={t("Four decision lenses")} title={t("Evidence, not a black-box score")} description={t("Select a lens to inspect its fixed observation trend and registered evidence boundary.")} />
        <div className="mt-5 grid gap-3 lg:grid-cols-2">
          {decisionMetrics.map((metric) => <DecisionModule key={metric.id} metric={metric} t={t} selected={metric.id === selectedId} onSelect={() => setSelectedId(metric.id)} />)}
        </div>
      </GlassPanel>

      <GlassPanel className="overflow-hidden p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Sparkles className="size-4 text-accent" aria-hidden="true" /><span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{t("Selected deterministic series")}</span></div>
            <h2 className="mt-2 text-lg font-semibold text-foreground">{t(selectedMetric.label)} {t("observation trend")}</h2>
            <p className="mt-1 max-w-2xl text-sm leading-5 text-muted">{translateEvidenceText(t, selectedMetric.description, selectedMetric.descriptionValues)}</p>
          </div>
          <StatusBadge status={selectedMetric.status} />
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-end">
          <EvidenceTrendChart metric={selectedMetric} />
          <dl className="grid grid-cols-2 gap-x-3 gap-y-4 rounded-md border border-border/70 bg-white/[0.025] p-4 text-xs">
            <div><dt className="text-muted">{t("Observations")}</dt><dd className="mt-1 font-mono text-base text-foreground tabular-nums">N={selectedMetric.observationCount ?? "—"}</dd></div>
            <div><dt className="text-muted">{t("Uncertainty")}</dt><dd className="mt-1 text-foreground">{selectedMetric.confidence ? t(selectedMetric.confidence) : t("Not available")}</dd></div>
            <div className="col-span-2"><dt className="flex items-center gap-1 text-muted"><Database className="size-3" aria-hidden="true" />{t("Provenance")}</dt><dd className="mt-1 text-foreground">{t("Synthetic offline fixture")} · {t(selectedRecord.data_tier)}</dd></div>
          </dl>
        </div>
      </GlassPanel>

      <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-white/[0.025] p-4 text-xs leading-5 text-muted">
        <Hash className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
        <p><strong className="font-medium text-foreground">{t("Traceable demo evidence.")}</strong> {t("Each displayed value has a fixed evidence ID, method version, observation count, status, and stated limitation. Missing uncertainty is shown as missing; it is never filled with an inferred confidence interval.")}</p>
      </div>
    </div>
  );
}
