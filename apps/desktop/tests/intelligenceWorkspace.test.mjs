import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { isClassicWorkspace, workspaceDestinations, workspaceSection } from "../src/workspace/workspaceMode.ts";
import { reviewCandidatesFromFixture, reviewCandidatesFromRuntime, scopedCandidate } from "../src/workspace/reviewWorkspaceData.ts";

const source = async (name) => readFile(new URL(`../src/${name}`, import.meta.url), "utf8");

test("workspace presentation switch has no account or permission side effect", () => {
  assert.equal(isClassicWorkspace(""), false);
  assert.equal(isClassicWorkspace("?workspace=classic"), true);
  assert.equal(isClassicWorkspace("?workspace=classicish"), false);
  assert.equal(isClassicWorkspace("?data_mode=demo"), false);
  assert.equal(workspaceSection("/investments/episodes/owned"), "/investments");
  assert.equal(workspaceSection("/investments/compare-example"), "/comparison");
  assert.equal(new Set(workspaceDestinations.map((item) => item.path)).size, workspaceDestinations.length);
});

test("review index uses exact ownership and deterministic chronological ordering without scores", () => {
  const entry = (episodeId, subjectId, accountId, openedAt) => ({episode:{episodeId,subjectId,accountId,openedAt,closedAt:null,durationDays:2,status:"open"}, instrument:{displayName:episodeId,instrumentId:"SYN"},decisions:[{}], reviewPresentation:{facts:[{}]}});
  const facts = [entry("b","me","account","2025-01-02"), entry("foreign","other","account","2025-01-04"), entry("wrong-account","me","other","2025-01-04"), entry("a","me","account","2025-01-02")];
  const before=JSON.stringify(facts);
  assert.deepEqual(reviewCandidatesFromFixture(facts,"me","account").map((x)=>x.episodeId),["a","b"]);
  assert.equal(JSON.stringify(facts),before);
  assert.deepEqual(reviewCandidatesFromFixture(facts,"missing","account"),[]);
  assert.equal(scopedCandidate([],"foreign"),null);
});

test("runtime review index leaves absent review metadata absent", () => {
  const items=reviewCandidatesFromRuntime({subject_id:"me",account_id:"account",episodes:[{episode_id:"real",instrument_id:"SH:600000",display_name:"real",status:"open",opened_at:"2025-01-01",closed_at:null,duration_days:2}]});
  assert.equal(items[0].decisionCount,null);
  assert.equal(items[0].reviewFactCount,null);
  assert.equal(items[0].source,"runtime");
});

test("live importer is only mounted in native real-account mode", async () => {
  const page=await source("workspace/DataWorkspace.tsx");
  assert.match(page,/data\.runtimeAvailable && data\.mode === "real_user"/);
  assert.match(page,/initialKind=\{tab === "prices" \? "market" : "trade"\}/);
  assert.doesNotMatch(page,/commitTrades|commitPrices|runtimeRequest|type="file"/);
});

test("Journal is temporary user input and cannot write financial or model facts", async () => {
  const page=await source("workspace/ReviewWorkspace.tsx");
  const journal=page.slice(page.indexOf("function JournalDraft"),page.indexOf("export function ReviewWorkspace"));
  assert.match(journal,/new Date\(\)\.toISOString\(\)/);
  assert.match(journal,/retrospective/);
  assert.doesNotMatch(journal,/localStorage|sessionStorage|fetch\(|invoke\(|realUserApi|reviewService|\.note\(/);
  assert.match(page,/key=\{`\$\{subject\}:\$\{account\}:\$\{current\.episodeId\}`\}/);
});

test("Ask preserves the existing consent runtime and query-selected context", async () => {
  const page=await source("workspace/ReviewWorkspace.tsx");
  assert.match(page,/\[location\.search\]/);
  assert.match(page,/value\.subject_id !== subject \|\| value\.account_id !== account/);
  assert.match(page,/next\.episode\.subjectId !== subject \|\| next\.episode\.accountId !== account/);
  assert.match(page,/data\.mode === "real_user" && <DecisionAnalysisWorkspace/);
  assert.doesNotMatch(page,/reviewService\.start|allow_model_review|DEEPSEEK|api\.deepseek|setTimeout/);
});

test("pretrade remains an explicitly independent synthetic scenario without client accounting", async () => {
  const page=await source("workspace/PretradeWorkspace.tsx");
  assert.match(page,/data\.mode === "demo" \|\| entered/);
  assert.match(page,/pretradeDemo\.subjectId/);
  assert.match(page,/<DecisionCheckPage \/>/);
  assert.doesNotMatch(page,/\.reduce\(|calculate|\.cash\s*[+\-]|portfolioValue\s*=/);
});
