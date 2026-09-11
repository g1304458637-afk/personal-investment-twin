import type { ReviewContextView, ReviewInference, ReviewScope } from "./decisionReview.ts";

export function reviewScopeKey(scope: ReviewScope): string {
  return JSON.stringify([scope.data_mode ?? "real_user", scope.subject_id, scope.account_id,
    scope.episode_id, scope.share_id ?? null, scope.compare_pair ?? false, scope.pair_side ?? "A"]);
}
export interface ReviewSessionState {
  context: ReviewContextView | null;
  answer: ReviewInference | null;
  question: string;
  note: string;
  noteKind: string;
  loading: boolean;
  busy: boolean;
  error: string | null;
  revision: number;
}
interface Api {
  context(scope: ReviewScope): Promise<ReviewContextView>;
  start(scope: ReviewScope, question: string): Promise<{ job_id: string }>;
  poll(scope: ReviewScope, jobId: string): Promise<{status: string; result: ReviewInference | null; reason?: string}>;
}
interface Entry {
  scope: ReviewScope;
  state: ReviewSessionState;
  generation: number;
  pending?: Promise<ReviewContextView>;
  task?: Promise<void>;
  listeners: Set<() => void>;
}
const initial = (): ReviewSessionState => ({context:null, answer:null, question:"", note:"", noteKind:"reason", loading:false, busy:false, error:null, revision:0});
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

/** App-session memory, NOT page state. No keys, raw imports, or model auto-start.
 * Invalidations cancel publication of old reads/jobs, not just their UI listeners.
 * Shared records never survive the last subscriber (expiry is checked by runtime).
 */
export class ReviewSessions {
  private entries = new Map<string, Entry>();
  private api: Api;
  private pause: () => Promise<void>;
  constructor(api: Api, pause: () => Promise<void> = () => new Promise(resolve => setTimeout(resolve, 1000))) {
    this.api = api; this.pause = pause;
  }
  private entry(scope: ReviewScope): Entry {
    const key = reviewScopeKey(scope);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = {scope:{...scope}, state:initial(), generation:0, listeners:new Set()};
      this.entries.set(key, entry);
    }
    // LRU: never discard an in-flight request or a mounted consumer.
    this.entries.delete(key); this.entries.set(key, entry);
    if (this.entries.size > 16) for (const [oldKey, old] of this.entries) {
      if (this.entries.size <= 16) break;
      if (old !== entry && !old.pending && !old.task && !old.listeners.size) this.entries.delete(oldKey);
    }
    return entry;
  }
  private publish(entry: Entry, patch: Partial<ReviewSessionState>) {
    entry.state = {...entry.state, ...patch};
    entry.listeners.forEach(listener => listener());
  }
  snapshot(scope: ReviewScope) { return this.entry(scope).state; }
  subscribe(scope: ReviewScope, listener: () => void) {
    const entry = this.entry(scope); entry.listeners.add(listener);
    return () => {
      entry.listeners.delete(listener);
      if (scope.share_id && !entry.listeners.size) {
        entry.generation++; this.entries.delete(reviewScopeKey(scope));
      }
    };
  }
  edit(scope: ReviewScope, patch: Partial<Pick<ReviewSessionState, "question" | "note" | "noteKind">>) {
    this.publish(this.entry(scope), patch);
  }
  load(scope: ReviewScope): Promise<ReviewContextView> {
    const entry = this.entry(scope);
    if (entry.pending) return entry.pending;
    if (entry.state.context) return Promise.resolve(entry.state.context);
    const generation = entry.generation;
    this.publish(entry, {loading:true, error:null});
    const pending = Promise.resolve().then(() => this.api.context({...scope})).then(context => {
      if (entry.generation !== generation) throw new Error("review_context_changed");
      const identity = context.identity_mapping;
      if (context.scope.subject_id !== scope.subject_id || context.scope.account_id !== scope.account_id
        || (context.scope.episode_id !== scope.episode_id && !(identity?.display_episode_id === scope.episode_id && identity.canonical_episode_id === context.scope.episode_id))) throw new Error("chat_scope_mismatch");
      this.publish(entry, {context, answer:context.inferences.find(answer => !answer.invalidated) ?? null, loading:false});
      return context;
    }).catch(error => {
      if (entry.generation === generation) this.publish(entry, {loading:false, error:errorText(error)});
      throw error;
    }).finally(() => { if (entry.pending === pending) entry.pending = undefined; });
    entry.pending = pending;
    return pending;
  }
  /** Warm only local facts. Failure is retryable when the user opens analysis. */
  prefetch(scope: ReviewScope) { return this.load(scope).then(() => undefined, () => undefined); }
  invalidate(subject: string, account: string) {
    // Subscribers synchronously read snapshots (and touch LRU order). Iterate
    // a stable list so notifying React cannot re-enqueue the same Map entry.
    for (const entry of [...this.entries.values()]) {
      if (entry.scope.subject_id !== subject || entry.scope.account_id !== account) continue;
      entry.generation++; entry.pending = undefined; entry.task = undefined;
      this.publish(entry, {...initial(), question:entry.state.question, note:entry.state.note,
        noteKind:entry.state.noteKind, revision:entry.state.revision + 1});
    }
  }
  analyze(scope: ReviewScope, question: string, consent: boolean): Promise<void> {
    const entry = this.entry(scope);
    if (entry.task) return entry.task;
    if (!consent || !entry.state.context || entry.state.loading || !question.trim()) return Promise.resolve();
    const generation = entry.generation;
    this.publish(entry, {busy:true, error:null});
    const task = (async () => {
      try {
        const job = await this.api.start({...scope}, question);
        for (let i = 0; i < 110 && entry.generation === generation; i++) {
          const response = await this.api.poll({...scope}, job.job_id);
          if (entry.generation !== generation) return;
          if (response.status === "complete" && response.result && !response.result.invalidated) {
            this.publish(entry, {answer:response.result}); return;
          }
          if (response.status !== "running") throw new Error(response.reason ?? "review_analysis_failed");
          await this.pause();
        }
        if (entry.generation === generation) throw new Error("review_timeout");
      } catch (error) {
        if (entry.generation === generation) this.publish(entry, {error:errorText(error)});
      } finally {
        if (entry.generation === generation) this.publish(entry, {busy:false});
      }
    })().finally(() => { if (entry.task === task) entry.task = undefined; });
    entry.task = task;
    return task;
  }
}
