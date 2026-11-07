import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import type {DemoData, Path} from '../src/model.ts';
import type {EpisodeArchive} from '../src/episodes.ts';
import {buildCareerSnapshot, buildCareerEpisodeStats} from '../src/careerMetrics.ts';

const data=JSON.parse(readFileSync(new URL('../public/demo-data.json',import.meta.url),'utf8')) as DemoData;
const archive=JSON.parse(readFileSync(new URL('../public/investment-episodes.json',import.meta.url),'utf8')) as EpisodeArchive;
const actual=(d:DemoData)=>d.paths.find(p=>p.id==='actual')!;
const near=(value:number,expected:number,tolerance=1e-9)=>assert.ok(Math.abs(value-expected)<=tolerance,`${value} != ${expected}`);

function cashAccount():DemoData {
  const copy=structuredClone(data);
  copy.source_fingerprint='cash-only-test';
  copy.dates=['2024-01-02','2024-01-03'];
  copy.assets=[];
  const path:Path={...actual(copy),fills:[],summary:{equity:'200',cash:'200',period_pnl:'0',fees:'0'},return:'0',max_drawdown:0,days:[
    {date:copy.dates[0],equity:'100',cash:'100',nav:'1',drawdown:'0',period_pnl:'0',net_contributions:'0',holdings:{},position_count:0},
    {date:copy.dates[1],equity:'200',cash:'200',nav:'1',drawdown:'0',period_pnl:'0',net_contributions:'100',holdings:{},position_count:0}
  ]};
  copy.paths=[path];return copy;
}
function emptyArchive(d:DemoData):EpisodeArchive {
  return {...structuredClone(archive),source_fingerprint:d.source_fingerprint,as_of:d.dates.at(-1)!,execution_binding:[],episodes:[],
    summary:{episode_count:0,trade_count:0,open_count:0,closed_count:0,pnl:'0',dividend_income:'0'}};
}

test('career headline and allocation values reconcile to the sample account',()=>{
  const s=buildCareerSnapshot(data);
  near(s.equity,791282.78);near(s.cash,364477.68);near(s.marketValue,426805.10);
  near(s.initialCapital,500000);near(s.netInvested,630000);near(s.pnl,161282.78);
  near(s.return,.3099914964554435);near(s.maxDrawdown,-.19711680364954828);
  near(s.currentDrawdown,-.0215490549754868);near(s.fees,1750.29);
  assert.equal(s.dayCount,1455);assert.equal(s.tradeCount,54);assert.equal(s.holdings.length,5);
  near(s.holdings.reduce((sum,h)=>sum+h.weight,0)+s.cash/s.equity,1);
  near(s.hhi!,.2443524964693904);near(s.top3Weight,(137718+119636+88881.1)/791282.78);
  near(s.meanDailyTurnover,.002859948747473182);
  near(s.years.reduce((sum,y)=>sum+y.pnl,0),s.pnl,.001);
  assert.equal(s.years.reduce((sum,y)=>sum+y.trades,0),54);
});

test('statistics use completed investment rounds and inclusive holding days',()=>{
  const s=buildCareerEpisodeStats(data,archive);
  assert.equal(s.closed.length,8);assert.equal(s.open.length,5);
  assert.equal(s.winCount,5);assert.equal(s.lossCount,3);assert.equal(s.flatCount,0);
  near(s.winRate!,.625);near(s.profitFactor!,1.5605462767985616);near(s.payoff!,.936327766079137);
  assert.equal(s.medianHoldingDays,567);
});

test('the actual account is selected by identity independently of strategy ordering',()=>{
  const shuffled=structuredClone(data);shuffled.paths.reverse();
  assert.equal(buildCareerSnapshot(shuffled).actual.id,'actual');
  assert.deepEqual(buildCareerEpisodeStats(shuffled,archive),buildCareerEpisodeStats(data,archive));
  near(buildCareerSnapshot(shuffled).meanDailyTurnover,buildCareerSnapshot(data).meanDailyTurnover);
});

test('cash deposits do not become return, profit, trading or concentration',()=>{
  const d=cashAccount(),s=buildCareerSnapshot(d),e=buildCareerEpisodeStats(d,emptyArchive(d));
  assert.equal(s.equity,200);assert.equal(s.initialCapital,100);assert.equal(s.netInvested,200);
  assert.equal(s.pnl,0);assert.equal(s.return,0);assert.equal(s.maxDrawdown,0);
  assert.equal(s.meanDailyTurnover,0);assert.equal(s.fees,0);assert.equal(s.hhi,null);assert.equal(s.effectiveCount,null);
  assert.equal(e.winRate,null);assert.equal(e.profitFactor,null);assert.equal(e.payoff,null);assert.equal(e.medianHoldingDays,null);
  const firstDayDeposit=cashAccount();
  for(const day of actual(firstDayDeposit).days){day.equity=String(Number(day.equity)+25);day.cash=day.equity;day.net_contributions=String(Number(day.net_contributions)+25);}
  actual(firstDayDeposit).summary.equity='225';actual(firstDayDeposit).summary.cash='225';
  const first=buildCareerSnapshot(firstDayDeposit);
  assert.equal(first.initialCapital,100);assert.equal(first.years[0].netFlow,125);
});

test('unavailable fund constituents and security classifications remain explicit',()=>{
  const s=buildCareerSnapshot(data);
  near(s.fundWeight,88881.1/791282.78);assert.equal(s.unknownWeight,0);
  const missing=structuredClone(data);delete missing.assets.find(a=>a.symbol==='510300')!.security_type;
  const unknown=buildCareerSnapshot(missing);
  assert.equal(unknown.fundWeight,0);near(unknown.unknownWeight,s.fundWeight);
  near(unknown.directWeight+unknown.unknownWeight+unknown.cash/unknown.equity,1);
});

test('inconsistent snapshots, dates and numeric values fail closed',()=>{
  const changes:((d:DemoData)=>void)[]=[
    d=>{actual(d).days.at(-1)!.cash='0';},
    d=>{actual(d).days[1].date='2025-02-30';},
    d=>{actual(d).days[1].date=actual(d).days[0].date;},
    d=>{actual(d).days.at(-1)!.nav='NaN';},
    d=>{actual(d).days.at(-1)!.drawdown='0';},
    d=>{actual(d).summary.fees=' ';},
    d=>{actual(d).days.at(-1)!.position_count=99;},
    d=>{actual(d).summary.equity='900000';},
    d=>{d.paths.push(structuredClone(actual(d)));}
  ];
  for(const change of changes){const altered=structuredClone(data);change(altered);assert.throws(()=>buildCareerSnapshot(altered));}
});

test('missing, duplicate and off-calendar fills cannot inflate trade statistics',()=>{
  const changes:((d:DemoData)=>void)[]=[
    d=>{actual(d).fills[1].execution_id=actual(d).fills[0].execution_id;},
    d=>{actual(d).fills[0].date='1999-01-01';},
    d=>{actual(d).fills[0].fee='';},
    d=>{actual(d).fills[0].side='UNKNOWN';},
    d=>{actual(d).fills[0].quantity='-100';},
    d=>{actual(d).fills[0].price='Infinity';}
  ];
  for(const change of changes){const altered=structuredClone(data);change(altered);assert.throws(()=>buildCareerSnapshot(altered));}
});

test('stale or internally inconsistent episode results cannot become dashboard values',()=>{
  const changes:((a:EpisodeArchive)=>void)[]=[
    a=>{a.source_fingerprint='other-account';},
    a=>{a.episodes[0].pnl='123';},
    a=>{a.episodes[0].display.pnl='123.00';},
    a=>{a.summary.open_count=99;},
    a=>{a.episodes.find(ep=>ep.status==='open')!.quantity='0';}
  ];
  for(const change of changes){const altered=structuredClone(archive);change(altered);assert.throws(()=>buildCareerEpisodeStats(data,altered));}
});

test('one profitable closed round has a win rate but no invented loss ratio',()=>{
  const d=cashAccount(),p=actual(d);d.assets=[{symbol:'000001',ticker:'sz000001',name:'测试证券',sector:'测试',security_type:'equity'}];
  p.days[0]={...p.days[0],cash:'50',holdings:{'000001':{quantity:'1',market_value:'50'}},position_count:1};
  p.days[1]={...p.days[1],equity:'110',cash:'110',nav:'1.1',period_pnl:'10',net_contributions:'0'};
  p.summary={equity:'110',cash:'110',period_pnl:'10',fees:'0'};
  p.fills=[{date:d.dates[0],ticker:'sz000001',name:'测试证券',side:'BUY',quantity:'1',price:'50',fee:'0',execution_id:'buy'},
    {date:d.dates[1],ticker:'sz000001',name:'测试证券',side:'SELL',quantity:'1',price:'60',fee:'0',execution_id:'sell'}];
  const a=emptyArchive(d);a.execution_binding=p.fills;
  a.summary={episode_count:1,trade_count:2,open_count:0,closed_count:1,pnl:'10',dividend_income:'0'};
  a.episodes=[{id:'test-round',ticker:'sz000001',symbol:'000001',name:'测试证券',round:1,rounds:1,status:'closed',opened_at:d.dates[0],closed_at:d.dates[1],as_of:d.dates[1],currency:'CNY',quantity:'0',market_value:'0',cost_basis:'0',invested_cost:'50',realized_pnl:'10',unrealized_pnl:'0',dividend_income:'0',pnl:'10',display:{pnl:'10.00',realized_pnl:'10.00',unrealized_pnl:'0.00',dividend_income:'0.00'},trade_ids:['buy','sell'],events:p.fills.map(f=>({...f,id:f.execution_id,kind:'trade',label:f.side,position_before:'0',position_after:'0',cash_before:'0',cash_after:'0'}))}];
  const s=buildCareerEpisodeStats(d,a);
  assert.equal(s.winRate,1);assert.equal(s.profitFactor,null);assert.equal(s.payoff,null);assert.equal(s.medianHoldingDays,2);
});
