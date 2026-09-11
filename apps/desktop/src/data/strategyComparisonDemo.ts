import source from "@/generated/strategy-comparison-demo.json";

import { adaptStrategyComparison } from "./strategyComparison.ts";

/** Vite-only binding of the generated comparison artifact. */
export const strategyComparison = adaptStrategyComparison(source);

/** Raw (snake_case) report for a showcase episode, for runtime explain calls. */
export function rawComparisonReportFor(episodeId: string): Record<string, unknown> | null {
  const reports = (source as unknown as { reports: Record<string, unknown>[] }).reports;
  const report = reports.find((item) => (item as { episode_id?: string }).episode_id === episodeId);
  return report ?? null;
}
