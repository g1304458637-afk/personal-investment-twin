import { Database, History } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FinancialObjectRow } from "@/components/investments/FinancialObjectRow";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { adaptDemoInvestmentsCatalog } from "@/data/investments";
import { belongsToExample } from "@/data/accountContext";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi, type RuntimeInvestments } from "@/data/runtimeService";
import { useLocale } from "@/locales/LocaleProvider";

export function InvestmentsPage() {
  const { locale, t, formatNumber } = useLocale();
  const data = useDataMode();
  const [loadedRuntime, setRuntime] = useState<RuntimeInvestments | null>(null);
  const runtime = loadedRuntime?.subject_id === data.activeAccount?.subject_id && loadedRuntime?.account_id === data.activeAccount?.account_id ? loadedRuntime : null;
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setRuntime(null); setRuntimeError(null);
    if (data.mode !== "real_user" || !data.activeAccount) return;
    void realUserApi.investments(data.activeAccount.subject_id, data.activeAccount.account_id)
      .then((value) => { if (!cancelled) setRuntime(value); }).catch((value) => { if (!cancelled) setRuntimeError(String(value)); });
    return () => { cancelled = true; };
  }, [data.mode, data.activeAccount]);
  const view = useMemo(() => {
    if (data.mode !== "real_user" || !runtime) {
      const entries = positionEpisodeDemo.entries.filter((entry) => belongsToExample(entry, data.exampleAccount));
      return adaptDemoInvestmentsCatalog({ ...positionEpisodeDemo, entries, defaultEpisodeId: entries[0].episode.episodeId });
    }
    const rows = runtime.episodes.map((episode) => ({ episodeId: episode.episode_id,
      subjectId: runtime.subject_id, instrumentId: episode.instrument_id, displayName: episode.display_name,
      isSynthetic: false, currency: episode.currency, status: episode.status, openedAt: episode.opened_at, closedAt: episode.closed_at,
      durationDays: episode.duration_days, durationKind: episode.duration_kind,
      quantity: episode.quantity, averageCost: episode.average_cost, valuationAt: episode.valuation_at,
      valuationPrice: episode.valuation_price, marketValue: episode.market_value }));
    return { subjectId: runtime.subject_id, asOf: runtime.as_of, dataTier: runtime.data_tier,
      portfolioState: { status: runtime.portfolio_state_status === "available" ? "available" as const : "unavailable" as const, reason: runtime.portfolio_state_reason },
      summary: { openEpisodeCount: runtime.summary.open_episode_count, closedEpisodeCount: runtime.summary.closed_episode_count, currentPositionCount: runtime.summary.current_position_count },
      openEpisodes: rows.filter((x) => x.status === "open"), closedEpisodes: rows.filter((x) => x.status === "closed"),
      primaryEpisodeId: null };
  }, [data.mode, runtime, data.exampleAccount]);
  if (data.mode === "real_user" && !data.activeAccount) return <div className="page space-y-6"><PageHeader showDemo={false} title={t("My Investments")} description={t("Import executions to reconstruct complete investment experiences.")} /><p className="text-sm text-muted">{t("Historical prices are needed for valuation and parts of the review.")}</p>{data.accountsLoading || data.accountError ? <StateNotice state={data.accountError ? "error" : "loading"} title={t(data.accountError ? "Could not read local accounts" : "Loading…")} detail={data.accountError ?? t("Opening view…")} /> : null}<div className="flex gap-3"><Button asChild variant="primary"><Link to="/data">{t("Import data")}</Link></Button><Button variant="quiet" onClick={() => data.setMode("demo")}>{t("View example account")}</Button></div></div>;
  if (data.mode === "real_user" && !runtime) return <div className="page"><PageHeader showDemo={false} eyebrow={t("Investment experience")} title={t("My Investments")} description={t("Browse the position Episodes formed from actual executions. Current marks are valuations, not exits or predictions.")} /><StateNotice state={runtimeError ? "disconnected" : "loading"} title={runtimeError ? t("Portfolio state is unavailable") : t("Loading…")} detail={runtimeError ?? t("Rebuilding from local canonical facts.")} /></div>;
  const asOf = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(view.asOf));
  const portfolioAvailable = view.portfolioState.status === "available";
  const openEpisodes = view.openEpisodes;
  const closedEpisodes = view.closedEpisodes;

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
            detail={t("No closed Position Episode is present in this account snapshot.")}
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
