import {
  ArrowRight,
  BrainCircuit,
  BriefcaseBusiness,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { FinancialObjectRow } from "@/components/investments/FinancialObjectRow";
import { Button } from "@/components/ui/button";
import { investments, twinState } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";

export default function OverviewHomePage() {
  const { locale, t, formatNumber } = useLocale();
  const { currentSnapshot } = twinState;
  const date = (value: string) => new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
  const portfolioAvailable = investments.portfolioState.status === "available";
  const openPreview = investments.openEpisodes.slice(0, 3);

  return (
    <div className="page overview-home">
      <PageHeader
        eyebrow={t("Personal Investment Twin")}
        title={t("What is worth knowing now")}
        description={t("A concise starting point built from the current deterministic snapshot—not a module directory or ranked alert feed.")}
        actions={<span className="as-of-label">{t("As of {date}", { date: date(investments.asOf) })}</span>}
      />

      <section className="product-section overview-current" aria-labelledby="overview-current-heading">
        <SectionHeading
          eyebrow={t("Current state")}
          title={t("Your represented investment state")}
          description={t("These counts and availability facts come directly from the backend snapshot.")}
        />
        {portfolioAvailable ? (
          <dl className="product-fact-strip product-fact-strip--overview">
            <div><dt>{t("Current positions")}</dt><dd>{formatNumber(investments.summary.currentPositionCount)}</dd></div>
            <div><dt>{t("Investment experiences in progress")}</dt><dd>{formatNumber(investments.summary.openEpisodeCount)}</dd></div>
            <div><dt>{t("Completed investment experiences")}</dt><dd>{formatNumber(investments.summary.closedEpisodeCount)}</dd></div>
            <div><dt>{t("Data tier")}</dt><dd className="product-fact-strip__text">{t("Synthetic / Demo")}</dd></div>
          </dl>
        ) : (
          <StateNotice
            state={investments.portfolioState.status === "not_started" ? "empty" : "disconnected"}
            title={t(investments.portfolioState.status === "not_started" ? "No investment records yet" : "Portfolio state is unavailable")}
            detail={t(investments.portfolioState.reason ?? "The current position state cannot be shown from the available facts.")}
          />
        )}
      </section>

      <section className="product-section" aria-labelledby="overview-open-heading">
        <SectionHeading
          eyebrow={t("In progress")}
          title={t("Investment experiences in progress")}
          description={t("A short continuation list; the complete open and closed history lives in My Investments.")}
          action={<Button asChild size="sm" variant="quiet"><Link to="/investments">{t("View all investments")} <ArrowRight /></Link></Button>}
        />
        {openPreview.length > 0 ? (
          <div className="financial-object-list">
            {openPreview.map((episode) => <FinancialObjectRow compact key={episode.episodeId} episode={episode} />)}
          </div>
        ) : (
          <StateNotice
            state="empty"
            compact
            title={t("No investment experiences are currently in progress")}
            detail={t("Open Episodes will appear here when the deterministic lifecycle provides them.")}
          />
        )}
      </section>

      <section className="product-section overview-twin" aria-labelledby="overview-twin-heading">
        <div className="overview-twin__identity">
          <span className="overview-twin__icon"><BrainCircuit aria-hidden="true" /></span>
          <div>
            <span className="section-heading__eyebrow">{t("My Twin")}</span>
            <h2 id="overview-twin-heading">{t("A current point-in-time Twin is available")}</h2>
            <p>{t("Snapshot {date} · {count} behavior metrics available. Historical comparison and evidence maturity remain in My Twin.", {
              date: date(currentSnapshot.snapshotAt),
              count: currentSnapshot.dataQuality.availableBehaviorMetricCount,
            })}</p>
          </div>
        </div>
        <Button asChild variant="secondary"><Link to="/twin">{t("Open My Twin")} <ArrowRight /></Link></Button>
      </section>

      {currentSnapshot.dataQuality.issueCount > 0 ? (
        <StateNotice
          state="insufficient"
          compact
          title={t("Data quality needs attention")}
          detail={currentSnapshot.dataQuality.issues.map((issue) => t(issue)).join(" ")}
        />
      ) : null}

      <section className="product-section overview-continue" aria-labelledby="overview-continue-heading">
        <SectionHeading
          eyebrow={t("Continue")}
          title={t("Choose the next context")}
          description={t("Browse what you experienced, or inspect the deterministic impact of a proposed trade before acting.")}
        />
        <div className="overview-continue__links">
          <Link to="/investments">
            <BriefcaseBusiness aria-hidden="true" />
            <span><strong>{t("My Investments")}</strong><small>{t("Browse open and closed Investment Episodes")}</small></span>
            <ArrowRight aria-hidden="true" />
          </Link>
          <Link to="/pretrade">
            <ScanSearch aria-hidden="true" />
            <span><strong>{t("Pre-decision")}</strong><small>{t("Check factual portfolio changes before a proposed execution")}</small></span>
            <ArrowRight aria-hidden="true" />
          </Link>
        </div>
      </section>

      <p className="overview-provenance">
        <ShieldCheck aria-hidden="true" />
        {t("Synthetic backend-generated facts for product demonstration; no live account is connected.")}
      </p>
    </div>
  );
}
