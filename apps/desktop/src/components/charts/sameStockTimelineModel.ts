import type { CompareDecision, CompareSide, CompareView } from "@/data/sameStock";
import { uniqueDailyObservationTimes } from "./dailyTimeAxis.ts";

export type SameStockParty = {
  id: "A" | "B";
  symbol: string;
  currency: string;
  color: string;
  side: CompareSide;
};

/** Presentation labels intentionally identify supplied records, not people or accounts. */
export function sameStockParties(view: CompareView): SameStockParty[] {
  return [
    { id: "A", symbol: view.a.symbol, currency: view.a.currency, color: "#8cdaf2", side: view.a },
    { id: "B", symbol: view.b.symbol, currency: view.b.currency, color: "#debfa1", side: view.b },
  ];
}

export function sameStockPartyLabel(party: SameStockParty, recordLabel: string, displaySymbol = party.symbol): string {
  return `${recordLabel} ${party.id} · ${displaySymbol}`;
}

/** Only market observations are zoom observations; execution times widen the visible boundary. */
export function sameStockTimelineTimes(view: CompareView) {
  const observationTimes = uniqueDailyObservationTimes(view.prices.map((point) => point.at));
  const boundaryTimes = [
    ...sameStockParties(view).flatMap((party) => [
      ...party.side.decisions.map((decision) => Date.parse(decision.at)),
      ...party.side.shape.map((point) => Date.parse(point.at)),
    ]),
  ].filter(Number.isFinite);
  return { observationTimes, boundaryTimes };
}

export function comparedDecision(view: CompareView, decisionId: string | null | undefined): { party: SameStockParty; decision: CompareDecision } | null {
  if (!decisionId) return null;
  for (const party of sameStockParties(view)) {
    const decision = party.side.decisions.find((item) => item.id === decisionId);
    if (decision) return { party, decision };
  }
  return null;
}
