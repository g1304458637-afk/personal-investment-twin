import { Database, History } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FinancialObjectRow } from "@/components/investments/FinancialObjectRow";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { investments } from "@/data/backendEvidence";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi, type RuntimeInvestments } from "@/data/runtimeService";
import { useLocale } from "@/locales/LocaleProvider";

export function InvestmentsPage() {
  const { locale, t, formatNumber } = useLocale();
  const data = useDataMode();
  const [runtime, setRuntime] = useState<RuntimeInvestments | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  useEffect(() => {
    if (data.mode !== "real_user" || !data.activeAccount) { setRuntime(null); return; }
    void realUserApi.investments(data.activeAccount.subject_id, data.activeAccount.account_id)
      .then(setRuntime).catch((value) => setRuntimeError(String(value)));
  }, [data.mode, data.activeAccount]);
  const view = useMemo(() => {
    if (data.mode !== "real_user" || !runtime) return investments;
    const rows = runtime.episodes.map((episode) => ({ episodeId: episode.episode_id,
      subjectId: runtime.subject_id, instrumentId: episode.instrument_id, displayName: episode.display_name,
      isSynthetic: false, status: episode.status, openedAt: episode.opened_at, closedAt: episode.closed_at,
      durationDays: episode.duration_days, durationKind: episode.duration_kind,
      quantity: episode.quantity, averageCost: episode.average_cost, valuationAt: episode.valuation_at,
      valuationPrice: episode.valuation_price, marketValue: episode.market_value }));
    return { subjectId: runtime.subject_id, asOf: runtime.as_of, dataTier: runtime.data_tier,
      portfolioState: { status: runtime.portfolio_state_status === "available" ? "available" as const : "unavailable" as const, reason: runtime.portfolio_state_reason },
      summary: { openEpisodeCount: runtime.summary.open_episode_count, closedEpisodeCount: runtime.summary.closed_episode_count, currentPositionCount: runtime.summary.current_position_count },
      openEpisodes: rows.filter((x) => x.status === "open"), closedEpisodes: rows.filter((x) => x.status === "closed"),
      primaryEpisodeId: null };
  }, [data.mode, runtime]);
  if (data.mode === "real_user" && !data.activeAccount) return <div className="page"><PageHeader showDemo={false} eyebrow={t("Investment experience")} title={t("My Investments")} description={t("Browse the position Episodes formed from actual executions. Current marks are valuations, not exits or predictions.")} /><StateNotice state="empty" title={t("No real account imported yet.")} detail={t("Import transactions from Data & Accounts before opening real-user investments.")} /></div>;
  if (data.mode === "real_user" && !runtime) return <div className="page"><PageHeader showDemo={false} eyebrow={t("Investment experience")} title={t("My Investments")} description={t("Browse the position Episodes formed from actual executions. Current marks are valuations, not exits or predictions.")} /><StateNotice state={runtimeError ? "disconnected" : "loading"} title={runtimeError ? t("Portfolio state is unavailable") : t("Loading…")} detail={runtimeError ?? t("Rebuilding from local canonical facts.")} /></div>;
  const asOf = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(view.asOf));
  const portfolioAvailable = view.portfolioState.status === "available";
  const primaryEpisode = view.primaryEpisodeId
    ? [...view.closedEpisodes, ...view.openEpisodes].find((episode) => episode.episodeId === view.primaryEpisodeId) ?? null
    : null;
  const openEpisodes = view.openEpisodes.filter((episode) => episode.episodeId !== view.primaryEpisodeId);
  const closedEpisodes = view.closedEpisodes.filter((episode) => episode.episodeId !== view.primaryEpisodeId);

  return (
    <div className="page investments-page">
      <PageHeader
        showDemo={data.mode === "demo"}
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
              <dd>{formatNumber(view.summary.currentPositionCount)}</dd>
            </div>
            <div>
              <dt>{t("Open Episodes")}</dt>
              <dd>{formatNumber(view.summary.openEpisodeCount)}</dd>
            </div>
            <div>
              <dt>{t("Closed Episodes")}</dt>
              <dd>{formatNumber(view.summary.closedEpisodeCount)}</dd>
            </div>
            <div>
              <dt>{t("Portfolio state")}</dt>
              <dd className="product-fact-strip__text">{t("Available")}</dd>
            </div>
          </dl>
        ) : (
          <StateNotice
            state={view.portfolioState.status === "not_started" ? "empty" : "disconnected"}
            title={t(view.portfolioState.status === "not_started" ? "No investment records yet" : "Portfolio state is unavailable")}
            detail={runtimeError ?? t(view.portfolioState.reason ?? "The current position state cannot be shown from the available facts.")}
          />
        )}
      </section>

      {primaryEpisode ? (
        <section className="product-section" aria-labelledby="primary-demo-heading">
          <SectionHeading
            eyebrow={t("Product Demo")}
            title={t("Primary Product Demo")}
            description={t("This is the canonical Product Demo path used for visual acceptance.")}
          />
          <div className="financial-object-list">
            <FinancialObjectRow episode={primaryEpisode} primary />
          </div>
        </section>
      ) : null}

      <section className="product-section" aria-labelledby="open-episodes-heading">
        <SectionHeading
          eyebrow={t("In progress")}
          title={t("Open Investment Episodes")}
          description={t("Each row is an ongoing position lifecycle. Its quantity, average cost, and valuation are backend replay facts.")}
        />
        {openEpisodes.length > 0 ? (
          <div className="financial-object-list">
            {openEpisodes.map((episode) => (
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
        {closedEpisodes.length > 0 ? (
          <div className="financial-object-list">
            {closedEpisodes.map((episode) => (
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
          <strong>{t(data.mode === "demo" ? "Synthetic presentation data" : "Local deterministic data")}</strong>
          {t(data.mode === "demo" ? "Display names are neutral demo metadata. Canonical instrument IDs and Episode references remain unchanged." : "Real-user facts are loaded from the local Python runtime; generated Demo JSON is not used.")}
        </p>
        <History aria-hidden="true" />
      </div>
    </div>
  );
}
