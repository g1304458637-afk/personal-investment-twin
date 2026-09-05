/** Presentation-only projection. No replay, return, cost, or risk calculation. */
export interface CompareDecision { id: string; at: string; kind: string; quantity: number; price: number; before: number; after: number; costBefore: number | null; costAfter: number | null }
export interface CompareSide { subjectId: string; episodeId: string; symbol: string; currency: string; tier: string; start: string; end: string; kind: string; pnl: number; returnValue: number | null; entryFees: number; exitFees: number; decisions: CompareDecision[]; shape: { at: string; value: number; quantity: number; cost: number | null; decisionId: string | null }[] }
export interface CompareView { id: string; status: string; reasons: string[]; method: string; version: string; a: CompareSide; b: CompareSide; start: string | null; end: string | null; prices: { at: string; value: number }[]; differences: { id: string; dimension: string; a: number; b: number; start: string; end: string; aRefs: string[]; bRefs: string[]; refs: string[] }[]; limitations: string[] }
type Obj = Record<string, unknown>;
function object(v: unknown): Obj { if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("Invalid comparison object"); return v as Obj; }
function text(v: unknown): string { if (typeof v !== "string" || !v.trim()) throw new Error("Missing comparison text"); return v; }
function number(v: unknown): number { if (typeof v !== "number" || !Number.isFinite(v)) throw new Error("Invalid comparison number"); return v; }
function optional(v: unknown): number | null { return v === null ? null : number(v); }
function list(v: unknown): unknown[] { if (!Array.isArray(v)) throw new Error("Missing comparison list"); return v; }
function strings(v: unknown): string[] { return list(v).map(text); }
function date(v: unknown): string { const s = text(v); if (!Number.isFinite(Date.parse(s))) throw new Error("Invalid comparison date"); return s; }
function side(raw: unknown, rawShape: unknown, asOf: string): CompareSide {
  const f = object(raw), e = object(f.episode), inst = object(f.instrument), result = object(object(f.outcome).actual_result);
  return { subjectId: text(e.subject_id), episodeId: text(e.episode_id), symbol: text(inst.local_symbol), currency: text(inst.currency), tier: text(e.data_tier), start: date(e.opened_at), end: e.closed_at === null ? asOf : date(e.closed_at), kind: text(result.result_kind), pnl: number(result.pnl), returnValue: optional(result.return_value), entryFees: number(result.recorded_entry_fees), exitFees: number(result.recorded_exit_fees),
    decisions: list(f.decisions).map((raw) => { const d = object(raw), before = object(d.before), after = object(d.after); return { id: text(d.decision_event_id), at: date(d.event_time), kind: text(d.event_type), quantity: number(d.executed_quantity), price: number(d.execution_price), before: number(before.quantity), after: number(after.quantity), costBefore: optional(before.average_cost), costAfter: optional(after.average_cost) }; }),
    shape: list(rawShape).map((raw) => { const p = object(raw); return { at: date(p.as_of), value: number(p.normalized_quantity), quantity: number(p.quantity), cost: optional(p.average_cost), decisionId: p.decision_ref === null ? null : text(p.decision_ref) }; }),
  };
}
export function adaptSameStock(raw: unknown): CompareView {
  const r = object(raw), asOf = date(r.as_of);
  const status = text(r.status);
  if (!["comparable", "partially_comparable", "unavailable"].includes(status)) throw new Error("Invalid comparison status");
  return { id: text(r.comparison_id), status, reasons: strings(r.reasons), method: text(r.method_id), version: text(r.method_version), a: side(r.a, r.a_position_shape, asOf), b: side(r.b, r.b_position_shape, asOf), start: r.common_start === null ? null : date(r.common_start), end: r.common_end === null ? null : date(r.common_end),
    prices: status === "unavailable" ? [] : list(r.market_observations).map((raw) => { const p = object(raw); return { at: date(p.observed_at), value: number(p.price) }; }),
    differences: status === "unavailable" ? [] : list(r.differences).map((raw) => { const f = object(raw); return { id: text(f.fact_id), dimension: text(f.dimension), a: number(f.a_value), b: number(f.b_value), start: date(f.window_start), end: date(f.window_end), aRefs: strings(f.a_decision_refs), bRefs: strings(f.b_decision_refs), refs: strings(f.fact_refs) }; }), limitations: strings(r.limitations) };
}

export function comparisonHighlight(view: CompareView, id: string | null) {
  const f = view.differences.find((x) => x.id === id);
  return f ? { start: f.start, end: f.end, aRefs: f.aRefs, bRefs: f.bRefs } : null;
}

/** Visual offsets only; same-time execution timestamps and ordering stay exact. */
export function executionLaneOffset(decisions: CompareDecision[], index: number): number {
  const peers = decisions.map((d, i) => ({ d, i })).filter(({ d }) => d.at === decisions[index].at);
  return peers.length <= 1 ? 0 : -12 + 24 * peers.findIndex(({ i }) => i === index) / (peers.length - 1);
}
