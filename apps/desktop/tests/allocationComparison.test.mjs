import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { allocationRows, allocationShare, allocationColour } from "../src/data/allocationComparison.ts";
import { adaptPretradeImpact } from "../src/data/pretradeImpact.ts";
import { pretradeCopy } from "../src/locales/pretrade.ts";

const payload = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8")).pretrade_demo;

test("allocation adapter preserves replay amounts and both denominators", () => {
  const view = adaptPretradeImpact(payload);
  for (const side of ["before", "after"]) {
    assert.equal(view[side].valuationDate, payload[side].valuation_observation_date);
    for (const source of payload[side].allocations) {
      const row = view[side].allocations.find((row) => row.symbol === source.symbol);
      assert.equal(row.value, source.value);
      assert.equal(row.accountWeight, source.account_weight);
      assert.equal(row.securityWeight, source.security_weight);
    }
  }
  const target = view.before.allocations.find((row) => row.symbol === payload.proposed_trade.symbol);
  assert.notEqual(target.accountWeight, target.securityWeight);
});

test("account / security toggle excludes cash only for holdings basis", () => {
  const { before, after } = adaptPretradeImpact(payload);
  const account = allocationRows(before.allocations, after.allocations, "account");
  const securities = allocationRows(before.allocations, after.allocations, "securities");
  assert.equal(account.length, securities.length + 1);
  assert.equal(new Set(account.map((row) => row.colour)).size, account.length);
  assert.ok(!securities.some((row) => row.identity.kind === "cash"));
  for (const row of securities) assert.equal(allocationShare(row.before, "securities"), row.before.securityWeight);
  assert.deepEqual(allocationRows([...before.allocations].reverse(), after.allocations, "account"), account);
});

test("fully sold or newly acquired holdings retain a shared identity and zero absent share", () => {
  const { before } = adaptPretradeImpact(payload);
  const sample = before.allocations.find((row) => row.kind === "security");
  const sold = allocationRows([sample], [], "account")[0];
  const bought = allocationRows([], [sample], "account")[0];
  assert.equal(sold.colour, bought.colour);
  assert.equal(sold.colour, allocationColour(sample.id));
  assert.equal(allocationShare(sold.after, "account"), 0);
  assert.equal(allocationShare(bought.before, "securities"), 0);
  assert.equal(sold.after, null);
});

test("older runtime does not produce an invented breakdown; malformed breakdown fails closed", () => {
  const old = structuredClone(payload); delete old.before.allocations;
  assert.equal(adaptPretradeImpact(old).before.allocations, null);
  const bad = structuredClone(payload); bad.before.allocations.pop();
  assert.throws(() => adaptPretradeImpact(bad), /Incomplete/);
  const nan = structuredClone(payload); nan.before.allocations[0].value = NaN;
  assert.throws(() => adaptPretradeImpact(nan), /finite/);
  const rejected = structuredClone(payload); rejected.after = null; rejected.simulation_status = "rejected";
  assert.equal(adaptPretradeImpact(rejected).after, null);
});

test("chart uses ECharts, click and keyboard selection, and honest look-through copy in both languages", async () => {
  const code = await readFile(new URL("../src/components/charts/PretradeAllocation.tsx", import.meta.url), "utf8");
  assert.match(code, /type: "pie"/);
  assert.match(code, /onChartClick/);
  assert.match(code, /aria-pressed/);
  assert.match(code, /prefers-reduced-motion/);
  assert.match(code, /renderMode: "richText"/);
  assert.match(code, /showcaseInstrumentName/);
  assert.match(pretradeCopy["zh-CN"].scopeDetail, /基金底层成分、行业分类尚未接入/);
  assert.match(pretradeCopy["en-US"].scopeDetail, /not connected/);
  assert.match(pretradeCopy["zh-CN"].hhiHelp, /不包含现金/);
});
