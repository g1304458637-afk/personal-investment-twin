import { Info, UsersRound } from "lucide-react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { peerCohort, peerMetrics } from "@/demo/fixture";
import { useLocale } from "@/locales/LocaleProvider";

export function PeerPage() {
  const { formatNumber, t } = useLocale();
  const formatPeerValue = (value: number, unit: string) => {
    if (unit === "×") return `${formatNumber(value, 2)}×`;
    return formatNumber(value, Number.isInteger(value) ? 0 : 2);
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Peer context")}
        title={t("Demo Cohort")}
        description={t("Synthetic cohort context for the Demo User. Distributional reference only; it is not an investment recommendation.")}
      />

      <GlassPanel className="p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <UsersRound className="size-4 text-accent" aria-hidden="true" />
              {t(peerCohort.name)}
            </div>
            <p className="mt-3 text-sm leading-6 text-muted">{t(peerCohort.definition)}</p>
          </div>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 rounded-md border border-border/70 bg-white/[0.025] px-4 py-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-[0.12em] text-muted">{t("Cohort N")}</dt>
              <dd className="mt-1 font-semibold tabular-nums">{formatNumber(peerCohort.n)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.12em] text-muted">{t("Data tier")}</dt>
              <dd className="mt-1 font-semibold">{t("Synthetic")}</dd>
            </div>
          </dl>
        </div>
        <div className="mt-5 border-t border-border/60 pt-4 text-xs leading-5 text-muted">{t(peerCohort.consent)}</div>
      </GlassPanel>

      <GlassPanel className="overflow-hidden">
        <div className="p-6 pb-4">
          <SectionHeading
            eyebrow={t("Distribution reference")}
            title={t("Where the Demo User sits")}
            description={t("P25, median and P75 describe the Demo Cohort distribution. Percentile is the Demo User’s position within this synthetic cohort.")}
          />
        </div>
        <div className="overflow-x-auto border-t border-border/60">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-white/[0.025] text-xs uppercase tracking-[0.1em] text-muted">
              <tr>
                <th className="px-6 py-3 font-medium">{t("Metric")}</th>
                <th className="px-4 py-3 font-medium">{t("Demo User")}</th>
                <th className="px-4 py-3 font-medium">P25</th>
                <th className="px-4 py-3 font-medium">{t("Median")}</th>
                <th className="px-4 py-3 font-medium">P75</th>
                <th className="px-6 py-3 font-medium">{t("Percentile")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {peerMetrics.map((metric) => (
                <tr key={metric.id} className="transition-colors hover:bg-white/[0.025]">
                  <th scope="row" className="px-6 py-4 font-medium text-foreground">{t(metric.label)}</th>
                  <td className="px-4 py-4 font-semibold tabular-nums">{formatPeerValue(metric.user, metric.unit)}</td>
                  <td className="px-4 py-4 tabular-nums text-muted">{formatPeerValue(metric.p25, metric.unit)}</td>
                  <td className="px-4 py-4 tabular-nums text-muted">{formatPeerValue(metric.median, metric.unit)}</td>
                  <td className="px-4 py-4 tabular-nums text-muted">{formatPeerValue(metric.p75, metric.unit)}</td>
                  <td className="px-6 py-4 tabular-nums">{t("{percentile}th", { percentile: formatNumber(metric.percentile) })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassPanel>

      <StateNotice
        state="demo"
        title={t("Synthetic cohort boundary")}
        detail={t("These deterministic demo values describe only the stated Demo Cohort definition and N. They do not represent real participants.")}
      />
      <p className="flex items-start gap-2 text-xs leading-5 text-muted">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {t("Percentiles are descriptive comparison context, not performance forecasts or suitability guidance.")}
      </p>
    </div>
  );
}
