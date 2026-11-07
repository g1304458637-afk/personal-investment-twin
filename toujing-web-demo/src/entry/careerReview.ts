import type { DemoData, Fill } from '../model.ts';

export type CareerReview = {
 start:string; end:string; tradeCount:number; assetCount:number;
 years:{year:string;index:number;title:string;subtitle:string;narration:string;pnl:number;netFlow:number}[];
 equity:number; netInvested:number; pnl:number; maxDrawdown:number; drawdownDate:string;
 addCount:number; lowerAddCount:number; counterCount:number; headline:string; summary:string;
 findings:{id:string;title:string;body:string;metric:string;unit:string;evidence:{date:string;label:string;detail:string;kind:'support'|'counter'|'account';executionId?:string}[]}[];
 sourceFingerprint:string;
};

const number = (value:unknown, label:string):number => {
 if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) throw new Error(`档案缺少有效的${label}`);
 return Number(value);
};
const close = (a:number,b:number) => Math.abs(a-b)<0.011;
const amount = (n:number) => `${n < 0 ? '−' : ''}${Math.abs(n).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}元`;
const rate = (n:number) => `${n < 0 ? '−' : '+'}${(Math.abs(n)*100).toFixed(2)}%`;

export function buildCareerReview(data:DemoData):CareerReview {
 const actual = data?.paths?.find(p=>p.kind==='actual');
 const dates = data?.dates;
 if (!actual || !Array.isArray(dates) || !dates.length || !actual.days?.length || !actual.fills || !data.lifetime || !Array.isArray(data.lifetime.years) || !Array.isArray(data.lifetime.adds) || !data.source_fingerprint || !Array.isArray(data.assets) || !data.assets.length) throw new Error('投资档案不完整：缺少实际路径、日期或来源');
 if (dates.length!==actual.days.length || dates.some((d,i)=>!/^\d{4}-\d{2}-\d{2}$/.test(d) || actual.days[i]?.date!==d || (i>0 && dates[i-1]>=d))) throw new Error('投资档案日期与实际路径不一致');
 const dateSet=new Set(dates);
 const ids=new Set<string>();
 for (const f of actual.fills) {
  if (!dateSet.has(f.date) || !f.execution_id || ids.has(f.execution_id) || !f.ticker || !f.name || !['BUY','SELL'].includes(f.side) || number(f.price,'成交价')<=0) throw new Error('投资档案成交记录无效或日期不一致');
  ids.add(f.execution_id);
 }
 const days=actual.days, first=days[0], last=days[days.length-1];
 const equity=number(last.equity,'期末资产'), pnl=number(last.period_pnl,'期末损益');
 const netInvested=equity-pnl;
 const expectedInvested=number(first.equity,'期初资产')+number(last.net_contributions,'期末净资金流')-number(first.net_contributions,'期初净资金流');
 if (!close(netInvested,expectedInvested)) throw new Error('投资档案资金投入与损益不一致');
 let drawdownDate=first.date, maxDrawdown=Infinity;
 for (const day of days) { const dd=number(day.drawdown,'净值回撤'); if(dd<maxDrawdown){maxDrawdown=dd;drawdownDate=day.date;} }
 const yearSet=new Set<string>();
 const years=data.lifetime.years.map(y=>{
  if (!/^\d{4}$/.test(y.year) || yearSet.has(y.year)) throw new Error('投资档案年度记录无效');
  yearSet.add(y.year);
  const reverseIndex=[...dates].reverse().findIndex(d=>d.startsWith(y.year+'-'));
  const index=reverseIndex<0 ? -1 : dates.length-1-reverseIndex;
  if(index<0) throw new Error('投资档案年度与日期不一致');
  const previous=[...days].reverse().find(d=>d.date<y.year+'-01-01');
  const basePnl=previous ? number(previous.period_pnl,'年度起始损益') : 0;
  const baseFlow=previous ? number(previous.net_contributions,'年度起始资金流') : number(first.net_contributions,'期初资金流');
  const yearPnl=number(y.pnl,'年度损益'), netFlow=number(y.net_flow,'年度资金流');
  if(!close(yearPnl,number(days[index].period_pnl,'年度末损益')-basePnl) || !close(netFlow,number(days[index].net_contributions,'年度末资金流')-baseFlow)) throw new Error('投资档案年度损益或资金流不一致');
  const subtitle=`年度损益${amount(yearPnl)}，净资金流${amount(netFlow)}`;
  return {year:y.year,index,title:`${y.year} 年`,subtitle,narration:subtitle+'。',pnl:yearPnl,netFlow};
 });
 if (!years.length || new Set(dates.map(d=>d.slice(0,4))).size!==years.length || years.some((y,i)=>i>0 && years[i-1].index>=y.index)) throw new Error('投资档案年度记录不完整');
 const fillById=new Map(actual.fills.map(f=>[f.execution_id,f]));
 const adds=data.lifetime.adds as (typeof data.lifetime.adds[number] & {execution_id?:string})[];
 const used=new Set<string>();
 const evidence=adds.map(add=>{
  const f=add.execution_id && fillById.get(add.execution_id);
  if (!f || used.has(f.execution_id) || f.side!=='BUY' || f.date!==add.date || f.ticker!==add.ticker || f.name!==add.name || !Number.isFinite(add.move_from_previous)) throw new Error('连续买入记录缺少匹配的成交证据');
  used.add(f.execution_id);
  const pos=actual.fills.indexOf(f);
  const previous=actual.fills.slice(0,pos).reverse().find((x:Fill)=>x.ticker===f.ticker && x.side==='BUY');
  if (previous && previous.date<=f.date && Math.abs(number(f.price,'成交价')/number(previous.price,'前次成交价')-1-add.move_from_previous)<0.000001) {
   return {date:f.date,label:f.name,detail:`本次买入价 ${f.price} 元；上次买入价 ${previous.price} 元（${previous.date}），变化 ${rate(add.move_from_previous)}`,kind:(add.move_from_previous<0?'support':'counter') as 'support'|'counter',executionId:f.execution_id};
  }
  return {date:f.date,label:f.name,detail:`本次买入价 ${f.price} 元；档案记录较上次买入价变化 ${rate(add.move_from_previous)}`,kind:(add.move_from_previous<0?'support':'counter') as 'support'|'counter',executionId:f.execution_id};
 });
 const addCount=evidence.length, lowerAddCount=evidence.filter(e=>e.kind==='support').length, counterCount=addCount-lowerAddCount;
 const headline=addCount ? `${addCount} 次连续买入中，${lowerAddCount} 次价格低于前次` : '连续买入记录不足，暂无法形成价格比较';
 return {start:dates[0],end:dates.at(-1)!,tradeCount:actual.fills.length,assetCount:new Set(data.assets.map(a=>a.ticker)).size,years,equity,netInvested,pnl,maxDrawdown,drawdownDate,addCount,lowerAddCount,counterCount,headline,summary:`期末资产 ${amount(equity)}，其中净投入 ${amount(netInvested)}，累计损益 ${amount(pnl)}。`,sourceFingerprint:data.source_fingerprint,
  findings:[
   {id:'adds',title:'连续买入价格',body:addCount?`档案列出的 ${addCount} 次连续买入中，${lowerAddCount} 次价格低于前次，${counterCount} 次未低于前次；这不是下跌机会率。`:'档案没有连续买入记录，无法比较。',metric:`${lowerAddCount}/${addCount}`,unit:'次',evidence},
   {id:'drawdown',title:'最大净值回撤',body:`资金流调整后的单位净值最大回撤为 ${rate(maxDrawdown)}，发生于 ${drawdownDate}。`,metric:rate(maxDrawdown),unit:'',evidence:[{date:drawdownDate,label:'最大净值回撤',detail:`当日单位净值回撤 ${rate(maxDrawdown)}`,kind:'account'}]},
   {id:'capital',title:'资金投入与损益',body:`期末资产 ${amount(equity)} = 净投入 ${amount(netInvested)} + 累计损益 ${amount(pnl)}。`,metric:amount(pnl),unit:'',evidence:[{date:last.date,label:'期末账户',detail:`净投入 ${amount(netInvested)}；累计损益 ${amount(pnl)}；期末资产 ${amount(equity)}`,kind:'account'}]}
  ]};
}
