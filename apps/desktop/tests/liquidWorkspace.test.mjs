import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { analysisLinks, liquidNavigation, liquidSection } from "../src/workspace/liquidNavigation.ts";
const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("liquid primary navigation consolidates existing tasks without orphaning deep views", () => {
  assert.deepEqual(liquidNavigation.filter(x => x.group === "work").map(x => x.path), ["/investments", "/strategy-simulation", "/my-strategies", "/analysis", "/pretrade", "/ask"]);
  for (const path of ["/analysis", "/review", "/review/decisions", "/history", "/comparison/history", "/investments/compare-example", "/advanced/evidence"]) assert.equal(liquidSection(path), "/analysis");
  assert.equal(liquidSection("/ask"), "/ask");
  assert.equal(liquidSection("/investments/episodes/owned"), "/investments");
  assert.equal(liquidSection("/journal"), "/pretrade");
  assert.equal(new Set(analysisLinks.map(x => x.path)).size, analysisLinks.length);
});

test("task hub only navigates; it cannot synthesize facts, authorize or mutate account state", async () => {
  const hub = await source("workspace/AnalysisWorkspace.tsx");
  assert.doesNotMatch(hub, /setMode|setActiveAccount|setExampleAccount|fetch\(|invoke\(|realUserApi|reviewService|\.reduce\(/);
  assert.match(hub, /\/investments\/compare-example/);
  assert.match(hub, /status: c.synthetic/);
  const app = await source("App.tsx");
  assert.match(app, /path="\/comparison\/history" element=\{load\(<SelfComparisonWorkspace/);
});

test("comparison hub has exactly three product sections and no duplicated review or agent cards", async () => {
  assert.deepEqual(analysisLinks.map((item) => item.path), ["/comparison/history", "/investments/compare-example", "/comparison/professional"]);
  const hub = await source("workspace/AnalysisWorkspace.tsx");
  assert.equal((hub.match(/to: "/g) ?? []).length, 3);
  assert.doesNotMatch(hub, /to: "\/(ask|review|history)"|lg-boundary/);
  const app = await source("App.tsx");
  assert.match(app, /path="\/comparison\/professional" element=\{load\(<ProfessionalComparisonWorkspace/);
  assert.match(app, /path="\/comparison" element=\{<Navigate to="\/analysis" replace/);
});

test("self comparison keeps account gating and existing dates/values, without mixing in cohort data", async () => {
  const self = await source("workspace/SelfComparisonWorkspace.tsx");
  assert.match(self, /historyWorkspaceData/);
  assert.match(self, /data.availability === "ready"/);
  assert.match(self, /item.subjectId === study.subjectId && item.accountId === study.accountId/);
  assert.match(self, /comparison.observationStart/);
  assert.match(self, /comparison.observationEnd/);
  assert.match(self, /comparison.median/);
  assert.match(self, /comparison.currentValue/);
  assert.match(self, /comparison.status === "complete"/);
  assert.match(self, /ResearchComparisonStudy kind="self"/);
  assert.doesNotMatch(self, /PeerRangeChart|data.peer|\.reduce\(|\/ask/);
});

test("professional comparison uses independently generated study portfolios, not renamed cohorts", async () => {
  const pro = await source("workspace/ProfessionalComparisonWorkspace.tsx");
  const copy = await source("workspace/comparisonCopy.ts");
  assert.match(pro, /ResearchComparisonStudy kind="professional"/);
  assert.doesNotMatch(pro, /backendEvidence|generated|peerBenchmark|invoke|fetch\(/);
  assert.match(copy, /专业账户数据待接入/);
  assert.match(copy, /Professional data not connected/);
  assert.match(copy, /不使用示例群体代替专业人员/);
});

test("background stays outside route animation and respects motion and page visibility", async () => {
  const shell = await source("workspace/IntelligenceShell.tsx");
  assert.ok(shell.indexOf("<LiquidBackdrop />") < shell.indexOf("<AnimatePresence"));
  const video = await source("workspace/LiquidBackdrop.tsx");
  assert.match(video, /prefers-reduced-motion: reduce/);
  assert.match(video, /document\.hidden/);
  assert.match(video, /removeEventListener\("visibilitychange"/);
  assert.match(video, /onError=\{\(\) => setFailed\(true\)\}/);
  assert.doesNotMatch(video, /useDataMode|subject_id|account_id|localStorage|fetch\(|invoke\(/);
});

test("desktop media permission is host-specific; script and connection policies are unchanged", async () => {
  const config = JSON.parse(await readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
  const csp = config.app.security.csp;
  assert.match(csp, /media-src 'self' https:\/\/d8j0ntlcm91z4.cloudfront.net;/);
  assert.match(csp, /script-src 'self';/);
  assert.doesNotMatch(csp, /media-src[^;]*\*|connect-src[^;]*cloudfront/);
});
