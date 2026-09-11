import assert from "node:assert/strict";
import test from "node:test";
import { restoredAccountTurns, runChatTurn } from "../src/data/agentChat.ts";

const scope = {scope_kind:"account",subject_id:"owned",account_id:"one",data_mode:"real_user"};
const finding = {id:"f",title:{zh:"账户",en:"Account"},body:{zh:"已有事实",en:"Fact"},episode_id:null};
const result = {inference_id:"account_inference_1",scope,source_fingerprint:"f1",invalidated:false,
  answer:{version:"account_review_answer_v1",summary:{zh:"摘要",en:"Summary"},findings:[finding],guide_ids:[]}};
const turn = {id:"t",question:"如何理解",status:"complete",result};
const context = {version:"account_review_context_v1",scope,source_fingerprint:"f1",finding_options:[finding],conversation_turns:[turn]};

test("local archive restore admits only verified same-scope answers and never calls model", () => {
  assert.deepEqual(restoredAccountTurns(context), [turn]);
  for (const changed of [{...result,invalidated:true},{...result,source_fingerprint:"other"},
    {...result,scope:{...scope,account_id:"foreign"}}]) {
    assert.deepEqual(restoredAccountTurns({...context,conversation_turns:[{...turn,result:changed}]}), []);
  }
  assert.deepEqual(restoredAccountTurns({...context,conversation_turns:[{...turn,status:"running"}]}), []);
});

test("DSA reading progress is a status, never a partial unverified answer", async () => {
  const phases=[]; let polled=0;
  const api={start:async()=>({job_id:"j"}),poll:async()=>++polled===1
    ? {status:"running",phase:"reading",result:null} : {status:"complete",result}};
  const actual=await runChatTurn(api,scope,context,"问题",undefined,new AbortController().signal,async()=>{},p=>phases.push(p));
  assert.deepEqual(phases,["reading"]);assert.equal(actual,result);
});
