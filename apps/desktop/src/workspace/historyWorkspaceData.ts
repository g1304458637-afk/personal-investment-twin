import {
  behaviorHistory,
  behaviorMetrics,
  peerBenchmark,
  selfBaseline,
  twinState,
} from "@/data/backendEvidence";
import generatedEvidence from "@/generated/showcase-demo.json";
import type { BehaviorHistorySeries } from "@/data/behaviorHistory";
import type { PeerBenchmarkView } from "@/data/peerBenchmark";
import type { SelfBaselineSummaryView } from "@/data/selfBaseline";
import type { EvidenceMetric } from "@/demo/types";
import {
  historyWorkspaceAvailability,
  type HistoryWorkspaceAvailability,
  type HistoryWorkspaceScope,
  type RegisteredHistoryStudy,
} from "./historyWorkspaceScope";

type TwinWorkspaceView = typeof twinState;
type RegisteredPeerMetricSource = {
  subject_id: string;
  metric_n: number;
  benchmark_status: string;
  observation_start: string;
  observation_end: string;
};
type RegisteredSyntheticSource = {
  evidence_records: Array<{ metric_id: string; subject_id: string }>;
  historical_series: {
    portfolio_hhi: { subject_id: string; metric_id: string };
    turnover: { subject_id: string; metric_id: string };
  };
  peer_benchmark: { metrics: Record<string, RegisteredPeerMetricSource> };
};

export type { HistoryWorkspaceAvailability, HistoryWorkspaceScope, RegisteredHistoryStudy } from "./historyWorkspaceScope";

export interface HistoryWorkspaceData {
  availability: HistoryWorkspaceAvailability;
  subjectId: string | null;
  accountId: string | null;
  datasetLabel: string | null;
  asOf: string | null;
  twin: TwinWorkspaceView | null;
  selfBaseline: SelfBaselineSummaryView | null;
  history: { hhi: BehaviorHistorySeries; turnover: BehaviorHistorySeries } | null;
  peer: PeerBenchmarkView | null;
  behaviorMetrics: readonly EvidenceMetric[] | null;
}

function explicitlyUnavailablePeerMetric(
  source: RegisteredPeerMetricSource,
  view: PeerBenchmarkView["metrics"][number],
) {
  return source.metric_n === 0
    && source.benchmark_status === "insufficient_cohort"
    && view.metricN === 0
    && view.status === "insufficient_cohort"
    && view.chartMetric === null;
}

function noPeerStatistics(view: PeerBenchmarkView) {
  return view.metrics.every((metric) => (
    metric.metricN === 0
    && metric.status === "insufficient_cohort"
    && metric.chartMetric === null
  ));
}

export function registeredHistoryStudy(): RegisteredHistoryStudy {
  const snapshot = twinState.currentSnapshot;
  const source = generatedEvidence as unknown as RegisteredSyntheticSource;
  const accounts = new Set([
    ...snapshot.episodes.open.map((episode) => episode.accountId),
    ...snapshot.episodes.closed.map((episode) => episode.accountId),
  ]);
  if (accounts.size !== 1) throw new Error("History study must have exactly one registered account.");
  const accountId = [...accounts][0]!;
  const requiredBehaviorMetricIds = new Set([
    "portfolio_concentration_hhi", "mean_daily_turnover", "disposition_effect", "loss_averaging_event_rate",
  ]);
  const behaviorSources = source.evidence_records
    .filter((record) => requiredBehaviorMetricIds.has(record.metric_id))
  const behaviorSourcesMatch = behaviorSources.length === requiredBehaviorMetricIds.size
    && new Set(behaviorSources.map((record) => record.metric_id)).size === requiredBehaviorMetricIds.size
    && behaviorSources.every((record) => record.subject_id === snapshot.subjectId);
  const historySourcesMatch = source.historical_series.portfolio_hhi.subject_id === snapshot.subjectId
    && source.historical_series.portfolio_hhi.metric_id === "portfolio_concentration_hhi"
    && source.historical_series.turnover.subject_id === snapshot.subjectId
    && source.historical_series.turnover.metric_id === "mean_daily_turnover";
  const peerSources = Object.entries(source.peer_benchmark.metrics);
  const peerSourcesMatch = peerSources.length === peerBenchmark.metrics.length
    && peerSources.every(([metricId, sourceMetric]) => {
      const viewMetric = peerBenchmark.metrics.find((metric) => metric.id === metricId);
      if (!viewMetric) return false;
      const scopeMatches = sourceMetric.subject_id === snapshot.subjectId
        && sourceMetric.observation_start <= sourceMetric.observation_end
        && sourceMetric.observation_end <= snapshot.snapshotAt
        && viewMetric.observationStart === sourceMetric.observation_start
        && viewMetric.observationEnd === sourceMetric.observation_end;
      const countMatches = Number.isInteger(sourceMetric.metric_n)
        && sourceMetric.metric_n >= 0
        && viewMetric.metricN === sourceMetric.metric_n
        && viewMetric.status === sourceMetric.benchmark_status;
      return scopeMatches && countMatches && (
        sourceMetric.metric_n > 0 || explicitlyUnavailablePeerMetric(sourceMetric, viewMetric)
      );
    });
  if (
    selfBaseline.subjectId !== snapshot.subjectId
    || behaviorHistory.hhi.metricId !== "portfolio_concentration_hhi"
    || behaviorHistory.turnover.metricId !== "mean_daily_turnover"
    || !behaviorSourcesMatch
    || !historySourcesMatch
    || !peerSourcesMatch
  ) throw new Error("History study source references are not registered for this Twin snapshot.");
  return {
    subjectId: snapshot.subjectId,
    accountId,
    asOf: snapshot.snapshotAt,
    historyMetricIds: [behaviorHistory.hhi.metricId, behaviorHistory.turnover.metricId],
  };
}

/**
 * The shipped History/Twin exports are deliberately synthetic-only. Keeping this
 * check here means a newly selected demo account can never inherit another
 * account's history while a real runtime can never silently fall back to demo.
 */
export function historyWorkspaceData(scope: HistoryWorkspaceScope): HistoryWorkspaceData {
  const study = registeredHistoryStudy();
  const availability = historyWorkspaceAvailability(scope, study);
  if (availability === "real_unavailable") {
    return { availability: "real_unavailable", subjectId: scope.subjectId, accountId: scope.accountId, datasetLabel: null, asOf: null, twin: null, selfBaseline: null, history: null, peer: null, behaviorMetrics: null };
  }
  if (availability !== "ready") {
    return { availability: "dataset_mismatch", subjectId: scope.subjectId, accountId: scope.accountId, datasetLabel: null, asOf: null, twin: null, selfBaseline: null, history: null, peer: null, behaviorMetrics: null };
  }
  return {
    availability: "ready",
    subjectId: scope.subjectId,
    accountId: scope.accountId,
    datasetLabel: "Synthetic behavior history · deterministic demo export",
    asOf: study.asOf,
    twin: twinState,
    selfBaseline,
    history: behaviorHistory,
    peer: noPeerStatistics(peerBenchmark) ? null : peerBenchmark,
    behaviorMetrics,
  };
}
