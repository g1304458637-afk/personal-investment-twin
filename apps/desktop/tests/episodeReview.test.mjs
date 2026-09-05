import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { adaptPositionEpisodeDemo } from "../src/data/positionEpisode.ts";
const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
test("review copies the backend's selection, order and source-linked story", () => {
  const view = adaptPositionEpisodeDemo(generated.position_episode_demo);
  for (const entry of view.entries) {
    const raw = generated.position_episode_demo.entries.find((item) => item.episode.episode_id === entry.episode.episodeId).review_presentation;
    assert.deepEqual(entry.reviewPresentation.facts.map((fact) => fact.itemId), raw.facts.map((fact) => fact.item_id));
    assert.ok(entry.reviewPresentation.facts.length <= 3);
    for (const step of entry.reviewPresentation.storySteps) assert.equal(step.decisionCount, entry.pathAnalysis.phases.find((phase) => phase.phaseId === step.phaseId).decisionEventIds.length);
  }
});
test("malformed/foreign/duplicated review sources fail closed", () => {
  for (const mutate of [r => r.episode_id = "other", r => r.story_steps[0].decision_count = 999, r => r.facts.push(r.facts[0])]) {
    const value = structuredClone(generated.position_episode_demo);
    mutate(value.entries[0].review_presentation);
    assert.throws(() => adaptPositionEpisodeDemo(value), /review/);
  }
});
test("first layer is chart-first and counterfactuals need explicit disclosure", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  const firstLayer = page.slice(page.indexOf("return <CurrencyProvider"));
  assert.ok(firstLayer.indexOf("data-price-path") < firstLayer.indexOf("data-review-facts"));
  assert.match(page, /useState<string \| null>\(null\)/);
  assert.match(firstLayer, /<details.*Historical comparison under fixed assumptions/s);
  assert.doesNotMatch(firstLayer.slice(0, firstLayer.indexOf("data-price-path")), /Canonical|Evidence IDs|Path module|scenario/);
  assert.match(page, /not the final result of the investment/);
  assert.match(page, /valuationObservationDate/);
  assert.doesNotMatch(page, /importanceScore|Math\.(abs|pow)|calculatePnl|calculateReturn/);
});
