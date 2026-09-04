import { ArrowRight, BetweenHorizontalStart, BrainCircuit, BriefcaseBusiness, History } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { reviewView } from "@/data/backendEvidence";
import type { ReviewObservationView } from "@/data/review";
import { useLocale } from "@/locales/LocaleProvider";

function ObservationIndex({ observations }: { observations: readonly ReviewObservationView[] }) {
  const { t } = useLocale();
  return (
    <ul className="review-domain-index">
      {observations.map((observation) => (
        <li key={observation.id}>
          <span>{t(observation.titleKey)}</span>
          {observation.status === "unavailable"
            ? <small>{t("Unavailable")}</small>
            : <StatusBadge status={observation.status} compact />}
        </li>
      ))}
    </ul>
  );
}

export function ReviewPage() {
  const { t } = useLocale();
  return (
    <div className="page review-page">
      <PageHeader
        eyebrow={t("Review")}
        title={t("Review decisions and investment patterns")}
        description={t("Look back at decisions and observable investment patterns supported by recorded investment evidence.")}
        actions={<DemoBadge />}
      />

      <section className="product-section">
        <SectionHeading
          eyebrow={t("How review works")}
          title={t("From investment experience to auditable evidence")}
          description={t("Review keeps what happened, what the evidence supports, and how it was calculated as separate layers.")}
        />
        <ol className="review-flow">
          <li><BriefcaseBusiness aria-hidden="true" /><span><strong>{t("Investment Episode")}</strong><small>{t("A position lifecycle formed from recorded executions")}</small></span></li>
          <li><BetweenHorizontalStart aria-hidden="true" /><span><strong>{t("Decision Event")}</strong><small>{t("What happened at a recorded execution")}</small></span></li>
          <li><History aria-hidden="true" /><span><strong>{t("Evidence")}</strong><small>{t("What a registered deterministic method can support")}</small></span></li>
        </ol>
      </section>

      <section className="product-section review-domain">
        <SectionHeading
          eyebrow={t("Decision review")}
          title={t("What the recorded decisions support")}
          description={t("Selection, sizing, and completed exits are decision evidence. Recorded fees remain a separate execution observation.")}
          action={<Button asChild size="sm" variant="quiet"><Link to="/review/decisions">{t("Open decision review")} <ArrowRight /></Link></Button>}
        />
        <ObservationIndex observations={[...reviewView.decisions, ...reviewView.execution]} />
      </section>

      <section className="product-section review-domain">
        <SectionHeading
          eyebrow={t("Investment patterns")}
          title={t("Observable portfolio and trading patterns")}
          description={t("Concentration, turnover, sale outcomes, and loss-state additions describe records—not personality or motive.")}
          action={<Button asChild size="sm" variant="quiet"><Link to="/review/patterns">{t("Open investment patterns")} <ArrowRight /></Link></Button>}
        />
        <ObservationIndex observations={reviewView.patterns} />
      </section>

      <section className="review-context-link" aria-label={t("Start from an investment experience")}>
        <BrainCircuit aria-hidden="true" />
        <div><strong>{t("Start from an investment experience")}</strong><p>{t("Open an Investment Episode to inspect its execution-backed Decision Events and linked Evidence.")}</p></div>
        <Link to="/investments">{t("Go to My Investments")} <ArrowRight aria-hidden="true" /></Link>
      </section>

      <p className="overview-provenance">{t("Synthetic review evidence for product demonstration; no real investor account is represented.")}</p>
    </div>
  );
}
