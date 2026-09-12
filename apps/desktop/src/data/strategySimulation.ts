/**
 * Transport adapter for the deterministic strategy simulation artifact.
 * Validation only: no finance is computed in the browser, and nothing here
 * can touch recorded user accounts — the artifact describes a synthetic,
 * fully independent strategy account.
 */

export type StrategyOrderStatus = "pending" | "filled" | "cancelled" | "rejected";
export type StrategyFillTrigger = "signal_order" | "stop_loss" | "delisting_liquidation";

export interface StrategyRuleView {
  ruleId: string;
  source: string;
  statement: string;
}

export interface StrategySpecView {
  strategyId: string;
  version: string;
  title: string;
  description: string;
  ruleTable: StrategyRuleView[];
  params: Record<string, number | string>;
}

export interface StrategySummaryView {
  initialCash: number;
  finalEquity: number;
  totalReturn: number;
  maxDrawdown: number;
  maxDrawdownPeakDate: string;
  maxDrawdownTroughDate: string;
  tradingDays: number;
  orderCount: number;
  fillCount: number;
  rejectedOrderCount: number;
  cancelledOrderCount: number;
  totalFees: number;
  roundTripCount: number;
  winRate: number | null;
  averageInvestedFraction: number;
  roundTrips: { instrument: string; closedOn: string; pnl: number; reason: string }[];
}

export interface StrategyEquityPoint {
  date: string;
  cash: number;
  equity: number;
  investedFraction: number;
  drawdownFromPeak: number;
}

export interface StrategyFillView {
  fillId: string;
  orderId: string | null;
  trigger: StrategyFillTrigger;
  instrument: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  fee: number;
  day: string;
  note: string | null;
}

export interface StrategyOrderView {
  orderId: string;
  signalDate: string;
  instrument: string;
  side: "BUY" | "SELL";
  intendedQuantity: number;
  reasonCode: string;
  reasonText: string;
  rank: number | null;
  status: StrategyOrderStatus;
  resolutionDate: string | null;
  resolutionReason: string | null;
}

export interface StrategyBar { date: string; open: number; high: number; low: number; close: number }

export interface StrategySimulationView {
  barsByInstrument: Record<string, StrategyBar[]>;
  strategy: StrategySpecView;
  dataFingerprint: string;
  summary: StrategySummaryView;
  equity: StrategyEquityPoint[];
  orders: StrategyOrderView[];
  fills: StrategyFillView[];
}

const fail = (): never => { throw new Error("strategy_simulation_projection_invalid"); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown): string => typeof x === "string" && x.trim().length > 0 && x.length <= 6000 ? x : fail();
const finite = (x: unknown): number => typeof x === "number" && Number.isFinite(x) ? x : fail();
const nullableText = (x: unknown): string | null => x === null ? null : text(x);
const nullableFinite = (x: unknown): number | null => x === null ? null : finite(x);
const array = (x: unknown): unknown[] => Array.isArray(x) && x.length <= 50000 ? x : fail();
const day = (x: unknown): string => {
  const s = text(x);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) fail();
  return s;
};
const side = (x: unknown): "BUY" | "SELL" => x === "BUY" || x === "SELL" ? x : fail();
const status = (x: unknown): StrategyOrderStatus => ["pending", "filled", "cancelled", "rejected"].includes(String(x)) ? x as StrategyOrderStatus : fail();
const trigger = (x: unknown): StrategyFillTrigger => ["signal_order", "stop_loss", "delisting_liquidation"].includes(String(x)) ? x as StrategyFillTrigger : fail();

function spec(raw: unknown): StrategySpecView {
  const value = object(raw);
  const params = object(value.params);
  const ruleTable = array(value.rule_table).map((item) => {
    const rule = object(item);
    return { ruleId: text(rule.rule_id), source: text(rule.source), statement: text(rule.statement) };
  });
  // Provenance completeness: rules must cite a recognised source class —
  // lens_rule (lifted from recorded checks) or public_rule (classic public
  // template) — plus declared adaptations; rule ids must be unique.
  if (ruleTable.length < 2) fail();
  if (!ruleTable.some((rule) => rule.source.startsWith("lens_rule") || rule.source.startsWith("public_rule"))) fail();
  if (!ruleTable.some((rule) => rule.source === "adaptation")) fail();
  if (new Set(ruleTable.map((rule) => rule.ruleId)).size !== ruleTable.length) fail();
  return {
    strategyId: text(value.strategy_id),
    version: text(value.version),
    title: text(value.title),
    description: text(value.description),
    ruleTable,
    params: Object.fromEntries(Object.entries(params).map(([key, item]) => {
      if (typeof item === "number" && Number.isFinite(item)) return [text(key), item] as const;
      if (typeof item === "string" && item.length <= 100) return [text(key), item] as const;
      return fail();
    })),
  };
}

function summary(raw: unknown): StrategySummaryView {
  const value = object(raw);
  const roundTrips = array(value.round_trips).map((item) => {
    const trip = object(item);
    return { instrument: text(trip.instrument), closedOn: day(trip.closed_on), pnl: finite(trip.pnl), reason: text(trip.reason) };
  });
  return {
    initialCash: finite(value.initial_cash),
    finalEquity: finite(value.final_equity),
    totalReturn: nullableFinite(value.total_return) ?? fail(),
    maxDrawdown: finite(value.max_drawdown),
    maxDrawdownPeakDate: day(value.max_drawdown_peak_date),
    maxDrawdownTroughDate: day(value.max_drawdown_trough_date),
    tradingDays: finite(value.trading_days),
    orderCount: finite(value.order_count),
    fillCount: finite(value.fill_count),
    rejectedOrderCount: finite(value.rejected_order_count),
    cancelledOrderCount: finite(value.cancelled_order_count),
    totalFees: finite(value.total_fees),
    roundTripCount: finite(value.round_trip_count),
    winRate: nullableFinite(value.win_rate),
    averageInvestedFraction: finite(value.average_invested_fraction),
    roundTrips,
  };
}

export function adaptStrategySimulation(raw: unknown): StrategySimulationView {
  const value = object(raw);
  if (value.schema_version !== "strategy_simulation.v1") fail();
  const equity = array(value.equity).map((item) => {
    const point = object(item);
    return {
      date: day(point.date), cash: finite(point.cash), equity: finite(point.equity),
      investedFraction: finite(point.invested_fraction), drawdownFromPeak: finite(point.drawdown_from_peak),
    };
  });
  for (let index = 1; index < equity.length; index += 1) {
    if (equity[index].date <= equity[index - 1].date) fail();
  }
  const fills: StrategyFillView[] = array(value.fills).map((item) => {
    const fill = object(item);
    const detail = object(fill.fee_detail);
    const fee = finite(fill.fee);
    const commission = finite(detail.commission);
    const stampDuty = finite(detail.stamp_duty);
    if (Math.abs(commission + stampDuty - fee) > 1e-6) fail();
    if (fee < 0 || finite(fill.quantity) <= 0 || finite(fill.price) <= 0) fail();
    return {
      fillId: text(fill.fill_id), orderId: nullableText(fill.order_id), trigger: trigger(fill.trigger),
      instrument: text(fill.instrument), side: side(fill.side), quantity: finite(fill.quantity),
      price: finite(fill.price), fee, day: day(fill.day), note: nullableText(fill.note),
    };
  });
  const orders: StrategyOrderView[] = array(value.orders).map((item) => {
    const order = object(item);
    return {
      orderId: text(order.order_id), signalDate: day(order.signal_date), instrument: text(order.instrument),
      side: side(order.side), intendedQuantity: finite(order.intended_quantity),
      reasonCode: text(order.reason_code), reasonText: text(order.reason_text),
      rank: nullableFinite(order.rank), status: status(order.status),
      resolutionDate: nullableText(order.resolution_date) === null ? null : day(order.resolution_date),
      resolutionReason: nullableText(order.resolution_reason),
    };
  });
  const fingerprint = text(value.data_fingerprint);
  if (!/^[a-f0-9]{64}$/.test(fingerprint)) fail();
  const summaryView = summary(value.summary);
  // Ledger consistency between the summary and the transported series.
  if (equity.length === 0 || Math.abs(summaryView.finalEquity - equity[equity.length - 1].equity) > 1e-6) fail();
  if (Math.abs(summaryView.totalFees - fills.reduce((total, fill) => total + fill.fee, 0)) > 1e-6) fail();
  if (summaryView.fillCount !== fills.length || summaryView.orderCount !== orders.length) fail();
  const barsByInstrument: Record<string, StrategyBar[]> = {};
  for (const item of array(value.bars ?? [])) {
    const bar = object(item);
    const row = { date: day(bar.date), open: finite(bar.open), high: finite(bar.high),
                  low: finite(bar.low), close: finite(bar.close) };
    if (row.high < Math.max(row.open, row.close) || row.low > Math.min(row.open, row.close)) fail();
    (barsByInstrument[text(bar.instrument)] ??= []).push(row);
  }
  for (const rows of Object.values(barsByInstrument)) {
    for (let index = 1; index < rows.length; index += 1) {
      if (rows[index].date <= rows[index - 1].date) fail();
    }
  }
  return {
    barsByInstrument,
    strategy: spec(value.strategy),
    dataFingerprint: fingerprint,
    summary: summaryView,
    equity, orders, fills,
  };
}
