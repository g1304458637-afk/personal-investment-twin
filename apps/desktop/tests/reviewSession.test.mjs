import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { ReviewSessions, reviewScopeKey } from '../src/data/reviewSession.ts';
import { notifyRuntimeDataChange, onRuntimeDataChange } from '../src/data/runtimeInvalidation.ts';

const scope = {subject_id:'owner', account_id:'account', episode_id:'episode', data_mode:'real_user'};
const context = (s=scope, inferences=[]) => ({scope:s, as_of:'2025-12-31', data_tier:'authorized_beta', records:[], comparison:null, inferences});
const result = {inference_id:'answer-1', invalidated:false};
const deferred = () => { let resolve, reject; const promise = new Promise((r,j) => {resolve=r; reject=j;}); return {promise, resolve, reject}; };
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture(overrides={}) {
  const calls={read:0, start:0, poll:0};
  const api={context:async s => {calls.read++; return context(s);}, start:async () => {calls.start++; return {job_id:'job'};}, poll:async () => {calls.poll++; return {status:'complete', result};}, ...overrides};
  return {calls, store:new ReviewSessions(api, async () => {})};
}
test('startup prefetch and a mounted page share exactly one pending context request', async () => {
  const read=deferred(); let calls=0;
  const {store}=fixture({context:() => {calls++; return read.promise;}});
  const warm=store.prefetch(scope), page=store.load({...scope});
  await flush(); assert.equal(calls,1); assert.equal(store.snapshot(scope).loading,true);
  read.resolve(context()); await Promise.all([warm,page]);
  assert.equal(store.snapshot(scope).loading,false);
  await store.load(scope); assert.equal(calls,1);
});
test('navigation retains context and drafts, without another read or model invocation', async () => {
  const {store,calls}=fixture();
  const leave=store.subscribe(scope,()=>{}); await store.load(scope);
  store.edit(scope,{question:'为什么亏损',note:'我的计划',noteKind:'plan'}); leave();
  const returnToPage=store.subscribe(scope,()=>{}); await store.load(scope);
  assert.equal(calls.read,1); assert.equal(calls.start,0);
  assert.equal(store.snapshot(scope).question,'为什么亏损'); assert.equal(store.snapshot(scope).noteKind,'plan'); returnToPage();
});
test('an analysis finishes after leaving the page and is restored without starting again', async () => {
  const finish=deferred(); let starts=0;
  const {store}=fixture({start:async()=>{starts++;return {job_id:'job'};},poll:()=>finish.promise});
  const leave=store.subscribe(scope,()=>{}); await store.load(scope);
  const task=store.analyze(scope,'分析',true); await flush(); leave();
  assert.equal(store.snapshot(scope).busy,true);
  assert.equal(store.analyze(scope,'分析',true),task);
  finish.resolve({status:'complete',result}); await task;
  await store.load(scope);
  assert.equal(starts,1); assert.equal(store.snapshot(scope).answer,result); assert.equal(store.snapshot(scope).busy,false);
});
test('only uninvalidated previous inference is restored; loading never grants consent', async () => {
  const {store,calls}=fixture({context:async()=>context(scope,[{...result,invalidated:true},result])});
  await store.load(scope); assert.equal(store.snapshot(scope).answer,result);
  await store.analyze(scope,'分析',false); assert.equal(calls.start,0);
});
test('data or note invalidation removes old facts and answer but keeps unsent draft', async () => {
  const {store,calls}=fixture(); await store.load(scope); await store.analyze(scope,'分析',true);
  store.edit(scope,{question:'草稿'}); store.invalidate('owner','unrelated'); assert.equal(store.snapshot(scope).answer,result);
  store.invalidate('owner','account'); assert.equal(store.snapshot(scope).context,null); assert.equal(store.snapshot(scope).answer,null);
  assert.equal(store.snapshot(scope).question,'草稿'); await store.load(scope); assert.equal(calls.read,2);
});
test('a slow old read cannot overwrite a new data version', async () => {
  const old=deferred(); let reads=0;
  const {store}=fixture({context:async()=>++reads===1?old.promise:context()});
  const first=store.load(scope); await flush(); store.invalidate('owner','account');
  const second=await store.load(scope); old.resolve({...context(),as_of:'old'});
  await assert.rejects(first,/review_context_changed/); assert.equal(store.snapshot(scope).context,second);
});
test('invalidation notifies a mounted snapshot reader only once despite LRU touches', async () => {
  const {store}=fixture(); await store.load(scope); let notifications=0;
  const off=store.subscribe(scope,()=>{assert.ok(++notifications<3);store.snapshot(scope);});
  store.invalidate('owner','account'); assert.equal(notifications,1); off();
});
test('a job result from before a mutation is never published to the new version', async () => {
  const finish=deferred(); const {store}=fixture({poll:()=>finish.promise});
  await store.load(scope); const task=store.analyze(scope,'分析',true); await flush(); store.invalidate('owner','account');
  await store.load(scope); finish.resolve({status:'complete',result}); await task;
  assert.equal(store.snapshot(scope).answer,null); assert.equal(store.snapshot(scope).busy,false);
});
test('scope keys isolate owner, account, episode, demo, counterpart, and share permissions', () => {
  for (const patch of [{subject_id:'other'},{account_id:'other'},{episode_id:'other'},{data_mode:'synthetic_showcase'},{share_id:'share'},{pair_side:'B'},{compare_pair:true}]) {
    assert.notEqual(reviewScopeKey(scope),reviewScopeKey({...scope,...patch}));
  }
  assert.equal(reviewScopeKey(scope),reviewScopeKey({episode_id:'episode',account_id:'account',subject_id:'owner'}));
});
test('wrong account response fails closed, while explicit display-to-canonical mapping is supported', async () => {
  const {store}=fixture({context:async()=>context({...scope,account_id:'foreign'})});
  await assert.rejects(store.load(scope),/chat_scope_mismatch/); assert.equal(store.snapshot(scope).context,null);
  const ok=fixture({context:async()=>({...context({...scope,episode_id:'canonical'}),identity_mapping:{display_episode_id:'episode',canonical_episode_id:'canonical'}})});
  await ok.store.load(scope); assert.ok(ok.store.snapshot(scope).context);
});
test('failed preparation is retryable, not retained as a permanently rejected promise', async () => {
  let reads=0; const {store}=fixture({context:async()=>{if(++reads===1)throw Error('offline');return context();}});
  await store.prefetch(scope); assert.equal(store.snapshot(scope).error,'offline');
  await store.load(scope); assert.equal(store.snapshot(scope).error,null); assert.equal(reads,2);
});
test('shared context is discarded on leaving so expiry/revocation is checked on return', async () => {
  const shared={...scope,share_id:'share'}; const {store,calls}=fixture();
  const leave=store.subscribe(shared,()=>{}); await store.load(shared); leave();
  await store.load(shared); assert.equal(calls.read,2);
});
test('bounded LRU discards old inactive contexts', async () => {
  const {store,calls}=fixture(); await store.load(scope);
  for(let i=0;i<20;i++)await store.load({...scope,episode_id:`other-${i}`});
  await store.load(scope); assert.equal(calls.read,22);
});
test('all account fact/permission writes invalidate reads, while read RPCs do not', () => {
  const changes=[]; const off=onRuntimeDataChange(change=>changes.push(change));
  for(const method of ['ingestion.commit_trade_import','market.commit_price_import','data.delete_account','review.add_note','compare.import_share','compare.revoke_share'])notifyRuntimeDataChange(method,scope);
  notifyRuntimeDataChange('review.context',scope); notifyRuntimeDataChange('review.poll',scope); off();
  assert.equal(changes.length,6); assert.deepEqual(changes[0],{subject:'owner',account:'account'});
});
test('preparation is wired before the analysis tab and never starts a model', async () => {
  const source = path => readFile(new URL(`../src/${path}`,import.meta.url),'utf8');
  const provider=await source('data/DataModeProvider.tsx'), page=await source('pages/PositionEpisodePage.tsx');
  ;
  assert.doesNotMatch(provider,/reviewService.start|reviewSessions.analyze/);
  assert.doesNotMatch(page,/reviewService.start|reviewSessions.analyze/);
  const rpc=await source('data/runtimeService.ts');
  assert.ok(rpc.indexOf('notifyRuntimeDataChange(method, params)')>rpc.indexOf('if (!response.ok'));
});
