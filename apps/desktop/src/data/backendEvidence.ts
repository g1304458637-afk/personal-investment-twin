import generatedEvidence from "@/generated/showcase-demo.json";
import type {
  DemoEvidenceRecord,
  EvidenceMetric,
  EvidenceStatus,
  JsonValue,
} from "@/demo/types";
import type { TranslationValues } from "@/locales/LocaleProvider";

import type { BehaviorHistorySeries } from "./behaviorHistory";
import {
  adaptDemoInvestmentsCatalog,
  adaptInvestmentsPayload,
  type BackendInvestmentsPayload,
} from "./investments";
import {
  adaptExplainabilityPayload,
  conceptOnlyView,
  type ExplainabilityView,
} from "./explainability";
import { adaptPeerBenchmarkPayload, type BackendPeerBenchmarkPayload } from "./peerBenchmark";
import {
  adaptPositionEpisodeDemo,
  type BackendPositionEpisodeDemo,
  type PositionEpisodeEntryView,
  type PositionEpisodeDemoView,
} from "./positionEpisode";
import { adaptPretradeImpact, type BackendPretradeImpact } from "./pretradeImpact";
import { buildReviewView } from "./review";
import {
  adaptSelfBaselinePayload,
  type BackendSelfBaselinePayload,
} from "./selfBaseline";
import { adaptTwinPayload, type BackendTwinPayload } from "./twinState";

export interface SelectedEpisodeView {
  episode_id: string;
  symbol: string;
  size: number;
  entry_time: string;
  avg_entry_price: number;
  entry_fees: number;
  exit_time: string | null;
  avg_exit_price: number | null;
  exit_fees: number | null;
  pnl: number;
  return_value: number;
  direction: string;
  status: string;
  position_id: number;
  valuation_time: string | null;
  valuation_price: number | null;
}

interface BackendEvidenceExport {
  schema_version: string;
  export_version: string;
  data_tier: "synthetic";
  selected_episode: SelectedEpisodeView;
  evidence_records: DemoEvidenceRecord[];
  historical_series: {
    portfolio_hhi: BackendHistoricalMetricSeries;
    turnover: BackendHistoricalMetricSeries;
  };
  twin: BackendTwinPayload;
  peer_benchmark: BackendPeerBenchmarkPayload;
  pretrade_demo: BackendPretradeImpact;
  investments: BackendInvestmentsPayload;
  position_episode_demo: BackendPositionEpisodeDemo;
  self_baseline: BackendSelfBaselinePayload;
  explainability: unknown;
  same_stock_compare_demo: unknown;
}

interface BackendHistoricalMetricSeries {
  subject_id: string;
  metric_id: string;
  method_id: string;
  method_version: string;
  data_tier: "synthetic";
  limitations: string[];
  points: Array<{
    as_of: string;
    value: number | null;
    evidence_status: EvidenceStatus;
    source_evidence_id: string;
  }>;
}

const backend = generatedEvidence as unknown as BackendEvidenceExport;

if (backend.data_tier !== "synthetic") {
  throw new Error("Desktop demo evidence must remain explicitly synthetic.");
}

export const selectedEpisode = backend.selected_episode;
export const evidenceRecords = backend.evidence_records;
export const recentEvidenceIds = evidenceRecords.slice(0, 4).map((record) => record.evidence_id);

function historyView(series: BackendHistoricalMetricSeries): BehaviorHistorySeries {
  if (series.data_tier !== "synthetic") {
    throw new Error("Desktop behavior history must remain explicitly synthetic.");
  }
  return {
    metricId: series.metric_id,
    methodId: series.method_id,
    methodVersion: series.method_version,
    dataTier: series.data_tier,
    limitations: series.limitations,
    points: series.points.map((point) => ({
      date: point.as_of,
      value: point.value,
      status: point.evidence_status,
      sourceEvidenceId: point.source_evidence_id,
    })),
  };
}

export const behaviorHistory = {
  hhi: historyView(backend.historical_series.portfolio_hhi),
  turnover: historyView(backend.historical_series.turnover),
};
export const peerBenchmark = adaptPeerBenchmarkPayload(backend.peer_benchmark);
export const pretradeDemo = adaptPretradeImpact(backend.pretrade_demo);
export const positionEpisodeDemo: PositionEpisodeDemoView = adaptPositionEpisodeDemo(
  backend.position_episode_demo,
);
export const twinInvestments = adaptInvestmentsPayload(backend.investments, positionEpisodeDemo);
export const investments = adaptDemoInvestmentsCatalog(positionEpisodeDemo);
export const twinState = adaptTwinPayload(
  backend.twin,
  [
    ...evidenceRecords,
    ...Object.values(backend.historical_series).flatMap((series) =>
      series.points.map((point) => ({
        evidence_id: point.source_evidence_id,
        subject_id: series.subject_id,
      })),
    ),
  ],
  positionEpisodeDemo.entries.map((entry) => ({
    episodeId: entry.episode.episodeId,
    subjectId: entry.episode.subjectId,
    status: entry.episode.status,
  })),
);
export const selfBaseline = adaptSelfBaselinePayload(
  backend.self_baseline,
  twinState.currentSnapshot.subjectId,
);
export const explainability = adaptExplainabilityPayload(backend.explainability);
export const sameStockCompareDemo = backend.same_stock_compare_demo;

export function explainabilityForEvidence(evidenceId: string): ExplainabilityView | null {
  return explainability.evidenceViews.find((item) => item.evidenceId === evidenceId) ?? null;
}

export function getEvidenceRecordById(evidenceId: string): DemoEvidenceRecord | null {
  return evidenceRecords.find((item) => item.evidence_id === evidenceId) ?? null;
}

export function explainabilityForConcept(conceptId: string): ExplainabilityView | null {
  return explainability.evidenceViews.find(
    (item) => item.concept.conceptId === conceptId && item.trace?.status === "complete",
  ) ?? conceptOnlyView(explainability, conceptId);
}

export const insufficientExplainability = explainability.evidenceViews.find(
  (item) => item.trace?.status === "insufficient",
) ?? null;
export const pretradeExplainability = explainability.pretrade;

export function getPositionEpisodeById(episodeId: string): PositionEpisodeEntryView | null {
  return positionEpisodeDemo.entries.find((entry) => entry.episode.episodeId === episodeId) ?? null;
}

export function translateEvidenceText(
  t: (source: string, values?: TranslationValues) => string,
  source: string,
  values?: TranslationValues,
): string {
  if (!values) return t(source);
  const localizedValues = Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, typeof value === "string" ? t(value) : value]),
  );
  return t(source, localizedValues);
}

function recordFor(metricId: string): DemoEvidenceRecord {
  const record = evidenceRecords.find((item) => item.metric_id === metricId);
  if (!record) throw new Error(`Missing generated evidence record for ${metricId}.`);
  return record;
}

function isRecord(value: JsonValue | undefined): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordValue(record: DemoEvidenceRecord): number | null {
  return numberValue(record.value);
}

function numberAttribute(record: DemoEvidenceRecord, key: string): number | null {
  return numberValue(record.attributes[key]);
}

function stringAttribute(record: DemoEvidenceRecord, key: string): string | null {
  const value = record.attributes[key];
  return typeof value === "string" ? value : null;
}

function percent(value: number | null, digits = 1): string {
  return value === null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function decimal(value: number | null, digits = 4): string {
  return value === null ? "—" : value.toFixed(digits);
}

function currency(value: number | null): string {
  return value === null ? "—" : `¥${value.toFixed(2)}`;
}

function denominatorLabel(value: DemoEvidenceRecord["denominator"]): string {
  if (value === null) return "—";
  return value === "portfolio_value" ? "portfolio value" : String(value);
}

function sizingPrimary(comparison: string | null): string {
  switch (comparison) {
    case "outperformed_baseline":
      return "Actual allocation outperformed equal-weight baseline";
    case "underperformed_baseline":
      return "Actual allocation underperformed equal-weight baseline";
    case "matched_baseline":
      return "Actual allocation matched equal-weight baseline";
    default:
      return "Actual allocation comparison unavailable";
  }
}

function exitDescription(comparison: string | null): string {
  switch (comparison) {
    case "actual_exit_underperformed_hold_baseline":
      return "Actual exit underperformed the fixed hold baseline. The result is a retrospective fixed-window comparison, not an exit contribution.";
    case "actual_exit_outperformed_hold_baseline":
      return "Actual exit outperformed the fixed hold baseline. The result is a retrospective fixed-window comparison, not an exit contribution.";
    case "actual_exit_matched_hold_baseline":
      return "Actual exit matched the fixed hold baseline. The result is a retrospective fixed-window comparison, not an exit contribution.";
    default:
      return "The result is a retrospective fixed-window comparison, not an exit contribution.";
  }
}

function comparisonLabel(comparison: string | null): string {
  switch (comparison) {
    case "outperformed":
      return "outperformed";
    case "underperformed":
      return "underperformed";
    case "matched":
      return "matched";
    default:
      return "comparison unavailable";
  }
}

function metricBase(
  record: DemoEvidenceRecord,
  id: string,
  label: string,
  eyebrow: string,
  primary: string,
  description: string,
  trend: number[],
  primaryValues?: Record<string, string | number>,
  descriptionValues?: Record<string, string | number>,
): EvidenceMetric {
  return {
    id,
    label,
    eyebrow,
    primary,
    description,
    observationCount: record.observation_count,
    status: record.evidence_status,
    confidence: null,
    evidenceId: record.evidence_id,
    trend,
    primaryValues,
    descriptionValues,
  };
}

const selectionRecord = recordFor("selection_episode_asset_return");
const sizingRecord = recordFor("sizing_equal_weight_comparison");
const exitRecord = recordFor("exit_timing_post_exit_asset_return");
const frictionRecord = recordFor("recorded_trading_friction_comparison");
const turnoverRecord = recordFor("mean_daily_turnover");
const concentrationRecord = recordFor("portfolio_concentration_hhi");
const dispositionRecord = recordFor("disposition_effect");
const lossAveragingRecord = recordFor("loss_averaging_event_rate");

const selectionMarketReturn = numberAttribute(selectionRecord, "market_benchmark_return");
const selectionIndustryReturn = numberAttribute(selectionRecord, "industry_benchmark_return");

export const decisionMetrics: EvidenceMetric[] = [
  metricBase(
    selectionRecord,
    "selection",
    "Selection",
    "Asset episode evidence",
    "Asset Episode TWR {value}",
    "Market benchmark {market} ({marketComparison}); industry benchmark {industry} ({industryComparison}).",
    recordValue(selectionRecord) === null ? [] : [recordValue(selectionRecord) as number],
    { value: percent(recordValue(selectionRecord), 1) },
    {
      market: percent(selectionMarketReturn, 1),
      marketComparison: comparisonLabel(stringAttribute(selectionRecord, "market_comparison")),
      industry: percent(selectionIndustryReturn, 1),
      industryComparison: comparisonLabel(stringAttribute(selectionRecord, "industry_comparison")),
    },
  ),
  metricBase(
    sizingRecord,
    "sizing",
    "Sizing",
    "Exposure evidence",
    sizingPrimary(stringAttribute(sizingRecord, "comparison")),
    "Actual end value {actual} vs equal-weight baseline {baseline}.",
    [numberAttribute(sizingRecord, "actual_end_value"), numberAttribute(sizingRecord, "baseline_end_value")].filter((value): value is number => value !== null),
    undefined,
    {
      actual: currency(numberAttribute(sizingRecord, "actual_end_value")),
      baseline: currency(numberAttribute(sizingRecord, "baseline_end_value")),
    },
  ),
  metricBase(
    exitRecord,
    "exit",
    "Exit",
    "Post-exit evidence",
    "Post-exit fixed-window return {value}",
    exitDescription(stringAttribute(exitRecord, "comparison")),
    recordValue(exitRecord) === null ? [] : [recordValue(exitRecord) as number],
    { value: percent(recordValue(exitRecord), 1) },
  ),
  metricBase(
    frictionRecord,
    "friction",
    "Friction",
    "Recorded explicit fees",
    "Recorded explicit fees {value}",
    "Actual end value {actual} vs zero-recorded-fee baseline {baseline}.",
    numberAttribute(frictionRecord, "recorded_fee_total") === null ? [] : [numberAttribute(frictionRecord, "recorded_fee_total") as number],
    { value: currency(numberAttribute(frictionRecord, "recorded_fee_total")) },
    {
      actual: currency(numberAttribute(frictionRecord, "actual_end_value")),
      baseline: currency(numberAttribute(frictionRecord, "zero_recorded_fee_end_value")),
    },
  ),
];

const dailyTurnover = turnoverRecord.attributes.daily_turnover;
const turnoverTrend = Array.isArray(dailyTurnover)
  ? dailyTurnover
      .filter(isRecord)
      .map((item) => numberValue(item.turnover))
      .filter((value): value is number => value !== null)
  : [];

export const behaviorMetrics: EvidenceMetric[] = [
  metricBase(
    concentrationRecord,
    "hhi",
    "HHI",
    "Portfolio concentration",
    "HHI {value}",
    "Latest snapshot: {assets} active assets; cash excluded from security weights.",
    recordValue(concentrationRecord) === null ? [] : [recordValue(concentrationRecord) as number],
    { value: decimal(recordValue(concentrationRecord)) },
    { assets: numberAttribute(concentrationRecord, "active_asset_count") ?? "—" },
  ),
  metricBase(
    turnoverRecord,
    "turnover",
    "Turnover",
    "Turnover intensity",
    "Average daily turnover {value}",
    "N={n}; denominator: {denominator}; total traded value {total}.",
    turnoverTrend,
    { value: percent(recordValue(turnoverRecord), 2) },
    {
      n: turnoverRecord.observation_count ?? "—",
      denominator: denominatorLabel(turnoverRecord.denominator),
      total: currency(turnoverRecord.numerator),
    },
  ),
  metricBase(
    dispositionRecord,
    "disposition",
    "Disposition",
    "Realized outcome tendency",
    "PGR {pgr} · PLR {plr}",
    "PGR − PLR {effect}; {events} eligible sale events.",
    recordValue(dispositionRecord) === null ? [] : [recordValue(dispositionRecord) as number],
    {
      pgr: percent(numberAttribute(dispositionRecord, "pgr"), 1),
      plr: percent(numberAttribute(dispositionRecord, "plr"), 1),
    },
    {
      effect: percent(recordValue(dispositionRecord), 1),
      events: numberAttribute(dispositionRecord, "eligible_sale_events") ?? "—",
    },
  ),
  metricBase(
    lossAveragingRecord,
    "loss-averaging",
    "Loss Averaging",
    "Observed add events",
    "{detected} detected / {eligible} eligible",
    "Event rate {rate}; additions below prior average cost are descriptive observations.",
    recordValue(lossAveragingRecord) === null ? [] : [recordValue(lossAveragingRecord) as number],
    {
      detected: lossAveragingRecord.numerator ?? "—",
      eligible: lossAveragingRecord.denominator ?? "—",
    },
    { rate: percent(recordValue(lossAveragingRecord), 1) },
  ),
];

export const reviewView = buildReviewView({
  decisionMetrics,
  behaviorMetrics,
  evidenceRecords,
  explainability,
  episodes: positionEpisodeDemo.entries,
});

export { selectionRecord, sizingRecord, exitRecord, frictionRecord };
