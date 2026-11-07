import type {DemoData, Fill} from './model';
import type {ResearchScope} from './alignment';

export type EpisodeTrade = {
  id:string; kind:'trade'; date:string; label:string; execution_id:string;
  side:string; quantity:string; price:string; fee:string;
  position_before:string; position_after:string; cash_before:string; cash_after:string;
};
export type EpisodeAction = {
  id:string; kind:'dividend'|'split'; date:string; label:string;
  amount?:string; ex_date?:string; ratio?:string; source_ref:string; note:string;
};
export type InvestmentEpisode = {
  id:string; ticker:string; name:string; symbol:string; round:number; rounds:number;
  status:'open'|'closed'; opened_at:string; closed_at:string|null; as_of:string;
  currency:'CNY'; quantity:string; market_value:string; cost_basis:string; invested_cost:string;
  realized_pnl:string; unrealized_pnl:string; dividend_income:string; pnl:string;
  display:{pnl:string; realized_pnl:string; unrealized_pnl:string; dividend_income:string};
  trade_ids:string[]; events:(EpisodeTrade|EpisodeAction)[];
};
export type EpisodeArchive = {
  schema_version:'investment_episodes.v1'; source_fingerprint:string; demo_data_sha256:string;
  as_of:string; data_tier:string;
  execution_binding:Pick<Fill,'execution_id'|'date'|'ticker'|'side'|'quantity'|'price'|'fee'>[];
  method:{engine:string; adapter:string; formula:string; cost_basis:string; dividend_basis:string; display_rounding:string; source_files:Record<string,string>};
  summary:{episode_count:number; trade_count:number; open_count:number; closed_count:number; pnl:string; dividend_income:string};
  episodes:InvestmentEpisode[];
};
export type EpisodeFilter={status:'all'|'open'|'closed'; year:string; query:string};
const fields=['execution_id','date','ticker','side','quantity','price','fee'] as const;

// The archive is a projection of the same account, never a fallback for another
// account/import or a freshly edited experiment's different actual records.
export function validateEpisodeArchive(raw:unknown, data:DemoData):EpisodeArchive {
  const archive=raw as EpisodeArchive;
  const actual=data.paths.find(p=>p.id==='actual');
  if(!archive||archive.schema_version!=='investment_episodes.v1'||!actual||
      archive.source_fingerprint!==data.source_fingerprint||archive.as_of!==data.dates.at(-1)||
      !Array.isArray(archive.execution_binding)||!Array.isArray(archive.episodes)||
      archive.execution_binding.length!==actual.fills.length){
    throw new Error('投资经历与当前账户版本不一致，请重新载入演示档案。');
  }
  const current=new Map(actual.fills.map(f=>[f.execution_id,f]));
  const bound=new Set<string>();
  for(const binding of archive.execution_binding){
    const fill=current.get(binding.execution_id);
    if(!fill||bound.has(binding.execution_id)||fields.some(k=>binding[k]!==fill[k])){
      throw new Error('成交记录已经变化，需要重新生成投资经历。');
    }
    bound.add(binding.execution_id);
  }
  const seen=new Set<string>();
  const ids=new Set<string>();
  for(const episode of archive.episodes){
    if(ids.has(episode.id)||!['open','closed'].includes(episode.status)||episode.as_of!==archive.as_of||
        (episode.status==='closed')!==Boolean(episode.closed_at)||
        (episode.closed_at&&episode.closed_at<episode.opened_at))throw new Error('投资经历的持仓范围校验未通过。');
    ids.add(episode.id);
    const trades=episode.events.filter((e):e is EpisodeTrade=>e.kind==='trade');
    if(trades.length!==episode.trade_ids.length||!trades.length)throw new Error('投资经历缺少成交依据。');
    for(const [index,id] of episode.trade_ids.entries()){
      const fill=current.get(id), event=trades[index];
      if(!fill||seen.has(id)||event.execution_id!==id||fill.ticker!==episode.ticker||
          fill.date<episode.opened_at||fill.date>(episode.closed_at??episode.as_of)||
          (['date','side','quantity','price','fee'] as const).some(k=>event[k]!==fill[k])){
        throw new Error('投资经历与逐笔成交的对应关系不完整。');
      }
      seen.add(id);
    }
    if(Object.values(episode.display).some(v=>!/^[-]?\d+\.\d{2}$/.test(v)))throw new Error('投资经历金额格式不正确。');
  }
  if(seen.size!==current.size||archive.summary.episode_count!==archive.episodes.length||
      archive.summary.pnl!==actual.summary.period_pnl)throw new Error('投资经历与账户汇总尚未对齐。');
  return archive;
}

export async function loadEpisodeArchive(data:DemoData,signal?:AbortSignal){
  const response=await fetch('/investment-episodes.json',{signal});
  if(!response.ok)throw new Error('投资经历暂时未载入，请重试。');
  return validateEpisodeArchive(await response.json(),data);
}

// Year filtering selects complete, overlapping episodes. It never cuts an
// open position into a new round or changes the financial outcome's cutoff.
export function filterEpisodes(episodes:InvestmentEpisode[],filter:EpisodeFilter){
  const query=filter.query.trim().toLowerCase();
  return episodes.filter(ep=>
    (filter.status==='all'||ep.status===filter.status)&&
    (filter.year==='all'||(ep.opened_at<=`${filter.year}-12-31`&&(ep.closed_at??ep.as_of)>=`${filter.year}-01-01`))&&
    (!query||`${ep.name} ${ep.ticker} ${ep.symbol} ${ep.opened_at} ${ep.closed_at??ep.as_of}`.toLowerCase().includes(query))
  ).sort((a,b)=>b.opened_at.localeCompare(a.opened_at)||a.ticker.localeCompare(b.ticker));
}

export function episodeRange(episode:InvestmentEpisode){
  return {start:episode.opened_at,end:episode.closed_at??episode.as_of};
}

export function episodeDays(episode:InvestmentEpisode){
  const {start,end}=episodeRange(episode);
  return Math.floor((Date.parse(end+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/86400000)+1;
}

// Display projections only. The original ledger owns positions and economics;
// opening a chart must never manufacture fills or borrow another round's trades.
export function episodeMarket(data:DemoData,episode:InvestmentEpisode){
  const {start,end}=episodeRange(episode);
  const actual=data.paths.find(path=>path.id==='actual')!;
  const ids=new Set(episode.trade_ids);
  const labels=new Map(episode.events.filter((e):e is EpisodeTrade=>e.kind==='trade').map(e=>[e.execution_id,e.label]));
  return {
    dates:data.dates.filter(date=>date>=start&&date<=end),
    bars:(data.bars[episode.ticker]??[]).filter(bar=>bar.date>=start&&bar.date<=end),
    fills:actual.fills.filter(fill=>fill.ticker===episode.ticker&&ids.has(fill.execution_id))
      .map(fill=>({...fill,pathIndex:0,pathName:'本人教学操作',label:labels.get(fill.execution_id)})),
    positions:new Map(actual.days.filter(day=>day.date>=start&&day.date<=end)
      .map(day=>[day.date,day.holdings[episode.symbol]?.quantity??'0']))
  };
}

export function episodeScope(data:DemoData,episode:InvestmentEpisode,range?:[string,string],current?:ResearchScope):ResearchScope{
  const full=episodeRange(episode),[start,end]=range??[full.start,full.end];
  if(start<full.start||end>full.end||start>end)throw new Error('所选日期超出这轮投资的范围。');
  const retain=current?.origin==='decision'&&current.instrument_id===episode.ticker;
  const historical=retain&&current.mode==='as_known_then';
  return {
    instrument_id:episode.ticker,start,end,kind:start===end?'candle':'range',
    origin:'decision',focus:retain?current.focus:'personal_review',
    mode:historical?'as_known_then':'hindsight',
    knowledge_at:historical?`${end}T23:59:59+08:00`:`${episode.as_of}T23:59:59+08:00`,
    historical_proof:historical?'public_reconstruction':'hindsight',
    experiment_ref:data.experiment_id
  };
}
