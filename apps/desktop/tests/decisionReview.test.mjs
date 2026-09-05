import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { reviewRows, selfHistoryRows, ReviewRequestGuard } from "../src/data/decisionReview.ts";

test("review financial rows preserve backend values and distinct historical hypotheses", () => {
  const actual = reviewRows({ kind: "episode", value: { result: { result_kind: "marked", pnl: -354.9999999999991, return_value: -.1014285714 } } });
  assert.equal(actual[0].label, "Current marked result");
  assert.equal(actual[0].value, -354.9999999999991);
  assert.equal(actual[1].value, -.1014285714);
  const cf = reviewRows({ kind: "historical_comparison", availability: "complete", value: {
    actual_result: { pnl: -100, valuation_at: "2025-01-03T00:00:00" }, counterfactual_result: { pnl: -30 },
    comparison: { pnl_difference: 70 }, evaluation_end: "2025-01-06T10:00:00", intervention: { changed_action: "omit_selected_executions" }, held_constant: ["included execution prices"] } });
  assert.equal(cf.find((r) => r.label === "Fixed-assumption minus actual result").value, 70);
  assert.equal(cf.find((r) => r.label === "Valuation observation").value, "2025-01-03T00:00:00");
  assert.equal(cf.find((r) => r.label === "Evaluation end").value, "2025-01-06T10:00:00");
});
test("self-history copies registered observation count and cannot invent unavailable statistics", () => {
  const record = { value: { summary: { default_window: "rolling_12m", metrics: [{ metric_id: "mean_daily_turnover", windows: [{ window: "rolling_12m", current_value: .02, valid_n: 2, status: "insufficient_self_history", median: null, insufficient_reason: "too_few_observations" }] }] } } };
  const [row] = selfHistoryRows(record);
  assert.equal(row.n, 2); assert.equal(row.current, .02); assert.equal(row.median, null);
  assert.equal(row.status, "insufficient_self_history");
});
test("older model responses cannot replace new target / question / note results", () => {
  const guard = new ReviewRequestGuard(), old = guard.next(), newer = guard.next();
  assert.equal(guard.accepts(old), false); assert.equal(guard.accepts(newer), true);
  guard.next(); assert.equal(guard.accepts(newer), false);
});
test("desktop gate, loading, explicit model consent and note invalidation remain visible", async () => {
  const source = await readFile(new URL("../src/components/review/DecisionAnalysisWorkspace.tsx", import.meta.url), "utf8");
  assert.match(source, /Browser · Offline Runtime/);
  assert.match(source, /No model has been called/);
  assert.match(source, /disabled=\{busy \|\| loading \|\| !consent\}/);
  assert.match(source, /response.status !== "running"/);
  assert.match(source, /guard.current.accepts\(ticket\)/);
  assert.match(source, /setAnswer\(null\)/);
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/);
});
test("service uses only narrow review/share RPC and never invents a browser model response", async () => {
  const source = await readFile(new URL("../src/data/reviewService.ts", import.meta.url), "utf8");
  assert.match(source, /"review.start"/); assert.match(source, /"compare.import_share"/);
  assert.doesNotMatch(source, /shell|fetch\(|api.deepseek|generated.*inference/);
});
