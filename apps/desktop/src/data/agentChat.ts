import type { ReviewContextView, ReviewInference, ReviewScope } from "./decisionReview";
import { projectReviewAnswer } from "./reviewAnswer.ts";
import { isChartGuideId } from "./chartGuide.ts";
import { validatedAnalysisCards, type AgentAnalysisCard } from "./agentAnalysisCards.ts";

export interface AccountChatScope { scope_kind: "account"; subject_id: string; account_id: string; data_mode: "real_user" | "synthetic_showcase" }
export interface EpisodeChatScope { scope_kind: "episode"; subject_id: string; account_id: string; episode_id: string; data_mode: "real_user" | "synthetic_showcase" }
export type ConversationScope = AccountChatScope | EpisodeChatScope;
/** ReviewScope is retained only for the legacy Episode review API. */
export type ChatScope = ReviewScope | ConversationScope;
type LocalText = { zh: string; en: string };
export interface AccountFinding { id: string; title: LocalText; body: LocalText; episode_id?: string | null }
export interface AccountChatContext { version: "account_review_context_v1"; scope: ConversationScope; as_of: string; data_tier: string; source_fingerprint: string; finding_options: AccountFinding[]; conversation_version?: string; record_refs?: string[]; episode_ids?: string[]; episode_display_ids?: Record<string, string>; conversation_turns?: ChatTurn[]; session_only?: boolean; research?: { quotes?: { available: boolean } } }
export interface ConversationAnswer { version: "account_conversation_answer_v2"; paragraphs: {kind: "fact" | "concept" | "interpretation"; text: LocalText; refs: string[]}[]; guides: {guide_id: string; episode_id: string | null; label: LocalText}[] }
export interface AccountChatInference { inference_id: string; scope: ConversationScope; source_fingerprint: string; invalidated: boolean; read_refs?: string[]; analysis_read_refs?: string[]; public_read_refs?: string[]; research_read_refs?: string[]; public_sources?: PublicSource[]; analysis_cards?: AgentAnalysisCard[]; verification?: string; answer: { version: "account_review_answer_v1"; summary: LocalText; findings: AccountFinding[]; guide_ids: string[] } | ConversationAnswer }
export interface PublicSource { title?: string | null; url?: string | null; site_name?: string | null; published_at?: string | null; retrieved_at?: string | null; provider?: string; adjust?: string }
export type ChatContext = (ReviewContextView & {request_scope?: ChatScope; source_fingerprint?: string; note_fingerprint?: string}) | AccountChatContext;
export type ChatInference = ReviewInference | AccountChatInference;
export interface ChatTurn { id: string; question: string; result: ChatInference | null; status: "running" | "complete" | "failed" | "stopped"; reason?: string; phase?: string; diagnosticId?: string }
export interface ChatApi {
  start(scope: ChatScope, question: string, previousId?: string): Promise<{ job_id: string }>;
  poll(scope: ChatScope, jobId: string): Promise<{ status: "running" | "complete" | "failed" | "stale"; result: ChatInference | null; reason?: string; phase?: string; diagnostic?: {code?: string; diagnostic_id?: string} }>;
  cancel?(scope: ChatScope, jobId: string): Promise<unknown>;
}
export const isConversationScope = (scope: ChatScope): scope is ConversationScope =>
  "scope_kind" in scope && (scope.scope_kind === "account" || scope.scope_kind === "episode");
export const isAccountScope = (scope: ChatScope): scope is AccountChatScope => isConversationScope(scope) && scope.scope_kind === "account";
export function chatScopeKey(scope: ChatScope) {
  if (isConversationScope(scope)) return JSON.stringify([
    "conversation", scope.scope_kind, scope.data_mode, scope.subject_id, scope.account_id,
    scope.scope_kind === "episode" ? scope.episode_id : null,
  ]);
  return JSON.stringify(["legacy_episode", scope.data_mode ?? "real_user", scope.subject_id, scope.account_id,
    scope.episode_id, scope.share_id ?? null, scope.compare_pair ?? false, scope.pair_side ?? "A"]);
}
export function contextMatchesScope(context: ChatContext, scope: ChatScope): boolean {
  if (context.scope.subject_id !== scope.subject_id || context.scope.account_id !== scope.account_id) return false;
  if (isConversationScope(scope)) return "version" in context && context.version === "account_review_context_v1"
    && isConversationScope(context.scope) && chatScopeKey(context.scope) === chatScopeKey(scope);
  if ("version" in context || !context.request_scope || chatScopeKey(context.request_scope) !== chatScopeKey(scope)) return false;
  return context.scope.episode_id === scope.episode_id || (context.identity_mapping?.display_episode_id === scope.episode_id
    && context.identity_mapping.canonical_episode_id === context.scope.episode_id);
}
export function projectAccountAnswer(result: ChatInference, context: ChatContext, locale: string) {
  if (!("version" in context) || result.invalidated
    || !result.scope || !isConversationScope(result.scope) || !isConversationScope(context.scope)
    || chatScopeKey(result.scope) !== chatScopeKey(context.scope)
    || !("source_fingerprint" in result) || !context.source_fingerprint || result.source_fingerprint !== context.source_fingerprint) return null;
  const answer = result.answer;
  const key = locale === "zh-CN" ? "zh" : "en";
  if (answer?.version === "account_conversation_answer_v2") {
    const stamped = result as AccountChatInference;
    const localText = (value: LocalText) => typeof value?.zh === "string" && !!value.zh.trim() && value.zh.length <= 1800
      && typeof value.en === "string" && !!value.en.trim() && value.en.length <= 2400;
    if ((stamped.analysis_read_refs !== undefined && !Array.isArray(stamped.analysis_read_refs))
      || (stamped.read_refs !== undefined && !Array.isArray(stamped.read_refs))
      || (stamped.public_read_refs !== undefined && !Array.isArray(stamped.public_read_refs))
      || (stamped.research_read_refs !== undefined && !Array.isArray(stamped.research_read_refs))) return null;
    const allReadRefs = stamped.read_refs || [];
    const analysisRefs = stamped.analysis_read_refs || [];
    const publicRefs = stamped.public_read_refs || [];
    const researchRefs = stamped.research_read_refs || [];
    const categorizedRefs = [...analysisRefs, ...publicRefs, ...researchRefs];
    const contextRefs = Array.isArray(context.record_refs) ? context.record_refs : [];
    const readSet = new Set(allReadRefs);
    // The runtime receipt ledger is authoritative. Owned-tool analysis records are
    // created during a run, so they cannot be predeclared in context.record_refs;
    // they must instead be both categorized and present in the audited read ledger.
    const allowedRefs = new Set([...contextRefs, ...categorizedRefs]);
    if (context.conversation_version !== answer.version || stamped.verification !== "receipts_and_grounding_review_v1"
      || !Array.isArray(stamped.read_refs) || !stamped.read_refs.length
      || !Array.isArray(context.record_refs) || !contextRefs.every(ref => typeof ref === "string")
      || !allReadRefs.length || !allReadRefs.every(ref => typeof ref === "string" && allowedRefs.has(ref))
      || !categorizedRefs.every(ref => typeof ref === "string" && readSet.has(ref))
      || !Array.isArray(answer.paragraphs) || !answer.paragraphs.length || answer.paragraphs.length > 5
      || !Array.isArray(answer.guides) || answer.guides.length > 3) return null;
    if (answer.paragraphs.some(p => !["fact", "concept", "interpretation"].includes(p.kind) || !localText(p.text)
      || !Array.isArray(p.refs) || !p.refs.length || p.refs.length > 8 || new Set(p.refs).size !== p.refs.length
      || !p.refs.every(ref => typeof ref === "string" && readSet.has(ref)))) return null;
    const seen = new Set<string>();
    for (const guide of answer.guides) {
      const id = JSON.stringify([guide.guide_id, guide.episode_id]);
      if (!isChartGuideId(guide.guide_id) || !localText(guide.label) || seen.has(id)
        || (guide.guide_id === "episode-process" ? !context.episode_ids?.includes(guide.episode_id ?? "") : guide.episode_id !== null)) return null;
      seen.add(id);
    }
    return { summary: answer.paragraphs[0].text[key], guideIds: [] as string[],
      cards: validatedAnalysisCards(stamped.analysis_cards, { read: allReadRefs, cited: answer.paragraphs.flatMap(p => p.refs), analysis: analysisRefs, public: publicRefs, synthetic: context.scope.data_mode === "synthetic_showcase" }),
      findings: answer.paragraphs.slice(1).map((p, i) => ({id:`paragraph-${i}`, title:"", body:p.text[key], episodeId:null as string | null | undefined})),
      actions: answer.guides.map(g => ({id:g.guide_id, episodeId:g.episode_id, label:g.label[key]})),
      sources: Array.isArray(stamped.public_sources) ? stamped.public_sources.filter(item =>
        typeof item?.title === "string" && item.title.trim() && (!item.url || /^https?:\/\//.test(item.url))).slice(0, 6) : [] };
  }
  if (answer?.version !== "account_review_answer_v1") return null;
  if (typeof answer.summary?.[key] !== "string" || !answer.summary[key] || !Array.isArray(answer.findings) || !answer.findings.length || answer.findings.length > 3
    || !Array.isArray(answer.guide_ids) || !answer.guide_ids.every(isChartGuideId) || new Set(answer.guide_ids).size !== answer.guide_ids.length) return null;
  const seen = new Set<string>();
  for (const finding of answer.findings) {
    const registered = context.finding_options.find(item => item.id === finding.id);
    if (!registered || seen.has(finding.id) || registered.episode_id !== finding.episode_id
      || registered.title.zh !== finding.title?.zh || registered.title.en !== finding.title?.en
      || registered.body.zh !== finding.body?.zh || registered.body.en !== finding.body?.en) return null;
    seen.add(finding.id);
  }
  return { summary: answer.summary[key], guideIds: answer.guide_ids, cards: [] as AgentAnalysisCard[], findings: answer.findings.map(item => ({ id:item.id, title:item.title[key], body:item.body[key], episodeId:item.episode_id })), actions: [] as {id:string; episodeId:string | null; label:string}[], sources: [] as PublicSource[] };
}
export function verifiedChatResult(result: ChatInference, context: ChatContext): boolean {
  if ("version" in context) return !!projectAccountAnswer(result, context, "zh-CN") && !!projectAccountAnswer(result, context, "en-US");
  const stamped = result as ReviewInference & {source_fingerprint?: string; note_fingerprint?: string; conversation?: {request_scope?: ChatScope}};
  return !!context.request_scope && !!stamped.conversation?.request_scope
    && chatScopeKey(context.request_scope) === chatScopeKey(stamped.conversation.request_scope)
    && !!context.source_fingerprint && context.source_fingerprint === stamped.source_fingerprint
    && !!context.note_fingerprint && context.note_fingerprint === stamped.note_fingerprint
    && !!projectReviewAnswer(result as ReviewInference, context, "zh-CN") && !!projectReviewAnswer(result as ReviewInference, context, "en-US");
}
const diagnosticCodes = new Set([
  "account_answer_number_not_in_sources", "account_answer_operation_count_mismatch",
  "account_answer_unread_reference", "account_grounding_failed", "account_grounding_incomplete_coverage",
  "account_model_request_failed", "account_model_timeout", "account_review_timeout",
  "account_model_response_incomplete", "account_research_incomplete",
  "account_conversation_schema_failed", "account_conversation_invalid_output",
  "account_conversation_context_over_limit", "account_conversation_unavailable",
  "account_fact_source_required", "account_concept_source_required",
  "account_completed_receipts_required", "account_incomplete_tool_receipt",
]);
export class ChatTurnError extends Error {
  diagnosticId?: string;
  constructor(reason: string, diagnostic?: {code?: string; diagnostic_id?: string}) {
    super(diagnostic?.code && diagnosticCodes.has(diagnostic.code) ? diagnostic.code : reason);
    this.diagnosticId = typeof diagnostic?.diagnostic_id === "string" && /^[a-f0-9]{12}$/.test(diagnostic.diagnostic_id)
      ? diagnostic.diagnostic_id : undefined;
  }
}
const stopError = () => new Error("chat_stopped");
function wait(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(stopError()); return; }
    const stop = () => { clearTimeout(timer); reject(stopError()); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, 1000);
    signal.addEventListener("abort", stop, {once:true});
  });
}
export async function runChatTurn(api: ChatApi, scope: ChatScope, context: ChatContext, question: string, previousId: string | undefined,
  signal: AbortSignal, pause: (signal: AbortSignal) => Promise<void> = wait,
  onProgress?: (phase: string) => void): Promise<ChatInference> {
  const check = () => { if (signal.aborted) throw stopError(); };
  check();
  if (!contextMatchesScope(context, scope) || !question.trim() || question.length > 2000) throw new Error("chat_scope_or_question_invalid");
  const job = await api.start(scope, question.trim(), previousId);
  const cancel = () => { void api.cancel?.(scope, job.job_id).catch(() => {}); };
  signal.addEventListener("abort", cancel, {once:true});
  try {
  if (signal.aborted) cancel();
  check();
  for (let i = 0; i < 170; i++) {
    const reply = await api.poll(scope, job.job_id);
    check();
    if (reply.status === "complete") {
      if (!reply.result?.inference_id || !verifiedChatResult(reply.result, context)) throw new Error("chat_answer_not_verified");
      return reply.result;
    }
    if (reply.status !== "running") throw new ChatTurnError(reply.reason ?? "review_analysis_failed", reply.status === "failed" ? reply.diagnostic : undefined);
    if (["researching", "reading", "searching", "quoting", "writing", "checking"].includes(reply.phase ?? "")) onProgress?.(reply.phase!);
    await pause(signal); check();
  }
  cancel(); throw new Error("review_timeout");
  } finally { signal.removeEventListener("abort", cancel); }
}

/** Session-only UI history. Never localStorage, Evidence, Twin or the source ledger. */
const transcripts = new Map<string, ChatTurn[]>();
const transcriptContexts = new Map<string, ChatContext>();
/** Restore the original validation context, not a new model answer. Memory only. */
export function readChatContext(scope: ChatScope): ChatContext | null {
  const context = transcriptContexts.get(chatScopeKey(scope));
  return context && contextMatchesScope(context, scope) ? structuredClone(context) : null;
}
export function saveChatContext(scope: ChatScope, context: ChatContext) {
  if (!contextMatchesScope(context, scope)) throw new Error("chat_scope_mismatch");
  transcriptContexts.set(chatScopeKey(scope), structuredClone(context));
  if (transcriptContexts.size > 8) transcriptContexts.delete(transcriptContexts.keys().next().value!);
}
export function readChat(scope: ChatScope): ChatTurn[] { return (transcripts.get(chatScopeKey(scope)) ?? []).map(item => item.status === "running" ? {...item, status:"stopped"} : item); }
export function saveChat(scope: ChatScope, turns: ChatTurn[]) {
  const key = chatScopeKey(scope); transcripts.delete(key); transcripts.set(key, turns.slice(-20));
  if (!turns.length) transcriptContexts.delete(key);
  if (transcripts.size > 8) {
    const oldest = transcripts.keys().next().value!;
    transcripts.delete(oldest); transcriptContexts.delete(oldest);
  }
}
export function previousChatResult(turns: ChatTurn[]): string | undefined {
  const latest = [...turns].reverse().find(turn => turn.status === "complete");
  return latest?.result && !latest.result.invalidated ? latest.result.inference_id : undefined;
}

/** Only restore validated scoped snapshots. Loading history never starts a model. */
export function restoredConversationTurns(context: ChatContext): ChatTurn[] {
  if (!("version" in context) || !Array.isArray(context.conversation_turns)) return [];
  return context.conversation_turns.slice(-50).filter(turn => typeof turn.id === "string"
    && typeof turn.question === "string" && turn.question.length > 0 && turn.question.length <= 2000
    && turn.status === "complete" && turn.result && verifiedChatResult(turn.result, context))
    .map(turn => ({id: turn.id, question: turn.question, status: "complete", result: structuredClone(turn.result)}));
}
/** Backward-compatible name for callers restoring whole-account archives. */
export function restoredAccountTurns(context: ChatContext): ChatTurn[] {
  return restoredConversationTurns(context);
}
export function decisionForDisplay(id: string, context: ReviewContextView & {request_scope?: ChatScope}, scope: ReviewScope): string | null {
  if (!contextMatchesScope(context, scope) || !context.records.some(item => item.kind === "decision"
    && item.subject_id === context.scope.subject_id && item.account_id === context.scope.account_id && item.episode_id === context.scope.episode_id
    && item.value.decision_event_id === id)) return null;
  if (scope.episode_id === context.scope.episode_id) return id;
  return context.identity_mapping?.decision_display_ids[id] ?? null;
}

/** Resolve navigation only after canonical guide verification; require an owned visible target. */
export function accountGuideEpisode(context: AccountChatContext, canonicalId: string, visibleIds: string[]): string | undefined {
  if (!context.episode_ids?.includes(canonicalId)) return undefined;
  const target = context.episode_display_ids?.[canonicalId] ?? canonicalId;
  return visibleIds.includes(target) ? target : undefined;
}
