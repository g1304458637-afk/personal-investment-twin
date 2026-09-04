import { Database, History } from "lucide-react";

import { FinancialObjectRow } from "@/components/investments/FinancialObjectRow";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { investments } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";

export function InvestmentsPage() {
  const { locale, t, formatNumber } = useLocale();
  const asOf = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(investments.asOf));
  const portfolioAvailable = investments.portfolioState.status === "available";

  return (
    <div className="page investments-page">
      <PageHeader
        eyebrow={t("Investment experience")}
        title={t("My Investments")}
        description={t("Browse the position Episodes formed from actual executions. Current marks are valuations, not exits or predictions.")}
        actions={<span className="as-of-label">{t("As of {date}", { date: asOf })}</span>}
      />

      <section className="product-section" aria-labelledby="investment-state-heading">
        <SectionHeading
          eyebrow={t("Current state")}
          title={t("What is currently represented")}
          description={t("Counts and position availability are copied from the deterministic point-in-time snapshot.")}
        />
        {portfolioAvailable ? (
          <dl className="product-fact-strip">
            <div>
              <dt>{t("Current positions")}</dt>
              <dd>{formatNumber(investments.summary.currentPositionCount)}</dd>
            </div>
            <div>
              <dt>{t("Open Episodes")}</dt>
              <dd>{formatNumber(investments.summary.openEpisodeCount)}</dd>
            </div>
            <div>
              <dt>{t("Closed Episodes")}</dt>
              <dd>{formatNumber(investments.summary.closedEpisodeCount)}</dd>
            </div>
            <div>
              <dt>{t("Portfolio state")}</dt>
              <dd className="product-fact-strip__text">{t("Available")}</dd>
            </div>
          </dl>
        ) : (
          <StateNotice
            state={investments.portfolioState.status === "not_started" ? "empty" : "disconnected"}
            title={t(investments.portfolioState.status === "not_started" ? "No investment records yet" : "Portfolio state is unavailable")}
            detail={t(investments.portfolioState.reason ?? "The current position state cannot be shown from the available facts.")}
          />
        )}
      </section>

      <section className="product-section" aria-labelledby="open-episodes-heading">
        <SectionHeading
          eyebrow={t("In progress")}
          title={t("Open Investment Episodes")}
          description={t("Each row is an ongoing position lifecycle. Its quantity, average cost, and valuation are backend replay facts.")}
        />
        {investments.openEpisodes.length > 0 ? (
          <div className="financial-object-list">
            {investments.openEpisodes.map((episode) => (
              <FinancialObjectRow key={episode.episodeId} episode={episode} />
            ))}
          </div>
        ) : (
          <StateNotice
            state="empty"
            compact
            title={t("No investment experiences are currently in progress")}
            detail={t("Closed history remains available below when the backend provides it.")}
          />
        )}
      </section>

      <section className="product-section" aria-labelledby="closed-episodes-heading">
        <SectionHeading
          eyebrow={t("Completed")}
          title={t("Closed Investment Episodes")}
          description={t("A closed Episode requires a real closing execution; a current market mark never closes an Episode.")}
        />
        {investments.closedEpisodes.length > 0 ? (
          <div className="financial-object-list">
            {investments.closedEpisodes.map((episode) => (
              <FinancialObjectRow key={episode.episodeId} episode={episode} />
            ))}
          </div>
        ) : (
          <StateNotice
            state="empty"
            compact
            title={t("No closed investment experiences yet")}
            detail={t("This subject has no closed Position Episode in the current synthetic snapshot.")}
          />
        )}
      </section>

      <div className="product-provenance-note">
        <Database aria-hidden="true" />
        <p>
          <strong>{t("Synthetic presentation data")}</strong>
          {t("Display names are neutral demo metadata. Canonical instrument IDs and Episode references remain unchanged.")}
        </p>
        <History aria-hidden="true" />
      </div>
    </div>
  );
}
