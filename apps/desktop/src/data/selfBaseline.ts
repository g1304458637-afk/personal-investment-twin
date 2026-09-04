export type SelfBaselineWindow = "rolling_3m" | "rolling_12m" | "lifetime";
export type SelfBaselineStatus =
  | "complete"
  | "insufficient_self_history"
  | "unsupported_for_self_baseline";
export type SelfComparisonBand =
  | "below_historical_iqr"
  | "within_historical_iqr"
  | "above_historical_iqr";

const WINDOWS: readonly SelfBaselineWindow[] = ["rolling_3m", "rolling_12m", "lifetime"];
const METRICS = new Set(["portfolio_concentration_hhi", "mean_daily_turnover"]);

export interface BackendSelfBaselinePayload {
  subject_id: string;
  as_of: string;
  default_window: string;
  metrics: unknown[];
  available_metric_count: number;
  insufficient_metric_count: number;
  data_tier: string;
  limitations: unknown[];
}

export interface SelfBaselineProvenanceView {
  currentSourceRef: string | null;
  historicalSeriesRef: string | null;
  historicalPointSourceRefs: string[];
  sourceMethodId: string;
  sourceMethodVersion: string;
  observationKind: string;
  observationUnit: string;
  observationCadence: string;
  quantileMethod: string;
  percentileMethod: string;
  dataTier: "synthetic";
}

export interface SelfBaselineComparisonView {
  comparisonId: string;
  subjectId: string;
  metricId: string;
  methodId: string;
  methodVersion: string;
  sourceMethodId: string;
  sourceMethodVersion: string;
  asOf: string;
  currentValue: number | null;
  window: SelfBaselineWindow;
  observationStart: string | null;
  observationEnd: string | null;
  observationKind: string;
  observationUnit: string;
  observationCadence: string;
  validN: number;
  median: number | null;
  p25: number | null;
  p75: number | null;
  selfHistoricalPercentile: number | null;
  deltaFromMedian: number | null;
  comparisonBand: SelfComparisonBand | null;
  status: SelfBaselineStatus;
  insufficientReason: string | null;
  provenance: SelfBaselineProvenanceView;
  limitations: string[];
}

export interface SelfBaselineMetricView {
  metricId: string;
  observationKind: string;
  observationUnit: string;
  observationCadence: string;
  windows: SelfBaselineComparisonView[];
}

export interface SelfBaselineSummaryView {
  subjectId: string;
  asOf: string;
  defaultWindow: SelfBaselineWindow;
  metrics: SelfBaselineMetricView[];
  availableMetricCount: number;
  insufficientMetricCount: number;
  dataTier: "synthetic";
  limitations: string[];
}

function sameTextItems(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export function windowsUseSameObservations(metric: SelfBaselineMetricView): boolean {
  const [first, ...rest] = metric.windows;
  if (!first) return false;
  return rest.every((item) => (
    item.validN === first.validN
    && item.observationStart === first.observationStart
    && item.observationEnd === first.observationEnd
    && sameTextItems(
      item.provenance.historicalPointSourceRefs,
      first.provenance.historicalPointSourceRefs,
    )
  ));
}

export function allWindowsUseSameObservations(summary: SelfBaselineSummaryView): boolean {
  return summary.metrics.length > 0 && summary.metrics.every(windowsUseSameObservations);
}

function object(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Self baseline ${name} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, name: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`Self baseline ${name} must be an array.`);
  return value;
}

function text(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Self baseline ${name} must be non-empty text.`);
  }
  return value;
}

function optionalText(value: unknown, name: string): string | null {
  return value === null ? null : text(value, name);
}

function time(value: unknown, name: string): string {
  const result = text(value, name);
  if (Number.isNaN(Date.parse(result))) throw new Error(`Self baseline ${name} must be a timestamp.`);
  return result;
}

function optionalTime(value: unknown, name: string): string | null {
  return value === null ? null : time(value, name);
}

function finite(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Self baseline ${name} must be finite.`);
  }
  return value;
}

function optionalFinite(value: unknown, name: string): number | null {
  return value === null ? null : finite(value, name);
}

function count(value: unknown, name: string): number {
  const result = finite(value, name);
  if (!Number.isInteger(result) || result < 0) {
    throw new Error(`Self baseline ${name} must be a non-negative integer.`);
  }
  return result;
}

function texts(value: unknown, name: string): string[] {
  return array(value, name).map((item, index) => text(item, `${name}[${index}]`));
}

function windowValue(value: unknown, name: string): SelfBaselineWindow {
  if (!WINDOWS.includes(value as SelfBaselineWindow)) {
    throw new Error(`Self baseline ${name} has an unsupported window.`);
  }
  return value as SelfBaselineWindow;
}

function status(value: unknown, name: string): SelfBaselineStatus {
  if (![
    "complete",
    "insufficient_self_history",
    "unsupported_for_self_baseline",
  ].includes(String(value))) {
    throw new Error(`Self baseline ${name} has an unsupported status.`);
  }
  return value as SelfBaselineStatus;
}

function band(value: unknown, name: string): SelfComparisonBand | null {
  if (value === null) return null;
  if (![
    "below_historical_iqr",
    "within_historical_iqr",
    "above_historical_iqr",
  ].includes(String(value))) {
    throw new Error(`Self baseline ${name} has an unsupported comparison band.`);
  }
  return value as SelfComparisonBand;
}

function provenance(value: unknown, name: string): SelfBaselineProvenanceView {
  const raw = object(value, name);
  if (raw.data_tier !== "synthetic") throw new Error(`Self baseline ${name} must remain synthetic.`);
  return {
    currentSourceRef: optionalText(raw.current_source_ref, `${name}.current_source_ref`),
    historicalSeriesRef: optionalText(raw.historical_series_ref, `${name}.historical_series_ref`),
    historicalPointSourceRefs: texts(raw.historical_point_source_refs, `${name}.historical_point_source_refs`),
    sourceMethodId: text(raw.source_method_id, `${name}.source_method_id`),
    sourceMethodVersion: text(raw.source_method_version, `${name}.source_method_version`),
    observationKind: text(raw.observation_kind, `${name}.observation_kind`),
    observationUnit: text(raw.observation_unit, `${name}.observation_unit`),
    observationCadence: text(raw.observation_cadence, `${name}.observation_cadence`),
    quantileMethod: text(raw.quantile_method, `${name}.quantile_method`),
    percentileMethod: text(raw.percentile_method, `${name}.percentile_method`),
    dataTier: "synthetic",
  };
}

function comparison(value: unknown, metricId: string, expectedSubject: string, name: string): SelfBaselineComparisonView {
  const raw = object(value, name);
  const comparisonStatus = status(raw.status, `${name}.status`);
  const result: SelfBaselineComparisonView = {
    comparisonId: text(raw.comparison_id, `${name}.comparison_id`),
    subjectId: text(raw.subject_id, `${name}.subject_id`),
    metricId: text(raw.metric_id, `${name}.metric_id`),
    methodId: text(raw.method_id, `${name}.method_id`),
    methodVersion: text(raw.method_version, `${name}.method_version`),
    sourceMethodId: text(raw.source_method_id, `${name}.source_method_id`),
    sourceMethodVersion: text(raw.source_method_version, `${name}.source_method_version`),
    asOf: time(raw.as_of, `${name}.as_of`),
    currentValue: optionalFinite(raw.current_value, `${name}.current_value`),
    window: windowValue(raw.window, `${name}.window`),
    observationStart: optionalTime(raw.observation_start, `${name}.observation_start`),
    observationEnd: optionalTime(raw.observation_end, `${name}.observation_end`),
    observationKind: text(raw.observation_kind, `${name}.observation_kind`),
    observationUnit: text(raw.observation_unit, `${name}.observation_unit`),
    observationCadence: text(raw.observation_cadence, `${name}.observation_cadence`),
    validN: count(raw.valid_n, `${name}.valid_n`),
    median: optionalFinite(raw.median, `${name}.median`),
    p25: optionalFinite(raw.p25, `${name}.p25`),
    p75: optionalFinite(raw.p75, `${name}.p75`),
    selfHistoricalPercentile: optionalFinite(raw.self_historical_percentile, `${name}.self_historical_percentile`),
    deltaFromMedian: optionalFinite(raw.delta_from_median, `${name}.delta_from_median`),
    comparisonBand: band(raw.comparison_band, `${name}.comparison_band`),
    status: comparisonStatus,
    insufficientReason: optionalText(raw.insufficient_reason, `${name}.insufficient_reason`),
    provenance: provenance(raw.provenance, `${name}.provenance`),
    limitations: texts(raw.limitations, `${name}.limitations`),
  };
  if (result.subjectId !== expectedSubject || result.metricId !== metricId) {
    throw new Error(`Self baseline ${name} does not match its subject and metric.`);
  }
  if (result.methodId !== "self_historical_distribution_v1" || result.methodVersion !== "1") {
    throw new Error(`Self baseline ${name} has an unsupported method contract.`);
  }
  if (
    result.observationKind !== result.provenance.observationKind
    || result.observationUnit !== result.provenance.observationUnit
    || result.observationCadence !== result.provenance.observationCadence
    || result.sourceMethodId !== result.provenance.sourceMethodId
    || result.sourceMethodVersion !== result.provenance.sourceMethodVersion
  ) {
    throw new Error(`Self baseline ${name} provenance does not match its comparison.`);
  }
  const statistics = [
    result.median,
    result.p25,
    result.p75,
    result.selfHistoricalPercentile,
    result.deltaFromMedian,
  ];
  if (comparisonStatus === "complete") {
    if (statistics.some((item) => item === null) || result.comparisonBand === null || result.insufficientReason !== null) {
      throw new Error(`Self baseline ${name} complete result is missing statistics.`);
    }
  } else if (statistics.some((item) => item !== null) || result.comparisonBand !== null || result.insufficientReason === null) {
    throw new Error(`Self baseline ${name} non-complete result must abstain.`);
  }
  return result;
}

export function adaptSelfBaselinePayload(
  value: unknown,
  expectedSubject: string,
): SelfBaselineSummaryView {
  const raw = object(value, "payload") as unknown as BackendSelfBaselinePayload;
  const subjectId = text(raw.subject_id, "subject_id");
  if (subjectId !== expectedSubject) throw new Error("Self baseline subject does not match the current Twin.");
  if (raw.data_tier !== "synthetic") throw new Error("Desktop Self baseline demo must remain explicitly synthetic.");
  const defaultWindow = windowValue(raw.default_window, "default_window");
  if (defaultWindow !== "rolling_12m") throw new Error("Desktop Self baseline default must be rolling_12m.");
  const seenMetrics = new Set<string>();
  const metrics = array(raw.metrics, "metrics").map((value, metricIndex) => {
    const name = `metrics[${metricIndex}]`;
    const metric = object(value, name);
    const metricId = text(metric.metric_id, `${name}.metric_id`);
    if (!METRICS.has(metricId)) throw new Error(`Self baseline ${name} is unsupported.`);
    if (seenMetrics.has(metricId)) throw new Error(`Self baseline contains duplicate metric ${metricId}.`);
    seenMetrics.add(metricId);
    const observationKind = text(metric.observation_kind, `${name}.observation_kind`);
    const observationUnit = text(metric.observation_unit, `${name}.observation_unit`);
    const observationCadence = text(metric.observation_cadence, `${name}.observation_cadence`);
    const seenWindows = new Set<SelfBaselineWindow>();
    const windows = array(metric.windows, `${name}.windows`).map((item, windowIndex) => {
      const result = comparison(item, metricId, subjectId, `${name}.windows[${windowIndex}]`);
      if (seenWindows.has(result.window)) throw new Error(`Self baseline ${name} contains duplicate window ${result.window}.`);
      seenWindows.add(result.window);
      if (
        result.observationKind !== observationKind
        || result.observationUnit !== observationUnit
        || result.observationCadence !== observationCadence
      ) {
        throw new Error(`Self baseline ${name} window observation contract is inconsistent.`);
      }
      return result;
    });
    if (WINDOWS.some((item) => !seenWindows.has(item)) || windows.length !== WINDOWS.length) {
      throw new Error(`Self baseline ${name} must contain all registered windows.`);
    }
    return { metricId, observationKind, observationUnit, observationCadence, windows };
  });
  if (seenMetrics.size !== METRICS.size) throw new Error("Self baseline is missing a registered Desktop metric.");
  return {
    subjectId,
    asOf: time(raw.as_of, "as_of"),
    defaultWindow,
    metrics,
    availableMetricCount: count(raw.available_metric_count, "available_metric_count"),
    insufficientMetricCount: count(raw.insufficient_metric_count, "insufficient_metric_count"),
    dataTier: "synthetic",
    limitations: texts(raw.limitations, "limitations"),
  };
}
