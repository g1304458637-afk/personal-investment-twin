import {useEffect,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {ArrowLeft,ArrowRight,ChevronLeft,ChevronRight,History,Search,X} from 'lucide-react';
import {money,safeLoad,save,type DemoData,type Fill} from './model';
import {episodeDays,episodeRange,filterEpisodes,loadEpisodeArchive,type EpisodeArchive,type EpisodeAction,type EpisodeFilter,type InvestmentEpisode} from './episodes';
import './investment-experiences.css';
import {EpisodeResearch} from './EpisodeResearch';

type Props={data:DemoData; renderDecision:(fill:Fill,onShowMarket?:()=>void)=>ReactNode; onResearch:(episode:InvestmentEpisode)=>void; initialEpisodeId?:string;onOpenEpisode?:(episodeId:string)=>void;onLeaveEpisode?:()=>void};
const signed=(value:string)=>(Number(value)>0?'+':'')+money(value);
const shortDate=(value:string)=>value.replaceAll('-','.');

function TransactionTrace({episode}:{episode:InvestmentEpisode}){
  const {start,end}=episodeRange(episode);
  const from=Date.parse(start), duration=Math.max(1,Date.parse(end)-from);
  const trades=episode.events.filter(e=>e.kind==='trade');
  return <svg className="episode-trace" viewBox="0 0 320 22" role="img" aria-label={`${trades.length} 笔买卖在本轮持有期内的位置`}>
    <line x1="6" x2="314" y1="11" y2="11" stroke="currentColor" opacity=".24"/>
    {trades.map(trade=><circle key={trade.id} cx={6+(Date.parse(trade.date)-from)/duration*308} cy="11" r="3.5" fill={trade.side==='BUY'?'#ace0f5':'#f4b29a'}><title>{trade.date} · {trade.label}</title></circle>)}
    {episode.status==='open'&&<circle cx="314" cy="11" r="4" fill="none" stroke="#a9dacb"/>}
  </svg>;
}

function EpisodeCard({episode,onOpen}:{episode:InvestmentEpisode;onOpen:()=>void}){
  return <button className="episode-card liquid-glass" onClick={onOpen} aria-label={`${episode.name}，第 ${episode.round} 轮，${episode.status==='open'?'持有中':'已结束'}，查看投资经历`}>
    <div className="episode-card-top"><div><h2>{episode.name}</h2><span>{episode.symbol} <i/> 第 {episode.round} 轮{episode.rounds>1?` / 共 ${episode.rounds} 轮`:''}</span></div><span className={`episode-status ${episode.status}`}><i/>{episode.status==='open'?'持有中':'已结束'}</span></div>
    <div className="episode-period"><time>{shortDate(episode.opened_at)}</time><span>—</span><time>{episode.closed_at?shortDate(episode.closed_at):'仍在持有'}</time></div>
    <div className="episode-outcome"><strong className={Number(episode.pnl)<0?'episode-loss':'episode-gain'}><small>¥</small>{signed(episode.display.pnl)}</strong><span>{episode.status==='open'?'截至期末盈亏':'本轮已实现盈亏'} · 含分红及成交费用</span></div>
    <div className="episode-card-bottom"><TransactionTrace episode={episode}/><div><span>{episode.trade_ids.length} 笔买卖 · {episodeDays(episode).toLocaleString('zh-CN')} 天</span><span className="episode-open">回看这轮投资<ArrowRight size={15}/></span></div></div>
  </button>;
}

function CompanyAction({event}:{event:EpisodeAction}){
  return <div className="episode-action-detail"><span>{event.date} · 公司行动</span><h3>{event.label}</h3>
    <strong>{event.kind==='dividend'?`¥${money(event.amount!)}`:`${event.ratio} 倍持股`}</strong>
    {event.ex_date&&<p>除息日 · {event.ex_date}</p>}<p>{event.note}</p>
    <details><summary>查看来源</summary><p>{event.source_ref}</p></details>
  </div>;
}

function EpisodeDetail({episode,archive,data,onBack,onResearch,renderDecision,initialEventId}:Props&{episode:InvestmentEpisode;archive:EpisodeArchive;onBack:()=>void;initialEventId?:string}){
  const [selected,setSelected]=useState(initialEventId??episode.trade_ids[0]);
  const [view,setView]=useState<'timeline'|'result'>('timeline');
  const event=episode.events.find(e=>e.id===selected)??episode.events[0];
  const fill=event.kind==='trade'?data.paths.find(p=>p.id==='actual')!.fills.find(f=>f.execution_id===event.execution_id):undefined;
  return <div className="episode-detail">
    <header className="episode-detail-heading"><button className="episode-back" onClick={onBack}><ArrowLeft size={16}/>返回行情</button><div><h1>{episode.name}<span>第 {episode.round} 轮 · 投资记录</span></h1><p>{shortDate(episode.opened_at)} — {episode.closed_at?shortDate(episode.closed_at):`仍在持有 · 截至 ${episode.as_of}`}<span> · {episode.trade_ids.length} 笔买卖</span></p></div><button className="secondary" onClick={()=>onResearch(episode)}>复盘这轮投资<ArrowRight size={15}/></button></header>
    <div className="episode-detail-summary liquid-glass"><div><span>{episode.status==='open'?'截至期末盈亏':'本轮已实现盈亏'}</span><strong className={Number(episode.pnl)<0?'episode-loss':'episode-gain'}>¥{signed(episode.display.pnl)}</strong></div><div><span>已实现交易盈亏</span><b>¥{signed(episode.display.realized_pnl)}</b></div><div><span>期末浮动盈亏</span><b>¥{signed(episode.display.unrealized_pnl)}</b></div><div><span>本轮分红</span><b>¥{money(episode.display.dividend_income)}</b></div></div>
    <div className="episode-detail-tabs" role="group" aria-label="投资经历详情"><button className={view==='timeline'?'active':''} onClick={()=>setView('timeline')}>投资时间线</button><button className={view==='result'?'active':''} onClick={()=>setView('result')}>盈亏与口径</button><span>从建仓到{episode.status==='open'?'现在':'退出'}，保留完整记录</span></div>
    {view==='timeline'?<div className="episode-timeline-workspace liquid-glass">
      <nav className="episode-timeline" aria-label="本轮投资记录">{episode.events.map(item=><button key={item.id} className={`episode-step ${item.id===selected?'selected':''}`} onClick={()=>setSelected(item.id)} aria-pressed={item.id===selected}>
        <span className={`episode-node ${item.kind==='trade'?item.side.toLowerCase():item.kind}`} aria-hidden="true"/>
        <span className="episode-step-copy"><time>{item.date}</time><b>{item.label}{item.kind==='trade'&&<small>{money(item.quantity,0)} {episode.ticker==='sh510300'?'份':'股'}</small>}</b><span>{item.kind==='trade'?`¥${money(item.price,Math.max(2,item.price.split('.')[1]?.length??0))} / ${episode.ticker==='sh510300'?'份':'股'}`:item.kind==='dividend'?`¥${money(item.amount!)}`:`持股变为 ${item.ratio} 倍`}</span></span>
        <ChevronRight size={14}/></button>)}</nav>
      <section className="episode-event-inspector" aria-label="选中记录详情" key={event.id}>
        {fill?renderDecision(fill,onBack):<CompanyAction event={event as EpisodeAction}/>}
        {event.kind==='trade'&&<div className="episode-position-change"><span>本笔成交前后持有</span><b>{money(event.position_before,0)}<ArrowRight size={13}/>{money(event.position_after,0)} {episode.ticker==='sh510300'?'份':'股'}</b><small>按原账本事件顺序计算，含已发生送转。</small></div>}
      </section>
    </div>:<div className="episode-result-panel liquid-glass"><h2>这轮投资的结果怎样组成</h2><p>{archive.method.formula}</p><dl><div><dt>累计买入成本（含费用）</dt><dd>¥{money(episode.invested_cost)}</dd></div><div><dt>期末持仓成本</dt><dd>¥{money(episode.cost_basis)}</dd></div><div><dt>期末持仓市值</dt><dd>¥{money(episode.market_value)}</dd></div></dl><p>{archive.method.cost_basis}</p><p>{archive.method.dividend_basis}</p><p>跨年筛选只选择经历，展示结果始终覆盖整轮投资；持有中的经历统一计至 {archive.as_of}。</p><details><summary>计算来源与版本</summary><p>{archive.method.engine}</p><p>{archive.method.display_rounding}</p><code>{archive.source_fingerprint}</code></details></div>}
    <footer className="episode-detail-foot">真实历史行情 · 虚构教学成交<span>点击一笔记录，查看详情或带入原有 Agent 研究</span></footer>
  </div>;
}

export function InvestmentExperiences(props:Props){
  const {data}=props;
  const [archive,setArchive]=useState<EpisodeArchive|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const [filter,setFilter]=useState<EpisodeFilter>({status:'all',year:safeLoad('decision-year','all'),query:''});
  const [selected,setSelected]=useState(props.initialEpisodeId??''),[page,setPage]=useState(0);
  const [layout,setLayout]=useState({columns:2,rows:2});
  const grid=useRef<HTMLDivElement>(null);
  const backFocus=useRef('');
  useEffect(()=>{
    const controller=new AbortController();setArchive(null);setError('');setSelected(props.initialEpisodeId??'');
    loadEpisodeArchive(data,controller.signal).then(setArchive).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[data,attempt]);
  useEffect(()=>{if(props.initialEpisodeId)setSelected(props.initialEpisodeId);},[props.initialEpisodeId]);
  useEffect(()=>{
    if(!grid.current)return;
    const observer=new ResizeObserver(([entry])=>{
      const {width,height}=entry.contentRect;
      const next={columns:width>=1050?3:width>=610?2:1,rows:height>=474?2:1};
      setLayout(old=>old.columns===next.columns&&old.rows===next.rows?old:next);
    });
    observer.observe(grid.current);return()=>observer.disconnect();
  },[archive,selected]);
  useEffect(()=>{if(!selected&&backFocus.current){document.getElementById(`episode-${backFocus.current}`)?.querySelector<HTMLButtonElement>('button')?.focus({preventScroll:true});backFocus.current='';}},[selected]);
  const change=(patch:Partial<EpisodeFilter>)=>{setFilter(old=>({...old,...patch}));setPage(0);if(patch.year)save('decision-year',patch.year);};
  const visible=filterEpisodes(archive?.episodes??[],filter);
  const size=layout.columns*layout.rows, pages=Math.max(1,Math.ceil(visible.length/size)), currentPage=Math.min(page,pages-1);
  const episode=archive?.episodes.find(ep=>ep.id===selected);
  return <section className="decisions-view investment-experiences" aria-label="投资经历">
    {archive&&episode?<EpisodeResearch data={data} episode={episode} key={episode.id}
      onBack={()=>{backFocus.current=selected;setSelected('');props.onLeaveEpisode?.();}}
      renderDetails={(onClose,eventId)=><EpisodeDetail {...props} archive={archive} episode={episode} key={eventId??'all'} initialEventId={eventId} onBack={onClose}/>}/>:<>
      <header className="episodes-heading"><div><h1>把每一轮投资，看完整。</h1><p>从第一次买入，到加减仓与退出。清仓后的再次建仓，是新的经历。</p></div>{archive&&<div className="episodes-counts"><span><b>{archive.summary.episode_count}</b> 轮投资</span><i/><span><b>{archive.summary.trade_count}</b> 笔买卖</span></div>}</header>
      <div className="episodes-controls"><div className="episode-filters" role="group" aria-label="按持仓状态筛选">{([{id:'all',name:'全部'},{id:'open',name:'持有中'},{id:'closed',name:'已结束'}] as const).map(item=><button key={item.id} onClick={()=>change({status:item.id})} className={filter.status===item.id?'active':''} aria-pressed={filter.status===item.id}>{item.name}{archive&&<span>{item.id==='all'?archive.summary.episode_count:item.id==='open'?archive.summary.open_count:archive.summary.closed_count}</span>}</button>)}</div>
        <div className="episode-search-controls"><select aria-label="筛选投资经历年份" value={filter.year} onChange={e=>change({year:e.target.value})}><option value="all">全部年份</option>{data.lifetime.years.map(y=><option key={y.year} value={y.year}>{y.year} 年内持有</option>)}</select><label className="episode-search"><Search size={15}/><input aria-label="搜索投资经历" placeholder="搜索公司、代码或日期" value={filter.query} onChange={e=>change({query:e.target.value})}/>{filter.query&&<button aria-label="清除搜索" onClick={()=>change({query:''})}><X size={13}/></button>}</label></div>
      </div>
      <div className="episodes-grid" ref={grid} style={{'--episode-cols':layout.columns,'--episode-rows':layout.rows} as CSSProperties}>
        {error?<div className="episode-state" role="alert"><p>{error}</p><button className="secondary" onClick={()=>setAttempt(x=>x+1)}>重新载入</button></div>:!archive?<div className="episode-state" role="status">正在整理投资经历…</div>:visible.length?visible.slice(currentPage*size,(currentPage+1)*size).map(ep=><div className="episode-cell" id={`episode-${ep.id}`} tabIndex={-1} key={ep.id}><EpisodeCard episode={ep} onOpen={()=>props.onOpenEpisode?props.onOpenEpisode(ep.id):setSelected(ep.id)}/></div>):<div className="episode-state"><History size={25}/><h2>没有符合条件的投资经历</h2><p>可以试试其他公司或年份。</p><button className="secondary" onClick={()=>change({status:'all',year:'all',query:''})}>查看全部经历</button></div>}
      </div>
      <footer className="episodes-footer"><span>{filter.year==='all'?'按建仓日期由近到远':`${filter.year} 年内持有过的完整经历`}<small> · 计至 {archive?.as_of??data.dates.at(-1)}</small></span><div className="episode-pagination" aria-label="投资经历分页"><span aria-live="polite">{visible.length} 轮 · {currentPage+1} / {pages}</span><button aria-label="上一页投资经历" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}><ChevronLeft size={17}/></button><button aria-label="下一页投资经历" disabled={currentPage===pages-1} onClick={()=>setPage(currentPage+1)}><ChevronRight size={17}/></button></div></footer>
      <p className="episode-provenance">真实历史行情 · 虚构教学成交 · 分红沿用演示账户税前口径</p>
    </>}
  </section>;
}
