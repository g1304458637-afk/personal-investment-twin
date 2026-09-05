import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { archiveRows, adaptDemoInvestmentsCatalog } from "../src/data/investments.ts";
import { adaptPositionEpisodeDemo } from "../src/data/positionEpisode.ts";
const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
const episodes = adaptPositionEpisodeDemo(generated.position_episode_demo);
const catalog = adaptDemoInvestmentsCatalog(episodes);
const rows = [...catalog.openEpisodes, ...catalog.closedEpisodes];
test("archive copies actual results, never local counterfactuals", () => {
  for (const row of rows) {
    const actual = episodes.entries.find((entry) => entry.episode.episodeId === row.episodeId).outcomeStory.episodeOutcome;
    assert.equal(row.outcome.pnl, actual.actualResult.pnl);
    assert.equal(row.outcome.return_value, actual.actualResult.returnValue);
    assert.equal(row.outcome.outcome_id, actual.outcomeId);
    assert.equal(row.outcome.result_kind, row.status === "open" ? "marked" : "realized");
  }
});
test("archive filtering is chronological and stable, not profit ranking", () => {
  const sorted = archiveRows(rows, "all", "");
  assert.deepEqual(sorted, archiveRows([...rows].reverse(), "all", ""));
  for (let i = 1; i < sorted.length; i++) assert.ok(Date.parse(sorted[i - 1].openedAt) >= Date.parse(sorted[i].openedAt));
  assert.ok(archiveRows(rows, "open", "").every((row) => row.status === "open"));
  assert.equal(archiveRows(rows, "all", "SYN_PRODUCT").length, 1);
  assert.deepEqual(archiveRows(rows, "all", "no-such-security"), []);
  assert.equal(new Set(sorted.map((row) => row.episodeId)).size, rows.length);
});
