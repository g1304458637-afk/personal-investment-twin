import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("same-stock page switches only between the supplied A/B synthetic records", async () => {
  const page = await source("pages/SameStockComparePage.tsx");
  assert.match(page, /useState<"A" \| "B">\("A"\)/);
  assert.match(page, /comparisonScope\(\s*sameStockCompareDemo,\s*reviewSide/s);
  assert.match(page, /pair_side: side/);
  assert.match(page, /data_mode: "synthetic_showcase"/);
  assert.doesNotMatch(page, /fetch\(|invoke\(|accountId=/);
});

test("same-stock UI distinguishes full-period facts from the shared observation window", async () => {
  const panel = await source("components/review/SameStockComparisonPanel.tsx");
  const copy = await source("components/review/sameStockCompareCopy.ts");
  assert.match(panel, /c\.fullPeriod/);
  assert.match(panel, /c\.sharedWindow/);
  assert.match(panel, /timestamp\(s\.start\)/);
  assert.match(panel, /view\.differences\.slice\(0, 3\)/);
  assert.match(copy, /完整投资期间/);
  assert.match(copy, /Full investment period/);
  assert.match(copy, /no common-window return is calculated/);
  assert.match(panel, /<TimeSeriesFrame/);
  assert.match(panel, /data-selected-operation/);
  assert.match(panel, /sameStockTimelineTimes/);
  assert.match(panel, /sameStockPartyLabel/);
  assert.match(panel, /showcaseInstrumentName/);
  assert.match(panel, /operationKinds/);
});

test("timeline aligns named records on one time store and uses only backend quantities or recorded average costs", async () => {
  const chart = await source("components/charts/SameStockTimeline.tsx");
  assert.match(chart, /pathMode: "quantity" \| "cost"/);
  assert.match(chart, /pathMode === "quantity" \? point\.quantity : point\.cost/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /c\.exactTime/);
  assert.match(chart, /sameStockPartyLabel/);
  assert.match(chart, /showcaseInstrumentName/);
  assert.match(chart, /operationKinds/);
  assert.match(chart, /decisionId: decision\.id/);
  assert.match(chart, /timeNavigation=\{timeNavigation\}/);
  assert.match(chart, /observationTimes=\{observationTimes\}/);
  assert.match(chart, /xAxisIndex: \[0, 1, 2\]/);
  assert.match(chart, /filter\(\(control\) => control\.type !== "slider"\)/);
  assert.match(chart, /trigger: "axis"/);
  assert.match(chart, /axisPointer: \{ type: "cross" \}/);
  assert.match(chart, /left: 120, right: 24/);
  assert.doesNotMatch(chart, /account_weight|accountWeight|risk weight/i);
  assert.doesNotMatch(chart, /candlestick|OHLC|volume/i);
});
