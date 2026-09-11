import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("showcase Episode routes use their registered OHLC workspace while real routes retain close-only charts", async () => {
  const page = await source("../src/pages/PositionEpisodePage.tsx");
  assert.match(page, /<EpisodeChartWorkspace/);
  assert.match(page, /entry=\{chartEntry\}/);
  assert.match(page, /showcaseChartForEpisode/);
  assert.match(page, /<InvestmentChartWorkspace entry=\{entry\} market=\{showcaseChart\.market\}/);
  assert.match(page, /onSelectDecision=\{lensMode \? selectLensDecision : setSelectedDecisionId\}/);
});

test("close-only workspace has one shared navigator while both recorded panes use the same store", async () => {
  const workspace = await source("../src/components/charts/EpisodeChartWorkspace.tsx");
  assert.match(workspace, /<TimeSeriesFrame/);
  assert.match(workspace, /navigation=\{timeNavigation\}/);
  assert.equal((workspace.match(/timeNavigation=\{timeNavigation\}/g) ?? []).length, 2);
  assert.equal((workspace.match(/showNavigator=\{false\}/g) ?? []).length, 2);
  assert.match(workspace, /<PositionEpisodeTimeline/);
  assert.match(workspace, /<PositionQuantityTimeline/);
  assert.doesNotMatch(workspace, /aggregateStandardBars|KLineData|market\.bars/);
});

test("price and quantity panes suppress duplicate sliders and share x-axis rails", async () => {
  const price = await source("../src/components/charts/PositionEpisodeTimeline.tsx");
  const quantity = await source("../src/components/charts/PositionQuantityTimeline.tsx");
  for (const chart of [price, quantity]) {
    assert.match(chart, /showNavigator\s*\?\s*dailyDataZoom/);
    assert.match(chart, /control\.type !== "slider"/);
    assert.match(chart, /left: 64, right: 116/);
  }
  assert.match(quantity, /boundaryGap: \["4%", "8%"\]/);
});
