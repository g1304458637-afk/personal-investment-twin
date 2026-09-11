import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { adaptSameStock } from "../src/data/sameStock.ts";
import { comparedDecision, sameStockParties, sameStockPartyLabel, sameStockTimelineTimes } from "../src/components/charts/sameStockTimelineModel.ts";

const raw = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8")).same_stock_compare_demo;

test("same-stock chart names supplied records and preserves their exact backend operation", () => {
  const view = adaptSameStock(raw);
  const [a, b] = sameStockParties(view);
  assert.equal(sameStockPartyLabel(a, "Record"), `Record A · ${view.a.symbol}`);
  assert.equal(sameStockPartyLabel(b, "Record"), `Record B · ${view.b.symbol}`);
  const found = comparedDecision(view, view.b.decisions[1].id);
  assert.equal(found?.party.id, "B");
  assert.deepEqual(found?.decision, view.b.decisions[1]);
});

test("same-stock zoom observes only common market closes while executions remain visible boundaries", () => {
  const view = adaptSameStock(raw);
  const { observationTimes, boundaryTimes } = sameStockTimelineTimes(view);
  assert.deepEqual(observationTimes, [...new Set(view.prices.map((point) => {
    const instant = new Date(point.at);
    return new Date(instant.getFullYear(), instant.getMonth(), instant.getDate()).getTime();
  }))].sort((a, b) => a - b));
  assert.ok(boundaryTimes.includes(Date.parse(view.a.decisions[0].at)));
  assert.ok(boundaryTimes.includes(Date.parse(view.b.decisions[0].at)));
  assert.equal(observationTimes.includes(Date.parse(view.a.decisions[0].at)), false, "an execution is not fabricated as a market close");
});
