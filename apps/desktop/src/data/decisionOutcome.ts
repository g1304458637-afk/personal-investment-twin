export type OutcomeResultKind = "realized" | "marked" | "counterfactual";
export type OutcomeResultBasis = "net_pnl" | "gross_pnl_before_incremental_friction";
export type OutcomeResultSign = "profit" | "flat" | "loss";
export type OutcomeRelation =
  | "deterministic_state_transition"
  | "accounting_realized_result"
  | "marked_position_result"
  | "historical_market_followup"
  | "registered_baseline_comparison"
  | "historical_counterfactual"
  | "statistical_association";
export type CounterfactualFeasibility =
  | "complete"
  | "infeasible_downstream_execution"
  | "insufficient_counterfactual_data"
  | "unsupported_scenario";
export type CounterfactualScenario =
  | "omit_event_until_next_decision_v1"
  | "omit_event_preserve_later_executions_v1"
  | "existing_exit_evidence_reuse_v1";
export type OutcomeComparisonStatus =
  | "complete"
  | "not_applicable"
  | "unavailable_result_basis_mismatch";
export type OutcomeTransition =
  | "matched"
  | "loss_reduced"
  | "loss_increased"
  | "loss_to_flat"
  | "loss_to_profit"
  | "profit_increased"
  | "profit_reduced"
  | "profit_to_flat"
  | "profit_to_loss"
  | "flat_to_profit"
  | "flat_to_loss";

export interface AuthoritativeSourceView {
  sourceKind: string;
  sourceRecordId: string;
  replayScopeId: string | null;
  vectorbtRecordId: number | null;
  executionRefs: string[];
}

export interface OutcomeResultView {
  resultKind: OutcomeResultKind;
  resultBasis: OutcomeResultBasis;
  pnl: number;
  returnValue: number | null;
  resultSign: OutcomeResultSign;
  positionStatus: "open" | "closed" | "absent";
  recordedEntryFees: number;
  recordedExitFees: number;
  valuationAt: string | null;
  valuationPrice: number | null;
  source: AuthoritativeSourceView;
}

export interface EpisodeOutcomeView {
  outcomeId: string;
  episodeId: string;
  subjectId: string;
  accountId: string;
  instrumentId: string;
  episodeStatus: "open" | "closed";
  analysisAsOf: string;
  relationType: "accounting_realized_result" | "marked_position_result";
  actualResult: OutcomeResultView;
  decisionEventRefs: string[];
  executionRefs: string[];
  durationDays: number;
  durationKind: "so_far" | "final";
  methodId: string;
  methodVersion: string;
  calculationCodeVersion: string;
  limitations: string[];
}

export interface DecisionOutcomeStateView {
  stateRef: string;
  quantity: number;
  averageCost: number | null;
  positionStatus: "flat" | "open";
}

export interface DecisionImmediateOutcomeView {
  outcomeId: string;
  subjectId: string;
  accountId: string;
  instrumentId: string;
  episodeId: string;
  decisionEventId: string;
  eventType: string;
  eventTime: string;
  relationTypes: OutcomeRelation[];
  before: DecisionOutcomeStateView;
  executionId: string;
  side: "BUY" | "SELL";
  executedQuantity: number;
  executionPrice: number;
  executionFee: number;
  executionSource: AuthoritativeSourceView;
  after: DecisionOutcomeStateView;
  immediateResult: OutcomeResultView | null;
  episodeResultRef: string;
  evidenceRefs: string[];
  methodId: string;
  methodVersion: string;
  calculationCodeVersion: string;
  limitations: string[];
}

export interface OutcomeComparisonView {
  status: OutcomeComparisonStatus;
  resultBasis: OutcomeResultBasis | null;
  pnlDifference: number | null;
  actualResultSign: OutcomeResultSign | null;
  counterfactualResultSign: OutcomeResultSign | null;
  resultTransition: OutcomeTransition | null;
}

export interface HistoricalCounterfactualView {
  counterfactualId: string;
  subjectId: string;
  accountId: string;
  instrumentId: string;
  episodeId: string;
  decisionEventId: string;
  scenarioId: CounterfactualScenario;
  scenarioVersion: string;
  methodId: string;
  methodVersion: string;
  calculationCodeVersion: string;
  relationType: "historical_counterfactual" | "registered_baseline_comparison";
  analysisAsOf: string;
  decisionAt: string;
  evaluationEnd: string | null;
  intervention: { changedAction: string; changedExecutionRefs: string[] };
  heldConstant: string[];
  downstreamOrderPolicy: string;
  priceBasis: string;
  frictionBasis: string;
  feasibilityStatus: CounterfactualFeasibility;
  infeasibleReason: string | null;
  firstConflictingExecutionId: string | null;
  actualResult: OutcomeResultView | null;
  counterfactualResult: OutcomeResultView | null;
  comparison: OutcomeComparisonView;
  baselineEvidenceRef: string | null;
  dataTier: "synthetic";
  limitations: string[];
}

export interface ExitFollowupView {
  evidenceId: string;
  evidenceStatus: "complete" | "insufficient_evidence";
  evidenceReason: string | null;
  actualExitPrice: number | null;
  exitSessionMarketPrice: number | null;
  counterfactualExitPrice: number | null;
  counterfactualExitTime: string | null;
  postExitAssetReturn: number | null;
  comparison: string | null;
  policyId: string | null;
  policySessions: number | null;
  limitations: string[];
}

export interface DecisionOutcomeStoryView {
  episodeOutcome: EpisodeOutcomeView;
  decisionOutcomes: DecisionImmediateOutcomeView[];
  counterfactuals: HistoricalCounterfactualView[];
  exitFollowup: ExitFollowupView | null;
}

export interface DecisionOutcomeContext {
  subjectId: string;
  accountId: string;
  instrumentId: string;
  episodeId: string;
  episodeStatus: "open" | "closed";
  decisions: Array<{ decisionId: string; executionId: string; side: "BUY" | "SELL"; eventType?: string }>;
}

function object(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Decision Outcome ${name} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`Decision Outcome ${name} is required.`);
  }
  return value;
}

function timestamp(value: unknown, name: string): string {
  const result = text(value, name);
  if (Number.isNaN(Date.parse(result))) throw new Error(`Decision Outcome ${name} must be a timestamp.`);
  return result;
}

function nullableTimestamp(value: unknown, name: string): string | null {
  return value === null ? null : timestamp(value, name);
}

function finite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Decision Outcome ${name} must be finite.`);
  }
  return value;
}

function nullableFinite(value: unknown, name: string): number | null {
  return value === null ? null : finite(value, name);
}

function enumValue<T extends string>(value: unknown, values: readonly T[], name: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    throw new Error(`Decision Outcome ${name} is unsupported.`);
  }
  return value as T;
}

function texts(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) throw new Error(`Decision Outcome ${name} must be an array.`);
  return value.map((item, index) => text(item, `${name}[${index}]`));
}

function source(value: unknown): AuthoritativeSourceView {
  const raw = object(value, "source");
  const vectorbtRecordId = raw.vectorbt_record_id === null
    ? null
    : finite(raw.vectorbt_record_id, "source.vectorbt_record_id");
  if (vectorbtRecordId !== null && !Number.isInteger(vectorbtRecordId)) {
    throw new Error("Decision Outcome source.vectorbt_record_id must be an integer.");
  }
  return {
    sourceKind: enumValue(raw.source_kind, [
      "vectorbt_order", "vectorbt_exit_trade", "vectorbt_position",
      "vectorbt_replay_position_absent", "registered_counterfactual_position_absent",
      "existing_exit_evidence",
    ], "source.source_kind"),
    sourceRecordId: text(raw.source_record_id, "source.source_record_id"),
    replayScopeId: raw.replay_scope_id === null ? null : text(raw.replay_scope_id, "source.replay_scope_id"),
    vectorbtRecordId,
    executionRefs: texts(raw.execution_refs, "source.execution_refs"),
  };
}

function result(value: unknown, name: string): OutcomeResultView {
  const raw = object(value, name);
  return {
    resultKind: enumValue(raw.result_kind, ["realized", "marked", "counterfactual"], `${name}.result_kind`),
    resultBasis: enumValue(raw.result_basis, ["net_pnl", "gross_pnl_before_incremental_friction"], `${name}.result_basis`),
    pnl: finite(raw.pnl, `${name}.pnl`),
    returnValue: nullableFinite(raw.return_value, `${name}.return_value`),
    resultSign: enumValue(raw.result_sign, ["profit", "flat", "loss"], `${name}.result_sign`),
    positionStatus: enumValue(raw.position_status, ["open", "closed", "absent"], `${name}.position_status`),
    recordedEntryFees: finite(raw.recorded_entry_fees, `${name}.recorded_entry_fees`),
    recordedExitFees: finite(raw.recorded_exit_fees, `${name}.recorded_exit_fees`),
    valuationAt: nullableTimestamp(raw.valuation_at, `${name}.valuation_at`),
    valuationPrice: nullableFinite(raw.valuation_price, `${name}.valuation_price`),
    source: source(raw.source),
  };
}

function state(value: unknown, name: string): DecisionOutcomeStateView {
  const raw = object(value, name);
  return {
    stateRef: text(raw.state_ref, `${name}.state_ref`),
    quantity: finite(raw.quantity, `${name}.quantity`),
    averageCost: nullableFinite(raw.average_cost, `${name}.average_cost`),
    positionStatus: enumValue(raw.position_status, ["flat", "open"], `${name}.position_status`),
  };
}

function assertOwnership(raw: Record<string, unknown>, context: DecisionOutcomeContext, name: string) {
  if (
    raw.subject_id !== context.subjectId
    || raw.account_id !== context.accountId
    || raw.instrument_id !== context.instrumentId
    || raw.episode_id !== context.episodeId
  ) {
    throw new Error(`Decision Outcome ${name} ownership does not match the Position Episode.`);
  }
}

function comparison(value: unknown): OutcomeComparisonView {
  const raw = object(value, "comparison");
  const status = enumValue(raw.comparison_status, [
    "complete", "not_applicable", "unavailable_result_basis_mismatch",
  ], "comparison.comparison_status");
  const parsed: OutcomeComparisonView = {
    status,
    resultBasis: raw.result_basis === null ? null : enumValue<OutcomeResultBasis>(raw.result_basis, ["net_pnl", "gross_pnl_before_incremental_friction"], "comparison.result_basis"),
    pnlDifference: nullableFinite(raw.pnl_difference, "comparison.pnl_difference"),
    actualResultSign: raw.actual_result_sign === null ? null : enumValue<OutcomeResultSign>(raw.actual_result_sign, ["profit", "flat", "loss"], "comparison.actual_result_sign"),
    counterfactualResultSign: raw.counterfactual_result_sign === null ? null : enumValue<OutcomeResultSign>(raw.counterfactual_result_sign, ["profit", "flat", "loss"], "comparison.counterfactual_result_sign"),
    resultTransition: raw.result_transition === null ? null : enumValue<OutcomeTransition>(raw.result_transition, [
      "matched", "loss_reduced", "loss_increased", "loss_to_flat", "loss_to_profit",
      "profit_increased", "profit_reduced", "profit_to_flat", "profit_to_loss",
      "flat_to_profit", "flat_to_loss",
    ], "comparison.result_transition"),
  };
  if (status === "complete" && (
    parsed.resultBasis === null || parsed.pnlDifference === null
    || parsed.actualResultSign === null || parsed.counterfactualResultSign === null
    || parsed.resultTransition === null
  )) throw new Error("Decision Outcome complete comparison is incomplete.");
  if (status !== "complete" && (parsed.pnlDifference !== null || parsed.resultTransition !== null)) {
    throw new Error("Decision Outcome unavailable comparison must not expose a difference or transition.");
  }
  return parsed;
}

function exitFollowup(value: unknown): ExitFollowupView | null {
  if (value === null) return null;
  const raw = object(value, "exit_followup");
  return {
    evidenceId: text(raw.evidence_id, "exit_followup.evidence_id"),
    evidenceStatus: enumValue(raw.evidence_status, ["complete", "insufficient_evidence"], "exit_followup.evidence_status"),
    evidenceReason: raw.evidence_reason === null ? null : text(raw.evidence_reason, "exit_followup.evidence_reason"),
    actualExitPrice: nullableFinite(raw.actual_exit_price, "exit_followup.actual_exit_price"),
    exitSessionMarketPrice: nullableFinite(raw.exit_session_market_price, "exit_followup.exit_session_market_price"),
    counterfactualExitPrice: nullableFinite(raw.counterfactual_exit_price, "exit_followup.counterfactual_exit_price"),
    counterfactualExitTime: nullableTimestamp(raw.counterfactual_exit_time, "exit_followup.counterfactual_exit_time"),
    postExitAssetReturn: nullableFinite(raw.post_exit_asset_return, "exit_followup.post_exit_asset_return"),
    comparison: raw.comparison === null ? null : text(raw.comparison, "exit_followup.comparison"),
    policyId: raw.policy_id === null ? null : text(raw.policy_id, "exit_followup.policy_id"),
    policySessions: nullableFinite(raw.policy_sessions, "exit_followup.policy_sessions"),
    limitations: texts(raw.limitations, "exit_followup.limitations"),
  };
}

export function adaptDecisionOutcomeStory(
  value: unknown,
  context: DecisionOutcomeContext,
): DecisionOutcomeStoryView {
  const raw = object(value, "story");
  const episodeRaw = object(raw.episode_outcome, "episode_outcome");
  assertOwnership(episodeRaw, context, "episode_outcome");
  const episodeStatus = enumValue(episodeRaw.episode_status, ["open", "closed"], "episode_outcome.episode_status");
  if (episodeStatus !== context.episodeStatus) throw new Error("Decision Outcome Episode status does not match lifecycle status.");
  const episodeResult = result(episodeRaw.actual_result, "episode_outcome.actual_result");
  if (
    (episodeStatus === "open" && (episodeResult.resultKind !== "marked" || episodeResult.positionStatus !== "open"))
    || (episodeStatus === "closed" && (episodeResult.resultKind !== "realized" || episodeResult.positionStatus !== "closed"))
  ) throw new Error("Decision Outcome Episode result semantics do not match lifecycle status.");
  const episodeOutcome: EpisodeOutcomeView = {
    outcomeId: text(episodeRaw.outcome_id, "episode_outcome.outcome_id"),
    episodeId: context.episodeId,
    subjectId: context.subjectId,
    accountId: context.accountId,
    instrumentId: context.instrumentId,
    episodeStatus,
    analysisAsOf: timestamp(episodeRaw.analysis_as_of, "episode_outcome.analysis_as_of"),
    relationType: enumValue(episodeRaw.relation_type, ["accounting_realized_result", "marked_position_result"], "episode_outcome.relation_type"),
    actualResult: episodeResult,
    decisionEventRefs: texts(episodeRaw.decision_event_refs, "episode_outcome.decision_event_refs"),
    executionRefs: texts(episodeRaw.execution_refs, "episode_outcome.execution_refs"),
    durationDays: finite(episodeRaw.duration_days, "episode_outcome.duration_days"),
    durationKind: enumValue(episodeRaw.duration_kind, ["so_far", "final"], "episode_outcome.duration_kind"),
    methodId: text(episodeRaw.method_id, "episode_outcome.method_id"),
    methodVersion: text(episodeRaw.method_version, "episode_outcome.method_version"),
    calculationCodeVersion: text(episodeRaw.calculation_code_version, "episode_outcome.calculation_code_version"),
    limitations: texts(episodeRaw.limitations, "episode_outcome.limitations"),
  };
  if (
    (episodeStatus === "open" && episodeOutcome.relationType !== "marked_position_result")
    || (episodeStatus === "closed" && episodeOutcome.relationType !== "accounting_realized_result")
  ) throw new Error("Decision Outcome Episode relation does not match lifecycle status.");
  const known = new Map(context.decisions.map((item) => [item.decisionId, item]));
  if (!Array.isArray(raw.decision_outcomes)) throw new Error("Decision Outcome decision_outcomes must be an array.");
  const decisionOutcomes = raw.decision_outcomes.map((value, index): DecisionImmediateOutcomeView => {
    const item = object(value, `decision_outcomes[${index}]`);
    assertOwnership(item, context, `decision_outcomes[${index}]`);
    const decisionEventId = text(item.decision_event_id, "decision_event_id");
    const expected = known.get(decisionEventId);
    if (
      !expected
      || item.execution_id !== expected.executionId
      || item.side !== expected.side
      || (expected.eventType !== undefined && item.event_type !== expected.eventType)
    ) {
      throw new Error(`Decision Outcome ${decisionEventId} does not resolve to the lifecycle event.`);
    }
    const immediateResult = item.immediate_result === null ? null : result(item.immediate_result, "immediate_result");
    if ((expected.side === "BUY" && immediateResult !== null) || (expected.side === "SELL" && immediateResult?.resultKind !== "realized")) {
      throw new Error(`Decision Outcome ${decisionEventId} has invalid realized-result semantics.`);
    }
    return {
      outcomeId: text(item.outcome_id, "decision_outcome.outcome_id"), subjectId: context.subjectId,
      accountId: context.accountId, instrumentId: context.instrumentId, episodeId: context.episodeId,
      decisionEventId, eventType: text(item.event_type, "decision_outcome.event_type"),
      eventTime: timestamp(item.event_time, "decision_outcome.event_time"),
      relationTypes: texts(item.relation_types, "decision_outcome.relation_types").map((relation) => enumValue(relation, [
        "deterministic_state_transition", "accounting_realized_result", "marked_position_result",
        "historical_market_followup", "registered_baseline_comparison", "historical_counterfactual", "statistical_association",
      ], "decision_outcome.relation_type")),
      before: state(item.before, "decision_outcome.before"), executionId: expected.executionId,
      side: expected.side, executedQuantity: finite(item.executed_quantity, "decision_outcome.executed_quantity"),
      executionPrice: finite(item.execution_price, "decision_outcome.execution_price"),
      executionFee: finite(item.execution_fee, "decision_outcome.execution_fee"),
      executionSource: source(item.execution_source), after: state(item.after, "decision_outcome.after"),
      immediateResult, episodeResultRef: text(item.episode_result_ref, "decision_outcome.episode_result_ref"),
      evidenceRefs: texts(item.evidence_refs, "decision_outcome.evidence_refs"),
      methodId: text(item.method_id, "decision_outcome.method_id"),
      methodVersion: text(item.method_version, "decision_outcome.method_version"),
      calculationCodeVersion: text(item.calculation_code_version, "decision_outcome.calculation_code_version"),
      limitations: texts(item.limitations, "decision_outcome.limitations"),
    };
  });
  if (
    decisionOutcomes.length !== context.decisions.length
    || new Set(decisionOutcomes.map((item) => item.decisionEventId)).size !== context.decisions.length
    || decisionOutcomes.some((item) => item.episodeResultRef !== episodeOutcome.outcomeId)
  ) {
    throw new Error("Decision Outcome event coverage or Episode result reference is incomplete.");
  }
  if (!Array.isArray(raw.counterfactuals)) throw new Error("Decision Outcome counterfactuals must be an array.");
  const counterfactuals = raw.counterfactuals.map((value, index): HistoricalCounterfactualView => {
    const item = object(value, `counterfactuals[${index}]`);
    assertOwnership(item, context, `counterfactuals[${index}]`);
    const decisionEventId = text(item.decision_event_id, "counterfactual.decision_event_id");
    if (!known.has(decisionEventId)) throw new Error(`Decision Outcome counterfactual references unknown event ${decisionEventId}.`);
    const intervention = object(item.intervention, "counterfactual.intervention");
    const parsedComparison = comparison(item.comparison);
    const actualResult = item.actual_result === null ? null : result(item.actual_result, "counterfactual.actual_result");
    const counterfactualResult = item.counterfactual_result === null ? null : result(item.counterfactual_result, "counterfactual.counterfactual_result");
    if (parsedComparison.status === "complete" && (!actualResult || !counterfactualResult)) {
      throw new Error("Decision Outcome complete counterfactual requires both backend results.");
    }
    return {
      counterfactualId: text(item.counterfactual_id, "counterfactual.counterfactual_id"),
      subjectId: context.subjectId, accountId: context.accountId, instrumentId: context.instrumentId,
      episodeId: context.episodeId, decisionEventId,
      scenarioId: enumValue(item.scenario_id, ["omit_event_until_next_decision_v1", "omit_event_preserve_later_executions_v1", "existing_exit_evidence_reuse_v1"], "counterfactual.scenario_id"),
      scenarioVersion: text(item.scenario_version, "counterfactual.scenario_version"),
      methodId: text(item.method_id, "counterfactual.method_id"),
      methodVersion: text(item.method_version, "counterfactual.method_version"),
      calculationCodeVersion: text(item.calculation_code_version, "counterfactual.calculation_code_version"),
      relationType: enumValue(item.relation_type, ["historical_counterfactual", "registered_baseline_comparison"], "counterfactual.relation_type"),
      analysisAsOf: timestamp(item.analysis_as_of, "counterfactual.analysis_as_of"),
      decisionAt: timestamp(item.decision_at, "counterfactual.decision_at"),
      evaluationEnd: nullableTimestamp(item.evaluation_end, "counterfactual.evaluation_end"),
      intervention: { changedAction: text(intervention.changed_action, "counterfactual.changed_action"), changedExecutionRefs: texts(intervention.changed_execution_refs, "counterfactual.changed_execution_refs") },
      heldConstant: texts(item.held_constant, "counterfactual.held_constant"),
      downstreamOrderPolicy: text(item.downstream_order_policy, "counterfactual.downstream_order_policy"),
      priceBasis: text(item.price_basis, "counterfactual.price_basis"),
      frictionBasis: text(item.friction_basis, "counterfactual.friction_basis"),
      feasibilityStatus: enumValue(item.feasibility_status, ["complete", "infeasible_downstream_execution", "insufficient_counterfactual_data", "unsupported_scenario"], "counterfactual.feasibility_status"),
      infeasibleReason: item.infeasible_reason === null ? null : text(item.infeasible_reason, "counterfactual.infeasible_reason"),
      firstConflictingExecutionId: item.first_conflicting_execution_id === null ? null : text(item.first_conflicting_execution_id, "counterfactual.first_conflicting_execution_id"),
      actualResult, counterfactualResult, comparison: parsedComparison,
      baselineEvidenceRef: item.baseline_evidence_ref === null ? null : text(item.baseline_evidence_ref, "counterfactual.baseline_evidence_ref"),
      dataTier: enumValue(item.data_tier, ["synthetic"], "counterfactual.data_tier"),
      limitations: texts(item.limitations, "counterfactual.limitations"),
    };
  });
  const followup = exitFollowup(raw.exit_followup);
  if (followup && !counterfactuals.some((item) => item.baselineEvidenceRef === followup.evidenceId)) {
    throw new Error("Decision Outcome Exit follow-up is not backed by the registered baseline reference.");
  }
  return { episodeOutcome, decisionOutcomes, counterfactuals, exitFollowup: followup };
}
