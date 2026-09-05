import type { EvidenceStatus } from "@/demo/types";

import {
  adaptDecisionOutcomeStory,
  adaptHistoricalCounterfactual,
  type DecisionImmediateOutcomeView,
  type DecisionOutcomeContext,
  type DecisionOutcomeStoryView,
  type HistoricalCounterfactualView,
} from "./decisionOutcome.ts";

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
  data_tier: "synthetic" | "authorized_beta";
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
    currency?: string | null;
    data_tier: "synthetic" | "authorized_beta";
  };
  episode: BackendPositionEpisode;
  decisions: BackendPositionEpisodeDecision[];
  states_by_ref: Record<string, BackendPositionEpisodeState>;
  snapshot: BackendPositionEpisodeSnapshot | null;
  evidence_references: BackendPositionEvidenceReference[];
  price_points: Array<{ observed_at: string; price: number; segment?: string }>;
  path_analysis?: unknown;
  outcome_story: unknown;
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
  outcome: DecisionImmediateOutcomeView;
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
  dataTier: "synthetic" | "authorized_beta";
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
    isSynthetic: boolean;
    currency: string | null;
    dataTier: "synthetic" | "authorized_beta";
  };
  episode: PositionEpisodeView;
  decisions: PositionDecisionView[];
  statesByRef: Record<string, PositionStateView>;
  snapshot: PositionEpisodeSnapshotView | null;
  evidenceReferences: PositionEvidenceReferenceView[];
  pricePoints: Array<{ observedAt: string; price: number; segment: "pre_entry" | "episode" | "post_exit" }>;
  pathAnalysis: EpisodePathAnalysisView;
  outcomeStory: DecisionOutcomeStoryView;
}

export interface PositionEpisodeDemoView {
  dataTier: "synthetic" | "authorized_beta";
  defaultEpisodeId: string;
  entries: PositionEpisodeEntryView[];
}

export type PathContextStatus = "complete" | "partial" | "insufficient";
export type PathPhaseType = "entry" | "scaling_in" | "scaling_out" | "exit";
export type PathContextSegment = "pre_entry" | "episode" | "post_exit";
export type QuantityAtObservationStatus = "available" | "ambiguous" | "unavailable";

export interface DailyMarketObservationView {
  observedAt: string;
  price: number;
  instrumentId: string;
  priceType: string | null;
  dataSource: string | null;
  dataVersion: string | null;
}

export interface PreEntryMarketContextView {
  status: PathContextStatus;
  observations: DailyMarketObservationView[];
  validObservationCount: number;
  requestedObservationCount: number;
  startObservation: DailyMarketObservationView | null;
  endObservation: DailyMarketObservationView | null;
  priceChange: number | null;
  priceReturn: number | null;
  methodVersion: string;
}

export interface MarketContextWindowView {
  segment: PathContextSegment;
  status: PathContextStatus;
  observations: DailyMarketObservationView[];
  validObservationCount: number;
  requestedObservationCount: number | null;
  dailyPathMax: DailyMarketObservationView | null;
  dailyPathMin: DailyMarketObservationView | null;
}

export interface DailyPricePeakDrawdownView {
  peakObservation: DailyMarketObservationView;
  troughObservation: DailyMarketObservationView;
  dailyPricePeakDrawdown: number;
  quantityAtTroughStatus: QuantityAtObservationStatus;
  quantityAtTrough: number | null;
  quantityStatusReason: string | null;
}

export interface MarketPathSegmentView {
  segmentId: string;
  kind: "rise" | "drawdown" | "recovery" | "range";
  validObservationCount: number;
  priceChange: number;
  priceReturn: number | null;
}

export interface DecisionPhaseView {
  phaseId: string;
  episodeId: string;
  phaseType: PathPhaseType;
  taxonomyVersion: string;
  startedAt: string;
  endedAt: string;
  decisionEventIds: string[];
  executionIds: string[];
  quantityBefore: number;
  quantityAfter: number;
  averageCostBefore: number | null;
  averageCostAfter: number | null;
  stateBeforeRef: string;
  stateAfterRef: string;
  methodVersion: string;
}

export interface EpisodePatternObservationView {
  patternId: string;
  episodeId: string;
  patternCode: string;
  methodVersion: string;
  decisionEventIds: string[];
  phaseIds: string[];
  evidenceIds: string[];
  facts: Record<string, unknown>;
}

export interface PathPresentationItemView {
  itemId: string;
  kind: "phase" | "pattern";
  phaseId: string | null;
  patternId: string | null;
  reasonCode: string;
}

export interface EpisodeMarketPathView {
  episodeId: string;
  preEntryContextStatus: PathContextStatus;
  episodeContextStatus: PathContextStatus;
  postExitContextStatus: PathContextStatus;
  preEntryContext: PreEntryMarketContextView;
  episodeMarketPath: MarketContextWindowView;
  postExitContext: MarketContextWindowView;
  dailyPricePeakDrawdown: DailyPricePeakDrawdownView | null;
  marketPathSegments: MarketPathSegmentView[];
  methodId: string;
  methodVersion: string;
  limitations: string[];
}

export interface EpisodePositionPathView {
  episodeId: string;
  maxQuantity: number;
  maxQuantityAsOf: string;
  maxQuantityStateId: string;
}

export interface EpisodePathAnalysisView {
  episodeId: string;
  methodId: string;
  methodVersion: string;
  marketPath: EpisodeMarketPathView;
  positionPath: EpisodePositionPathView;
  phases: DecisionPhaseView[];
  patterns: EpisodePatternObservationView[];
  phaseCounterfactuals: HistoricalCounterfactualView[];
  presentationItems: PathPresentationItemView[];
  limitations: string[];
}

const CONTEXT_STATUSES = ["complete", "partial", "insufficient"] as const;
const PHASE_TYPES = ["entry", "scaling_in", "scaling_out", "exit"] as const;
const SEGMENTS = ["pre_entry", "episode", "post_exit"] as const;
const QUANTITY_STATUSES = ["available", "ambiguous", "unavailable"] as const;
const PATTERN_CODES = [
  "consecutive_scaling_in",
  "consecutive_scaling_out",
  "add_after_positive_market_move",
  "reduce_after_negative_market_move",
  "exit_after_negative_market_move",
  "loss_state_addition_reused",
  "high_quantity_during_daily_price_drawdown",
  "price_following_scale_sequence",
  "long_no_execution_interval",
] as const;

function pathObject(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Position episode ${name} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function pathText(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Position episode ${name} must be a non-empty string.`);
  }
  return value;
}

function pathTexts(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) throw new Error(`Position episode ${name} must be an array.`);
  return value.map((item, index) => pathText(item, `${name}[${index}]`));
}

function pathTimestamp(value: unknown, name: string): string {
  const result = pathText(value, name);
  if (Number.isNaN(Date.parse(result))) throw new Error(`Position episode ${name} must be a timestamp.`);
  return result;
}

function pathEnum<T extends string>(value: unknown, values: readonly T[], name: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    throw new Error(`Position episode ${name} is unsupported.`);
  }
  return value as T;
}

function pathNullable<T>(value: unknown, name: string, parse: (item: unknown, label: string) => T): T | null {
  return value === null ? null : parse(value, name);
}

function observationView(value: unknown, name: string): DailyMarketObservationView {
  const raw = pathObject(value, name);
  return {
    observedAt: pathTimestamp(raw.observed_at, `${name}.observed_at`),
    price: finite(raw.price as number, `${name}.price`),
    instrumentId: pathText(raw.instrument_id, `${name}.instrument_id`),
    priceType: pathNullable(raw.price_type, `${name}.price_type`, pathText),
    dataSource: pathNullable(raw.data_source, `${name}.data_source`, pathText),
    dataVersion: pathNullable(raw.data_version, `${name}.data_version`, pathText),
  };
}

function observations(value: unknown, name: string): DailyMarketObservationView[] {
  if (!Array.isArray(value)) throw new Error(`Position episode ${name} must be an array.`);
  return value.map((item, index) => observationView(item, `${name}[${index}]`));
}

function preEntryContext(value: unknown): PreEntryMarketContextView {
  const raw = pathObject(value, "pre_entry_context");
  return {
    status: pathEnum(raw.status, CONTEXT_STATUSES, "pre_entry_context.status"),
    observations: observations(raw.observations, "pre_entry_context.observations"),
    validObservationCount: finite(raw.valid_observation_count as number, "pre_entry_context.valid_observation_count"),
    requestedObservationCount: finite(raw.requested_observation_count as number, "pre_entry_context.requested_observation_count"),
    startObservation: pathNullable(raw.start_observation, "pre_entry_context.start_observation", observationView),
    endObservation: pathNullable(raw.end_observation, "pre_entry_context.end_observation", observationView),
    priceChange: raw.price_change === null ? null : finite(raw.price_change as number, "pre_entry_context.price_change"),
    priceReturn: raw.price_return === null ? null : finite(raw.price_return as number, "pre_entry_context.price_return"),
    methodVersion: pathText(raw.method_version, "pre_entry_context.method_version"),
  };
}

function marketWindow(value: unknown, name: string, expected: PathContextSegment): MarketContextWindowView {
  const raw = pathObject(value, name);
  const segment = pathEnum(raw.segment, SEGMENTS, `${name}.segment`);
  if (segment !== expected) throw new Error(`Position episode ${name}.segment must be ${expected}.`);
  return {
    segment,
    status: pathEnum(raw.status, CONTEXT_STATUSES, `${name}.status`),
    observations: observations(raw.observations, `${name}.observations`),
    validObservationCount: finite(raw.valid_observation_count as number, `${name}.valid_observation_count`),
    requestedObservationCount: raw.requested_observation_count === null
      ? null
      : finite(raw.requested_observation_count as number, `${name}.requested_observation_count`),
    dailyPathMax: pathNullable(raw.daily_path_max, `${name}.daily_path_max`, observationView),
    dailyPathMin: pathNullable(raw.daily_path_min, `${name}.daily_path_min`, observationView),
  };
}

function drawdownView(value: unknown): DailyPricePeakDrawdownView {
  const raw = pathObject(value, "daily_price_peak_drawdown");
  return {
    peakObservation: observationView(raw.peak_observation, "daily_price_peak_drawdown.peak_observation"),
    troughObservation: observationView(raw.trough_observation, "daily_price_peak_drawdown.trough_observation"),
    dailyPricePeakDrawdown: finite(raw.daily_price_peak_drawdown as number, "daily_price_peak_drawdown.daily_price_peak_drawdown"),
    quantityAtTroughStatus: pathEnum(raw.quantity_at_trough_status, QUANTITY_STATUSES, "daily_price_peak_drawdown.quantity_at_trough_status"),
    quantityAtTrough: raw.quantity_at_trough === null ? null : finite(raw.quantity_at_trough as number, "daily_price_peak_drawdown.quantity_at_trough"),
    quantityStatusReason: pathNullable(raw.quantity_status_reason, "daily_price_peak_drawdown.quantity_status_reason", pathText),
  };
}

function marketPathSegments(value: unknown): MarketPathSegmentView[] {
  if (!Array.isArray(value)) throw new Error("Position episode market_path_segments must be an array.");
  return value.map((item, index) => {
    const raw = pathObject(item, `market_path_segments[${index}]`);
    return {
      segmentId: pathText(raw.segment_id, `market_path_segments[${index}].segment_id`),
      kind: pathEnum(raw.kind, ["rise", "drawdown", "recovery", "range"] as const, `market_path_segments[${index}].kind`),
      validObservationCount: finite(raw.valid_observation_count as number, `market_path_segments[${index}].valid_observation_count`),
      priceChange: finite(raw.price_change as number, `market_path_segments[${index}].price_change`),
      priceReturn: raw.price_return === null ? null : finite(raw.price_return as number, `market_path_segments[${index}].price_return`),
    };
  });
}

function adaptPathAnalysis(
  value: unknown,
  context: DecisionOutcomeContext,
  knownDecisionIds: Set<string>,
): EpisodePathAnalysisView {
  const raw = pathObject(value, "path_analysis");
  if (pathText(raw.episode_id, "path_analysis.episode_id") !== context.episodeId) {
    throw new Error("Position episode path_analysis belongs to another Episode.");
  }
  const marketRaw = pathObject(raw.market_path, "path_analysis.market_path");
  if (pathText(marketRaw.episode_id, "market_path.episode_id") !== context.episodeId) {
    throw new Error("Position episode market_path belongs to another Episode.");
  }
  const positionRaw = pathObject(raw.position_path, "path_analysis.position_path");
  if (pathText(positionRaw.episode_id, "position_path.episode_id") !== context.episodeId) {
    throw new Error("Position episode position_path belongs to another Episode.");
  }
  if (!Array.isArray(raw.phases)) throw new Error("Position episode path_analysis.phases must be an array.");
  if (!Array.isArray(raw.patterns)) throw new Error("Position episode path_analysis.patterns must be an array.");
  if (!Array.isArray(raw.phase_counterfactuals)) throw new Error("Position episode path_analysis.phase_counterfactuals must be an array.");
  if (!Array.isArray(raw.presentation_items)) throw new Error("Position episode path_analysis.presentation_items must be an array.");
  const phases = raw.phases.map((item, index): DecisionPhaseView => {
    const phase = pathObject(item, `phases[${index}]`);
    const decisionEventIds = pathTexts(phase.decision_event_ids, `phases[${index}].decision_event_ids`);
    if (decisionEventIds.length === 0 || decisionEventIds.some((id) => !knownDecisionIds.has(id))) {
      throw new Error(`Position episode phases[${index}] references unknown decisions.`);
    }
    if (pathText(phase.episode_id, `phases[${index}].episode_id`) !== context.episodeId) {
      throw new Error(`Position episode phases[${index}] belongs to another Episode.`);
    }
    return {
      phaseId: pathText(phase.phase_id, `phases[${index}].phase_id`),
      episodeId: context.episodeId,
      phaseType: pathEnum(phase.phase_type, PHASE_TYPES, `phases[${index}].phase_type`),
      taxonomyVersion: pathText(phase.taxonomy_version, `phases[${index}].taxonomy_version`),
      startedAt: pathTimestamp(phase.started_at, `phases[${index}].started_at`),
      endedAt: pathTimestamp(phase.ended_at, `phases[${index}].ended_at`),
      decisionEventIds,
      executionIds: pathTexts(phase.execution_ids, `phases[${index}].execution_ids`),
      quantityBefore: finite(phase.quantity_before as number, `phases[${index}].quantity_before`),
      quantityAfter: finite(phase.quantity_after as number, `phases[${index}].quantity_after`),
      averageCostBefore: phase.average_cost_before === null ? null : finite(phase.average_cost_before as number, `phases[${index}].average_cost_before`),
      averageCostAfter: phase.average_cost_after === null ? null : finite(phase.average_cost_after as number, `phases[${index}].average_cost_after`),
      stateBeforeRef: pathText(phase.state_before_ref, `phases[${index}].state_before_ref`),
      stateAfterRef: pathText(phase.state_after_ref, `phases[${index}].state_after_ref`),
      methodVersion: pathText(phase.method_version, `phases[${index}].method_version`),
    };
  });
  const phaseIds = new Set(phases.map((item) => item.phaseId));
  const patterns = raw.patterns.map((item, index): EpisodePatternObservationView => {
    const pattern = pathObject(item, `patterns[${index}]`);
    const decisionEventIds = pathTexts(pattern.decision_event_ids, `patterns[${index}].decision_event_ids`);
    if (decisionEventIds.some((id) => !knownDecisionIds.has(id))) {
      throw new Error(`Position episode patterns[${index}] references unknown decisions.`);
    }
    const linkedPhases = pathTexts(pattern.phase_ids, `patterns[${index}].phase_ids`);
    if (linkedPhases.some((id) => !phaseIds.has(id))) {
      throw new Error(`Position episode patterns[${index}] references unknown phases.`);
    }
    if (pathText(pattern.episode_id, `patterns[${index}].episode_id`) !== context.episodeId) {
      throw new Error(`Position episode patterns[${index}] belongs to another Episode.`);
    }
    const factsRaw = pattern.facts;
    if (typeof factsRaw !== "object" || factsRaw === null || Array.isArray(factsRaw)) {
      throw new Error(`Position episode patterns[${index}].facts must be an object.`);
    }
    return {
      patternId: pathText(pattern.pattern_id, `patterns[${index}].pattern_id`),
      episodeId: context.episodeId,
      patternCode: pathEnum(pattern.pattern_code, PATTERN_CODES, `patterns[${index}].pattern_code`),
      methodVersion: pathText(pattern.method_version, `patterns[${index}].method_version`),
      decisionEventIds,
      phaseIds: linkedPhases,
      evidenceIds: pathTexts(pattern.evidence_ids, `patterns[${index}].evidence_ids`),
      facts: factsRaw as Record<string, unknown>,
    };
  });
  const patternIds = new Set(patterns.map((item) => item.patternId));
  const presentationItems = raw.presentation_items.map((item, index): PathPresentationItemView => {
    const rawItem = pathObject(item, `presentation_items[${index}]`);
    const kind = pathEnum(rawItem.kind, ["phase", "pattern"] as const, `presentation_items[${index}].kind`);
    const phaseId = pathNullable(rawItem.phase_id, `presentation_items[${index}].phase_id`, pathText);
    const patternId = pathNullable(rawItem.pattern_id, `presentation_items[${index}].pattern_id`, pathText);
    if (kind === "phase" && (phaseId === null || !phaseIds.has(phaseId))) {
      throw new Error(`Position episode presentation_items[${index}] references an unknown phase.`);
    }
    if (kind === "pattern" && (patternId === null || !patternIds.has(patternId))) {
      throw new Error(`Position episode presentation_items[${index}] references an unknown pattern.`);
    }
    if (phaseId !== null && !phaseIds.has(phaseId)) {
      throw new Error(`Position episode presentation_items[${index}] references an unknown phase.`);
    }
    return {
      itemId: pathText(rawItem.item_id, `presentation_items[${index}].item_id`),
      kind,
      phaseId,
      patternId,
      reasonCode: pathText(rawItem.reason_code, `presentation_items[${index}].reason_code`),
    };
  });
  return {
    episodeId: context.episodeId,
    methodId: pathText(raw.method_id, "path_analysis.method_id"),
    methodVersion: pathText(raw.method_version, "path_analysis.method_version"),
    marketPath: {
      episodeId: context.episodeId,
      preEntryContextStatus: pathEnum(marketRaw.pre_entry_context_status, CONTEXT_STATUSES, "market_path.pre_entry_context_status"),
      episodeContextStatus: pathEnum(marketRaw.episode_context_status, CONTEXT_STATUSES, "market_path.episode_context_status"),
      postExitContextStatus: pathEnum(marketRaw.post_exit_context_status, CONTEXT_STATUSES, "market_path.post_exit_context_status"),
      preEntryContext: preEntryContext(marketRaw.pre_entry_context),
      episodeMarketPath: marketWindow(marketRaw.episode_market_path, "episode_market_path", "episode"),
      postExitContext: marketWindow(marketRaw.post_exit_context, "post_exit_context", "post_exit"),
      dailyPricePeakDrawdown: pathNullable(marketRaw.daily_price_peak_drawdown, "daily_price_peak_drawdown", (item) => drawdownView(item)),
      marketPathSegments: marketPathSegments(marketRaw.market_path_segments),
      methodId: pathText(marketRaw.method_id, "market_path.method_id"),
      methodVersion: pathText(marketRaw.method_version, "market_path.method_version"),
      limitations: pathTexts(marketRaw.limitations, "market_path.limitations"),
    },
    positionPath: {
      episodeId: context.episodeId,
      maxQuantity: finite(positionRaw.max_quantity as number, "position_path.max_quantity"),
      maxQuantityAsOf: pathTimestamp(positionRaw.max_quantity_as_of, "position_path.max_quantity_as_of"),
      maxQuantityStateId: pathText(positionRaw.max_quantity_state_id, "position_path.max_quantity_state_id"),
    },
    phases,
    patterns,
    phaseCounterfactuals: raw.phase_counterfactuals.map((item, index) =>
      adaptHistoricalCounterfactual(item, context, knownDecisionIds, `phase_counterfactuals[${index}]`),
    ),
    presentationItems,
    limitations: pathTexts(raw.limitations, "path_analysis.limitations"),
  };
}

export function selectPrimaryPathItems(path: EpisodePathAnalysisView): PathPresentationItemView[] {
  return path.presentationItems.slice(0, 6);
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

function adaptEntry(entry: BackendPositionEpisodeEntry, expectedTier: "synthetic" | "authorized_beta" = "synthetic"): PositionEpisodeEntryView {
  if (entry.episode.data_tier !== expectedTier) throw new Error("Position episode data tier does not match its transport.");
  if (entry.instrument.currency != null && !/^[A-Z]{3}$/.test(entry.instrument.currency)) throw new Error("Invalid listing currency metadata.");
  for (const [ref, state] of Object.entries(entry.states_by_ref)) {
    if (ref !== state.state_id || state.subject_id !== entry.episode.subject_id || state.account_id !== entry.episode.account_id || state.instrument_id !== entry.episode.instrument_id) {
      throw new Error("Position state ownership/reference mismatch.");
    }
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
    || entry.instrument.data_tier !== expectedTier
    || entry.instrument.is_synthetic !== (expectedTier === "synthetic")
  ) {
    throw new Error("Position episode instrument metadata must match its synthetic Episode.");
  }
  const displayName = typeof entry.instrument.display_name === "string"
    && entry.instrument.display_name.trim().length > 0
    ? entry.instrument.display_name.trim()
    : episode.instrumentId;
  const baseDecisions = entry.decisions.map((decision) => {
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

  const outcomeContext = {
    subjectId: episode.subjectId,
    accountId: episode.accountId,
    instrumentId: episode.instrumentId,
    episodeId: episode.episodeId,
    episodeStatus: episode.status,
    decisions: baseDecisions.map((decision) => ({
      decisionId: decision.decisionId,
      executionId: decision.executionId,
      side: decision.side,
      eventType: decision.decisionType,
    })),
  };
  const outcomeStory = adaptDecisionOutcomeStory(entry.outcome_story, outcomeContext);
  const knownDecisionIds = new Set(baseDecisions.map((decision) => decision.decisionId));
  const pathAnalysis = adaptPathAnalysis(entry.path_analysis, outcomeContext, knownDecisionIds);
  const outcomeByDecision = new Map(
    outcomeStory.decisionOutcomes.map((outcome) => [outcome.decisionEventId, outcome]),
  );
  const decisions: PositionDecisionView[] = baseDecisions.map((decision) => {
    const outcome = outcomeByDecision.get(decision.decisionId);
    if (!outcome) throw new Error(`Position episode decision ${decision.decisionId} has no Outcome.`);
    if (
      outcome.before.stateRef !== decision.stateBeforeRef
      || outcome.after.stateRef !== decision.stateAfterRef
      || outcome.executedQuantity !== decision.executedQuantity
      || outcome.executionPrice !== decision.executionPrice
      || outcome.executionFee !== decision.fees
    ) throw new Error(`Position episode decision ${decision.decisionId} Outcome does not match replay facts.`);
    for (const [result, state] of [[outcome.before, decision.stateBefore], [outcome.after, decision.stateAfter]] as const) {
      if (result.quantity !== state.quantity || result.averageCost !== state.averageCost) {
        throw new Error("Outcome state values do not match referenced replay state.");
      }
    }
    return { ...decision, outcome };
  });

  if (episode.status === "open") {
    if (entry.price_points.some((point) => point.segment === "post_exit")) throw new Error("Open Episode cannot have post-exit context.");
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
      isSynthetic: entry.instrument.is_synthetic,
      currency: expectedTier === "synthetic" ? "CNY" : entry.instrument.currency ?? null,
      dataTier: expectedTier,
    },
    episode,
    decisions,
    statesByRef,
    snapshot,
    evidenceReferences: entry.evidence_references.map(evidenceReferenceView),
    pricePoints: entry.price_points.map((point) => ({
      observedAt: point.observed_at,
      price: finite(point.price, "price point"),
      segment: pathEnum(point.segment, SEGMENTS, "price_points.segment"),
    })),
    pathAnalysis,
    outcomeStory,
  };
}

export function adaptPositionEpisodeDemo(value: BackendPositionEpisodeDemo): PositionEpisodeDemoView {
  if (value.data_tier !== "synthetic") {
    throw new Error("Desktop position episode demo must remain explicitly synthetic.");
  }
  const entries = value.entries.map((entry) => adaptEntry(entry));
  if (!entries.some((entry) => entry.episode.episodeId === value.default_episode_id)) {
    throw new Error("Position episode demo default episode is missing.");
  }
  return {
    dataTier: value.data_tier,
    defaultEpisodeId: value.default_episode_id,
    entries,
  };
}

export function adaptRuntimePositionEpisodeEntry(value: unknown): PositionEpisodeEntryView {
  return adaptEntry(value as BackendPositionEpisodeEntry, "authorized_beta");
}
