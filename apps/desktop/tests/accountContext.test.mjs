import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { exampleAccounts, belongsToExample } from "../src/data/accountContext.ts";
import { adaptPositionEpisodeDemo } from "../src/data/positionEpisode.ts";

const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
const entries = adaptPositionEpisodeDemo(generated.position_episode_demo).entries;
test("example accounts never combine independent owners", () => {
  const accounts = exampleAccounts(entries);
  assert.ok(accounts.length > 1);
  assert.deepEqual(accounts, exampleAccounts(entries));
  for (const entry of entries) assert.equal(accounts.filter((account) => belongsToExample(entry, account)).length, 1);
  const entry = entries[0];
  const owner = accounts.find((account) => belongsToExample(entry, account));
  assert.equal(belongsToExample(entry, { ...owner, accountId: "other" }), false);
  assert.equal(belongsToExample(entry, { ...owner, subjectId: "other" }), false);
});
test("startup does not resume a synthetic preference or fallback on runtime failure", async () => {
  const provider = await readFile(new URL("../src/data/DataModeProvider.tsx", import.meta.url), "utf8");
  assert.match(provider, /useState<DataMode>\("real_user"\)/);
  assert.doesNotMatch(provider, /localStorage|setModeState\("demo"\)/);
  const settings = await readFile(new URL("../src/pages/SettingsPage.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(settings, /Switch|uiStateExamples|peerParticipation|privacyMode/);
});
