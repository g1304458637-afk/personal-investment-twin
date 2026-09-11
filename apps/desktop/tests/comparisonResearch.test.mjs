import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { adaptComparisonResearch } from "../src/data/comparisonResearch.ts";
const raw = JSON.parse(await readFile(new URL("../src/generated/comparison-research-demo.json", import.meta.url), "utf8"));
const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("three independent synthetic accounts map exact Python numbers and real dates", () => {
  const result = adaptComparisonResearch(raw);
  assert.equal(result.dataTier, "synthetic");
  assert.equal(result.accounts.length, 3);
  for (const [i, a] of result.accounts.entries()) for (const k of ["earlier", "recent", "full"]) {
    const p = a.periods[k], r = raw.accounts[i].periods[k];
    assert.equal(p.performance.periodReturn, r.performance.period_return);
    assert.equal(p.performance.maxDrawdown, r.performance.max_drawdown_magnitude);
    assert.equal(p.behavior.turnover, r.behavior.mean_daily_turnover);
    assert.equal(p.behavior.pgrMinusPlr, r.behavior.disposition.disposition_effect);
    assert.equal(p.behavior.eligibleAdds, r.behavior.loss_averaging.eligible_add_events);
    assert.deepEqual(p.performance.points.map(p => p.date), r.performance.points.map(p => p.observed_at.slice(0,10)));
    assert.equal(p.performance.points[0].nav, 100);
    assert.equal(p.performance.sharpe, null);
    assert.deepEqual(p.allocation.underlying.map(x => x.weight), r.allocation.lookthrough.exposures.map(x => x.weight));
  }
});

test("scope, method, dates and malformed financial values fail closed", () => {
  for (const mutate of [
    p => { p.data_tier = "real"; },
    p => { p.accounts[0].subject_id = "other"; },
    p => { p.accounts[0].periods.full.performance.account_id = p.accounts[1].account_id; },
    p => { p.accounts[0].periods.full.performance.method_version = "unknown"; },
    p => { p.accounts[0].periods.full.performance.points.reverse(); },
    p => { p.accounts[0].periods.full.performance.points[1].cumulative_nav = Infinity; },
    p => { p.accounts[0].periods.full.behavior.end_date = "2030-01-01"; },
    p => { p.accounts[0].periods.full.benchmark.points.pop(); },
    p => { p.accounts[0].periods.full.operations[0].date = "2025-01-02T16:00:00"; },
    p => { p.accounts[0].periods.full.allocation.direct[0].weight = .999; },
  ]) { const p = structuredClone(raw); mutate(p); assert.throws(() => adaptComparisonResearch(p)); }
});

test("same underlying security retains direct + fund paths; no fabricated PLR", () => {
  const a = adaptComparisonResearch(raw).accounts[0].periods.recent;
  const s = a.allocation.underlying.find(x => x.id === "SYN_VALUE");
  assert.ok(s.directWeight > 0 && s.indirectWeight > 0);
  assert.deepEqual(s.paths, [["SYN_FUND", "SYN_VALUE"], ["SYN_VALUE"]]);
  assert.equal(a.behavior.plr, null); assert.equal(a.behavior.pgrMinusPlr, null);
  assert.equal(a.behavior.lossRate, 0); assert.equal(a.behavior.eligibleAdds, 2);
});

test("comparison preserves backend difference direction and rejects mismatched pairs", () => {
  const result = adaptComparisonResearch(raw);
  assert.deepEqual(result.comparisons.self.differences.map(d => d.change), raw.comparisons.self.differences.map(d => d.right_minus_left));
  for (const mutate of [
    p => { p.comparisons.self.right_account_id = "SYN_STUDY_FOCUSED"; },
    p => { p.comparisons.professional.SYN_STUDY_BALANCED.full.right_period_end = "2025-04-02"; },
    p => { p.comparisons.self.differences[0].unit = "percent"; },
    p => { p.comparisons.self.differences[0].right_minus_left = null; },
    p => { p.comparisons.self.differences.push(p.comparisons.self.differences[0]); },
  ]) { const p = structuredClone(raw); mutate(p); assert.throws(() => adaptComparisonResearch(p)); }
});

test("real-account gate is explicit and showcase research cannot mutate account or invoke models", async () => {
  const workspace = await source("workspace/ResearchComparisonStudy.tsx");
  assert.match(workspace, /mode !== "demo"/);
  assert.doesNotMatch(workspace, /setMode|setActiveAccount|setExampleAccount|invoke\(|fetch\(|reviewService/);
  const copy = await source("workspace/researchStudyCopy.ts");
  assert.match(copy, /不代表真实专业人士/);
  assert.match(copy, /complete synthetic showcase account/);
});

test("fund disclosure dates come from used membership versions, not classification dates", () => {
  const p = structuredClone(raw);
  const lookthrough = p.accounts[0].periods.full.allocation.lookthrough;
  lookthrough.selected_disclosures[0].published_at = "2025-01-03T00:00:00";
  const actual = adaptComparisonResearch(p).accounts[0].periods.full.allocation.disclosures[0];
  assert.equal(actual.publishedDate, "2025-01-03");
  assert.equal(actual.effectiveDate, "2025-01-02");
  assert.deepEqual(actual.sourceIds, lookthrough.selected_disclosures[0].source_ids);
  for (const key of ["effective_at", "published_at", "observed_at"]) {
    const future = structuredClone(raw);
    future.accounts[0].periods.full.allocation.lookthrough.selected_disclosures[0][key] = "2030-01-01T00:00:00";
    assert.throws(() => adaptComparisonResearch(future), /Future comparison disclosure/);
  }
});
