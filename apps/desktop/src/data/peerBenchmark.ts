export type PeerMetricId = "portfolio_hhi" | "turnover" | "closed_episode_count";

type PeerValueFormat = "decimal" | "percent" | "integer";

export interface BackendCohortDefinition {
  cohort_id: string;
  market: string;
  asset_types: string[];
  direction: string;
  observation_start: string;
  observation_end: string;
  leverage_allowed: boolean;
  data_tier: "synthetic";
  min_descriptive_n: number;
  description: string;
  limitations: string[];
}

export interface BackendPeerBenchmarkResult {
  subject_id: string;
  cohort_id: string;
  metric_id: string;
  subject_value: number | null;
  cohort_n: number;
  metric_n: number;
  p25: number | null;
  median: number | null;
  p75: number | null;
  percentile: number | null;
  benchmark_status: string;
  benchmark_reason: string | null;
  quantile_method: string;
  percentile_method: string;
  data_tier: "synthetic";
  observation_start: string;
  observation_end: string;
  limitations: string[];
}

export interface BackendPeerBenchmarkPayload {
  cohort: BackendCohortDefinition;
  cohort_n: number;
  metrics: Record<PeerMetricId, BackendPeerBenchmarkResult>;
}

export interface PeerRangeMetric {
  id: PeerMetricId;
  label: string;
  valueFormat: PeerValueFormat;
  user: number;
  p25: number;
  median: number;
  p75: number;
  percentile: number;
}

export interface PeerBenchmarkMetricView {
  id: PeerMetricId;
  label: string;
  valueFormat: PeerValueFormat;
  subjectValue: number | null;
  cohortN: number;
  metricN: number;
  p25: number | null;
  median: number | null;
  p75: number | null;
  percentile: number | null;
  status: string;
  reason: string | null;
  quantileMethod: string;
  percentileMethod: string;
  observationStart: string;
  observationEnd: string;
  limitations: string[];
  chartMetric: PeerRangeMetric | null;
}

export interface PeerBenchmarkView {
  cohort: {
    id: string;
    market: string;
    assetTypes: string[];
    direction: string;
    observationStart: string;
    observationEnd: string;
    leverageAllowed: boolean;
    minDescriptiveN: number;
    description: string;
    limitations: string[];
  };
  cohortN: number;
  metrics: PeerBenchmarkMetricView[];
}

const metricPresentation: Record<PeerMetricId, Pick<PeerRangeMetric, "label" | "valueFormat">> = {
  portfolio_hhi: { label: "HHI", valueFormat: "decimal" },
  turnover: { label: "Turnover", valueFormat: "percent" },
  closed_episode_count: { label: "Closed episodes", valueFormat: "integer" },
};

const metricOrder: PeerMetricId[] = ["portfolio_hhi", "turnover", "closed_episode_count"];
const backendMetricIds: Record<PeerMetricId, string> = {
  portfolio_hhi: "portfolio_concentration_hhi",
  turnover: "mean_daily_turnover",
  closed_episode_count: "closed_episode_count",
};

function isFiniteNumber(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function assertSynthetic(dataTier: string, context: string) {
  if (dataTier !== "synthetic") {
    throw new Error(`${context} must remain explicitly synthetic in the desktop demo.`);
  }
}

function chartMetric(result: BackendPeerBenchmarkResult, id: PeerMetricId): PeerRangeMetric | null {
  const { subject_value: subjectValue, p25, median, p75, percentile } = result;
  if (
    result.benchmark_status !== "complete"
    || !isFiniteNumber(subjectValue)
    || !isFiniteNumber(p25)
    || !isFiniteNumber(median)
    || !isFiniteNumber(p75)
    || !isFiniteNumber(percentile)
  ) return null;
  const presentation = metricPresentation[id];
  return {
    id,
    label: presentation.label,
    valueFormat: presentation.valueFormat,
    user: subjectValue,
    p25,
    median,
    p75,
    percentile,
  };
}

function metricView(
  result: BackendPeerBenchmarkResult,
  id: PeerMetricId,
  cohort: BackendCohortDefinition,
  cohortN: number,
): PeerBenchmarkMetricView {
  assertSynthetic(result.data_tier, `Peer benchmark ${id}`);
  if (result.metric_id !== backendMetricIds[id]) {
    throw new Error(`Peer benchmark ${id} has an unexpected metric_id.`);
  }
  if (
    result.cohort_id !== cohort.cohort_id
    || result.cohort_n !== cohortN
    || result.observation_start !== cohort.observation_start
    || result.observation_end !== cohort.observation_end
  ) {
    throw new Error(`Peer benchmark ${id} does not match its cohort definition.`);
  }
  const presentation = metricPresentation[id];
  return {
    id,
    label: presentation.label,
    valueFormat: presentation.valueFormat,
    subjectValue: result.subject_value,
    cohortN: result.cohort_n,
    metricN: result.metric_n,
    p25: result.p25,
    median: result.median,
    p75: result.p75,
    percentile: result.percentile,
    status: result.benchmark_status,
    reason: result.benchmark_reason,
    quantileMethod: result.quantile_method,
    percentileMethod: result.percentile_method,
    observationStart: result.observation_start,
    observationEnd: result.observation_end,
    limitations: result.limitations,
    chartMetric: chartMetric(result, id),
  };
}

export function adaptPeerBenchmarkPayload(value: BackendPeerBenchmarkPayload): PeerBenchmarkView {
  assertSynthetic(value.cohort.data_tier, "Peer cohort");
  const subjectIds = new Set(metricOrder.map((id) => value.metrics[id].subject_id));
  if (subjectIds.size !== 1) {
    throw new Error("Peer benchmark metrics must describe one subject.");
  }
  return {
    cohort: {
      id: value.cohort.cohort_id,
      market: value.cohort.market,
      assetTypes: value.cohort.asset_types,
      direction: value.cohort.direction,
      observationStart: value.cohort.observation_start,
      observationEnd: value.cohort.observation_end,
      leverageAllowed: value.cohort.leverage_allowed,
      minDescriptiveN: value.cohort.min_descriptive_n,
      description: value.cohort.description,
      limitations: value.cohort.limitations,
    },
    cohortN: value.cohort_n,
    metrics: metricOrder.map((id) => metricView(value.metrics[id], id, value.cohort, value.cohort_n)),
  };
}

export function isCompletePeerBenchmarkMetric(
  metric: PeerBenchmarkMetricView,
): metric is PeerBenchmarkMetricView & { chartMetric: PeerRangeMetric } {
  return metric.chartMetric !== null;
}
