import { useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, MessageCircle, ScanLine } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { realUserApi } from "@/data/runtimeService";
import { adaptRuntimePositionEpisodeEntry, type PositionEpisodeEntryView } from "@/data/positionEpisode";
import { DecisionAnalysisWorkspace } from "@/components/review/DecisionAnalysisWorkspace";
import { useLocale } from "@/locales/LocaleProvider";
import { reviewCandidatesFromFixture, reviewCandidatesFromRuntime, scopedCandidate, type ReviewEpisodeCandidate } from "./reviewWorkspaceData";
import { useWorkspaceCopy } from "./copy";
import "./review-workspace.css";

const zh = {
  title: "从记录中，重新看见决策", description: "选择一轮投资，沿着已记录的操作与依据复盘。不按收益高低给你的决策打分。", queue: "投资复盘索引", facts: "这轮投资的操作与依据", factHint: "按原始顺序呈现；打开操作可查看交易前后状态及已注册的历史假设。", noFacts: "尚无可用于复盘的详细记录。", scope: "当前对象", period: "投资期间", holding: "持有中", closed: "已结束", open: "打开完整复盘", empty: "先选择一个有成交记录的账户", emptyHint: "导入真实账户或明确进入 Synthetic 产品预览。这里不会替你选择其他账户的数据。", journalTitle: "给决策留下当时的语境", journalHint: "用户自述不是系统确认的事实。事后补记不会变成事前已知的信息。", plan: "当时的计划", reason: "操作理由", exit: "退出条件", followup: "下次复盘日期", write: "我想记录…", retrospective: "这是一条事后补记", draft: "生成本页草稿预览", draftHint: "仅当前页面内存保留；切换页面、账户、投资或刷新会清空。没有写入 Journal、Evidence、Twin 或账本。", noteAt: "草稿记录于", noJournal: "Journal 持久化尚未接入", userStatement: "用户自述 · 非金融事实", askTitle: "有依据地问，沿记录理解", askHint: "从当前投资的确定性事实出发，区分历史比较、可能解释与仍缺少的信息。", offline: "当前对象未接通模型运行", offlineHint: "普通示例 Episode 没有可调用的分析范围，不会播放假过程或生成示例回答。原有 SYN_COMPARE_A/B 独立工作区保留真实本机分析入口。", pair: "打开独立同股示例 A / B", tools: "记录事实 → 支持与反例 → 已注册历史比较 → 可验证回答", loading: "正在读取该账户的确定性记录…", errors: "无法读取当前记录", unavailable: "尚未形成此范围的事实", all: "全部已记录操作", evidence: "依据引用", factCount: "后端精选事实", steps: "记录 / 复核 / 理解", noRanking: "按投资开始时间排列，不声称系统已计算复盘优先级。", question: "想问这轮投资什么？", questionHint: "输入仅在本页暂存。连接后仍需明确的模型使用授权。", askExamples: ["这轮投资发生了什么？", "哪些操作值得再看？", "有哪些信息还无法确认？"],
};
const en: typeof zh = {
  title: "See your decisions in context", description: "Follow recorded actions and their evidence. Investment outcomes are not a decision score.", queue: "Review index", facts: "Recorded actions & evidence", factHint: "Original ordering is retained. Open an action for before/after state and registered historical alternatives.", noFacts: "Detailed review records are not available.", scope: "Selected investment", period: "Episode period", holding: "Open", closed: "Closed", open: "Open complete review", empty: "Choose an account with execution records", emptyHint: "Import your account or explicitly enter Synthetic preview. Another account’s data cannot substitute.", journalTitle: "Leave context for your decisions", journalHint: "A user statement is not a confirmed fact. Retrospective notes never become prior knowledge.", plan: "Original plan", reason: "Reason for the action", exit: "Exit conditions", followup: "Next review date", write: "I want to record…", retrospective: "This is a retrospective note", draft: "Preview this page’s draft", draftHint: "In-memory on this page only. Navigation, account/Episode changes or refresh clear it. Nothing is written to Journal, Evidence, Twin or the ledger.", noteAt: "Draft recorded at", noJournal: "Journal persistence is not connected", userStatement: "User statement · Not a financial fact", askTitle: "Ask with evidence in view", askHint: "Start with deterministic facts. Separate historical comparisons, possible explanations and missing information.", offline: "Model runtime is not connected for this object", offlineHint: "Ordinary example Episodes have no callable analysis scope. No fake progress or sample answer is shown. The independent SYN_COMPARE_A/B workspace retains its real local analysis entry.", pair: "Open independent same-stock A / B example", tools: "Recorded facts → support & contradictions → registered history → validated answer", loading: "Reading this account’s deterministic records…", errors: "Could not read current records", unavailable: "Facts unavailable for this scope", all: "All recorded actions", evidence: "Evidence references", factCount: "Backend-selected facts", steps: "RECORD / REVIEW / UNDERSTAND", noRanking: "Ordered by start date. No computed review-priority ranking is claimed.", question: "What would you like to ask?", questionHint: "Input stays on this page. Connected model use still requires explicit consent.", askExamples: ["What happened in this investment?", "Which actions merit a closer look?", "What is still unknown?"],
};

function JournalDraft({ episodeId }: { episodeId: string }) {
  const { locale } = useLocale(); const c = locale === "zh-CN" ? zh : en;
  const [fields, setFields] = useState({plan: "", reason: "", exit: "", followup: ""});
  const [retrospective, setRetrospective] = useState(true);
  const [draft, setDraft] = useState<{ fields: typeof fields; recordedAt: string; retrospective: boolean } | null>(null);
  return <section className="iw-panel__body"><span className="iw-badge">{c.noJournal}</span><p className="iw-note">{c.draftHint}</p>
    <form className="iw-form" onSubmit={(event) => {event.preventDefault(); setDraft({ fields: {...fields}, recordedAt: new Date().toISOString(), retrospective });}}>
      {(["plan", "reason", "exit"] as const).map((field) => <label key={field}><span>{c[field]}</span><textarea value={fields[field]} placeholder={c.write} onChange={(event) => {setDraft(null); setFields({...fields, [field]: event.target.value});}} /></label>)}
      <div className="iw-form__row"><label><span>{c.followup}</span><input type="date" value={fields.followup} onChange={(event) => {setDraft(null); setFields({...fields, followup: event.target.value});}} /></label><label className="iw-retrospective"><input type="checkbox" checked={retrospective} onChange={(event) => {setDraft(null); setRetrospective(event.target.checked);}} />{c.retrospective}</label></div>
      <button className="iw-action" disabled={!fields.plan.trim() && !fields.reason.trim() && !fields.exit.trim()}>{c.draft}</button>
    </form>
    {draft && <section className="iw-session-entry" data-journal-draft><span className="iw-kicker">{c.userStatement}</span><small>{c.noteAt} {draft.recordedAt} · {episodeId} · {draft.retrospective ? c.retrospective : c.userStatement}</small>{Object.entries(draft.fields).filter(([, value]) => value).map(([field, value]) => <p key={field}><strong>{c[field as keyof typeof fields]}</strong><br />{value}</p>)}</section>}
  </section>;
}

export function ReviewWorkspace({ view = "review" }: { view?: "review" | "journal" | "ask" }) {
  const data = useDataMode(); const { locale, t, formatNumber } = useLocale(); const w = useWorkspaceCopy(); const c = locale === "zh-CN" ? zh : en;
  const location = useLocation(); const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(new URLSearchParams(location.search).get("episode"));
  useEffect(() => { setSelectedId(new URLSearchParams(location.search).get("episode")); }, [location.search]);
  const [candidates, setCandidates] = useState<ReviewEpisodeCandidate[]>([]);
  const [entry, setEntry] = useState<PositionEpisodeEntryView | null>(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null); const [question, setQuestion] = useState("");
  const subject = data.mode === "demo" ? data.exampleAccount.subjectId : data.activeAccount?.subject_id;
  const account = data.mode === "demo" ? data.exampleAccount.accountId : data.activeAccount?.account_id;
  useEffect(() => {
    let cancelled = false; setCandidates([]); setEntry(null); setError(null); setQuestion("");
    if (!subject || !account) {setLoading(false); return;}
    if (data.mode === "demo") {setCandidates(reviewCandidatesFromFixture(positionEpisodeDemo.entries, subject, account)); setLoading(false); return;}
    setLoading(true);
    void realUserApi.investments(subject, account).then((value) => { if (!cancelled) {
      if (value.subject_id !== subject || value.account_id !== account) throw new Error("account_scope_mismatch");
      setCandidates(reviewCandidatesFromRuntime(value));
    }}).catch((e) => {if (!cancelled) setError(String(e));}).finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [data.mode, subject, account]);
  const current = useMemo(() => scopedCandidate(candidates, selectedId), [candidates, selectedId]);
  useEffect(() => {
    let cancelled = false; setEntry(null); setError(null); setQuestion("");
    if (!current) return;
    if (data.mode === "demo") {setEntry(positionEpisodeDemo.entries.find((item) => item.episode.episodeId === current.episodeId && item.episode.subjectId === subject && item.episode.accountId === account) ?? null); return;}
    setLoading(true);
    void realUserApi.episode(current.subjectId, current.accountId, current.episodeId).then((result) => {
      if (cancelled) return; if (!result.entry) {setError(result.reason ?? "episode_unavailable"); return;}
      const next = adaptRuntimePositionEpisodeEntry(result.entry);
      if (next.episode.episodeId !== current.episodeId || next.episode.subjectId !== subject || next.episode.accountId !== account) throw new Error("episode_scope_mismatch");
      setEntry(next);
    }).catch((e) => {if (!cancelled) setError(String(e));}).finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [current, data.mode, subject, account]);
  const date = (value: string) => new Intl.DateTimeFormat(locale, {year:"numeric",month:"short",day:"numeric"}).format(new Date(value));
  return <div className="iw-page iw-review-workspace"><header className="iw-page-heading"><span className="iw-kicker">{c.steps}</span><h1>{view === "journal" ? c.journalTitle : view === "ask" ? c.askTitle : c.title}</h1><p>{view === "journal" ? c.journalHint : view === "ask" ? c.askHint : c.description}</p></header>
    <div className="iw-tabs" role="group" aria-label={w.review}>{(["review", "journal", "ask"] as const).map((tab) => <Link key={tab} to={`/${tab}${current ? `?episode=${encodeURIComponent(current.episodeId)}` : ""}`} className={view === tab ? "is-active" : ""}>{tab === "review" ? <ScanLine size={14} /> : tab === "journal" ? <BookOpen size={14} /> : <MessageCircle size={14} />}{w[tab]}</Link>)}</div>
    {error && <p role="alert" className="iw-note">{c.errors}: {error}</p>}{loading && <p role="status" className="iw-note">{c.loading}</p>}
    {!current && !loading ? <section className="iw-surface iw-disconnected"><ScanLine size={32} /><h2>{c.empty}</h2><p>{c.emptyHint}</p><div className="iw-context"><Link className="iw-primary" to="/data">{w.data}<ArrowRight size={15} /></Link><button className="iw-action" onClick={() => data.setMode("demo")}>{w.preview}</button><Link className="iw-text-link" to="/investments/compare-example">{c.pair}</Link></div></section> : current ? <div className="iw-grid"><aside className="iw-rail"><div className="iw-rail__head"><h2>{c.queue}</h2><span className="iw-count">{candidates.length}</span></div>{candidates.map((item) => <button key={item.episodeId} className="iw-candidate" aria-pressed={current.episodeId === item.episodeId} onClick={() => navigate(`/${view}?episode=${encodeURIComponent(item.episodeId)}`)}><strong>{t(item.instrumentName)}</strong><span>{date(item.openedAt)} → {item.closedAt ? date(item.closedAt) : c.holding}</span><span>{item.reviewFactCount === null ? c.unavailable : `${c.factCount} ${item.reviewFactCount}`} · {item.status === "open" ? c.holding : c.closed}</span></button>)}<p className="iw-rail-note">{c.noRanking}</p></aside>
      <section className="iw-panel"><div className="iw-panel__head"><div><span className="iw-kicker">{c.scope}</span><h2>{t(current.instrumentName)}</h2></div><Link className="iw-link" to={`/investments/episodes/${current.episodeId}`}>{c.open} ↗</Link></div>
        {view === "journal" ? <JournalDraft key={`${subject}:${account}:${current.episodeId}`} episodeId={current.episodeId} /> : <div className="iw-panel__body"><div className="iw-fact-grid"><div className="iw-fact"><span>{c.period}</span><strong>{date(current.openedAt)} → {current.closedAt ? date(current.closedAt) : c.holding}</strong></div><div className="iw-fact"><span>{c.all}</span><strong>{entry ? entry.decisions.length : "—"}</strong></div><div className="iw-fact"><span>{c.evidence}</span><strong>{entry ? entry.evidenceReferences.length : "—"}</strong></div></div>
          {view === "review" && entry?.reviewPresentation?.facts.length ? <section className="iw-selected-facts"><span className="iw-kicker">{c.factCount}</span>{entry.reviewPresentation.facts.map((fact) => { const pattern = entry.pathAnalysis.patterns.find((item) => item.patternId === fact.patternId); const labels: Record<string,string> = {consecutive_scaling_in:"Consecutive scaling in",consecutive_scaling_out:"Consecutive scaling out",add_after_positive_market_move:"Add after a recorded positive market move",exit_after_negative_market_move:"Exit after a recorded negative market move",high_quantity_during_daily_price_drawdown:"Recorded quantity during the daily price peak-to-trough path",long_no_execution_interval:"Long interval with no additional executions",price_following_scale_sequence:"Scaling sequence aligned with the recorded price path",loss_state_addition_reused:"Existing loss-state Evidence reused"}; return <Link key={fact.itemId} to={`/investments/episodes/${current.episodeId}?fact=${encodeURIComponent(fact.itemId)}`}><strong>{t(labels[pattern?.patternCode ?? ""] ?? "Facts worth revisiting")}</strong><span>{date(fact.startAt)} → {date(fact.endAt)}</span><ArrowRight size={14} /></Link>; })}</section> : null}
          {view === "review" ? <section className="iw-section"><h2 className="iw-section__title">{c.facts}</h2><p className="iw-section__hint">{c.factHint}</p><ul className="iw-review-facts">{entry?.decisions.map((decision) => <li key={decision.decisionId}><Link to={`/investments/episodes/${current.episodeId}?decision=${encodeURIComponent(decision.decisionId)}`}><span>{t({open_position:"Open position",add_position:"Add position",reduce_position:"Reduce position",close_position:"Close position / final sale"}[decision.decisionType])}</span><small>{date(decision.occurredAt)} · {formatNumber(decision.executedQuantity)} @ {formatNumber(decision.executionPrice, 2)}</small><ArrowRight size={14} /></Link></li>)}</ul>{!entry?.decisions.length && <p className="iw-note">{c.noFacts}</p>}</section> : <section className="iw-section"><p className="iw-section__hint">{c.tools}</p>{data.mode === "demo" && <><label className="iw-form"><span>{c.question}</span><textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={c.questionHint} /></label><div className="iw-question-suggestions">{c.askExamples.map((text) => <button key={text} onClick={() => setQuestion(text)}>{text}</button>)}</div><div className="iw-note"><strong>{c.offline}</strong><p>{c.offlineHint}</p></div><Link className="iw-text-link" to="/investments/compare-example">{c.pair}<ArrowRight size={14} /></Link></>}
          {data.mode === "real_user" && <DecisionAnalysisWorkspace key={current.episodeId} scope={{subject_id:current.subjectId,account_id:current.accountId,episode_id:current.episodeId,data_mode:"real_user"}} onDecision={(id) => navigate(`/investments/episodes/${current.episodeId}?decision=${encodeURIComponent(id)}`)} />}</section>}
        </div>}
      </section></div> : null}
    {data.mode === "demo" && <section className="iw-surface iw-method-study"><span className="iw-kicker">SYNTHETIC / INDEPENDENT METHOD STUDIES</span><h2>{t("Decision evidence")}</h2><p>{t("Standalone legacy example · not the selected account")}</p><div className="iw-context"><Link className="iw-text-link" to="/review/decisions">{t("Selection")} · {t("Sizing")} · {t("Exit")} · {t("Friction")}<ArrowRight size={14} /></Link><Link className="iw-text-link" to="/advanced/evidence">{t("Evidence, method, and source")}<ArrowRight size={14} /></Link></div></section>}
  </div>;
}
