
import { Search, ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StateNotice } from "@/components/common/StateNotice";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { showcaseInstrumentName } from "@/data/showcaseDemo";
import { adaptDemoInvestmentsCatalog, archiveRows } from "@/data/investments";
import { belongsToExample, exampleAccountLabel } from "@/data/accountContext";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi, type RuntimeInvestments } from "@/data/runtimeService";
import { formatCurrencyValue } from "@/lib/format";
import { useLocale } from "@/locales/LocaleProvider";

import "./episode-workspace.css";
import { AccountReviewPackPanel } from "@/pages/AccountReviewPack";
import { useLiquidCopy } from "@/workspace/liquidCopy";

function InvestmentRow({ episode }: { episode: import("@/data/investments").InvestmentEpisodeRowView }) {
  const { locale, t, formatPercent } = useLocale();
  const c = useLiquidCopy();
  const displayName = episode.isSynthetic
    ? showcaseInstrumentName(episode.instrumentId, locale, episode.displayName)
    : t(episode.displayName);
  const date = (value: string) => new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  const outcome = episode.outcome;
  const pnl = outcome.pnl;
  const resultAvailable = outcome.availability === "available" && pnl !== null;
  return <Link className="iw-investment-row lg-interactive" to={`/investments/episodes/${episode.episodeId}`}>
    <div><strong className="iw-row-name">{displayName}</strong><span className="iw-row-meta">{episode.instrumentId} · {t("One investment experience")}</span></div>
    <div><span className="iw-status" data-open={episode.status === "open" || undefined}>{t(episode.status === "open" ? "Holding" : "Closed")}</span><span className="iw-row-meta">{date(episode.openedAt)} → {episode.closedAt ? date(episode.closedAt) : t("Present")}</span></div>
    <div className="iw-result">{resultAvailable && pnl !== null ? <><strong className={`iw-result-value ${pnl < 0 ? "text-negative" : pnl > 0 ? "text-positive" : "text-foreground"}`}>{formatCurrencyValue(pnl, locale, episode.currency)}</strong><p className="iw-result-label">{t(outcome.result_kind === "marked" ? "Current marked result" : "Final realized result")}{outcome.return_value !== null ? ` · ${formatPercent(outcome.return_value, 2)}` : ""}</p></> : <><strong className="text-sm text-foreground">{t("Result unavailable")}</strong><p className="iw-result-label">{t(outcome.reason ?? "No authoritative result is available.")}</p></>}</div>
    <span className="lg-investment-action">{c.cardAction}<ArrowUpRight className="size-4" aria-hidden="true" /></span>
  </Link>;
}

export function InvestmentsPage() {
  const { locale, t } = useLocale();
  const data = useDataMode();
  const glass = useLiquidCopy();
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
  if (data.mode === "real_user" && !data.activeAccount) return <div className="page iw-investments iw-investments--empty">
    <header className="iw-investments-head"><div><p className="iw-kicker">{t("Investment intelligence")}</p><h1 className="iw-investments-title">{glass.emptyTitle}</h1><p className="iw-subtle mt-3 max-w-xl">{glass.emptyDetail}</p></div></header>
    <section className="iw-onboarding iw-inset"><div><p className="iw-kicker">{t("Account required")}</p><h2>{t("Open your investment workspace")}</h2><p className="iw-subtle mt-2">{t("An account context is required before authoritative investment experiences can be shown.")}</p></div><div className="iw-onboarding-actions"><div><span>01</span><strong>{t("Import recorded executions")}</strong><p>{t("Create a local account context from your own files, then review each complete investment path.")}</p><Button asChild variant="primary"><Link to="/data">{t("Import data")}</Link></Button></div><div><span>02</span><strong>{t("Explore a synthetic preview")}</strong><p>{t("Preview data is clearly labelled, stays separate from your account, and never writes to your records.")}</p><Button variant="quiet" onClick={() => data.setMode("demo")}>{t("View example account")}</Button></div></div></section>
    {data.accountsLoading || data.accountError ? <div className="mt-4"><StateNotice compact state={data.accountError ? "error" : "loading"} title={t(data.accountError ? "Could not read local accounts" : "Opening local accounts…")} detail={data.accountError ?? t("Checking the local account directory.")} /></div> : null}
  </div>;
  if (data.mode === "real_user" && !runtime) return <div className="page"><StateNotice state={runtimeError ? "disconnected" : "loading"} title={runtimeError ? t("Portfolio state is unavailable") : t("Opening investment workspace…")} detail={runtimeError ?? t("Rebuilding from local canonical facts.")} /></div>;
  const date = (value: string) => Number.isNaN(Date.parse(value)) ? "—" : new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  const rows = archiveRows([...view.openEpisodes, ...view.closedEpisodes], filter, query);
  const hasInvestments = view.openEpisodes.length > 0 || view.closedEpisodes.length > 0;
  const accountName = data.mode === "demo" ? exampleAccountLabel(data.exampleAccount, locale) : data.activeAccount?.display_name ?? t("Selected account");
  return <div className="page iw-investments">
    <header className="iw-investments-head"><div><p className="iw-kicker">{t("Investment intelligence")}</p><h1 className="iw-investments-title">{t("My Investments")}</h1><p className="iw-subtle mt-3 max-w-2xl">{t("Every entry is one complete investment experience reconstructed from recorded executions — including later re-entries in the same security.")}</p></div><div className="iw-context"><span><strong>{accountName}</strong></span><span>{t("Data as of {date}", {date: date(view.asOf)})}</span><span>{view.dataTier === "synthetic" ? t("Synthetic preview") : t("Authorized account")}</span></div></header>
    {view.portfolioState.status !== "available" ? <StateNotice state="insufficient" title={t("Portfolio state is unavailable")} detail={t(view.portfolioState.reason ?? "The current position state cannot be shown from the available facts.")} /> : null}
    <dl className="iw-account-deck iw-inset"><div><dt>{t("Account context")}</dt><dd className="iw-account-name">{accountName}</dd><p className="iw-account-note">{t("Results remain authoritative only where an Outcome record is available.")}</p></div><div><dt>{t("Currently holding")}</dt><dd>{view.summary.openEpisodeCount}</dd><p className="iw-account-note">{t("Open investment experiences")}</p></div><div><dt>{t("Current positions")}</dt><dd>{view.summary.currentPositionCount}</dd><p className="iw-account-note">{t("Available portfolio projection")}</p></div><div><dt>{t("Completed")}</dt><dd>{view.summary.closedEpisodeCount}</dd><p className="iw-account-note">{t("Closed investment experiences")}</p></div></dl>
    <div className="iw-listbar"><div><div className="iw-filter" role="group" aria-label={t("Investment status")}>{(["open", "closed", "all"] as const).map((value) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{t({open: "Holding", closed: "Closed", all: "All investments"}[value])}</button>)}</div><p className="iw-subtle mt-2">{t("Newest start date first · select an investment to review its path")}</p></div><label className="iw-search"><Search className="size-3.5" aria-hidden="true" /><input aria-label={t("Search securities")} placeholder={t("Search securities")} value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
    <section className="iw-episode-list" aria-label={t("Investment experiences")}>{rows.map((episode) => <InvestmentRow key={episode.episodeId} episode={episode} />)}</section>
    {!rows.length && view.portfolioState.status === "available" ? <div className="mt-5"><StateNotice compact state="empty"
      title={t(!hasInvestments ? "No investment records yet" : query ? "No matching investments" : filter === "open" ? "No investment experiences are currently in progress" : "No closed investment experiences yet")}
      detail={t(hasInvestments ? "Change the filter to see other investments." : "Import executions to reconstruct complete investment experiences.")} />
      {hasInvestments ? <Button className="mt-3" variant="quiet" onClick={() => {setFilter("all"); setQuery("");}}>{t("All investments")}</Button> : <Button asChild className="mt-3"><Link to="/data">{t("Import data")}</Link></Button>}
    </div> : null}
    <AccountReviewPackPanel />
  </div>;
}
