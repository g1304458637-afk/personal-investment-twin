import type { EvidenceStatus } from "@/demo/types";

export type PositionEpisodeStatus = "open" | "closed";
export type PositionDecisionType =
  | "open_position"
  | "add_position"
  | "reduce_position"
  | "close_position";

export interface BackendPositionEpisodeState {
  state_id: string;
  subject_id: string;
  account_id: string;
  instrument_id: string;
  as_of: string;
  boundary: "before_execution" | "after_execution" | "as_of_valuation";
  execution_id: string | null;
  quantity: number;
  average_cost: number | null;
  valuation_at: string | null;
  valuation_price: number | null;
  market_value: number | null;
  replay_method_id: string;
}

export interface BackendPositionEpisodeDecision {
  decision_id: string;
  episode_id: string;
  execution_id: string;
  occurred_at: string;
  decision_type: PositionDecisionType;
  side: "BUY" | "SELL";
  executed_quantity: number;
  execution_price: number;
  fees: number;
  state_before_ref: string;
  state_after_ref: string;
  evidence_refs: string[];
}

export interface BackendPositionEvidenceReference {
  evidence_id: string;
  metric_id: string;
  method_id: string;
  method_version: string;
  evidence_status: EvidenceStatus;
  evidence_reason: string | null;
  available_at: string;
}

export interface BackendPositionEpisode {
  episode_id: string;
  subject_id: string;
  account_id: string;
  instrument_id: string;
  status: PositionEpisodeStatus;
  opened_at: string;
  closed_at: string | null;
  opening_execution_id: string;
  closing_execution_id: string | null;
  execution_refs: string[];
  decision_refs: string[];
  evidence_refs: string[];
  duration_days: number;
  duration_kind: "final" | "so_far";
  replay_method_id: string;
  calculation_code_version: string;
  data_tier: "synthetic";
  limitations: string[];
}

export interface BackendPositionEpisodeSnapshot {
  episode_id: string;
  as_of: string;
  position_state_ref: string;
}

export interface BackendPositionEpisodeEntry {
  instrument: {
    instrument_id: string;
    display_name: string | null;
    is_synthetic: boolean;
    data_tier: "synthetic";
  };
  episode: BackendPositionEpisode;
  decisions: BackendPositionEpisodeDecision[];
  states_by_ref: Record<string, BackendPositionEpisodeState>;
  snapshot: BackendPositionEpisodeSnapshot | null;
  evidence_references: BackendPositionEvidenceReference[];
  price_points: Array<{ observed_at: string; price: number }>;
}

export interface BackendPositionEpisodeDemo {
  data_tier: "synthetic";
  default_episode_id: string;
  entries: BackendPositionEpisodeEntry[];
}

export interface PositionStateView {
  stateId: string;
  subjectId: string;
  accountId: string;
  instrumentId: string;
  asOf: string;
  boundary: BackendPositionEpisodeState["boundary"];
  executionId: string | null;
  quantity: number;
  averageCost: number | null;
  valuationAt: string | null;
  valuationPrice: number | null;
  marketValue: number | null;
  replayMethodId: string;
}

export interface PositionEvidenceReferenceView {
  evidenceId: string;
  metricId: string;
  methodId: string;
  methodVersion: string;
  status: EvidenceStatus;
  reason: string | null;
  availableAt: string;
}

export interface PositionDecisionView {
  decisionId: string;
  episodeId: string;
  executionId: string;
  occurredAt: string;
  decisionType: PositionDecisionType;
  side: "BUY" | "SELL";
  executedQuantity: number;
  executionPrice: number;
  fees: number;
  stateBeforeRef: string;
  stateAfterRef: string;
  stateBefore: PositionStateView;
  stateAfter: PositionStateView;
  evidenceRefs: string[];
}

export interface PositionEpisodeView {
  episodeId: string;
  subjectId: string;
  accountId: string;
  instrumentId: string;
  status: PositionEpisodeStatus;
  openedAt: string;
  closedAt: string | null;
  openingExecutionId: string;
  closingExecutionId: string | null;
  executionRefs: string[];
  decisionRefs: string[];
  evidenceRefs: string[];
  durationDays: number;
  durationKind: "final" | "so_far";
  replayMethodId: string;
  calculationCodeVersion: string;
  dataTier: "synthetic";
  limitations: string[];
}

export interface PositionEpisodeSnapshotView {
  episodeId: string;
  asOf: string;
  positionStateRef: string;
  positionState: PositionStateView;
}

export interface PositionEpisodeEntryView {
  instrument: {
    instrumentId: string;
    displayName: string;
    isSynthetic: true;
    dataTier: "synthetic";
  };
  episode: PositionEpisodeView;
  decisions: PositionDecisionView[];
  statesByRef: Record<string, PositionStateView>;
  snapshot: PositionEpisodeSnapshotView | null;
  evidenceReferences: PositionEvidenceReferenceView[];
  pricePoints: Array<{ observedAt: string; price: number }>;
}

export interface PositionEpisodeDemoView {
  dataTier: "synthetic";
  defaultEpisodeId: string;
  entries: PositionEpisodeEntryView[];
}

function finite(value: number, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Position episode ${name} must be finite.`);
  }
  return value;
}

function stateView(state: BackendPositionEpisodeState): PositionStateView {
  return {
    stateId: state.state_id,
    subjectId: state.subject_id,
    accountId: state.account_id,
    instrumentId: state.instrument_id,
    asOf: state.as_of,
    boundary: state.boundary,
    executionId: state.execution_id,
    quantity: finite(state.quantity, "state quantity"),
    averageCost: state.average_cost === null ? null : finite(state.average_cost, "state average cost"),
    valuationAt: state.valuation_at,
    valuationPrice: state.valuation_price === null ? null : finite(state.valuation_price, "state valuation price"),
    marketValue: state.market_value === null ? null : finite(state.market_value, "state market value"),
    replayMethodId: state.replay_method_id,
  };
}

function evidenceReferenceView(reference: BackendPositionEvidenceReference): PositionEvidenceReferenceView {
  return {
    evidenceId: reference.evidence_id,
    metricId: reference.metric_id,
    methodId: reference.method_id,
    methodVersion: reference.method_version,
    status: reference.evidence_status,
    reason: reference.evidence_reason,
    availableAt: reference.available_at,
  };
}

function requiredState(
  statesByRef: Record<string, PositionStateView>,
  ref: string,
  decisionId: string,
): PositionStateView {
  const state = statesByRef[ref];
  if (!state) {
    throw new Error(`Position episode decision ${decisionId} references missing state ${ref}.`);
  }
  return state;
}

function adaptEntry(entry: BackendPositionEpisodeEntry): PositionEpisodeEntryView {
  if (entry.episode.data_tier !== "synthetic") {
    throw new Error("Desktop position episode demo must remain explicitly synthetic.");
  }
  const statesByRef = Object.fromEntries(
    Object.entries(entry.states_by_ref).map(([ref, state]) => [ref, stateView(state)]),
  );
  const episode: PositionEpisodeView = {
    episodeId: entry.episode.episode_id,
    subjectId: entry.episode.subject_id,
    accountId: entry.episode.account_id,
    instrumentId: entry.episode.instrument_id,
    status: entry.episode.status,
    openedAt: entry.episode.opened_at,
    closedAt: entry.episode.closed_at,
    openingExecutionId: entry.episode.opening_execution_id,
    closingExecutionId: entry.episode.closing_execution_id,
    executionRefs: entry.episode.execution_refs,
    decisionRefs: entry.episode.decision_refs,
    evidenceRefs: entry.episode.evidence_refs,
    durationDays: finite(entry.episode.duration_days, "duration"),
    durationKind: entry.episode.duration_kind,
    replayMethodId: entry.episode.replay_method_id,
    calculationCodeVersion: entry.episode.calculation_code_version,
    dataTier: entry.episode.data_tier,
    limitations: entry.episode.limitations,
  };
  if (
    entry.instrument.instrument_id !== episode.instrumentId
    || entry.instrument.data_tier !== "synthetic"
    || entry.instrument.is_synthetic !== true
  ) {
    throw new Error("Position episode instrument metadata must match its synthetic Episode.");
  }
  const displayName = typeof entry.instrument.display_name === "string"
    && entry.instrument.display_name.trim().length > 0
    ? entry.instrument.display_name.trim()
    : episode.instrumentId;
  const decisions = entry.decisions.map((decision) => {
    if (decision.episode_id !== episode.episodeId) {
      throw new Error(`Position episode decision ${decision.decision_id} belongs to another Episode.`);
    }
    return {
      decisionId: decision.decision_id,
      episodeId: decision.episode_id,
      executionId: decision.execution_id,
      occurredAt: decision.occurred_at,
      decisionType: decision.decision_type,
      side: decision.side,
      executedQuantity: finite(decision.executed_quantity, "decision quantity"),
      executionPrice: finite(decision.execution_price, "decision execution price"),
      fees: finite(decision.fees, "decision fees"),
      stateBeforeRef: decision.state_before_ref,
      stateAfterRef: decision.state_after_ref,
      stateBefore: requiredState(statesByRef, decision.state_before_ref, decision.decision_id),
      stateAfter: requiredState(statesByRef, decision.state_after_ref, decision.decision_id),
      evidenceRefs: decision.evidence_refs,
    };
  });

  if (episode.status === "open") {
    if (episode.closedAt !== null || episode.closingExecutionId !== null) {
      throw new Error("Open position episode must not expose a close timestamp or closing execution.");
    }
    if (!entry.snapshot) {
      throw new Error("Open position episode must provide an as-of valuation snapshot.");
    }
    if (decisions.some((decision) => decision.decisionType === "close_position")) {
      throw new Error("Open position episode must not contain a close decision.");
    }
  } else {
    if (episode.closedAt === null || episode.closingExecutionId === null) {
      throw new Error("Closed position episode must expose its real closing execution.");
    }
    if (!decisions.some((decision) => decision.decisionType === "close_position")) {
      throw new Error("Closed position episode must contain a close decision.");
    }
  }

  if (entry.snapshot && entry.snapshot.episode_id !== episode.episodeId) {
    throw new Error("Position episode snapshot belongs to another Episode.");
  }
  const snapshot = entry.snapshot
    ? {
        episodeId: entry.snapshot.episode_id,
        asOf: entry.snapshot.as_of,
        positionStateRef: entry.snapshot.position_state_ref,
        positionState: requiredState(
          statesByRef,
          entry.snapshot.position_state_ref,
          entry.snapshot.episode_id,
        ),
      }
    : null;

  return {
    instrument: {
      instrumentId: episode.instrumentId,
      displayName,
      isSynthetic: true,
      dataTier: "synthetic",
    },
    episode,
    decisions,
    statesByRef,
    snapshot,
    evidenceReferences: entry.evidence_references.map(evidenceReferenceView),
    pricePoints: entry.price_points.map((point) => ({
      observedAt: point.observed_at,
      price: finite(point.price, "price point"),
    })),
  };
}

export function adaptPositionEpisodeDemo(value: BackendPositionEpisodeDemo): PositionEpisodeDemoView {
  if (value.data_tier !== "synthetic") {
    throw new Error("Desktop position episode demo must remain explicitly synthetic.");
  }
  const entries = value.entries.map(adaptEntry);
  if (!entries.some((entry) => entry.episode.episodeId === value.default_episode_id)) {
    throw new Error("Position episode demo default episode is missing.");
  }
  return {
    dataTier: value.data_tier,
    defaultEpisodeId: value.default_episode_id,
    entries,
  };
}
