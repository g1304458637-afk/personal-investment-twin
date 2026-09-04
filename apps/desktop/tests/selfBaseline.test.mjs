import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const {
  adaptSelfBaselinePayload,
  allWindowsUseSameObservations,
} = await import("../src/data/selfBaseline.ts");
const generated = JSON.parse(await readFile(
  new URL("../src/generated/backend-demo-evidence.json", import.meta.url),
  "utf8",
));

function source() {
  return structuredClone(generated.self_baseline);
}

function adapt(payload = source()) {
  return adaptSelfBaselinePayload(payload, generated.twin.current_snapshot.subject_id);
}

test("maps all registered windows and keeps rolling 12m as the default", () => {
  const view = adapt();
  assert.equal(view.defaultWindow, "rolling_12m");
  assert.deepEqual(
    view.metrics.map((metric) => metric.metricId).sort(),
    ["mean_daily_turnover", "portfolio_concentration_hhi"],
  );
  for (const metric of view.metrics) {
    assert.deepEqual(metric.windows.map((item) => item.window), [
      "rolling_3m",
      "rolling_12m",
      "lifetime",
    ]);
  }
});

test("preserves observation range, cadence, method identity, and backend delta", () => {
  const hhi = adapt().metrics.find((item) => item.metricId === "portfolio_concentration_hhi");
  const annual = hhi.windows.find((item) => item.window === "rolling_12m");
  assert.equal(annual.observationStart, "2025-01-02T00:00:00");
  assert.equal(annual.observationEnd, "2025-01-07T00:00:00");
  assert.equal(annual.observationCadence, "supplied_complete_market_price_observation_dates");
  assert.equal(annual.sourceMethodId, "hhi_security_weights_v1");
  assert.equal(annual.provenance.quantileMethod, "numpy_quantile_linear_v1");
  assert.equal(annual.provenance.percentileMethod, "empirical_midrank_percentile_v1");
  assert.equal(annual.deltaFromMedian, generated.self_baseline.metrics
    .find((item) => item.metric_id === "portfolio_concentration_hhi")
    .windows.find((item) => item.window === "rolling_12m").delta_from_median);
});

test("rolling 12m remains a lookback while short actual observation coverage stays explicit", async () => {
  const annual = adapt().metrics
    .find((item) => item.metricId === "portfolio_concentration_hhi")
    .windows.find((item) => item.window === "rolling_12m");
  assert.equal(annual.validN, 4);
  assert.equal(annual.observationStart, "2025-01-02T00:00:00");
  assert.equal(annual.observationEnd, "2025-01-07T00:00:00");

  const section = await readFile(new URL("../src/components/twin/SelfBaselineSection.tsx", import.meta.url), "utf8");
  const zh = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");
  const en = await readFile(new URL("../src/locales/en-US.ts", import.meta.url), "utf8");
  assert.match(section, /Actual observations/);
  assert.match(section, /Observed range/);
  assert.match(section, /observationStart/);
  assert.match(section, /observationEnd/);
  assert.match(section, /validN/);
  assert.match(zh, /"12 months": "过去 12 个月"/);
  assert.match(zh, /"\{window\} lookback · \{position\}": "\{window\}回看窗口/);
  assert.match(en, /"12 months": "12 months"/);
  assert.match(en, /"\{window\} lookback · \{position\}"/);
  for (const misleading of [
    /完整过去一年/,
    /过去一年大多数时间/,
    /过去12个月通常水平/,
    /complete 12[- ]month history/i,
    /most of the past year/i,
  ]) {
    assert.doesNotMatch(`${section}\n${zh}\n${en}`, misleading);
  }
});

test("irregular observations are disclosed as equal-weighted rather than time-weighted", async () => {
  const hhi = adapt().metrics.find((item) => item.metricId === "portfolio_concentration_hhi");
  assert.equal(hhi.observationCadence, "supplied_complete_market_price_observation_dates");
  assert.ok(hhi.windows.every((item) => item.limitations.some(
    (limitation) => limitation.includes("observation-weighted") && limitation.includes("not a time-weighted"),
  )));

  const section = await readFile(new URL("../src/components/twin/SelfBaselineSection.tsx", import.meta.url), "utf8");
  assert.match(section, /Equal per observation/);
  assert.match(section, /Time-weighted/);
  assert.match(section, /Missing dates are not filled/);
});

test("turnover keeps represented no-trade zero distinct from an absent date", () => {
  const turnover = adapt().metrics.find((item) => item.metricId === "mean_daily_turnover");
  for (const item of turnover.windows) {
    assert.ok(item.limitations.some((limitation) => (
      limitation.includes("no trade contributes zero turnover")
      && limitation.includes("absent from the source is not silently inserted")
    )));
  }
});

test("identical 3m, 12m, and lifetime observation sets are disclosed without fabricated differences", async () => {
  const view = adapt();
  assert.equal(allWindowsUseSameObservations(view), true);

  const changed = structuredClone(view);
  changed.metrics[0].windows[2].provenance.historicalPointSourceRefs.push("different-source-ref");
  assert.equal(allWindowsUseSameObservations(changed), false);

  const section = await readFile(new URL("../src/components/twin/SelfBaselineSection.tsx", import.meta.url), "utf8");
  assert.match(section, /allWindowsUseSameObservations/);
  assert.match(section, /currently contain the same valid observations/);
});

test("insufficient results retain N and reason while all numeric statistics stay null", () => {
  const turnover = adapt().metrics.find((item) => item.metricId === "mean_daily_turnover");
  const annual = turnover.windows.find((item) => item.window === "rolling_12m");
  assert.equal(annual.status, "insufficient_self_history");
  assert.equal(annual.validN, 4);
  assert.match(annual.insufficientReason, /5 are required/);
  assert.deepEqual(
    [annual.median, annual.p25, annual.p75, annual.selfHistoricalPercentile, annual.deltaFromMedian],
    [null, null, null, null, null],
  );
  assert.equal(annual.comparisonBand, null);
});

test("wrong subject, malformed payload, unsupported metric, unknown window, and duplicates fail closed", () => {
  const wrongSubject = source();
  wrongSubject.subject_id = "another-subject";
  assert.throws(() => adapt(wrongSubject), /subject does not match/);

  const malformed = source();
  malformed.metrics[0].windows[0].valid_n = -1;
  assert.throws(() => adapt(malformed), /non-negative integer/);

  const unsupported = source();
  unsupported.metrics[0].metric_id = "selection_episode_asset_return";
  assert.throws(() => adapt(unsupported), /unsupported/);

  const unknownWindow = source();
  unknownWindow.metrics[0].windows[0].window = "rolling_6m";
  assert.throws(() => adapt(unknownWindow), /unsupported window/);

  const duplicate = source();
  duplicate.metrics.push(structuredClone(duplicate.metrics[0]));
  assert.throws(() => adapt(duplicate), /duplicate metric/);
});

test("generated payload is deterministic data and adapters contain no financial calculation helpers", async () => {
  const first = JSON.stringify(adapt());
  const second = JSON.stringify(adapt());
  assert.equal(first, second);

  const adapter = await readFile(new URL("../src/data/selfBaseline.ts", import.meta.url), "utf8");
  const page = await readFile(new URL("../src/pages/MyTwinPage.tsx", import.meta.url), "utf8");
  const section = await readFile(new URL("../src/components/twin/SelfBaselineSection.tsx", import.meta.url), "utf8");
  assert.match(page, /SelfBaselineSection summary=\{selfBaseline\}/);
  assert.match(section, /summary\.defaultWindow/);
  assert.match(section, /role="img"/);
  for (const forbidden of [/Math\.pow/, /Math\.sqrt/, /reduce\([^)]*\+/, /numpy/, /percentileofscore/]) {
    assert.doesNotMatch(adapter, forbidden);
    assert.doesNotMatch(page, forbidden);
    assert.doesNotMatch(section, forbidden);
  }
  for (const forbiddenCoverage of [/coveragePercent/i, /daysCovered/i, /missingDayRatio/i, /coverageScore/i, /confidenceScore/i]) {
    assert.doesNotMatch(adapter, forbiddenCoverage);
    assert.doesNotMatch(section, forbiddenCoverage);
  }
});
