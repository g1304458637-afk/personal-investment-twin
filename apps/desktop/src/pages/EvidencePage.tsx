import { Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { evidenceRecords } from "@/demo/fixture";
import type { DemoEvidenceRecord, EvidenceStatus } from "@/demo/types";
import { displayEvidenceValue, statusLabel } from "@/lib/format";
import { useLocale } from "@/locales/LocaleProvider";

const all = "all";

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function EvidenceDetail({ record }: { record: DemoEvidenceRecord }) {
  const { locale, t } = useLocale();
  const provenance = record.provenance.map((source) => (
    <li key={`${source.source_id}-${source.instrument}-${source.benchmark_id}`}>
      <strong>{source.source_name}</strong>
      <span>{t(humanize(source.source_type))} · {source.data_version} · {t("as of {date}", { date: source.as_of })}</span>
      <span>
        {source.instrument ?? t("No instrument")}
        {source.benchmark_id ? ` · ${t("benchmark: {id}", { id: source.benchmark_id })}` : ""}
      </span>
    </li>
  ));

  return (
    <>
      <div className="space-y-3 pr-8">
        <DemoBadge />
        <span className="eyebrow">{t("Evidence record")}</span>
        <SheetTitle className="text-xl font-semibold tracking-tight">{t(record.metric_id)}</SheetTitle>
        <SheetDescription>
          {t("A method-bound observation for review. It is not an investment recommendation or forecast.")}
        </SheetDescription>
        <StatusBadge status={record.evidence_status} />
      </div>

      <div className="mt-7 space-y-6">
        <section className="rounded-lg border border-border/70 bg-white/[0.025] p-4 dark:bg-white/[0.025]" aria-label={t("Evidence summary")}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
            <div><dt className="text-xs text-muted">{t("Value")}</dt><dd className="mt-1 font-medium tabular-nums">{displayEvidenceValue(record.value, locale)}</dd></div>
            <div><dt className="text-xs text-muted">{t("Observations (N)")}</dt><dd className="mt-1 font-medium tabular-nums">{record.observation_count ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted">{t("Metric")}</dt><dd className="mt-1 break-words font-mono text-xs">{record.metric_id}</dd></div>
            <div><dt className="text-xs text-muted">{t("Kind")}</dt><dd className="mt-1">{t(record.evidence_kind)}</dd></div>
            <div><dt className="text-xs text-muted">{t("Method")}</dt><dd className="mt-1 break-words font-mono text-xs">{record.method_id} · v{record.method_version}</dd></div>
            <div><dt className="text-xs text-muted">{t("Data tier")}</dt><dd className="mt-1">{t(humanize(record.data_tier))}</dd></div>
          </dl>
        </section>

        <DetailSection title={t("Evidence ID")}><code className="break-all text-xs text-muted">{record.evidence_id}</code></DetailSection>
        <DetailSection title={t("Observation window")}>
          <p>{record.observation_start ?? t("Not available")} → {record.observation_end ?? t("Not available")}</p>
          <p className="mt-1 text-xs text-muted">{t("As of {date}", { date: record.as_of })}</p>
        </DetailSection>
        <DetailSection title={t("Method boundary")}>
          <p>{t(record.evidence_reason ?? "The registered method boundary was met for this record.")}</p>
          {record.ci_lower !== null || record.ci_upper !== null ? <p className="mt-1 text-xs text-muted">{t("Interval: {lower} to {upper}", { lower: record.ci_lower ?? "—", upper: record.ci_upper ?? "—" })}</p> : null}
        </DetailSection>
        <DetailSection title={t("Provenance")}><ul className="space-y-3 text-sm text-muted">{provenance}</ul></DetailSection>
        <DetailSection title={t("Limitations")}><ul className="list-disc space-y-2 pl-5 text-sm text-muted">{record.limitations.map((item) => <li key={item}>{t(item)}</li>)}</ul></DetailSection>
        <DetailSection title={t("Calculation code")}><code className="text-xs text-muted">{record.calculation_code_version}</code></DetailSection>
      </div>
    </>
  );
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><h3 className="mb-2 text-sm font-medium">{title}</h3><div className="text-sm text-foreground/90">{children}</div></section>;
}

export default function EvidencePage() {
  const { locale, t, formatNumber } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [metric, setMetric] = useState(all);
  const [status, setStatus] = useState<EvidenceStatus | typeof all>(all);
  const [kind, setKind] = useState(all);
  const selected = evidenceRecords.find((record) => record.evidence_id === searchParams.get("selected")) ?? null;

  const metrics = useMemo(() => [...new Set(evidenceRecords.map((record) => record.metric_id))], []);
  const kinds = useMemo(() => [...new Set(evidenceRecords.map((record) => record.evidence_kind))], []);
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return evidenceRecords.filter((record) => {
      const searchable = [record.evidence_id, record.metric_id, record.method_id, record.evidence_kind, record.evidence_status].join(" ").toLowerCase();
      return (!term || searchable.includes(term)) && (metric === all || record.metric_id === metric) && (status === all || record.evidence_status === status) && (kind === all || record.evidence_kind === kind);
    });
  }, [query, metric, status, kind]);

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t("Evidence explorer")} title={t("Trace every claim to its boundary")} description={t("Browse registered demo observations, their methods, source lineage and explicit limitations.")} />

      <GlassPanel className="p-5">
        <SectionHeading eyebrow={t("Registered observations")} title={t("Evidence index")} description={t("Filters affect the local demo fixture only; no live data request is made.")} action={<DemoBadge compact />} />
        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(240px,1fr)_repeat(3,minmax(150px,auto))]">
          <label className="relative"><span className="sr-only">{t("Search evidence")}</span><Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Search ID, metric or method")} className="pl-9" /></label>
          <FilterSelect label="Metric" value={metric} onChange={setMetric} options={metrics} formatter={(value) => value} />
          <FilterSelect label="Status" value={status} onChange={(value) => setStatus(value as EvidenceStatus | typeof all)} options={["complete", "partial", "insufficient_evidence", "experimental"]} formatter={(value) => statusLabel[value as EvidenceStatus]} />
          <FilterSelect label="Kind" value={kind} onChange={setKind} options={kinds} formatter={(value) => value} />
        </div>
      </GlassPanel>

      <GlassPanel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border/70 px-5 py-4"><div className="flex items-center gap-2"><SlidersHorizontal className="size-4 text-muted" /><span className="text-sm font-medium">{t("{count} records", { count: formatNumber(filtered.length) })}</span></div><span className="text-xs text-muted">{t("Select a row for full provenance")}</span></div>
        {filtered.length === 0 ? <div className="p-6"><StateNotice state="empty" title={t("No matching evidence")} detail={t("Try a broader search or clear one of the local filters. No missing record is substituted.")} /></div> : <div className="divide-y divide-border/60">{filtered.map((record) => <button key={record.evidence_id} type="button" className="grid w-full gap-3 px-5 py-4 text-left transition-colors hover:bg-white/[0.045] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/55 md:grid-cols-[minmax(180px,1.15fr)_minmax(150px,1fr)_auto_auto] md:items-center" onClick={() => setSearchParams({ selected: record.evidence_id })}><div><p className="font-medium">{t(record.metric_id)}</p><code className="mt-1 block truncate text-[11px] text-muted">{record.evidence_id}</code></div><div><p className="text-sm text-foreground/85">{record.method_id}</p><p className="mt-1 text-xs text-muted">v{record.method_version} · {t(record.evidence_kind)}</p></div><div className="text-sm tabular-nums"><span className="text-muted">{t("Value")} </span>{displayEvidenceValue(record.value, locale)}<span className="ml-2 text-xs text-muted">N={record.observation_count ?? "—"}</span></div><StatusBadge status={record.evidence_status} compact /></button>)}</div>}
      </GlassPanel>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSearchParams({})}>{selected ? <SheetContent><EvidenceDetail record={selected} /></SheetContent> : null}</Sheet>
    </div>
  );
}

function FilterSelect({ label, value, onChange, options, formatter = humanize }: { label: string; value: string; onChange: (value: string) => void; options: readonly string[]; formatter?: (value: string) => string }) {
  const { t } = useLocale();
  return <label className="text-xs text-muted"><span className="sr-only">{t(label)}</span><select aria-label={t("Filter evidence by {label}", { label: t(label) })} value={value} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-md border border-border/80 bg-black/[0.08] px-3 text-sm text-foreground outline-none transition focus:border-accent/45 focus:ring-2 focus:ring-accent/15 dark:bg-white/[0.035]"><option value={all}>{t("All {label}", { label: t(label) })}</option>{options.map((option) => <option key={option} value={option}>{t(formatter(option))}</option>)}</select></label>;
}
