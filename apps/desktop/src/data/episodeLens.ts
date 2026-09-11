import type { PositionEpisodeEntryView } from "./positionEpisode.ts";

export type DecisionLensVerdict = "aligned" | "different" | "insufficient" | "not_applicable";
export interface DecisionLensCondition {
  label: string; actual: number | null; operator: string; threshold: number | null;
  passed: boolean | null; unit: "price" | "count" | "ratio";
}
export interface DecisionLensCheck {
  decision_id: string; execution_id: string; state_before_ref: string; occurred_at: string;
  market_date: string | null;
  actual: { side: "BUY" | "SELL"; quantity: number; price: number; quantity_before: number; average_cost_before: number | null };
  verdict: DecisionLensVerdict; expected_action: string; explanation: string;
  observed_through: string | null; observation_count: number;
  conditions: DecisionLensCondition[]; input_fingerprint: string; limitations: string[];
}
export interface DecisionLensMethod {
  id: string; version: string; title: string; description: string; rule: string;
  parameters: Record<string, number>; checks: DecisionLensCheck[];
}
export interface DecisionLensReport {
  schema_version: "decision_lens.v1";
  episode_id: string; subject_id: string; account_id: string; instrument_id: string;
  data_tier: "synthetic" | "authorized_beta";
  temporal_policy: "prior_daily_close_only";
  limitations: string[]; methods: DecisionLensMethod[];
}

const methodIds = new Set(["trend_ma20", "closing_breakout20", "cost_addition"]);
const verdicts = new Set(["aligned", "different", "insufficient", "not_applicable"]);
const fail = (): never => { throw new Error("lens_projection_invalid"); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown): string => typeof x === "string" && x.trim().length > 0 && x.length <= 6000 ? x : fail();
const finite = (x: unknown): number => typeof x === "number" && Number.isFinite(x) ? x : fail();
const nullableNumber = (x: unknown) => x === null ? null : finite(x);
const array = (x: unknown): unknown[] => Array.isArray(x) && x.length <= 10000 ? x : fail();
const strings = (x: unknown) => array(x).map(text);
const day = (x: unknown): string => {
  const s = text(x);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) fail();
  return s;
};

/** Validate transport, ownership and ledger correspondence. No signals are computed in the UI. */
export function adaptDecisionLensReport(raw: unknown, entry: PositionEpisodeEntryView): DecisionLensReport {
  const report = object(raw);
  const episode = entry.episode;
  if (report.schema_version !== "decision_lens.v1" || report.temporal_policy !== "prior_daily_close_only"
    || report.episode_id !== episode.episodeId || report.subject_id !== episode.subjectId
    || report.account_id !== episode.accountId || report.instrument_id !== episode.instrumentId
    || report.data_tier !== entry.instrument.dataTier) fail();
  const decisions = new Map(entry.decisions.map(d => [d.decisionId, d]));
  const seenMethods = new Set<string>();
  const methods = array(report.methods).map(value => {
    const method = object(value);
    const id = text(method.id);
    if (!methodIds.has(id) || seenMethods.has(id)) fail();
    seenMethods.add(id);
    const seenChecks = new Set<string>();
    const checks = array(method.checks).map(value => {
      const check = object(value);
      const decisionId = text(check.decision_id);
      const decision = decisions.get(decisionId);
      if (!decision || seenChecks.has(decisionId)) return fail();
      seenChecks.add(decisionId);
      const actual = object(check.actual);
      if (check.execution_id !== decision.executionId || check.state_before_ref !== decision.stateBeforeRef
        || check.occurred_at !== decision.occurredAt || actual.side !== decision.side
        || actual.quantity !== decision.executedQuantity || actual.price !== decision.executionPrice
        || actual.quantity_before !== decision.stateBefore.quantity || actual.average_cost_before !== decision.stateBefore.averageCost) fail();
      const marketDate = check.market_date === null ? null : day(check.market_date);
      const observedThrough = check.observed_through === null ? null : day(check.observed_through);
      if (observedThrough !== null && (marketDate === null || observedThrough >= marketDate)) fail();
      const observationCount = finite(check.observation_count);
      if (!Number.isInteger(observationCount) || observationCount < 0) fail();
      const verdict = text(check.verdict);
      if (!verdicts.has(verdict)) fail();
      if (marketDate === null && id !== "cost_addition" && verdict !== "insufficient") fail();
      const fingerprint = text(check.input_fingerprint);
      if (!/^[a-f0-9]{64}$/.test(fingerprint)) fail();
      const conditions = array(check.conditions).map(value => {
        const c = object(value);
        if (![true, false, null].includes(c.passed as boolean | null) || !["price", "count", "ratio"].includes(String(c.unit))) fail();
        return {label: text(c.label), actual: nullableNumber(c.actual), operator: text(c.operator), threshold: nullableNumber(c.threshold), passed: c.passed as boolean | null, unit: c.unit as DecisionLensCondition["unit"]};
      });
      return {
        decision_id: decisionId, execution_id: decision.executionId, state_before_ref: decision.stateBeforeRef,
        occurred_at: decision.occurredAt, market_date: marketDate,
        actual: {side: decision.side, quantity: finite(actual.quantity), price: finite(actual.price), quantity_before: finite(actual.quantity_before), average_cost_before: nullableNumber(actual.average_cost_before)},
        verdict: verdict as DecisionLensVerdict, expected_action: text(check.expected_action), explanation: text(check.explanation),
        observed_through: observedThrough, observation_count: observationCount, input_fingerprint: fingerprint,
        conditions, limitations: strings(check.limitations),
      };
    });
    if (seenChecks.size !== decisions.size) fail();
    // Present in ledger order even if a transport arrives out of order.
    const order = new Map(entry.decisions.map((d, i) => [d.decisionId, i]));
    checks.sort((a, b) => order.get(a.decision_id)! - order.get(b.decision_id)!);
    const parameters = Object.fromEntries(Object.entries(object(method.parameters)).map(([key, value]) => [text(key), finite(value)]));
    return {id, version: text(method.version), title: text(method.title), description: text(method.description), rule: text(method.rule), parameters, checks};
  });
  if (methods.length !== methodIds.size) fail();
  return {schema_version: "decision_lens.v1", episode_id: episode.episodeId, subject_id: episode.subjectId,
    account_id: text(episode.accountId), instrument_id: episode.instrumentId, data_tier: entry.instrument.dataTier,
    temporal_policy: "prior_daily_close_only", limitations: strings(report.limitations), methods};
}

export function selectLensState(report: DecisionLensReport, requestedMethod: string | null, requestedDecision: string | null) {
  const method = report.methods.find(m => m.id === requestedMethod) ?? report.methods[0];
  const check = method.checks.find(c => c.decision_id === requestedDecision)
    ?? method.checks.find(c => c.verdict === "different")
    ?? method.checks.find(c => c.verdict === "aligned") ?? method.checks[0] ?? null;
  return {method, check};
}

/** Exchange calendar dates are dates, not instants in the viewer's timezone. */
export function formatLensDate(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "short", day: "numeric",
    ...(/^\d{4}-\d{2}-\d{2}$/.test(value) ? {timeZone: "UTC"} : {}),
  }).format(date);
}
