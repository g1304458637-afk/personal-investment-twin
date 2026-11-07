import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { animate, type AnimationPlaybackControls, type AnimationSequence } from 'motion';
import { ArrowRight, ArrowUpRight, Check, ChevronRight, FileText, Pause, Play, RotateCcw, X } from 'lucide-react';
import { money, wan, type DemoData } from '../model';
import { buildCareerReview, type CareerReview } from './careerReview';
import { createAwakeningScene } from './awakeningScene';
import { createTraceScene, SCENE_END } from './motion';
import { makeTrace } from './trace';
import { AWAKENING, awakeningPhase, careerTime } from './awakeningTiming';
import { buildImportReview, type ImportedPreview, type ImportReview } from './importReview';
import './career-awakening.css';

const LENGTH = AWAKENING.end;
const REPLAY_START = AWAKENING.replayStart;
const REPLAY_END = AWAKENING.replayEnd;
const REVIEW_READY = AWAKENING.reviewReady;
const afterIgnition = (time:number) => time + REPLAY_START - 2;
const clamp = (n:number) => Math.max(0, Math.min(1, n));
const dateText = (date:string) => date.replaceAll('-', '.');

type Props = { data:DemoData; preview?:ImportedPreview; reducedMotion:boolean; onFinish:()=>void; onDiscuss:(question:string)=>void; onPlaybackPause:(paused:boolean)=>void };
type Evidence = CareerReview['findings'][number];
type StoryYear = {year:string;index:number;pnl?:number;netFlow?:number;tradeCount:number;buyCount:number;sellCount:number};

export function CareerAwakening(props:Props) {
 const result=useMemo<{review:CareerReview|null;imported:ImportReview|null;error:string}>(()=>{
  try{return props.preview?{review:null,imported:buildImportReview(props.preview),error:''}:{review:buildCareerReview(props.data),imported:null,error:''};}
  catch(e){return {review:null,imported:null,error:(e as Error).message};}
 },[props.data,props.preview]);
 if(!result.review&&!result.imported)return <section className="genesis-error"><img src="/orb.png" alt="投镜"/><h1>这份档案还需要核对。</h1><p>{result.error}</p><button className="primary" onClick={props.onFinish}>返回投资档案<ArrowRight size={16}/></button></section>;
 return <AwakeningPlayer {...props} review={result.review} imported={result.imported}/>;
}

function AwakeningPlayer({data,review,imported,reducedMotion,onFinish,onDiscuss,onPlaybackPause}:Props & {review:CareerReview|null;imported:ImportReview|null}) {
 const [systemReduced,setSystemReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches);
 const reduce=reducedMotion||systemReduced;
 const [time,setTime]=useState(reduce?LENGTH:0),[paused,setPaused]=useState(false),[generation,setGeneration]=useState(0);
 const [evidence,setEvidence]=useState<Evidence|null>(null);
 const root=useRef<HTMLElement>(null),canvas=useRef<HTMLCanvasElement>(null),traceCanvas=useRef<HTMLCanvasElement>(null),globe=useRef<HTMLImageElement>(null),traceRail=useRef<HTMLDivElement>(null);
 const clock=useRef<AnimationPlaybackControls|null>(null),lastTime=useRef(0),evidenceTrigger=useRef<HTMLButtonElement|null>(null);
 const paint=useRef<(time:number)=>void>(()=>{});
 const pausePlayback=()=>{const position=lastTime.current;clock.current?.pause();if(clock.current)clock.current.time=position;paint.current(position);};
 const resumePlayback=()=>{const animation=clock.current;if(!animation)return;const position=lastTime.current;animation.play();animation.time=position;};
 const actual=review?data.paths.find(p=>p.kind==='actual')!:null;
 const fills=imported?.fills??actual!.fills;
 const dates=imported?.dates??data.dates;
 const tradeCount=fills.length;
 const trace=useMemo(()=>makeTrace(fills),[fills]);
 const years=useMemo<StoryYear[]>(()=>imported?imported.years:review!.years.map(y=>{
  const records=fills.filter(f=>f.date.startsWith(y.year)),buyCount=records.filter(f=>f.side==='BUY').length;
  return {...y,tradeCount:records.length,buyCount,sellCount:records.length-buyCount};
 }),[imported,review,fills]);
 const progress=clamp((time-REPLAY_START)/(REPLAY_END-REPLAY_START));
 const yearIndex=Math.min(years.length-1,Math.floor(progress*years.length));
 const year=years[yearIndex];
 const yearStart=yearIndex?years[yearIndex-1].index+1:0;
 const yearFraction=clamp(progress*years.length-yearIndex);
 const cursor=Math.min(dates.length-1,Math.floor(yearStart+(year.index-yearStart)*yearFraction));
 const date=dates[cursor];
 const ready=time>=REVIEW_READY;
 const phase=awakeningPhase(time);
 const shownFills=fills.filter(f=>f.date<=date);
 const latestFill=shownFills.at(-1);
 const sourceLabel=imported?'你的成交记录 · 本机解析':'林远 · 教学档案';
 const subtitle=time<AWAKENING.ignition?`${tradeCount} 笔成交，正在汇入你的投镜。`:
  time<AWAKENING.unfold?'每一笔记录，都在点亮我对你的理解。':
  time<REPLAY_START?'把分散的选择，重新连成属于你的投资时间轴。':
  time<REPLAY_END?(imported?`${year.year} 年，${year.tradeCount} 笔成交：${year.buyCount} 次买入、${year.sellCount} 次卖出。`:
   `${year.year} 年，投资${year.pnl!>=0?'盈利':'亏损'} ${wan(Math.abs(year.pnl!))} 万元。${year.netFlow!>0?`另有 ${wan(year.netFlow!)} 万元净资金转入。`:year.netFlow!<0?`另有 ${wan(-year.netFlow!)} 万元净资金转出。`:'这一年没有净资金转入。'}`):
  time<AWAKENING.chargeStart?(imported?`${imported.buys} 次买入，${imported.sells} 次卖出。第一份回顾，来自你刚刚导入的记录。`:`${review!.addCount} 次连续买入，${review!.lowerAddCount} 次价格更低。每一个发现，都能回到原始记录。`):
  time<AWAKENING.revealStart?'这些经历，正在汇成我对你的第一份理解。':time<REVIEW_READY?'让每一次选择，都成为下一次研究的依据。':'';
 const subtitleKey=phase==='life'?year.year:phase;

 useEffect(()=>{const q=window.matchMedia('(prefers-reduced-motion: reduce)');const update=()=>setSystemReduced(q.matches);q.addEventListener('change',update);return()=>q.removeEventListener('change',update);},[]);
 useEffect(()=>{onPlaybackPause(paused||reduce);},[paused,reduce,onPlaybackPause]);
 useEffect(()=>()=>onPlaybackPause(false),[onPlaybackPause]);

 useLayoutEffect(()=>{
  if(!root.current)return;
  const el=root.current;
  let scene:ReturnType<typeof createAwakeningScene>|undefined;
  if(!reduce&&canvas.current){try{scene=createAwakeningScene(canvas.current);el.dataset.renderer='webgl';}catch{el.dataset.renderer='css';}}
  const select=(s:string)=>el.querySelector(s) as HTMLElement;
  const orb=select('.genesis-orb-move'),body=select('.genesis-orb-body'),card=select('.genesis-card-motion'),content=select('.genesis-card-content');
  const traceScene=!reduce&&traceCanvas.current&&globe.current&&traceRail.current?createTraceScene(traceCanvas.current,globe.current,traceRail.current,trace.points):undefined;
  const orbSize=body.clientWidth,scaleX=orbSize/card.clientWidth,scaleY=orbSize/card.clientHeight;
  const sequence:AnimationSequence=[
   [select('.genesis-ignition'),{opacity:[0,1]},{at:0,duration:1.1}],
   [select('.genesis-ignition'),{opacity:[1,0],y:[0,-25]},{at:6.6,duration:1}],
   [select('.genesis-memory-rail'),{opacity:[0,1]},{at:.3,duration:.8}],
   [select('.genesis-memory-rail'),{opacity:[1,0]},{at:7.2,duration:1}],
   [select('.genesis-traces'),{opacity:[1,0]},{at:7.6,duration:.8}],
   [select('.genesis-story'),{opacity:[0,1]},{at:7.3,duration:1.1}],
   [body,{opacity:[0,1],scale:[.65,1]},{at:0,duration:1.7,ease:[.16,1,.3,1]}],
   [select('.genesis-chart-stage'),{opacity:[0,1],y:[45,0]},{at:7.5,duration:1.4}],
   [select('.genesis-story'),{opacity:[1,0],y:[0,-35],filter:['blur(0px)','blur(8px)']},{at:afterIgnition(16),duration:1.5}],
   [select('.genesis-chart-stage'),{opacity:[1,0],scale:[1,.82],y:[0,-90],filter:['blur(0px)','blur(9px)']},{at:afterIgnition(16.2),duration:1.7}],
   [orb,{x:['18vw','0vw'],y:['-5vh','4vh']},{at:afterIgnition(16),duration:2.8,ease:[.65,0,.35,1]}],
   [body,{scale:[1,.8,.58,1.1],rotateZ:[0,-25,110,210]},{at:afterIgnition(18),duration:2.8,times:[0,.45,.8,1],ease:'easeInOut'}],
   [body,{rotateY:[0,-82],scale:[1.1,.72],opacity:[1,1,0]},{at:afterIgnition(20.45),duration:.95,ease:[.65,0,.35,1]}],
   [select('.genesis-flare'),{opacity:[0,.95,.65,0],scale:[.16,.65,1.5,2.5]},{at:afterIgnition(20.35),duration:2.2,times:[0,.16,.4,1]}],
   [select('.genesis-horizon'),{opacity:[0,1,.7,0],scaleX:[.05,1.4,2,2.2],scaleY:[.3,3,1,.05]},{at:afterIgnition(20.45),duration:2.1,times:[0,.16,.4,1]}],
   [select('.genesis-rift'),{opacity:[0,.9,1,0],scaleX:[.02,.16,.45,1.1],scaleY:[.25,.8,1.1,1.35],rotate:[-25,-12,12,23]},{at:afterIgnition(19.8),duration:2.7,times:[0,.2,.4,1]}],
   [select('.genesis-wave-blue'),{opacity:[0,.9,.45,0],scale:[.15,.75,2.2,3.7]},{at:afterIgnition(20.55),duration:2.3,times:[0,.12,.5,1],ease:[.16,1,.3,1]}],
   [select('.genesis-wave-orange'),{opacity:[0,.85,.3,0],scale:[.1,.8,2.1,3.4]},{at:afterIgnition(20.7),duration:2.5,times:[0,.12,.5,1],ease:[.16,1,.3,1]}],
   [card,{opacity:[0,1,1,1,1],rotateY:[0,-84,-72,12,0],rotateZ:[0,-14,-9,2,0],scaleX:[scaleX*1.1,scaleX*.72,.6,1.03,1],scaleY:[scaleY*1.1,scaleY*.72,.85,1.03,1],borderRadius:['50%','45%','28%','23px','18px']},{at:afterIgnition(20.45),duration:4,times:[0,.23,.4,.76,1],ease:[.45,0,.2,1]}],
   [select('.genesis-card-sheen'),{opacity:[1,1,.6,.08]},{at:afterIgnition(20.45),duration:4,times:[0,.35,.6,1]}],
   [content,{opacity:[0,1],y:[18,0]},{at:afterIgnition(23.2),duration:1.3}],
  ];
  const choreography=animate(sequence,{defaultTransition:{autoplay:false}});
  choreography.speed=0;
  choreography.pause();
  let previous=-1;
  const render=(t:number)=>{
   lastTime.current=t;
   choreography.time=t;
   scene?.render(careerTime(t));
   if(t<=REPLAY_START+.1)traceScene?.render(Math.min(t*1000,SCENE_END));
   el.style.setProperty('--journey-progress',`${clamp(t/LENGTH)*100}%`);
   if(t-previous>.065||t>=LENGTH||t<previous){previous=t;setTime(t);}
  };
  paint.current=render;
  const animation=animate(0,LENGTH,{duration:LENGTH,ease:'linear',autoplay:!reduce,onUpdate:render});
  clock.current=animation;
  setPaused(false);
  if(reduce){animation.time=LENGTH;render(LENGTH);}else render(0);
  const visibility=()=>{if(document.hidden){pausePlayback();setPaused(true);}};
  document.addEventListener('visibilitychange',visibility);
  return()=>{document.removeEventListener('visibilitychange',visibility);animation.stop();choreography.stop();scene?.dispose();traceScene?.dispose();clock.current=null;};
 },[generation,reduce,trace]);

 const togglePause=()=>{if(ready)return;const next=!paused;setPaused(next);if(next)pausePlayback();else resumePlayback();};
 const jump=()=>{if(clock.current){clock.current.time=LENGTH;clock.current.pause();}paint.current(LENGTH);setPaused(false);};
 const replay=()=>{setEvidence(null);setGeneration(g=>g+1);};
 const openEvidence=(item:Evidence,event:React.MouseEvent<HTMLButtonElement>)=>{evidenceTrigger.current=event.currentTarget;clock.current?.pause();setPaused(true);setEvidence(item);};
 const closeEvidence=()=>{setEvidence(null);setPaused(false);evidenceTrigger.current?.focus();};
 const discuss=()=>{if(!review)return;onDiscuss(`我正在查看林远教学档案的首轮回顾：${review.headline}。请从其中一笔具体成交开始，帮我核对当时的持仓、行情和依据。`);};

 return <section ref={root} className="genesis-scene" data-phase={phase} data-reduced={reduce?'true':'false'} aria-label={imported?"你导入的投资记录与首轮回顾":"林远的投资生涯与投镜首轮回顾"}>
  <div className="genesis-atmosphere" aria-hidden="true"/>
  <canvas className="genesis-traces" ref={traceCanvas} aria-hidden="true"/>
  <canvas className="genesis-webgl" ref={canvas} aria-hidden="true"/>
  <div className="genesis-flare" aria-hidden="true"/><div className="genesis-horizon" aria-hidden="true"/><div className="genesis-rift" aria-hidden="true"/>
  <div className="genesis-wave genesis-wave-blue" aria-hidden="true"/><div className="genesis-wave genesis-wave-orange" aria-hidden="true"/>
  <header className="genesis-header"><div className="genesis-brand"><img src="/orb.png" alt=""/><strong>投镜</strong><span>{sourceLabel}</span></div><div className="genesis-controls">
   {!ready&&<button onClick={togglePause} aria-label={paused?'继续播放':'暂停播放'}>{paused?<Play size={17}/>:<Pause size={17}/>}<span>{paused?'继续':'暂停'}</span></button>}
   {ready?<button onClick={replay} disabled={reduce}><RotateCcw size={16}/><span>重播</span></button>:<button onClick={jump}>直接看回顾<ArrowRight size={16}/></button>}
   <button aria-label="返回我的投资" onClick={onFinish}><X size={18}/></button>
  </div></header>

  <div className="genesis-orb-position" aria-hidden="true"><div className="genesis-orb-move"><div className="genesis-orb-body"><img ref={globe} src="/orb.png" alt=""/></div></div></div>
  <div className="genesis-ignition" aria-hidden={time>=REPLAY_START}>
   <h1>让过去的选择，<br/>唤醒你的投镜。</h1><p>{time<AWAKENING.ignition?'成交记录正在汇聚':time<AWAKENING.unfold?'你的投镜，正在被点亮':'你的时间轴，正在展开'}</p>
  </div>
  <div className="genesis-memory-rail" aria-hidden="true"><div><span>{sourceLabel}</span><span>{tradeCount} 笔成交{trace.count>trace.points.length?' · 光点抽样展示':''}</span></div><div className="genesis-trace-rail" ref={traceRail}>{trace.points.map((point,i)=><i className={point.sell?'sell':''} key={i} style={{left:`${point.position*100}%`}}/>)}</div><div>{trace.years.map(year=><span key={year}>{year}</span>)}</div></div>
  <div className="genesis-story" aria-hidden={time<7.3||time>=REPLAY_END}>
   <h1>每一次选择，<br/>都在成为你。</h1>
   <p>我会沿着你的足迹，<br/>回看过去，也陪你检验下一次选择。</p>
   <div className="genesis-year"><strong>{year.year}</strong><span>{dateText(date)}</span></div>
  </div>
  <div className="genesis-chart-stage" aria-hidden={time<7.5||time>=afterIgnition(18)}>
   <div className="genesis-chart-head">{imported?<><span><i/>买入 <i className="orange"/>卖出 · 按实际成交日期</span><strong>{shownFills.length}<small>笔成交</small></strong></>:<><span><i/>账户资产 <i className="orange"/>累计净投入</span><strong>{wan(actual!.days[cursor].equity)}<small>万元</small></strong></>}</div>
   {imported?<ImportedTimeline imported={imported} cursor={cursor}/>:<LifeChart data={data} cursor={cursor}/>}
   <div className="genesis-year-rail">{years.map((y,i)=><span key={y.year} className={i===yearIndex?'current':i<yearIndex?'past':''}><b>{y.year}</b><small>{i<=yearIndex?(imported?`${y.tradeCount} 笔成交`:`${y.pnl!>=0?'+':'−'}${wan(Math.abs(y.pnl!))} 万`):'待回看'}</small></span>)}</div>
   <div className="genesis-trade-ticker">{latestFill?<><span className={latestFill.side==='BUY'?'buy':'sell'}>{latestFill.side==='BUY'?'买入':'卖出'}</span><b>{latestFill.name}</b><span>{dateText(latestFill.date)} · {money(latestFill.quantity,0)} {imported?'单位':latestFill.ticker==='sh510300'?'份':'股'}</span></>:<span>从你的第一笔选择开始</span>}<small>{shownFills.length} / {tradeCount} 笔</small></div>
  </div>

  <div className="genesis-card-position" inert={!ready} aria-hidden={!ready}>
   <article className="genesis-card-motion"><div className="genesis-card-sheen" aria-hidden="true"/><div className="genesis-card-content">
    {review?<>    <header className="genesis-card-header"><img src="/orb.png" alt="投镜"/><div><h2>林远，这是我读到的你。</h2><p>{review.start.slice(0,4)}—{review.end.slice(0,4)} · {review.tradeCount} 笔教学成交 · 首轮回顾</p></div><span className="genesis-verified"><Check size={15}/>依据可查</span></header>
    <div className="genesis-insight"><div><h3>更低的买入价，<br/>是你多次做出的选择。</h3><p>{review.headline}，其余 {review.counterCount} 次是相反样本。<br/>我们可以回到每一笔成交，继续理解当时的选择。</p><button onClick={e=>openEvidence(review.findings[0],e)}>查看这 {review.addCount} 次记录<ArrowUpRight size={16}/></button></div><div className="genesis-ratio"><strong>{review.lowerAddCount}<span>/ {review.addCount}</span></strong><p>连续买入中的更低价格</p></div></div>
    <div className="genesis-review-facts"><button onClick={e=>openEvidence(review.findings[1],e)}><span>你曾经历的最大回撤</span><strong>{(review.maxDrawdown*100).toFixed(1)}<small>%</small></strong><p>{dateText(review.drawdownDate)} · 净值口径<ChevronRight size={16}/></p></button><button onClick={e=>openEvidence(review.findings[2],e)}><span>这些年，投资创造的损益</span><strong>{review.pnl>=0?'+':'−'}{wan(Math.abs(review.pnl))}<small>万元</small></strong><p>净投入 {wan(review.netInvested)} 万 · 期末 {wan(review.equity)} 万<ChevronRight size={16}/></p></button></div>
    <div className="genesis-card-next"><p>接下来，一起看看：<br/><b>这些加仓发生时，你承担了多大的仓位？</b></p><button onClick={discuss}>和投镜继续回顾<ArrowRight size={18}/></button></div>
    <footer className="genesis-card-foot"><span>本地档案计算 · 每条发现都可以核对</span><button onClick={onFinish}>进入投资生涯<ArrowUpRight size={14}/></button></footer></>:<ImportedCard imported={imported!} onFinish={onFinish} onEvidence={openEvidence}/>}
   </div></article>
  </div>

  <footer className={`genesis-subtitles ${ready?'finished':''}`}>
   {!ready&&<div className="genesis-subtitle-line" aria-live="off"><img src="/orb.png" alt=""/><p key={subtitleKey}>{subtitle}</p></div>}
   <div className="genesis-track" aria-hidden="true"><span/></div>
   <div className="genesis-chapters"><span className={time<REPLAY_START?'active':''}>汇聚经历 · 唤醒投镜</span><span className={time>=REPLAY_START&&time<REPLAY_END?'active':''}>回放你的生涯</span><span className={time>=REPLAY_END?'active':''}>回顾 · 展开分析卡</span></div>
  </footer>
  {evidence&&<EvidenceDialog item={evidence} source={imported?imported.fileName:`林远教学档案 · 来源 ${review!.sourceFingerprint.slice(0,12)}`} imported={!!imported} onClose={closeEvidence}/>}
 </section>;
}

function LifeChart({data,cursor}:{data:DemoData;cursor:number}){
 const chart=useMemo(()=>{
  const actual=data.paths.find(p=>p.kind==='actual')!,days=actual.days;
  const initial=Number(days[0].equity)-Number(days[0].net_contributions);
  const values=days.map(d=>Number(d.equity));const funds=days.map(d=>initial+Number(d.net_contributions));
  const min=Math.min(...values,...funds)*.95,max=Math.max(...values,...funds)*1.04;
  const point=(value:number,index:number)=>[index/(days.length-1)*1000,205-(value-min)/(max-min)*180];
  const line=(v:number[])=>v.map((n,i)=>`${i?'L':'M'}${point(n,i).map(x=>x.toFixed(2)).join(',')}`).join(' ');
  const markers=actual.fills.map(f=>{const i=days.findIndex(d=>d.date===f.date);return {...f,index:i,point:point(Number(days[i].equity),i)};});
  return{equity:line(values),funds:line(funds),points:values.map(point),markers};
 },[data]);
 const [x,y]=chart.points[cursor];
 return <svg className="genesis-life-chart" viewBox="-12 -10 1024 240" role="img" aria-label={`投资生涯回放，当前日期 ${data.dates[cursor]}`}>
  <defs><linearGradient id="genesis-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#55b9ff" stopOpacity=".3"/><stop offset="100%" stopColor="#55b9ff" stopOpacity="0"/></linearGradient><clipPath id="genesis-reveal"><rect x="-6" y="-10" width={x+7} height="245"/></clipPath></defs>
  {[35,90,145,205].map(v=><line key={v} x1="0" y1={v} x2="1000" y2={v} stroke="#cce8ff" strokeOpacity=".09"/>)}
  <g clipPath="url(#genesis-reveal)"><path d={`${chart.equity} L1000,220 L0,220 Z`} fill="url(#genesis-area)"/><path d={chart.funds} fill="none" stroke="#ffb16f" strokeWidth="1.5" strokeDasharray="5 6"/><path d={chart.equity} fill="none" stroke="#b1e5ff" strokeWidth="2.2"/>{chart.markers.map(m=><circle key={m.execution_id} cx={m.point[0]} cy={m.point[1]} r="3.1" fill={m.side==='BUY'?'#76d4ff':'#ffaf72'}/>)}</g>
  <line x1={x} y1="0" x2={x} y2="215" stroke="#83d8ff" strokeOpacity=".25"/><circle cx={x} cy={y} r="12" fill="#60caff" opacity=".16"/><circle cx={x} cy={y} r="4" fill="#e4f8ff"/>
 </svg>;
}

function EvidenceDialog({item,source,imported,onClose}:{item:Evidence;source:string;imported:boolean;onClose:()=>void}){
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{panel.current?.querySelector<HTMLButtonElement>('button')?.focus();},[]);
 return <div className="genesis-evidence-scrim" onClick={e=>{if(e.target===e.currentTarget)onClose();}}><div className="genesis-evidence" ref={panel} role="dialog" aria-modal="true" aria-label={item.title} onKeyDown={e=>{
  if(e.key==='Escape'){e.stopPropagation();onClose();}if(e.key==='Tab'){const nodes=panel.current?.querySelectorAll<HTMLButtonElement>('button')??[];if(nodes.length){e.preventDefault();nodes[0].focus();}}
 }}><header><h2>{item.title}</h2><button onClick={onClose} aria-label="关闭研究依据"><X size={20}/></button></header><p>{item.body}</p><div className="genesis-evidence-list">{item.evidence.map((e,i)=><article key={e.executionId??i}><span className={e.kind==='counter'?'counter':''}>{e.kind==='counter'?'相反样本':e.kind==='support'?'支持记录':imported?'文件记录':'账户快照'}</span><div><h3>{e.label}<small>{dateText(e.date)}</small></h3><p>{e.detail}</p>{e.executionId&&<small>成交记录：{e.executionId}</small>}</div></article>)}</div><footer><FileText size={16}/><span>{source}<br/>{imported?'仅根据文件里的成交记录整理；账户收益和回撤需补齐资金与持仓数据。':'本地归档核对，未调用在线模型；这些记录不证明当时的投资动机。'}</span></footer></div></div>;
}

function ImportedTimeline({imported,cursor}:{imported:ImportReview;cursor:number}) {
 const chart=useMemo(()=>{
  const first=Date.parse(imported.start),span=Date.parse(imported.end)-first;
  const x=(date:string)=>span?(Date.parse(date)-first)/span*1000:500;
  const buckets=new Map<number,{buy:number;sell:number}>();
  for(const fill of imported.fills){const pixel=Math.round(x(fill.date)),bucket=buckets.get(pixel)??{buy:0,sell:0};bucket[fill.side==='BUY'?'buy':'sell']++;buckets.set(pixel,bucket);}
  const max=Math.max(1,...[...buckets.values()].flatMap(value=>[value.buy,value.sell]));
  const paths={buy:'',sell:''};
  for(const [pixel,value] of buckets){if(value.buy)paths.buy+=`M${pixel},92v${-value.buy/max*60} `;if(value.sell)paths.sell+=`M${pixel},142v${value.sell/max*60} `;}
  return {...paths,x};
 },[imported]);
 const x=chart.x(imported.dates[cursor]);
 return <svg className="genesis-life-chart" viewBox="-12 -10 1024 240" role="img" aria-label={`成交记录时间轴，当前日期 ${imported.dates[cursor]}`}>
  <defs><clipPath id="genesis-import-reveal"><rect x="-6" y="0" width={x+12} height="230"/></clipPath></defs>
  <line x1="0" y1="117" x2="1000" y2="117" stroke="#aacce8" strokeOpacity=".22"/>
  <line x1="0" y1="92" x2="1000" y2="92" stroke="#aacce8" strokeOpacity=".08"/>
  <line x1="0" y1="142" x2="1000" y2="142" stroke="#aacce8" strokeOpacity=".08"/>
  <g clipPath="url(#genesis-import-reveal)"><path d={chart.buy} stroke="#97dcff" strokeWidth="3"/><path d={chart.sell} stroke="#ffb17a" strokeWidth="3"/></g>
  <line x1={x} y1="20" x2={x} y2="215" stroke="#d6f2ff" strokeOpacity=".35"/><circle cx={x} cy="117" r="5" fill="#dff4ff"/>
 </svg>;
}

function ImportedCard({imported,onFinish,onEvidence}:{imported:ImportReview;onFinish:()=>void;onEvidence:(item:Evidence,event:React.MouseEvent<HTMLButtonElement>)=>void}) {
 const records:Evidence={id:'import-records',title:'你导入的成交记录',body:`${imported.fileName} · 共 ${imported.tradeCount} 笔成交。${imported.tradeCount>120?'此处展示最早 120 笔，完整记录可在资料与账户查看。':'以下记录按成交日期排列，保留原文件行号。'}`,metric:String(imported.tradeCount),unit:'笔',evidence:imported.fills.slice(0,120).map(fill=>({date:fill.date,label:`${fill.side==='BUY'?'买入':'卖出'} · ${fill.name}`,detail:`成交价 ${fill.price}；成交数量 ${fill.quantity}`,kind:'account',executionId:fill.execution_id}))};
 return <>
  <header className="genesis-card-header"><img src="/orb.png" alt="投镜"/><div><h2>这是你的第一份交易画像。</h2><p className="genesis-file-name" title={imported.fileName}>{imported.fileName} · {imported.tradeCount} 笔成交</p></div><span className="genesis-verified"><Check size={15}/>来自你的文件</span></header>
  <div className="genesis-insight"><div><h3>每一笔选择，<br/>都有了自己的时间坐标。</h3><p>从 {dateText(imported.start)} 到 {dateText(imported.end)}，<br/>记录了 {imported.buys} 次买入、{imported.sells} 次卖出，涉及 {imported.securities.length} 个标的。</p><button onClick={event=>onEvidence(records,event)}>核对导入的成交<ArrowUpRight size={16}/></button></div><div className="genesis-ratio"><strong>{imported.buys}<span>/ {imported.tradeCount}</span></strong><p>买入记录 / 全部成交</p></div></div>
  <div className="genesis-review-facts"><button onClick={event=>onEvidence(records,event)}><span>留下记录的年份</span><strong>{imported.years.length}<small>年</small></strong><p>{imported.years[0].year}—{imported.years.at(-1)!.year}<ChevronRight size={16}/></p></button><button onClick={event=>onEvidence(records,event)}><span>交易过的标的</span><strong>{imported.securities.length}<small>个</small></strong><p>{imported.securities.slice(0,3).join(' · ')}{imported.securities.length>3?'…':''}<ChevronRight size={16}/></p></button></div>
  <div className="genesis-card-next"><p>回顾已经开始。<br/><b>补齐资金与持仓资料，就能继续核对收益与回撤。</b></p><button onClick={onFinish}>查看我的成交记录<ArrowRight size={18}/></button></div>
  <footer className="genesis-card-foot"><span>本机解析 · 未计算账户收益与回撤</span><button onClick={onFinish}>进入资料与账户<ArrowUpRight size={14}/></button></footer>
 </>;
}
