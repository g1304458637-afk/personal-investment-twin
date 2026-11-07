import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {ArrowDownToLine,ArrowLeft,ArrowRight,ArrowUpRight,BookOpen,Brain,Building2,Check,CheckCheck,ChevronDown,ChevronRight,Clock3,Copy,Database,Expand,FileText,FolderOpen,GitBranch,Heart,History,Layers3,Link2,LockKeyhole,Maximize2,MessageCircle,Minus,MoreHorizontal,Pause,Play,Plus,RotateCcw,Search,Send,Settings2,ShieldCheck,SkipForward,Sparkles,TrendingUp,Upload,Users,Wallet,X} from 'lucide-react';
import {COLORS,DemoData,Fill,LABELS,Path,Rule,csvRows,download,money,nearestIndex,parseRule,pct,safeLoad,save,simulateRule,wan} from './model';
import {IconButton,Orb,DecisionDetail,useDemo} from './App';
import {PriceChart,ReplayChart} from './Charts';
import {replayBounds} from './replayWindow';
import {defaultScope,runtime,normalizeExperiment,type ResearchScope} from './alignment';
import {ResultView,RuntimePanel,DocumentReader,ValuationLab,DecisionEditor} from './NativeTools';
import {CompanyOperatingCanvas} from './company/CompanyOperatingCanvas';

type ReplayProps = {
 initialTicker?: string;
 initialDate?: string;
 initialPlaying?: boolean;
 initialPaths?: number[];
 initialRange?: {start:string;end:string};
 active?: boolean;
 backLabel?: string;
 onBack?: () => void;
 follow?: {name:string;budget:number;path:number};
};

export function Replay({initialTicker,initialDate,initialPlaying=false,initialPaths,initialRange,active=true,backLabel='返回我的投资',onBack,follow}:ReplayProps){
 const {data,ticker:currentTicker,setTicker:rememberTicker,ask,sheet,toast,researchScope,setResearchScope,lowMotion}=useDemo();
 const [ticker,setTicker]=useState(()=>data.bars[initialTicker??currentTicker]?initialTicker??currentTicker:'sz000333');
 const [playing,setPlaying]=useState(()=>initialPlaying&&!lowMotion&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches);
 const [rawCursor,setRawCursor]=useState(()=>{
  if(initialDate)return nearestIndex(data.dates,initialDate);
  if(initialPlaying)return 0;
  return safeLoad(`cursor-${data.experiment_id}-${ticker}`,data.dates.length-1);
 });
 const [speed,setSpeed]=useState(2);
 const [selected,setSelected]=useState(initialPaths??[0,1,2,3,4,5]);
 const [metric,setMetric]=useState<'nav'|'equity'|'drawdown'>('nav');
 const [showResults,setShowResults]=useState(()=>safeLoad('replay-show-results',true));
 const [selecting,setSelecting]=useState(false);
 const [range,setRange]=useState<[string,string]|null>(null);
 const [lookback,setLookback]=useState<{count:number;through:number}|null>(null);
 const ref=useRef<HTMLDivElement>(null);
 const options=useRef<HTMLDetailsElement>(null);
 const {paths,dates}=data;
 const lastIndex=dates.length-1;
 const bounds=replayBounds(dates,initialRange);
 const endIndex=Math.min(bounds.end,lookback?.through??bounds.end);
 const startIndex=lookback?Math.max(bounds.start,endIndex-lookback.count+1):bounds.start;
 const windowDates=useMemo(()=>dates.slice(startIndex,endIndex+1),[dates,startIndex,endIndex]);
 const cursor=Math.max(startIndex,Math.min(endIndex,Number.isFinite(rawCursor)?Math.round(rawCursor):startIndex));
 const cursorRef=useRef(cursor);
 cursorRef.current=cursor;

 useEffect(()=>{
  if(!initialTicker&&!playing)save(`cursor-${data.experiment_id}-${ticker}`,cursor);
 },[cursor,playing,ticker,data.experiment_id,initialTicker]);
 useEffect(()=>{
  if(!active){setPlaying(false);return;}
  if(!playing)return;
  let frame=0;
  let last=performance.now();
  let progress=cursorRef.current;
  const tick=(now:number)=>{
   progress+=Math.min(100,now-last)/1000*(dates.length/90)*speed;
   last=now;
   const next=Math.min(endIndex,Math.floor(progress));
   if(next!==cursorRef.current)setRawCursor(next);
   if(next===endIndex){setPlaying(false);return;}
   frame=requestAnimationFrame(tick);
  };
  frame=requestAnimationFrame(tick);
  return()=>cancelAnimationFrame(frame);
 },[playing,speed,endIndex,dates.length,active]);

 const date=dates[cursor];
 const windowCursor=cursor-startIndex;
 const asset=data.assets.find(a=>a.ticker===ticker);
 const unit=ticker==='sh510300'?'份':'股';
 const fillsByDay=useMemo(()=>paths.map(path=>{
  const days=new Map<string,Fill[]>();
  path.fills.filter(fill=>fill.ticker===ticker).forEach(fill=>{
   const list=days.get(fill.date)??[];
   list.push(fill);
   days.set(fill.date,list);
  });
  return days;
 }),[paths,ticker]);
 const divergences=useMemo(()=>dates.filter(day=>{
  const actions=fillsByDay.map(byDay=>(byDay.get(day)??[]).map(f=>[f.side,f.quantity].join(':')).sort().join('|'));
  return actions.some(Boolean)&&new Set(actions).size>1;
 }),[dates,fillsByDay]);
 const markers=useMemo(()=>selected.flatMap(i=>paths[i].fills
  .filter(f=>f.ticker===ticker)
  .map(f=>({...f,pathIndex:i,pathName:LABELS[i]}))),[paths,ticker,selected]);
 const toggle=(i:number)=>setSelected(visible=>visible.includes(i)?
  visible.length>1?visible.filter(index=>index!==i):visible:[...visible,i]);
 const seek=(index:number)=>{
  setPlaying(false);
  setSelecting(false);
  setRange(null);
  setRawCursor(index);
 };
 const next=()=>{
  const day=divergences.find(day=>day>date&&day<=dates[endIndex]);
  if(day)seek(nearestIndex(dates,day));
  else toast('当前回放区间内没有下一处分歧。');
 };
 const scopeFor=(start=range?.[0]??dates[startIndex],end=range?.[1]??date):ResearchScope=>{
  const base=defaultScope(data,ticker,'replay');
  const retainHistorical=researchScope.instrument_id===ticker&&researchScope.origin==='replay'&&researchScope.mode==='as_known_then';
  return {
   ...base,start,end,kind:start===end?'candle':'range',
   focus:researchScope.origin==='replay'?researchScope.focus:'public_price',
   mode:retainHistorical?'as_known_then':'hindsight',
   knowledge_at:retainHistorical?researchScope.knowledge_at:base.knowledge_at,
   historical_proof:retainHistorical?'public_reconstruction':'hindsight',
   path_ids:selected.map(i=>paths[i].id)
  };
 };
 const choose=(start:string,end:string)=>{
  setPlaying(false);
  setSelecting(false);
  setRange([start,end]);
  setResearchScope(scopeFor(start,end));
 };
 const switchTicker=(nextTicker:string)=>{
  setTicker(nextTicker);
  if(!initialTicker)rememberTicker(nextTicker);
  setPlaying(false);
  setSelecting(false);
  setRange(null);
 };
 const chooseWindow=(count:number)=>{
  setPlaying(false);
  setSelecting(false);
  setRange(null);
  setLookback(count?{count,through:cursor}:null);
  if(options.current)options.current.open=false;
 };
 const togglePlayback=()=>{
  if(playing){setPlaying(false);return;}
  setRange(null);
  setSelecting(false);
  if(cursor===endIndex)setRawCursor(startIndex);
  setPlaying(true);
 };
 const foldResults=()=>{
  setShowResults(v=>{save('replay-show-results',!v);return !v;});
  if(options.current)options.current.open=false;
 };
 const explain=()=>{
  setPlaying(false);
  sheet(`${asset?.name??ticker} · ${date}`,<div className="detail-stack">
   <h3>这一天，六条路径怎样行动？</h3>
   {paths.map((path,i)=>{
    const state=path.days[cursor];
    const fills=fillsByDay[i].get(date)??[];
    return <div key={i} className="path-detail">
     <div><i style={{background:COLORS[i]}} className="dot"/><b>{LABELS[i]}</b><span>资产 ¥{money(state.equity)}</span></div>
     <p>{fills.length?fills.map(f=>`${f.side==='BUY'?'买入':'卖出'} ${money(f.quantity,0)}${unit} · ¥${money(f.price)} · 费用 ¥${money(f.fee)}`).join('；'):'当日没有这只证券的新成交。'}</p>
     <small>组合现金 ¥{money(state.cash)} · 净值 {Number(state.nav).toFixed(4)}</small>
     {!!path.rule_card.length&&<details><summary>查看这一条路径的规则</summary>{path.rule_card.map(r=><p key={r.id}>{r.label}：{r.value}</p>)}</details>}
    </div>;
   })}
   <button className="primary" onClick={()=>ask(`回看 ${date} 附近的行情和本人操作。结合当时的信息和后续走势解释这段经历。`,{
    ...scopeFor(dates[Math.max(0,cursor-20)],date),focus:'personal_review'
   })}>解释当日行情与本人操作<ArrowRight size={15}/></button>
  </div>);
 };
 const sources=()=>{
  setPlaying(false);
  if(options.current)options.current.open=false;
  sheet('计算与来源',<div className="detail-stack">
   <p>逐日状态来自投镜策略引擎。六条路径共用资金计划、日历和执行假设。</p>
   <p>K 线与买卖标记对应所选证券，金额、净值与回撤对应全组合。视窗用完整历史区间定坐标，绘制推进到当前日期。</p>
   {data.assumptions.map(a=><p key={a}>{a}</p>)}
   <ResultView value={data.formulas}/>
   <details><summary>行情原件与版本</summary><ResultView value={data.sources.filter(s=>s.file.startsWith(ticker))}/><code>{data.source_fingerprint}</code></details>
   <button className="secondary" onClick={()=>download('投镜-同场实验报告.json',JSON.stringify({
    date,ticker,paths:paths.map((p,i)=>({name:LABELS[i],state:p.days[cursor],rule:p.rule})),
    source_fingerprint:data.source_fingerprint,assumptions:data.assumptions
   },null,2))}>导出当日实验报告<ArrowDownToLine size={15}/></button>
  </div>);
 };
 const actualFills=fillsByDay[0].get(date)??[];
 const playLabel=playing?'暂停回放':cursor===endIndex?'从起点重播六条路径':'播放六条路径';
 return <div className="replay-view aligned-replay" ref={ref}>
  <div className="replay-heading">
   {onBack&&<button className="replay-back" aria-label={backLabel} onClick={onBack}><ArrowLeft size={18}/><span>{backLabel}</span></button>}
   <div className="replay-title"><h1>同一段行情，<span>六种选择。</span></h1><p>个股行情与买卖，随六条组合路径一起回放。</p></div>
   <div className="replay-heading-actions">
    <IconButton label="全屏观看" onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void ref.current?.requestFullscreen().catch(()=>toast('当前窗口不支持全屏。'));}}><Expand size={18}/></IconButton>
   </div>
  </div>
  <div className="replay-stage liquid-glass">
   <div className="replay-stage-top">
    <div className="asset-picker"><select aria-label="切换回放证券" value={ticker} onChange={e=>switchTicker(e.target.value)}>{data.assets.map(a=><option key={a.ticker} value={a.ticker}>{a.name} · {a.symbol}</option>)}</select><span>个股日线 · 未复权</span></div>
    <div className="play-date"><span>{playing?'正在回放':'停留在'}</span><strong>{date.replaceAll('-',' / ')}</strong></div>
    <div className="replay-tools">
     <button className={`secondary small ${selecting?'selected':''}`} onClick={()=>{setSelecting(!selecting);setPlaying(false);}} aria-pressed={selecting}>{selecting?'拖动框选':'框选解释'}</button>
     <details className="chart-options" ref={options}><summary aria-label="更多图表选项">•••</summary><div>
      <button onClick={foldResults}>{showResults?'收起净值对照':'显示净值对照'}</button>
      <label>固定回放区间<select value={lookback?.count??0} onChange={e=>chooseWindow(Number(e.target.value))}><option value={0}>全程</option><option value={120}>截至此日的 120 个交易日</option><option value={240}>截至此日的 240 个交易日</option></select></label>
      <button onClick={sources}>计算与来源</button>
     </div></details>
    </div>
   </div>
   <div className="path-switches">{paths.map((path,i)=><button className={selected.includes(i)?'on':''} key={i} title={path.name} style={{'--path-color':COLORS[i]}as React.CSSProperties} onClick={()=>toggle(i)} aria-pressed={selected.includes(i)}><i/><span>{LABELS[i]}</span>{selected.includes(i)&&<Check size={12}/>}</button>)}</div>
   <div className={`replay-canvas ${showResults?'with-results':'market-only'}`} data-window-start={windowDates[0]} data-window-end={windowDates.at(-1)}>
    <div className="market-pane">
     <PriceChart key={ticker} bars={data.bars[ticker]??[]} dates={windowDates} cursor={windowCursor} fills={markers} unit={unit}
      selecting={selecting} selection={range??undefined} onSelectionStart={()=>setPlaying(false)} onRange={choose} onPick={day=>choose(day,day)}/>
     {range&&<div className="selection-action"><span>{range[0]}{range[0]!==range[1]?' — '+range[1]:''}</span>
      <button className="primary small" onClick={()=>ask('解释这段行情的变化，结合可用因素和模型对照给出分析。',scopeFor())}>解释这段<ArrowUpRight size={14}/></button>
      <button className="text-button" onClick={()=>setRange(null)}>清除</button>
     </div>}
    </div>
    {showResults&&<div className="nav-pane">
     <div className="nav-pane-title"><span>全组合表现 · 六条路径</span><div className="small-segmented">
      {([{id:'nav',label:'净值'},{id:'equity',label:'资产'},{id:'drawdown',label:'回撤'}]as const).map(m=><button key={m.id} className={metric===m.id?'active':''} onClick={()=>setMetric(m.id)}>{m.label}</button>)}
      <button onClick={foldResults} aria-label="收起净值对照">−</button>
     </div></div>
     <ReplayChart paths={paths} dates={windowDates} cursor={windowCursor} startIndex={startIndex} selected={selected} onSeek={seek} metric={metric}/>
    </div>}
   </div>
   <div className="path-totals">{paths.map((path,i)=><button className={!selected.includes(i)?'muted-path':''} key={i} style={{'--path-color':COLORS[i]}as React.CSSProperties} onClick={()=>toggle(i)} aria-label={`切换${LABELS[i]}`}><span>{LABELS[i]}</span><strong>{wan(path.days[cursor].equity)}<small>万</small></strong><em>{pct(Number(path.days[cursor].nav)-1)}</em></button>)}</div>
   <div className="divergence-strip"><GitBranch size={16}/><div>
    <b>{follow?`模拟跟随 · ${follow.name} · ¥${money(follow.budget*Number(paths[follow.path].days[cursor].nav))}`:divergences.includes(date)?`${date} · 路径出现不同操作`:`${date} · 继续持有与观察`}</b>
    <span>{follow?`以 ¥${money(follow.budget,0)} 为起点，按归档净值等比映射`:actualFills.length?actualFills.map(f=>`本人${f.side==='BUY'?'买入':'卖出'} ${money(f.quantity,0)}${unit}`).join('；'):'本人当日没有这只证券的新成交'}</span>
   </div><button className="text-button" onClick={explain}>查看当日操作<ArrowRight size={14}/></button></div>
   <div className="playback-controls">
    <button className="play-button" aria-label={playLabel} title={playLabel} disabled={startIndex===endIndex} onClick={togglePlayback}>{playing?<Pause size={21} fill="currentColor"/>:<Play size={21} fill="currentColor"/>}</button>
    <div className="play-track">
     <input type="range" min={startIndex} max={endIndex} value={cursor} onChange={e=>seek(Number(e.target.value))} aria-label="回放日期" aria-valuetext={date} style={{'--progress':windowCursor/Math.max(1,endIndex-startIndex)*100+'%'}as React.CSSProperties}/>
     <div><span>{windowDates[0]}</span><span>{windowDates.at(-1)}</span></div>
    </div>
    <select className="speed-select" value={speed} onChange={e=>setSpeed(Number(e.target.value))} aria-label="播放速度"><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option><option value={8}>8×</option></select>
    <button className="secondary small" onClick={next} aria-label="下一分歧"><SkipForward size={15}/>下一分歧</button>
    <IconButton label="回到区间起点" onClick={()=>seek(startIndex)}><RotateCcw size={16}/></IconButton>
   </div>
  </div>
  <div className="page-foot"><span><i className="status-dot"/>真实历史行情 · 教学成交 · {windowDates.length} 个交易日</span><button className="text-button" onClick={()=>{setPlaying(false);ask(undefined,scopeFor());}}>问投镜<ArrowUpRight size={14}/></button></div>
 </div>;
}

export function Strategies({initialRule}:{initialRule?:Rule}={}){
 const {data,customRule,setCustomRule,replay,sheet,closeSheet,toast,ticker,setExperiment}=useDemo();
 const [input,setInput]=useState(''),[rule,setRule]=useState<Rule>(initialRule??customRule??data.paths[2].rule!),[messages,setMessages]=useState<{who:string;text:string}[]>([]),[mode,setMode]=useState('我的想法'),[busy,setBusy]=useState(''),[error,setError]=useState(''),[saved,setSaved]=useState(''),[changes,setChanges]=useState<any[]>([]),[source,setSource]=useState('');const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const submit=async(text:string)=>{if(!text.trim()||busy)return;setBusy('正在校验规则');setError('');setInput('');setMessages(m=>[...m,{who:'you',text}]);try{const result=await runtime('workbench.strategy.propose',{question:text,base:rule,...(source?{source}:{})});if(!alive.current)return;setRule(result.rule);setChanges(result.changes);setSaved('');setMessages(m=>[...m,{who:'ai',text:result.message+'\n'+result.card.map((c:any)=>`${c.label}：${c.value}`).join('\n')}]);}catch(e){if(alive.current)setError((e as Error).message);}finally{if(alive.current)setBusy('');}};
 const extract=async(kind:string)=>{setMode(kind);setError('');if(kind==='专业方法'){setRule(data.paths[3].rule!);setMessages(m=>[...m,{who:'ai',text:'已载入原方法库的长期持有模板。来源与额外执行参数列在规则卡中；也可以粘贴自己的方法材料。'}]);return;}if(kind==='分享策略'){setRule({...data.paths[4].rule!,name:'社区趋势 · 我的改编',kind:'variant',parent_id:data.paths[4].id});setMessages(m=>[...m,{who:'ai',text:'已读取同一份教学分享规则，保留父版本。修改后按新版本运行。'}]);return;}if(kind==='个人经历'){setBusy('正在读取行为证据');try{const d=await runtime('workbench.strategy.discover');if(!alive.current)return;setRule(data.paths[1].rule!);setMessages(m=>[...m,{who:'ai',text:`原行为工具读取了 ${d.training_rows} 个提炼样本和 ${d.test_rows} 个检验样本。个人镜像已放入规则卡，可按自己的理解调整。`}]);sheet('行为发现与时间外检验',<ResultView value={d}/>);}catch(e){setError((e as Error).message);}finally{setBusy('');}}};
 const versions=()=>sheet('策略版本与分享',<StrategyVersions onLoad={r=>{setRule(r);setSaved('');closeSheet();toast('版本已载入原规则卡');}} rule={rule}/>);
 const start=async()=>{
  if(busy)return;
  setBusy('正在运行六条路径');
  setError('');
  try{
   const variant={...rule,kind:'variant'};
   const version=await runtime('workbench.strategy.save',{rule:variant,confirmed:true});
   if(!alive.current)return;
   setCustomRule(version.body);
   setSaved(version.id);
   const rules=data.paths.slice(1).map((path,i)=>i===1?version.body:path.rule);
   const result=await runtime('workbench.strategy.run',{rules});
   const experiment=normalizeExperiment(result,data);
   if(!alive.current)return;
   setExperiment(experiment);
   save('last-experiment-ref',result.artifact_ref);
   toast('计算完成。六条路径可以在本页播放。');
   replay(ticker,true);
  }catch(e){if(alive.current)setError((e as Error).message);}
  finally{if(alive.current)setBusy('');}
 };
 return <div className="strategy-view aligned-strategy"><div className="page-title"><div><h1>说出想法，让它成为方法。</h1><p>同一个规则合同，同一套投镜策略引擎。</p></div><button className="secondary" onClick={versions}><History size={16}/>版本与分享</button></div>
 <div className="strategy-layout"><section className="strategy-conversation liquid-glass"><div className="section-line"><div className="inline-orb"><Orb size="tiny"/><b>一起构建你的策略</b></div><span className="quiet-tag">本地规则工具</span></div><div className="strategy-modes">{['我的想法','个人经历','专业方法','分享策略'].map(m=><button disabled={!!busy} className={mode===m?'active':''} key={m} onClick={()=>void extract(m)}>{m}</button>)}</div><div className="strategy-dialogue">{messages.length===0?<><div className="strategy-intro"><Orb/><h2>你的投资习惯，<br/>值得拥有一个名字。</h2><p>提出规则，核对条件，再看看它怎样行动。</p></div><div className="strategy-starters">{['改为逢低分批买入，单只最多两成','盈利15%后卖出一半','改为20日均线上方入场'].map(t=><button key={t} onClick={()=>void submit(t)}>{t}<ArrowUpRight size={14}/></button>)}</div></>:messages.map((m,i)=><div className={`co-message ${m.who}`} key={i}>{m.who==='ai'&&<div className="inline-orb"><Orb size="tiny"/>投镜 · 规则工具</div>}<p>{m.text}</p></div>)}{mode==='专业方法'&&<details className="source-input"><summary>补充自己的方法或投资经历</summary><textarea rows={5} value={source} maxLength={20000} onChange={e=>setSource(e.target.value)} placeholder="粘贴方法材料。执行条件仍由你在对话框提出和确认。"/><button className="secondary" disabled={!source.trim()} onClick={async()=>{try{const r=await runtime('workbench.strategy.source.save',{confirmed:true,text:source,title:'用户提供的方法材料'});toast('材料已保存在隔离研究资料库');sheet('已保存方法资料',<ResultView value={{来源:r.id,说明:'规则卡中的参数仍需由你确认。'}}/>);}catch(e){setError((e as Error).message);}}}>保存这份材料</button></details>}{error&&<p className="form-error" role="alert">{error}</p>}{busy&&<p role="status">{busy}…</p>}</div><form className="strategy-composer" onSubmit={e=>{e.preventDefault();void submit(input);}}><textarea rows={2} placeholder="例如：单只上限20%，盈利15%后卖一半…" value={input} onChange={e=>setInput(e.target.value)} aria-label="用自然语言创建策略" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void submit(input);}}}/><button className="send-button" aria-label="生成策略规则" disabled={!input.trim()||!!busy}><ArrowRight size={18}/></button></form></section>
 <section className="strategy-artifact liquid-glass"><div className="rule-artifact-head"><span className="pill"><GitBranch size={13}/>{saved?'已保存版本':'策略草稿'}</span><span>确认后可回放</span></div><input className="rule-name" value={rule.name} aria-label="策略名称" onChange={e=>setRule({...rule,name:e.target.value})}/><p>八只教学证券共同运行；修改只产生新的实验。</p><div className="rule-flow"><div><span>开始进入</span><select value={rule.entry} aria-label="入场规则" onChange={e=>setRule({...rule,entry:e.target.value})}><option value="dip">低于均线，分批进入</option><option value="trend">高于均线，跟随趋势</option><option value="hold">进入之后，长期持有</option></select></div><div><span>仓位上限</span><div className="rule-slider"><input type="range" min={5} max={50} step={5} value={rule.max_weight*100} onChange={e=>setRule({...rule,max_weight:Number(e.target.value)/100})} aria-label="单只仓位上限"/><strong>{(rule.max_weight*100).toFixed(0)}<small>%</small></strong></div></div><div><span>加仓条件</span><b>{rule.add_drop?`回落 ${(rule.add_drop*100).toFixed(0)}%，至少间隔 ${rule.cooldown} 个交易日`:'不主动追加'}</b></div><div><span>减仓条件</span><b>{rule.entry==='hold'?'持有至期末':`盈利 ${(rule.take_profit*100).toFixed(0)}% · 减持 ${(rule.partial_fraction*100).toFixed(0)}%`}</b></div><details><summary>全部参数、来源与本次变化</summary><ResultView value={{规则:rule,变化:changes}}/></details></div><div className="rule-confirm"><small>次日开盘 · T+1 · 同一资金计划 · 确认后写入隔离策略库</small><button className="primary wide" disabled={!!busy} onClick={()=>void start()}>{busy||'确认规则，运行并回放'}<Play size={17}/></button></div></section></div></div>;
}
function StrategyVersions({rule,onLoad}:{rule:Rule;onLoad:(r:Rule)=>void}){
 const {data,replay,setExperiment}=useDemo();
 const [items,setItems]=useState<any[]>([]),[error,setError]=useState('');useEffect(()=>{let active=true;runtime('workbench.strategy.list').then(v=>{if(active)setItems(v.items);}).catch(e=>active&&setError(e.message));return()=>{active=false;};},[]);
 return <div className="detail-stack">{safeLoad('last-experiment-ref','')&&<button className="secondary" onClick={async()=>{try{const saved=await runtime('workbench.strategy.experiment.get',{id:safeLoad('last-experiment-ref','')});setExperiment(normalizeExperiment({...saved.body,artifact_ref:saved.id},data));replay();}catch(e){setError((e as Error).message);}}}>打开上次计算的回放<Play size={14}/></button>}<button className="secondary" onClick={async()=>{try{download('投镜-策略分享包.json',JSON.stringify(await runtime('workbench.strategy.export',{rule}),null,2));}catch(e){setError((e as Error).message);}}}>导出原生策略合同<ArrowDownToLine size={14}/></button><label className="file-pick">导入策略分享包<input type="file" accept=".json" onChange={async e=>{const f=e.target.files?.[0];if(!f)return;try{if(f.size>1000000)throw new Error('策略文件请小于1MB');const p=await runtime('workbench.strategy.import',{package:JSON.parse(await f.text())});onLoad(p.rule);}catch(e){setError((e as Error).message);}}}/></label>{error&&<p className="form-error">{error}</p>}{items.map(v=><button key={v.id} className="history-item" onClick={()=>onLoad(v.body)}><GitBranch size={15}/><span>{v.body.name}<small>版本 {v.id.slice(-8)}</small></span></button>)}{!items.length&&<p>确认一份规则后，版本会出现在这里。</p>}</div>;
}

export function Company(){
 const {data,sheet,ask,prepareQuestion,ticker,setTicker,researchScope,setResearchScope}=useDemo();
 const [company,setCompany]=useState(['sz000333','sz000651','sh600690'].includes(ticker)?ticker:'sz000333'),[mode,setMode]=useState('经营全貌'),[docMode,setDocMode]=useState('原文');
 const [companies,setCompanies]=useState<{instrument_id:string;name:string}[]>([]);
 useEffect(()=>{let active=true;runtime('workbench.company.catalog').then(v=>{if(active)setCompanies(v.companies);}).catch(()=>{});return()=>{active=false;};},[]);
 const scope=useMemo(()=>researchScope.origin==='company'&&researchScope.instrument_id===company?researchScope:defaultScope(data,company,'company'),[company,data,researchScope]);
 const name=companies.find(item=>item.instrument_id===company)?.name??data.assets.find(item=>item.ticker===company)?.name??company;
 return <div className="company-view aligned-company"><div className="page-title"><div><h1>从一份报告，看见一家公司的全貌。</h1><p>经营关系、原文与计算，共享同一份研究范围。</p></div><div className="select-company"><Building2 size={18}/><select value={company} onChange={e=>{setCompany(e.target.value);setTicker(e.target.value);setResearchScope(defaultScope(data,e.target.value,'company'));}} aria-label="选择研究公司">{(companies.length?companies:[{instrument_id:company,name}]).map(c=><option key={c.instrument_id} value={c.instrument_id}>{c.name}</option>)}</select></div></div>
 <div className="company-toolbar"><div className="segmented">{['经营全貌','财报与证据','估值实验','我的判断'].map(m=><button key={m} className={m===mode?'active':''} onClick={()=>setMode(m)}>{m}</button>)}</div><button className="text-button" onClick={()=>ask(undefined,scope)}><Sparkles size={14}/>问这家公司</button></div>
 <div className="company-content liquid-glass">
  <div className="company-graph-pane" hidden={mode!=='经营全貌'}><CompanyOperatingCanvas scope={scope} name={name} active={mode==='经营全貌'}
   onSource={sourceScope=>{setResearchScope(sourceScope);sheet('报告原文',<DocumentReader scope={sourceScope} onAsk={(q,s)=>prepareQuestion(q,s??sourceScope)}/>);}}
   onQuestion={prepareQuestion}/></div>
  {mode==='财报与证据'?<div className="company-evidence"><div className="small-segmented">{['原文','财务与现金流'].map(t=><button className={docMode===t?'active':''} onClick={()=>setDocMode(t)} key={t}>{t}</button>)}</div>{docMode==='原文'?<DocumentReader scope={scope} onAsk={ask}/>:<RuntimePanel id="financial" scope={scope} data={data} onAsk={ask}/>}</div>:mode==='估值实验'?<ValuationLab scope={scope} onAsk={ask}/>:mode==='我的判断'?<DecisionEditor key={scope.instrument_id+scope.knowledge_at} scope={scope}/>:null}
 </div><div className="page-foot company-page-foot"><span>公开公司研究 · 原公司资料引擎</span><CompanyResearchRange scope={scope} onApply={setResearchScope}/></div></div>;
}
function CompanyResearchRange({scope,onApply}:{scope:ResearchScope;onApply:(scope:ResearchScope)=>void}){
 const day=(instant:string)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(instant));
 const today=day(new Date().toISOString());
 const [date,setDate]=useState(day(scope.knowledge_at)),[mode,setMode]=useState(scope.mode),[error,setError]=useState('');
 useEffect(()=>{setDate(day(scope.knowledge_at));setMode(scope.mode);setError('');},[scope.instrument_id,scope.knowledge_at,scope.mode]);
 return <form className="company-range" onSubmit={event=>{
  event.preventDefault();if(!date||date>today){setError('请选择今天或更早的资料截止日期。');return;}
  setError('');onApply({...scope,mode,historical_proof:mode==='as_known_then'?'public_reconstruction':'hindsight',knowledge_at:date===today?new Date().toISOString():new Date(date+'T23:59:59+08:00').toISOString(),selection_object:undefined});
 }}><label>资料截止<input type="date" aria-label="公司研究资料截止日期" value={date} max={today} required onChange={e=>setDate(e.target.value)}/></label><select aria-label="公司研究资料时点口径" value={mode} onChange={e=>setMode(e.target.value as ResearchScope['mode'])}><option value="hindsight">事后研究</option><option value="as_known_then">按公开时间回看</option></select><button className="text-button" type="submit">应用</button>{error&&<span className="company-range-error" role="alert">{error}</span>}</form>;
}

const people=[{name:'周知行',role:'长期主义实践者',initial:'周',path:3,color:COLORS[3],title:'先看生意，再给时间。',body:'把研究过的公司放进长期持有实验，少一次操作，会改变什么？',tags:['长期持有','公开方法','6年区间']},{name:'陈序',role:'趋势与仓位研究者',initial:'陈',path:4,color:COLORS[4],title:'用规则，给情绪留一段距离。',body:'入场和减仓都有明确条件。和我的交易放在同一张图上，差异一目了然。',tags:['趋势规则','仓位控制','29笔模拟成交']},{name:'林远',role:'正在形成自己的方法',initial:'林',path:1,color:COLORS[1],title:'不是每次下跌，都需要加仓。',body:'这是从我的六年经历中提炼的镜像。保留过去，也开始检验新的规则。',tags:['个人镜像','行为记忆','规则可改编']}];
export function Community(){
 const {data,replay,sheet,toast,closeSheet,ticker}=useDemo();const [active,setActive]=useState('精选经历'),[liked,setLiked]=useState<number[]>(()=>safeLoad('likes',[])),[published,setPublished]=useState(()=>safeLoad('published',false)),[followed,setFollowed]=useState(()=>safeLoad('followed',''));
 const like=(i:number)=>{const next=liked.includes(i)?liked.filter(x=>x!==i):[...liked,i];setLiked(next);save('likes',next);};
 type Plan={name:string;budget:number;path:number;mode:string};
 const [plan,setPlan]=useState<Plan|null>(()=>safeLoad('follow-plan',null));
 const openFollow=(selected:Plan)=>{
  const follow=selected.mode==='按比例模拟'?selected:undefined;
  sheet('同图比较 · '+selected.name,<div className="inline-replay">
   <Replay initialTicker={ticker} initialPlaying initialPaths={[0,selected.path,5]} follow={follow}/>
  </div>);
 };
 const follow=(p:typeof people[number])=>sheet('模拟跟随 · '+p.name,<FollowPanel name={p.name} path={data.paths[p.path]} onConfirm={(budget,mode)=>{
  const selected={name:p.name,budget,path:p.path,mode};
  setFollowed(p.name);
  setPlan(selected);
  save('followed',p.name);
  save('follow-plan',selected);
  closeSheet();
  if(mode==='按比例模拟')openFollow(selected);
  else toast('已关注这份研究与策略。');
 }}/>);
 return <div className="community-view"><div className="page-title"><div><h1>看见别人的选择，<br/>找到自己的答案。</h1><p>经历可以分享，规则可以检验。把不同投资方式，放在同一段行情里。</p></div><button className="primary" onClick={()=>sheet('分享我的投资经验',<SharePanel onPublish={()=>{setPublished(true);save('published',true);toast('已发布到本地演示社区');}}/>)}><Plus size={16}/>分享我的经历</button></div><div className="community-toolbar"><div className="segmented">{['精选经历','策略集市','我的关注'].map(t=><button className={active===t?'active':''} key={t} onClick={()=>setActive(t)}>{t}</button>)}</div><span className="quiet-tag">本地社区情景 · 人物为虚构角色</span></div>
 {active==='我的关注'?<div className="following-view liquid-glass"><Users size={32}/><h2>{followed?plan?.mode==='按比例模拟'?`正在模拟跟随 ${followed}`:`已关注 ${followed}`:'关注一种可检验的方法。'}</h2>
 <p>{plan?.mode==='按比例模拟'?`模拟预算 ¥${money(plan.budget,0)}。打开同图查看净值随时间的变化。`:'查看规则、原文和历史路径，再决定是否加入实验。'}</p>
 <div className="button-row">{plan&&<><button className="primary" onClick={()=>openFollow(plan)}><Play size={16}/>查看同图比较</button><button className="secondary" onClick={()=>{setFollowed('');setPlan(null);save('followed','');save('follow-plan',null);toast('已取消本地关注');}}>取消{plan.mode==='按比例模拟'?'模拟跟随':'关注'}</button></>}</div>
 </div>:<div className="community-stories">{people.map((p,i)=>{const result=data.paths[p.path];return <article className="community-story liquid-glass" key={p.name} style={{'--person-color':p.color}as React.CSSProperties}><div className="person-row"><span className="person-avatar">{p.initial}</span><div><h3>{p.name}</h3><p>{p.role}</p></div><button className={`icon-button ${liked.includes(i)?'liked':''}`} aria-label={'收藏'+p.name+'的策略'} onClick={()=>like(i)}><Heart size={17} fill={liked.includes(i)?'currentColor':'none'}/></button></div><div className="community-quote"><span>“</span><h2>{p.title}</h2><p>{p.body}</p></div><div className="strategy-preview"><svg viewBox="0 0 330 90" role="img" aria-label={p.name+'的模拟净值路径'}><path d={result.days.filter((_,j)=>j%8===0).map((d,j,arr)=>`${j?'L':'M'}${j/(arr.length-1)*330},${86-(Number(d.nav)-.8)*74}`).join(' ')} fill="none" stroke={p.color} strokeWidth="2"/><path d={data.paths[0].days.filter((_,j)=>j%8===0).map((d,j,arr)=>`${j?'L':'M'}${j/(arr.length-1)*330},${86-(Number(d.nav)-.8)*74}`).join(' ')} fill="none" stroke="#b8d4e7" strokeWidth="1" strokeOpacity=".45" strokeDasharray="4 4"/></svg><div><span>模拟净值变化</span><b>{pct(result.return)}</b></div></div><div className="tag-row">{p.tags.map(t=><span key={t}>{t}</span>)}</div><div className="community-card-actions"><button className="primary" onClick={()=>replay(ticker,true,[0,p.path,5])}><Play size={15}/>与我同图比较</button><button className="secondary" onClick={()=>follow(p)}>模拟跟随<ArrowUpRight size={14}/></button></div><div className="community-card-foot"><button className="text-button" onClick={()=>sheet(p.name+' · 交流与改编',<CommentPanel person={p.name} onAdapt={()=>sheet('改编 '+p.name+' 的方法',<Strategies initialRule={{...result.rule!,kind:'variant',name:result.name+' · 我的改编',parent_id:result.id}}/>)}/>)}><MessageCircle size={14}/>交流与改编</button><span>规则与来源可查看</span></div></article>;})}</div>}
 {published&&<button className="published-strip" onClick={()=>sheet('我的分享',<SharePanel onPublish={()=>toast('分享内容已更新')}/>)}><Check size={16}/>你的「{safeLoad('shared-title','六年经历与个人镜像')}」已加入演示社区<ArrowUpRight size={15}/></button>}
 <div className="community-bottom"><GitBranch size={20}/><div><b>一次点击，进入同一条时间线。</b><span>自己的历史、他人的方法、改编后的策略，共同展开。</span></div><button className="text-button" onClick={()=>replay(ticker,true)}>六条路径全部比较<ArrowRight size={16}/></button></div></div>;
}
function FollowPanel({name,path,onConfirm}:{name:string;path:Path;onConfirm:(budget:number,mode:string)=>void}){const [budget,setBudget]=useState(100000),[mode,setMode]=useState('按比例模拟'),[agreed,setAgreed]=useState(false);return <div className="detail-stack"><span className="pill">独立沙盒 · 不发送真实订单</span><h3>把{name}的方法，放进你的实验。</h3><p>可以仅关注研究，也可以按归档净值映射你的资金，在当前页查看模拟金额和回撤。</p><label className="field">模拟资金<input type="number" min="10000" step="10000" value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label><label className="field">执行方式<select value={mode} onChange={e=>setMode(e.target.value)}><option>按比例模拟</option><option>仅关注研究与策略更新</option></select></label><div className="rule-line"><span>策略版本</span><p>{path.name}</p></div><div className="rule-line"><span>资金隔离</span><p>按归档策略净值映射你的模拟资金，不复制真实订单；原始投资记录不改变。</p></div><label className="check-row"><input type="checkbox" checked={agreed} onChange={e=>setAgreed(e.target.checked)}/>我确认用模拟资金体验此策略</label><button className="primary wide" disabled={!agreed||budget<10000||!Number.isFinite(budget)} onClick={()=>onConfirm(budget,mode)}>确认，开始模拟跟随<Play size={16}/></button></div>;}
function SharePanel({onPublish}:{onPublish:()=>void}){
 const {data,memories}=useDemo();
 const [title,setTitle]=useState(()=>safeLoad('shared-title','六年之后，我如何重新理解分批买入'));
 const [body,setBody]=useState(()=>safeLoad('shared-body','把自己的操作和镜像放在同一段行情上，看看什么规则让它们走向不同的结果。'));
 const [include,setInclude]=useState<string[]>(()=>safeLoad('shared-includes',['规则','实验报告']));
 const [memoryId,setMemoryId]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [published,setPublished]=useState<unknown>(()=>safeLoad('shared-package',null));
 const eligibleMemories=memories.filter(m=>!m.withdrawn);
 const memory=eligibleMemories.find(m=>m.id===memoryId);
 const shareMemory=safeLoad('sharing',false);
 const publish=async()=>{
  setBusy(true);
  setError('');
  try{
   const pack={
    title:title.trim(),body,scope:'local_demo',date:new Date().toISOString(),
    rule:include.includes('规则')?await runtime('workbench.strategy.export',{rule:data.paths[2].rule}):undefined,
    report:include.includes('实验报告')?{
     experiment_id:data.experiment_id,method_version:data.method_version,source_fingerprint:data.source_fingerprint,
     period:[data.dates[0],data.dates.at(-1)],paths:data.paths.map((path,i)=>({name:LABELS[i],return:path.return,max_drawdown:path.max_drawdown}))
    }:undefined,
    memory:shareMemory&&include.includes('研究记忆')&&memory?{type:memory.type,title:memory.title,body:memory.body,date:memory.date}:undefined,
    teaching_trades:include.includes('教学成交')?data.paths[0].fills.map(f=>({date:f.date,ticker:f.ticker,side:f.side,quantity:f.quantity,price:f.price})):undefined
   };
   save('shared-title',pack.title);
   save('shared-body',body);
   save('shared-includes',include);
   save('shared-package',pack);
   setPublished(pack);
   onPublish();
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 };
 const options=['规则','实验报告','教学成交',...(shareMemory?['研究记忆']:[])];
 return <div className="detail-stack">
  <label className="field">标题<input value={title} maxLength={80} onChange={e=>setTitle(e.target.value)}/></label>
  <label className="field">我的经验<textarea rows={4} value={body} maxLength={4000} onChange={e=>setBody(e.target.value)}/></label>
  <h3>选择这次要分享的内容</h3>
  {options.map(item=><label className="check-row" key={item}><input type="checkbox" checked={include.includes(item)} onChange={()=>setInclude(list=>list.includes(item)?list.filter(v=>v!==item):[...list,item])}/>{item}</label>)}
  {options.includes('研究记忆')&&include.includes('研究记忆')&&<label className="field">选择一条记忆<select value={memoryId} onChange={e=>setMemoryId(e.target.value)}>
   <option value="">请选择</option>{eligibleMemories.map(m=><option key={m.id} value={m.id}>{m.title}</option>)}
  </select></label>}
  <p>发布到本地演示社区。策略包通过原投镜分享接口生成。</p>
  {error&&<p className="form-error" role="alert">{error}</p>}
  <button className="primary wide" onClick={()=>void publish()} disabled={!title.trim()||busy||(options.includes('研究记忆')&&include.includes('研究记忆')&&!memory)}>{busy?'正在生成分享内容…':'发布到演示社区'}<ArrowRight size={16}/></button>
  {!!published&&<button className="secondary" onClick={()=>download('投镜-本地分享.json',JSON.stringify(published,null,2))}>导出已发布内容<ArrowDownToLine size={15}/></button>}
 </div>;
}
function CommentPanel({person,onAdapt}:{person:string;onAdapt:()=>void}){const [text,setText]=useState(''),[comments,setComments]=useState<string[]>(()=>safeLoad('comments-'+person,[]));return <div className="detail-stack"><h3>与{person}的方法对话</h3><p>先看规则与历史条件，再聊哪些部分适合自己的方法。</p>{comments.map((c,i)=><div className="local-comment" key={i}><b>我</b><p>{c}</p></div>)}<textarea rows={3} value={text} onChange={e=>setText(e.target.value)} placeholder="写下想讨论的问题…" aria-label="评论内容"/><button className="primary" disabled={!text.trim()} onClick={()=>{const c=[...comments,text];setComments(c);save('comments-'+person,c);setText('');}}>添加本地评论<Send size={15}/></button><button className="secondary" onClick={onAdapt}>创建我的改编版本<GitBranch size={15}/></button></div>;}

export function DataPage({initialImport,onImported}:{initialImport?:{name:string;rows:Record<string,string>[]} | null;onImported?:(value:{name:string;rows:Record<string,string>[]} | null)=>void}={}){
 const {data,toast,sheet}=useDemo();const [rows,setRows]=useState<Record<string,string>[]>(()=>initialImport?.rows??safeLoad('imported-rows',[])),[error,setError]=useState(''),[phase,setPhase]=useState(()=>(initialImport?.rows??safeLoad<unknown[]>('imported-rows',[])).length?1:0),[fileName,setFileName]=useState(()=>initialImport?.name??safeLoad('imported-name','本地 CSV')),[drag,setDrag]=useState(false);const inputRef=useRef<HTMLInputElement>(null);
 const read=async(file:File)=>{setError('');setFileName(file.name);try{if(file.size>5e6)throw new Error('演示导入支持 5 MB 以内的 CSV');const r=csvRows(await file.text());setRows(r);save('imported-rows',r);save('imported-name',file.name);onImported?.({name:file.name,rows:r});setPhase(1);toast(`已解析 ${r.length} 笔记录，文件留在浏览器`);}catch(e){setError((e as Error).message);}};
 const sample=()=>{const r=data.paths[0].fills.map(f=>({date:f.date,ticker:f.ticker,side:f.side,quantity:f.quantity,price:f.price}));setRows(r);setFileName('林远的六年投资档案.csv');onImported?.({name:'林远的六年投资档案.csv',rows:r});setPhase(1);};
 return <div className="data-view"><div className="page-title"><div><h1>导入经历，唤醒你的投镜。</h1><p>把分散的记录，变成一份持续生长的个人投资记忆。</p></div><button className="secondary" onClick={()=>{download('投镜-导入模板.csv','date,ticker,side,quantity,price\n2024-02-26,sz000333,BUY,500,62.42\n','text/csv;charset=utf-8');toast('CSV 模板已下载');}}><ArrowDownToLine size={16}/>下载导入模板</button></div><div className="import-flow"><div className={`import-drop liquid-glass ${drag?'dragging':''}`} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);if(e.dataTransfer.files[0])void read(e.dataTransfer.files[0]);}}><div className="import-symbol"><Upload size={32}/></div><h2>{phase?'查看已读取的交易记录。':'把过去，交给未来的自己。'}</h2><p>{phase?`${fileName} · ${rows.length} 笔记录已解析`:'拖入 CSV 交易文件，或先用林远的六年档案体验。'}</p><div className="button-row"><button className="primary" onClick={()=>inputRef.current?.click()}>选择本地文件<Upload size={15}/></button><button className="secondary" onClick={sample}>预览林远的交易文件<ArrowRight size={15}/></button></div><input ref={inputRef} type="file" accept=".csv,text/csv" hidden onChange={e=>e.target.files?.[0]&&void read(e.target.files[0])}/><span className="quiet-tag"><LockKeyhole size={13}/>文件只在本机处理</span>{error&&<p className="form-error" role="alert">{error}</p>}</div>
 <div className="import-steps">{[{title:'整理投资事实',desc:phase?`${rows.length} 笔交易已按日期解析`:'成交、出入金、持仓和公司行动'},{title:'连接历史场景',desc:'定位证券、交易日期和当时的资料'},{title:'形成个人记忆',desc:'区分事实、想法、行为与策略假设'},{title:'开始你的完整复盘',desc:'从一笔选择，到一生投资方法'}].map((s,i)=><div className={phase>i?'done':''} key={s.title}><span>{phase>i?<Check size={17}/>:i+1}</span><div><h3>{s.title}</h3><p>{s.desc}</p></div></div>)}</div></div>
 {phase>0?<div className="import-preview liquid-glass"><div className="section-line"><b>导入预览</b><span>{rows.length} 笔 · 新上传文件为独立预览，不覆盖主展示账本</span><span>显示前 {Math.min(8,rows.length)} 笔</span></div><div className="preview-rows">{rows.slice(0,8).map((r,i)=><div key={i}><span>{r.date}</span><b>{data.assets.find(a=>a.ticker===r.ticker)?.name||r.ticker}</b><span>{r.side==='BUY'?'买入':'卖出'} {r.quantity} 股</span><span>¥{r.price}</span><button className="text-button" onClick={()=>sheet('导入记录',<div className="detail-stack"><h3>{r.ticker} · {r.date}</h3>{Object.entries(r).map(([k,v])=><div className="kv" key={k}><span>{k}</span><b>{v}</b></div>)}<p>这是本地导入预览。六路径演示继续使用已经核对的林远教学档案。</p></div>)}>查看<ArrowUpRight size={13}/></button></div>)}</div></div>:<div className="data-sources-row"><div><Database size={21}/><h3>一个主展示账户</h3><p>2020—2025 · 八只证券 · 54 笔教学交易</p></div><div><FileText size={21}/><h3>来源可追溯</h3><p>历史行情、公开披露和方法身份分开保留</p></div><div><ShieldCheck size={21}/><h3>记忆始终属于你</h3><p>原始资料、本地对话、规则与实验可导出</p></div></div>}</div>;
}

export function SettingsPage(){
 const {data,memories,lowMotion,setLowMotion,toast,sheet}=useDemo();const [font,setFont]=useState(()=>safeLoad('font-scale',100)),[sharing,setSharing]=useState(()=>safeLoad('sharing',false));
 useEffect(()=>{save('font-scale',font);document.documentElement.style.setProperty('--font-scale',String(font/100));},[font]);
 return <div className="settings-view"><div className="page-title"><div><h1>你的投镜，由你掌控。</h1><p>显示、记忆、模型与权限，都有清楚的边界。</p></div></div><div className="settings-layout"><div className="settings-group liquid-glass"><h2>阅读与播放</h2><div className="setting-row"><div><h3>减少动效</h3><p>停下背景与玻璃球，保留手动播放。</p></div><button className={`switch ${lowMotion?'on':''}`} role="switch" aria-checked={lowMotion} aria-label="减少动效" onClick={()=>setLowMotion(!lowMotion)}><i/></button></div><div className="setting-row"><div><h3>阅读字号</h3><p>对话和正文使用相同的缩放偏好。</p></div><select aria-label="阅读字号" value={font} onChange={e=>setFont(Number(e.target.value))}><option value={100}>100%</option><option value={110}>110%</option><option value={125}>125%</option></select></div><div className="setting-row"><div><h3>画面与声音</h3><p>演示默认静音。图表使用矢量绘制。</p></div><span className="pill">深色玻璃</span></div></div>
 <div className="settings-group liquid-glass"><h2>个人 AI 与权限</h2><div className="setting-row"><div><h3>当前研究模式</h3><p>使用原投镜研究工具，运行在隔离的教学档案上。</p></div><span className="pill">离线演示</span></div><div className="setting-row"><div><h3>账户研究范围</h3><p>本地演示仅使用林远的教学档案与公开资料。</p></div><span className="pill">教学账户</span></div><div className="setting-row"><div><h3>分享选定的研究记忆</h3><p>每次发布仍可选择具体内容。</p></div><button className={`switch ${sharing?'on':''}`} role="switch" aria-checked={sharing} aria-label="分享研究记忆" onClick={()=>{setSharing(!sharing);save('sharing',!sharing);}}><i/></button></div></div>
 <div className="settings-group liquid-glass"><h2>资料与你的记忆</h2><div className="setting-row"><div><h3>导出个人档案</h3><p>包括本地记忆、对话、策略与计算身份。</p></div><button className="secondary small" onClick={()=>{download('投镜-个人投资AI档案.json',JSON.stringify({memories,messages:safeLoad('messages',[]),rule:safeLoad('rule',null),data_fingerprint:data.source_fingerprint},null,2));toast('个人投资档案已导出');}}><ArrowDownToLine size={15}/>导出</button></div><div className="setting-row"><div><h3>本地演示的数据来源</h3><p>复用现有投镜的行情归档与计算结果。</p></div><button className="text-button" onClick={()=>sheet('演示与正式能力的区别',<div className="detail-stack"><h3>可以直接体验</h3><p>生涯总览、54 笔决策、六路径同步播放、规则共创、经营结构、长期记忆、本地分享与模拟跟随。</p><h3>数据身份</h3><p>真实历史日线；虚构教学成交；六路径是既有引擎结果。新规则由投镜原策略引擎计算。公司图谱来自本机已核对的报告提取。</p><h3>当前演示实现</h3><p>助手调用投镜离线研究工具。公开报告可以在当前页定位，模拟跟随使用归档净值与自选预算。</p><h3>与你原软件的关系</h3><p>这是独立网页演示，未改写原生候选、真实账户或原金融门禁。</p></div>)}>查看说明<ArrowUpRight size={15}/></button></div></div></div></div>;
}
