/** Presentation-only projection. All returns, weights and behavior values are Python outputs. */
export type PeriodKey = "earlier" | "recent" | "full";
export type AllocationSlice = { id: string; weight: number; directWeight?: number; indirectWeight?: number; paths?: string[][] };
export type ResearchDisclosure = { fundId: string; effectiveDate: string; publishedDate: string; observedDate: string; sourceIds: string[] };
export type ResearchOperation = { id: string; episodeId: string; date: string; symbol: string; kind: string; quantity: number; price: number; beforeQuantity: number; afterQuantity: number; beforeCost: number | null; afterCost: number | null; fee: number };
export type ResearchPeriod = {
  startDate: string; endDate: string; sourceRef: string;
  performance: { points: { date: string; nav: number; value: number; drawdown: number }[]; periodReturn: number; maxDrawdown: number; peakDate: string | null; troughDate: string | null; recoveryDate: string | null; volatility: number | null; sharpe: number | null; observationCount: number };
  behavior: { turnover: number | null; fees: number; actionCount: number; hhi: number | null; top1: number | null; top3: number | null; observationCount: number; pgr: number | null; plr: number | null; pgrMinusPlr: number | null; dispositionCount: number; lossRate: number | null; lossEvents: number; eligibleAdds: number };
  allocation: { date: string; totalValue: number; cash: number; direct: AllocationSlice[]; underlying: AllocationSlice[]; sectors: AllocationSlice[]; sectorDenominator: number; sectorUnclassified: number; disclosures: ResearchDisclosure[] };
  operations: ResearchOperation[];
  benchmark: { periodReturn: number; points: { date: string; nav: number }[] };
};
export type ResearchAccount = { id: string; periods: Record<PeriodKey, ResearchPeriod> };
export type ResearchDifference = { id: string; left: number | null; right: number | null; change: number | null; unit: string };
export type ResearchPair = { id: string; differences: ResearchDifference[]; sharedUnderlying: { id: string; leftWeight: number; rightWeight: number; overlapWeight: number }[] };
export type ComparisonResearch = { dataTier: "synthetic"; asOf: string; currency: string; defaultSubject: string; names: Record<string, { zh: string; en: string }>; accounts: ResearchAccount[]; comparisons: { self: ResearchPair; professional: Record<string, Record<PeriodKey, ResearchPair>> } };

type Obj = Record<string, unknown>;
function obj(v: unknown): Obj { if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("Invalid comparison object"); return v as Obj; }
function str(v: unknown): string { if (typeof v !== "string" || !v) throw new Error("Invalid comparison string"); return v; }
function num(v: unknown): number { if (typeof v !== "number" || !Number.isFinite(v)) throw new Error("Invalid comparison number"); return v; }
function nullable(v: unknown): number | null { return v == null ? null : num(v); }
function rows(v: unknown): unknown[] { if (!Array.isArray(v)) throw new Error("Invalid comparison list"); return v; }
function date(v: unknown): string { const s = str(v); if (!/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(s) || !Number.isFinite(Date.parse(s))) throw new Error("Invalid comparison date"); return s.slice(0, 10); }
const maybeDate = (v: unknown) => v == null ? null : date(v);
function weight(v: unknown): number { const n = num(v); if (n < 0 || n > 1 + 1e-8) throw new Error("Invalid comparison weight"); return n; }
function slices(v: unknown): AllocationSlice[] { return rows(v).map(item => { const r = obj(item); return { id: str(r.asset_id), weight: weight(r.weight) }; }); }
function fullAllocation(s: AllocationSlice[]) { if (Math.abs(s.reduce((n, x) => n + x.weight, 0) - 1) > 1e-7) throw new Error("Incomplete account allocation"); }

function period(v: unknown, account: string, asOf: string): ResearchPeriod {
  const p = obj(v), f = obj(p.performance), b = obj(p.behavior), a = obj(p.allocation), l = obj(a.lookthrough), s = obj(l.sector_breakdown), d = obj(b.disposition), loss = obj(b.loss_averaging), benchmark = obj(p.benchmark);
  const startDate = date(p.start_date), endDate = date(p.end_date);
  if (startDate >= endDate || endDate > asOf || f.account_id !== account || f.data_tier !== "synthetic" || f.base_currency !== "CNY" || f.method_id !== "account_fixed_cash_twr_empyrical_v1" || f.method_version !== "1.0.0") throw new Error("Comparison scope / method mismatch");
  if (date(f.period_start) !== startDate || date(f.period_end) !== endDate || date(b.start_date) !== startDate || date(b.end_date) !== endDate || date(a.date) !== endDate || date(l.as_of) !== endDate) throw new Error("Comparison period mismatch");
  const points = rows(f.points).map(item => { const r = obj(item); return { date: date(r.observed_at), nav: num(r.cumulative_nav), value: num(r.account_value), drawdown: num(r.drawdown) }; });
  if (points.length < 2 || points[0].date !== startDate || points.at(-1)?.date !== endDate || points.some((p, i) => p.nav <= 0 || p.value <= 0 || p.drawdown > 1e-8 || (i > 0 && p.date <= points[i - 1].date))) throw new Error("Invalid comparison history");
  const direct = slices(a.direct), underlying = rows(l.exposures).map(item => { const r = obj(item); return { id: str(r.asset_id), weight: weight(r.weight), directWeight: weight(r.direct_weight), indirectWeight: weight(r.indirect_weight), paths: rows(r.paths).map(p => rows(obj(p).asset_path).map(str)) }; });
  fullAllocation(direct); fullAllocation(underlying);
  const availableDate = (v: unknown) => { const d = date(v); if (d > endDate) throw new Error("Future comparison disclosure"); return d; };
  for (const item of rows(l.exposures)) { const c = obj(item).classification; if (c) for (const key of ["effective_at", "published_at", "observed_at"]) availableDate(obj(c)[key]); }
  const disclosures = rows(l.selected_disclosures).map(item => { const r = obj(item); return { fundId: str(r.fund_id), effectiveDate: availableDate(r.effective_at), publishedDate: availableDate(r.published_at), observedDate: availableDate(r.observed_at), sourceIds: rows(r.source_ids).map(str) }; });
  const operations = rows(p.operations).map(item => { const r = obj(item); const day = date(r.date); if (day <= startDate || day > endDate) throw new Error("Operation outside comparison period"); return { id: str(r.decision_id), episodeId: str(r.episode_id), date: str(r.date), symbol: str(r.symbol), kind: str(r.kind), quantity: num(r.quantity), price: num(r.execution_price), beforeQuantity: num(r.before_quantity), afterQuantity: num(r.after_quantity), beforeCost: nullable(r.before_cost), afterCost: nullable(r.after_cost), fee: num(r.fee) }; });
  const bp = rows(benchmark.points).map(item => { const r = obj(item); return { date: date(r.date), nav: num(r.nav) }; });
  if (benchmark.data_tier !== "synthetic" || bp.length !== points.length || bp.some((p, i) => p.date !== points[i].date)) throw new Error("Benchmark observation mismatch");
  return {
    startDate, endDate, sourceRef: str(p.source_ref),
    performance: { points, periodReturn: num(f.period_return), maxDrawdown: num(f.max_drawdown_magnitude), peakDate: maybeDate(f.max_drawdown_peak_at), troughDate: maybeDate(f.max_drawdown_trough_at), recoveryDate: maybeDate(f.max_drawdown_recovered_at), volatility: nullable(f.annualized_volatility), sharpe: nullable(f.sharpe_ratio), observationCount: num(f.return_observation_count) },
    behavior: { turnover: nullable(b.mean_daily_turnover), fees: num(b.recorded_fee_total), actionCount: num(b.action_count), hhi: nullable(b.hhi_end), top1: nullable(b.top1_weight), top3: nullable(b.top3_weight), observationCount: num(b.observation_count), pgr: nullable(d.pgr), plr: nullable(d.plr), pgrMinusPlr: nullable(d.disposition_effect), dispositionCount: num(d.observation_count), lossRate: nullable(loss.event_rate), lossEvents: num(loss.loss_averaging_events), eligibleAdds: num(loss.eligible_add_events) },
    allocation: { date: date(a.date), totalValue: num(a.portfolio_value), cash: num(a.cash), direct, underlying, sectors: rows(s.components).map(item => { const r = obj(item); return { id: str(r.label), weight: weight(r.weight) }; }), sectorDenominator: weight(s.denominator_weight), sectorUnclassified: weight(s.unclassified_weight), disclosures },
    operations, benchmark: { periodReturn: num(benchmark.period_return), points: bp },
  };
}

function pair(v: unknown, kind: string, left: ResearchAccount, right: ResearchAccount, leftKey: PeriodKey, rightKey: PeriodKey): ResearchPair {
  const r = obj(v), a = left.periods[leftKey], b = right.periods[rightKey];
  if (r.method_id !== "account_period_factual_comparison_v1" || r.method_version !== "1" || r.data_tier !== "synthetic" || r.currency !== "CNY" || r.kind !== kind || r.left_account_id !== left.id || r.right_account_id !== right.id || date(r.left_period_start) !== a.startDate || date(r.left_period_end) !== a.endDate || date(r.right_period_start) !== b.startDate || date(r.right_period_end) !== b.endDate) throw new Error("Comparison pair scope mismatch");
  if (kind === "professional" && (a.startDate !== b.startDate || a.endDate !== b.endDate || a.performance.points.map(p => p.date).join() !== b.performance.points.map(p => p.date).join())) throw new Error("Comparison pair observation mismatch");
  const differences = rows(r.differences).map(item => { const d = obj(item); return { id: str(d.metric_id), left: nullable(d.left_value), right: nullable(d.right_value), change: nullable(d.right_minus_left), unit: str(d.unit) }; });
  const units: Record<string, string> = { period_return: "percentage_points", max_drawdown_magnitude: "percentage_points", mean_daily_turnover: "percentage_points", portfolio_hhi: "index", recorded_fee_total: "CNY" };
  if (differences.length !== Object.keys(units).length || new Set(differences.map(d => d.id)).size !== differences.length || differences.some(d => units[d.id] !== d.unit || ((d.left === null || d.right === null) !== (d.change === null)))) throw new Error("Invalid comparison differences");
  return { id: str(r.comparison_id), differences, sharedUnderlying: rows(r.shared_underlying).map(item => { const s = obj(item); return { id: str(s.asset_id), leftWeight: weight(s.left_weight), rightWeight: weight(s.right_weight), overlapWeight: weight(s.overlap_weight) }; }) };
}

export function adaptComparisonResearch(value: unknown): ComparisonResearch {
  const raw = obj(value), asOf = date(raw.as_of);
  if (raw.schema_version !== "comparison_research_demo_v1" || raw.data_tier !== "synthetic" || raw.currency !== "CNY") throw new Error("Unsupported comparison study");
  const names = Object.fromEntries(Object.entries(obj(raw.names)).map(([id, v]) => { const n = obj(v); return [id, { zh: str(n.zh), en: str(n.en) }]; }));
  const accounts = rows(raw.accounts).map(item => { const a = obj(item), id = str(a.account_id), p = obj(a.periods); if (a.subject_id !== id || a.data_tier !== "synthetic" || !id.startsWith("SYN_STUDY_")) throw new Error("Comparison account mismatch"); return { id, periods: { earlier: period(p.earlier, id, asOf), recent: period(p.recent, id, asOf), full: period(p.full, id, asOf) } }; });
  const defaultSubject = str(raw.default_subject);
  if (new Set(accounts.map(a => a.id)).size !== accounts.length || !accounts.some(a => a.id === defaultSubject)) throw new Error("Duplicate / missing comparison account");
  const self = accounts.find(a => a.id === defaultSubject)!, comparisons = obj(raw.comparisons), professional = obj(comparisons.professional);
  return { dataTier: "synthetic", asOf, currency: str(raw.currency), defaultSubject, names, accounts, comparisons: {
    self: pair(comparisons.self, "self_periods", self, self, "earlier", "recent"),
    professional: Object.fromEntries(accounts.filter(a => a.id !== defaultSubject).map(a => { const c = obj(professional[a.id]); return [a.id, { full: pair(c.full, "professional", self, a, "full", "full"), earlier: pair(c.earlier, "professional", self, a, "earlier", "earlier"), recent: pair(c.recent, "professional", self, a, "recent", "recent") }]; })),
  } };
}
