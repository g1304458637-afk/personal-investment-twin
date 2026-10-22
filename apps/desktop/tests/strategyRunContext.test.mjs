import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

import { accountIdentity, confirmedActiveAccount, LatestRunGate, ScopeRevision,
  sensitivityAvailability, strategyRunKey } from "../src/lib/strategyRunContext.ts";
import { reviewPackBelongsToAccount } from "../src/lib/reviewPackOwnership.ts";
import { adaptStrategySimulation } from "../src/data/strategySimulation.ts";
import { adaptReviewPack } from "../src/data/reviewPack.ts";

const spec = { schema_version: "user_strategy.v2", entry: { all_of: [{ factor: "rsi", window: 14 }] } };
const base = { strategyId: "user_1", spec, mode: "demo", subjectId: "demo_subject",
  accountId: "example_1", sourceFingerprint: "synthetic-source-a", universe: "synthetic" };

test("run identity binds spec contents, account, mode, source and universe", () => {
  const key = strategyRunKey(base);
  assert.equal(key, strategyRunKey({ ...base, spec: { entry: { all_of: [{ window: 14, factor: "rsi" }] }, schema_version: "user_strategy.v2" } }));
  for (const changed of [
    { spec: { ...spec, entry: { all_of: [{ factor: "rsi", window: 20 }] } } },
    { accountId: "example_2" }, { subjectId: "other_subject" },
    { mode: "real_user" }, { sourceFingerprint: "synthetic-source-b" },
    { universe: "own_account" },
  ]) assert.notEqual(key, strategyRunKey({ ...base, ...changed }));
});

test("late completion after context switch or rerun cannot become current", () => {
  const gate = new LatestRunGate();
  const original = strategyRunKey(base);
  const first = gate.begin(original);
  assert.equal(gate.accepts(original, first), true);
  const accountTwo = strategyRunKey({ ...base, accountId: "example_2" });
  gate.setContext(accountTwo);
  assert.equal(gate.accepts(original, first), false);
  const second = gate.begin(accountTwo);
  const rerun = gate.begin(accountTwo);
  assert.equal(gate.accepts(accountTwo, second), false);
  assert.equal(gate.accepts(accountTwo, rerun), true);
  gate.setContext(original);
  assert.equal(gate.accepts(original, first), false);
  gate.invalidate();
  assert.equal(gate.accepts(accountTwo, rerun), false);
});

test("global A → B → A needs a new account confirmation and cannot revive A's result", () => {
  const scope = new ScopeRevision();
  const accountA = { subject_id: "subject", account_id: "A", display_name: "Account A" };
  const accountB = { subject_id: "subject", account_id: "B", display_name: "Account B" };
  const firstRevision = scope.update(JSON.stringify(["real_user", accountIdentity(accountA)]));
  const confirmation = { key: accountIdentity(accountA), scopeRevision: firstRevision };
  assert.equal(confirmedActiveAccount(confirmation, accountA, firstRevision), accountA);
  const firstKey = strategyRunKey({ ...base, mode: "real_user", subjectId: "subject", accountId: "A",
    sourceFingerprint: `source:${firstRevision}`, universe: "own_account" });
  const secondRevision = scope.update(JSON.stringify(["real_user", accountIdentity(accountB)]));
  assert.equal(confirmedActiveAccount(confirmation, accountB, secondRevision), null);
  const thirdRevision = scope.update(JSON.stringify(["real_user", accountIdentity(accountA)]));
  assert.equal(confirmedActiveAccount(confirmation, accountA, thirdRevision), null);
  assert.notEqual(firstKey, strategyRunKey({ ...base, mode: "real_user", subjectId: "subject",
    accountId: "A", sourceFingerprint: `source:${thirdRevision}`, universe: "own_account" }));
  assert.equal(confirmedActiveAccount({ key: accountIdentity(accountA), scopeRevision: thirdRevision }, accountA, thirdRevision), accountA);
  const demoRevision = scope.update(JSON.stringify(["demo", "example"]));
  assert.equal(confirmedActiveAccount(confirmation, accountA, demoRevision), null);
});

test("sensitivity accepts synthetic built-in or workshop runs only", () => {
  assert.equal(sensitivityAvailability("built_in", null, "synthetic"), "available");
  assert.equal(sensitivityAvailability("user", "user_strategy.v2", "synthetic"), "available");
  assert.equal(sensitivityAvailability("user", "user_strategy_formula.v1", "synthetic"), "formula_unsupported");
  assert.equal(sensitivityAvailability("user", "user_strategy.v2", "own_account"), "real_history_unsupported");
  assert.equal(sensitivityAvailability("user", "user_strategy_formula.v1", "own_account"), "real_history_unsupported");
});

test("demo review pack cannot be rendered for a different selected owner", () => {
  const pack = { subjectId: "demo_subject", accountId: "review_demo" };
  assert.equal(reviewPackBelongsToAccount(pack, "demo_subject", "review_demo"), true);
  assert.equal(reviewPackBelongsToAccount(pack, "demo_subject", "example_1"), false);
  assert.equal(reviewPackBelongsToAccount(pack, "another_subject", "review_demo"), false);
});

test("shipped review pack owner matches the account displayed by the showcase", async () => {
  const pack = adaptReviewPack(JSON.parse(await readFile(new URL("../src/generated/showcase-review-pack-demo.json", import.meta.url), "utf8")));
  const showcase = JSON.parse(await readFile(new URL("../src/generated/showcase-demo.json", import.meta.url), "utf8"));
  const displayed = showcase.position_episode_demo.entries.map((entry) => entry.episode);
  assert.ok(displayed.length > 0);
  for (const episode of displayed) {
    assert.equal(reviewPackBelongsToAccount(pack,
      episode.subject_id, episode.account_id), true);
  }
});

test("benchmark policy is transported verbatim and malformed provenance fails closed", async () => {
  const raw = JSON.parse(await readFile(new URL("../src/generated/strategy-simulation-demo.json", import.meta.url), "utf8"));
  const policy = { entry: "first observed close", fees_and_slippage: "excluded (gross benchmark)" };
  assert.deepEqual(adaptStrategySimulation({ ...raw, summary: { ...raw.summary, benchmark_buy_hold_policy: policy } }).summary.benchmarkBuyHoldPolicy, policy);
  assert.throws(() => adaptStrategySimulation({ ...raw, summary: { ...raw.summary,
    benchmark_buy_hold_policy: { fees_and_slippage: 4 } } }));
});
