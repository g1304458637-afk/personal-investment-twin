import type { DemoEvidenceRecord, EvidenceMetric, EvidenceStatus } from "@/demo/types";

import type { ExplainabilityCatalog, ExplainabilityView } from "./explainability";
import type { PositionEpisodeEntryView } from "./positionEpisode";

export type ReviewObservationStatus = EvidenceStatus | "unavailable";
export type ReviewObservationGroup =
  | "decision"
  | "execution"
  | "portfolio_structure"
  | "trading_activity"
  | "sale_observation"
  | "addition_observation";

export interface ReviewObservationView {
  id: string;
  group: ReviewObservationGroup;
  titleKey: string;
  eyebrowKey: string;
  conceptId: string;
  primary: string;
  description: string;
  primaryValues?: Record<string, string | number>;
  descriptionValues?: Record<string, string | number>;
  status: ReviewObservationStatus;
  observationCount: number | null;
  evidenceId: string | null;
  explainability: ExplainabilityView | null;
  episodeId: string | null;
}

export interface ReviewView {
  dataTier: "synthetic";
  decisions: ReviewObservationView[];
  execution: ReviewObservationView[];
  patterns: ReviewObservationView[];
}

interface ReviewDefinition {
  id: string;
  group: ReviewObservationGroup;
  titleKey: string;
  eyebrowKey: string;
  conceptId: string;
}

export const DECISION_REVIEW_ORDER = ["selection", "sizing", "exit"] as const;
export const EXECUTION_REVIEW_ORDER = ["friction"] as const;
export const PATTERN_REVIEW_ORDER = ["hhi", "turnover", "disposition", "loss-averaging"] as const;

const decisionDefinitions: ReviewDefinition[] = [
  { id: "selection", group: "decision", titleKey: "Instrument selection", eyebrowKey: "Asset choice evidence", conceptId: "selection_episode_asset_return" },
  { id: "sizing", group: "decision", titleKey: "Position sizing", eyebrowKey: "Allocation evidence", conceptId: "sizing_equal_weight_comparison" },
  { id: "exit", group: "decision", titleKey: "Completed exit decision", eyebrowKey: "Post-exit observation", conceptId: "post_exit_fixed_window_return" },
  { id: "friction", group: "execution", titleKey: "Recorded execution costs", eyebrowKey: "Execution record", conceptId: "recorded_trading_friction" },
];

const patternDefinitions: ReviewDefinition[] = [
  { id: "hhi", group: "portfolio_structure", titleKey: "Portfolio concentration", eyebrowKey: "Portfolio structure · HHI", conceptId: "portfolio_concentration_hhi" },
  { id: "turnover", group: "trading_activity", titleKey: "Turnover intensity", eyebrowKey: "Trading activity · Turnover", conceptId: "turnover_intensity" },
  { id: "disposition", group: "sale_observation", titleKey: "Sale outcome observation", eyebrowKey: "Recorded sale observations · PGR / PLR", conceptId: "disposition_effect" },
  { id: "loss-averaging", group: "addition_observation", titleKey: "Loss-state addition observation", eyebrowKey: "Recorded addition events", conceptId: "loss_state_addition" },
];

function unavailable(definition: ReviewDefinition): ReviewObservationView {
  return {
    ...definition,
    primary: "Evidence unavailable",
    description: "No backend Evidence is available for this observation.",
    status: "unavailable",
    observationCount: null,
    evidenceId: null,
    explainability: null,
    episodeId: null,
  };
}

function linkedEpisode(
  record: DemoEvidenceRecord,
  episodes: readonly PositionEpisodeEntryView[],
): string | null {
  const matches = episodes.filter(
    (entry) => entry.episode.subjectId === record.subject_id
      && entry.evidenceReferences.some((reference) => reference.evidenceId === record.evidence_id),
  );
  return matches.length === 1 ? matches[0].episode.episodeId : null;
}

function observation(
  definition: ReviewDefinition,
  metrics: readonly EvidenceMetric[],
  records: readonly DemoEvidenceRecord[],
  explainability: ExplainabilityCatalog,
  episodes: readonly PositionEpisodeEntryView[],
): ReviewObservationView {
  const metric = metrics.find((item) => item.id === definition.id);
  if (!metric) return unavailable(definition);
  const record = records.find((item) => item.evidence_id === metric.evidenceId);
  if (!record) return unavailable(definition);
  const exactView = explainability.evidenceViews.find((item) => item.evidenceId === record.evidence_id);
  const conceptView = explainability.evidenceViews.find(
    (item) => item.concept.conceptId === definition.conceptId && item.trace?.status === "complete",
  );
  return {
    ...definition,
    primary: metric.primary,
    description: metric.description,
    primaryValues: metric.primaryValues,
    descriptionValues: metric.descriptionValues,
    status: metric.status,
    observationCount: metric.observationCount,
    evidenceId: record.evidence_id,
    explainability: exactView ?? conceptView ?? null,
    episodeId: linkedEpisode(record, episodes),
  };
}

export function buildReviewView({
  decisionMetrics,
  behaviorMetrics,
  evidenceRecords,
  explainability,
  episodes,
}: {
  decisionMetrics: readonly EvidenceMetric[];
  behaviorMetrics: readonly EvidenceMetric[];
  evidenceRecords: readonly DemoEvidenceRecord[];
  explainability: ExplainabilityCatalog;
  episodes: readonly PositionEpisodeEntryView[];
}): ReviewView {
  const decisionRows = decisionDefinitions.map((definition) =>
    observation(definition, decisionMetrics, evidenceRecords, explainability, episodes));
  return {
    dataTier: "synthetic",
    decisions: DECISION_REVIEW_ORDER.map((id) => decisionRows.find((item) => item.id === id)!),
    execution: EXECUTION_REVIEW_ORDER.map((id) => decisionRows.find((item) => item.id === id)!),
    patterns: patternDefinitions.map((definition) =>
      observation(definition, behaviorMetrics, evidenceRecords, explainability, episodes)),
  };
}
