import { ChevronRight, Info, LockKeyhole, Send, ShieldCheck, UsersRound } from "lucide-react";

import { PeerRangeChart } from "@/components/charts/PeerRangeChart";
import { AnimatedNumber } from "@/components/common/AnimatedNumber";
import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { peerBenchmark, twinState } from "@/data/backendEvidence";
import { isCompletePeerBenchmarkMetric, type PeerBenchmarkMetricView } from "@/data/peerBenchmark";
import type { TwinMetricComparisonView } from "@/data/twinState";
import { useLocale } from "@/locales/LocaleProvider";

const peerMetricDirections: Record<string, readonly [string, string]> = {
  turnover: ["Lower turnover", "Higher turnover"],
  portfolio_hhi: ["Lower concentration", "Higher concentration"],
  closed_episode_count: ["Fewer closed episodes", "More closed episodes"],
};

const historyMetricLabels: Record<string, string> = {
  portfolio_concentration_hhi: "HHI",
  mean_daily_turnover: "Turnover",
};

export function ComparePage() {
  const { formatNumber, formatPercent, locale, t } = useLocale();
  const historyDate = (value: string) => new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
  const historyValue = (metric: TwinMetricComparisonView, value: number | null) => {
    if (value === null) return t("Not available");
    return metric.metricId === "portfolio_concentration_hhi"
      ? formatNumber(value, 4)
      : formatPercent(value, 2);
  };
  const historyAbsoluteChange = (metric: TwinMetricComparisonView) => {
    if (metric.absoluteChange === null) return t("Not available");
    return metric.metricId === "portfolio_concentration_hhi"
      ? formatNumber(metric.absoluteChange, 4)
      : `${formatNumber(metric.absoluteChange * 100, 2)} pp`;
  };
  const formatPeerValue = (metric: PeerBenchmarkMetricView, value: number) => {
    if (metric.valueFormat === "percent") return formatPercent(value, 2);
    return formatNumber(value, metric.valueFormat === "integer" ? 0 : 4);
  };
  const medianDifference = (metric: PeerBenchmarkMetricView & { chartMetric: NonNullable<PeerBenchmarkMetricView["chartMetric"]> }) => {
    const difference = metric.chartMetric.user - metric.chartMetric.median;
    if (difference === 0) return t("Matches cohort median");
    return t(difference > 0 ? "Above cohort median by {difference}" : "Below cohort median by {difference}", {
      difference: formatPeerValue(metric, Math.abs(difference)),
    });
  };
  const completePeerMetrics = peerBenchmark.metrics.filter(isCompletePeerBenchmarkMetric);
  const rankedByPercentileDistance = [...completePeerMetrics].sort(
    (left, right) => Math.abs(right.chartMetric.percentile - 50) - Math.abs(left.chartMetric.percentile - 50),
  );
  const furthestFromCohortMedian = rankedByPercentileDistance[0];
  const closestToCohortMedian = rankedByPercentileDistance[rankedByPercentileDistance.length - 1];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Comparison surfaces")}
        title={t("Compare evidence context")}
        description={t("Compare your synthetic demo evidence across time, against a defined cohort, or through an explicitly authorized invitation.")}
      />

      <Tabs defaultValue="past" className="w-full">
        <TabsList aria-label={t("Comparison mode")} className="flex h-auto w-full flex-wrap justify-start gap-1">
          <TabsTrigger value="past">{t("Now vs Past")}</TabsTrigger>
          <TabsTrigger value="peer">{t("Me vs Cohort")}</TabsTrigger>
          <TabsTrigger value="user">{t("Me vs User")}</TabsTrigger>
        </TabsList>

        <TabsContent value="past">
          <GlassPanel className="p-6">
            <SectionHeading
              eyebrow={t("Demo User · deterministic history")}
              title={t("Now vs Past")}
              description={t("A temporal comparison of registered demo observations. This view is descriptive and does not predict an outcome.")}
            />
            <dl className="mt-6 divide-y divide-border/60 rounded-md border border-border/70">
              {twinState.comparisons.map((comparison) => (
                <div key={comparison.metricId} className="grid gap-2 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div>
                    <dt className="font-medium">{t(historyMetricLabels[comparison.metricId])}</dt>
                    {comparison.status === "insufficient_evidence" ? (
                      <dd className="mt-1 text-sm leading-5 text-muted">{t("Insufficient historical evidence")}</dd>
                    ) : (
                      <dd className="mt-1 text-sm leading-5 text-muted">
                        {t("{past} on {pastDate} → {current} on {currentDate}", {
                          past: historyValue(comparison, comparison.pastValue),
                          pastDate: comparison.referenceDate ? historyDate(comparison.referenceDate) : "—",
                          current: historyValue(comparison, comparison.currentValue),
                          currentDate: comparison.currentDate ? historyDate(comparison.currentDate) : "—",
                        })}
                      </dd>
                    )}
                  </div>
                  <dd className="text-right font-semibold tabular-nums text-foreground">
                    {comparison.status === "insufficient_evidence"
                      ? "—"
                      : t("Absolute {absolute} · Relative {relative}", {
                          absolute: historyAbsoluteChange(comparison),
                          relative: comparison.relativeChange === null ? "—" : formatPercent(comparison.relativeChange, 1),
                        })}
                  </dd>
                </div>
              ))}
            </dl>
            <StateNotice
              state="insufficient"
              compact
              title={t("No sufficient historical evidence for other metrics")}
              detail={t("Selection, Sizing, Exit, Friction, Disposition, and Loss Averaging remain current evidence only; no historical series is inferred.")}
            />
          </GlassPanel>
        </TabsContent>

        <TabsContent value="peer" className="space-y-3">
          <div className="flex flex-col gap-3 rounded-md border border-border/70 bg-white/[0.022] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <UsersRound className="size-4 shrink-0 text-accent" aria-hidden="true" />
              <strong className="truncate font-medium">{t("Synthetic Demo Cohort")}</strong>
              <span className="text-muted">·</span>
              <span className="whitespace-nowrap tabular-nums text-muted">N={formatNumber(peerBenchmark.cohortN)}</span>
            </div>
            <Sheet>
              <SheetTrigger asChild>
                <Button type="button" variant="quiet" size="sm" className="shrink-0">
                  {t("View cohort definition")}
                  <ChevronRight aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent>
                <SheetTitle className="text-xl font-semibold tracking-tight">{t("Cohort definition")}</SheetTitle>
                <SheetDescription className="mt-2 text-sm leading-6 text-muted">
                  {t("The fixed metadata behind this synthetic comparison.")}
                </SheetDescription>
                <p className="mt-7 border-y border-border/70 py-4 text-sm leading-6 text-muted">{t(peerBenchmark.cohort.description)}</p>
                <dl className="divide-y divide-border/65">
                  {[
                    [t("Cohort ID"), peerBenchmark.cohort.id],
                    [t("Market"), t(peerBenchmark.cohort.market)],
                    [t("Asset type"), peerBenchmark.cohort.assetTypes.map((value) => t(value)).join(", ")],
                    [t("Position scope"), t(peerBenchmark.cohort.direction)],
                    [t("Observation window"), `${historyDate(peerBenchmark.cohort.observationStart)} → ${historyDate(peerBenchmark.cohort.observationEnd)}`],
                    [t("Cohort N"), formatNumber(peerBenchmark.cohortN)],
                    [t("Minimum descriptive N"), formatNumber(peerBenchmark.cohort.minDescriptiveN)],
                    [t("Data tier"), t("Synthetic / Demo")],
                  ].map(([label, value]) => (
                    <div key={label} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] gap-5 py-4 text-sm">
                      <dt className="text-muted">{label}</dt>
                      <dd className="text-right font-medium">{value}</dd>
                    </div>
                  ))}
                </dl>
                <dl className="mt-5 divide-y divide-border/65 border-t border-border/65">
                  {peerBenchmark.metrics.map((metric) => (
                    <div key={metric.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] gap-5 py-4 text-sm">
                      <dt className="text-muted">{t(metric.label)} · N={formatNumber(metric.metricN)}</dt>
                      <dd className="text-right font-medium">{metric.quantileMethod} · {metric.percentileMethod}</dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-5 border-t border-border/65 pt-4">
                  <h3 className="text-sm font-medium">{t("Cohort limitations")}</h3>
                  <ul className="mt-2 space-y-1 text-xs leading-5 text-muted">
                    {peerBenchmark.cohort.limitations.map((limitation) => (
                      <li key={limitation}>• {t(limitation)}</li>
                    ))}
                  </ul>
                </div>
                <StateNotice
                  state="demo"
                  compact
                  title={t("Synthetic cohort boundary")}
                  detail={t("These deterministic demo values describe only the stated Demo Cohort definition and N. They do not represent the distribution of real Chinese investors.")}
                />
              </SheetContent>
            </Sheet>
          </div>

          {completePeerMetrics.length > 0 ? (
            <GlassPanel className="overflow-hidden">
              <div className="px-5 py-3.5">
                <SectionHeading
                  eyebrow={t("Difference summary")}
                  title={t("Compared with your Demo Cohort")}
                  description={t("Compared by distance from the 50th percentile. This is descriptive context, not a quality ranking.")}
                />
              </div>
              <div className={`grid border-t border-border/60 ${completePeerMetrics.length > 1 ? "md:grid-cols-2 md:divide-x md:divide-border/60" : ""}`}>
                {[
                  { label: t("Furthest from cohort median"), metric: furthestFromCohortMedian },
                  ...(completePeerMetrics.length > 1 ? [{ label: t("Closest to cohort median"), metric: closestToCohortMedian }] : []),
                ].map(({ label, metric }) => (
                  <div key={label} className="relative overflow-hidden px-5 py-3">
                    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_0%,rgba(111,214,224,.08),transparent_52%)]" aria-hidden="true" />
                    <div className="relative flex items-end justify-between gap-4">
                      <div>
                        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</span>
                        <h3 className="mt-1 text-[15px] font-semibold">{t(metric.label)}</h3>
                        <p className="mt-1 text-xs text-muted">{medianDifference(metric)}</p>
                      </div>
                      <AnimatedNumber
                        value={metric.chartMetric.percentile}
                        format={(value) => t("Percentile {percentile}", { percentile: formatNumber(Math.round(value)) })}
                        className="whitespace-nowrap text-lg font-semibold text-accent"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </GlassPanel>
          ) : null}

          <GlassPanel className="overflow-hidden">
            <div className="px-5 py-3.5">
              <SectionHeading
                eyebrow={t("Cohort distribution")}
                title={t("Where you sit")}
                description={t("P25, median and P75 come from the registered synthetic cohort. A higher percentile describes position only; it does not mean better.")}
              />
            </div>
            <div className="divide-y divide-border/60 border-t border-border/60">
              {peerBenchmark.metrics.map((metric) => {
                const [lowDirection, highDirection] = peerMetricDirections[metric.id] ?? ["Lower value", "Higher value"];
                return (
                  <article key={metric.id} className="group relative overflow-hidden px-5 py-2.5">
                    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_78%_50%,rgba(105,207,219,.07),transparent_38%)] opacity-0 transition-opacity duration-200 group-hover:opacity-100" aria-hidden="true" />
                    <div className="relative flex flex-wrap items-center justify-between gap-x-5 gap-y-1">
                      <h3 className="text-sm font-semibold">{t(metric.label)}</h3>
                      <p className="text-xs tabular-nums text-muted">
                        {metric.chartMetric ? medianDifference(metric as PeerBenchmarkMetricView & { chartMetric: NonNullable<PeerBenchmarkMetricView["chartMetric"]> }) : t("Insufficient cohort evidence")}
                      </p>
                    </div>
                    <div className="relative mt-1.5 flex justify-between text-[10px] text-muted">
                      <span>← {t(lowDirection)}</span>
                      <span>{t(highDirection)} →</span>
                    </div>
                    <p className="relative mt-1 text-[10px] tabular-nums text-muted">{t("Metric N")}: {formatNumber(metric.metricN)} · {historyDate(metric.observationStart)} → {historyDate(metric.observationEnd)}</p>
                    {metric.chartMetric ? (
                      <div className="relative"><PeerRangeChart metric={metric.chartMetric} /></div>
                    ) : (
                      <StateNotice
                        state="insufficient"
                        compact
                        title={t("Insufficient cohort evidence")}
                        detail={metric.reason ?? t("This metric does not have enough eligible synthetic cohort observations to show a range.")}
                      />
                    )}
                  </article>
                );
              })}
            </div>
          </GlassPanel>

          <StateNotice
            state="demo"
            compact
            title={t("Synthetic cohort boundary")}
            detail={t("These deterministic demo values describe only the stated Demo Cohort definition and N. They do not represent the distribution of real Chinese investors.")}
          />
          <p className="flex items-start gap-2 text-xs leading-5 text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            {t("Percentiles are descriptive comparison context, not performance forecasts or suitability guidance.")}
          </p>
        </TabsContent>

        <TabsContent value="user">
          <GlassPanel className="p-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div className="max-w-2xl">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <LockKeyhole className="size-4 text-accent" aria-hidden="true" />
                  {t("Permission required")}
                </div>
                <SectionHeading
                  eyebrow={t("Private comparison")}
                  title={t("Me vs User")}
                  description={t("An invitation establishes whether a limited evidence comparison may be shown. No private information is visible before consent.")}
                />
              </div>
              <Button type="button" variant="primary" disabled aria-label={t("Create invite (not connected in this demo)")}>
                <Send aria-hidden="true" />
                {t("Invite not connected")}
              </Button>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {[
                ["1", "Invite", "Create a consent-bound invitation."],
                ["2", "Awaiting response", "The invite is pending; no comparison is available."],
                ["3", "Authorized", "Only the agreed comparison summary can appear."],
              ].map(([step, label, detail]) => (
                <div key={step} className="rounded-md border border-border/70 bg-white/[0.025] p-4">
                  <span className="text-xs font-semibold text-accent">{step}</span>
                  <h3 className="mt-2 font-medium">{t(label)}</h3>
                  <p className="mt-1 text-sm leading-5 text-muted">{t(detail)}</p>
                </div>
              ))}
            </div>
            <StateNotice
              state="empty"
              compact
              title={t("No authorized comparison selected")}
              detail={t("A connected consent service would be required before an invitation or shared evidence summary could exist. This demo creates neither.")}
            />
            <div className="mt-5 flex items-center gap-2 text-xs leading-5 text-muted">
              <ShieldCheck className="size-4 shrink-0 text-accent" aria-hidden="true" />
              {t("Permission status is the only state shown here until an invite is accepted.")}
            </div>
          </GlassPanel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
