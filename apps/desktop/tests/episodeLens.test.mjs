import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { adaptDecisionLensReport, selectLensState } from '../src/data/episodeLens.ts';

const decision = {decisionId:'d1',executionId:'e1',stateBeforeRef:'s1',occurredAt:'2025-03-07T07:00:00',side:'BUY',executedQuantity:400,executionPrice:12,stateBefore:{quantity:700,averageCost:10}};
const entry = {episode:{episodeId:'ep1',subjectId:'user1',accountId:'account1',instrumentId:'stock1'},instrument:{dataTier:'synthetic'},decisions:[decision]};
const check = {decision_id:'d1',execution_id:'e1',state_before_ref:'s1',occurred_at:decision.occurredAt,market_date:'2025-03-07',actual:{side:'BUY',quantity:400,price:12,quantity_before:700,average_cost_before:10},verdict:'aligned',expected_action:'允许加仓',explanation:'符合这套规则',observed_through:'2025-03-06',observation_count:20,conditions:[{label:'最近收盘价',actual:12,operator:'>=',threshold:11,passed:true,unit:'price'}],input_fingerprint:'a'.repeat(64),limitations:[]};
function report() {return {schema_version:'decision_lens.v1',temporal_policy:'prior_daily_close_only',episode_id:'ep1',subject_id:'user1',account_id:'account1',instrument_id:'stock1',data_tier:'synthetic',limitations:[],methods:['trend_ma20','closing_breakout20','cost_addition'].map(id=>({id,version:'1.0.0',title:'方法',description:'方法说明',rule:'规则',parameters:{window:20},checks:[structuredClone(check)]}))};}

test('Lens transports only verified method results; does not mutate actual history',()=>{
  const before=structuredClone(entry); const raw=report(); const original=structuredClone(raw);
  const view=adaptDecisionLensReport(raw,entry);
  assert.equal(view.methods.length,3); assert.deepEqual(raw,original); assert.deepEqual(entry,before);
});
test('calendar labels retain exchange dates in positive and negative browser timezones',()=>{
  const moduleUrl=new URL('../src/data/episodeLens.ts',import.meta.url).href;
  for(const TZ of ['America/Los_Angeles','Pacific/Honolulu','Asia/Shanghai','UTC']) {
    const child=spawnSync(process.execPath,['--input-type=module','-e',`import {formatLensDate} from ${JSON.stringify(moduleUrl)}; console.log(formatLensDate('2025-01-02','en-US')); console.log(formatLensDate('2025-12-31','zh-CN'));`],{env:{...process.env,TZ},encoding:'utf8'});
    assert.equal(child.status,0,child.stderr);
    assert.deepEqual(child.stdout.trim().split('\n'),['Jan 2, 2025','2025年12月31日'],TZ);
  }
});
for (const field of ['episode_id','subject_id','account_id','instrument_id','data_tier']) {
  test(`Lens rejects foreign ${field}`,()=>{const raw=report();raw[field]='foreign';assert.throws(()=>adaptDecisionLensReport(raw,entry));});
}
for(const mutate of [
  c=>c.execution_id='other',c=>c.state_before_ref='other',c=>c.actual.price=13,
  c=>c.actual.quantity=401,c=>c.actual.quantity_before=0,c=>c.actual.average_cost_before=9,
  c=>c.actual.side='SELL',c=>c.occurred_at='2025-03-08T07:00:00',
  c=>c.observed_through='2025-03-07',c=>c.observed_through='2025-03-08',
  c=>c.market_date='2025-02-30',c=>c.observation_count=NaN,c=>c.observation_count=-1,
  c=>c.conditions[0].actual=Infinity,c=>c.conditions[0].passed='true',c=>c.input_fingerprint='unverified',
]) test(`Lens rejects ledger/time/schema tampering: ${mutate.toString()}`,()=>{const raw=report();mutate(raw.methods[0].checks[0]);assert.throws(()=>adaptDecisionLensReport(raw,entry));});

test('Lens requires registered unique methods and complete nonduplicated decisions',()=>{
  for(const mutate of [r=>r.methods.pop(),r=>r.methods.push(r.methods[0]),r=>r.methods[0].checks=[],r=>r.methods[0].checks.push(r.methods[0].checks[0]),r=>r.methods[0].id='arbitrary_formula']){const raw=report();mutate(raw);assert.throws(()=>adaptDecisionLensReport(raw,entry));}
});
test('method switch preserves selected real decision, invalid deep links get valid defaults',()=>{
  const r=adaptDecisionLensReport(report(),entry);
  assert.equal(selectLensState(r,'cost_addition','d1').check.decision_id,'d1');
  assert.equal(selectLensState(r,'unknown','foreign').method.id,'trend_ma20');
  assert.equal(selectLensState(r,'unknown','foreign').check.decision_id,'d1');
});
test('all shipped Lens reports match canonical showcase ledger; histories unchanged',async()=>{
  const source=JSON.parse(await readFile(new URL('../src/generated/showcase-demo.json',import.meta.url),'utf8'));
  const generated=JSON.parse(await readFile(new URL('../src/generated/episode-lenses-demo.json',import.meta.url),'utf8'));
  const {adaptPositionEpisodeDemo}=await import('../src/data/positionEpisode.ts');
  const entries=adaptPositionEpisodeDemo(source.position_episode_demo).entries;
  assert.equal(generated.reports.length,entries.length);
  let different=0;
  for(const entry of entries){const raw=generated.reports.find(r=>r.episode_id===entry.episode.episodeId); const view=adaptDecisionLensReport(raw,entry);for(const method of view.methods)different+=method.checks.filter(c=>c.verdict==='different').length;}
  assert.ok(different>0,'demo must explain actual rule differences, not only placeholders');
});
test('Lens shares actual chart instances and does not call a model or calculate finance in browser',async()=>{
  const page=await readFile(new URL('../src/pages/PositionEpisodePage.tsx',import.meta.url),'utf8');
  assert.match(page,/LensMethodSelector/);assert.match(page,/LensDecisionInspector/);assert.match(page,/LensDecisionTimeline/);
  assert.match(page,/sampleSection !== "process" && !lensMode/);
  assert.match(page,/next\.set\("lensDecision", lensState\.check\.decision_id\)/);
  const component=await readFile(new URL('../src/components/review/DecisionLensPanel.tsx',import.meta.url),'utf8');
  assert.doesNotMatch(component,/realUserApi|reviewService|fetch\(|calculatePnl|calculateReturn|eval\(/);
});
