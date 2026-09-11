import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { searchServiceRequest, quotesServiceRequest, searchServiceCopy, quotesServiceCopy } from "../src/data/searchService.ts";

test("browser rejects search and quotes without storing a key", async () => {
  await assert.rejects(searchServiceRequest("save", "test-only-value"), /desktop_runtime_required/);
  await assert.rejects(quotesServiceRequest(), /desktop_runtime_required/);
});

test("only save and setEnabled send arguments to the exact fixed commands", async () => {
  const calls = [];
  const call = async (command, args) => { calls.push([command, args]); return { configured: true, enabled: true }; };
  for (const action of ["save", "status", "delete", "test", "setEnabled"]) {
    await searchServiceRequest(action, action === "save" ? "test-only-value" : action === "setEnabled" ? false : undefined, call);
  }
  await quotesServiceRequest(call);
  assert.deepEqual(calls, [
    ["search_service_save", { apiKey: "test-only-value" }],
    ["search_service_status", undefined],
    ["search_service_delete", undefined],
    ["search_service_test", undefined],
    ["search_service_set_enabled", { enabled: false }],
    ["quotes_service_status", undefined],
  ]);
});

test("native unknown error is redacted, known code remains usable", async () => {
  await assert.rejects(searchServiceRequest("test", undefined, async () => { throw "private-test-value"; }), /^Error: search_service_unavailable$/);
  await assert.rejects(searchServiceRequest("test", undefined, async () => { throw "search_not_configured"; }), /^Error: search_not_configured$/);
});

test("search settings keep a separate password field and never echo DeepSeek commands", () => {
  const source = readFileSync(new URL("../src/components/review/SearchServiceSettings.tsx", import.meta.url), "utf8");
  const model = readFileSync(new URL("../src/components/review/ModelServiceSettings.tsx", import.meta.url), "utf8");
  assert.match(source, /id="bocha-key"/);
  assert.match(source, /type="password"/);
  assert.match(source, /if \(locked.current \|\| !desktop\) return/);
  assert.ok(source.indexOf("setKey(\"\");", source.indexOf("async function act")) < source.indexOf("await searchServiceRequest", source.indexOf("async function act")));
  assert.doesNotMatch(source, /localStorage|sessionStorage|console\./);
  assert.match(model, /SearchServiceSettings/);
  assert.match(model, /QuotesServiceStatus/);
  assert.doesNotMatch(source, /model_service_|deepseek-key/);
});

test("copy discloses independent Keychain item, fixed test term and account-analysis isolation", () => {
  for (const c of Object.values(searchServiceCopy)) {
    assert.ok(c.testNotice && c.browser && c.deleted && c.errors.search_not_configured);
    assert.match(c.description, /DeepSeek/);
  }
  assert.match(searchServiceCopy["zh-CN"].testNotice, /上海证券交易所/);
  assert.match(searchServiceCopy["zh-CN"].disabled, /账户分析不受影响/);
  assert.match(quotesServiceCopy["zh-CN"].available, /Evidence/);
});
