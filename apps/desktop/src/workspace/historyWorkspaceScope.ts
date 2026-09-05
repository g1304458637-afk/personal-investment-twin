export type HistoryWorkspaceAvailability = "ready" | "real_unavailable" | "dataset_mismatch";

export interface HistoryWorkspaceScope {
  mode: "demo" | "real_user";
  subjectId: string | null;
  accountId: string | null;
}

export interface RegisteredHistoryStudy {
  subjectId: string;
  accountId: string;
  asOf: string;
  historyMetricIds: readonly string[];
}

/** Pure scope gate: no financial computation and no demo fallback in real mode. */
export function historyWorkspaceAvailability(
  scope: HistoryWorkspaceScope,
  study: RegisteredHistoryStudy,
): HistoryWorkspaceAvailability {
  if (scope.mode === "real_user") return "real_unavailable";
  return scope.subjectId === study.subjectId && scope.accountId === study.accountId
    ? "ready"
    : "dataset_mismatch";
}
