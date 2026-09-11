import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("historical metric charts retain their existing insufficient and single-observation safeguards", async () => {
  const chart = await source("components/charts/HistoricalMetricChart.tsx");
  assert.match(chart, /if \(mode === "insufficient"\)/);
  assert.match(chart, /if \(mode === "single"\)/);
  assert.match(chart, /type: "time"/);
  assert.match(chart, /data: series\.points\.map\(\(point\) => \[dailyTimeCoordinate\(point\.date\), point\.value\]/);
  assert.match(chart, /frameDailyTimeDomain\(observationTimes\)/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /smooth: false/);
  assert.match(chart, /frameDataZoom/);
  assert.match(chart, /TimeSeriesFrame title=\{label\} navigation=\{timeNavigation\}/);
  assert.match(chart, /useDailyTimeNavigation\(`behavior-history:/);
});

test("legacy portfolio trend uses its recorded dates and amounts without smoothing", async () => {
  const chart = await source("components/charts/PortfolioTrendChart.tsx");
  assert.match(chart, /type: "time"/);
  assert.match(chart, /portfolioHistory\.map\(\(point\) => \[dailyTimeCoordinate\(point\.date\), point\.value\]/);
  assert.match(chart, /portfolioHistory\.map\(\(point\) => \[dailyTimeCoordinate\(point\.date\), point\.reference\]/);
  assert.match(chart, /frameDailyTimeDomain\(observationTimes\)/);
  assert.match(chart, /formatCurrency\(value\)/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /smooth: false/);
  assert.match(chart, /frameDataZoom/);
  assert.match(chart, /TimeSeriesFrame/);
  assert.doesNotMatch(chart, /point\.date\.slice\(5\)/);
});
