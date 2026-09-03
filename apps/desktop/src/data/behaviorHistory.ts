import type { EvidenceStatus } from "@/demo/types";

export interface BehaviorHistoryPoint {
  date: string;
  value: number | null;
  status: EvidenceStatus;
  sourceEvidenceId: string;
}

export interface BehaviorHistorySeries {
  metricId: string;
  methodId: string;
  methodVersion: string;
  dataTier: "synthetic";
  limitations: string[];
  points: BehaviorHistoryPoint[];
}

export type HistoryDisplayMode = "insufficient" | "single" | "series";

export function validHistoryPoints(series: BehaviorHistorySeries): BehaviorHistoryPoint[] {
  return series.points.filter(
    (point) => point.value !== null && point.status !== "insufficient_evidence",
  );
}

export function historyDisplayMode(series: BehaviorHistorySeries): HistoryDisplayMode {
  const count = validHistoryPoints(series).length;
  if (count === 0) return "insufficient";
  if (count === 1) return "single";
  return "series";
}
