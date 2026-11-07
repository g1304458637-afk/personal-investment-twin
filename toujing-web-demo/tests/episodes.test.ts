import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {episodeDays,episodeRange,episodeMarket,episodeScope,filterEpisodes,validateEpisodeArchive,type EpisodeArchive} from '../src/episodes.ts';
import {replayBounds} from '../src/replayWindow.ts';
import type {DemoData} from '../src/model.ts';

const demoBytes=readFileSync(new URL('../public/demo-data.json',import.meta.url));
const data=JSON.parse(demoBytes.toString()) as DemoData;
const archive=JSON.parse(readFileSync(new URL('../public/investment-episodes.json',import.meta.url),'utf8')) as EpisodeArchive;

test('episode archive binds to the exact same demo and covers all executions once',()=>{
  assert.equal(archive.demo_data_sha256,createHash('sha256').update(demoBytes).digest('hex'));
  assert.equal(validateEpisodeArchive(archive,data),archive);
  assert.equal(archive.episodes.length,13);
  assert.equal(archive.summary.open_count,5);
  assert.equal(archive.summary.closed_count,8);
  const ids=archive.episodes.flatMap(e=>e.trade_ids);
  assert.equal(ids.length,54);
  assert.equal(new Set(ids).size,54);
  assert.deepEqual([...ids].sort(),data.paths[0].fills.map(f=>f.execution_id).sort());
});

test('re-entry is a separate round; partial sells stay in the original round',()=>{
  const midea=archive.episodes.filter(e=>e.ticker==='sz000333');
  assert.deepEqual(midea.map(e=>[e.round,e.opened_at,e.closed_at]),[
    [1,'2020-02-07','2020-11-23'],[2,'2021-03-24','2022-11-07'],[3,'2023-03-20',null]
  ]);
  assert.deepEqual(midea[0].events.filter(e=>e.kind==='trade').map(e=>e.label),['建仓','加仓','减仓','清仓']);
  assert.equal(midea[0].display.pnl,'32124.81');
  assert.equal(midea[1].display.pnl,'-33409.96');
  assert.equal(midea[2].display.pnl,'39431.93');
});

test('year filter returns complete overlapping episodes and keeps the original cutoff',()=>{
  const matches=filterEpisodes(archive.episodes,{status:'all',year:'2022',query:'美的'});
  assert.equal(matches.length,1);
  assert.equal(matches[0].opened_at,'2021-03-24');
  assert.equal(matches[0].trade_ids.length,4);
  assert.deepEqual(episodeRange(matches[0]),{start:'2021-03-24',end:'2022-11-07'});
  const holdings=filterEpisodes(archive.episodes,{status:'open',year:'2020',query:'长江'});
  assert.equal(holdings.length,1);
  assert.equal(holdings[0].as_of,'2025-12-31');
  assert.equal(holdings[0].trade_ids.length,7);
  assert.equal(episodeRange(holdings[0]).end,'2025-12-31');
});

test('search, status and reverse chronological ordering work together',()=>{
  const result=filterEpisodes(archive.episodes,{status:'closed',year:'all',query:' 000333 '});
  assert.deepEqual(result.map(e=>e.round),[2,1]);
  assert.equal(filterEpisodes(archive.episodes,{status:'all',year:'all',query:'2020-02-07'}).length,1);
  assert.equal(filterEpisodes(archive.episodes,{status:'all',year:'all',query:'不存在'}).length,0);
  const all=filterEpisodes(archive.episodes,{status:'all',year:'all',query:''});
  assert.equal(all[0].opened_at,'2025-02-17');
});

test('company actions remain independent of fills and exact source prices survive',()=>{
  const catl=archive.episodes.find(e=>e.ticker==='sz300750'&&e.round===1)!;
  assert(catl.events.some(e=>e.kind==='split'&&e.date==='2023-04-26'));
  assert.equal(catl.trade_ids.length,4);
  const etf=archive.episodes.find(e=>e.ticker==='sh510300')!;
  const first=etf.events.find(e=>e.kind==='trade')!;
  assert.equal(first.kind,'trade');
  if(first.kind==='trade')assert.equal(first.price,'4.134');
  assert(archive.episodes.every(e=>e.events.every((x,i)=>i===0||x.date>=e.events[i-1].date)));
});

test('changed actual account inputs and stale archives cannot use old financial results',()=>{
  for(const change of [
    (d:DemoData)=>{d.source_fingerprint='other-account';},
    (d:DemoData)=>{d.paths[0].fills[0].price='4.135';},
    (d:DemoData)=>{d.paths[0].fills.pop();},
    (d:DemoData)=>{d.paths[0].summary.period_pnl='100000';},
    (d:DemoData)=>{d.dates.pop();},
  ]){
    const altered=structuredClone(data);change(altered);
    assert.throws(()=>validateEpisodeArchive(archive,altered));
  }
  const variantOnly=structuredClone(data);variantOnly.paths[2].name='新规则';
  assert.equal(validateEpisodeArchive(archive,variantOnly),archive);
});

test('missing, duplicate, or mis-scoped episode trades fail validation',()=>{
  for(const change of [
    (a:EpisodeArchive)=>{a.episodes[0].trade_ids.pop();},
    (a:EpisodeArchive)=>{a.episodes[0].ticker='sz000333';},
    (a:EpisodeArchive)=>{a.episodes[0].opened_at='2024-01-01';},
    (a:EpisodeArchive)=>{a.episodes[0].status='closed';},
    (a:EpisodeArchive)=>{a.execution_binding[1]=a.execution_binding[0];},
    (a:EpisodeArchive)=>{a.episodes[0].display.pnl='NaN';},
  ]){
    const altered=structuredClone(archive);change(altered);
    assert.throws(()=>validateEpisodeArchive(altered,data));
  }
});

test('holding duration and range are independent of local timezone and filters',()=>{
  const firstMidea=archive.episodes.find(e=>e.ticker==='sz000333'&&e.round===1)!;
  assert.equal(episodeDays(firstMidea),291);
  assert.deepEqual(episodeRange(firstMidea),{start:'2020-02-07',end:'2020-11-23'});
  assert.deepEqual(episodeRange(archive.episodes.find(e=>e.ticker==='sz000333'&&e.round===3)!),{start:'2023-03-20',end:'2025-12-31'});
});

test('a stock chart shows only this episode, preserving original prices and ledger holdings',()=>{
  for(const episode of archive.episodes){
    const market=episodeMarket(data,episode),range=episodeRange(episode);
    assert.deepEqual(market.fills.map(f=>f.execution_id),episode.trade_ids);
    assert(market.fills.every(f=>f.ticker===episode.ticker));
    assert(market.dates.every(date=>date>=range.start&&date<=range.end));
    assert(market.bars.every(bar=>bar.date>=range.start&&bar.date<=range.end));
    for(const fill of market.fills){
      const original=data.paths[0].fills.find(f=>f.execution_id===fill.execution_id)!;
      assert.equal(fill.price,original.price);
      assert.equal(fill.quantity,original.quantity);
    }
    for(const day of data.paths[0].days.filter(d=>d.date>=range.start&&d.date<=range.end)){
      assert.equal(market.positions.get(day.date),day.holdings[episode.symbol]?.quantity??'0');
    }
  }
  const firstMidea=archive.episodes.find(e=>e.ticker==='sz000333'&&e.round===1)!;
  assert.deepEqual(episodeMarket(data,firstMidea).fills.map(f=>f.label),['建仓','加仓','减仓','清仓']);
});

test('selection passes the episode symbol and exact date range without old trade or replay identities',()=>{
  const episode=archive.episodes.find(e=>e.ticker==='sz000333'&&e.round===1)!;
  const initial=episodeScope(data,episode);
  assert.equal(initial.instrument_id,'sz000333');
  assert.equal(initial.start,'2020-02-07');
  assert.equal(initial.end,'2020-11-23');
  const range=episodeScope(data,episode,['2020-06-01','2020-07-20'],{
    ...initial,focus:'public_price',execution_id:'old-execution',path_ids:['variant'],kind:'execution'
  });
  assert.equal(range.focus,'public_price');
  assert.equal(range.kind,'range');
  assert.equal(range.start,'2020-06-01');
  assert.equal(range.end,'2020-07-20');
  assert.equal(range.execution_id,undefined);
  assert.equal(range.path_ids,undefined);
  assert.equal(episodeScope(data,episode,['2020-06-01','2020-06-01']).kind,'candle');
  assert.throws(()=>episodeScope(data,episode,['2020-01-01','2020-06-01']));
  assert.throws(()=>episodeScope(data,episode,['2020-06-01','2021-01-01']));
  assert.throws(()=>episodeScope(data,episode,['2020-07-20','2020-06-01']));
});

test('historical selection keeps an explicit cutoff and does not inherit another company context',()=>{
  const episode=archive.episodes.find(e=>e.ticker==='sz000333'&&e.round===1)!;
  const scope=episodeScope(data,episode);
  const historical=episodeScope(data,episode,['2020-06-01','2020-07-20'],{...scope,mode:'as_known_then'});
  assert.equal(historical.knowledge_at,'2020-07-20T23:59:59+08:00');
  assert.equal(historical.historical_proof,'public_reconstruction');
  const switched=episodeScope(data,episode,undefined,{...historical,instrument_id:'sh600036',focus:'public_price'});
  assert.equal(switched.mode,'hindsight');
  assert.equal(switched.focus,'personal_review');
  assert.equal(switched.instrument_id,'sz000333');
});

test('comparison is bounded to the selected episode, including weekend endpoints',()=>{
  for(const episode of archive.episodes){
    const range=episodeRange(episode),bounds=replayBounds(data.dates,range);
    assert.deepEqual(data.dates.slice(bounds.start,bounds.end+1),episodeMarket(data,episode).dates);
    assert(data.dates[bounds.start]>=range.start);
    assert(data.dates[bounds.end]<=range.end);
  }
  const dates=['2020-02-07','2020-02-10','2020-02-11','2020-02-12'];
  assert.deepEqual(replayBounds(dates,{start:'2020-02-08',end:'2020-02-11'}),{start:1,end:2});
  assert.deepEqual(replayBounds(dates),{start:0,end:3});
  assert.throws(()=>replayBounds(dates,{start:'2020-02-08',end:'2020-02-09'}));
  assert.throws(()=>replayBounds(dates,{start:'2020-02-12',end:'2020-02-07'}));
  assert.throws(()=>replayBounds([]));
});
