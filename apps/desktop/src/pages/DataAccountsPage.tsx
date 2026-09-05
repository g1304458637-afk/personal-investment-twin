import { AlertTriangle, Database, FileUp, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDataMode } from "@/data/DataModeProvider";
import { pickCsv, realUserApi, type MarketPreview, type RuntimeDataStatus, type TradePreview } from "@/data/runtimeService";
import { useLocale } from "@/locales/LocaleProvider";

import { canConfirmImport, confirmedImportRequest } from "@/data/importConfirmation";

type Kind = "trade" | "market";

const summaryLabels: Record<string, string> = {
  accepted_canonical_facts: "Ready to import", new_executions: "New executions", instrument_resolutions: "Instrument resolutions",
  blocking_rows: "Blocked rows", conflicts: "Conflicts", exact_duplicates: "Exact duplicates",
  possible_duplicates: "Possible duplicates", fee_issue_count: "Fee warnings",
  instrument_issue_count: "Instrument issues", total_observations: "Price observations",
  new_observations: "New prices", existing_observations: "Existing prices",
  duplicate_rows: "Duplicate rows", invalid_rows: "Invalid rows",
};

const statusLabels: Record<string, string> = {
  instrument_resolution: "Instrument resolution", new_execution: "New execution", possible_duplicate: "Possible duplicate", exact_duplicate: "Exact duplicate",
  invalid: "Cannot import", conflict: "Conflict", new_observation: "New price",
  existing_observation: "Already imported", complete: "Complete", missing: "Missing",
  partial: "Partial", available: "Ready for review", waiting_for_market_data: "Waiting for market data",
  replay_ineligible: "Replay unavailable", no_trades: "No transactions",
};

export function DataAccountsPage() {
  const { t, formatNumber } = useLocale();
  const data = useDataMode();
  const [kind, setKind] = useState<Kind>("trade");
  const [subjectId, setSubjectId] = useState("local-user");
  const [accountId, setAccountId] = useState("main-account");
  const [displayName, setDisplayName] = useState("我的投资账户");
  const [initialCash, setInitialCash] = useState("100000");
  const [timezone, setTimezone] = useState("Asia/Shanghai");
  const [resolutionSymbol, setResolutionSymbol] = useState("");
  const [resolutionMarket, setResolutionMarket] = useState("");
  const [resolutionType, setResolutionType] = useState("equity");
  const [sourceId, setSourceId] = useState("user_price_csv");
  const [sourceVersion, setSourceVersion] = useState("v1");
  const [file, setFile] = useState<{ path: string; filename: string } | null>(null);
  const [confirmation, setConfirmation] = useState<{ key: string; configuration: Record<string, unknown>; preview: TradePreview | MarketPreview } | null>(null);
  const pending = useRef(false);
  const requestGeneration = useRef(0);
  const currentKey = useRef("");
  const setPreview = (_: null) => setConfirmation(null);
  const [duplicateChoices, setDuplicateChoices] = useState<Record<string, "keep" | "skip">>({});
  const [status, setStatus] = useState<RuntimeDataStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = data.activeAccount;
  useEffect(() => {
    let cancelled = false;
    setStatus(null);
    if (!active) return;
    void realUserApi.status(active.subject_id, active.account_id)
      .then((value) => { if (!cancelled) setStatus(value); })
      .catch((value) => { if (!cancelled) setError(String(value)); });
    return () => { cancelled = true; };
  }, [active]);
  const params = () => ({ file_path: file?.path, subject_id: subjectId, account_id: accountId,
    display_name: displayName, initial_cash: Number(initialCash), source_timezone: timezone,
    use_source_row_order_as_sequence: true, source_id: sourceId, source_version: sourceVersion,
    resolution_symbol: resolutionSymbol, resolution_market: resolutionMarket, resolution_security_type: resolutionType });
  const configurationKey = JSON.stringify([kind, params()]);
  currentKey.current = configurationKey;
  const preview = confirmation?.key === configurationKey ? confirmation.preview : null;
  useEffect(() => () => { requestGeneration.current += 1; }, []);
  const choose = async () => {
    if (pending.current) return;
    try { const selected = await pickCsv(); if (selected) { setFile(selected); setPreview(null); setError(null); } }
    catch (value) { setError(String(value)); }
  };
  const runPreview = async () => {
    if (!file || pending.current) return;
    const configuration = params(), key = configurationKey, generation = ++requestGeneration.current;
    pending.current = true; setBusy(true); setError(null); setPreview(null);
    try {
      const result = kind === "trade" ? await realUserApi.previewTrades(configuration) : await realUserApi.previewPrices(configuration);
      if (generation === requestGeneration.current && key === currentKey.current) {
        setConfirmation({ key, configuration, preview: result }); setDuplicateChoices({});
      }
    } catch (value) { if (generation === requestGeneration.current && key === currentKey.current) setError(String(value)); }
    finally { pending.current = false; if (generation === requestGeneration.current) setBusy(false); }
  };
  const commit = async () => {
    if (!preview || !confirmation || pending.current || !canConfirmImport(preview, duplicateChoices)) return;
    pending.current = true; setBusy(true); setError(null);
    try {
      const request = confirmedImportRequest(confirmation.configuration, preview, duplicateChoices);
      if (kind === "trade") await realUserApi.commitTrades(request);
      else await realUserApi.commitPrices(request);
      await data.refresh(); data.setMode("real_user"); setPreview(null); setFile(null);
    } catch (value) { setError(value instanceof Error ? value.message : String(value)); }
    finally { pending.current = false; setBusy(false); }
  };
  const remove = async () => {
    if (!active || pending.current || !window.confirm(t("Delete this local account and all of its imported facts?"))) return;
    pending.current = true; setBusy(true); setError(null);
    try { await realUserApi.deleteAccount(active.subject_id, active.account_id); await data.refresh(); setStatus(null); }
    catch (value) { setError(String(value)); }
    finally { pending.current = false; setBusy(false); }
  };
  if (!data.runtimeAvailable) return <div className="page"><PageHeader eyebrow={t("Local data")} title={t("Data & Accounts")} description={t("Import canonical transactions and historical prices into the local deterministic runtime.")} /><StateNotice state="insufficient" title={t("Desktop runtime required")} detail={t("Browser preview remains Synthetic Demo and cannot import local financial files.")} /></div>;
  const summary = preview?.summary ?? {};
  return <div className="page space-y-6 pb-8">
    <PageHeader eyebrow={t("Local-first · private by default")} title={t("Data & Accounts")} description={t("Preview first. Only canonical facts, hashes, and audit metadata are saved; raw CSV files are not retained.")} actions={<div className="flex gap-2"><Button variant={data.mode === "demo" ? "primary" : "quiet"} onClick={() => data.setMode("demo")}>{t("Demo")}</Button><Button variant={data.mode === "real_user" ? "primary" : "quiet"} disabled={!data.accounts.length} onClick={() => data.setMode("real_user")}>{t("My data")}</Button></div>} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <GlassPanel className="p-5 md:p-6"><SectionHeading eyebrow={t("Import workflow")} title={t(kind === "trade" ? "Import transaction CSV" : "Import historical price CSV")} description={t("Select a local CSV, inspect the deterministic preview, then explicitly confirm.")} />
        <fieldset disabled={busy} className="contents"><div className="mt-5 flex gap-2"><Button variant={kind === "trade" ? "primary" : "quiet"} onClick={() => { setKind("trade"); setPreview(null); }}>{t("Transactions")}</Button><Button variant={kind === "market" ? "primary" : "quiet"} onClick={() => { setKind("market"); setPreview(null); }}>{t("Historical prices")}</Button></div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2"><Input value={subjectId} onChange={(e) => setSubjectId(e.target.value)} placeholder="Subject ID" /><Input value={accountId} onChange={(e) => setAccountId(e.target.value)} placeholder="Account ID" />{kind === "trade" ? <><Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={t("Account name")} /><Input value={initialCash} onChange={(e) => setInitialCash(e.target.value)} inputMode="decimal" placeholder={t("Initial cash")} /><Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="IANA timezone" /><Input value={resolutionSymbol} onChange={(e) => setResolutionSymbol(e.target.value)} placeholder={t("Unresolved symbol (optional)")} /><Input value={resolutionMarket} onChange={(e) => setResolutionMarket(e.target.value)} placeholder={t("Confirmed market (optional)")} /><Input value={resolutionType} onChange={(e) => setResolutionType(e.target.value)} placeholder={t("Security type")} /></> : <><Input value={sourceId} onChange={(e) => setSourceId(e.target.value)} placeholder="Source ID" /><Input value={sourceVersion} onChange={(e) => setSourceVersion(e.target.value)} placeholder="Source version" /></>}</div>
        <div className="mt-5 flex flex-wrap items-center gap-3"><Button onClick={choose} variant="quiet"><FileUp />{t("Choose CSV")}</Button><span className="text-sm text-muted">{file?.filename ?? t("No file selected")}</span><Button disabled={!file || busy} onClick={runPreview}>{busy ? t("Loading…") : t("Preview import")}</Button></div>
        </fieldset>{error ? <div className="mt-4 flex gap-2 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger"><AlertTriangle className="size-4 shrink-0" />{error}</div> : null}
        {preview ? <div className="mt-6"><dl className="product-fact-strip">{Object.entries(summary).filter(([, value]) => value !== 0).map(([key, value]) => <div key={key}><dt>{t(summaryLabels[key] ?? key)}</dt><dd>{formatNumber(value)}</dd></div>)}</dl><div className="mt-4 max-h-64 overflow-auto border-y border-border/70"><table className="w-full text-left text-xs"><thead className="text-muted"><tr><th className="py-3">{t("Row")}</th><th>{t("Status")}</th><th>{t("Confirmed facts")}</th><th>{t("Issues")}</th><th>{t("Resolution")}</th></tr></thead><tbody>{preview.rows.map((row) => { const key = "row_ref" in row ? row.row_ref : String(row.row_number); return <tr key={key} className="border-t border-border/50"><td className="py-3 font-mono">{key.split(":").at(-1)}</td><td>{t(statusLabels[row.status] ?? row.status)}</td><td className="max-w-80 whitespace-normal break-words p-2 font-mono">{row.candidate ? ("row_ref" in row ? [
      row.candidate.event_time, row.candidate.instrument_id ?? "unresolved", row.candidate.side,
      row.candidate.executed_quantity, row.candidate.executed_price,
      row.candidate.fee_status, row.candidate.fee_amount ?? "—",
    ].map(String).join(" · ") : [row.candidate.date, row.candidate.symbol, row.candidate.close, row.candidate.price_type].join(" · ")) : "—"}</td><td>{row.issues.map((x) => t(x.code)).join(", ") || "—"}</td><td>{row.status === "possible_duplicate" && "row_ref" in row ? <span className="flex gap-1"><Button size="sm" variant={duplicateChoices[row.row_ref] === "keep" ? "primary" : "quiet"} onClick={() => setDuplicateChoices((old) => ({ ...old, [row.row_ref]: "keep" }))}>{t("Keep as another execution")}</Button><Button size="sm" variant={duplicateChoices[row.row_ref] === "skip" ? "primary" : "quiet"} onClick={() => setDuplicateChoices((old) => ({ ...old, [row.row_ref]: "skip" }))}>{t("Skip as duplicate")}</Button></span> : "—"}</td></tr>; })}</tbody></table></div><Button className="mt-4" disabled={busy || !canConfirmImport(preview, duplicateChoices)} onClick={commit}>{t("Confirm import")}</Button></div> : null}
      </GlassPanel>
      <div className="space-y-4"><GlassPanel className="p-5"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold"><Database className="size-4 text-accent" />{t("Local accounts")}</div><Button size="icon" variant="ghost" disabled={busy} onClick={() => { void data.refresh().catch((value) => setError(String(value))); }}><RefreshCw /></Button></div>{data.accounts.length ? <div className="mt-4 space-y-2">{data.accounts.map((account) => <button key={`${account.subject_id}:${account.account_id}`} className="w-full rounded-lg border border-border/70 p-3 text-left text-sm" onClick={() => data.setActiveAccount(account)}><strong>{account.display_name}</strong><span className="mt-1 block font-mono text-[10px] text-muted">{account.account_id}</span></button>)}</div> : <p className="mt-4 text-sm text-muted">{t("No real account imported yet.")}</p>}</GlassPanel>
        {active && status ? <GlassPanel className="p-5"><SectionHeading eyebrow={t("Data status")} title={active.display_name} /><dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between"><dt>{t("Transactions")}</dt><dd>{status.execution_count}</dd></div><div className="flex justify-between"><dt>{t("Fees")}</dt><dd>{t(statusLabels[status.fee_status] ?? status.fee_status)}</dd></div><div className="flex justify-between"><dt>{t("Market prices")}</dt><dd>{t(statusLabels[status.market_data.status] ?? status.market_data.status)}</dd></div><div className="flex justify-between"><dt>{t("Review status")}</dt><dd>{t(statusLabels[status.review_status] ?? status.review_status)}</dd></div><div className="flex justify-between"><dt>{t("Last trade import")}</dt><dd>{status.last_trade_import?.slice(0, 10) ?? "—"}</dd></div><div className="flex justify-between"><dt>{t("Last market import")}</dt><dd>{status.last_market_import?.slice(0, 10) ?? "—"}</dd></div><div className="flex justify-between"><dt>{t("Market prices through")}</dt><dd>{status.latest_market_date ?? "—"}</dd></div></dl><div className="mt-5 border-t border-border/70 pt-4"><p className="text-xs font-medium">{t("Recent imports")}</p>{status.import_history.slice(0, 4).map((batch) => <p key={batch.batch_id} className="mt-2 text-xs text-muted">{batch.filename} · {batch.imported_at.slice(0, 10)}</p>)}</div><Button variant="quiet" className="mt-5 text-danger" onClick={remove}><Trash2 />{t("Delete local account")}</Button></GlassPanel> : null}
      </div>
    </div>
  </div>;
}
