import type { PositionDecisionView, PositionEpisodeEntryView, PositionStateView } from "@/data/positionEpisode";

/** A backend supplied daily bar. The chart never fills or derives missing bars. */
export interface StandardBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  amount: number | null;
}

export interface StandardChartMarket {
  instrumentId: string;
  replayInstrumentId: string;
  displayName: string;
  currency: string;
  priceBasis: string;
  sourceUrl: string;
  sourceSha256: string;
  bars: StandardBar[];
}

export type StandardChartInterval = "day" | "week" | "month";

export interface ChartPositionStep {
  date: string;
  quantity: number | null;
  averageCost: number | null;
  /** This is a daily closing state, not an intraday position claim. */
  stateAsOf: string | null;
}

export interface ChartDecisionGroup {
  date: string;
  decisions: PositionDecisionView[];
  /** Exact session dates represented by this visual marker. */
  sessionDates: string[];
}

export interface ChartFocusWindow {
  startIndex: number;
  endIndex: number;
}

export function utcSessionDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10);
  return `${parsed.getUTCFullYear()}-${String(parsed.getUTCMonth() + 1).padStart(2, "0")}-${String(parsed.getUTCDate()).padStart(2, "0")}`;
}

export function barTimestamp(date: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return Number.NaN;
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function isoWeekKey(date: string): string {
  const timestamp = barTimestamp(date);
  const value = new Date(timestamp);
  const day = value.getUTCDay() || 7;
  value.setUTCDate(value.getUTCDate() + 4 - day);
  const year = value.getUTCFullYear();
  const start = Date.UTC(year, 0, 1);
  const week = Math.ceil(((value.getTime() - start) / 86_400_000 + 1) / 7);
  return `${year}-W${String(week).padStart(2, "0")}`;
}

function intervalKey(date: string, interval: StandardChartInterval): string {
  if (interval === "day") return date;
  if (interval === "month") return date.slice(0, 7);
  return isoWeekKey(date);
}

/**
 * Aggregates supplied bars in chronological order. Volume/amount stay unavailable if
 * any constituent session is unavailable; this avoids making a partial total look real.
 */
export function aggregateStandardBars(bars: readonly StandardBar[], interval: StandardChartInterval): StandardBar[] {
  if (interval === "day") return bars.map((bar) => ({ ...bar }));
  const groups = new Map<string, StandardBar[]>();
  for (const bar of bars) {
    const key = intervalKey(bar.date, interval);
    const existing = groups.get(key);
    if (existing) existing.push(bar);
    else groups.set(key, [bar]);
  }
  return [...groups.values()].map((group) => {
    const first = group[0];
    const last = group[group.length - 1];
    const completeVolume = group.every((bar) => bar.volume !== null);
    const completeAmount = group.every((bar) => bar.amount !== null);
    return {
      date: first.date,
      open: first.open,
      high: Math.max(...group.map((bar) => bar.high)),
      low: Math.min(...group.map((bar) => bar.low)),
      close: last.close,
      volume: completeVolume ? group.reduce((sum, bar) => sum + (bar.volume ?? 0), 0) : null,
      amount: completeAmount ? group.reduce((sum, bar) => sum + (bar.amount ?? 0), 0) : null,
    };
  });
}

export function groupChartDecisions(entry: PositionEpisodeEntryView): ChartDecisionGroup[] {
  const groups = new Map<string, PositionDecisionView[]>();
  for (const decision of entry.decisions) {
    const date = utcSessionDate(decision.occurredAt);
    const existing = groups.get(date);
    if (existing) existing.push(decision);
    else groups.set(date, [decision]);
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, decisions]) => ({
    date,
    sessionDates: [date],
    // Same-session entries retain the precise backend time and a deterministic backend order.
    decisions: [...decisions].sort((left, right) => Date.parse(left.occurredAt) - Date.parse(right.occurredAt)),
  }));
}

/** Maps all operations to the visible day/week/month candle without changing their timestamps. */
export function groupChartDecisionsForBars(
  entry: PositionEpisodeEntryView,
  bars: readonly StandardBar[],
  interval: StandardChartInterval,
): ChartDecisionGroup[] {
  if (interval === "day") return groupChartDecisions(entry);
  const bucketStart = new Map(bars.map((bar) => [intervalKey(bar.date, interval), bar.date]));
  const combined = new Map<string, ChartDecisionGroup>();
  for (const dailyGroup of groupChartDecisions(entry)) {
    const bucket = bucketStart.get(intervalKey(dailyGroup.date, interval));
    if (!bucket) continue; // There is no supplied market candle for that execution's period.
    const existing = combined.get(bucket);
    if (existing) {
      existing.decisions.push(...dailyGroup.decisions);
      existing.sessionDates.push(dailyGroup.date);
    } else {
      combined.set(bucket, { date: bucket, decisions: [...dailyGroup.decisions], sessionDates: [dailyGroup.date] });
    }
  }
  return [...combined.values()].sort((left, right) => left.date.localeCompare(right.date)).map((group) => ({
    ...group,
    sessionDates: [...new Set(group.sessionDates)].sort(),
    decisions: [...group.decisions].sort((left, right) => Date.parse(left.occurredAt) - Date.parse(right.occurredAt)),
  }));
}

function visibleCost(state: PositionStateView): number | null {
  if (!Number.isFinite(state.quantity) || state.quantity <= 0) return null;
  return typeof state.averageCost === "number" && Number.isFinite(state.averageCost) ? state.averageCost : null;
}

/**
 * Uses state snapshots supplied by replay. It deliberately performs no quantity or
 * cost arithmetic. A session point means the last recorded state for that session.
 */
export function positionStepsForBars(entry: PositionEpisodeEntryView, bars: readonly StandardBar[]): ChartPositionStep[] {
  const byDate = new Map(groupChartDecisions(entry).map((group) => [group.date, group.decisions]));
  let state: PositionStateView | null = null;
  return bars.map((bar) => {
    const decisions = byDate.get(bar.date);
    if (decisions?.length) state = decisions[decisions.length - 1].stateAfter;
    return {
      date: bar.date,
      quantity: state?.quantity ?? null,
      averageCost: state ? visibleCost(state) : null,
      stateAsOf: state?.asOf ?? null,
    };
  });
}

/** Carries the last supplied daily closing state into each aggregated chart period. */
export function positionStepsForChartBars(
  entry: PositionEpisodeEntryView,
  sourceBars: readonly StandardBar[],
  chartBars: readonly StandardBar[],
  interval: StandardChartInterval,
): ChartPositionStep[] {
  if (interval === "day") return positionStepsForBars(entry, chartBars);
  const daily = positionStepsForBars(entry, sourceBars);
  const lastByPeriod = new Map<string, ChartPositionStep>();
  for (const step of daily) lastByPeriod.set(intervalKey(step.date, interval), step);
  return chartBars.map((bar) => lastByPeriod.get(intervalKey(bar.date, interval)) ?? {
    date: bar.date, quantity: null, averageCost: null, stateAsOf: null,
  });
}

export function clampFocusWindow(
  bars: readonly StandardBar[],
  focus: { startAt: string; endAt: string } | null | undefined,
  contextSessions = 7,
): ChartFocusWindow | null {
  if (!bars.length || !focus) return null;
  const startDate = utcSessionDate(focus.startAt);
  const endDate = utcSessionDate(focus.endAt);
  const from = startDate <= endDate ? startDate : endDate;
  const to = startDate <= endDate ? endDate : startDate;
  let first = bars.findIndex((bar) => bar.date >= from);
  let last = -1;
  for (let index = bars.length - 1; index >= 0; index -= 1) {
    if (bars[index].date <= to) { last = index; break; }
  }
  if (first < 0) first = bars.length - 1;
  if (last < 0) last = 0;
  if (first > last) [first, last] = [last, first];
  return {
    startIndex: Math.max(0, first - contextSessions),
    endIndex: Math.min(bars.length - 1, last + contextSessions),
  };
}

export function precisionForBars(bars: readonly StandardBar[]): number {
  const values = bars.flatMap((bar) => [bar.open, bar.high, bar.low, bar.close]);
  const decimals = values.map((value) => {
    if (!Number.isFinite(value)) return 2;
    const text = String(value);
    return text.includes(".") ? Math.min(6, text.length - text.indexOf(".") - 1) : 0;
  });
  return Math.max(2, ...decimals);
}

/** Context is measured in source sessions, never seven weeks after switching to week K. */
export function focusForChartBars(source: readonly StandardBar[], bars: readonly StandardBar[], focus: { startAt: string; endAt: string }, contextSessions = 7): ChartFocusWindow | null {
  const daily = clampFocusWindow(source, focus, contextSessions);
  if (!daily || !bars.length) return null;
  const indexAt = (date: string) => {
    let index = 0;
    while (index + 1 < bars.length && bars[index + 1].date <= date) index += 1;
    return index;
  };
  return { startIndex: indexAt(source[daily.startIndex].date), endIndex: indexAt(source[daily.endIndex].date) };
}
