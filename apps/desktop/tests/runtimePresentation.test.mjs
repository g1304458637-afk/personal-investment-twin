import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { adaptPositionEpisodeDemo, adaptRuntimePositionEpisodeEntry } from "../src/data/positionEpisode.ts";
import { formatCurrencyValue } from "../src/lib/format.ts";

const generated = JSON.parse(readFileSync(new URL("../src/generated/backend-demo-evidence.json", import.meta.url)));
const demo = generated.position_episode_demo;

test("currency formatting never substitutes yuan for dollars or an unknown denomination", () => {
  assert.match(formatCurrencyValue(100, "en-US", "USD"), /\$100/);
  assert.doesNotMatch(formatCurrencyValue(100, "zh-CN", "USD"), /¥|￥/);
  assert.match(formatCurrencyValue(100, "zh-CN", null), /币种未知/);
  assert.doesNotMatch(formatCurrencyValue(100, "en-US", null), /CNY|¥|￥|\$/);
});

test("adapter rejects cross-owner states and divergent Outcome copies", () => {
  for (const mutation of [
    (e) => { Object.values(e.states_by_ref)[0].account_id = "other"; },
    (e) => { Object.values(e.states_by_ref)[0].subject_id = "other"; },
    (e) => { e.outcome_story.decision_outcomes[0].after.quantity += 1; },
  ]) {
    const value = structuredClone(demo);
    mutation(value.entries[0]);
    assert.throws(() => adaptPositionEpisodeDemo(value), /ownership|state values/);
  }
});

test("Open cannot smuggle post-exit display observations; real metadata keeps USD", () => {
  const value = structuredClone(demo);
  const entry = value.entries.find((e) => e.episode.status === "open");
  entry.price_points.push({ observed_at: entry.snapshot.as_of, price: 10, segment: "post_exit" });
  assert.throws(() => adaptPositionEpisodeDemo(value), /post-exit/);
  const real = structuredClone(demo.entries[0]);
  real.instrument = { ...real.instrument, is_synthetic: false, data_tier: "authorized_beta", currency: "USD" };
  real.episode.data_tier = "authorized_beta";
  assert.equal(adaptRuntimePositionEpisodeEntry(real).instrument.currency, "USD");
});

test("path points and execution references cannot diverge from authoritative state", () => {
  for (const mutate of [
    (e) => { e.path_analysis.position_path.points[0].quantity += 1; },
    (e) => { e.path_analysis.position_path.points[0].state_id = "missing"; },
    (e) => { e.decisions[0].execution_id = "missing"; },
  ]) {
    const value = structuredClone(demo); mutate(value.entries[0]);
    assert.throws(() => adaptPositionEpisodeDemo(value), /state|reference|Episode/);
  }
});

test("actual serialized long-horizon payload is measured in bytes, including arrays", () => {
  const entry = demo.entries.find((e) => e.instrument.instrument_id === "SYN_LONG_OPEN");
  const bytes = Buffer.byteLength(JSON.stringify(entry));
  assert.ok(entry.price_points.length > 1000);
  assert.ok(bytes > 100000 && bytes < 2000000, `actual Episode payload ${bytes} bytes`);
  const roundtrip = JSON.parse(JSON.stringify(entry));
  assert.deepEqual(roundtrip, entry);
});
