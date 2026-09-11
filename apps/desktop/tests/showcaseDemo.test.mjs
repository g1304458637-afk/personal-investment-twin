import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

import { adaptComparisonResearch } from "../src/data/comparisonResearch.ts";
import { adaptPositionEpisodeDemo } from "../src/data/positionEpisode.ts";
import { adaptPretradeImpact } from "../src/data/pretradeImpact.ts";
import { adaptSameStock } from "../src/data/sameStock.ts";
import { adaptStandardChartDemo } from "../src/data/standardChart.ts";

const showcase = JSON.parse(await readFile(new URL("../src/generated/showcase-demo.json", import.meta.url), "utf8"));
const MAIN = "SYN_STUDY_SHOWCASE";
const REFERENCE = "SYN_STUDY_SHOWCASE_REFERENCE";

test("the shipped showcase is one synthetic account with five chartable investment episodes", () => {
  assert.equal(showcase.data_tier, "synthetic");
  assert.equal(showcase.showcase.subject_id, MAIN);
  assert.equal(showcase.showcase.account_id, MAIN);
  assert.equal(showcase.showcase.source_version, "toujing_showcase_v1");
  assert.deepEqual(showcase.showcase.display_name, { zh: "我的年度投资 · 示例", en: "My investment year · Example" });

  const episodes = adaptPositionEpisodeDemo(showcase.position_episode_demo);
  assert.equal(episodes.entries.length, 5);
  assert.equal(episodes.entries.filter((entry) => entry.episode.status === "open").length, 3);
  assert.equal(episodes.entries.filter((entry) => entry.episode.status === "closed").length, 2);
  assert.ok(episodes.entries.every((entry) => entry.episode.subjectId === MAIN && entry.episode.accountId === MAIN));
  const names = showcase.showcase.names;
  assert.ok(episodes.entries.every((entry) => names[entry.instrument.instrumentId]));
  for (const name of Object.values(names)) {
    assert.equal(typeof name.zh, "string");
    assert.equal(typeof name.en, "string");
    assert.ok(name.zh.length > 0 && name.en.length > 0);
  }

  assert.equal(showcase.charts.length, episodes.entries.length);
  const chartEpisodes = showcase.charts.map(adaptStandardChartDemo);
  assert.deepEqual(new Set(chartEpisodes.map((chart) => chart.entry.episode.episodeId)), new Set(episodes.entries.map((entry) => entry.episode.episodeId)));
  for (const chart of chartEpisodes) {
    assert.equal(chart.market.bars[0].date, "2025-01-02");
    assert.equal(chart.market.bars.at(-1)?.date, "2025-12-31");
    assert.ok(chart.market.bars.length >= 250);
  }
});

test("showcase presentation uses the payload's bilingual account and instrument names", async () => {
  const adapter = await readFile(new URL("../src/data/showcaseDemo.ts", import.meta.url), "utf8");
  const investments = await readFile(new URL("../src/pages/InvestmentsPage.tsx", import.meta.url), "utf8");
  const episode = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(adapter, /locale === "zh-CN" \? name\.zh : name\.en/);
  assert.match(investments, /showcaseInstrumentName\(episode\.instrumentId, locale/);
  assert.match(episode, /showcaseInstrumentName\(entry\.instrument\.instrumentId, locale/);
  const pretrade = await readFile(new URL("../src/pages/DecisionCheckPage.tsx", import.meta.url), "utf8");
  assert.match(pretrade, /showcaseInstrumentName\(instrumentId, locale, instrumentId\)/);
  assert.match(pretrade, /symbol: instrumentLabel\(pretradeDemo\.symbol\)/);
  const chart = await readFile(new URL("../src/components/charts/InvestmentChartWorkspace.tsx", import.meta.url), "utf8");
  assert.match(chart, /market\.priceBasis === "synthetic_unadjusted"/);
  assert.match(chart, /模拟未复权价格/);
});

test("comparison, same-stock review, and pretrade all remain rooted in the showcase source", () => {
  const study = adaptComparisonResearch(showcase.comparison_research);
  assert.equal(study.defaultSubject, MAIN);
  assert.deepEqual(study.accounts.map((account) => account.id), [MAIN, REFERENCE]);
  assert.equal(study.names[MAIN].zh, "我的年度投资 · 示例");
  assert.equal(study.names[REFERENCE].zh, "稳健配置参考 · 模拟");
  for (const account of study.accounts) {
    assert.equal(account.periods.earlier.startDate, "2025-01-02");
    assert.equal(account.periods.earlier.endDate, "2025-07-02");
    assert.equal(account.periods.recent.startDate, "2025-07-02");
    assert.equal(account.periods.recent.endDate, "2025-12-31");
  }

  const sameStock = adaptSameStock(showcase.same_stock_compare_demo);
  assert.equal(sameStock.a.subjectId, MAIN);
  assert.equal(sameStock.b.subjectId, REFERENCE);
  assert.equal(showcase.same_stock_compare_demo.a.episode.account_id, MAIN);
  assert.equal(showcase.same_stock_compare_demo.b.episode.account_id, REFERENCE);

  const pretrade = adaptPretradeImpact(showcase.pretrade_demo);
  assert.equal(pretrade.subjectId, MAIN);
  assert.equal(pretrade.status, "complete");
  assert.ok(pretrade.before && pretrade.after && pretrade.delta && pretrade.selfContext);
  assert.equal(pretrade.peerContext, null);
});
