import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { adaptSameStock, comparisonHighlight } from "../src/data/sameStock.ts";
const raw = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8")).same_stock_compare_demo;

test("same-stock view copies authoritative results, fees and dates without arithmetic", () => {
  const view = adaptSameStock(raw);
  for (const who of ["a", "b"]) {
    assert.equal(view[who].pnl, raw[who].outcome.actual_result.pnl);
    assert.equal(view[who].returnValue, raw[who].outcome.actual_result.return_value);
    assert.equal(view[who].entryFees, raw[who].outcome.actual_result.recorded_entry_fees);
    assert.equal(view[who].start, raw[who].episode.opened_at);
    assert.equal(view[who].tier, "synthetic");
    assert.deepEqual(view[who].decisions.map((d) => d.id), raw[who].decisions.map((d) => d.decision_event_id));
  }
  assert.ok(Math.abs(view.a.pnl + 355) < 1e-8);
  assert.ok(Math.abs(view.b.pnl - 195) < 1e-8);
});
test("one finding highlights both exact canonical lanes and the shared market window", () => {
  const v = adaptSameStock(raw), f = v.differences[0];
  assert.deepEqual(comparisonHighlight(v, f.id), { start: f.start, end: f.end, aRefs: f.aRefs, bRefs: f.bRefs });
  assert.equal(comparisonHighlight(v, "unknown"), null);
  assert.ok(f.aRefs.every((id) => v.a.decisions.some((d) => d.id === id)));
  assert.ok(f.bRefs.every((id) => v.b.decisions.some((d) => d.id === id)));
});
test("unavailable comparison cannot retain a valid shared chart or previous differences", () => {
  const v = adaptSameStock({ ...raw, status: "unavailable" });
  assert.deepEqual(v.prices, []);
  assert.deepEqual(v.differences, []);
  assert.throws(() => adaptSameStock({ ...raw, status: "good_investor" }));
});
test("normalization is copied from backend and never a relative risk calculation", () => {
  const v = adaptSameStock(raw);
  assert.deepEqual(v.a.shape.map((p) => p.value), raw.a_position_shape.map((p) => p.normalized_quantity));
  assert.deepEqual(v.b.shape.map((p) => p.quantity), raw.b_position_shape.map((p) => p.quantity));
});
