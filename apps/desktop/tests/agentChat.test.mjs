import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { chatScopeKey, contextMatchesScope, isConversationScope, projectAccountAnswer, runChatTurn, saveChat, readChat, previousChatResult } from "../src/data/agentChat.ts";
const scope = {scope_kind:"account",subject_id:"owned",account_id:"one",data_mode:"real_user"};
const finding = {id:"fact1",title:{zh:"账户",en:"Account"},body:{zh:"已有账户事实",en:"Existing account fact"},episode_id:null};
const context = {version:"account_review_context_v1",scope,source_fingerprint:"facts1",as_of:"2026-01-06",data_tier:"authorized_beta",finding_options:[finding]};
const result = {inference_id:"account_inference_1",scope,source_fingerprint:"facts1",invalidated:false,answer:{version:"account_review_answer_v1",summary:{zh:"账户分析",en:"Account review"},findings:[finding],guide_ids:[]}};
const pause = async () => {};
const copy = value => structuredClone(value);

test("whole account scope has no Episode and its source mode participates in identity", () => {
  assert.equal(contextMatchesScope(context,scope),true);
  assert.equal("episode_id" in scope,false);
  for (const changed of [{...scope,account_id:"other"},{...scope,subject_id:"other"},{...scope,data_mode:"synthetic_showcase"}]) {
    assert.notEqual(chatScopeKey(scope),chatScopeKey(changed));
    assert.equal(contextMatchesScope(context,changed),false);
  }
  const episode={subject_id:"owned",account_id:"one",episode_id:"ep1"};
  assert.equal(chatScopeKey(episode),chatScopeKey({...episode,pair_side:"A"}));
});
test("DSA Episode scope is explicit and cannot share legacy review or account cache identity", () => {
  const episode={scope_kind:"episode",subject_id:"owned",account_id:"one",episode_id:"ep1",data_mode:"real_user"};
  const legacy={subject_id:"owned",account_id:"one",episode_id:"ep1",data_mode:"real_user"};
  assert.equal(isConversationScope(scope),true);assert.equal(isConversationScope(episode),true);
  assert.equal(isConversationScope(legacy),false);
  assert.notEqual(chatScopeKey(episode),chatScopeKey(legacy));
  assert.notEqual(chatScopeKey(episode),chatScopeKey(scope));
  assert.notEqual(chatScopeKey(episode),chatScopeKey({...episode,episode_id:"ep2"}));
  const episodeContext={...context,scope:episode};
  assert.equal(contextMatchesScope(episodeContext,episode),true);
  assert.equal(contextMatchesScope(episodeContext,legacy),false);
  assert.equal(contextMatchesScope(context,episode),false);
});
test("Episode context binds request scope including share and comparison metadata", () => {
  const s={subject_id:"owned",account_id:"one",episode_id:"ep1",data_mode:"real_user"};
  const c={scope:s,request_scope:s,records:[]};
  assert.equal(contextMatchesScope(c,s),true);
  for (const change of [{share_id:"share1"},{compare_pair:true},{pair_side:"B"},{data_mode:"synthetic_episode"}]) assert.equal(contextMatchesScope(c,{...s,...change}),false);
  assert.equal(contextMatchesScope({...c,request_scope:undefined},s),false);
});
test("account answer only displays registered facts from the exact source and registered guides", () => {
  assert.equal(projectAccountAnswer(result,context,"zh-CN").findings[0].body,finding.body.zh);
  for (const mutate of [
    r=>{r.scope.account_id="other";},r=>{r.scope.data_mode="synthetic_showcase";},r=>{r.scope.scope_kind="episode";},
    r=>{r.invalidated=true;},r=>{r.source_fingerprint="changed";},r=>{r.answer.findings[0].body.zh="invented";},
    r=>{r.answer.findings[0].episode_id="foreign";},r=>{r.answer.findings[0].id="unread";},
    r=>{r.answer.guide_ids=["https://evil.test"];},r=>{r.answer.findings=[];},r=>{r.answer.findings.push(copy(finding));},
  ]) {const r=copy(result);mutate(r);assert.equal(projectAccountAnswer(r,context,"zh-CN"),null);}
});
test("loading -> success preserves prior backend inference id without transmitting assistant text", async () => {
  const calls=[]; let count=0;
  const api={start:async(...args)=>{calls.push(args);return {job_id:"job1"};},poll:async()=>++count===1?{status:"running",result:null}:{status:"complete",result}};
  assert.deepEqual(await runChatTurn(api,scope,context,"  question  ","account_inference_previous",new AbortController().signal,pause),result);
  assert.deepEqual(calls,[[scope,"question","account_inference_previous"]]);assert.equal(count,2);
});
test("rejection and stale responses fail closed without a model prose fallback", async () => {
  for (const status of ["failed","stale"]) {
    const api={start:async()=>({job_id:"j"}),poll:async()=>({status,reason:"account_facts_changed",result:null})};
    await assert.rejects(runChatTurn(api,scope,context,"question",undefined,new AbortController().signal,pause),/account_facts_changed/);
  }
  const api={start:async()=>({job_id:"j"}),poll:async()=>({status:"complete",result:{...result,invalidated:true}})};
  await assert.rejects(runChatTurn(api,scope,context,"question",undefined,new AbortController().signal,pause),/not_verified/);
});
test("stopped old request cannot return over a newer successful request", async () => {
  let release; let reached;const polled=new Promise(resolve=>{reached=resolve;});
  const api={start:async()=>({job_id:"a"}),poll:async()=>{reached();return new Promise(resolve=>{release=resolve;});}};
  const controller=new AbortController();const old=runChatTurn(api,scope,context,"A",undefined,controller.signal,pause);
  const rejected=assert.rejects(old,/chat_stopped/);await polled;controller.abort();
  const newer=await runChatTurn({start:async()=>({job_id:"b"}),poll:async()=>({status:"complete",result:{...result,inference_id:"new"}})},scope,context,"B",undefined,new AbortController().signal,pause);
  release({status:"complete",result});await rejected;assert.equal(newer.inference_id,"new");
});
test("a context mismatch never starts a model call", async () => {
  let called=false;const api={start:async()=>{called=true;return{job_id:"j"};},poll:async()=>({status:"complete",result})};
  await assert.rejects(runChatTurn(api,{...scope,account_id:"foreign"},context,"question",undefined,new AbortController().signal,pause),/scope_or_question_invalid/);
  assert.equal(called,false);
});
test("session history is scope-isolated and invalid latest answer never falls back to an older predecessor", () => {
  const turns=[{id:"one",question:"Q",status:"complete",result},{id:"two",question:"Q2",status:"running",result:null}];
  saveChat(scope,turns);assert.equal(readChat(scope)[1].status,"stopped");assert.equal(readChat({...scope,account_id:"other"}).length,0);
  assert.equal(previousChatResult(turns),result.inference_id);
  assert.equal(previousChatResult([...turns,{id:"three",status:"complete",result:{...result,invalidated:true}}]),undefined);
  saveChat(scope,[]);assert.equal(readChat(scope).length,0);
});
test("standalone UI keeps consent, explicit offline guides, stop waiting and account default", async () => {
  const page=await readFile(new URL("../src/workspace/AgentWorkspace.tsx",import.meta.url),"utf8");
  const service=await readFile(new URL("../src/data/agentChatService.ts",import.meta.url),"utf8");
  assert.match(page,/scope_kind:"account"/);assert.match(page,/scope_kind:"episode"/);assert.match(page,/<option value="">\{c.account\}/);
  assert.match(page,/!consent/);assert.match(page,/active.current !== controller/);assert.match(page,/\.abort\(\)/);
  assert.match(page,/c.browser/);assert.match(page,/c.guideHint/);assert.match(page,/isComposing/);
  assert.doesNotMatch(page,/invoke\(|fetch\(|localStorage|dangerouslySetInnerHTML/);
  assert.match(service,/previous_inference_id/);assert.doesNotMatch(service,/apiKey|Authorization|assistant_text/);
  assert.match(service,/isConversationScope\(scope\)/);
  assert.match(page,/c.entries.map/);assert.match(page,/AgentTurnStatus turn=\{turn\}/);
  const status=await readFile(new URL("../src/workspace/agentTurnStatusModel.ts",import.meta.url),"utf8");
  assert.match(status,/searching:/);assert.match(status,/quoting:/);
  assert.match(page,/answer.sources/);assert.match(page,/searchServiceRequest/);
});
test("persistent copy has six distinct entries including research, comparisons and scenarios", async () => {
  const { agentChatCopy } = await import("../src/workspace/agentChatCopy.ts");
  for (const locale of ["zh-CN","en-US"]) {
    const ids = agentChatCopy[locale].entries.map(item => item.id);
    assert.deepEqual(ids, ["analyze","compare","scenario","research","learn","chart"]);
    assert.ok(agentChatCopy[locale].searchNeeded);
  }
});


test("failed DSA turn preserves safe failure category and diagnostic id", async () => {
  const api={start:async()=>({job_id:"j"}),poll:async()=>({status:"failed",result:null,
    reason:"account_review_analysis_failed",diagnostic:{code:"account_answer_number_not_in_sources",diagnostic_id:"abc123def456"}})};
  await assert.rejects(runChatTurn(api,scope,context,"question",undefined,new AbortController().signal,pause), error => {
    assert.equal(error.message,"account_answer_number_not_in_sources");
    assert.equal(error.diagnosticId,"abc123def456"); return true;
  });
  api.poll=async()=>({status:"failed",result:null,reason:"account_review_analysis_failed",
    diagnostic:{code:"secret-private-prose",diagnostic_id:"secret-private-prose"}});
  await assert.rejects(runChatTurn(api,scope,context,"question",undefined,new AbortController().signal,pause), error => {
    assert.equal(error.message,"account_review_analysis_failed"); assert.equal(error.diagnosticId,undefined); return true;
  });
});

test("schema and validation errors are distinct from changed account scope", async () => {
  const {chatErrorText}=await import("../src/workspace/agentChatCopy.ts");
  assert.match(chatErrorText("account_answer_number_not_in_sources","zh-CN"), /数字.*来源/);
  assert.match(chatErrorText("account_conversation_schema_failed","zh-CN"), /格式/);
  assert.match(chatErrorText("account_review_timeout","zh-CN"), /超时/);
  assert.match(chatErrorText("account_conversation_context_over_limit","en-US"), /context limit/);
  assert.match(chatErrorText("conversation_stale","zh-CN"), /新对话/);
  assert.doesNotMatch(chatErrorText("account_conversation_schema_failed","zh-CN"), /资料.*变化/);
});
