import { ArrowUpRight, Braces, Database, FlaskConical, Info, Sigma } from "lucide-react";
import { useState } from "react";

import { CalculationRenderer } from "@/components/evidence/CalculationRenderer";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ExplainabilityView, TraceScalar } from "@/data/explainability";
import { useLocale } from "@/locales/LocaleProvider";

export interface EvidenceInspectorContext {
  label?: string;
  title?: string;
  detail?: string;
}

function resultText(
  value: TraceScalar,
  unit: string,
  conceptId: string,
  locale: string,
  t: (source: string) => string,
) {
  if (value === null) return "—";
  if (typeof value === "string") {
    const comparisons: Record<string, string> = {
      outperformed_baseline: "Actual result was above the registered baseline",
      underperformed_baseline: "Actual result was below the registered baseline",
      matched_baseline: "Actual result matched the registered baseline",
    };
    return t(comparisons[value] ?? value);
  }
  if (typeof value !== "number") return String(value);
  if (unit === "currency" || unit === "currency_per_unit") {
    return new Intl.NumberFormat(locale, { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(value);
  }
  if (unit === "ratio" && [
    "turnover_intensity",
    "disposition_effect",
    "loss_state_addition",
    "post_exit_fixed_window_return",
    "selection_episode_asset_return",
    "decision_evidence_hit_rate",
  ].includes(conceptId)) {
    return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(value);
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(value);
}

function sourceLabel(sourceType: string) {
  const labels: Record<string, string> = {
    execution: "Recorded execution",
    normalized_executions: "Recorded executions",
    portfolio_state: "Portfolio state",
    counterfactual_portfolio: "Registered counterfactual portfolio",
    proposed_trade: "Proposed trade",
    market_price: "Market prices",
    price_series: "Market price series",
    position_episode: "Position Episode",
    evidence: "Evidence record",
  };
  return labels[sourceType] ?? sourceType.replaceAll("_", " ");
}

function statusLabel(status: string) {
  if (status === "complete") return "Complete evidence";
  if (status === "partial") return "Partial evidence";
  if (status === "insufficient" || status === "insufficient_evidence") return "Evidence still maturing";
  if (status === "rejected") return "Calculation rejected";
  if (status === "concept_only") return "Registered concept";
  return status;
}

function Explanation({ view }: { view: ExplainabilityView }) {
  const { t } = useLocale();
  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-xs font-medium uppercase tracking-[0.13em] text-muted">{t("What this measures")}</h3>
        <p className="mt-3 text-sm leading-6 text-foreground/90">{t(view.concept.detailedDefinitionKey)}</p>
      </section>
      <section className="border-t border-border/70 pt-5">
        <h3 className="text-xs font-medium uppercase tracking-[0.13em] text-muted">{t("What this result can say")}</h3>
        <p className="mt-3 text-sm leading-6 text-foreground/90">{t(view.concept.shortDefinitionKey)}</p>
      </section>
      {view.limitations.length > 0 ? (
        <section className="border-t border-border/70 pt-5">
          <h3 className="text-xs font-medium uppercase tracking-[0.13em] text-muted">{t("Method limitations")}</h3>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-muted">
            {view.limitations.map((item) => <li key={item} className="flex gap-2"><Info className="mt-1 size-3.5 shrink-0 text-accent" aria-hidden="true" /><span>{t(item)}</span></li>)}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Calculation({ view }: { view: ExplainabilityView }) {
  const { t } = useLocale();
  const trace = view.trace;
  if (!trace) {
    return (
      <div className="border-y border-border/70 py-7 text-center">
        <Sigma className="mx-auto size-5 text-muted" aria-hidden="true" />
        <h3 className="mt-3 text-sm font-medium">{t("Calculation details are not available yet")}</h3>
        <p className="mx-auto mt-2 max-w-sm text-xs leading-5 text-muted">{t("The registered concept and method remain visible. The interface will not recreate or infer a missing calculation trace.")}</p>
      </div>
    );
  }
  if (trace.status === "insufficient" || trace.status === "rejected") {
    const available = Object.entries(trace.availableObservation);
    const reason = trace.conceptId === "post_exit_fixed_window_return"
      ? t("Post-exit market-price observations have not yet reached the registered 20-session window.")
      : t(trace.reason ?? "The deterministic method's required observations are not yet complete.");
    return (
      <div>
        <div className="border-y border-border/70 py-6">
          <p className="text-sm font-medium">{t("A complete result cannot be formed yet")}</p>
          <p className="mt-2 text-sm leading-6 text-muted">{reason}</p>
        </div>
        {trace.requiredCondition ? <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-b border-border/70 py-4 text-sm"><span className="text-muted">{t("Required condition")}</span><span className="max-w-[260px] text-right">{t(trace.requiredCondition)}</span></div> : null}
        {available.map(([key, value]) => <div key={key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-b border-border/70 py-3 text-sm"><span className="text-muted">{t(key.replaceAll("_", " "))}</span><span className="font-mono tabular-nums">{String(value)}</span></div>)}
      </div>
    );
  }
  return <CalculationRenderer trace={trace} />;
}

function Method({ view }: { view: ExplainabilityView }) {
  const { locale, t } = useLocale();
  const trace = view.trace;
  const asOf = trace?.asOf ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(trace.asOf)) : t("Not available");
  const sources = Array.from(new Map(view.provenance.map((item) => [`${item.sourceType}:${item.sourceName}:${item.instrument}`, item])).values());
  const inputSources = Array.from(new Set(trace?.inputs.map((item) => item.sourceType) ?? []));
  return (
    <div>
      <dl className="divide-y divide-border/65 border-y border-border/65 text-sm">
        <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-4 py-3"><dt className="text-muted">{t("Method")}</dt><dd className="font-medium">{view.concept.methodId}</dd></div>
        <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-4 py-3"><dt className="text-muted">{t("Method Version")}</dt><dd>{view.concept.methodVersion}</dd></div>
        <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-4 py-3"><dt className="text-muted">{t("As of")}</dt><dd>{asOf}</dd></div>
      </dl>

      <section className="mt-6">
        <h3 className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.13em] text-muted"><Database className="size-3.5" aria-hidden="true" />{t("Data sources")}</h3>
        {sources.length > 0 ? <div className="mt-3 divide-y divide-border/65 border-y border-border/65">{sources.map((source, index) => <div key={`${source.sourceType}:${source.sourceName}:${index}`} className="py-3 text-sm"><p className="font-medium">{t(sourceLabel(source.sourceType))}</p><p className="mt-1 text-xs text-muted">{source.sourceName}{source.instrument ? ` · ${source.instrument}` : ""} · v${source.dataVersion}</p></div>)}</div> : inputSources.length > 0 ? <div className="mt-3 divide-y divide-border/65 border-y border-border/65">{inputSources.map((sourceType) => <p key={sourceType} className="py-3 text-sm font-medium">{t(sourceLabel(sourceType))}</p>)}</div> : <p className="mt-3 text-sm text-muted">{t("No source metadata is available for this trace.")}</p>}
      </section>

      <details className="mt-6 border-y border-border/70 py-3">
        <summary className="cursor-pointer text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-accent/55">{t("Technical details")}</summary>
        <dl className="mt-4 space-y-4 text-xs text-muted">
          <div><dt>{t("Evidence ID")}</dt><dd className="mt-1 break-all font-mono text-foreground">{view.evidenceId ?? "—"}</dd></div>
          <div><dt>{t("Trace ID")}</dt><dd className="mt-1 break-all font-mono text-foreground">{trace?.traceId ?? "—"}</dd></div>
          <div><dt>{t("Calculation code")}</dt><dd className="mt-1 break-all font-mono text-foreground">{trace?.calculationCodeVersion ?? "—"}</dd></div>
          {trace?.sourceRefs.map((source) => <div key={source}><dt>{t("Source reference")}</dt><dd className="mt-1 break-all font-mono text-foreground">{source}</dd></div>)}
        </dl>
      </details>
    </div>
  );
}

export function EvidenceInspector({
  view,
  context,
  open,
  onOpenChange,
}: {
  view: ExplainabilityView;
  context?: EvidenceInspectorContext;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { locale, t } = useLocale();
  const status = view.trace?.status ?? view.result?.status ?? "concept_only";
  const primary = view.result?.value ?? view.trace?.result ?? null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(96vw,620px)] sm:p-7">
        <header className="pr-10">
          {context?.label ? <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent">{context.label}</p> : null}
          {context?.title ? <p className="mt-1 text-sm text-muted">{context.title}{context.detail ? ` · ${context.detail}` : ""}</p> : null}
          <SheetTitle className="mt-3 text-xl font-semibold tracking-tight">{t(view.concept.titleKey)}</SheetTitle>
          <SheetDescription className="mt-2 text-sm leading-6">{t(view.concept.shortDefinitionKey)}</SheetDescription>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-3 border-b border-border/70 pb-5">
            <strong className="font-mono text-[30px] font-semibold leading-none tabular-nums">{resultText(primary, view.concept.unit, view.concept.conceptId, locale, t)}</strong>
            <span className="rounded-full border border-border/80 bg-white/[0.035] px-2.5 py-1 text-[11px] text-muted">{t(statusLabel(status))}</span>
          </div>
        </header>

        <Tabs defaultValue="explanation" className="mt-5">
          <TabsList aria-label={t("Evidence explanation layers")} className="grid w-full grid-cols-3">
            <TabsTrigger value="explanation"><Info className="mr-1.5 size-3.5" />{t("Explanation")}</TabsTrigger>
            <TabsTrigger value="calculation"><Sigma className="mr-1.5 size-3.5" />{t("Calculation")}</TabsTrigger>
            <TabsTrigger value="method"><Braces className="mr-1.5 size-3.5" />{t("Method")}</TabsTrigger>
          </TabsList>
          <TabsContent value="explanation"><Explanation view={view} /></TabsContent>
          <TabsContent value="calculation"><Calculation view={view} /></TabsContent>
          <TabsContent value="method"><Method view={view} /></TabsContent>
        </Tabs>

        <div className="mt-7 flex items-start gap-2 border-t border-border/70 pt-4 text-xs leading-5 text-muted">
          <FlaskConical className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
          <p>{t("Synthetic demo evidence. It does not represent a real investor account or real market history.")}</p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function EvidenceExplainButton({
  view,
  context,
  label = "View evidence",
  className,
}: {
  view: ExplainabilityView | null;
  context?: EvidenceInspectorContext;
  label?: string;
  className?: string;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  if (!view) return null;
  return (
    <>
      <Button type="button" variant="quiet" size="sm" className={className} onClick={() => setOpen(true)}>
        {t(label)} <ArrowUpRight className="size-3.5" aria-hidden="true" />
      </Button>
      <EvidenceInspector view={view} context={context} open={open} onOpenChange={setOpen} />
    </>
  );
}
