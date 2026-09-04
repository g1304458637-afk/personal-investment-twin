import type { EvidenceStatus } from "@/demo/types";

type PortfolioStateStatus = "available" | "not_started" | "unavailable";
type EpisodeStatus = "open" | "closed";

export interface EvidenceOwner {
  evidence_id: string;
  subject_id: string;
}

export interface EpisodeOwner {
  episodeId: string;
  subjectId: string;
  status: EpisodeStatus;
}

interface BackendTwinInputVersionRef {
  source_type: string;
  source_name: string;
  data_version: string;
  as_of: string | null;
  price_type: string | null;
  is_synthetic: boolean;
  source_id: string | null;
  instrument: string | null;
  benchmark_id: string | null;
}

interface BackendTwinPositionState {
  state_ref: string;
  account_id: string;
  instrument_id: string;
  quantity: number;
  average_cost: number | null;
  valuation_at: string | null;
  valuation_price: number | null;
  market_value: number | null;
  replay_method_id: string;
}

interface BackendTwinEpisodeRef {
  episode_id: string;
  status: EpisodeStatus;
  account_id: string;
  instrument_id: string;
  opened_at: string;
  closed_at: string | null;
  opening_execution_id: string;
  closing_execution_id: string | null;
  execution_refs: string[];
  decision_refs: string[];
  evidence_refs: string[];
  current_position_state_ref: string | null;
}

export interface BackendTwinEvidenceRef {
  evidence_id: string;
  metric_id: string;
  evidence_status: EvidenceStatus;
  available_at: string;
  evidence_kind: string;
  method_id: string;
  method_version: string;
  evidence_reason: string | null;
  calculation_code_version: string;
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
  snapshot_id: string;
  subject_id: string;
  snapshot_at: string;
  schema_version: string;
  projection_method_id: string;
  projection_method_version: string;
  calculation_code_version: string;
  input_version_refs: BackendTwinInputVersionRef[];
  portfolio_state: {
    as_of: string;
    status: PortfolioStateStatus;
    reason: string | null;
    replay_method_id: string | null;
    positions: BackendTwinPositionState[];
  };
  episode_refs: {
    open: BackendTwinEpisodeRef[];
    closed: BackendTwinEpisodeRef[];
  };
  decision_event_refs: string[];
  decision_evidence_refs: BackendTwinEvidenceRef[];
  behavior_evidence_refs: BackendTwinEvidenceRef[];
  behavior_state: BackendTwinMetricState[];
  evidence_summary: {
    total: number;
    complete: number;
    partial: number;
    insufficient: number;
    experimental: number;
    unavailable_metric_ids: string[];
  };
  data_quality_summary: {
    expected_evidence_count: number;
    referenced_evidence_count: number;
    complete_evidence_count: number;
    insufficient_evidence_count: number;
    available_behavior_metric_count: number;
    missing_behavior_metrics: string[];
    partial_evidence_count: number;
    experimental_evidence_count: number;
    missing_evidence_metrics: string[];
    portfolio_state_status: PortfolioStateStatus;
    open_episode_count: number;
    closed_episode_count: number;
    issue_count: number;
    issues: string[];
  };
  self_baseline_refs: string[];
  peer_context_refs: string[];
  notable_change_refs: string[];
  intervention_history_ref: string | null;
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
  evidenceKind: string;
  methodId: string;
  methodVersion: string;
  reason: string | null;
  calculationCodeVersion: string;
}

export interface TwinMetricStateView {
  metricId: string;
  asOf: string;
  value: number | null;
  status: EvidenceStatus;
  sourceEvidenceId: string;
  observationCount: number | null;
}

export interface TwinInputVersionRefView {
  sourceType: string;
  sourceName: string;
  dataVersion: string;
  asOf: string | null;
  priceType: string | null;
  isSynthetic: boolean;
  sourceId: string | null;
  instrument: string | null;
  benchmarkId: string | null;
}

export interface TwinPositionStateView {
  stateRef: string;
  accountId: string;
  instrumentId: string;
  quantity: number;
  averageCost: number | null;
  valuationAt: string | null;
  valuationPrice: number | null;
  marketValue: number | null;
  replayMethodId: string;
}

export interface TwinEpisodeRefView {
  episodeId: string;
  status: EpisodeStatus;
  accountId: string;
  instrumentId: string;
  openedAt: string;
  closedAt: string | null;
  openingExecutionId: string;
  closingExecutionId: string | null;
  executionRefs: string[];
  decisionRefs: string[];
  evidenceRefs: string[];
  currentPositionStateRef: string | null;
  currentPositionState: TwinPositionStateView | null;
}

export interface TwinSnapshotView {
  snapshotId: string;
  subjectId: string;
  snapshotAt: string;
  schemaVersion: string;
  projectionMethodId: string;
  projectionMethodVersion: string;
  calculationCodeVersion: string;
  inputVersionRefs: TwinInputVersionRefView[];
  portfolioState: {
    asOf: string;
    status: PortfolioStateStatus;
    reason: string | null;
    replayMethodId: string | null;
    positions: TwinPositionStateView[];
  };
  episodes: {
    open: TwinEpisodeRefView[];
    closed: TwinEpisodeRefView[];
  };
  decisionEventRefs: string[];
  decisionEvidenceRefs: TwinEvidenceRefView[];
  behaviorEvidenceRefs: TwinEvidenceRefView[];
  behaviorState: TwinMetricStateView[];
  evidenceSummary: {
    total: number;
    complete: number;
    partial: number;
    insufficient: number;
    experimental: number;
    unavailableMetricIds: string[];
  };
  dataQuality: {
    expectedEvidenceCount: number;
    referencedEvidenceCount: number;
    completeEvidenceCount: number;
    insufficientEvidenceCount: number;
    availableBehaviorMetricCount: number;
    missingBehaviorMetrics: string[];
    partialEvidenceCount: number;
    experimentalEvidenceCount: number;
    missingEvidenceMetrics: string[];
    portfolioStateStatus: PortfolioStateStatus;
    openEpisodeCount: number;
    closedEpisodeCount: number;
    issueCount: number;
    issues: string[];
  };
  futureCapabilities: {
    selfBaselineRefs: string[];
    peerContextRefs: string[];
    notableChangeRefs: string[];
    interventionHistoryRef: string | null;
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

function object(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Twin ${name} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function requiredText(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`Twin ${name} is required.`);
  return value;
}

function optionalText(value: unknown, name: string): string | null {
  return value === null ? null : requiredText(value, name);
}

function requiredTime(value: unknown, name: string): string {
  const result = requiredText(value, name);
  if (Number.isNaN(Date.parse(result))) throw new Error(`Twin ${name} must be a timestamp.`);
  return result;
}

function optionalTime(value: unknown, name: string): string | null {
  return value === null ? null : requiredTime(value, name);
}

function number(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`Twin ${name} must be finite.`);
  return value;
}

function optionalNumber(value: unknown, name: string): number | null {
  return value === null ? null : number(value, name);
}

function integer(value: unknown, name: string): number {
  const result = number(value, name);
  if (!Number.isInteger(result) || result < 0) throw new Error(`Twin ${name} must be a non-negative integer.`);
  return result;
}

function array(value: unknown, name: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`Twin ${name} must be an array.`);
  return value;
}

function textArray(value: unknown, name: string): string[] {
  return array(value, name).map((item, index) => requiredText(item, `${name}[${index}]`));
}

function status(value: unknown, name: string): EvidenceStatus {
  if (!["complete", "partial", "insufficient_evidence", "experimental"].includes(String(value))) {
    throw new Error(`Twin ${name} has an unsupported Evidence status.`);
  }
  return value as EvidenceStatus;
}

function portfolioStatus(value: unknown, name: string): PortfolioStateStatus {
  if (!["available", "not_started", "unavailable"].includes(String(value))) {
    throw new Error(`Twin ${name} has an unsupported portfolio state.`);
  }
  return value as PortfolioStateStatus;
}

function evidenceRef(value: unknown, name: string): TwinEvidenceRefView {
  const raw = object(value, name) as unknown as BackendTwinEvidenceRef;
  return {
    evidenceId: requiredText(raw.evidence_id, `${name}.evidence_id`),
    metricId: requiredText(raw.metric_id, `${name}.metric_id`),
    status: status(raw.evidence_status, `${name}.evidence_status`),
    availableAt: requiredTime(raw.available_at, `${name}.available_at`),
    evidenceKind: requiredText(raw.evidence_kind, `${name}.evidence_kind`),
    methodId: requiredText(raw.method_id, `${name}.method_id`),
    methodVersion: requiredText(raw.method_version, `${name}.method_version`),
    reason: optionalText(raw.evidence_reason, `${name}.evidence_reason`),
    calculationCodeVersion: requiredText(raw.calculation_code_version, `${name}.calculation_code_version`),
  };
}

function position(value: unknown, name: string): TwinPositionStateView {
  const raw = object(value, name) as unknown as BackendTwinPositionState;
  return {
    stateRef: requiredText(raw.state_ref, `${name}.state_ref`),
    accountId: requiredText(raw.account_id, `${name}.account_id`),
    instrumentId: requiredText(raw.instrument_id, `${name}.instrument_id`),
    quantity: number(raw.quantity, `${name}.quantity`),
    averageCost: optionalNumber(raw.average_cost, `${name}.average_cost`),
    valuationAt: optionalTime(raw.valuation_at, `${name}.valuation_at`),
    valuationPrice: optionalNumber(raw.valuation_price, `${name}.valuation_price`),
    marketValue: optionalNumber(raw.market_value, `${name}.market_value`),
    replayMethodId: requiredText(raw.replay_method_id, `${name}.replay_method_id`),
  };
}

function inputRef(value: unknown, name: string): TwinInputVersionRefView {
  const raw = object(value, name) as unknown as BackendTwinInputVersionRef;
  if (typeof raw.is_synthetic !== "boolean") throw new Error(`Twin ${name}.is_synthetic must be boolean.`);
  return {
    sourceType: requiredText(raw.source_type, `${name}.source_type`),
    sourceName: requiredText(raw.source_name, `${name}.source_name`),
    dataVersion: requiredText(raw.data_version, `${name}.data_version`),
    asOf: optionalTime(raw.as_of, `${name}.as_of`),
    priceType: optionalText(raw.price_type, `${name}.price_type`),
    isSynthetic: raw.is_synthetic,
    sourceId: optionalText(raw.source_id, `${name}.source_id`),
    instrument: optionalText(raw.instrument, `${name}.instrument`),
    benchmarkId: optionalText(raw.benchmark_id, `${name}.benchmark_id`),
  };
}

function comparison(value: unknown, name: string): TwinMetricComparisonView {
  const raw = object(value, name) as unknown as BackendTwinMetricComparison;
  return {
    metricId: requiredText(raw.metric_id, `${name}.metric_id`),
    methodId: requiredText(raw.method_id, `${name}.method_id`),
    methodVersion: requiredText(raw.method_version, `${name}.method_version`),
    referenceDate: optionalTime(raw.reference_date, `${name}.reference_date`),
    currentDate: optionalTime(raw.current_date, `${name}.current_date`),
    pastValue: optionalNumber(raw.past_value, `${name}.past_value`),
    currentValue: optionalNumber(raw.current_value, `${name}.current_value`),
    absoluteChange: optionalNumber(raw.absolute_change, `${name}.absolute_change`),
    relativeChange: optionalNumber(raw.relative_change, `${name}.relative_change`),
    status: status(raw.evidence_status, `${name}.evidence_status`),
    reason: optionalText(raw.evidence_reason, `${name}.evidence_reason`),
    referenceEvidenceId: optionalText(raw.reference_evidence_id, `${name}.reference_evidence_id`),
    currentEvidenceId: optionalText(raw.current_evidence_id, `${name}.current_evidence_id`),
  };
}

function snapshot(
  value: unknown,
  evidenceOwners: ReadonlyMap<string, string>,
  episodeOwners: ReadonlyMap<string, { subjectId: string; status: EpisodeStatus }>,
): TwinSnapshotView {
  const raw = object(value, "snapshot") as unknown as BackendTwinSnapshot;
  const subjectId = requiredText(raw.subject_id, "snapshot.subject_id");
  const snapshotAt = requiredTime(raw.snapshot_at, "snapshot.snapshot_at");
  const schemaVersion = requiredText(raw.schema_version, "snapshot.schema_version");
  const projectionMethodId = requiredText(raw.projection_method_id, "snapshot.projection_method_id");
  if (raw.data_tier !== "synthetic") throw new Error("Desktop Twin demo must remain explicitly synthetic.");
  if (schemaVersion !== "1" || projectionMethodId !== "personal_twin_point_in_time_projection_v1") {
    throw new Error("Desktop Twin received an unsupported snapshot contract version.");
  }

  const rawPortfolio = object(raw.portfolio_state, "portfolio_state") as unknown as BackendTwinSnapshot["portfolio_state"];
  const positions = array(rawPortfolio.positions, "portfolio_state.positions").map((item, index) =>
    position(item, `portfolio_state.positions[${index}]`),
  );
  const positionsByRef = new Map(positions.map((item) => [item.stateRef, item]));
  const rawEpisodes = object(raw.episode_refs, "episode_refs") as unknown as BackendTwinSnapshot["episode_refs"];
  const episodeRef = (value: unknown, expected: EpisodeStatus, index: number): TwinEpisodeRefView => {
    const name = `episode_refs.${expected}[${index}]`;
    const item = object(value, name) as unknown as BackendTwinEpisodeRef;
    if (item.status !== expected) throw new Error(`Twin ${name} has the wrong status.`);
    const episodeId = requiredText(item.episode_id, `${name}.episode_id`);
    const owner = episodeOwners.get(episodeId);
    if (owner?.subjectId !== subjectId || owner.status !== expected) {
      throw new Error(`Twin ${name} does not resolve to a matching Episode for this subject.`);
    }
    const stateRef = optionalText(item.current_position_state_ref, `${name}.current_position_state_ref`);
    const currentState = stateRef === null ? null : positionsByRef.get(stateRef) ?? null;
    if (expected === "open" && currentState === null) throw new Error(`Twin ${name} has no resolvable current position state.`);
    if (expected === "closed" && (item.closed_at === null || item.closing_execution_id === null || stateRef !== null)) {
      throw new Error(`Twin ${name} has invalid closed lifecycle semantics.`);
    }
    return {
      episodeId,
      status: expected,
      accountId: requiredText(item.account_id, `${name}.account_id`),
      instrumentId: requiredText(item.instrument_id, `${name}.instrument_id`),
      openedAt: requiredTime(item.opened_at, `${name}.opened_at`),
      closedAt: optionalTime(item.closed_at, `${name}.closed_at`),
      openingExecutionId: requiredText(item.opening_execution_id, `${name}.opening_execution_id`),
      closingExecutionId: optionalText(item.closing_execution_id, `${name}.closing_execution_id`),
      executionRefs: textArray(item.execution_refs, `${name}.execution_refs`),
      decisionRefs: textArray(item.decision_refs, `${name}.decision_refs`),
      evidenceRefs: textArray(item.evidence_refs, `${name}.evidence_refs`),
      currentPositionStateRef: stateRef,
      currentPositionState: currentState,
    };
  };
  const openEpisodes = array(rawEpisodes.open, "episode_refs.open").map((item, index) => episodeRef(item, "open", index));
  const closedEpisodes = array(rawEpisodes.closed, "episode_refs.closed").map((item, index) => episodeRef(item, "closed", index));
  const decisionEvidenceRefs = array(raw.decision_evidence_refs, "decision_evidence_refs").map((item, index) => evidenceRef(item, `decision_evidence_refs[${index}]`));
  const behaviorEvidenceRefs = array(raw.behavior_evidence_refs, "behavior_evidence_refs").map((item, index) => evidenceRef(item, `behavior_evidence_refs[${index}]`));
  for (const item of [...decisionEvidenceRefs, ...behaviorEvidenceRefs]) {
    if (evidenceOwners.get(item.evidenceId) !== subjectId) throw new Error(`Twin Evidence ${item.evidenceId} does not resolve to this subject.`);
  }
  const behaviorState = array(raw.behavior_state, "behavior_state").map((value, index) => {
    const name = `behavior_state[${index}]`;
    const item = object(value, name) as unknown as BackendTwinMetricState;
    const sourceEvidenceId = requiredText(item.source_evidence_id, `${name}.source_evidence_id`);
    if (evidenceOwners.get(sourceEvidenceId) !== subjectId) throw new Error(`Twin ${name} references unknown or cross-subject Evidence.`);
    return {
      metricId: requiredText(item.metric_id, `${name}.metric_id`),
      asOf: requiredTime(item.as_of, `${name}.as_of`),
      value: optionalNumber(item.value, `${name}.value`),
      status: status(item.evidence_status, `${name}.evidence_status`),
      sourceEvidenceId,
      observationCount: item.observation_count === null ? null : integer(item.observation_count, `${name}.observation_count`),
    };
  });
  const summary = object(raw.evidence_summary, "evidence_summary") as unknown as BackendTwinSnapshot["evidence_summary"];
  const quality = object(raw.data_quality_summary, "data_quality_summary") as unknown as BackendTwinSnapshot["data_quality_summary"];
  const selfBaselineRefs = textArray(raw.self_baseline_refs, "self_baseline_refs");
  const peerContextRefs = textArray(raw.peer_context_refs, "peer_context_refs");
  const notableChangeRefs = textArray(raw.notable_change_refs, "notable_change_refs");
  const interventionHistoryRef = optionalText(raw.intervention_history_ref, "intervention_history_ref");
  if (selfBaselineRefs.length || peerContextRefs.length || notableChangeRefs.length || interventionHistoryRef !== null) {
    throw new Error("Desktop Twin v1 received unsupported future capability data.");
  }
  const inputVersionRefs = array(raw.input_version_refs, "input_version_refs").map((item, index) => inputRef(item, `input_version_refs[${index}]`));
  const assertNotFuture = (value: string | null, name: string) => {
    if (value !== null && Date.parse(value) > Date.parse(snapshotAt)) throw new Error(`Twin ${name} exceeds snapshot_at.`);
  };
  assertNotFuture(requiredTime(rawPortfolio.as_of, "portfolio_state.as_of"), "portfolio_state.as_of");
  inputVersionRefs.forEach((item, index) => assertNotFuture(item.asOf, `input_version_refs[${index}].as_of`));
  [...decisionEvidenceRefs, ...behaviorEvidenceRefs].forEach((item, index) => assertNotFuture(item.availableAt, `evidence_refs[${index}].available_at`));
  behaviorState.forEach((item, index) => assertNotFuture(item.asOf, `behavior_state[${index}].as_of`));
  [...openEpisodes, ...closedEpisodes].forEach((item, index) => {
    assertNotFuture(item.openedAt, `episode_refs[${index}].opened_at`);
    assertNotFuture(item.closedAt, `episode_refs[${index}].closed_at`);
  });
  return {
    snapshotId: requiredText(raw.snapshot_id, "snapshot.snapshot_id"),
    subjectId,
    snapshotAt,
    schemaVersion,
    projectionMethodId,
    projectionMethodVersion: requiredText(raw.projection_method_version, "snapshot.projection_method_version"),
    calculationCodeVersion: requiredText(raw.calculation_code_version, "snapshot.calculation_code_version"),
    inputVersionRefs,
    portfolioState: {
      asOf: requiredTime(rawPortfolio.as_of, "portfolio_state.as_of"),
      status: portfolioStatus(rawPortfolio.status, "portfolio_state.status"),
      reason: optionalText(rawPortfolio.reason, "portfolio_state.reason"),
      replayMethodId: optionalText(rawPortfolio.replay_method_id, "portfolio_state.replay_method_id"),
      positions,
    },
    episodes: { open: openEpisodes, closed: closedEpisodes },
    decisionEventRefs: textArray(raw.decision_event_refs, "decision_event_refs"),
    decisionEvidenceRefs,
    behaviorEvidenceRefs,
    behaviorState,
    evidenceSummary: {
      total: integer(summary.total, "evidence_summary.total"),
      complete: integer(summary.complete, "evidence_summary.complete"),
      partial: integer(summary.partial, "evidence_summary.partial"),
      insufficient: integer(summary.insufficient, "evidence_summary.insufficient"),
      experimental: integer(summary.experimental, "evidence_summary.experimental"),
      unavailableMetricIds: textArray(summary.unavailable_metric_ids, "evidence_summary.unavailable_metric_ids"),
    },
    dataQuality: {
      expectedEvidenceCount: integer(quality.expected_evidence_count, "data_quality_summary.expected_evidence_count"),
      referencedEvidenceCount: integer(quality.referenced_evidence_count, "data_quality_summary.referenced_evidence_count"),
      completeEvidenceCount: integer(quality.complete_evidence_count, "data_quality_summary.complete_evidence_count"),
      insufficientEvidenceCount: integer(quality.insufficient_evidence_count, "data_quality_summary.insufficient_evidence_count"),
      availableBehaviorMetricCount: integer(quality.available_behavior_metric_count, "data_quality_summary.available_behavior_metric_count"),
      missingBehaviorMetrics: textArray(quality.missing_behavior_metrics, "data_quality_summary.missing_behavior_metrics"),
      partialEvidenceCount: integer(quality.partial_evidence_count, "data_quality_summary.partial_evidence_count"),
      experimentalEvidenceCount: integer(quality.experimental_evidence_count, "data_quality_summary.experimental_evidence_count"),
      missingEvidenceMetrics: textArray(quality.missing_evidence_metrics, "data_quality_summary.missing_evidence_metrics"),
      portfolioStateStatus: portfolioStatus(quality.portfolio_state_status, "data_quality_summary.portfolio_state_status"),
      openEpisodeCount: integer(quality.open_episode_count, "data_quality_summary.open_episode_count"),
      closedEpisodeCount: integer(quality.closed_episode_count, "data_quality_summary.closed_episode_count"),
      issueCount: integer(quality.issue_count, "data_quality_summary.issue_count"),
      issues: textArray(quality.issues, "data_quality_summary.issues"),
    },
    futureCapabilities: { selfBaselineRefs, peerContextRefs, notableChangeRefs, interventionHistoryRef },
    dataTier: "synthetic",
    limitations: textArray(raw.limitations, "limitations"),
  };
}

export function adaptTwinPayload(
  value: unknown,
  evidenceOwners: readonly EvidenceOwner[],
  episodeOwners: readonly EpisodeOwner[],
) {
  const raw = object(value, "payload") as unknown as BackendTwinPayload;
  if (raw.data_tier !== "synthetic") throw new Error("Desktop Twin payload must remain explicitly synthetic.");
  const owners = new Map(evidenceOwners.map((item) => [item.evidence_id, item.subject_id]));
  const episodes = new Map(episodeOwners.map((item) => [item.episodeId, {
    subjectId: item.subjectId,
    status: item.status,
  }]));
  const historicalSnapshots = array(raw.historical_snapshots, "historical_snapshots").map((item) => snapshot(item, owners, episodes));
  if (historicalSnapshots.some((item, index) => index > 0 && item.snapshotAt <= historicalSnapshots[index - 1].snapshotAt)) {
    throw new Error("Historical Twin snapshots must be chronological.");
  }
  const comparisons = object(raw.comparison, "comparison") as unknown as BackendTwinPayload["comparison"];
  return {
    currentSnapshot: snapshot(raw.current_snapshot, owners, episodes),
    historicalSnapshots,
    comparisons: [
      comparison(comparisons.portfolio_hhi, "comparison.portfolio_hhi"),
      comparison(comparisons.turnover, "comparison.turnover"),
    ],
  };
}
