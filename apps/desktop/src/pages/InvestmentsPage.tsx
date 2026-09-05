
import { useEffect, useMemo, useState } from "react";

import { FinancialObjectRow } from "@/components/investments/FinancialObjectRow";
import { PageHeader } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { adaptDemoInvestmentsCatalog, archiveRows } from "@/data/investments";
import { belongsToExample } from "@/data/accountContext";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi, type RuntimeInvestments } from "@/data/runtimeService";
import { useLocale } from "@/locales/LocaleProvider";

export function InvestmentsPage() {
  const { locale, t } = useLocale();
  const data = useDataMode();
  const [filter, setFilter] = useState<"open" | "closed" | "all">("all");
  const [query, setQuery] = useState("");
  useEffect(() => { setFilter("all"); setQuery(""); }, [data.mode, data.activeAccount, data.exampleAccount]);
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
      valuationPrice: episode.valuation_price, marketValue: episode.market_value, outcome: episode.outcome_summary }));
    return { subjectId: runtime.subject_id, asOf: runtime.as_of, dataTier: runtime.data_tier,
      portfolioState: { status: runtime.portfolio_state_status === "available" ? "available" as const : "unavailable" as const, reason: runtime.portfolio_state_reason },
      summary: { openEpisodeCount: runtime.summary.open_episode_count, closedEpisodeCount: runtime.summary.closed_episode_count, currentPositionCount: runtime.summary.current_position_count },
      openEpisodes: rows.filter((x) => x.status === "open"), closedEpisodes: rows.filter((x) => x.status === "closed"),
      primaryEpisodeId: null };
  }, [data.mode, runtime, data.exampleAccount]);
  if (data.mode === "real_user" && !data.activeAccount) return <div className="page space-y-6"><PageHeader showDemo={false} title={t("Toujing · Personal investment review")} description={t("See how your decisions changed historical results. Compare same-stock paths using recorded facts.")} /><p className="text-sm text-muted">{t("Historical prices are needed for valuation and parts of the review.")}</p>{data.accountsLoading || data.accountError ? <StateNotice state={data.accountError ? "error" : "loading"} title={t(data.accountError ? "Could not read local accounts" : "Loading…")} detail={data.accountError ?? t("Opening view…")} /> : null}<div className="flex flex-wrap gap-3"><Button asChild variant="primary"><Link to="/data">{t("Import data")}</Link></Button><Button asChild variant="quiet"><Link to="/investments/compare-example">{t("View a same-stock comparison example")}</Link></Button><Button variant="quiet" onClick={() => data.setMode("demo")}>{t("View example account")}</Button></div></div>;
  if (data.mode === "real_user" && !runtime) return <div className="page"><PageHeader showDemo={false} eyebrow={t("Investment experience")} title={t("My Investments")} description={t("Browse the position Episodes formed from actual executions. Current marks are valuations, not exits or predictions.")} /><StateNotice state={runtimeError ? "disconnected" : "loading"} title={runtimeError ? t("Portfolio state is unavailable") : t("Loading…")} detail={runtimeError ?? t("Rebuilding from local canonical facts.")} /></div>;
  const date = (value: string) => Number.isNaN(Date.parse(value)) ? "—" : new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  const rows = archiveRows([...view.openEpisodes, ...view.closedEpisodes], filter, query);
  const hasInvestments = view.openEpisodes.length > 0 || view.closedEpisodes.length > 0;
  return <div className="page investments-page">
    <PageHeader showDemo={false} title={t("My Investments")}
      description={t("Complete investment experiences reconstructed from your records.")}
      actions={<div className="text-right text-xs text-muted"><p className="mb-1 text-foreground">{data.mode === "demo" ? t("Example account · Synthetic") : data.activeAccount?.display_name}</p>{t("Data as of {date}", {date: date(view.asOf)})}</div>} />
    {view.portfolioState.status !== "available" ? <StateNotice state="insufficient" title={t("Portfolio state is unavailable")} detail={t(view.portfolioState.reason ?? "The current position state cannot be shown from the available facts.")} /> : null}
    <div className="mt-7 mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-1" role="group" aria-label={t("Investment status")}>
        {(["open", "closed", "all"] as const).map((value) => <Button key={value} variant={filter === value ? "primary" : "quiet"} aria-pressed={filter === value} onClick={() => setFilter(value)}>{t({open: "Holding", closed: "Closed", all: "All investments"}[value])}</Button>)}
      </div>
      <input className="rounded-md border border-border bg-background px-3 py-2 text-sm" aria-label={t("Search securities")} placeholder={t("Search securities")} value={query} onChange={(event) => setQuery(event.target.value)} />
    </div>
    <p className="mb-3 text-[11px] text-muted">{t("Newest start date first · one row per investment")}</p>
    <div className="archive-column-head"><span>{t("Instrument")}</span><span>{t("Investment period")}</span><span>{t("Investment result")}</span></div>
    <div className="financial-object-list">{rows.map((episode) => <FinancialObjectRow key={episode.episodeId} episode={episode} />)}</div>
    {!rows.length && view.portfolioState.status === "available" ? <div className="py-8"><StateNotice compact state="empty"
      title={t(!hasInvestments ? "No investment records yet" : query ? "No matching investments" : filter === "open" ? "No investment experiences are currently in progress" : "No closed investment experiences yet")}
      detail={t(hasInvestments ? "Change the filter to see other investments." : "Import executions to reconstruct complete investment experiences.")} />
      {hasInvestments ? <Button className="mt-3" variant="quiet" onClick={() => {setFilter("all"); setQuery("");}}>{t("All investments")}</Button> : <Button asChild className="mt-3"><Link to="/data">{t("Import data")}</Link></Button>}
    </div> : null}
  </div>;
}
