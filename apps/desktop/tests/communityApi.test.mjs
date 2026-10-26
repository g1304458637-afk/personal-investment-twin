import test from 'node:test';
import assert from 'node:assert/strict';
import {communityCard,communityApi,CommunityError} from '../src/data/communityApi.ts';
import {exampleInvestmentInputs,projectInvestmentShare,defaultInvestmentDisclosure,validatePublishedInvestmentCard} from '../src/data/investmentSharing.ts';

test('member preview removes untrusted source claims without adding hidden fields',()=>{
 const input=exampleInvestmentInputs()[1];input.source='local_account';input.definitions=['PRIVATE_PATH'];
 const original=projectInvestmentShare(input,defaultInvestmentDisclosure());const shown=communityCard(original);
 assert.equal(shown.source,'user_reported');assert.equal(validatePublishedInvestmentCard(shown),true);
 assert.ok(!JSON.stringify(shown).includes('PRIVATE_PATH'));assert.ok(!JSON.stringify(shown).includes('marketValue'));
 assert.deepEqual(shown.disclosure,original.disclosure);assert.equal(original.source,'local_account');
 assert.equal(communityCard({...original,source:'synthetic'}).source,'synthetic');
});

test('API uses same-origin cookies and fresh in-memory CSRF; errors never become success',async()=>{
 const original=globalThis.fetch;const calls=[];
 try{
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.endsWith('session')?{csrf:'csrf-test'}:{ok:true}};};
  await communityApi('session');await communityApi('posts/1/follow',{following:true});
  assert.equal(calls[1].options.credentials,'same-origin');assert.equal(calls[1].options.headers['X-CSRF-Token'],'csrf-test');
  assert.equal(calls[1].options.body,'{"following":true}');
  await communityApi('logout',{});await communityApi('posts',{});assert.equal(calls.at(-1).options.headers['X-CSRF-Token'],'');
  globalThis.fetch=async()=>({ok:false,status:403,json:async()=>({error:'denied'})});
  await assert.rejects(communityApi('posts',{}),e=>e instanceof CommunityError&&e.status===403&&e.message==='denied');
 }finally{globalThis.fetch=original;}
});
