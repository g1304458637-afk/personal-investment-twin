import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const generated = JSON.parse(
  await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"),
);
const { adaptPositionEpisodeDemo, selectPrimaryPathItems } = await import("../src/data/positionEpisode.ts");
const view = adaptPositionEpisodeDemo(structuredClone(generated.position_episode_demo));

function entry(instrumentId) {
  const found = view.entries.find((item) => item.instrument.instrumentId === instrumentId);
  assert.ok(found, `missing ${instrumentId}`);
  return found;
}

test("long-horizon fixtures keep the Product Demo as default and retain 1000-point paths", () => {
  const product = entry("SYN_PRODUCT");
  const closed = entry("SYN_LONG_CLOSED");
  const opened = entry("SYN_LONG_OPEN");
  assert.equal(view.defaultEpisodeId, product.episode.episodeId);
  assert.equal(closed.episode.status, "closed");
  assert.equal(opened.episode.status, "open");
  assert.equal(opened.episode.closedAt, null);
  assert.ok(closed.pricePoints.filter((item) => item.segment === "episode").length >= 750);
  assert.ok(opened.pricePoints.length >= 1000);
  assert.equal(closed.pricePoints.length, new Set(closed.pricePoints.map((item) => item.observedAt.slice(0, 10))).size);
  assert.ok(closed.pathAnalysis.marketPath.preEntryContext.validObservationCount <= 20);
  assert.ok(closed.pathAnalysis.marketPath.postExitContext.validObservationCount <= 20);
  assert.equal(opened.pathAnalysis.marketPath.postExitContext.validObservationCount, 0);
  assert.equal(closed.decisions.length, 5);
  assert.deepEqual(closed.decisions.map((item) => item.decisionType), [
    "open_position", "add_position", "add_position", "reduce_position", "close_position",
  ]);
});

test("long-horizon UI density stays path-first and decision-linked", () => {
  const closed = entry("SYN_LONG_CLOSED");
  const items = selectPrimaryPathItems(closed.pathAnalysis);
  assert.ok(items.length <= 6);
  assert.ok(closed.pathAnalysis.marketPath.marketPathSegments.length >= 3);
  assert.ok(closed.pathAnalysis.patterns.some((item) => item.patternCode === "long_no_execution_interval"));
  assert.equal(closed.pathAnalysis.phases.every((item) => ["entry", "scaling_in", "scaling_out", "exit"].includes(item.phaseType)), true);
  assert.equal(closed.outcomeStory.episodeOutcome.actualResult.resultKind, "realized");
  assert.equal(entry("SYN_LONG_OPEN").outcomeStory.episodeOutcome.actualResult.resultKind, "marked");
});

test("long-horizon copy stays neutral and bilingual", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  const zh = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");
  const en = await readFile(new URL("../src/locales/en-US.ts", import.meta.url), "utf8");
  assert.match(page, /data-review-story/);
  assert.match(page, /long_no_execution_interval/);
  assert.doesNotMatch(page, /1000 observation|map\(\(obs/);
  assert.match(zh, /此后 \{count\} 个日历日没有新增交易记录/);
  assert.match(en, /No additional executions were recorded for \{count\} calendar days/);
  assert.doesNotMatch(zh, /你决定坚定持有|死扛|很有耐心|纪律很好/);
  assert.doesNotMatch(en, /you firmly held|dead.?cat|very patient/i);
});
