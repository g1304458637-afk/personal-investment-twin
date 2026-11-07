import {useEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {ArrowRight, ChevronRight, Info, MessageCircle, RotateCcw} from 'lucide-react';
import type {Day, DemoData} from './model';
import {money} from './model';
import {loadEpisodeArchive, type EpisodeArchive} from './episodes';
import {buildCareerEpisodeStats, buildCareerSnapshot, type CareerHolding, type CareerSnapshot} from './careerMetrics';
import './career-dashboard.css';

type Props={data:DemoData;onDetails:(title:string,content:ReactNode)=>void;onYear:(year:string)=>void;onEpisode:(id:string)=>void;onQuestion:(question:string)=>void};
type ChartMode='assets'|'returns'|'drawdown';
type HoldingView='positions'|'sectors'|'lookthrough';
const decimal=(n:number,digits=2)=>money(n,digits);
const percent=(n:number,digits=2)=>decimal(n*100,digits);
const signed=(n:number,digits=2)=>(n>0?'+':n<0?'−':'')+decimal(Math.abs(n),digits);
const tone=(n:number)=>n>0?'cd-gain':n<0?'cd-loss':'';
const dateShort=(value:string)=>value.replaceAll('-','.');

function Metric({label,value,unit,note,color='',onClick}:{label:string;value:string;unit?:string;note?:string;color?:string;onClick:()=>void}){
  return <button type="button" className="cd-metric" onClick={onClick} aria-label={`${label} ${value}${unit??''}，查看计算说明`}>
    <span className="cd-metric-label">{label}</span><strong className={color}>{value}{unit&&<small>{unit}</small>}</strong>{note&&<span className="cd-metric-note">{note}</span>}
  </button>;
}

function CareerChart({snapshot,mode,onSnapshot}:{snapshot:CareerSnapshot;mode:ChartMode;onSnapshot:(day:Day)=>void}){
  const ref=useRef<HTMLDivElement>(null);
  const [size,setSize]=useState({width:700,height:160});
  const [selected,setSelected]=useState<number|null>(null);
  const days=snapshot.actual.days,index=Math.min(selected??days.length-1,days.length-1),day=days[index];
  useEffect(()=>{setSelected(null);},[snapshot]);
  useEffect(()=>{
    const el=ref.current;if(!el)return;
    const observer=new ResizeObserver(([entry])=>{const {width,height}=entry.contentRect;if(width>0&&height>0)setSize(old=>old.width===width&&old.height===height?old:{width,height});});
    observer.observe(el);return()=>observer.disconnect();
  },[]);
  const plot=useMemo(()=>{
    const left=43,right=10,top=13,bottom=24,width=Math.max(1,size.width-left-right),height=Math.max(40,size.height-top-bottom);
    const series=mode==='assets'?[days.map(d=>Number(d.equity)/10000),days.map(d=>(snapshot.initialCapital+Number(d.net_contributions))/10000)]:[days.map(d=>mode==='returns'?(Number(d.nav)-1)*100:Number(d.drawdown)*100)];
    const flat=series.flat(),minimum=Math.min(...flat),maximum=Math.max(...flat);
    const padding=Math.max(mode==='assets'?1:.5,(maximum-minimum)*.08);
    const low=mode==='drawdown'?Math.min(-.5,minimum-padding):Math.min(minimum-padding,mode==='returns'?0:minimum-padding);
    const high=mode==='drawdown'?0:Math.max(low+1,maximum+padding);
    const times=days.map(d=>Date.parse(d.date+'T00:00:00Z')),start=times[0],span=Math.max(1,times.at(-1)!-start);
    const x=(i:number)=>left+(times[i]-start)/span*width,y=(v:number)=>top+(high-v)/(high-low)*height;
    const paths=series.map(values=>values.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' '));
    const tickCount=size.width>=600?6:size.width>=400?4:3;
    const ticks=Array.from(new Set(Array.from({length:Math.min(tickCount,days.length)},(_,i)=>Math.round(i*(days.length-1)/Math.max(1,Math.min(tickCount,days.length)-1)))));
    return {left,right,top,bottom,width,height,low,high,x,y,paths,series,times,start,span,ticks};
  },[snapshot,mode,size.width,size.height]);
  const pick=(clientX:number,element:SVGRectElement)=>{
    const bounds=element.getBoundingClientRect(),fraction=Math.max(0,Math.min(1,(clientX-bounds.left)/bounds.width));
    const target=plot.start+fraction*plot.span;let lo=0,hi=days.length-1;
    while(lo<hi){const mid=Math.floor((lo+hi)/2);if(plot.times[mid]<target)lo=mid+1;else hi=mid;}
    return lo>0&&Math.abs(plot.times[lo-1]-target)<Math.abs(plot.times[lo]-target)?lo-1:lo;
  };
  const activeValue=mode==='assets'?`${decimal(Number(day.equity)/10000)} 万`:mode==='returns'?`${signed((Number(day.nav)-1)*100)}%`:`${signed(Number(day.drawdown)*100)}%`;
  return <>
    <div className="cd-plot" ref={ref}>
      <svg width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label={`${dateShort(days[0].date)}至${dateShort(days.at(-1)!.date)}的${mode==='assets'?'账户资产与累计净投入':mode==='returns'?'资金流调整累计收益率':'资金流调整净值回撤'}曲线`}>
        <title>{mode==='assets'?'资产与净投入，单位万元':mode==='returns'?'累计收益率，单位百分比':'净值回撤，单位百分比'}</title>
        {Array.from({length:4},(_,i)=>plot.low+(plot.high-plot.low)*i/3).map((value,i)=><g key={i} aria-hidden="true"><line x1={plot.left} x2={plot.left+plot.width} y1={plot.y(value)} y2={plot.y(value)} className="cd-gridline"/><text x={plot.left-8} y={plot.y(value)+4} textAnchor="end">{decimal(value,0)}</text></g>)}
        {plot.ticks.map((i,n)=><text aria-hidden="true" key={i} x={plot.x(i)} y={size.height-5} textAnchor={n===0?'start':n===plot.ticks.length-1?'end':'middle'}>{days[i].date.slice(0,7)}</text>)}
        {plot.paths.map((d,i)=><path key={`contrast-${i}`} d={d} fill="none" className={`cd-line-underlay${i?' cd-flow-underlay':''}`} vectorEffect="non-scaling-stroke" aria-hidden="true"/>)}
        {plot.paths.map((d,i)=><path key={i} d={d} fill="none" className={i?'cd-flow-line':'cd-value-line'} vectorEffect="non-scaling-stroke"/>)}
        <line x1={plot.x(index)} x2={plot.x(index)} y1={plot.top} y2={plot.top+plot.height} className="cd-cursor-line"/>
        <circle cx={plot.x(index)} cy={plot.y(plot.series[0][index])} r="3" className="cd-current-point"/>
        <rect x={plot.left} y={plot.top} width={plot.width} height={plot.height} fill="transparent"
          onPointerMove={e=>setSelected(pick(e.clientX,e.currentTarget))} onClick={e=>onSnapshot(days[pick(e.clientX,e.currentTarget)])}/>
      </svg>
    </div>
    <div className="cd-chart-position"><span>{dateShort(day.date)} <b>{activeValue}</b></span><button type="button" onClick={()=>onSnapshot(day)}>查看当日明细<ChevronRight size={13}/></button></div>
    <input className="cd-date-range" type="range" aria-label="选择账户快照日期" aria-valuetext={`${day.date}，${activeValue}`} min={0} max={days.length-1} value={index} onChange={e=>setSelected(Number(e.target.value))}/>
  </>;
}

export function CareerDashboard({data,onDetails,onYear,onEpisode,onQuestion}:Props){
  const [mode,setMode]=useState<ChartMode>('assets'),[holdingView,setHoldingView]=useState<HoldingView>('positions');
  const [attempt,setAttempt]=useState(0);
  const [episodeState,setEpisodeState]=useState<{data:DemoData;archive:EpisodeArchive|null;error:string}|null>(null);
  const base=useMemo(()=>{try{return {snapshot:buildCareerSnapshot(data),error:''};}catch(e){return {snapshot:null,error:(e as Error).message};}},[data]);
  useEffect(()=>{
    if(!base.snapshot)return;
    const controller=new AbortController();setEpisodeState({data,archive:null,error:''});
    loadEpisodeArchive(data,controller.signal).then(archive=>{
      buildCareerEpisodeStats(data,archive);
      if(!controller.signal.aborted)setEpisodeState({data,archive,error:''});
    }).catch(e=>{if(!controller.signal.aborted)setEpisodeState({data,archive:null,error:e.message});});
    return()=>controller.abort();
  },[data,attempt,base.snapshot]);
  const archive=episodeState?.data===data?episodeState.archive:null;
  const episodes=useMemo(()=>{if(!archive)return null;return buildCareerEpisodeStats(data,archive);},[archive,data]);
  const episodeError=episodeState?.data===data?episodeState.error:'';
  if(!base.snapshot)return <section className="career-dashboard cd-unavailable" role="alert"><h1>账户档案需要核对</h1><p>{base.error}</p><button className="secondary" onClick={()=>window.location.reload()}><RotateCcw size={15}/>重新载入档案</button></section>;
  const s=base.snapshot,asOf=s.last.date;
  const explain=(title:string,body:string,detail?:ReactNode)=>onDetails(title,<div className="cd-detail"><p>{body}</p>{detail}<p className="cd-detail-meta">账户：本地教学档案 · {s.first.date}—{asOf}</p><button className="secondary" onClick={()=>onQuestion(`请结合我的账户记录解释${title}，说明使用的数据、计算口径和具体依据。`)}><MessageCircle size={15}/>问投镜</button></div>);
  const openHolding=(holding:CareerHolding)=>{
    const episode=episodes?.open.find(ep=>ep.symbol===holding.symbol);
    onDetails(`${holding.name} · 当前持仓`,<div className="cd-detail"><h3>{holding.name} <small>{holding.symbol}</small></h3><dl>
      <div><dt>持有数量</dt><dd>{money(holding.quantity,0)} {holding.kind==='fund'?'份':'股'}</dd></div><div><dt>期末市值</dt><dd>¥{money(holding.marketValue)}</dd></div><div><dt>占总资产</dt><dd>{percent(holding.weight)}%</dd></div>
      <div><dt>浮动盈亏</dt><dd>{episode?`¥${signed(Number(episode.unrealized_pnl))}`:'投资经历资料尚未载入'}</dd></div></dl>
      <p>截至 {asOf}。{holding.kind==='fund'?'此处显示直接持有的基金份额，底层披露尚未接入。':'行业分类：'+holding.sector+'。'}</p>
      {episode&&<button className="secondary" onClick={()=>onEpisode(episode.id)}>查看这轮投资<ArrowRight size={15}/></button>}</div>);
  };
  const showSnapshot=(day:Day)=>onDetails(`${day.date} · 账户快照`,<div className="cd-detail"><div className="cd-detail-value">¥{money(day.equity)}</div><p>现金 ¥{money(day.cash)} · {day.position_count} 项持仓</p><dl>{Object.entries(day.holdings).map(([symbol,h])=><div key={symbol}><dt>{data.assets.find(a=>a.symbol===symbol)?.name??symbol}</dt><dd>{money(h.quantity,0)} 股/份 · ¥{money(h.market_value)}</dd></div>)}</dl><p>累计净投入 ¥{money(s.initialCapital+Number(day.net_contributions))} · 累计损益 ¥{signed(Number(day.period_pnl))}</p></div>);
  const tradeDetail=(metric:'win'|'payoff'|'factor'|'holding')=>{
    if(!episodes){explain('投资经历统计',episodeError||'正在载入与当前账户相同版本的投资经历；成交与账户数据已经可以查看。');return;}
    const titles={win:'已结束经历胜率',payoff:'平均盈亏比',factor:'盈利因子',holding:'持有期中位数'};
    const definitions={win:`${episodes.winCount} 段净盈利 ÷ ${episodes.closed.length} 段已结束经历。零损益经历计入分母；仍持有的 ${episodes.open.length} 段单列，不按单笔成交计算胜率。`,payoff:'已结束经历的平均盈利 ÷ 平均亏损绝对值；盈利或亏损样本为空时不定义。',factor:'已结束经历的盈利总额 ÷ 亏损总额绝对值；没有亏损时不返回任意高分。',holding:'取已结束经历持有天数的中位数，与投资经历页面一致，含建仓和清仓当天；仍持有的经历不计入。'};
    explain(titles[metric],definitions[metric],<><p>经历净损益沿用账本的分红与费用口径。</p><div className="cd-episode-results">{episodes.closed.map(ep=><button key={ep.id} onClick={()=>onEpisode(ep.id)}><span>{ep.name}<small>第 {ep.round} 轮 · {ep.opened_at}—{ep.closed_at}</small></span><b className={tone(Number(ep.pnl))}>{signed(Number(ep.pnl))}</b><ChevronRight size={14}/></button>)}</div></>);
  };
  const methodDetails=()=>explain('投资生涯计算口径','全部数字读取本人教学路径；持仓取期末快照，交易统计覆盖当前档案期间。',<dl>
    <div><dt>资金与收益</dt><dd>总资产 = 证券市值 + 现金；累计损益 = 总资产 − 净投入。累计收益和回撤沿用资金流调整净值。</dd></div>
    <div><dt>换手</dt><dd>每日买卖额之和 ÷ 当日末总资产，再对 {s.dayCount} 个估值日取平均，包含未交易日；这是双边强度。</dd></div>
    <div><dt>集中度</dt><dd>HHI 使用证券组合内的市值权重，不含现金；基金作为一项直接持仓。前三大和最大持仓占比均以账户总资产为分母。</dd></div>
    <div><dt>经历统计</dt><dd>按建仓至清仓分组，部分卖出不会产生新一轮；含分红及成交费用，持有天数含首尾日。</dd></div>
    <div><dt>穿透</dt><dd>基金底层披露未接入的部分保持未知，不将已知证券放大为完整组合。</dd></div></dl>);
  return <section className="career-dashboard" aria-label="投资生涯数据看板">
    <header className="cd-heading"><div><h1>投资生涯</h1><p>{dateShort(s.first.date).slice(0,7)}—{dateShort(asOf).slice(0,7)}<span> · {s.tradeCount} 笔成交{episodes?` · ${episodes.open.length+episodes.closed.length} 段经历`:''}</span></p></div><div className="cd-heading-actions"><span>教学档案 · 截至 {asOf}</span><button className="cd-inline-action" onClick={methodDetails}><Info size={14}/>计算口径</button></div></header>
    <div className="cd-kpis">
      <Metric label="总资产" value={decimal(s.equity/10000)} unit="万" color="cd-primary-value" onClick={()=>explain('总资产',`截至 ${asOf}，证券市值 ¥${money(s.marketValue)} + 现金 ¥${money(s.cash)} = 总资产 ¥${money(s.equity)}。`)}/>
      <Metric label="累计净投入" value={decimal(s.netInvested/10000)} unit="万" onClick={()=>explain('累计净投入',`期初资本 ¥${money(s.initialCapital)} + 净外部资金流 ¥${signed(Number(s.last.net_contributions))} = ¥${money(s.netInvested)}。账户内买卖和留在账户的分红不作为外部投入。`)}/>
      <Metric label="累计净损益" value={signed(s.pnl/10000)} unit="万" color={tone(s.pnl)} onClick={()=>explain('累计净损益',`总资产 ¥${money(s.equity)} − 净投入 ¥${money(s.netInvested)} = 累计损益 ¥${signed(s.pnl)}。含持仓浮动损益及档案中的分红和费用。`)}/>
      <Metric label="累计收益率" value={signed(s.return*100)} unit="%" color={tone(s.return)} onClick={()=>explain('累计收益率',`资金流调整期末单位净值 ${decimal(Number(s.last.nav),6)} − 1。沿用档案的日末资金流约定，不使用资产增幅代替投资回报。`)}/>
      <Metric label="最大回撤" value={signed(s.maxDrawdown*100)} unit="%" color={tone(s.maxDrawdown)} onClick={()=>explain('最大回撤','取完整逐日资金流调整净值相对此前最高点的最大跌幅；以负值展示，不从资产余额直接计算。')}/>
      <Metric label="现金仓位" value={percent(s.cash/s.equity)} unit="%" onClick={()=>explain('现金仓位',`期末现金 ¥${money(s.cash)} ÷ 总资产 ¥${money(s.equity)}。`)}/>
    </div>
    <div className="cd-upper-grid">
      <section className="cd-panel liquid-glass cd-trend" aria-label="账户轨迹">
        <div className="cd-panel-heading"><h2>账户轨迹</h2><div className="cd-segments" role="group" aria-label="主图指标">{([{id:'assets',label:'资产'},{id:'returns',label:'收益'},{id:'drawdown',label:'回撤'}] as const).map(item=><button key={item.id} aria-pressed={mode===item.id} onClick={()=>setMode(item.id)}>{item.label}</button>)}</div></div>
        <div className="cd-legend"><span><i/>{mode==='assets'?'账户资产':mode==='returns'?'资金流调整收益率':'净值回撤'}</span>{mode==='assets'&&<span><i className="cd-flow-key"/>累计净投入</span>}<span className="cd-chart-unit">{mode==='assets'?'万元':'%'}</span></div>
        <CareerChart snapshot={s} mode={mode} onSnapshot={showSnapshot}/>
      </section>
      <section className="cd-panel liquid-glass cd-risk" aria-label="持仓与风险"><div className="cd-panel-heading"><h2>持仓与风险</h2><span>期末快照</span></div>
        <div className="cd-risk-grid">
          <Metric label="最大持仓占比" value={percent(s.maxWeight)} unit="%" note={s.holdings[0]?.name??'无证券持仓'} onClick={()=>explain('最大持仓占比','期末市值最大的直接持仓 ÷ 账户总资产；包括股票和基金。')}/>
          <Metric label="前三大持仓" value={percent(s.top3Weight)} unit="%" note="占账户总资产" onClick={()=>explain('前三大持仓','前三项直接持仓市值之和 ÷ 账户总资产。',<dl>{s.holdings.slice(0,3).map(h=><div key={h.symbol}><dt>{h.name}</dt><dd>{percent(h.weight)}%</dd></div>)}</dl>)}/>
          <Metric label="直接持仓 HHI" value={s.hhi===null?'—':decimal(s.hhi,3)} note="组合内，不含现金" onClick={()=>explain('直接持仓 HHI',s.hhi===null?'没有证券持仓，集中度不可定义。':`各项证券在证券组合内的市值权重平方求和；ETF 按一项证券。有效持仓数为 ${decimal(s.effectiveCount!)}，不衡量证券间相关性。`)}/>
          <Metric label="当前回撤" value={signed(s.currentDrawdown*100)} unit="%" note="相对历史净值高点" color={tone(s.currentDrawdown)} onClick={()=>explain('当前回撤','期末资金流调整净值 ÷ 历史最高净值 − 1。与整个期间最深的最大回撤分别展示。')}/>
        </div>
        <div className="cd-allocation-label"><span>证券 {percent(s.marketValue/s.equity)}%</span><span>现金 {percent(s.cash/s.equity)}%</span></div><div className="cd-allocation-track" role="img" aria-label={`证券仓位${percent(s.marketValue/s.equity)}%，现金仓位${percent(s.cash/s.equity)}%`}><span style={{width:percent(s.marketValue/s.equity)+'%'}}/></div>
      </section>
    </div>
    <div className="cd-lower-grid">
      <section className="cd-panel liquid-glass cd-holdings" aria-label="持仓结构"><div className="cd-panel-heading"><h2>持仓结构 <small>{s.holdings.length}</small></h2><div className="cd-segments" role="group" aria-label="持仓展示方式">{([{id:'positions',label:'证券'},{id:'sectors',label:'行业'},{id:'lookthrough',label:'穿透'}] as const).map(item=><button key={item.id} aria-pressed={holdingView===item.id} onClick={()=>setHoldingView(item.id)}>{item.label}</button>)}</div></div>
        <div className={`cd-holdings-body${s.holdings.length<=8?' cd-holdings-fit':''}`}>
          {holdingView==='positions'?s.holdings.length?<table className="cd-position-table"><thead><tr><th scope="col">证券</th><th scope="col">市值 / 万</th><th scope="col">账户占比</th><th scope="col">浮动盈亏 / 元</th></tr></thead><tbody>{s.holdings.map(h=>{
            const ep=episodes?.open.find(item=>item.symbol===h.symbol),unrealized=ep?Number(ep.unrealized_pnl):null;
            return <tr key={h.symbol}><td><button onClick={()=>openHolding(h)}>{h.name}<small>{h.symbol}</small></button></td><td>{decimal(h.marketValue/10000)}</td><td>{percent(h.weight,1)}%</td><td className={unrealized===null?'':tone(unrealized)}>{unrealized===null?'—':signed(unrealized,0)}</td></tr>;
          })}</tbody></table>:<p className="cd-inline-empty">当前没有证券持仓，账户现金为 ¥{money(s.cash)}。</p>:holdingView==='sectors'?<div className="cd-sectors">{[...s.sectors,{name:'现金',weight:s.cash/s.equity,kind:'cash'}].sort((a,b)=>b.weight-a.weight).map(item=><div className="cd-sector-row" key={item.kind+item.name}><span>{item.name}{item.kind==='fund'&&<small> · 未穿透</small>}</span><span className={`cd-sector-track ${item.kind==='cash'?'cash':''}`}><i style={{width:percent(item.weight)+'%'}}/></span><b>{percent(item.weight,1)}%</b></div>)}</div>:<div className="cd-lookthrough">
            <div className="cd-lookthrough-summary"><span>待穿透基金权重</span><strong>{percent(s.fundWeight)}<small>%</small></strong></div>
            <dl><div><dt>直接股票</dt><dd>{percent(s.directWeight)}%</dd></div><div><dt>现金</dt><dd>{percent(s.cash/s.equity)}%</dd></div>{s.unknownWeight>0&&<div><dt>类别待确认</dt><dd>{percent(s.unknownWeight)}%</dd></div>}</dl>
            {s.holdings.filter(h=>h.kind==='fund').map(h=><button className="cd-fund-row" key={h.symbol} onClick={()=>openHolding(h)}><span>{h.name}<small>底层持仓披露未接入</small></span><b>{percent(h.weight)}%</b><ChevronRight size={14}/></button>)}
            <p>{s.fundWeight?'基金底层明细暂缺，保留未知权重；直接持仓不等于完整穿透结果。':'当前没有基金持仓，已显示直接证券与现金。'}</p>
          </div>}
        </div>
        <div className="cd-holdings-foot">证券市值 {decimal(s.marketValue/10000)} 万 · 现金 {decimal(s.cash/10000)} 万<span>占比均以总资产为分母</span></div>
      </section>
      <section className="cd-panel liquid-glass cd-trades" aria-label="交易画像"><div className="cd-panel-heading"><h2>交易画像</h2><span>全部期间</span></div>
        <div className="cd-trade-grid" aria-busy={!episodes&&!episodeError}>
          <Metric label="日均双边换手" value={percent(s.meanDailyTurnover,3)} unit="%" onClick={()=>explain('日均双边换手',`每日买入额与卖出额之和 ÷ 当日末总资产，再对 ${s.dayCount} 个估值日取平均，包含未交易日。该期间有 ${s.tradeCount} 笔成交；不等于基金年度单边换手率。`)}/>
          <Metric label="已结束经历胜率" value={episodes?.winRate==null?'—':percent(episodes.winRate,1)} unit={episodes?.winRate==null?undefined:'%'} onClick={()=>tradeDetail('win')}/>
          <Metric label="盈利因子" value={episodes?.profitFactor==null?'—':decimal(episodes.profitFactor)} onClick={()=>tradeDetail('factor')}/>
          <Metric label="平均盈亏比" value={episodes?.payoff==null?'—':decimal(episodes.payoff)} onClick={()=>tradeDetail('payoff')}/>
          <Metric label="持有期中位数" value={episodes?.medianHoldingDays==null?'—':decimal(episodes.medianHoldingDays,Number.isInteger(episodes.medianHoldingDays)?0:1)} unit={episodes?.medianHoldingDays==null?undefined:'天'} onClick={()=>tradeDetail('holding')}/>
          <Metric label="累计交易费用" value={decimal(s.fees)} unit="元" onClick={()=>explain('累计交易费用',`${s.tradeCount} 笔实际教学成交的费用合计 ¥${money(s.fees)}；按原始费用字段汇总，不重复扣除基金净值内费用。`)}/>
        </div>
        <div className="cd-trade-foot">{episodeError?<div role="alert"><span>{episodeError}</span><button onClick={()=>setAttempt(n=>n+1)}><RotateCcw size={13}/>重试</button></div>:episodes?<span>胜率等基于 {episodes.closed.length} 段已结束经历 · {episodes.open.length} 段仍持有</span>:<span role="status">正在核对投资经历，账户统计已可查看…</span>}</div>
      </section>
    </div>
    <section className="cd-years" aria-label="年度复盘"><div className="cd-years-heading"><h2>年度复盘</h2><span>净损益 · 万元</span></div><div className="cd-year-items">{s.years.map(year=><button key={year.year} onClick={()=>onYear(year.year)} aria-label={`查看${year.year}年的投资经历，年度净损益${signed(year.pnl)}元`}><span>{year.year}</span><strong className={tone(year.pnl)}>{signed(year.pnl/10000)}</strong><small>{year.trades} 笔成交<ChevronRight size={12}/></small></button>)}</div></section>
  </section>;
}
