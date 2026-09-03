import type { EvidenceStatus } from "@/demo/types";

export interface BackendTwinEvidenceRef {
  evidence_id: string;
  metric_id: string;
  evidence_status: EvidenceStatus;
  available_at: string;
}

export interface BackendTwinMetricState {
  metric_id: string;
  as_of: string;
  value: number | null;
  evidence_status: EvidenceStatus;
  source_evidence_id: string;
  observation_count: number | null;
}

export interface BackendTwinSnapshot {
  subject_id: string;
  snapshot_at: string;
  decision_evidence_refs: BackendTwinEvidenceRef[];
  behavior_evidence_refs: BackendTwinEvidenceRef[];
  behavior_state: BackendTwinMetricState[];
  data_quality_summary: {
    expected_evidence_count: number;
    referenced_evidence_count: number;
    complete_evidence_count: number;
    insufficient_evidence_count: number;
    available_behavior_metric_count: number;
    missing_behavior_metrics: string[];
  };
  data_tier: "synthetic";
  limitations: string[];
}

export interface BackendTwinMetricComparison {
  metric_id: string;
  method_id: string;
  method_version: string;
  reference_date: string | null;
  current_date: string | null;
  past_value: number | null;
  current_value: number | null;
  absolute_change: number | null;
  relative_change: number | null;
  evidence_status: EvidenceStatus;
  evidence_reason: string | null;
  reference_evidence_id: string | null;
  current_evidence_id: string | null;
}

export interface BackendTwinPayload {
  data_tier: "synthetic";
  current_snapshot: BackendTwinSnapshot;
  historical_snapshots: BackendTwinSnapshot[];
  comparison: {
    portfolio_hhi: BackendTwinMetricComparison;
    turnover: BackendTwinMetricComparison;
  };
}

export interface TwinEvidenceRefView {
  evidenceId: string;
  metricId: string;
  status: EvidenceStatus;
  availableAt: string;
}

export interface TwinMetricStateView {
  metricId: string;
  asOf: string;
  value: number | null;
  status: EvidenceStatus;
  sourceEvidenceId: string;
  observationCount: number | null;
}

export interface TwinSnapshotView {
  subjectId: string;
  snapshotAt: string;
  decisionEvidenceRefs: TwinEvidenceRefView[];
  behaviorEvidenceRefs: TwinEvidenceRefView[];
  behaviorState: TwinMetricStateView[];
  dataQuality: {
    expectedEvidenceCount: number;
    referencedEvidenceCount: number;
    completeEvidenceCount: number;
    insufficientEvidenceCount: number;
    availableBehaviorMetricCount: number;
    missingBehaviorMetrics: string[];
  };
  dataTier: "synthetic";
  limitations: string[];
}

export interface TwinMetricComparisonView {
  metricId: string;
  methodId: string;
  methodVersion: string;
  referenceDate: string | null;
  currentDate: string | null;
  pastValue: number | null;
  currentValue: number | null;
  absoluteChange: number | null;
  relativeChange: number | null;
  status: EvidenceStatus;
  reason: string | null;
  referenceEvidenceId: string | null;
  currentEvidenceId: string | null;
}

function evidenceRef(value: BackendTwinEvidenceRef): TwinEvidenceRefView {
  return {
    evidenceId: value.evidence_id,
    metricId: value.metric_id,
    status: value.evidence_status,
    availableAt: value.available_at,
  };
}

function snapshot(value: BackendTwinSnapshot): TwinSnapshotView {
  if (value.data_tier !== "synthetic") {
    throw new Error("Desktop Twin demo must remain explicitly synthetic.");
  }
  return {
    subjectId: value.subject_id,
    snapshotAt: value.snapshot_at,
    decisionEvidenceRefs: value.decision_evidence_refs.map(evidenceRef),
    behaviorEvidenceRefs: value.behavior_evidence_refs.map(evidenceRef),
    behaviorState: value.behavior_state.map((item) => ({
      metricId: item.metric_id,
      asOf: item.as_of,
      value: item.value,
      status: item.evidence_status,
      sourceEvidenceId: item.source_evidence_id,
      observationCount: item.observation_count,
    })),
    dataQuality: {
      expectedEvidenceCount: value.data_quality_summary.expected_evidence_count,
      referencedEvidenceCount: value.data_quality_summary.referenced_evidence_count,
      completeEvidenceCount: value.data_quality_summary.complete_evidence_count,
      insufficientEvidenceCount: value.data_quality_summary.insufficient_evidence_count,
      availableBehaviorMetricCount: value.data_quality_summary.available_behavior_metric_count,
      missingBehaviorMetrics: value.data_quality_summary.missing_behavior_metrics,
    },
    dataTier: value.data_tier,
    limitations: value.limitations,
  };
}

function comparison(value: BackendTwinMetricComparison): TwinMetricComparisonView {
  return {
    metricId: value.metric_id,
    methodId: value.method_id,
    methodVersion: value.method_version,
    referenceDate: value.reference_date,
    currentDate: value.current_date,
    pastValue: value.past_value,
    currentValue: value.current_value,
    absoluteChange: value.absolute_change,
    relativeChange: value.relative_change,
    status: value.evidence_status,
    reason: value.evidence_reason,
    referenceEvidenceId: value.reference_evidence_id,
    currentEvidenceId: value.current_evidence_id,
  };
}

export function adaptTwinPayload(value: BackendTwinPayload) {
  if (value.data_tier !== "synthetic") {
    throw new Error("Desktop Twin payload must remain explicitly synthetic.");
  }
  const historicalSnapshots = value.historical_snapshots.map(snapshot);
  if (historicalSnapshots.some((item, index) => index > 0 && item.snapshotAt <= historicalSnapshots[index - 1].snapshotAt)) {
    throw new Error("Historical Twin snapshots must be chronological.");
  }
  return {
    currentSnapshot: snapshot(value.current_snapshot),
    historicalSnapshots,
    comparisons: [
      comparison(value.comparison.portfolio_hhi),
      comparison(value.comparison.turnover),
    ],
  };
}
