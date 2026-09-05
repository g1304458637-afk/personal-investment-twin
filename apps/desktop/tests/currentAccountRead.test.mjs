import assert from "node:assert/strict";
import test from "node:test";
import { readCurrentAccounts } from "../src/data/currentAccountRead.ts";

for (const rejected of [false, true]) test(`outdated account ${rejected ? "error" : "success"} cannot supersede the latest read`, async () => {
  let finish, fail, current = 1;
  const pending = new Promise((resolve, reject) => { finish = resolve; fail = reject; });
  const old = readCurrentAccounts(() => pending, () => current === 1);
  current = 2;
  const latest = { accounts: [{ subject_id: "new-subject", account_id: "new-account" }] };
  assert.equal(await readCurrentAccounts(async () => latest, () => current === 2), latest);
  if (rejected) fail(new Error("old account failed")); else finish({ accounts: [] });
  assert.equal(await old, null);
});

test("current account failure is not silently swallowed", async () => {
  await assert.rejects(readCurrentAccounts(async () => { throw new Error("runtime unavailable"); }, () => true), /runtime unavailable/);
});
