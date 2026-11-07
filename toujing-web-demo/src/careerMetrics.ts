import type {DemoData, Day, Path} from './model.ts';
import {episodeDays, validateEpisodeArchive, type EpisodeArchive, type InvestmentEpisode} from './episodes.ts';

export type CareerHolding = {
  symbol:string; ticker:string; name:string; sector:string;
  kind:'equity'|'fund'|'unknown'; quantity:number; marketValue:number; weight:number;
};
export type CareerYear = {year:string; index:number; pnl:number; netFlow:number; return:number; trades:number};
export type CareerSnapshot = {
  actual:Path; first:Day; last:Day; initialCapital:number;
  equity:number; cash:number; marketValue:number; pnl:number; netInvested:number;
  return:number; maxDrawdown:number; currentDrawdown:number; fees:number;
  meanDailyTurnover:number; tradeCount:number; dayCount:number;
  holdings:CareerHolding[]; hhi:number|null; effectiveCount:number|null;
  maxWeight:number; top3Weight:number; fundWeight:number; directWeight:number; unknownWeight:number;
  sectors:{name:string; weight:number; kind:'equity'|'fund'|'unknown'}[];
  years:CareerYear[];
};
export type CareerEpisodeStats = {
  closed:InvestmentEpisode[]; open:InvestmentEpisode[];
  winCount:number; lossCount:number; flatCount:number;
  winRate:number|null; payoff:number|null; profitFactor:number|null; medianHoldingDays:number|null;
};

const number=(value:unknown,label:string):number=>{
  if((typeof value!=='string'&&typeof value!=='number')||(typeof value==='string'&&!value.trim())||!Number.isFinite(Number(value)))throw new Error(`账户档案缺少有效的${label}。`);
  return Number(value);
};
const close=(a:number,b:number,tolerance=.021)=>Math.abs(a-b)<=tolerance;
const validDate=(value:string)=>{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const time=Date.parse(value+'T00:00:00Z');
  return Number.isFinite(time)&&new Date(time).toISOString().slice(0,10)===value;
};

// Read-only projection of the existing actual account. It never synthesizes
// ledger entries, replaces valuations, or borrows a different strategy's data.
export function buildCareerSnapshot(data:DemoData):CareerSnapshot {
  const actuals=data?.paths?.filter(path=>path.id==='actual'&&path.kind==='actual');
  if(actuals?.length!==1||!data.dates?.length||!Array.isArray(data.assets))throw new Error('缺少完整的本人账户档案。');
  const actual=actuals[0],days=actual.days;
  if(days.length!==data.dates.length||!days.length)throw new Error('账户日期与逐日估值没有对齐。');
  const first=days[0],last=days.at(-1)!;
  const initialCapital=number(first.equity,'期初资产')-number(first.period_pnl,'期初损益')-number(first.net_contributions,'期初资金流');
  const byDate=new Map<string,number>();
  let maxDrawdown=0,peak=1;
  for(const [index,day] of days.entries()){
    if(!validDate(day.date)||day.date!==data.dates[index]||(index>0&&day.date<=days[index-1].date))throw new Error('账户估值日期无效或顺序不一致。');
    const equity=number(day.equity,'逐日资产'),cash=number(day.cash,'逐日现金');
    const pnl=number(day.period_pnl,'逐日损益'),flows=number(day.net_contributions,'逐日资金流');
    const nav=number(day.nav,'单位净值'),drawdown=number(day.drawdown,'净值回撤');
    if(equity<=0||cash<0||nav<=0||drawdown>1e-10||drawdown<=-1)throw new Error('当前看板需要正净资产及有效的现货账户估值。');
    let invested=0;
    for(const holding of Object.values(day.holdings??{})){
      const value=number(holding.market_value,'持仓市值'),quantity=number(holding.quantity,'持仓数量');
      if(value<0||quantity<0||(quantity===0&&value>0))throw new Error('持仓数量或市值不符合当前现货账户口径。');
      invested+=value;
    }
    if(!close(cash+invested,equity)||!close(equity-pnl-flows,initialCapital))throw new Error('现金、持仓和账户损益尚未对齐，暂不展示统计。');
    peak=Math.max(peak,nav);
    if(!close(nav/peak-1,drawdown,1e-8))throw new Error('单位净值与回撤记录不一致。');
    maxDrawdown=Math.min(maxDrawdown,drawdown);
    byDate.set(day.date,equity);
  }
  const equity=number(last.equity,'期末资产'),cash=number(last.cash,'期末现金'),pnl=number(last.period_pnl,'累计损益');
  const netInvested=initialCapital+number(last.net_contributions,'净资金流');
  if(!close(equity-pnl,netInvested))throw new Error('净投入与期末损益没有对齐。');
  for(const [key,value]of Object.entries({equity,cash,period_pnl:pnl})){
    if(!close(number(actual.summary[key],'账户汇总'),value))throw new Error('账户汇总与最新估值不一致。');
  }
  const assets=new Map(data.assets.map(asset=>[asset.symbol,asset]));
  const holdings=Object.entries(last.holdings).filter(([,h])=>number(h.quantity,'持仓数量')>0).map(([symbol,holding]):CareerHolding=>{
    const asset=assets.get(symbol),securityType=asset?.security_type;
    const kind=securityType==='equity'?'equity':['etf','fund'].includes(securityType??'')?'fund':'unknown';
    const marketValue=number(holding.market_value,'持仓市值');
    return {symbol,ticker:asset?.ticker??symbol,name:asset?.name??symbol,sector:asset?.sector||'未分类',kind,
      quantity:number(holding.quantity,'持仓数量'),marketValue,weight:marketValue/equity};
  }).sort((a,b)=>b.marketValue-a.marketValue||a.symbol.localeCompare(b.symbol));
  if(last.position_count!==holdings.length)throw new Error('持仓数量与明细尚未对齐。');
  const marketValue=holdings.reduce((sum,h)=>sum+h.marketValue,0);
  const hhi=marketValue>0?holdings.reduce((sum,h)=>sum+(h.marketValue/marketValue)**2,0):null;
  const sectors=new Map<string,{name:string;weight:number;kind:CareerHolding['kind']}>();
  for(const h of holdings){const key=h.kind+':'+h.sector;const prior=sectors.get(key);sectors.set(key,{name:h.sector,kind:h.kind,weight:(prior?.weight??0)+h.weight});}
  const ids=new Set<string>(),tradedByDate=new Map<string,number>(),tradesByYear=new Map<string,number>();
  let fees=0;
  for(const fill of actual.fills){
    const price=number(fill.price,'成交价'),quantity=number(fill.quantity,'成交数量'),fee=number(fill.fee,'成交费用');
    if(!fill.execution_id||ids.has(fill.execution_id)||!byDate.has(fill.date)||!['BUY','SELL'].includes(fill.side)||price<=0||quantity<=0||fee<0)throw new Error('成交记录不完整，无法计算换手与费用。');
    ids.add(fill.execution_id);fees+=fee;
    tradedByDate.set(fill.date,(tradedByDate.get(fill.date)??0)+price*quantity);
    const year=fill.date.slice(0,4);tradesByYear.set(year,(tradesByYear.get(year)??0)+1);
  }
  if(!close(fees,number(actual.summary.fees,'费用汇总')))throw new Error('成交费用与账户汇总不一致。');
  const meanDailyTurnover=days.reduce((sum,day)=>sum+(tradedByDate.get(day.date)??0)/byDate.get(day.date)!,0)/days.length;
  const yearEnds=new Map<string,number>();days.forEach((day,index)=>yearEnds.set(day.date.slice(0,4),index));
  let previousPnl=0,previousFlow=0,previousNav=1;
  const years=Array.from(yearEnds,([year,index]):CareerYear=>{
    const day=days[index],endPnl=number(day.period_pnl,'年度损益'),endFlow=number(day.net_contributions,'年度资金流'),endNav=number(day.nav,'年度净值');
    const item={year,index,pnl:endPnl-previousPnl,netFlow:endFlow-previousFlow,return:endNav/previousNav-1,trades:tradesByYear.get(year)??0};
    previousPnl=endPnl;previousFlow=endFlow;previousNav=endNav;return item;
  });
  return {actual,first,last,initialCapital,equity,cash,marketValue,pnl,netInvested,return:number(last.nav,'单位净值')-1,
    maxDrawdown,currentDrawdown:number(last.drawdown,'当前回撤'),fees,meanDailyTurnover,tradeCount:actual.fills.length,dayCount:days.length,
    holdings,hhi,effectiveCount:hhi?1/hhi:null,maxWeight:holdings[0]?.weight??0,top3Weight:holdings.slice(0,3).reduce((sum,h)=>sum+h.weight,0),
    fundWeight:holdings.filter(h=>h.kind==='fund').reduce((sum,h)=>sum+h.weight,0),directWeight:holdings.filter(h=>h.kind==='equity').reduce((sum,h)=>sum+h.weight,0),
    unknownWeight:holdings.filter(h=>h.kind==='unknown').reduce((sum,h)=>sum+h.weight,0),sectors:Array.from(sectors.values()).sort((a,b)=>b.weight-a.weight),years};
}

export function buildCareerEpisodeStats(data:DemoData,raw:EpisodeArchive):CareerEpisodeStats {
  const archive=validateEpisodeArchive(raw,data);
  const snapshot=buildCareerSnapshot(data);
  const open=archive.episodes.filter(ep=>ep.status==='open'),closed=archive.episodes.filter(ep=>ep.status==='closed');
  const holdings=new Map(snapshot.holdings.map(h=>[h.symbol,h]));
  if(open.length!==holdings.size||archive.summary.open_count!==open.length||archive.summary.closed_count!==closed.length)throw new Error('投资经历的持仓状态数量不一致。');
  const openSymbols=new Set<string>();
  let totalPnl=0;
  for(const ep of archive.episodes){
    const value=number(ep.market_value,'经历市值'),cost=number(ep.cost_basis,'经历成本'),quantity=number(ep.quantity,'经历数量');
    const realized=number(ep.realized_pnl,'已实现损益'),unrealized=number(ep.unrealized_pnl,'浮动损益'),dividend=number(ep.dividend_income,'分红'),pnl=number(ep.pnl,'经历损益');
    if(!close(value-cost,unrealized)||!close(realized+unrealized+dividend,pnl))throw new Error('投资经历损益组成不一致。');
    for(const key of ['pnl','realized_pnl','unrealized_pnl','dividend_income'] as const){if(!close(number(ep.display[key],'显示金额'),number(ep[key],'原始金额'),.0051))throw new Error('投资经历的显示金额与原始记录不一致。');}
    if(!validDate(ep.opened_at)||!validDate(ep.closed_at??ep.as_of)||ep.opened_at>(ep.closed_at??ep.as_of))throw new Error('投资经历日期不完整。');
    if(ep.status==='open'){
      const h=holdings.get(ep.symbol);
      if(!h||openSymbols.has(ep.symbol)||!close(h.marketValue,value)||!close(h.quantity,quantity,1e-8))throw new Error('当前持仓与投资经历没有对齐。');
      openSymbols.add(ep.symbol);
    }else if(quantity!==0||Math.abs(value)>.005||Math.abs(cost)>.005)throw new Error('已结束经历仍有未清持仓。');
    totalPnl+=pnl;
  }
  if(!close(totalPnl,snapshot.pnl))throw new Error('各轮投资经历与账户总损益没有对齐。');
  const wins=closed.filter(ep=>number(ep.pnl,'净损益')>0),losses=closed.filter(ep=>number(ep.pnl,'净损益')<0);
  const gain=wins.reduce((sum,ep)=>sum+Number(ep.pnl),0),loss=-losses.reduce((sum,ep)=>sum+Number(ep.pnl),0);
  const durations=closed.map(episodeDays).sort((a,b)=>a-b),middle=Math.floor(durations.length/2);
  return {closed,open,winCount:wins.length,lossCount:losses.length,flatCount:closed.length-wins.length-losses.length,
    winRate:closed.length?wins.length/closed.length:null,profitFactor:loss>0?gain/loss:null,
    payoff:wins.length&&losses.length?(gain/wins.length)/(loss/losses.length):null,
    medianHoldingDays:durations.length?(durations.length%2?durations[middle]:(durations[middle-1]+durations[middle])/2):null};
}
