import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const { parseClampedNumberInput } = await import("../src/lib/numberInput.ts");

const source = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("formula specs render through describeUserStrategySpec, never through spec.entry.all_of", async () => {
  const page = await source("../src/pages/StrategySimulationPage.tsx");
  // The old code unconditionally dereferenced spec.entry.all_of / spec.exit.any_of
  // and crashed (white screen) on user_strategy_formula.v1 specs.
  assert.doesNotMatch(page, /spec\.entry as \{|spec\.exit as \{/);
  assert.match(page, /describeUserStrategySpec\(selectedUserStrategy\.spec\)/);
  assert.match(page, /display\.kind === "formula"/);
});

test("a top-level ErrorBoundary with a reload action wraps the whole app", async () => {
  const boundary = await source("../src/components/common/ErrorBoundary.tsx");
  assert.match(boundary, /getDerivedStateFromError/);
  assert.match(boundary, /role="alert"/);
  assert.match(boundary, /window\.location\.reload\(\)/);
  const app = await source("../src/App.tsx");
  const provider = app.indexOf("<LocaleProvider>");
  const mounted = app.indexOf("<AppErrorBoundary>");
  const children = app.indexOf("</AppErrorBoundary>");
  const closingProvider = app.indexOf("</LocaleProvider>");
  assert.ok(provider >= 0 && mounted > provider && children < closingProvider,
    "the boundary must sit inside LocaleProvider so its fallback can translate");
});

test("failed custom runs land in an error state that shows the run button again", async () => {
  const simulation = await source("../src/pages/StrategySimulationPage.tsx");
  const strategies = await source("../src/pages/MyStrategiesPage.tsx");
  const runBodies = [
    simulation.slice(simulation.indexOf("const runUserStrategy"), simulation.indexOf("const deleteUserStrategy")),
    strategies.slice(strategies.indexOf("const run = ("), strategies.indexOf("const equityOption")),
  ];
  for (const [body, name] of runBodies.map((body, i) => [body, i === 0 ? "StrategySimulationPage" : "MyStrategiesPage"])) {
    assert.ok(body.length > 0, name);
    assert.match(body, /"error"/, `${name}: failure paths set the error run state`);
    // No failure path may put the run back into "loading".
    assert.doesNotMatch(body.replace(/setUserRunError|setRunErrors/g, ""), /"loading"\}\)\);/, name);
    assert.match(body, /"loading"/, name);
  }
  // Both pages type the run state with the "error" member.
  assert.match(simulation, /"loading" \| "ready" \| "error"/);
  assert.match(strategies, /"loading" \| "ready" \| "error"/);
});

test("built-in chunk loads catch failures and stale data is gated by a strategy-id match", async () => {
  const page = await source("../src/pages/StrategySimulationPage.tsx");
  assert.match(page, /entry\.load\(\)\.then\(\(module\) => \{[\s\S]*?\}\)\.catch\(/);
  assert.match(page, /setStrategyLoadError/);
  assert.match(page, /simulationReady = isUserStrategy\s*\?\s*!!userArtifacts\[strategyId\]\s*:\s*simulation\.strategy\.strategyId === strategyId/);
  assert.match(page, /!simulationReady && !isUserStrategy \? strategyLoadError/);
});

test("toujing.strategy only persists built-in ids and episode replay rejects unknown ids", async () => {
  const simulation = await source("../src/pages/StrategySimulationPage.tsx");
  assert.match(simulation, /if \(!id\.startsWith\("user_"\)\) localStorage\.setItem\("toujing\.strategy", id\);/);
  const episode = await source("../src/pages/PositionEpisodePage.tsx");
  assert.match(episode, /RULE_REPLAY_STRATEGY_IDS\.includes\(stored\) \? stored : "toujing_t1_breakout_trend"/);
  assert.match(episode, /const RULE_REPLAY_STRATEGY_IDS/);
});

test("sensitivity runs carry a generation guard against late responses", async () => {
  const page = await source("../src/pages/StrategySimulationPage.tsx");
  assert.match(page, /const sensitivityGeneration = useRef\(0\)/);
  assert.match(page, /const generation = \+\+sensitivityGeneration\.current;/);
  assert.match(page, /if \(generation !== sensitivityGeneration\.current\) return;/);
  assert.match(page, /\[strategyId, sensitivityParam\]\)/);
});

test("chart axis formats dates in UTC and the stats card reuses the money currency", async () => {
  const page = await source("../src/pages/StrategySimulationPage.tsx");
  assert.match(page, /Intl\.DateTimeFormat\(locale, \{ year: "2-digit", month: "short", timeZone: "UTC" \}\)/);
  assert.match(page, /detail=\{`\$\{summary\.tradingDays\} · \$\{currency\}`\}/);
  assert.doesNotMatch(page, /· CNY`/);
  const annualized = page.slice(page.indexOf("const annualizedTone"), page.indexOf("</StatCard>", page.indexOf("Annualized")));
  assert.match(annualized, /annualizedReturn === null \? undefined/);
});

test("workshop numeric inputs keep a string draft and clamp on commit", async () => {
  for (const path of ["../src/components/strategy/StrategyWorkshop.tsx", "../src/pages/MyStrategiesPage.tsx"]) {
    const file = await source(path);
    assert.doesNotMatch(file, /Number\(event\.target\.value\) \|\|/, path);
    assert.match(file, /WorkshopNumberInput/, path);
  }
  // Parsing: cleared or non-numeric drafts fall back; values clamp into the
  // backend's allowed ranges (fraction 5..100, stop 1..50, positions 1..8).
  assert.equal(parseClampedNumberInput("", 25, 5, 100), 25);
  assert.equal(parseClampedNumberInput("-", 25, 5, 100), 25);
  assert.equal(parseClampedNumberInput("abc", 25, 5, 100), 25);
  assert.equal(parseClampedNumberInput("5000", 25, 5, 100), 100);
  assert.equal(parseClampedNumberInput("0", 25, 5, 100), 5);
  assert.equal(parseClampedNumberInput("40", 25, 5, 100), 40);
  assert.equal(parseClampedNumberInput(" 12.5 ", 10, 1, 50), 12.5);
  assert.equal(parseClampedNumberInput("2", 4, 1, 8), 2);
});

test("runtime transport treats null/false/0 results as payloads, not errors", async () => {
  const service = await source("../src/data/runtimeService.ts");
  assert.match(service, /if \(!response\.ok \|\| response\.error\) throw/);
  assert.doesNotMatch(service, /!response\.result/);
});

const MISSING_I18N_KEYS = [
  "Annualized return", "Trading days", "Sharpe ratio", "Good risk-adjusted return",
  "Low risk-adjusted return", "Buy and hold", "Rules", "Results", "Charts", "Comparison",
  "Entry", "Loading…", "Cancel", "Strategy name", "Click again to confirm",
  "All functions are strictly backward-looking; formulas cannot access files, network, or your account data.",
  "Showcase comparison · Synthetic", "先填写并检查，再看前后变化",
];

test("every listed t() key exists in both dictionaries", async () => {
  const en = await source("../src/locales/en-US.ts");
  const zh = await source("../src/locales/zh-CN.ts");
  for (const key of MISSING_I18N_KEYS) {
    const needle = JSON.stringify(key) + ":";
    assert.ok(en.includes(needle), `en-US missing key: ${key}`);
    assert.ok(zh.includes(needle), `zh-CN missing key: ${key}`);
  }
  // zh must keep covering the en dictionary (satisfies constraint source line).
  assert.match(zh, /satisfies Record<keyof typeof enUS, string>/);
});
