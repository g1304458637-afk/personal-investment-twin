import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("research portfolio comparison consumes the stable period projection without financial arithmetic", async () => {
  const component = await source("components/comparison/ResearchPortfolioComparison.tsx");
  assert.match(component, /left: ResearchPeriod; right: ResearchPeriod/);
  assert.match(component, /period\.performance\.periodReturn/);
  assert.match(component, /period\.performance\.maxDrawdown/);
  assert.match(component, /period\.performance\.volatility/);
  assert.match(component, /period\.behavior\.hhi/);
  assert.match(component, /period\.behavior\.turnover/);
  assert.doesNotMatch(component, /calculate|portfolioReplay|Math\.(abs|pow)|periodReturn\s*[-+*/]/i);
});

test("research comparison keeps same-period paths together and independent periods on real date axes", async () => {
  const component = await source("components/comparison/ResearchPortfolioComparison.tsx");
  assert.match(component, /samePeriod \? <PerformanceSeriesChart periods=\{periodItems\}/);
  assert.match(component, /research-comparison__separate-series/);
  assert.match(component, /periods=\{\[item\]\}/);
  assert.match(component, /TimeSeriesFrame title=\{title\}.*navigation=\{navigation\}/);
  assert.match(component, /useDailyTimeNavigation\(`research-performance:/);
  assert.match(component, /dailyTimeCoordinate\(point\.date\)/);
  assert.match(component, /frameDailyTimeDomain\(observationTimes\)/);
  assert.match(component, /connectNulls: false/);
  assert.match(component, /smooth: false/);
  assert.match(component, /frameDataZoom/);
  assert.match(component, /resetKey=\{title\}/);
  assert.doesNotMatch(component, /resetKey=\{`\$\{title\}-\$\{metric\}/);
  assert.match(component, /c\.benchmark/);
  assert.doesNotMatch(component, /observationCount.*Date\.parse|ordinal/i);
});

test("research comparison projects direct/look-through allocations and selected operation state", async () => {
  const component = await source("components/comparison/ResearchPortfolioComparison.tsx");
  const copy = await source("components/comparison/researchComparisonCopy.ts");
  assert.match(component, /allocation\.direct/);
  assert.match(component, /allocation\.underlying/);
  assert.match(component, /slice\.directWeight/);
  assert.match(component, /slice\.indirectWeight/);
  assert.match(component, /slice\.paths/);
  assert.match(component, /setSelectedOperation\(null\)/);
  assert.doesNotMatch(component, /navigate|Link|episodeId.*to=/);
  assert.match(component, /LegendComponent/);
  assert.match(component, /c\.notHeld/);
  assert.match(component, /leftLabel.*rightLabel/);
  assert.match(component, /c\.noEligibleLossObservations/);
  assert.match(copy, /双方净值从 100 起步/);
  assert.match(copy, /Both NAV paths start at 100/);
  assert.match(component, /periods\[0\]\.period\.benchmark\.points/);
  assert.match(component, /comparison\.differences/);
  assert.doesNotMatch(component, /href="#comparison/);
});
