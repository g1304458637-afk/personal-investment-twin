import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { capabilityCatalog, capabilityStatus, capabilityScopeTarget } from "../src/workspace/agentCapabilityCatalog.ts";

const ready = { desktop: true, wholeAccount: true, model: "configured", quotes: "configured", search: "configured" };
test("every capability describes a benefit, coverage and an editable example in both languages", () => {
  assert.equal(capabilityCatalog.length, 6);
  for (const item of capabilityCatalog) for (const lang of ["zh", "en"]) {
    for (const field of ["title", "benefit", "includes", "prompt"]) assert.ok(item[field][lang].length > 3);
    assert.ok(item.prompt[lang].length < 2000);
  }
});
test("status distinguishes preview, limited scope, configuration and data availability", () => {
  assert.match(capabilityStatus("research", {...ready, desktop: false}, true), /网页预览/);
  assert.match(capabilityStatus("model", {...ready, wholeAccount: false}, true), /当前轮次可提问 · 全账户计算请切换范围/);
  assert.match(capabilityStatus("research", {...ready, model: "checking"}, true), /检查模型/);
  assert.match(capabilityStatus("research", {...ready, model: "unavailable"}, true), /配置模型/);
  assert.match(capabilityStatus("research", {...ready, search: "unavailable"}, true), /新闻搜索待开启/);
  assert.match(capabilityStatus("research", {...ready, quotes: "unavailable"}, true), /行情库未就绪/);
  assert.match(capabilityStatus("research", ready, true), /搜索已开启/);
  assert.doesNotMatch(capabilityStatus("research", ready, true), /连接成功|实时可用/);
  assert.match(capabilityStatus("guide", {...ready, model: "unavailable"}, true), /页面指引可用/);
});
test("overview is persistent; examples never submit or grant consent; dedicated pages stay distinct", async () => {
  const page = await readFile(new URL("../src/workspace/AgentWorkspace.tsx", import.meta.url), "utf8");
  const overview = await readFile(new URL("../src/workspace/AgentCapabilityOverview.tsx", import.meta.url), "utf8");
  assert.ok(page.indexOf("<AgentCapabilityOverview") < page.indexOf('<section className="agent-chat__conversation"'));
  assert.match(overview, /onQuestion\(item.prompt\[lang\]\)/);
  assert.doesNotMatch(overview, /runChatTurn|setConsent|submit\(/);
  assert.match(overview, /disabled=\{busy\}/);
  assert.match(overview, /选择账户后检查服务状态/);
  assert.match(overview, /to="\/data"/);
  assert.match(overview, /to="\/pretrade"/);
  assert.match(overview, /to="\/analysis"/);
  assert.match(overview, /capabilityScopeTarget/);
});
test("scenario and comparison examples respect their actual supported scope", () => {
  assert.equal(capabilityScopeTarget("scenario", {...ready, synthetic: false}), "/data");
  assert.match(capabilityStatus("scenario", {...ready, synthetic: false}, true), /仅支持示例/);
  assert.equal(capabilityScopeTarget("scenario", {...ready, synthetic: true, wholeAccount: false}), "/ask");
  assert.equal(capabilityScopeTarget("account", {...ready, wholeAccount: false}), "/ask");
  assert.equal(capabilityScopeTarget("scenario", {...ready, synthetic: true}), null);
  assert.equal(capabilityScopeTarget("research", {...ready, synthetic: false, wholeAccount: false}), null);
});
test("quote readiness reuses completed account context instead of a competing cold-start request", async () => {
  const page = await readFile(new URL("../src/workspace/AgentWorkspace.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /quotesServiceRequest/);
  assert.match(page, /value\.research\?\.quotes\?\.available === true/);
  assert.match(page, /setQuotesState\("checking"\)/);
});
