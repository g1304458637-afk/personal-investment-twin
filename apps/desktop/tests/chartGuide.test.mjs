import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { chartGuideCatalog, chartGuideIds, chartGuideTarget } from "../src/data/chartGuide.ts";

test("chart guide catalog is a closed three-guide allowlist", () => {
  assert.deepEqual(chartGuideIds, ["episode-process", "pretrade-allocation", "same-stock"]);
  assert.deepEqual(Object.keys(chartGuideCatalog), [...chartGuideIds]);
  assert.equal(chartGuideTarget("episode-process", "episode:one", "decision:one"), "/investments/episodes/episode%3Aone?section=process&guide=episode-process&decision=decision%3Aone");
  assert.equal(chartGuideTarget("pretrade-allocation"), "/pretrade?guide=pretrade-allocation");
  assert.equal(chartGuideTarget("same-stock"), "/investments/compare-example?guide=same-stock");
});

test("chart guide routes reject arbitrary or malformed targets", () => {
  for (const args of [
    ["not-a-guide"], ["episode-process"], ["episode-process", "../other"],
    ["episode-process", "episode", "bad/query"], ["pretrade-allocation", "episode"],
    ["same-stock", undefined, "decision"],
  ]) assert.equal(chartGuideTarget(...args), null);
});

test("guide UI contains no simulation action and pages use hard-coded anchors", async () => {
  const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const guide = await read("../src/components/guidance/ChartGuide.tsx");
  assert.doesNotMatch(guide, /runCheck|checkPretrade|dispatch\(/);
  assert.match(guide, /visibleGuideTarget/);
  assert.match(guide, /closest<HTMLElement>\("\[data-guide-scope\]"\)/);
  assert.doesNotMatch(guide, /document\.querySelector/);
  assert.match(guide, /event\.key === "Escape"/);
  for (const path of ["../src/pages/PositionEpisodePage.tsx", "../src/pages/DecisionCheckPage.tsx", "../src/pages/SameStockComparePage.tsx"]) {
    assert.match(await read(path), /data-guide=/);
  }
});

test("guide steps have aligned English copy and distinct visible targets", async () => {
  for (const guide of Object.values(chartGuideCatalog)) {
    assert.ok(guide.title.zh && guide.title.en);
    for (const step of guide.steps) {
      assert.ok(step.title.zh && step.title.en && step.detail.zh && step.detail.en);
    }
  }
  assert.deepEqual(chartGuideCatalog["episode-process"].steps.map((step) => step.anchor), ["episode-price-cost", "episode-price-cost", "episode-quantity"]);
  assert.deepEqual(chartGuideCatalog["same-stock"].steps.map((step) => step.anchor), ["same-stock-price", "same-stock-trades", "same-stock-quantity"]);
  const workspace = await readFile(new URL("../src/components/charts/InvestmentChartWorkspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /investment-chart-quantity-guide-target/);
  assert.doesNotMatch(workspace, /data-guide="episode-quantity" className="investment-chart-navigator"/);
});
