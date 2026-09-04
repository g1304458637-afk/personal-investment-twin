import { ArrowRight, BetweenHorizontalStart, BriefcaseBusiness, ReceiptText } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { DemoBadge } from "@/components/common/StatusBadge";
import { EvidenceObservationRow } from "@/components/review/EvidenceObservationRow";
import { Button } from "@/components/ui/button";
import { reviewView } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";

export function DecisionsPage() {
  const { t } = useLocale();

  return (
    <div className="page review-detail-page">
      <PageHeader
        eyebrow={t("Review")}
        title={t("Decision review")}
        description={t("Review deterministic evidence about asset choice, position sizing, and completed exits without turning outcomes into a score or recommendation.")}
        actions={
          <Button asChild variant="quiet" size="sm">
            <Link to="/investments"><BriefcaseBusiness />{t("View investment experiences")}</Link>
          </Button>
        }
      />

      <section className="product-section" aria-labelledby="decision-evidence-heading">
        <SectionHeading
          eyebrow={t("Decision evidence")}
          title={t("What the recorded decisions support")}
          description={t("The order follows a stable product taxonomy—asset choice, sizing, then completed exit—not result direction or magnitude.")}
        />
        <div className="review-observation-list" id="decision-evidence-heading">
          {reviewView.decisions.map((observation) => (
            <EvidenceObservationRow
              key={observation.id}
              observation={observation}
              inspectorContext="Decision evidence"
            />
          ))}
        </div>
      </section>

      <section className="product-section" aria-labelledby="execution-evidence-heading">
        <SectionHeading
          eyebrow={t("Execution record")}
          title={t("Recorded execution costs")}
          description={t("Recorded explicit fees describe execution friction. They are kept separate because they are not a decision category such as selection, sizing, or exit.")}
        />
        <div className="review-observation-list" id="execution-evidence-heading">
          {reviewView.execution.map((observation) => (
            <EvidenceObservationRow
              key={observation.id}
              observation={observation}
              inspectorContext="Execution evidence"
            />
          ))}
        </div>
      </section>

      <section className="review-boundary-strip" aria-label={t("Decision Event and Evidence are separate")}>
        <BetweenHorizontalStart aria-hidden="true" />
        <div>
          <strong>{t("Decision Event and Evidence are separate")}</strong>
          <p>{t("An Episode records when a position was opened, added to, reduced, or closed. Evidence is produced only where a registered method supports an observation, and may describe an Episode rather than one individual execution.")}</p>
        </div>
        <Button asChild size="sm" variant="quiet">
          <Link to="/investments">{t("Browse Episodes")} <ArrowRight /></Link>
        </Button>
      </section>

      <p className="review-method-note">
        <ReceiptText aria-hidden="true" />
        {t("Complete, insufficient, and experimental describe evidence availability—not whether a decision was good or bad.")}
      </p>
      <p className="overview-provenance"><DemoBadge compact />{t("Synthetic offline fixture; no real investor account is represented.")}</p>
    </div>
  );
}
