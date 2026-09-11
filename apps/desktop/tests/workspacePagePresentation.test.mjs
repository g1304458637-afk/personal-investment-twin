import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("investment workspace presents adapter-owned summaries and outcome values", async () => {
  const page = await source("../src/pages/InvestmentsPage.tsx");
  assert.match(page, /view\.summary\.openEpisodeCount/);
  assert.match(page, /view\.summary\.currentPositionCount/);
  assert.match(page, /view\.summary\.closedEpisodeCount/);
  assert.match(page, /const pnl = outcome\.pnl/);
  assert.match(page, /outcome\.result_kind === "marked"/);
  assert.doesNotMatch(page, /\.reduce\s*\(/);
  assert.doesNotMatch(page, /calculate(?:Pnl|Return|Portfolio)|Math\./);
});

test("episode workspace keeps marked outcomes dated and leaves charts wired to recorded state", async () => {
  const page = await source("../src/pages/PositionEpisodePage.tsx");
  const workspace = await source("../src/components/charts/EpisodeChartWorkspace.tsx");
  assert.match(page, /result\.resultKind === "marked"/);
  assert.match(page, /result\.valuationAt/);
  assert.match(page, /This is a current mark, not a realized exit/);
  assert.match(page, /<EpisodeChartWorkspace/);
  assert.match(workspace, /<PositionEpisodeTimeline/);
  assert.match(workspace, /<PositionQuantityTimeline/);
  assert.match(page, /onSelectDecision=\{lensMode \? selectLensDecision : setSelectedDecisionId\}/);
  assert.doesNotMatch(page, /calculate(?:Pnl|Return|Portfolio)|Math\./);
});

test("episode decision deep links only open an execution belonging to the loaded episode", async () => {
  const page = await source("../src/pages/PositionEpisodePage.tsx");
  assert.match(page, /const requestedDecisionId = search\.get\("decision"\)/);
  assert.match(page, /entry\.decisions\.some\(\(decision\) => decision\.decisionId === requestedDecisionId\)/);
  assert.match(page, /if \(!entry \|\| !requestedDecisionId\) return/);
  assert.doesNotMatch(page, /setSelectedDecisionId\(search\.get\("decision"\)\)/);
});
