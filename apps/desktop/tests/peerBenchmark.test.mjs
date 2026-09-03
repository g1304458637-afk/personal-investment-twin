import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptPeerBenchmarkPayload, isCompletePeerBenchmarkMetric } = await import("../src/data/peerBenchmark.ts");

function result(metricId, overrides = {}) {
  return {
    subject_id: "demo-user:synthetic-behavior",
    cohort_id: "synthetic-cn-equity-long-only-v1",
    metric_id: metricId,
    subject_value: 0.31,
    cohort_n: 72,
    metric_n: 72,
    p25: 0.22,
    median: 0.29,
    p75: 0.38,
    percentile: 55,
    benchmark_status: "complete",
    benchmark_reason: null,
    quantile_method: "numpy_quantile_linear_v1",
    percentile_method: "scipy_percentileofscore_rank_v1",
    data_tier: "synthetic",
    observation_start: "2025-01-02T00:00:00",
    observation_end: "2025-01-08T00:00:00",
    limitations: [],
    ...overrides,
  };
}

function payload(overrides = {}) {
  return {
    cohort: {
      cohort_id: "synthetic-cn-equity-long-only-v1",
      market: "CN",
      asset_types: ["equity"],
      direction: "long_only",
      observation_start: "2025-01-02T00:00:00",
      observation_end: "2025-01-08T00:00:00",
      leverage_allowed: false,
      data_tier: "synthetic",
      min_descriptive_n: 30,
      description: "Deterministic synthetic cohort.",
      limitations: [],
    },
    cohort_n: 72,
    metrics: {
      portfolio_hhi: result("portfolio_concentration_hhi"),
      turnover: result("mean_daily_turnover", { subject_value: 0.08, p25: 0.03, median: 0.05, p75: 0.1, percentile: 65 }),
      closed_episode_count: result("closed_episode_count", { subject_value: 3, p25: 2, median: 4, p75: 6, percentile: 42 }),
    },
    ...overrides,
  };
}

test("peer adapter creates a complete chart metric only from finite complete benchmark values", () => {
  const view = adaptPeerBenchmarkPayload(payload());
  assert.deepEqual(view.metrics.map((metric) => metric.id), ["portfolio_hhi", "turnover", "closed_episode_count"]);
  assert.equal(view.metrics[0].chartMetric?.median, 0.29);
  assert.equal(view.metrics[1].chartMetric?.valueFormat, "percent");
  assert.equal(view.metrics.filter(isCompletePeerBenchmarkMetric).length, 3);
});

test("peer adapter preserves insufficient benchmark state without a range metric", () => {
  const source = payload();
  source.metrics.turnover = result("mean_daily_turnover", {
    metric_n: 29,
    p25: null,
    median: null,
    p75: null,
    percentile: null,
    benchmark_status: "insufficient_cohort",
    benchmark_reason: "Fewer than the descriptive minimum.",
  });
  const metric = adaptPeerBenchmarkPayload(source).metrics[1];
  assert.equal(metric.status, "insufficient_cohort");
  assert.equal(metric.reason, "Fewer than the descriptive minimum.");
  assert.equal(metric.chartMetric, null);
  assert.equal(isCompletePeerBenchmarkMetric(metric), false);
});

test("peer adapter rejects non-synthetic cohort or metric payloads", () => {
  const nonSyntheticCohort = payload();
  nonSyntheticCohort.cohort.data_tier = "production";
  assert.throws(() => adaptPeerBenchmarkPayload(nonSyntheticCohort), /synthetic/);

  const nonSyntheticMetric = payload();
  nonSyntheticMetric.metrics.portfolio_hhi.data_tier = "production";
  assert.throws(() => adaptPeerBenchmarkPayload(nonSyntheticMetric), /synthetic/);
});

test("the old handwritten Compare peer fixture is absent", async () => {
  const fixture = await readFile(new URL("../src/demo/fixture.ts", import.meta.url), "utf8");
  assert.equal(fixture.includes("peerCohort"), false);
  assert.equal(fixture.includes("peerMetrics"), false);
  assert.equal(fixture.includes("p25: 0.54"), false);
});
