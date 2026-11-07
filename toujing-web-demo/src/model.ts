export type Bar={date:string;open:string;high:string;low:string;close:string};
export type Fill={date:string;ticker:string;name:string;side:string;quantity:string;price:string;fee:string;execution_id:string;note?:string};
export type Day={date:string;equity:string;cash:string;nav:string;drawdown:string;net_contributions:string;holdings:Record<string,{quantity:string;market_value:string;cost_basis?:string}>;position_count:number;period_pnl:string};
export type Rule={name:string;entry:string;window:number;max_weight:number;initial_weight:number;add_drop:number;take_profit:number;stop_loss:number;cooldown:number;max_positions:number;partial_fraction:number;[key:string]:unknown};
export type Path={id:string;name:string;kind:string;days:Day[];fills:Fill[];summary:Record<string,string>;max_drawdown:number;return:string;rule:Rule|null;rule_card:{id:string;label:string;value:string}[]};
export type EventItem={id:string;title:string;date:string;category:string;url:string;ticker:string|null;published_at?:string};
export type DemoData={dates:string[];source_fingerprint:string;experiment_id:string;method_version:string;paths:Path[];bars:Record<string,Bar[]>;assets:{ticker:string;name:string;symbol:string;sector:string;security_type?:string}[];events:EventItem[];lifetime:{summary:Record<string,string|number>;years:{year:string;equity:string;pnl:string;net_flow:string;return:string;trades:number}[];facts:{id:string;title:string;value:number;unit:string;evidence_refs:string[];counterexamples:string[]}[];adds:{date:string;name:string;ticker:string;move_from_previous:number}[]};formulas:Record<string,string>;sources:{file:string;url:string;sha256:string;retrieved_at:string}[];assumptions:string[]};
export const COLORS=['#9fddff','#6ee0be','#ffb17e','#b7a2ff','#f399b0','#e1d88a'];
export const LABELS=['我的实际操作','个人行为镜像','我的规则变体','长期持有方法','社区趋势策略','等额持有基准'];
export const money=(n:number|string,digits=2)=>Number(n).toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits});
export const wan=(n:number|string,digits=2)=>(Number(n)/10000).toFixed(digits);
export const pct=(n:number|string,digits=1)=>`${Number(n)>=0?'+':''}${(Number(n)*100).toFixed(digits)}%`;
export const dateLabel=(s:string)=>s.replaceAll('-','.');
export function nearestIndex(dates:string[],date:string){let lo=0,hi=dates.length-1;while(lo<hi){const m=Math.ceil((lo+hi)/2);if(dates[m]<=date)lo=m;else hi=m-1;}return lo;}
export function linePath(values:number[],width:number,height:number,min:number,max:number){return values.map((v,i)=>`${i?'L':'M'}${(i/(values.length-1||1)*width).toFixed(2)},${(height-(v-min)/(max-min||1)*height).toFixed(2)}`).join(' ');}
export function safeLoad<T>(key:string,fallback:T):T{try{return JSON.parse(localStorage.getItem('tj-demo-'+key)||'null')??fallback;}catch{return fallback;}}
export function save(key:string,value:unknown){try{localStorage.setItem('tj-demo-'+key,JSON.stringify(value));}catch{/* Browser private-mode persistence is optional. */}}
export function download(name:string,content:string,type='application/json'){const u=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
export function parseRule(text:string,base?:Partial<Rule>):Rule{
 const r:Rule={name:'我的长期投资规则',entry:'dip',window:60,max_weight:.2,initial_weight:.1,add_drop:.1,take_profit:.3,stop_loss:.2,cooldown:60,max_positions:5,partial_fraction:.5,...base};
 if(/趋势|突破|均线上方/.test(text))r.entry='trend';if(/长期持有|一直持有|不卖/.test(text))r.entry='hold';
 const w=text.match(/(?:上限|最多|不超过|仓位)[^\d]{0,5}(\d+(?:\.\d+)?)\s*[%％]/);if(w)r.max_weight=Math.min(.8,Math.max(.05,Number(w[1])/100));
 if(/两成|二成/.test(text))r.max_weight=.2;if(/三成/.test(text))r.max_weight=.3;
 const profit=text.match(/(?:盈利|上涨|止盈)[^\d]{0,4}(\d+(?:\.\d+)?)\s*[%％]/);if(profit)r.take_profit=Number(profit[1])/100;
 const drop=text.match(/(?:下跌|回落|跌)[^\d]{0,4}(\d+(?:\.\d+)?)\s*[%％]/);if(drop)r.add_drop=Number(drop[1])/100;
 const ma=text.match(/(\d+)\s*(?:日|天)均线/);if(ma)r.window=Math.max(5,Math.min(250,Number(ma[1])));
 if(/不加仓|不追加/.test(text))r.add_drop=0;if(/一半|分两次|50[%％]/.test(text))r.partial_fraction=.5;
 if(!['dip','trend','hold'].includes(r.entry))throw new Error('入场规则必须为分批、趋势或持有');
 const bounds:Record<string,[number,number]>={window:[5,250],max_weight:[.01,1],initial_weight:[.01,1],add_drop:[0,1],take_profit:[0,5],stop_loss:[0,1],cooldown:[0,250],max_positions:[1,20],partial_fraction:[.01,1]};
 for(const [key,[min,max]]of Object.entries(bounds)){const v=r[key];if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)throw new Error(`规则参数 ${key} 超出支持范围`);}
 if(!Number.isInteger(r.window)||!Number.isInteger(r.cooldown)||!Number.isInteger(r.max_positions))throw new Error('天数与持仓数量必须为整数');
 if(typeof r.name!=='string'||!r.name.trim())throw new Error('规则需要一个名称');
 return r;
}
// Isolated, price-only teaching experiment. Integer-fen cash; next-session execution.
// It never writes to the product ledger and does not replace the archived six-path run.
export function simulateRule(d:DemoData,ticker:string,r:Rule):Path{
 r=parseRule('',r);if(!d.bars[ticker]?.length)throw new Error('该证券没有本地实验行情');
 const bars=d.bars[ticker],map=new Map(bars.map(b=>[b.date,b]));let cash=50000000,qty=0,cost=0,lastBuy=0,lastTrade=-999,pending:'BUY'|'SELL'|null=null,nav=1,prevEq=50000000,prevFlow=0,maxNav=1,feeSum=0;
 const days:Day[]=[],fills:Fill[]=[];const closes:number[]=[];let lastPrice=0;
 d.dates.forEach((date,i)=>{const b=map.get(date);const totalFlow=Math.round(Number(d.paths[0].days[i].net_contributions)*100);const flow=totalFlow-prevFlow;prevFlow=totalFlow;
  if(b){lastPrice=Math.round(Number(b.close)*100);const open=Math.round(Number(b.open)*100);
   if(pending==='BUY'){const eq=cash+qty*open;const budget=Math.min(cash,Math.round(eq*r.initial_weight),Math.max(0,Math.round(eq*r.max_weight)-qty*open));let q=Math.floor(budget/open/100)*100;let fee=Math.max(500,Math.round(q*open*.0003));while(q>0&&q*open+fee>cash){q-=100;fee=Math.max(500,Math.round(q*open*.0003));}
    if(q>0){cash-=q*open+fee;qty+=q;cost+=q*open+fee;lastBuy=open;lastTrade=i;feeSum+=fee;fills.push({date,ticker,name:d.assets.find(a=>a.ticker===ticker)?.name||ticker,side:'BUY',quantity:String(q),price:(open/100).toFixed(2),fee:(fee/100).toFixed(2),execution_id:`local-${i}-b`});}}
   if(pending==='SELL'&&qty>0&&i>lastTrade){const q=Math.min(qty,Math.max(100,Math.floor(qty*r.partial_fraction/100)*100));const fee=Math.max(500,Math.round(q*open*.0003))+Math.round(q*open*.001);cash+=q*open-fee;cost=Math.round(cost*(qty-q)/qty);qty-=q;feeSum+=fee;lastTrade=i;fills.push({date,ticker,name:d.assets.find(a=>a.ticker===ticker)?.name||ticker,side:'SELL',quantity:String(q),price:(open/100).toFixed(2),fee:(fee/100).toFixed(2),execution_id:`local-${i}-s`});}
   pending=null;closes.push(lastPrice);if(closes.length>=r.window){const ma=closes.slice(-r.window).reduce((a,b)=>a+b,0)/r.window;const eligible=r.entry==='hold'||(r.entry==='trend'?lastPrice>ma:lastPrice<ma);
    if(!qty&&eligible)pending='BUY';else if(qty&&r.entry!=='hold'){if((lastPrice/(cost/qty)-1>=r.take_profit||(r.stop_loss>0&&lastPrice/(cost/qty)-1<=-r.stop_loss))&&i-lastTrade>20)pending='SELL';else if(r.add_drop>0&&lastPrice<lastBuy*(1-r.add_drop)&&i-lastTrade>=r.cooldown)pending='BUY';}}}
  cash+=flow;const eq=cash+qty*lastPrice;nav*=prevEq>0?(eq-flow)/prevEq:1;maxNav=Math.max(nav,maxNav);prevEq=eq;
  days.push({date,equity:(eq/100).toFixed(2),cash:(cash/100).toFixed(2),nav:String(nav),drawdown:String(nav/maxNav-1),net_contributions:(totalFlow/100).toFixed(2),holdings:qty?{[ticker.slice(2)]:{quantity:String(qty),market_value:(qty*lastPrice/100).toFixed(2)}}:{},position_count:qty?1:0,period_pnl:((eq-50000000-totalFlow)/100).toFixed(2)});
 });
 return{id:'local-rule',name:r.name,kind:'custom',rule:r,days,fills,summary:{equity:days.at(-1)!.equity,cash:days.at(-1)!.cash,fees:(feeSum/100).toFixed(2)},return:String(nav-1),max_drawdown:Math.min(...days.map(x=>Number(x.drawdown))),rule_card:[]};
}
export function csvRows(text:string){
 const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines.length<2)throw new Error('请提供表头和至少一行交易记录');
 const heads=lines[0].split(',').map(s=>s.trim());const required=['date','ticker','side','quantity','price'];if(!required.every(k=>heads.includes(k)))throw new Error('CSV 需要 date,ticker,side,quantity,price 五列');
 return lines.slice(1).filter(Boolean).map((line,i)=>{const cells=line.split(',');const row=Object.fromEntries(heads.map((h,j)=>[h,(cells[j]||'').trim()]));const parsed=new Date(row.date+'T00:00:00Z');const dateValid=/^\d{4}-\d{2}-\d{2}$/.test(row.date)&&Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===row.date;if(!dateValid||!['BUY','SELL'].includes(row.side)||!row.ticker||Number(row.quantity)<=0||Number(row.price)<=0||!Number.isFinite(Number(row.price))||!Number.isFinite(Number(row.quantity)))throw new Error(`第 ${i+2} 行的日期、方向或数值不正确`);return row;});
}
