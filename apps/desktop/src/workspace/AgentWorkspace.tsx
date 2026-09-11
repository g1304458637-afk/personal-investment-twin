import { useEffect, useRef, useState } from "react";
import { ArrowUp, ArrowUpRight, ChartNoAxesCombined, MessageCircle, Plus, Square, RotateCcw, ChevronDown } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { useLocale } from "@/locales/LocaleProvider";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { realUserApi } from "@/data/runtimeService";
import { modelServiceRequest, type ModelServiceStatus } from "@/data/modelService";
import { searchServiceRequest, type SearchServiceStatus } from "@/data/searchService";
import { AgentCapabilityOverview } from "./AgentCapabilityOverview";
import { capabilityCatalog, capabilityScopeTarget, type ServiceState } from "./agentCapabilityCatalog";
import { AgentAnalysisCards } from "./AgentAnalysisCards";
import { AgentTurnStatus } from "./AgentTurnStatus";
import { agentChatService } from "@/data/agentChatService";
import { startChatTurn } from "@/data/chatTurnState";
import { accountGuideEpisode, restoredConversationTurns } from "@/data/agentChat";
import { chartGuideTarget } from "@/data/chartGuide";
import { ChatTurnError, chatScopeKey, contextMatchesScope, isAccountScope, previousChatResult, projectAccountAnswer, readChat, readChatContext, saveChatContext, runChatTurn, saveChat, verifiedChatResult, type ChatContext, type ConversationScope, type ChatTurn } from "@/data/agentChat";
import { SourceLink } from "@/components/common/SourceLink";
import { reviewCandidatesFromFixture, reviewCandidatesFromRuntime, type ReviewEpisodeCandidate } from "./reviewWorkspaceData";
import { agentChatCopy, chatErrorText, chatContextErrorText } from "./agentChatCopy";
import "./agent-chat.css";

function ChatSession({ scope, candidates }: { scope: ConversationScope; candidates: ReviewEpisodeCandidate[] }) {
  const { locale } = useLocale(); const c = agentChatCopy[locale];
  const [context, setContext] = useState<ChatContext | null>(() => readChatContext(scope));
  const [configured, setConfigured] = useState(false);
  const [searchReady, setSearchReady] = useState(false);
  const [searchState, setSearchState] = useState<ServiceState>("checking");
  const [quotesState, setQuotesState] = useState<ServiceState>("checking");
  const [modelLoading, setModelLoading] = useState(false);
  const [modelError, setModelError] = useState<string>();
  const [loading, setLoading] = useState(agentChatService.available());
  const [contextError, setContextError] = useState<string>();
  const [reload, setReload] = useState(0);
  const [turns, setTurns] = useState<ChatTurn[]>(() => readChat(scope));
  const [draft, setDraft] = useState(""); const [consent, setConsent] = useState(false);
  const [activeEntry, setActiveEntry] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const active = useRef<AbortController | null>(null);
  const latestTurns = useRef(turns); const transcript = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const restoreOnLoad = useRef(true);
  const update = (next: ChatTurn[]) => { latestTurns.current = next; saveChat(scope, next); setTurns(next); };
  useEffect(() => {
    let alive = true; setContextError(undefined);
    if (!agentChatService.available()) return;
    setLoading(true); setModelLoading(true); setConfigured(false); setModelError(undefined);
    setSearchState("checking"); setQuotesState("checking");
    void agentChatService.context(scope).then(value => {
      if (!alive) return;
      if (!contextMatchesScope(value, scope)) throw new Error("chat_scope_mismatch");
      saveChatContext(scope, value); setContext(value);
      // Account context already checks the quote library under its cold-start
      // deadline. A parallel 30-second status request can time out in the queue.
      setQuotesState("version" in value && value.research?.quotes?.available === true ? "configured" : "unavailable");
      if (restoreOnLoad.current && !latestTurns.current.length) update(restoredConversationTurns(value));
    }).catch(error => { if (alive) { setContextError(error instanceof Error ? error.message : "context_unavailable"); setQuotesState("unavailable"); } })
      .finally(() => { if (alive) setLoading(false); });
    void modelServiceRequest<ModelServiceStatus>("status").then(model => {
      if (alive) setConfigured(model.configured);
    }).catch(error => { if (alive) setModelError(error instanceof Error ? error.message : "model_service_unavailable"); })
      .finally(() => { if (alive) setModelLoading(false); });
    void searchServiceRequest<SearchServiceStatus>("status").then(search => {
      if (alive) { setSearchReady(search.configured && search.enabled); setSearchState(search.configured && search.enabled ? "configured" : "unavailable"); }
    }).catch(() => { if (alive) { setSearchReady(false); setSearchState("unavailable"); } });
    return () => { alive = false; };
  }, [reload]); // ChatSession is keyed by the complete scope, including account and data mode.
  useEffect(() => () => {
    active.current?.abort(); active.current = null;
    saveChat(scope, latestTurns.current.map(turn => turn.status === "running" ? { ...turn, status: "stopped" } : turn));
  }, []);
  useEffect(() => { if (turns.length && followLatest.current && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight; }, [turns]);
  useEffect(() => { if (textarea.current) { textarea.current.style.height = "auto"; textarea.current.style.height = `${Math.min(160, Math.max(52, textarea.current.scrollHeight))}px`; } }, [draft]);
  const submit = async (retryId?: string) => {
    const question = retryId ? latestTurns.current.at(-1)?.question ?? "" : draft.trim();
    if (active.current || loading || contextError || !context || !configured || !consent || !question || question.length > 2000) return;
    const controller = new AbortController(); active.current = controller; setBusy(true);
    const id = retryId ?? crypto.randomUUID(); const previous = previousChatResult(latestTurns.current);
    followLatest.current = true;
    update(startChatTurn(latestTurns.current, question, id, retryId)); if (!retryId) setDraft("");
    try {
      const result = await runChatTurn(agentChatService, scope, context, question, previous, controller.signal, undefined, phase => {
        if (active.current === controller) update(latestTurns.current.map(turn => turn.id === id ? {...turn, phase} : turn));
      });
      if (active.current !== controller) return;
      update(latestTurns.current.map(turn => turn.id === id ? { ...turn, result, status: "complete" } : turn));
    } catch (error) {
      if (active.current !== controller) return;
      update(latestTurns.current.map(turn => turn.id === id ? { ...turn, status: "failed", reason: error instanceof Error ? error.message : "review_failed", diagnosticId: error instanceof ChatTurnError ? error.diagnosticId : undefined } : turn));
    } finally { if (active.current === controller) { active.current = null; setBusy(false); } }
  };
  const stop = () => {
    active.current?.abort(); active.current = null; setBusy(false);
    update(latestTurns.current.map(turn => turn.status === "running" ? { ...turn, status: "stopped" } : turn));
  };
  const newChat = () => { restoreOnLoad.current = false; stop(); update([]); setDraft(""); setConsent(false); setReload(value => value + 1); textarea.current?.focus({ preventScroll: true }); };
  const prompts = isAccountScope(scope) ? c.accountPrompts : c.episodePrompts;
  const entry = c.entries.find(item => item.id === activeEntry);
  const services = {
    desktop: agentChatService.available(), wholeAccount: isAccountScope(scope), synthetic: scope.data_mode === "synthetic_showcase",
    model: (modelLoading ? "checking" : configured ? "configured" : "unavailable") as ServiceState, quotes: quotesState, search: searchState,
  };
  const selectedCapability = capabilityCatalog.find(item => item.id === activeEntry);
  const entryScopeTarget = selectedCapability ? capabilityScopeTarget(selectedCapability.needs, services) : null;
  const comparisonPrompts = locale === "zh-CN" ? [
    "帮我比较两个时间段的账户表现，先告诉我有哪些日期记录、还需要我选择什么。",
    "查找我在同一只股票上的两轮投资，先检查是否有共同市场区间，再解释操作和成本的差异。",
  ] : ["Compare two periods of my account. First tell me which dates are recorded and what I need to choose.",
    "Find two investments I made in the same stock. Check for a shared market window before explaining operations and costs."];
  const scenarioPrompts = selectedCapability?.id === "scenario" ? [selectedCapability.prompt[locale === "zh-CN" ? "zh" : "en"]] : [];
  const entryPrompts = entryScopeTarget ? [] : activeEntry === "analyze" ? prompts : activeEntry === "compare" ? comparisonPrompts
    : activeEntry === "scenario" ? scenarioPrompts : c.suggestions[activeEntry as keyof typeof c.suggestions] ?? [];
  const chooseQuestion = (question: string) => {
    setDraft(question);
    textarea.current?.scrollIntoView({ behavior: "auto", block: "center" });
    textarea.current?.focus({ preventScroll: true });
  };
  return <div className="agent-chat__workspace">
    <AgentCapabilityOverview locale={locale} busy={busy} onQuestion={chooseQuestion} services={services} />
    <section className="agent-chat__conversation" aria-label={c.title}>
    <div className="agent-chat__session-bar"><span>{isAccountScope(scope) ? c.account : c.episode}</span><div className="agent-chat__session-actions">{context && restoredConversationTurns(context).length > 0 && <button disabled={busy || loading} onClick={() => { update(restoredConversationTurns(context)); restoreOnLoad.current = true; }}><RotateCcw size={15}/>{locale === "zh-CN" ? "已保存的对话" : "Saved conversation"}</button>}<button onClick={newChat} disabled={busy}><Plus size={15} />{c.newChat}</button></div></div>
    {!agentChatService.available() ? <p className="agent-chat__notice">{c.browser}</p> : loading ? <p role="status" className="agent-chat__notice">{context ? c.refreshing : c.loading}</p> : contextError ? <div role="alert" className="agent-chat__notice">{chatContextErrorText(contextError, locale)} <button onClick={() => setReload(value => value + 1)}>{c.retry}</button></div> : modelLoading ? <p role="status" className="agent-chat__notice">{c.modelLoading}</p> : modelError ? <div role="alert" className="agent-chat__notice">{chatErrorText(modelError, locale)} <Link to="/settings">{c.configuration} ↗</Link></div> : !configured ? <p className="agent-chat__notice">{c.missing} <Link to="/settings">{c.configuration} ↗</Link></p> : null}
    <div ref={transcript} className="agent-chat__transcript" role="log" aria-label={c.title} aria-live="polite" aria-relevant="additions text" onScroll={event => { const el = event.currentTarget; followLatest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
      {!turns.length && !contextError && <div className="agent-chat__welcome"><MessageCircle size={26} strokeWidth={1.3} /><h2>{c.emptyTitle}</h2><p>{c.empty}</p>
        <p className="agent-chat__welcome-hint">{c.capabilityHint}</p>
      </div>}
      {turns.map(turn => <article key={turn.id} className="agent-chat__turn">
        <div className="agent-chat__question"><span>{c.user}</span><p>{turn.question}</p></div>
        <div className="agent-chat__answer"><span className="agent-chat__speaker">{c.agent}</span>
          {turn.status !== "complete" ? <AgentTurnStatus turn={turn} locale={locale}/> : turn.result && context ? (() => {
            if (!verifiedChatResult(turn.result, context)) return <p>{chatErrorText("conversation_stale", locale)}</p>;
            if ("version" in context) {
              const answer = projectAccountAnswer(turn.result, context, locale);
              if (!answer) return <p>{chatErrorText("conversation_stale", locale)}</p>;
              return <div data-account-answer><p className="agent-chat__summary">{answer.summary}</p><AgentAnalysisCards cards={answer.cards} locale={locale}/>{answer.findings.map(finding => <section key={finding.id}>{finding.title && <h3>{finding.title}</h3>}<p>{finding.body}</p>{finding.episodeId && candidates.some(item => item.episodeId === finding.episodeId) && <Link to={chartGuideTarget("episode-process", finding.episodeId)!}>{c.viewChart} <ArrowUpRight size={14} /></Link>}</section>)}{answer.guideIds.filter(id => id !== "episode-process").map(id => <div key={id}><Link to={chartGuideTarget(id)!}>{c.guide} · {id === "pretrade-allocation" ? c.guideAllocation : c.guideCompare}<ArrowUpRight size={14}/></Link></div>)}{answer.actions.map(action => {
                const displayId = action.episodeId ? accountGuideEpisode(context, action.episodeId, candidates.map(item => item.episodeId)) : undefined;
                const target = action.id === "episode-process" && !displayId ? null : chartGuideTarget(action.id, displayId);
                return target ? <div key={`${action.id}:${action.episodeId}`}><Link to={target}>{action.label}<ArrowUpRight size={14}/></Link></div> : null;
              })}{answer.sources?.length ? <details className="agent-chat__source-disclosure"><summary>{c.sources} · {answer.sources.length}<ChevronDown size={13} aria-hidden="true"/></summary><ul className="agent-chat__sources">{answer.sources.map(source => <li key={`${source.provider}:${source.url || source.title}`}>{source.url ? <SourceLink url={source.url} zh={locale === "zh-CN"}>{source.title}<ArrowUpRight size={12}/></SourceLink> : <span>{source.title}</span>}<small>{[source.site_name, source.published_at?.slice(0,10), source.retrieved_at?.slice(0,16)?.replace("T"," "), source.adjust].filter(Boolean).join(" · ")}</small></li>)}</ul></details> : null}</div>;
            }
            return <p>{chatErrorText("conversation_stale", locale)}</p>;
          })() : <p>{c.loading}</p>}
          {(turn.status === "failed" || turn.status === "stopped") && turns.at(-1)?.id === turn.id && <button className="agent-chat__retry" disabled={busy || loading || !!contextError || !context || !configured || !consent} onClick={() => void submit(turn.id)}><RotateCcw size={14}/>{c.retryAnswer}</button>}
        </div>
      </article>)}
    </div>
    <div className="agent-chat__capabilities" aria-label={c.capabilities} onKeyDown={event => { if (event.key === "Escape" && activeEntry) { event.preventDefault(); const button = event.currentTarget.querySelector<HTMLButtonElement>('button[aria-expanded="true"]'); setActiveEntry(null); button?.focus(); } }}>
      <div className="agent-chat__capability-bar">{c.entries.map(item => <button type="button" key={item.id} aria-expanded={activeEntry === item.id} aria-controls="agent-capability-examples" onClick={() => setActiveEntry(current => current === item.id ? null : item.id)}>{item.title}<ChevronDown size={13} aria-hidden="true" /></button>)}</div>
      {entry && <div id="agent-capability-examples" className="agent-chat__capability-examples">
        <p>{entry.blurb}</p><button type="button" className="agent-chat__examples-close" onClick={() => setActiveEntry(null)}>{locale === "zh-CN" ? "收起" : "Close"}</button>
        {entryScopeTarget && <Link to={entryScopeTarget}>{entryScopeTarget === "/ask" ? (locale === "zh-CN" ? "切换到整个账户" : "Switch to whole account") : (locale === "zh-CN" ? "前往数据与账户选择示例" : "Choose an example in Data & accounts")}<ArrowUpRight size={12}/></Link>}
        <div>{entryPrompts.map(question => <button type="button" key={question} disabled={busy} onClick={() => { setDraft(question); setActiveEntry(null); textarea.current?.focus({ preventScroll: true }); }}>{question}<ArrowUpRight size={13} aria-hidden="true" /></button>)}</div>
        {activeEntry === "research" && !searchReady && <Link to="/settings">{c.searchNeeded}<ArrowUpRight size={12} aria-hidden="true" /></Link>}
      </div>}
    </div>
    <form className="agent-chat__composer" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <label className="sr-only" htmlFor="agent-question">{c.question}</label><textarea ref={textarea} id="agent-question" rows={2} value={draft} maxLength={2000} placeholder={c.question} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />
      <div className="agent-chat__composer-actions"><label><input type="checkbox" checked={consent} disabled={busy || !agentChatService.available()} onChange={event => setConsent(event.target.checked)} />{c.consent}</label>{busy ? <button type="button" onClick={stop}><Square size={14} />{c.stop}</button> : <button type="submit" disabled={loading || !!contextError || !configured || !context || !consent || !draft.trim()} aria-label={c.send}><ArrowUp size={18} />{c.send}</button>}</div>
      {!busy && agentChatService.available() && draft.trim() && !consent && <p className="agent-chat__send-hint">{locale === "zh-CN" ? "勾选上方授权后发送；选择示例问题不会自动调用模型。" : "Allow model access above to send. Example prompts never submit automatically."}</p>}
    </form><p className="agent-chat__session-note">{context && "version" in context && context.session_only === false ? (isAccountScope(scope)
      ? (locale === "zh-CN" ? "已完成的账户对话自动保存在本机；切换页面或重启不会重新生成。" : "Completed account conversations are saved locally; navigation or restart does not regenerate answers.")
      : (locale === "zh-CN" ? "已完成的本轮对话自动保存在本机；切换页面或重启不会重新生成。" : "Completed investment conversations are saved locally; navigation or restart does not regenerate answers.")) : c.session}</p>
  </section></div>;
}

export function AgentWorkspace() {
  const data = useDataMode(); const { locale, t } = useLocale(); const c = agentChatCopy[locale];
  const location = useLocation(); const navigate = useNavigate();
  const subject = data.mode === "demo" ? data.exampleAccount.subjectId : data.activeAccount?.subject_id;
  const account = data.mode === "demo" ? data.exampleAccount.accountId : data.activeAccount?.account_id;
  const selected = new URLSearchParams(location.search).get("episode") ?? "";
  const [catalog, setCatalog] = useState<{ key: string; items: ReviewEpisodeCandidate[] }>({key:"",items:[]});
  const accountKey = JSON.stringify([data.mode, subject, account]);
  const candidates = catalog.key === accountKey ? catalog.items : [];
  useEffect(() => {
    let alive = true;
    if (!subject || !account) return;
    if (data.mode === "demo") { setCatalog({key:accountKey,items:reviewCandidatesFromFixture(positionEpisodeDemo.entries, subject, account)}); return; }
    void realUserApi.investments(subject, account).then(value => { if (alive && value.subject_id === subject && value.account_id === account) setCatalog({key:accountKey,items:reviewCandidatesFromRuntime(value)}); }).catch(() => { if (alive) setCatalog({key:accountKey,items:[]}); });
    return () => { alive = false; };
  }, [accountKey]);
  const validEpisode = candidates.find(item => item.episodeId === selected);
  const scope: ConversationScope | null = !subject || !account || (selected && !validEpisode) ? null : selected
    ? {scope_kind:"episode",subject_id:subject,account_id:account,episode_id:selected,data_mode:data.mode === "demo" ? "synthetic_showcase" : "real_user"}
    : {scope_kind:"account",subject_id:subject,account_id:account,data_mode:data.mode === "demo" ? "synthetic_showcase" : "real_user"};
  return <div className="agent-chat iw-page">
    <header className="agent-chat__heading"><h1>{c.title}</h1><p>{c.intro}</p></header>
    {(!subject || !account) && <AgentCapabilityOverview locale={locale} busy={false} canCompose={false} onQuestion={() => undefined} services={{
      desktop: agentChatService.available(), wholeAccount: true, model: "unavailable", quotes: "unavailable", search: "unavailable",
    }} />}
    {!subject || !account ? <section className="agent-chat__empty"><MessageCircle size={28} /><h2>{c.emptyTitle}</h2><p>{c.noAccount}</p><div><Link className="iw-action" to="/data">{c.import}</Link><button className="iw-primary" onClick={() => { data.setMode("demo"); navigate("/ask"); }}>{c.example}</button></div></section> : <>
      <div className="agent-chat__scope"><label htmlFor="agent-scope">{c.scope}</label><select id="agent-scope" value={selected} onChange={event => navigate(event.target.value ? `/ask?episode=${encodeURIComponent(event.target.value)}` : "/ask")}><option value="">{c.account}</option>{selected && !validEpisode && <option value={selected} disabled>{c.unavailableEpisode}</option>}{candidates.map(item => <option key={item.episodeId} value={item.episodeId}>{t(item.instrumentName)} · {item.openedAt.slice(0,10)}</option>)}</select>{validEpisode && <Link to={chartGuideTarget("episode-process", validEpisode.episodeId)!}>{c.open}<ArrowUpRight size={14}/></Link>}</div>
      <div className="agent-chat__layout">{scope ? <ChatSession key={chatScopeKey(scope)} scope={scope} candidates={candidates} /> : <section className="agent-chat__empty"><p>{c.unavailableEpisode}</p><button onClick={() => navigate("/ask")}>{c.account}</button></section>}
        <details className="agent-chat__guide-disclosure"><summary><ChartNoAxesCombined size={17}/>{c.guide}<ChevronDown size={15}/></summary><aside className="agent-chat__guides"><p>{c.guideHint}</p>{validEpisode ? <Link to={chartGuideTarget("episode-process",validEpisode.episodeId)!}>{c.guideEpisode}<ArrowUpRight size={15} /></Link> : <label>{c.guideEpisode}<select aria-label={c.choose} value="" onChange={event => { const item = candidates.find(candidate => candidate.episodeId === event.target.value); const target = item && chartGuideTarget("episode-process", item.episodeId); if (target) navigate(target); }}><option value="" disabled>{c.choose}</option>{candidates.map(item => <option key={item.episodeId} value={item.episodeId}>{t(item.instrumentName)} · {item.openedAt.slice(0,10)}</option>)}</select></label>}<Link to={chartGuideTarget("pretrade-allocation")!}>{c.guideAllocation}<ArrowUpRight size={15}/></Link><Link to={chartGuideTarget("same-stock")!}>{c.guideCompare}<ArrowUpRight size={15}/></Link><p className="agent-chat__scope-note">{c.scopeHint}</p></aside></details>
      </div>
    </>}
  </div>;
}
