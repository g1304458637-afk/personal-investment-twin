import type { CompareDecision, CompareSide, CompareView } from "@/data/sameStock";
import type { StandardChartDemoView } from "@/data/standardChart";
import type { StandardBar } from "./standardChartModel";

// Compare and the standard chart must refer to the same supplied daily prices.
// A similarly named security alone is not enough to attach showcase OHLC.
export function matchingComparisonChart(view: CompareView, charts: readonly StandardChartDemoView[]) {
  if (view.status === "unavailable" || !view.prices.length || view.a.tier !== "synthetic" || view.b.tier !== "synthetic") return null;
  return charts.find(({ entry, market }) => {
    if (entry.episode.subjectId !== view.a.subjectId || entry.episode.dataTier !== "synthetic" || entry.episode.openedAt !== view.a.start || market.instrumentId !== view.a.symbol || view.a.symbol !== view.b.symbol || market.currency !== view.a.currency || view.a.currency !== view.b.currency) return false;
    // The two existing transports assign different replay/episode IDs. Verify
    // the full recorded execution sequence instead of equating those IDs.
    if (entry.decisions.length !== view.a.decisions.length || !view.a.decisions.every((decision, index) => {
      const actual = entry.decisions[index];
      return actual.occurredAt === decision.at && actual.decisionType === decision.kind && actual.executedQuantity === decision.quantity && actual.executionPrice === decision.price
        && actual.stateBefore.quantity === decision.before && actual.stateAfter.quantity === decision.after
        && actual.stateBefore.averageCost === decision.costBefore && actual.stateAfter.averageCost === decision.costAfter;
    })) return false;
    const closes = new Map(market.bars.map(bar => [bar.date, bar.close]));
    return view.prices.every(point => Math.abs((closes.get(point.at.slice(0, 10)) ?? Infinity) - point.value) < 1e-8)
      && [view.a, view.b].every(side => side.decisions.every(decision => closes.has(decision.at.slice(0, 10))));
  }) ?? null;
}

export interface ComparisonBarState { date: string; quantity: number | null; averageCost: number | null }
export interface ComparisonBarGroup { date: string; party: "A" | "B"; decisions: CompareDecision[] }

/** Select the last supplied replay state in each candle's period; no position/cost arithmetic. */
export function comparisonBarStates(side: CompareSide, source: readonly StandardBar[], bars: readonly StandardBar[]): ComparisonBarState[] {
  const states = [...side.shape].sort((a, b) => a.at.localeCompare(b.at));
  let cursor = 0;
  let state: CompareSide["shape"][number] | null = null;
  return bars.map((bar, index) => {
    const end = index + 1 < bars.length ? bars[index + 1].date : null;
    const lastSession = source.filter(item => item.date >= bar.date && (!end || item.date < end)).at(-1)?.date ?? bar.date;
    while (cursor < states.length && states[cursor].at.slice(0, 10) <= lastSession) state = states[cursor++];
    return { date: bar.date, quantity: state?.quantity ?? null, averageCost: state && state.quantity > 0 ? state.cost : null };
  });
}

/** Labels share a candle, but every execution retains its original identity and timestamp. */
export function comparisonBarGroups(view: CompareView, source: readonly StandardBar[], bars: readonly StandardBar[]): ComparisonBarGroup[] {
  const dates = new Set(source.map(bar => bar.date));
  const groups: ComparisonBarGroup[] = [];
  for (const party of ["A", "B"] as const) {
    const side = party === "A" ? view.a : view.b;
    for (const decision of side.decisions) {
      const date = decision.at.slice(0, 10);
      if (!dates.has(date)) continue;
      const bucket = [...bars].reverse().find(bar => bar.date <= date);
      if (!bucket) continue;
      const group = groups.find(group => group.party === party && group.date === bucket.date);
      if (group) group.decisions.push(decision);
      else groups.push({ date: bucket.date, party, decisions: [decision] });
    }
  }
  return groups.sort((a, b) => a.date.localeCompare(b.date) || a.party.localeCompare(b.party)).map(group => ({ ...group, decisions: [...group.decisions].sort((a, b) => a.at.localeCompare(b.at)) }));
}
