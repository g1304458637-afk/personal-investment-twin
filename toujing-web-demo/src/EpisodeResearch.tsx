import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {ArrowLeft,ArrowUpRight,ChevronDown,Maximize2,Minus,Play,Plus,ScanLine,X} from 'lucide-react';
import {useDemo} from './App';
import {PriceChart} from './Charts';
import {Replay} from './Pages';
import {episodeMarket,episodeRange,episodeScope,type InvestmentEpisode} from './episodes';
import {money,type DemoData} from './model';
import type {ResearchScope} from './alignment';
import './episode-research.css';

type Props={
  data:DemoData;episode:InvestmentEpisode;onBack:()=>void;
  renderDetails:(onClose:()=>void,eventId?:string)=>ReactNode;
};

// The chart stays mounted while reading records or visiting comparison. These
// are views of the same episode, not new account or research sessions.
export function EpisodeResearch({data,episode,onBack,renderDetails}:Props){
  const {ask,researchScope,setResearchScope,setAssistantVisible}=useDemo();
  const market=useMemo(()=>episodeMarket(data,episode),[data,episode]);
  const full=episodeRange(episode),last=market.dates.length-1;
  const [view,setView]=useState<'chart'|'records'|'comparison'>('chart');
  const [visitedComparison,setVisitedComparison]=useState(false);
  const [selection,setSelection]=useState<[string,string]|null>(null);
  const [selecting,setSelecting]=useState(false);
  const [windowRange,setWindowRange]=useState<[number,number]>([0,last]);
  const [hoverDate,setHoverDate]=useState<string|null>(null);
  const [recordId,setRecordId]=useState<string>();
  const savedScope=useRef<ResearchScope>(episodeScope(data,episode));
  const initial=useRef(true);
  const staticPane=useRef<HTMLDivElement>(null);
  const replayButton=useRef<HTMLButtonElement>(null);
  const rangeDates=useMemo(()=>market.dates.slice(windowRange[0],windowRange[1]+1),[market.dates,windowRange]);
  const bars=useMemo(()=>new Map(market.bars.map(bar=>[bar.date,bar])),[market.bars]);
  const quoteDate=hoverDate??selection?.[1]??rangeDates.at(-1);
  const quote=quoteDate?bars.get(quoteDate):undefined;
  const unit=episode.ticker==='sh510300'?'份':'股';

  useEffect(()=>{
    if(initial.current){initial.current=false;ask(undefined,episodeScope(data,episode));}
  },[ask,data,episode]);

  const currentScope=(range=selection??[full.start,full.end] as [string,string])=>episodeScope(data,episode,range,researchScope);
  const choose=(start:string,end:string)=>{
    const next:[string,string]=[start,end];
    setSelection(next);setSelecting(false);
    ask(undefined,currentScope(next));
  };
  const clearSelection=()=>{
    setSelection(null);setSelecting(false);
    setResearchScope(episodeScope(data,episode,undefined,researchScope));
  };
  const explain=()=>ask(`结合${episode.name} ${selection?.[0]??full.start}至${selection?.[1]??full.end}的行情与本轮买卖，解释这段投资经历。`,currentScope());
  const zoom=(factor:number)=>{
    const [start,end]=windowRange;
    const count=Math.min(market.dates.length,Math.max(20,Math.round((end-start+1)*factor)));
    const focus=selection?market.dates.indexOf(selection[1]):Math.round((start+end)/2);
    const nextStart=Math.max(0,Math.min(market.dates.length-count,Math.round(focus-count/2)));
    setWindowRange([nextStart,nextStart+count-1]);
  };
  const openComparison=()=>{
    savedScope.current=currentScope();
    setVisitedComparison(true);setView('comparison');setAssistantVisible(false);
    setResearchScope({...episodeScope(data,episode),origin:'replay',path_ids:data.paths.map(path=>path.id)});
  };
  const returnToChart=()=>{
    setView('chart');ask(undefined,savedScope.current);
    requestAnimationFrame(()=>replayButton.current?.focus({preventScroll:true}));
  };
  const openRecords=(eventId?:string)=>{setRecordId(eventId);setView('records');};

  return <div className="episode-research" data-episode-id={episode.id} data-view={view}>
    <div className="episode-static-view" ref={staticPane} hidden={view!=='chart'}>
      <header className="episode-research-heading">
        <button className="episode-back" onClick={()=>{setAssistantVisible(false);onBack();}}><ArrowLeft size={16}/>投资经历</button>
        <div className="episode-research-identity"><h1>{episode.name}<small>{episode.symbol} · 第 {episode.round} 轮</small></h1><p>{full.start} — {full.end}<span> · {episode.status==='open'?'持有中':'已结束'}</span></p></div>
        <button ref={replayButton} className="secondary episode-play-link" onClick={openComparison}><Play size={14}/>播放对比<ArrowUpRight size={13}/></button>
      </header>
      <div className="episode-chart-panel liquid-glass">
        <div className="episode-chart-toolbar">
          <span className="episode-chart-type">日 K<small>未复权 · 人民币</small></span>
          <div className="episode-chart-actions">
            <button className={selecting?'active':''} aria-pressed={selecting} onClick={()=>setSelecting(!selecting)}><ScanLine size={14}/>{selecting?'拖动选择':'框选解释'}</button>
            <button aria-label="放大行情" title="放大行情" disabled={rangeDates.length<=20} onClick={()=>zoom(.6)}><Plus size={15}/></button>
            <button aria-label="缩小行情" title="缩小行情" disabled={rangeDates.length>=market.dates.length} onClick={()=>zoom(1.6)}><Minus size={15}/></button>
            <button aria-label="显示整轮行情" title="显示整轮行情" onClick={()=>setWindowRange([0,last])}><Maximize2 size={14}/></button>
          </div>
        </div>
        <div className="episode-quote" aria-live="off">
          <time>{quoteDate}</time>{quote?<><span>开 <b>{quote.open}</b></span><span>高 <b>{quote.high}</b></span><span>低 <b>{quote.low}</b></span><span>收 <b>{quote.close}</b></span><span className="episode-quote-position">持有 <b>{money(market.positions.get(quoteDate!)??'0',0)} {unit}</b></span></>:<span>当日无日线记录</span>}
        </div>
        <div className="episode-candle-stage" data-range-start={rangeDates[0]} data-range-end={rangeDates.at(-1)}>
          <PriceChart bars={market.bars} dates={rangeDates} cursor={rangeDates.length-1} fills={market.fills} unit={unit}
            mode="static" selecting={selecting} selection={selection??undefined} onSelectionStart={()=>{}}
            onRange={choose} onPick={day=>choose(day,day)} onHoverDateChange={setHoverDate}
            onMarkerPick={fill=>openRecords(fill.execution_id)}/>
          {selection&&<div className="selection-action episode-selection-action"><span>{selection[0]}{selection[0]!==selection[1]?' — '+selection[1]:''}</span><button className="primary small" onClick={explain}>解释这段<ArrowUpRight size={14}/></button><button className="episode-clear-selection" aria-label="清除行情选区" onClick={clearSelection}><X size={14}/></button></div>}
          {selecting&&!selection&&<div className="episode-selection-hint">在图上拖动，选出想研究的一段行情</div>}
        </div>
        <div className="episode-chart-range" aria-label="调整行情显示范围">
          <time>{rangeDates[0]}</time><div><input type="range" min={0} max={last} value={windowRange[0]} aria-label="行情显示起点" aria-valuetext={rangeDates[0]} onChange={e=>setWindowRange(([start,end])=>[Math.min(Number(e.target.value),Math.max(0,end-1)),end])}/><input type="range" min={0} max={last} value={windowRange[1]} aria-label="行情显示终点" aria-valuetext={rangeDates.at(-1)} onChange={e=>setWindowRange(([start,end])=>[start,Math.max(Number(e.target.value),Math.min(last,start+1))])}/></div><time>{rangeDates.at(-1)}</time>
        </div>
        <footer className="episode-chart-footer">
          <button className="episode-records-toggle" onClick={()=>openRecords()}><span>{episode.trade_ids.length} 笔买卖 · {episode.status==='open'?'期末':'本轮'}盈亏 <b className={Number(episode.pnl)<0?'episode-loss':'episode-gain'}>{Number(episode.pnl)>0?'+':''}{money(episode.display.pnl)} 元</b></span><ChevronDown size={13}/><span className="episode-records-caption">记录与明细</span></button>
          <span className="episode-chart-provenance">真实行情 · 教学成交</span>
        </footer>
      </div>
      <p className="episode-research-hint">拖动框选行情，在右侧继续追问；点击买卖标记查看成交。</p>
    </div>
    {view==='records'&&<div className="episode-records-view">{renderDetails(()=>setView('chart'),recordId)}</div>}
    {visitedComparison&&<div className="episode-comparison-view" hidden={view!=='comparison'}>
      <Replay initialTicker={episode.ticker} initialDate={full.end} initialRange={full} active={view==='comparison'} initialPlaying={false} onBack={returnToChart} backLabel="返回行情研究"/>
    </div>}
  </div>;
}
