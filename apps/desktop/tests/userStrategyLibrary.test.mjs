import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const { describeUserStrategySpec, readUserStrategies, USER_STRATEGIES_KEY }
  = await import("../src/lib/userStrategyLibrary.ts");
const { conditionStatement } = await import("../src/lib/strategyFactors.ts");

function storageWith(value) {
  return { getItem: (key) => (key === USER_STRATEGIES_KEY ? value : null) };
}

function validEntry(overrides = {}) {
  return {
    id: "user_1_abc",
    name: "突破策略",
    savedAt: "2026-09-15",
    spec: {
      schema_version: "user_strategy.v2",
      name: "突破策略",
      entry: { all_of: [{ factor: "breakout_high", params: { window: 20 }, op: "true" }], any_of: [] },
      exit: { any_of: [], stop_loss_pct: 0.08, atr_trailing_mult: null },
      sizing: { mode: "equal_weight", fraction: 0.25 },
      constraints: { max_positions: 4 },
    },
    ...overrides,
  };
}

test("readUserStrategies keeps well-formed entries and drops malformed ones", () => {
  const good = validEntry();
  const payload = JSON.stringify([
    good,
    null,                                          // not an object
    [],                                            // array, not object
    { ...good, id: 42 },                           // id not a string
    { ...good, id: "" },                           // empty id
    { ...good, name: "  " },                       // blank name
    { ...good, savedAt: "" },                      // empty savedAt
    { ...good, savedAt: null },                    // savedAt not a string
    { ...good, spec: "user_strategy.v2" },         // spec not an object
    { ...good, spec: { name: "no schema" } },      // spec without schema_version
    "garbage",                                     // plain string
  ]);
  const loaded = readUserStrategies(storageWith(payload));
  assert.deepEqual(loaded.map((entry) => entry.id), [good.id]);
  assert.equal(loaded[0].name, good.name);
  assert.equal(loaded[0].spec.schema_version, "user_strategy.v2");
});

test("readUserStrategies fails closed on corrupt storage, bad JSON, and missing storage", () => {
  assert.deepEqual(readUserStrategies(storageWith("not json {")), []);
  assert.deepEqual(readUserStrategies(storageWith('{"id":"oops"}')), []);
  assert.deepEqual(readUserStrategies(storageWith("")), []);
  assert.deepEqual(readUserStrategies(storageWith(null)), []);
  const throwing = { getItem: () => { throw new Error("denied"); } };
  assert.deepEqual(readUserStrategies(throwing), []);
  assert.deepEqual(readUserStrategies(undefined), []);
});

test("formula-mode specs render formula text instead of crashing on missing entry/exit", async () => {
  // Exactly the shape MyStrategiesPage saves in formula mode: no
  // entry.all_of / exit.any_of at all.
  const page = await readFile(new URL("../src/pages/MyStrategiesPage.tsx", import.meta.url), "utf8");
  assert.match(page, /schema_version: "user_strategy_formula\.v1"/);
  const spec = {
    schema_version: "user_strategy_formula.v1",
    name: "公式策略",
    entry_formula: "close > highest(20) and close > sma(20)",
    exit_formula: "close < lowest(10)",
    stop_loss_pct: null,
    sizing: { mode: "equal_weight", fraction: 0.25 },
    constraints: { max_positions: 4 },
  };
  const display = describeUserStrategySpec(spec);
  assert.equal(display.kind, "formula");
  assert.deepEqual(display.entry, ["close > highest(20) and close > sma(20)"]);
  assert.deepEqual(display.exit, ["close < lowest(10)"]);
});

test("workshop v2 specs render condition statements for entry and exit groups", () => {
  const spec = validEntry().spec;
  const display = describeUserStrategySpec(spec);
  assert.equal(display.kind, "conditions");
  assert.deepEqual(display.entry, ["创 N 日新高（回看窗口 20）成立"]);
  assert.deepEqual(display.exit, []);
});

test("describeUserStrategySpec skips malformed groups and unknown factors without throwing", () => {
  assert.deepEqual(describeUserStrategySpec(null), { kind: "conditions", entry: [], exit: [] });
  assert.deepEqual(describeUserStrategySpec("x"), { kind: "conditions", entry: [], exit: [] });
  assert.deepEqual(describeUserStrategySpec({}), { kind: "conditions", entry: [], exit: [] });
  assert.deepEqual(describeUserStrategySpec({ schema_version: "user_strategy.v2", entry: "bad", exit: null }),
    { kind: "conditions", entry: [], exit: [] });
  const hostile = {
    schema_version: "user_strategy.v2",
    entry: { all_of: [null, "x", { factor: "no_such_factor", op: "true" }, { factor: "rsi", op: "lt", threshold: 30, params: { window: 14 } }], any_of: [{ factor: "roc", op: "gt", threshold: 0.1, params: { window: 20 } }] },
    exit: { any_of: [{ factor: "breakdown_low", op: "true", params: { window: 10 } }] },
  };
  const display = describeUserStrategySpec(hostile);
  assert.deepEqual(display.entry, [
    conditionStatement({ factor: "rsi", op: "lt", threshold: 30, params: { window: 14 } }),
    conditionStatement({ factor: "roc", op: "gt", threshold: 0.1, params: { window: 20 } }),
  ]);
  assert.deepEqual(display.exit, [conditionStatement({ factor: "breakdown_low", op: "true", params: { window: 10 } })]);
});

test("both strategy pages read saved strategies through the shared shape-checked reader", async () => {
  for (const path of ["../src/pages/StrategySimulationPage.tsx", "../src/pages/MyStrategiesPage.tsx"]) {
    const source = await readFile(new URL(path, import.meta.url), "utf8");
    assert.match(source, /readUserStrategies/);
    assert.doesNotMatch(source, /JSON\.parse\(localStorage\.getItem\("toujing\.userStrategies"\)/);
  }
  const library = await readFile(new URL("../src/lib/userStrategyLibrary.ts", import.meta.url), "utf8");
  assert.match(library, /USER_STRATEGIES_KEY = "toujing\.userStrategies"/);
});
