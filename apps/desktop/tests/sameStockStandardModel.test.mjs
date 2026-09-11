import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { adaptSameStock } from "../src/data/sameStock.ts";
import { adaptStandardChartDemo } from "../src/data/standardChart.ts";
import { aggregateStandardBars } from "../src/components/charts/standardChartModel.ts";
import { matchingComparisonChart, comparisonBarStates, comparisonBarGroups } from "../src/components/charts/sameStockStandardModel.ts";

const source = JSON.parse(await readFile(new URL("../src/generated/showcase-demo.json", import.meta.url), "utf8"));
const view = adaptSameStock(source.same_stock_compare_demo);
const charts = source.charts.map(adaptStandardChartDemo);
const chart = matchingComparisonChart(view, charts);

test("shipped comparison joins exactly the investment execution sequence and all 105 closes", () => {
  assert.ok(chart);
  assert.equal(chart.market.bars.length, 260);
  assert.equal(view.prices.length, 105);
  assert.notEqual(chart.entry.episode.episodeId, view.a.episodeId);
  assert.deepEqual(chart.entry.decisions.map(d => d.occurredAt), view.a.decisions.map(d => d.at));
  const closes = new Map(chart.market.bars.map(bar => [bar.date, bar.close]));
  for (const point of view.prices) assert.equal(closes.get(point.at.slice(0, 10)), point.value);
});

test("never borrows showcase candles for real data, another subject, changed trades or mismatched closes", () => {
  for (const mutate of [
    v => { v.a.tier = "real"; }, v => { v.b.tier = "real"; },
    v => { v.a.subjectId = "another-account"; }, v => { v.b.currency = "USD"; },
    v => { v.a.decisions[0].price += 1; }, v => { v.a.decisions[0].costAfter += 1; },
    v => { v.prices[0].value += 0.01; }, v => { v.prices = []; },
    v => { v.b.decisions[0].at = "2025-01-12T10:00:00"; },
  ]) {
    const altered = structuredClone(view); mutate(altered);
    assert.equal(matchingComparisonChart(altered, charts), null);
  }
});

test("A/B period-end paths copy backend states and hide costs after close", () => {
  const bars = chart.market.bars;
  for (const side of [view.a, view.b]) {
    const result = comparisonBarStates(side, bars, bars);
    assert.equal(result[0].quantity, null);
    for (const decision of side.decisions) {
      const state = result.find(s => s.date === decision.at.slice(0, 10));
      assert.equal(state.quantity, decision.after);
      assert.equal(state.averageCost, decision.after > 0 ? decision.costAfter : null);
    }
    assert.equal(result.at(-1).quantity, 0);
    assert.equal(result.at(-1).averageCost, null);
  }
});

test("day/week/month candles preserve all A/B trades and period-end states", () => {
  for (const interval of ["day", "week", "month"]) {
    const bars = aggregateStandardBars(chart.market.bars, interval);
    const groups = comparisonBarGroups(view, chart.market.bars, bars);
    for (const party of ["A", "B"]) {
      const side = party === "A" ? view.a : view.b;
      assert.deepEqual(groups.filter(g => g.party === party).flatMap(g => g.decisions), side.decisions);
      const daily = comparisonBarStates(side, chart.market.bars, chart.market.bars);
      const grouped = comparisonBarStates(side, chart.market.bars, bars);
      for (let i = 0; i < bars.length; i++) {
        const expected = daily.filter(s => s.date >= bars[i].date && (!bars[i + 1] || s.date < bars[i + 1].date)).at(-1);
        assert.equal(grouped[i].quantity, expected.quantity);
        assert.equal(grouped[i].averageCost, expected.averageCost);
      }
    }
  }
});

test("same-day executions stay inspectable and use the final supplied closing state", () => {
  const v = structuredClone(view);
  v.a.decisions.push({ ...v.a.decisions[0], id: "later-trade", at: "2025-01-13T11:00:00", after: 450 });
  v.a.shape.push({ at: "2025-01-13T11:00:00", quantity:450, cost:10.25, value:0, decisionId:"later-trade" });
  const groups = comparisonBarGroups(v, chart.market.bars, chart.market.bars);
  assert.equal(groups.find(g => g.party === "A" && g.date === "2025-01-13").decisions.length, 2);
  const state = comparisonBarStates(v.a, chart.market.bars, chart.market.bars).find(s => s.date === "2025-01-13");
  assert.deepEqual(state, {date:"2025-01-13", quantity:450, averageCost:10.25});
});

test("comparison reuses the investment workspace and keeps the plot transparent", async () => {
  const panel = await readFile(new URL("../src/components/review/SameStockComparisonPanel.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/components/charts/investment-chart-workspace.css", import.meta.url), "utf8");
  assert.match(panel, /standardChart \? <InvestmentChartWorkspace/);
  assert.match(css, /\.investment-chart-workspace\.is-comparison \{ background: transparent; box-shadow: none; \}/);
});
