import test from "node:test";
import assert from "node:assert/strict";
import { projectAccountAnswer, runChatTurn, accountGuideEpisode, saveChat, readChat, saveChatContext, readChatContext } from "../src/data/agentChat.ts";
const scope = {scope_kind:"account", subject_id:"S", account_id:"A", data_mode:"real_user"};
const context = {version:"account_review_context_v1", scope, source_fingerprint:"f", finding_options:[],
  conversation_version:"account_conversation_answer_v2", record_refs:["read", "unread"], episode_ids:["ep"]};
const result = {inference_id:"i", scope, source_fingerprint:"f", invalidated:false, read_refs:["read"],
  verification:"receipts_and_grounding_review_v1", answer:{version:"account_conversation_answer_v2",
    paragraphs:[{kind:"concept",text:{zh:"这个比例不包含现金。",en:"This weight excludes cash."},refs:["read"]}],
    guides:[{guide_id:"episode-process",episode_id:"ep",label:{zh:"看看这轮",en:"Open this investment"}}]}};
test("canonical guide maps to owned display Episode without rewriting evidence", () => {
  const c = {...context,episode_display_ids:{ep:'display'}};
  assert.equal(accountGuideEpisode(c,'ep',['display']),'display');
  assert.equal(accountGuideEpisode(c,'foreign',['display']),undefined);
  assert.equal(accountGuideEpisode(c,'ep',['other']),undefined);
  assert.equal(accountGuideEpisode(context,'ep',['ep']),'ep');
  assert.equal(result.answer.guides[0].episode_id,'ep');
});
test("V2 renders natural answer and exact guide without fixed finding options",()=>{
  const projected=projectAccountAnswer(result,context,"zh-CN");
  assert.equal(projected.summary,"这个比例不包含现金。");
  assert.equal(projected.actions[0].episodeId,"ep");
});
test("route return restores a completed answer before fresh context is available",()=>{
  saveChat(scope,[{id:'saved',question:'What does this mean?',status:'complete',result}]);
  saveChatContext(scope,context);
  const restored=readChat(scope);
  assert.equal(restored[0].status,'complete');
  assert.equal(projectAccountAnswer(restored[0].result,readChatContext(scope),'zh-CN').summary,'这个比例不包含现金。');
  const copy=readChatContext(scope); copy.record_refs.length=0;
  assert.equal(readChatContext(scope).record_refs.length,2);
  assert.equal(readChatContext({...scope,account_id:'foreign'}),null);
  assert.equal(readChatContext({...scope,data_mode:'synthetic_showcase'}),null);
  assert.throws(()=>saveChatContext({...scope,account_id:'foreign'},context),/scope_mismatch/);
});
test("fresh changed facts invalidate an old answer; a new conversation clears its snapshot",()=>{
  saveChatContext(scope,{...context,source_fingerprint:'changed'});
  assert.equal(projectAccountAnswer(result,readChatContext(scope),'zh-CN'),null);
  saveChat(scope,[]);
  assert.equal(readChatContext(scope),null);
  assert.deepEqual(readChat(scope),[]);
});
test("V2 rejects unread refs, foreign episodes, stale scope and missing verification",()=>{
  for(const mutate of [r=>r.answer.paragraphs[0].refs=["unread"],r=>r.answer.guides[0].episode_id="foreign",
    r=>r.scope.account_id="other",r=>r.source_fingerprint="old",r=>r.verification=null,
    r=>r.answer.paragraphs[0].text.zh="",r=>r.answer.guides[0].guide_id="https://evil.test"]){
    const r=structuredClone(result);mutate(r);assert.equal(projectAccountAnswer(r,context,"zh-CN"),null);
  }
});
test("poll progress comes from runtime and no raw prose is rendered",async()=>{
  const phases=[];let n=0;
  const api={start:async()=>({job_id:"j"}),poll:async()=>++n<3?{status:"running",result:null,phase:n===1?"writing":"checking"}:{status:"complete",result}};
  await runChatTurn(api,scope,context,"Q",undefined,new AbortController().signal,async()=>{},p=>phases.push(p));
  assert.deepEqual(phases,["writing","checking"]);
});
test("public read refs can display dated sources and unread public refs stay hidden",()=>{
  const publicRef="public1";
  const withSources={...result, read_refs:["read", publicRef], public_read_refs:[publicRef],
    public_sources:[{title:"上交所", url:"https://www.sse.com.cn/", retrieved_at:"2026-09-08T04:00:00+00:00", provider:"bocha"}]};
  const projected=projectAccountAnswer(withSources, context, "zh-CN");
  assert.equal(projected.sources[0].url, "https://www.sse.com.cn/");
  const unread={...withSources, public_read_refs:[]};
  assert.equal(projectAccountAnswer(unread, context, "zh-CN"), null);
  const javascript={...withSources, public_sources:[{title:"x", url:"javascript:alert(1)"}]};
  assert.equal(projectAccountAnswer(javascript, context, "zh-CN").sources.length, 0);
});
test("stop requests backend cancellation for the owned job",async()=>{
  const controller=new AbortController();const calls=[];
  const api={start:async()=>({job_id:"j"}),poll:async()=>({status:"running",result:null}),
    cancel:async(s,j)=>calls.push([s,j])};
  await assert.rejects(runChatTurn(api,scope,context,"Q",undefined,controller.signal,async()=>controller.abort()),/chat_stopped/);
  assert.deepEqual(calls,[[scope,"j"]]);
});
test("runtime-audited method/status refs render and restore, undeclared/unread refs fail closed", () => {
  const value = structuredClone(result);
  value.read_refs = ["method", "status"];
  value.research_read_refs = ["method", "status"];
  value.answer.paragraphs[0].refs = ["method"];
  assert.ok(projectAccountAnswer(value, context, "zh-CN"));
  saveChat(scope, [{id:"research", question:"Research", status:"complete", result:value}]);
  assert.ok(projectAccountAnswer(readChat(scope)[0].result, context, "zh-CN"));
  for (const refs of [[], ["method"], ["method", "status", "unread"], "not-an-array", {}]) {
    assert.equal(projectAccountAnswer({...value, research_read_refs: refs}, context, "zh-CN"), null);
  }
});
test("Episode DSA validates dynamic owned reads, public technical reads and exact scope", () => {
  const episodeScope={scope_kind:"episode",subject_id:"S",account_id:"A",episode_id:"display-ep",data_mode:"real_user"};
  const episodeContext={...context,scope:episodeScope,record_refs:["base-context"]};
  const episodeResult={...result,scope:episodeScope,
    read_refs:["base-context","owned-episode","owned-technical","public-fundamentals","public-technical"],
    analysis_read_refs:["owned-episode","owned-technical"],
    public_read_refs:["public-fundamentals","public-technical"],
    answer:{...result.answer,paragraphs:[
      {kind:"fact",text:{zh:"这轮记录可核对。",en:"This investment record is auditable."},refs:["owned-episode"]},
      {kind:"interpretation",text:{zh:"公开技术资料另列。",en:"Public technical context is separate."},refs:["public-technical"]},
    ],guides:[]}};
  assert.ok(projectAccountAnswer(episodeResult,episodeContext,"zh-CN"));
  const accountTurns=readChat(scope).length;
  saveChat(episodeScope,[{id:"episode",question:"这轮怎样？",status:"complete",result:episodeResult}]);
  assert.equal(readChat(episodeScope).length,1);assert.equal(readChat(scope).length,accountTurns);
  for (const mutate of [
    r=>{r.analysis_read_refs=["owned-episode","owned-technical","unread-analysis"]},
    r=>{r.read_refs=r.read_refs.filter(ref=>ref!=="owned-technical")},
    r=>{r.analysis_read_refs=[42]},
    r=>{r.public_read_refs=[{}]},
    r=>{r.read_refs=[...r.read_refs,42]},
    r=>{r.scope.episode_id="other"},
    r=>{r.answer.paragraphs[0].refs=["not-read"]},
  ]) { const value=structuredClone(episodeResult);mutate(value);assert.equal(projectAccountAnswer(value,episodeContext,"zh-CN"),null); }
  assert.equal(projectAccountAnswer(episodeResult,{...episodeContext,record_refs:["base-context",42]},"zh-CN"),null);
  saveChat(episodeScope,[]);
});
