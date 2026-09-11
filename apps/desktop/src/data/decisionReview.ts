/** Review projection only. Numbers are copied from deterministic records. */
import type { ReviewAnswerV2 } from "./reviewAnswer";
export interface ReviewInference { answer?: ReviewAnswerV2; scope?: ReviewScope }
export interface ReviewScope { subject_id: string; account_id: string; episode_id: string; data_mode?: "real_user" | "synthetic_pair" | "synthetic_episode" | "synthetic_showcase"; pair_side?: "A" | "B"; compare_pair?: boolean; share_id?: string }
export interface ReviewFact { ref: string; kind: string; title: string; subject_id: string; account_id: string; episode_id: string; currency: string; as_of: string; method_id: string; method_version: string; availability: string; underlying_refs: string[]; value: Record<string, unknown> }
export interface ReviewInference { inference_id: string; generated_at: string; invalidated: boolean; replaced_by: string | null; provider: string; model: string; facts: ReviewFact[]; historical_comparisons: ReviewFact[]; possible_explanations: { kind: string; claim: string; supporting_evidence_refs: string[]; contradictory_evidence_refs: string[]; alternative_explanations: string[]; missing_information: string[] }[]; question_kind: string; executed_tools: string[] }
export interface ReviewContextView { scope: ReviewScope; as_of: string; data_tier: string; records: ReviewFact[]; comparison: unknown | null; inferences: ReviewInference[]; identity_mapping?: { version: string; display_episode_id: string; canonical_episode_id: string; decision_display_ids: Record<string, string> } | null }
export interface ReviewRow { label: string; value: string | number | null; format?: "money" | "percent"; decisionId?: string }
export function object(v: unknown): Record<string, unknown> { return v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {}; }
function value(v: unknown): string | number | null { return typeof v === "number" && Number.isFinite(v) || typeof v === "string" ? v as string | number : null; }
export function reviewRows(f: ReviewFact): ReviewRow[] {
  const v = object(f.value), result = object(v.result);
  if (f.kind === "episode") return [
    { label: result.result_kind === "marked" ? "Current marked result" : "Final realized result", value: value(result.pnl), format: "money" },
    { label: "Position return", value: value(result.return_value), format: "percent" },
    { label: "Recorded entry fees", value: value(result.recorded_entry_fees), format: "money" },
    { label: "Recorded exit fees", value: value(result.recorded_exit_fees), format: "money" },
  ];
  if (f.kind === "decision") return [
    { label: "Recorded decision", value: value(v.event_type), decisionId: String(v.decision_event_id) },
    { label: "Time", value: value(v.event_time) }, { label: "Executed quantity", value: value(v.executed_quantity) },
    { label: "Execution price", value: value(v.execution_price), format: "money" },
    { label: "Quantity before", value: value(object(v.before).quantity) }, { label: "Quantity after", value: value(object(v.after).quantity) },
    { label: "Average cost before", value: value(object(v.before).average_cost), format: "money" },
    { label: "Average cost after", value: value(object(v.after).average_cost), format: "money" },
  ];
  if (f.kind === "historical_comparison") return [
    { label: "Changed action", value: value(object(v.intervention).changed_action) },
    { label: "Held constant", value: Array.isArray(v.held_constant) ? v.held_constant.join(" · ") : null },
    { label: "Evaluation end", value: value(v.evaluation_end) },
    { label: "Valuation observation", value: value(object(v.actual_result).valuation_at) },
    { label: "Actual historical result", value: value(object(v.actual_result).pnl), format: "money" },
    { label: "Fixed-assumption result", value: value(object(v.counterfactual_result).pnl), format: "money" },
    { label: "Fixed-assumption minus actual result", value: value(object(v.comparison).pnl_difference), format: "money" },
    { label: "Availability / reason", value: value(v.infeasible_reason) ?? f.availability },
  ];
  if (f.kind === "user_note") return [{ label: "Retrospective user note", value: value(v.text) }, { label: "Recorded at", value: value(v.recorded_at) }];
  if (f.kind === "market") {
    const before = object(v.pre_entry_context), drawdown = object(v.daily_price_peak_drawdown);
    return [
      { label: "Recorded pre-entry market return", value: value(before.price_return), format: "percent" },
      { label: "Pre-entry observation count", value: value(before.valid_observation_count) },
      { label: "Recorded peak date", value: value(object(drawdown.peak_observation).observed_at) },
      { label: "Recorded trough date", value: value(object(drawdown.trough_observation).observed_at) },
      { label: "Recorded daily peak drawdown", value: value(drawdown.daily_price_peak_drawdown), format: "percent" },
      { label: "Quantity at recorded trough", value: value(drawdown.quantity_at_trough) },
      { label: "Availability / reason", value: value(drawdown.quantity_status_reason) ?? value(drawdown.quantity_at_trough_status) },
    ];
  }
  if (f.kind === "phase") return [
    { label: "Recorded decisions", value: value(v.phase_type) }, { label: "From", value: value(v.started_at) },
    { label: "To", value: value(v.ended_at) }, { label: "Quantity before", value: value(v.quantity_before) },
    { label: "Quantity after", value: value(v.quantity_after) },
  ];
  return [{ label: "Availability / reason", value: f.availability }];
}
export function selfHistoryRows(f: ReviewFact): { metric: string; current: number | null; median: number | null; n: number | null; status: string; reason: string | null; start: string | null; end: string | null }[] {
  const summary = object(object(f.value).summary);
  return (Array.isArray(summary.metrics) ? summary.metrics : []).map((raw) => {
    const m = object(raw), w = (Array.isArray(m.windows) ? m.windows : []).map(object).find((x) => x.window === summary.default_window) ?? {};
    const number = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? v : null;
    return { metric: String(m.metric_id), current: number(w.current_value), median: number(w.median), n: number(w.valid_n), status: String(w.status ?? "insufficient_self_history"), reason: typeof w.insufficient_reason === "string" ? w.insufficient_reason : null, start: typeof w.observation_start === "string" ? w.observation_start : null, end: typeof w.observation_end === "string" ? w.observation_end : null };
  });
}
/** Request generations also invalidate results when notes/target change. */
export class ReviewRequestGuard {
  private generation = 0;
  next() { return ++this.generation; }
  accepts(ticket: number) { return ticket === this.generation; }
}
