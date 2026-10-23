import assert from 'node:assert/strict';
import test from 'node:test';
import { requestGroundedCompanyAnswer, CompanyRequestError } from '../src/data/companyResearchAnswer.ts';
const history=[{role:'user',content:'营业收入是多少？'}];
const grounded={status:'ANSWERED',answer:'原始值 100 千元 [1]',display_answer:'显示值 100 千元 [1]',citations:[{index:1,evidence_ids:['e1'],label:'营业收入'}]};

test('model answer retains current-build evidence and display text',async()=>{
 const calls=[];const reply=await requestGroundedCompanyAnswer('build_a',history,async(action,params)=>{calls.push([action,params]);return grounded;});
 assert.equal(reply.source,'model');assert.equal(reply.content,grounded.display_answer);assert.equal(reply.citations[0].evidence_ids[0],'e1');assert.equal(calls.length,1);assert.equal(calls[0][1].build_id,'build_a');
});
test('rejected model answer is withheld; labelled lookup uses the same company',async()=>{
 const calls=[];const reply=await requestGroundedCompanyAnswer('build_b',history,async(action,params)=>{calls.push([action,params]);return action==='chat'?{status:'NOT_IN_MODEL',reason_code:'ANSWER_VALIDATION_FAILED',answer:'unsafe invented 999',citations:[]}:grounded;});
 assert.equal(reply.source,'lookup');assert.match(reply.notice,/未通过/);assert.doesNotMatch(reply.content,/999/);assert.deepEqual(calls.map(c=>c[1].build_id),['build_b','build_b']);
});
test('unconfigured model falls back explicitly; transport failure never invents a reply',async()=>{
 const reply=await requestGroundedCompanyAnswer('build_a',history,async(action)=>{if(action==='chat')throw new CompanyRequestError('company_model_unavailable','missing');return grounded;});
 assert.equal(reply.source,'lookup');assert.match(reply.notice,/AI 模型暂不可用/);
 await assert.rejects(()=>requestGroundedCompanyAnswer('build_a',history,async()=>{throw new CompanyRequestError('company_engine_unavailable','offline');}),/offline/);
});
test('an ANSWERED reply without evidence is rejected rather than displayed',async()=>{
 await assert.rejects(()=>requestGroundedCompanyAnswer('build_a',history,async()=>({...grounded,citations:[]})),/证据格式/);
});
test('a cancelled company change never starts lookup for the old company',async()=>{
 const controller=new AbortController();controller.abort();let calls=0;
 await assert.rejects(()=>requestGroundedCompanyAnswer('build_a',history,async()=>{calls++;throw new CompanyRequestError('company_model_unavailable','missing');},controller.signal));
 assert.equal(calls,1);
});
test('long questions are not silently truncated into a different lookup',async()=>{
 const actions=[];await assert.rejects(()=>requestGroundedCompanyAnswer('build_a',[{role:'user',content:'问'.repeat(501)}],async(action)=>{actions.push(action);throw new CompanyRequestError('company_model_unavailable','missing');}),/500/);
 assert.deepEqual(actions,['chat']);
});
