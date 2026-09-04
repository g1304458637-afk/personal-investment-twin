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
  assert.match(chart, /entry\.pricePoints/);
  assert.match(chart, /decision\.executionPrice/);
  assert.match(chart, /current\.valuationPrice/);
  assert.match(chart, /decision\.outcome\.after\.averageCost/);
  assert.match(chart, /id: "average-cost"/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /selectedDecisionId/);
  assert.match(chart, /markArea/);
  assert.match(chart, /pre-entry-price/);
  assert.match(chart, /post-exit-price/);
  assert.match(chart, /Holding period/);
  assert.match(chart, /0\.016/);
  assert.doesNotMatch(chart, /0\.055/);
  assert.doesNotMatch(chart, /areaStyle/);
  assert.match(chart, /minInterval: MS_PER_DAY/);
  assert.match(chart, /dailyDataZoom\(8, minValueSpan\)/);
  assert.match(chart, /formatDailyAxisTick/);
  assert.match(chart, /hideOverlap: true/);
  assert.match(chart, /bySegment\("pre_entry"\)\.length/);
  assert.match(chart, /hasPreEntryPath \?/);
  assert.match(chart, /hasPostExitPath \?/);
  assert.doesNotMatch(chart, /executionPrice.*pricePoints|valuationPrice.*executionPrice/);
});

test("quantity chart is an unsmoothed backend-state step series keyed by event ID", async () => {
  const chart = await readFile(new URL("../src/components/charts/PositionQuantityTimeline.tsx", import.meta.url), "utf8");
  assert.match(chart, /decision\.outcome\.after\.quantity/);
  assert.match(chart, /step: "end"/);
  assert.match(chart, /smooth: false/);
  assert.match(chart, /connectNulls: false/);
  assert.match(chart, /decisionId: decision\.decisionId/);
  assert.match(chart, /chartGroup/);
  assert.match(chart, /markArea/);
  assert.match(chart, /dailyDataZoom\(6, minValueSpan\)/);
  assert.match(chart, /minInterval: MS_PER_DAY/);
  assert.match(chart, /dailyTimeDomain/);
  assert.doesNotMatch(chart, /forward.?fill|interpolat|\.reduce\s*\(/i);
});

test("missing backend cost remains null and never becomes zero", () => {
  const closed = view.entries.find((entry) => entry.instrument.instrumentId === "600000.SH");
  const final = closed.decisions.at(-1);
  assert.equal(final.outcome.after.averageCost, null);
  assert.notEqual(final.outcome.after.averageCost, 0);
});

test("Episode Story keeps path-first structure and Decision drilldown", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  const echart = await readFile(new URL("../src/components/charts/EChart.tsx", import.meta.url), "utf8");
  assert.match(page, /entry\.outcomeStory\.episodeOutcome\.actualResult/);
  assert.match(page, /decision\.outcome\.immediateResult/);
  assert.match(page, /Position quantity \{before\} → \{after\}/);
  assert.match(page, /type="button"/);
  assert.match(page, /aria-expanded/);
  assert.match(page, /data-decision-event-id/);
  assert.match(page, /scrollIntoView/);
  assert.match(page, /selectedDecisionId=\{selectedDecisionId\}/);
  assert.match(page, /selectPrimaryPathItems/);
  assert.match(page, /showPreEntryContext/);
  assert.match(page, /data-path-section/);
  assert.match(page, /data-selected-phase/);
  assert.match(page, /data-phase-counterfactual/);
  assert.match(page, /omit_decision_phase_until_next_decision_v1/);
  assert.match(page, /After the previous decision, the recorded market path rose \{percent\}, then an add occurred\./);
  assert.match(page, /data-path-summary/);
  assert.match(page, /These 3–6 items are selected by the backend/);
  assert.doesNotMatch(page, /追涨|抄底|fear|greed|FOMO|VWAP|groupDecision|耐心|死扛|坚定持有/i);
  assert.doesNotMatch(page, /Math\.(abs|pow)|\.reduce\s*\(/);
  assert.match(echart, /MarkAreaComponent/);
  assert.match(echart, /DataZoomComponent/);
  assert.match(echart, /AxisPointerComponent/);
  assert.match(echart, /connect\(/);
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
  assert.match(zh, /"建仓前已记录的市场观测中，价格上涨 \{percent\}。"/);
  assert.match(zh, /"退出后市场路径"/);
  assert.match(zh, /"加仓阶段"/);
  assert.match(zh, /"减仓阶段"/);
  assert.match(zh, /"After the previous decision, the recorded market path rose \{percent\}, then an add occurred."/);
  assert.match(zh, /"此后 \{count\} 个日历日没有新增交易记录。"/);
  assert.match(zh, /"这 3–6 条由后端选出。界面不重新分组阶段，也不计算市场涨跌。"/);
  assert.doesNotMatch(zh, /你决定坚定持有|死扛|很有耐心|纪律很好/);
  assert.doesNotMatch(en, /you decided to hold|you firmly held|dead.?cat/i);
  assert.doesNotMatch(en, /"Chase the rally|"Bottom.?fish/i);
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

test("generated Product Demo projects backend path analysis without handwritten phases", () => {
  const product = view.entries.find((entry) => entry.instrument.instrumentId === "SYN_PRODUCT");
  assert.ok(product);
  assert.equal(product.episode.episodeId, generated.position_episode_demo.default_episode_id);
  assert.deepEqual(product.decisions.map((item) => item.decisionType), [
    "open_position", "add_position", "add_position", "reduce_position", "reduce_position", "close_position",
  ]);
  assert.deepEqual(product.pathAnalysis.phases.map((item) => item.phaseType), [
    "entry", "scaling_in", "scaling_out", "exit",
  ]);
  assert.notEqual(product.pathAnalysis.marketPath.preEntryContextStatus, "insufficient");
  assert.ok(product.pricePoints.filter((item) => item.segment === "pre_entry").length >= 20);
  assert.ok(product.pathAnalysis.presentationItems.length >= 3);
  assert.ok(product.pathAnalysis.presentationItems.length <= 6);
  assert.ok(product.pricePoints.some((item) => item.segment === "pre_entry"));
  assert.ok(product.pricePoints.some((item) => item.segment === "episode"));
  assert.ok(product.pricePoints.some((item) => item.segment === "post_exit"));
  assert.ok(product.pathAnalysis.phaseCounterfactuals.some((item) => item.scenarioId === "omit_decision_phase_until_next_decision_v1"));
});

function dailyMoves(points) {
  const dates = new Set();
  let up = 0;
  let down = 0;
  let unchanged = 0;
  let flips = 0;
  let previous = null;
  let previousSign = 0;
  for (const point of points) {
    dates.add(point.observedAt.slice(0, 10));
    if (previous !== null) {
      const delta = point.price - previous;
      const sign = delta > 0 ? 1 : delta < 0 ? -1 : 0;
      if (sign > 0) up += 1;
      else if (sign < 0) down += 1;
      else unchanged += 1;
      if (sign !== 0 && previousSign !== 0 && sign !== previousSign) flips += 1;
      if (sign !== 0) previousSign = sign;
    }
    previous = point.price;
  }
  return { uniqueDates: dates.size, up, down, unchanged, flips };
}

test("primary Product Demo market path is an irregular daily series, not a test ramp", () => {
  const product = view.entries.find((entry) => entry.instrument.instrumentId === "SYN_PRODUCT");
  const moves = dailyMoves(product.pricePoints);
  assert.ok(moves.uniqueDates >= 60);
  assert.equal(moves.uniqueDates, product.pricePoints.length);
  assert.ok(moves.up >= 20);
  assert.ok(moves.down >= 20);
  assert.ok(moves.flips >= 15);
  assert.ok(product.pricePoints.filter((item) => item.segment === "pre_entry").length >= 20);
  assert.ok(product.pricePoints.every((point) => point.segment === "pre_entry" || point.segment === "episode" || point.segment === "post_exit"));
  const averageCosts = product.decisions.map((item) => item.outcome.after.averageCost);
  assert.ok(product.pricePoints.some((point) => !averageCosts.includes(point.price)));
  assert.notEqual(product.pricePoints.length, product.decisions.length);
});
