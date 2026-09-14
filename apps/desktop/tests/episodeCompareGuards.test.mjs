import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");

test("rule replay strategy selection falls back to the default for unknown persisted ids", () => {
  // Only built-in ids are ever written to "toujing.strategy"; reading must
  // not let a stale/custom id slip into the slug lookup, the select, or the
  // label (previously an unknown id silently used T1 while printing its raw
  // id as the label).
  assert.match(page, /const RULE_REPLAY_STRATEGY_IDS: readonly string\[\] = \[\s*"toujing_t1_breakout_trend",\s*"toujing_dual_ma",\s*"toujing_rsi_mean_reversion",\s*"toujing_turtle_s2_long",\s*\]/);
  const initializer = page.slice(
    page.indexOf("const [compareStrategyId, setCompareStrategyIdState]"),
    page.indexOf("const setCompareStrategyId ="),
  );
  assert.match(initializer, /localStorage\.getItem\("toujing\.strategy"\)/);
  assert.match(initializer, /RULE_REPLAY_STRATEGY_IDS\.includes\(stored\) \? stored : "toujing_t1_breakout_trend"/);
});

test("episode comparison writes stay on built-in strategies only", async () => {
  const simulation = await readFile(new URL("../src/pages/StrategySimulationPage.tsx", import.meta.url), "utf8");
  assert.match(simulation, /if \(!id\.startsWith\("user_"\)\) localStorage\.setItem\("toujing\.strategy", id\);/);
});

test("episode change clears the real-account comparison and invalidates in-flight requests", () => {
  const reset = page.slice(
    page.indexOf("// Route parameter changes reuse this component instance"),
    page.indexOf("useEffect(() => {\n    if (!entry || !requestedDecisionId) return;"),
  );
  assert.match(reset, /\[episodeId, data\.mode, data\.exampleAccount, data\.activeAccount\]/);
  assert.match(reset, /realCompareGeneration\.current \+= 1;/);
  assert.match(reset, /setRealCompare\(null\);/);
});

test("real-account comparison drops responses that belong to another Episode", () => {
  const loader = page.slice(
    page.indexOf("const loadRealCompare = () => {"),
    page.indexOf("const currentVerdicts = useMemo"),
  );
  // The requested episode id is captured at click time and re-checked
  // against the adapted report before anything lands in state.
  assert.match(loader, /const requestedEpisodeId = episode\.episodeId;/);
  assert.match(loader, /realUserApi\.strategyComparison\(episode\.subjectId, episode\.accountId, requestedEpisodeId\)/);
  assert.match(loader, /const generation = \+\+realCompareGeneration\.current;/);
  assert.match(loader, /if \(generation !== realCompareGeneration\.current\) return;/);
  assert.match(loader, /adaptSingleComparisonReport\(result\.report\)/);
  assert.match(loader, /if \(report\.episodeId !== requestedEpisodeId\) \{\s*setRealCompare\(\{ state: "error", reason: "comparison_episode_mismatch" \}\);/);
});

test("review-card download revokes the object URL asynchronously", () => {
  const download = page.slice(
    page.indexOf("const blob = new Blob([card.svg]"),
    page.indexOf("</button>", page.indexOf("anchor.click()")),
  );
  assert.match(download, /anchor\.click\(\);/);
  assert.match(download, /window\.setTimeout\(\(\) => URL\.revokeObjectURL\(url\), 10_000\);/);
  // No synchronous revoke between click and the deferred release.
  assert.doesNotMatch(download, /click\(\);\s*URL\.revokeObjectURL/);
});
