import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
const { adaptPositionEpisodeDemo } = await import("../src/data/positionEpisode.ts");

const view = adaptPositionEpisodeDemo(structuredClone(generated.position_episode_demo));

test("demo covers every Decision type and maps backend before/after state", () => {
  const closed = view.entries.find((entry) => entry.instrument.instrumentId === "600000.SH");
  assert.deepEqual(closed.decisions.map((item) => item.decisionType), ["open_position", "add_position", "reduce_position", "close_position"]);
  for (const decision of closed.decisions) {
    assert.equal(decision.outcome.before.stateRef, decision.stateBeforeRef);
    assert.equal(decision.outcome.after.stateRef, decision.stateAfterRef);
    assert.equal(decision.outcome.executionPrice, decision.executionPrice);
  }
  assert.equal(closed.decisions[1].outcome.before.averageCost, 10);
  assert.equal(closed.decisions[1].outcome.after.averageCost, 10.333333333333334);
});

test("partial profit and loss sales retain backend realized results", () => {
  const profit = view.entries.find((entry) => entry.instrument.instrumentId === "SYN_WIN_SOLD").decisions.find((item) => item.side === "SELL");
  const loss = view.entries.find((entry) => entry.instrument.instrumentId === "SYN_LOSS_SOLD").decisions.find((item) => item.side === "SELL");
  assert.equal(profit.outcome.immediateResult.resultSign, "profit");
  assert.equal(profit.outcome.immediateResult.pnl, 100);
  assert.equal(loss.outcome.immediateResult.resultSign, "loss");
  assert.equal(loss.outcome.immediateResult.pnl, -200);
});

test("chart contracts preserve market, execution, valuation, and average-cost sources", async () => {
  const chart = await readFile(new URL("../src/components/charts/PositionEpisodeTimeline.tsx", import.meta.url), "utf8");
  assert.match(chart, /entry\.pricePoints\.map/);
  assert.match(chart, /decision\.executionPrice/);
  assert.match(chart, /current\.valuationPrice/);
  assert.match(chart, /decision\.outcome\.after\.averageCost/);
  assert.match(chart, /id: "average-cost"/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /selectedDecisionId/);
  assert.doesNotMatch(chart, /executionPrice.*pricePoints|valuationPrice.*executionPrice/);
});

test("quantity chart is an unsmoothed backend-state step series keyed by event ID", async () => {
  const chart = await readFile(new URL("../src/components/charts/PositionQuantityTimeline.tsx", import.meta.url), "utf8");
  assert.match(chart, /decision\.outcome\.after\.quantity/);
  assert.match(chart, /step: "end"/);
  assert.match(chart, /smooth: false/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /decisionId: decision\.decisionId/);
  assert.doesNotMatch(chart, /forward.?fill|interpolat|\.reduce\s*\(/i);
});

test("missing backend cost remains null and never becomes zero", () => {
  const closed = view.entries.find((entry) => entry.instrument.instrumentId === "600000.SH");
  const final = closed.decisions.at(-1);
  assert.equal(final.outcome.after.averageCost, null);
  assert.notEqual(final.outcome.after.averageCost, 0);
});

test("Episode Story keeps critical results and event facts outside hover-only chart UI", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(page, /entry\.outcomeStory\.episodeOutcome\.actualResult/);
  assert.match(page, /decision\.outcome\.immediateResult/);
  assert.match(page, /Position quantity \{before\} → \{after\}/);
  assert.match(page, /type="button"/);
  assert.match(page, /aria-expanded/);
  assert.match(page, /data-decision-event-id/);
  assert.match(page, /scrollIntoView/);
  assert.match(page, /selectedDecisionId=\{selectedDecisionId\}/);
});

test("counterfactual UI reads backend values, transition, assumptions, and infeasibility", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(page, /item\.actualResult\.pnl/);
  assert.match(page, /item\.counterfactualResult\.pnl/);
  assert.match(page, /item\.comparison\.pnlDifference/);
  assert.match(page, /transitionKeys\[item\.comparison\.resultTransition/);
  assert.match(page, /item\.heldConstant\.map/);
  assert.match(page, /infeasible_downstream_execution/);
  assert.match(page, /firstConflictingExecutionId/);
  assert.doesNotMatch(page, /calculatePnL|best action|optimal position|should buy|should sell/i);
  assert.doesNotMatch(page, /Math\.(abs|pow)|\.reduce\s*\(/);
});

test("Exit story separates execution price from fixed-window market price and links Evidence", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(page, /item\.actualExitPrice/);
  assert.match(page, /item\.exitSessionMarketPrice/);
  assert.match(page, /item\.postExitAssetReturn/);
  assert.match(page, /EvidenceExplainButton/);
  assert.match(page, /explainabilityForEvidence/);
});

test("zh-CN and en-US include deterministic Story wording and avoid advice", async () => {
  const zh = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");
  const en = await readFile(new URL("../src/locales/en-US.ts", import.meta.url), "utf8");
  for (const source of [zh, en]) {
    assert.match(source, /"Episode realized profit"/);
    assert.match(source, /"Current unrealized loss"/);
    assert.match(source, /"This sale realized a loss"/);
    assert.match(source, /"If this execution had been omitted"/);
    assert.match(source, /"A full historical alternative cannot be calculated"/);
  }
  assert.match(zh, /"Episode realized profit": "本轮已实现盈利"/);
  assert.match(zh, /"Current unrealized loss": "当前浮动亏损"/);
});

test("responsive Story layout avoids fixed page widths and keeps technical IDs secondary", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(page, /sm:grid-cols/);
  assert.match(page, /lg:grid-cols/);
  assert.match(page, /w-\[min\(96vw,680px\)\]/);
  assert.doesNotMatch(page, /min-w-\[(?:8|9|1\d)\d\dpx\]/);
  assert.match(page, /entry\.outcomeStory\.episodeOutcome/);
  assert.match(page, /<details[^>]*>.*Technical details/s);
});
