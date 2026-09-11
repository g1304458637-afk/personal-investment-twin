import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { reviewService, reviewSessions, type SharedEpisode } from "@/data/reviewService";
import { selfHistoryRows, ReviewRequestGuard, type ReviewScope } from "@/data/decisionReview";
import { answerCopy } from "@/data/reviewAnswer";
import { ReviewAnswer } from "./ReviewAnswer";
import { adaptSameStock } from "@/data/sameStock";
import { SameStockComparisonPanel } from "./SameStockComparisonPanel";
import { useLocale } from "@/locales/LocaleProvider";

const inputClass = "w-full rounded-md border border-border bg-background/70 px-3 py-2 text-sm";

function Sharing({ scope, onChoose, onChange }: { scope: ReviewScope; onChoose: (id: string) => void; onChange: () => void }) {
  const { t } = useLocale();
  const [shares, setShares] = useState<SharedEpisode[]>([]), [error, setError] = useState<string | null>(null);
  const [fingerprint, setFingerprint] = useState(""), [exportedFingerprint, setExportedFingerprint] = useState("");
  const [recipient, setRecipient] = useState(""), [account, setAccount] = useState(""), [expiry, setExpiry] = useState("");
  const [consent, setConsent] = useState(false), [agentConsent, setAgentConsent] = useState(false), [busy, setBusy] = useState(false);
  const refresh = () => reviewService.shares(scope).then((r) => setShares(r.shares));
  useEffect(() => { let current = true; void reviewService.shares(scope).then((r) => { if (current) setShares(r.shares); }).catch((e: Error) => { if (current) setError(e.message); }); return () => { current = false; }; }, [scope]);
  async function act(run: () => Promise<unknown>) { setBusy(true); setError(null); try { await run(); await refresh(); onChange(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } }
  return <div className="space-y-4 text-sm">
    <Button size="sm" variant="quiet" onClick={() => onChoose("")}>{t("Clear comparison and review only my records")}</Button>
    <p className="text-muted">{t("Only a voluntarily shared Episode is eligible. A local account is not permission to inspect another person.")}</p>
    <p className="text-xs text-warning">{t("A signed share contains derived decisions and results, not raw CSV. Confirm the sender key fingerprint separately; signatures do not certify identity or independent replay.")}</p>
    <p className="break-all text-xs text-muted">{t("Your receiving scope")}: {scope.subject_id} / {scope.account_id}</p>
    <div className="space-y-2">{shares.map((s) => <div className="flex flex-wrap items-center gap-3 border-b border-border py-2" key={s.share_id}><Button size="sm" variant="quiet" disabled={busy} onClick={() => onChoose(s.share_id)}>{s.instrument.local_symbol} · {s.subject_id}</Button><span className="text-xs text-muted">{t(s.allow_agent_review ? "Model review permitted" : "Local comparison only")} · {s.expires_at}</span><Button size="sm" variant="quiet" disabled={busy} onClick={() => void act(() => reviewService.revoke(scope, s.share_id))}>{t("Revoke local access")}</Button></div>)}</div>
    <label className="block space-y-2"><span>{t("Sender fingerprint confirmed through a separate channel")}</span><input className={inputClass} type="password" autoComplete="off" value={fingerprint} onChange={(e) => setFingerprint(e.target.value)} /></label>
    <Button size="sm" disabled={busy || !fingerprint} onClick={() => void act(async () => { const r = await reviewService.importShare(scope, fingerprint); setFingerprint(""); if (r) onChoose(r.share_id); })}>{t("Import Episode share")}</Button>
    <details className="border-t border-border pt-3"><summary className="cursor-pointer">{t("Share only this investment")}</summary><div className="mt-3 space-y-3">
      <label className="block">{t("Recipient subject ID")}<input className={inputClass} value={recipient} onChange={(e) => setRecipient(e.target.value)} /></label>
      <label className="block">{t("Recipient account ID")}<input className={inputClass} value={account} onChange={(e) => setAccount(e.target.value)} /></label>
      <label className="block">{t("Access expires at (local time)")}<input type="datetime-local" className={inputClass} value={expiry} onChange={(e) => setExpiry(e.target.value)} /></label>
      <label className="flex gap-2"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />{t("I explicitly authorize this recipient to compare this Episode's derived facts.")}</label>
      <label className="flex gap-2"><input type="checkbox" checked={agentConsent} onChange={(e) => setAgentConsent(e.target.checked)} />{t("Also allow these derived facts to be sent to the configured review model. No cohort consent.")}</label>
      <Button size="sm" disabled={busy || !consent || !recipient || !account || !expiry} onClick={() => void act(async () => { const r = await reviewService.exportShare(scope, recipient, account, new Date(expiry).toISOString(), agentConsent); if (r) setExportedFingerprint(r.signer_fingerprint); })}>{t("Export limited Episode share")}</Button>
      {exportedFingerprint ? <label className="block space-y-2 text-xs text-warning">{t("Have the recipient confirm this public-key fingerprint through a separate trusted channel. The private signing key is never exported.")}<input type="password" readOnly className={inputClass} value={exportedFingerprint} aria-label={t("Sender public-key fingerprint")} onFocus={(e) => e.target.select()} /></label> : null}
    </div></details>
    <p className="text-xs text-muted">{t("Revocation here blocks local reuse. Offline exports already received elsewhere cannot be remotely revoked; expiry limits future checks.")}</p>
    {error ? <p role="alert" className="text-warning">{t(error)}</p> : null}
  </div>;
}

export function DecisionAnalysisWorkspace({ scope: inputScope, onDecision: navigateDecision, initialMode = null }: { scope: ReviewScope; onDecision?: (id: string) => void; initialMode?: "analysis" | null }) {
  const { t, formatNumber, locale } = useLocale();
  const copy = answerCopy[locale === "zh-CN" ? "zh" : "en"];
  const key = JSON.stringify(inputScope), base = useMemo<ReviewScope>(() => JSON.parse(key), [key]);
  const [mode, setMode] = useState<"analysis" | "compare" | "self" | null>(initialMode), [shareId, setShareId] = useState<string | undefined>();
  const scope = useMemo(() => ({ ...base, ...(shareId ? { share_id: shareId } : {}) }), [base, shareId]);
  const supportsConversation = !scope.share_id && !scope.compare_pair
    && (!scope.data_mode || scope.data_mode === "real_user" || scope.data_mode === "synthetic_showcase");
  const session = useSyncExternalStore(
    useCallback(listener => reviewSessions.subscribe(scope, listener), [scope]),
    useCallback(() => reviewSessions.snapshot(scope), [scope]),
  );
  const { context, answer, question, note, noteKind, loading, revision } = session;
  const [consent, setConsent] = useState(false), [saving, setSaving] = useState(false), [noteError, setNoteError] = useState<string | null>(null);
  const busy = saving || session.busy, error = noteError ?? session.error;
  const guard = useRef(new ReviewRequestGuard());
  const live = reviewService.available();
  // Agent Evidence stays canonical.  A display-scoped showcase page may resolve
  // its canonical decision ids, while a canonical same-stock scope must retain
  // those ids exactly (and never borrow another episode's display mapping).
  const onDecision = navigateDecision ? (id: string) => {
    const mapping = context?.identity_mapping;
    if (base.data_mode === "synthetic_showcase") {
      if (!mapping) return;
      if (base.episode_id === mapping.canonical_episode_id) {
        navigateDecision(id);
        return;
      }
      if (mapping?.display_episode_id !== base.episode_id) return;
      const displayId = mapping.decision_display_ids[id];
      if (displayId) navigateDecision(displayId);
    } else if (base.data_mode === "synthetic_episode") {
      if (mapping?.display_episode_id !== base.episode_id) return;
      const displayId = mapping.decision_display_ids[id];
      if (displayId) navigateDecision(displayId);
    } else navigateDecision(id);
  } : undefined;
  useEffect(() => { setShareId(undefined); setConsent(false); setNoteError(null); }, [base]);
  useEffect(() => {
    if (!live || !mode) return;
    // Unmounting removes the listener, not the app-scoped read or analysis job.
    void reviewSessions.load(scope).catch(() => { /* Shared state displays failures. */ });
  }, [scope, revision, live, mode]);
  useEffect(() => () => { guard.current.next(); }, [scope]);
  const compare = useMemo(() => context?.comparison ? adaptSameStock(context.comparison) : null, [context]);
  async function analyze() {
    if (!live || !consent || !context || busy || loading) return;
    setNoteError(null);
    await reviewSessions.analyze(scope, question || copy.question, consent);
  }
  async function saveNote() {
    const ticket = guard.current.next(); setSaving(true); setNoteError(null);
    try { await reviewService.note(scope, note, noteKind); reviewSessions.edit(scope, {note:""}); }
    catch (e) { if (guard.current.accepts(ticket)) setNoteError(e instanceof Error ? e.message : String(e)); }
    finally { if (guard.current.accepts(ticket)) setSaving(false); }
  }
  return <section className="mt-6 border-y border-border py-4" data-decision-analysis>
    <div className="flex flex-wrap gap-2">
      {supportsConversation ? (live
        ? <Button asChild size="sm" variant="primary"><Link to={`/ask?episode=${encodeURIComponent(base.episode_id)}`}>{t("Analyze this investment")}</Link></Button>
        : <Button size="sm" disabled variant="primary">{t("Analyze this investment")}</Button>)
        : <Button size="sm" disabled={!live} variant="primary" aria-pressed={mode === "analysis"} onClick={() => setMode(mode === "analysis" ? null : "analysis")}>{t("Analyze this investment")}</Button>}
      {(["compare", "self"] as const).map((m) => <Button key={m} size="sm" disabled={!live} variant="quiet" aria-pressed={mode === m} onClick={() => setMode(mode === m ? null : m)}>{t({ compare: "Compare same stock", self: "Against my own past" }[m])}</Button>)}
      {supportsConversation ? <Button size="sm" disabled={!live} variant="quiet" aria-pressed={mode === "analysis"} onClick={() => setMode(mode === "analysis" ? null : "analysis")}>{locale === "zh-CN" ? "笔记与历史" : "Notes & history"}</Button> : null}
    </div>
    {!live ? <div className="review-offline"><p className="text-sm text-muted">{t("Browser · Offline Runtime. The chart is a deterministic example; live review and sharing require the desktop app. No model has been called.")}</p>{!supportsConversation ? <><label className="block mt-4 text-sm">{t("Continue with a question")}<textarea className={inputClass} disabled placeholder={t("What happened in this investment, and what remains uncertain?")} /></label><Button className="mt-3" disabled>{t("Analyze this investment")}</Button></> : null}</div> : null}
    {mode && live ? <div className="mt-5 space-y-5">
      {loading ? <p role="status" className="text-sm text-muted">{locale === "zh-CN" ? "正在准备这轮投资的分析资料，切换页面后仍会继续…" : "Preparing this investment’s analysis; preparation continues while you browse…"}</p> : null}
      {!loading && context ? <p className="text-xs text-muted">{locale === "zh-CN" ? "分析资料已就绪 · 切换页面可继续查看，数据更新后自动刷新" : "Analysis ready · retained across pages and refreshed when records change"}</p> : null}
      {error && !context && !loading ? <Button size="sm" variant="quiet" onClick={() => void reviewSessions.prefetch(scope)}>{locale === "zh-CN" ? "重新准备" : "Retry preparation"}</Button> : null}
      {error ? <p role="alert" className="break-words text-sm text-warning">{t(error)}{["model_not_configured", "model_keychain_unavailable", "model_configuration_failed"].includes(error) && <a href="#/settings" className="ml-3 underline">{t("Configure model service")}</a>}</p> : null}
      {context?.data_tier === "synthetic" ? <p className="text-xs text-warning">{t("Example account · Synthetic")}</p> : null}
      {mode === "compare" ? <>
        {(!base.data_mode || base.data_mode === "real_user") ? <Sharing scope={base} onChoose={setShareId} onChange={() => reviewSessions.invalidate(base.subject_id, base.account_id)} /> : null}
        {compare ? <SameStockComparisonPanel view={compare} /> : <p className="text-sm text-muted">{t("Choose a permitted Episode of the same qualified instrument. No automatic account matching.")}</p>}
      </> : null}
      {mode === "self" ? <>
        <h2 className="text-base">{t("Against my own past")}</h2>
        {context?.records.filter((r) => r.kind === "self_history").map((f) => <div key={f.ref}>{selfHistoryRows(f).map((r) => <div key={r.metric} className="border-b border-border py-3 text-sm"><p>{t(r.metric)}</p><p className="mt-2 font-mono">{t("Current")}: {r.current === null ? "—" : formatNumber(r.current, 4)} · {t("Historical median")}: {r.median === null ? "—" : formatNumber(r.median, 4)}</p><p className="mt-1 text-xs text-muted">N={r.n ?? "—"} · {r.start ?? "—"} → {r.end ?? "—"}</p>{r.status !== "complete" ? <p className="mt-2 text-xs text-warning">{t("Insufficient self-history")} · {t(r.reason ?? "")}</p> : null}</div>)}</div>)}
        <p className="text-xs text-muted">{t("Only HHI and mean daily turnover have registered self-history. Repeated chasing or long-term ability cannot be inferred here.")}</p>
      </> : null}
      {mode === "analysis" && context ? <>
        <h2 className="text-base">{copy.title}</h2>
        {!answer ? <p className="max-w-3xl text-sm leading-7 text-muted">{copy.empty}</p>
          : answer.answer ? <ReviewAnswer answer={answer} context={context} onDecision={onDecision} />
          : <div className="space-y-3"><p className="text-xs text-muted">{copy.legacy}</p>{answer.possible_explanations.filter(h => h.kind !== "unknown").map((h, i) => <p key={i} className="text-sm leading-7">{t(h.claim)}</p>)}</div>}
        {supportsConversation ? <p className="text-xs text-muted">{locale === "zh-CN" ? "要继续连续对话，请使用上方“分析这轮”。" : "Use “Analyze this investment” above to continue the conversation."}</p> : <>
          <label className="block space-y-2 text-sm"><span>{t("Continue with a question")}</span><textarea className={inputClass} maxLength={2000} value={question} disabled={busy} placeholder={copy.question} onChange={(e) => reviewSessions.edit(scope, {question:e.target.value})} /></label>
          <label className="flex gap-2 text-xs text-muted"><input type="checkbox" checked={consent} disabled={busy} onChange={(e) => setConsent(e.target.checked)} />{t("Send these scoped derived facts and my notes to the configured review model. It cannot place trades.")}</label>
          <Button disabled={busy || loading || !consent} onClick={() => void analyze()}>{t(busy ? "Reviewing facts and counterexamples…" : "Ask for an evidence-grounded review")}</Button>
        </>}
        <details className="border-t border-border pt-3"><summary className="cursor-pointer text-sm">{t("Add a reason or original plan (retrospective)")}</summary><div className="mt-3 space-y-3"><p className="text-xs text-muted">{t("This is recorded now, not proof that the information existed before the trade. New notes invalidate earlier interpretations.")}</p><select aria-label={t("Note type")} className={inputClass} value={noteKind} disabled={busy} onChange={(e) => reviewSessions.edit(scope, {noteKind:e.target.value})}><option value="reason">{t("My recalled reason")}</option><option value="plan">{t("My recalled staged plan")}</option></select><textarea aria-label={t("Retrospective user note")} className={inputClass} maxLength={4000} value={note} disabled={busy} onChange={(e) => reviewSessions.edit(scope, {note:e.target.value})} /><Button size="sm" disabled={busy || !note.trim()} onClick={() => void saveNote()}>{t("Save retrospective note")}</Button></div></details>
        <details className="text-xs text-muted"><summary>{t("Previous interpretations (revisable)")}</summary>{context.inferences.map((r) => <p key={r.inference_id} className="mt-2">{r.generated_at} · {t(r.invalidated ? "Invalidated by newer information" : "Previous interpretation, not financial evidence")}</p>)}</details>
      </> : null}
    </div> : null}
  </section>;
}
