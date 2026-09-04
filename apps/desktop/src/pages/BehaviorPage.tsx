import { ArrowRight, CircleHelp, FlaskConical } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { HistoricalMetricChart } from "@/components/charts/HistoricalMetricChart";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { EvidenceObservationRow } from "@/components/review/EvidenceObservationRow";
import { Button } from "@/components/ui/button";
import {
  behaviorHistory,
  behaviorMetrics,
  reviewView,
  translateEvidenceText,
} from "@/data/backendEvidence";
import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";

type HistoricalPatternId = "hhi" | "turnover";

const historyExplanations: Record<HistoricalPatternId, string> = {
  hhi: "HHI history shows deterministic portfolio-concentration snapshots. It does not judge whether concentration is good or bad.",
  turnover: "Turnover history shows the registered daily turnover observations. It does not infer motive or future trading activity.",
};

export function BehaviorPage() {
  const { t } = useLocale();
  const [historicalId, setHistoricalId] = useState<HistoricalPatternId>("hhi");
  const selectedObservation = reviewView.patterns.find((item) => item.id === historicalId)!;
  const selectedMetric = behaviorMetrics.find((item) => item.id === historicalId)!;
  const selectedHistory = historicalId === "hhi" ? behaviorHistory.hhi : behaviorHistory.turnover;

  return (
    <div className="page review-detail-page">
      <PageHeader
        eyebrow={t("Review")}
        title={t("Investment patterns")}
        description={t("Observe portfolio structure and recorded trading patterns without inferring personality, motivation, skill, or future behavior.")}
        actions={<DemoBadge />}
      />

      <section className="product-section" aria-labelledby="portfolio-structure-heading">
        <SectionHeading
          eyebrow={t("Portfolio structure")}
          title={t("How holdings were distributed")}
          description={t("A point-in-time concentration observation copied from the deterministic portfolio snapshot.")}
        />
        <div className="review-observation-list" id="portfolio-structure-heading">
          <EvidenceObservationRow observation={reviewView.patterns[0]} inspectorContext="Investment pattern evidence" />
        </div>
      </section>

      <section className="product-section" aria-labelledby="trading-activity-heading">
        <SectionHeading
          eyebrow={t("Trading activity")}
          title={t("How much recorded trading occurred")}
          description={t("A multi-day turnover observation over the registered window; it does not estimate unrecorded costs.")}
        />
        <div className="review-observation-list" id="trading-activity-heading">
          <EvidenceObservationRow observation={reviewView.patterns[1]} inspectorContext="Investment pattern evidence" />
        </div>
      </section>

      <section className="product-section" aria-labelledby="sale-observation-heading">
        <SectionHeading
          eyebrow={t("Sale observations")}
          title={t("How eligible realized outcomes were recorded")}
          description={t("PGR, PLR, and their backend-provided difference describe eligible sale observations only.")}
        />
        <div className="review-observation-list" id="sale-observation-heading">
          <EvidenceObservationRow observation={reviewView.patterns[2]} inspectorContext="Investment pattern evidence" />
        </div>
      </section>

      <section className="product-section" aria-labelledby="addition-observation-heading">
        <SectionHeading
          eyebrow={t("Addition observations")}
          title={t("Additions made below prior average cost")}
          description={t("The registered event count is descriptive and does not establish intent or decision quality.")}
        />
        <div className="review-observation-list" id="addition-observation-heading">
          <EvidenceObservationRow observation={reviewView.patterns[3]} inspectorContext="Investment pattern evidence" />
        </div>
      </section>

      <section className="product-section review-history" aria-labelledby="recorded-history-heading">
        <SectionHeading
          eyebrow={t("Recorded history")}
          title={t("Historical observations with real backend series")}
          description={t("Only HHI and Turnover have historical series in v1. Self-relative percentile context remains in My Twin.")}
          action={<Button asChild size="sm" variant="quiet"><Link to="/twin">{t("View against my past")} <ArrowRight /></Link></Button>}
        />
        <div className="review-history__tabs" role="group" aria-label={t("Historical pattern")}>
          {(["hhi", "turnover"] as const).map((id) => (
            <button
              type="button"
              key={id}
              className={cn(id === historicalId && "is-active")}
              aria-pressed={id === historicalId}
              onClick={() => setHistoricalId(id)}
            >
              {t(id === "hhi" ? "Portfolio concentration" : "Turnover intensity")}
            </button>
          ))}
        </div>
        <div className="review-history__surface">
          <div>
            <div className="review-history__heading">
              <span>{t(selectedObservation.eyebrowKey)}</span>
              <h3>{t(selectedObservation.titleKey)}</h3>
              <p>{t(historyExplanations[historicalId])}</p>
            </div>
            <HistoricalMetricChart
              series={selectedHistory}
              label={t(selectedObservation.titleKey)}
              singleValueLabel={translateEvidenceText(t, selectedMetric.primary, selectedMetric.primaryValues)}
              percent={historicalId === "turnover"}
            />
          </div>
          <dl>
            <div><dt>{t("Current observation")}</dt><dd>{translateEvidenceText(t, selectedMetric.primary, selectedMetric.primaryValues)}</dd></div>
            <div><dt>{t("Evidence coverage")}</dt><dd>N={selectedMetric.observationCount ?? "—"}</dd></div>
            <div><dt>{t("Status")}</dt><dd><StatusBadge status={selectedMetric.status} compact /></dd></div>
            <div><dt>{t("Data context")}</dt><dd><FlaskConical aria-hidden="true" />{t("Demo / Synthetic")}</dd></div>
          </dl>
        </div>
      </section>

      <p className="review-method-note">
        <CircleHelp aria-hidden="true" />
        {t("These observations describe recorded data. They do not infer aggressiveness, fear, discipline, risk tolerance, or any other personality trait.")}
      </p>
    </div>
  );
}
