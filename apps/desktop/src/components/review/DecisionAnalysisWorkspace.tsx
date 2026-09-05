import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { reviewService, type SharedEpisode } from "@/data/reviewService";
import { object, reviewRows, selfHistoryRows, ReviewRequestGuard, type ReviewContextView, type ReviewFact, type ReviewInference, type ReviewScope } from "@/data/decisionReview";
import { adaptSameStock } from "@/data/sameStock";
import { SameStockComparisonPanel } from "./SameStockComparisonPanel";
import { useLocale } from "@/locales/LocaleProvider";

const inputClass = "w-full rounded-md border border-border bg-background/70 px-3 py-2 text-sm";

function Fact({ fact, onDecision, expanded = false }: { fact: ReviewFact; onDecision?: (id: string) => void; expanded?: boolean }) {
  const { t, locale } = useLocale();
  const raw = object(fact.value);
  const title = fact.kind === "decision" ? t(String(raw.event_type)) : fact.kind === "phase" ? t(String(raw.phase_type)) : t(fact.title);
  const when = raw.event_time ?? raw.started_at ?? raw.decision_at;
  const dateLabel = typeof when === "string" ? new Intl.DateTimeFormat(locale, {month:"numeric", day:"numeric"}).format(new Date(when)) : "";
  return <details className="border-b border-border py-3" open={expanded || undefined}>
    <summary className="cursor-pointer text-sm">{title} {dateLabel} · <span className="text-xs text-muted">{fact.subject_id}{fact.availability !== "complete" ? " · " + t(fact.availability) : ""}</span></summary>
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">{reviewRows(fact).map((row) => <div key={row.label} className="min-w-0"><dt className="text-muted">{t(row.label)}</dt><dd className="mt-1 break-words">{row.decisionId && onDecision ? <button className="text-accent" onClick={() => onDecision(row.decisionId!)}>{t(String(row.value))} → {t("View this execution")}</button> : row.value === null ? "—" : typeof row.value === "number" ? new Intl.NumberFormat(locale, row.format === "money" ? { style: "currency", currency: fact.currency } : row.format === "percent" ? { style: "percent", maximumFractionDigits: 2 } : { maximumFractionDigits: 4 }).format(row.value) : t(row.value)}</dd></div>)}</dl>
    {fact.kind === "historical_comparison" ? <p className="mt-3 text-xs text-warning">{t("A fixed historical hypothesis, not what you should have done. Prior daily marks are not intraday prices.")}</p> : null}
    <details className="mt-3 text-xs text-muted"><summary>{t("Method and source details")}</summary><p className="mt-2 break-all font-mono">{fact.method_id}@{fact.method_version} · {fact.ref} · {fact.as_of}</p><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[10px]">{JSON.stringify(fact.value, null, 2)}</pre></details>
  </details>;
}

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

export function DecisionAnalysisWorkspace({ scope: inputScope, onDecision }: { scope: ReviewScope; onDecision?: (id: string) => void }) {
  const { t, formatNumber } = useLocale();
  const key = JSON.stringify(inputScope), base = useMemo<ReviewScope>(() => JSON.parse(key), [key]);
  const [mode, setMode] = useState<"analysis" | "compare" | "self" | null>(null), [shareId, setShareId] = useState<string | undefined>();
  const scope = useMemo(() => ({ ...base, ...(shareId ? { share_id: shareId } : {}) }), [base, shareId]);
  const [context, setContext] = useState<ReviewContextView | null>(null), [answer, setAnswer] = useState<ReviewInference | null>(null);
  const [question, setQuestion] = useState(""), [note, setNote] = useState(""), [noteKind, setNoteKind] = useState("reason");
  const [consent, setConsent] = useState(false), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false), [error, setError] = useState<string | null>(null);
  const [focusedRef, setFocusedRef] = useState<string | null>(null), [revision, setRevision] = useState(0);
  const guard = useRef(new ReviewRequestGuard());
  const live = reviewService.available();
  useEffect(() => { setShareId(undefined); setNote(""); setQuestion(""); setConsent(false); setFocusedRef(null); }, [base]);
  useEffect(() => {
    const ticket = guard.current.next(); setContext(null); setAnswer(null); setError(null); setBusy(false);
    if (!live || !mode) return;
    setLoading(true);
    void reviewService.context(scope).then((c) => { if (guard.current.accepts(ticket)) setContext(c); }).catch((e: Error) => { if (guard.current.accepts(ticket)) setError(e.message); }).finally(() => { if (guard.current.accepts(ticket)) setLoading(false); });
    return () => { guard.current.next(); };
  }, [scope, revision, live, mode]);
  const compare = useMemo(() => context?.comparison ? adaptSameStock(context.comparison) : null, [context]);
  async function analyze() {
    const ticket = guard.current.next(); setBusy(true); setAnswer(null); setError(null);
    try {
      const job = await reviewService.start(scope, question || t("What happened in this investment, and what remains uncertain?"));
      for (let i = 0; i < 110 && guard.current.accepts(ticket); i++) {
        const response = await reviewService.poll(scope, job.job_id);
        if (!guard.current.accepts(ticket)) return;
        if (response.status === "complete") { setAnswer(response.result); return; }
        if (response.status !== "running") throw new Error(response.reason ?? response.status);
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      if (guard.current.accepts(ticket)) throw new Error("review_timeout");
    } catch (e) { if (guard.current.accepts(ticket)) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (guard.current.accepts(ticket)) setBusy(false); }
  }
  async function saveNote() {
    const ticket = guard.current.next(); setAnswer(null); setBusy(true); setError(null);
    try { await reviewService.note(scope, note, noteKind); if (guard.current.accepts(ticket)) { setNote(""); setRevision((r) => r + 1); } }
    catch (e) { if (guard.current.accepts(ticket)) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (guard.current.accepts(ticket)) setBusy(false); }
  }
  const facts = answer?.facts ?? context?.records.filter((r) => r.kind === "episode") ?? [];
  const historical = answer?.historical_comparisons ?? context?.records.filter((r) => r.kind === "historical_comparison") ?? [];
  const focused = context?.records.find((r) => r.ref === focusedRef);
  const link = (ref: string) => { setFocusedRef(ref); const f = context?.records.find((r) => r.ref === ref); const d = object(f?.value).decision_event_id; if (typeof d === "string") onDecision?.(d); };
  return <section className="mt-6 border-y border-border py-4" data-decision-analysis>
    <div className="flex flex-wrap gap-2">{(["analysis", "compare", "self"] as const).map((m) => <Button key={m} size="sm" disabled={!live} variant="quiet" aria-pressed={mode === m} onClick={() => setMode(mode === m ? null : m)}>{t({ analysis: "Analyze this investment", compare: "Compare same stock", self: "Against my own past" }[m])}</Button>)}</div>
    {!live ? <p className="mt-3 text-xs text-warning">{t("Browser · Offline Runtime. The chart is a deterministic example; live review and sharing require the desktop app. No model has been called.")}</p> : null}
    {mode && live ? <div className="mt-5 space-y-5">
      {loading ? <p role="status" className="text-sm text-muted">{t("Reading authorized deterministic facts…")}</p> : null}
      {error ? <p role="alert" className="break-words text-sm text-warning">{t(error)}</p> : null}
      {context?.data_tier === "synthetic" ? <p className="text-xs text-warning">{t("Example account · Synthetic")}</p> : null}
      {mode === "compare" ? <>
        {base.data_mode !== "synthetic_pair" ? <Sharing scope={base} onChoose={setShareId} onChange={() => setRevision((r) => r + 1)} /> : null}
        {compare ? <SameStockComparisonPanel view={compare} /> : <p className="text-sm text-muted">{t("Choose a permitted Episode of the same qualified instrument. No automatic account matching.")}</p>}
      </> : null}
      {mode === "self" ? <>
        <h2 className="text-base">{t("Against my own past")}</h2>
        {context?.records.filter((r) => r.kind === "self_history").map((f) => <div key={f.ref}>{selfHistoryRows(f).map((r) => <div key={r.metric} className="border-b border-border py-3 text-sm"><p>{t(r.metric)}</p><p className="mt-2 font-mono">{t("Current")}: {r.current === null ? "—" : formatNumber(r.current, 4)} · {t("Historical median")}: {r.median === null ? "—" : formatNumber(r.median, 4)}</p><p className="mt-1 text-xs text-muted">N={r.n ?? "—"} · {r.start ?? "—"} → {r.end ?? "—"}</p>{r.status !== "complete" ? <p className="mt-2 text-xs text-warning">{t("Insufficient self-history")} · {t(r.reason ?? "")}</p> : null}</div>)}</div>)}
        <p className="text-xs text-muted">{t("Only HHI and mean daily turnover have registered self-history. Repeated chasing or long-term ability cannot be inferred here.")}</p>
      </> : null}
      {mode === "analysis" && context ? <>
        <h2 className="text-base">{t("What the records establish")}</h2>
        {facts.map((f) => <Fact key={f.ref} fact={f} onDecision={onDecision} />)}
        <details><summary className="cursor-pointer text-sm">{t("Recorded operations and cost changes")}</summary>{context.records.filter((f) => ["decision", "phase"].includes(f.kind)).map((f) => <Fact key={f.ref} fact={f} onDecision={onDecision} />)}</details>
        <details><summary className="cursor-pointer text-sm">{t("Recorded market and holding context")}</summary>{context.records.filter((f) => f.kind === "market").map((f) => <Fact key={f.ref} fact={f} onDecision={onDecision} />)}</details>
        <details><summary className="cursor-pointer text-sm">{t("Historical comparisons under fixed assumptions")} ({historical.length})</summary>{historical.map((f) => <Fact key={f.ref} fact={f} onDecision={onDecision} />)}</details>
        <h2 className="text-base">{t("Possible explanations")}</h2>
        {!answer ? <p className="text-sm text-muted">{t("No model interpretation yet. The records above are deterministic, not an AI answer.")}</p> : <>
          {answer.possible_explanations.map((h, i) => <div key={i} className="space-y-2 border-b border-border pb-3 text-sm"><p>{t(h.claim)}</p><p className="text-xs text-muted">{t("Alternative explanations")}: {h.alternative_explanations.map((s) => t(s)).join(" · ")}</p><p className="text-xs text-muted">{t("Missing information")}: {h.missing_information.map((s) => t(s)).join(" · ")}</p><div className="flex flex-wrap gap-2">{[...h.supporting_evidence_refs, ...h.contradictory_evidence_refs].map((ref) => <button key={ref} className="text-xs text-accent" onClick={() => link(ref)}>{t(h.contradictory_evidence_refs.includes(ref) ? "Contrary material" : "Supporting material")} → {t(context.records.find((r) => r.ref === ref)?.title ?? "View evidence")}</button>)}</div></div>)}
          <p className="text-sm">{t(answer.question_kind)}</p><p className="text-xs text-muted">{answer.provider} · {answer.model} · {answer.generated_at}</p>
          <details className="text-xs text-muted"><summary>{t("Executed review tools")}</summary>{answer.executed_tools.join(" · ")}</details>
        </>}
        {focused ? <Fact key={focused.ref} fact={focused} onDecision={onDecision} expanded /> : null}
        <label className="block space-y-2 text-sm"><span>{t("Continue with a question")}</span><textarea className={inputClass} maxLength={2000} value={question} disabled={busy} placeholder={t("What happened in this investment, and what remains uncertain?")} onChange={(e) => { setQuestion(e.target.value); setAnswer(null); guard.current.next(); }} /></label>
        <label className="flex gap-2 text-xs text-muted"><input type="checkbox" checked={consent} disabled={busy} onChange={(e) => setConsent(e.target.checked)} />{t("Send these scoped derived facts and my notes to the configured review model. It cannot place trades.")}</label>
        <Button disabled={busy || loading || !consent} onClick={() => void analyze()}>{t(busy ? "Reviewing facts and counterexamples…" : "Ask for an evidence-grounded review")}</Button>
        <details className="border-t border-border pt-3"><summary className="cursor-pointer text-sm">{t("Add a reason or original plan (retrospective)")}</summary><div className="mt-3 space-y-3"><p className="text-xs text-muted">{t("This is recorded now, not proof that the information existed before the trade. New notes invalidate earlier interpretations.")}</p><select aria-label={t("Note type")} className={inputClass} value={noteKind} disabled={busy} onChange={(e) => setNoteKind(e.target.value)}><option value="reason">{t("My recalled reason")}</option><option value="plan">{t("My recalled staged plan")}</option></select><textarea aria-label={t("Retrospective user note")} className={inputClass} maxLength={4000} value={note} disabled={busy} onChange={(e) => setNote(e.target.value)} /><Button size="sm" disabled={busy || !note.trim()} onClick={() => void saveNote()}>{t("Save retrospective note")}</Button></div></details>
        <details className="text-xs text-muted"><summary>{t("Previous interpretations (revisable)")}</summary>{context.inferences.map((r) => <p key={r.inference_id} className="mt-2">{r.generated_at} · {t(r.invalidated ? "Invalidated by newer information" : "Previous interpretation, not financial evidence")}</p>)}</details>
      </> : null}
    </div> : null}
  </section>;
}
