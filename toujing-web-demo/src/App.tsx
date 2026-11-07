import {createContext,useContext,useEffect,useRef,useState, type ReactNode} from 'react';
import {ArrowDownToLine,ArrowRight,ArrowUpRight,AudioLines,BookOpen,Brain,Building2,Check,ChevronDown,ChevronLeft,ChevronRight,Clock3,Database,Expand,FileText,FolderOpen,GitBranch,History,Layers3,Maximize2,MessageCircle,MoreHorizontal,PanelLeftClose,PanelLeftOpen,Play,Plus,Search,Send,Settings2,ShieldCheck,Sparkles,Trash2,Users,Wallet,X} from 'lucide-react';
import {COLORS,DemoData,Fill,LABELS,Rule,download,money,nearestIndex,pct,safeLoad,save,wan} from './model';
import {CareerDashboard} from './CareerDashboard';
import {beginResearch,defaultScope,scopeKey,scopeLabel,statusLabel,taskText,runtime,taskAccess,presentTask,type CapabilityId,type ResearchScope,type ResearchTask} from './alignment';
import {DocumentReader,FeatureDirectory,RuntimePanel,ScopeControl,ResearchResult,ResultView} from './NativeTools';
import {ResearchLibraryPanel} from './ResearchLibraryPanel';
import {InvestmentExperiences} from './InvestmentExperiences';
import {AskToujing} from './AskToujing';
import {episodeRange} from './episodes';
import {Replay,Strategies,Company,Community,DataPage,SettingsPage} from './Pages';
import {EntryExperience, type EntryResult, type ImportedPreview} from './entry/EntryExperience';

// The background is part of the user's pinned visual identity.
const BG_VIDEO = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260511_230229_7c9bc431-46cf-489a-948d-e8144d8eb5d4.mp4';

type Nav='investment'|'strategies'|'company'|'community'|'data'|'settings';
type Tab='career'|'decisions'|'memory'|'ask'|'replay';
export type Memory={id:string;source?:{task_id?:string;selection?:ResearchScope};revisions?:{body:string;date:string}[];withdrawn?:boolean;type:'事实'|'用户想法'|'行为发现'|'策略假设';title:string;body:string;date:string};
type Message={id:string;role:'user'|'assistant';text:string;scope:string;context?:ResearchScope;task?:ResearchTask;error?:string;action?:'strategy'|'replay'|'memory'|'company'};
type DetailPanel={id:string;title:string;content:ReactNode};
type ContextType={data:DemoData;toast:(s:string)=>void;sheet:(title:string,content:ReactNode)=>void;closeSheet:()=>void;ask:(q?:string,scope?:ResearchScope)=>void;prepareQuestion:(question:string,scope:ResearchScope)=>void;setAssistantVisible:(visible:boolean)=>void;openInvestmentEpisode:(id:string)=>void;researchScope:ResearchScope;setResearchScope:(s:ResearchScope)=>void;openCapability:(id:CapabilityId)=>void;setExperiment:(x:DemoData)=>void;replay:(ticker?:string,play?:boolean,focus?:number[],date?:string)=>void;go:(nav:Nav,tab?:Tab)=>void;ticker:string;setTicker:(s:string)=>void;customRule:Rule|null;setCustomRule:(r:Rule)=>void;memories:Memory[];setMemories:(x:Memory[])=>void;lowMotion:boolean;setLowMotion:(b:boolean)=>void};
const Ctx=createContext<ContextType>(null!);
export const useDemo=()=>useContext(Ctx);
export const IconButton=({label,onClick,children,className=''}:{label:string;onClick:()=>void;children:ReactNode;className?:string})=><button className={`icon-button ${className}`} aria-label={label} title={label} onClick={onClick}>{children}</button>;
export const Orb=({size='small',active=false}:{size?:'tiny'|'small'|'large';active?:boolean})=><span className={`orb orb-${size} ${active?'is-active':''}`}><img src="/orb.png" alt="投镜蓝橙玻璃球" draggable="false"/></span>;

const NAVS:{id:Nav;label:string;icon:typeof Wallet}[]=[{id:'investment',label:'我的投资',icon:Wallet},{id:'strategies',label:'我的策略',icon:GitBranch},{id:'company',label:'公司研究',icon:Building2},{id:'community',label:'研究社区',icon:Users},{id:'data',label:'资料与账户',icon:Database},{id:'settings',label:'设置',icon:Settings2}];
const historyReplaceNav=(nav:Nav)=>window.history.replaceState(null,'',nav==='investment'?'#/investments':'#/'+nav);
const initialMemories:Memory[]=[
 {id:'1',type:'事实',title:'六年的投资足迹',body:'54 笔教学成交，8 只证券，13 轮投资经历。交易、资金与逐日状态来自同一份档案。',date:'2025-12-31'},
 {id:'2',type:'行为发现',title:'连续买入时，7 次价格低于前一次',body:'11 次连续买入中，7 次成交价低于上一次买入；其余 4 次是相反样本。可以逐笔查看，尚不推断当时的想法。',date:'2025-12-31'},
 {id:'3',type:'用户想法',title:'给长期投资一点耐心',body:'“我希望保留分批买入，但不让单只股票决定整个账户。”——演示用户的确认记录。',date:'2025-12-31'},
 {id:'4',type:'策略假设',title:'用仓位上限检验自己的习惯',body:'单只上限 20%，首次投入 10%，每次修改保存独立版本；与个人镜像在相同资金计划下比较。',date:'2025-12-31'}
];

export default function App(){
 const [data,setData]=useState<DemoData|null>(null),[error,setError]=useState('');
 const [entryVisible,setEntryVisible]=useState(true),[entryImport,setEntryImport]=useState<ImportedPreview|null>(null);
 const [entryPlaybackPaused,setEntryPlaybackPaused]=useState(false);
 const [entrySample,setEntrySample]=useState(()=>new URLSearchParams(window.location.search).get('awakening')==='play');
 const [nav,setNav]=useState<Nav>(()=>({community:'community',strategies:'strategies',company:'company',data:'data',settings:'settings'} as Record<string,Nav>)[location.hash.slice(2)]??'investment'),[tab,setTab]=useState<Tab>('career'),[collapsed,setCollapsed]=useState(false),[ticker,setTicker]=useState('sz000333');
 const [drawerOpen,setDrawerOpen]=useState(true);
 const [episodeToOpen,setEpisodeToOpen]=useState('');
 const [notice,setNotice]=useState(''),[panels,setPanels]=useState<DetailPanel[]>([]),[chatOpen,setChatOpen]=useState(false),[chatInput,setChatInput]=useState(''),[thinking,setThinking]=useState(false);
 const [messages,setMessages]=useState<Message[]>(()=>safeLoad('messages',[])),[memories,setMemories]=useState<Memory[]>(()=>safeLoad('memories',initialMemories));
 const [lowMotion,setLowMotion]=useState(()=>safeLoad('low-motion',false)),[customRule,setCustomRule]=useState<Rule|null>(()=>safeLoad('rule',null));
 const [researchScope,setResearchScope]=useState<ResearchScope|null>(()=>safeLoad('research-scope',null));
 const [activeTask,setActiveTask]=useState<ResearchTask|null>(null);
 const generation=useRef(0),alive=useRef(true),inFlight=useRef(false);
 const drawer=panels.at(-1);
 const clearPanels=()=>setPanels([]);
 const closeSheet=()=>setPanels(stack=>stack.slice(0,-1));
 const [search,setSearch]=useState(false),[searchText,setSearchText]=useState(''),[tour,setTour]=useState(-1);const chatEnd=useRef<HTMLDivElement>(null),chatComposer=useRef<HTMLTextAreaElement>(null);
 useEffect(()=>{fetch('/demo-data.json').then(r=>{if(!r.ok)throw new Error('档案读取失败');return r.json();}).then(setData).catch(e=>setError(e.message));},[]);
 // Migrate a live pre-dashboard tab during Vite hot updates.
 useEffect(()=>{if((tab as string)==='ai')setTab('career');},[tab]);
 useEffect(()=>{save('research-scope',researchScope);},[researchScope]);
 useEffect(()=>{document.documentElement.style.setProperty('--font-scale',String(safeLoad('font-scale',100)/100));},[]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
 useEffect(()=>{save('messages',messages);chatEnd.current?.scrollIntoView({behavior:lowMotion?'instant':'smooth',block:'end'});},[messages,thinking]);
 useEffect(()=>{save('memories',memories);},[memories]);useEffect(()=>{save('rule',customRule);},[customRule]);useEffect(()=>{save('low-motion',lowMotion);document.documentElement.dataset.motion=lowMotion?'reduced':'full';},[lowMotion]);
 useEffect(()=>{if(notice){const t=setTimeout(()=>setNotice(''),3800);return()=>clearTimeout(t);}},[notice]);
 useEffect(()=>{
  const openSearch=(e:KeyboardEvent)=>{
   if((e.metaKey||e.ctrlKey)&&e.key==='k'){
    e.preventDefault();
    setSearch(v=>!v);
   }
  };
  window.addEventListener('keydown',openSearch);
  return()=>window.removeEventListener('keydown',openSearch);
 },[]);
 const toast=(s:string)=>setNotice(s);
 const go=(n:Nav,t?:Tab)=>{
  if(data){
   const origin=n==='company'?'company':n==='strategies'?'strategy':n==='community'?'community':'career';
   const instrument=n==='company'&&!['sz000333','sz000651','sh600690'].includes(ticker)?'sz000333':ticker;
   setResearchScope(defaultScope(data,instrument,origin));
  }
  setNav(n);
  historyReplaceNav(n);
  if(t)setTab(t);
  clearPanels();
  setChatOpen(false);
 };
 const replay=(t=ticker)=>{
  if(data)setResearchScope(defaultScope(data,t));
  setTicker(t);
  setTab('replay');
 };
 const sheet=(title:string,content:ReactNode)=>{
  setDrawerOpen(true);
  setPanels(stack=>[...stack,{id:crypto.randomUUID(),title,content}]);
 };
 const scope=researchScope??(data?defaultScope(data,ticker,nav==='company'?'company':'career'):null);
 const openCapability=(id:CapabilityId)=>{if(!data||!scope)return;sheet('研究与资料',<RuntimePanel id={id} scope={scope} data={data} onAsk={ask}/>);};
 const pollTask=async(task:ResearchTask,messageId:string,stamp:number,context:ResearchScope)=>{
  let current=task;
  while(alive.current&&stamp===generation.current){
   setActiveTask(current);setMessages(ms=>ms.map(m=>m.id===messageId?{...m,task:current,text:taskText(current),error:current.error_code??undefined}:m));
   if(!['running','cancel_requested'].includes(current.status))break;
   await new Promise(r=>setTimeout(r,800));
   const response=await runtime<{task:ResearchTask}>('workbench.research.status',{task_id:current.task_id,...taskAccess(current)});current=presentTask(response.task,context,taskAccess(current));
  }
  if(stamp===generation.current){inFlight.current=false;setThinking(false);setActiveTask(null);}
 };
 const send=async(question:string,override?:ResearchScope)=>{
  const q=question.trim();const current=override??scope;
  if(!q||!data||!current)return;
  if(inFlight.current){toast('这轮研究还在进行，可以完成或取消后继续。');return;}
  inFlight.current=true;
  setChatInput('');setChatOpen(true);setResearchScope(current);const frozen={...current};const messageId=crypto.randomUUID();const stamp=++generation.current;
  const previous=messages.filter(m=>m.task?.status==='completed'&&m.context&&scopeKey(m.context)===scopeKey(frozen)).at(-1)?.task;
  setMessages(ms=>[...ms,{id:crypto.randomUUID(),role:'user',text:q,scope:scopeLabel(frozen),context:frozen},{id:messageId,role:'assistant',text:'',scope:scopeLabel(frozen),context:frozen}]);setThinking(true);
  const conversation=messages.filter(m=>m.task?.library_conversation_id).at(-1)?.task?.library_conversation_id;
  try{
   const response=await beginResearch(q,frozen,previous,typeof conversation==='string'?conversation:undefined);
   if(stamp!==generation.current){
    if(response.task.status==='running')void runtime('workbench.research.cancel',{task_id:response.task.task_id,...taskAccess(response.task)}).catch(()=>{});
    return;
   }
   await pollTask(response.task,messageId,stamp,frozen);
  }catch(e){
   if(stamp===generation.current){
    setMessages(ms=>ms.map(m=>m.id===messageId?{...m,error:(e as Error).message}:m));
    inFlight.current=false;
    setThinking(false);
    setActiveTask(null);
   }
  }
 };
 const closeAssistant=()=>{setChatOpen(false);if(panels.length)setDrawerOpen(true);};
 const ask=(q?:string,override?:ResearchScope)=>{setChatOpen(true);setDrawerOpen(false);if(override)setResearchScope(override);if(q)void send(q,override);};
 // Discovery examples prepare a question; only the composer submits it.
 const prepareQuestion=(question:string,selectedScope:ResearchScope)=>{
  if(inFlight.current){toast('这轮研究还在进行，可以完成或取消后继续。');return;}
  setResearchScope(selectedScope);setChatInput(question);setDrawerOpen(false);setChatOpen(true);
  requestAnimationFrame(()=>chatComposer.current?.focus());
 };
 const cancel=async()=>{if(activeTask){try{const r=await runtime<{task:ResearchTask}>('workbench.research.cancel',{task_id:activeTask.task_id,...taskAccess(activeTask)});setActiveTask(r.task);}catch(e){toast((e as Error).message);}}};
 const resume=async(m:Message)=>{if(!m.task||inFlight.current)return;const stamp=++generation.current;inFlight.current=true;setThinking(true);try{const r=await runtime<{task:ResearchTask}>('workbench.research.resume',{task_id:m.task.task_id,operation_id:crypto.randomUUID(),use_model:false,...taskAccess(m.task),...(m.context?.origin==='company'?{}:{research_focus:m.context?.focus??'public_price'})});await pollTask(presentTask(r.task,m.context??scope!,taskAccess(m.task)),m.id,stamp,m.context??scope!);}catch(e){if(stamp===generation.current){toast((e as Error).message);inFlight.current=false;setThinking(false);}}};
 const citation=async(message:Message,id:string)=>{
  if(!message.task)return;
  try{
   const result=await runtime('workbench.research.citation',{task_id:message.task.task_id,evidence_id:id,...taskAccess(message.task)});
   const e=result.evidence;
   const position=typeof e.page==='number'&&typeof e.document_id==='string'&&message.context?{
    document_id:e.document_id,page:e.page,start:e.start??0,end:e.end??0
   }:undefined;
   sheet('引用与原始依据',<div className="detail-stack">
    <p>{message.scope}</p><h3>{e.title??'引用记录'}</h3><p className="message-text">{e.text}</p>
    {result.snapshot_current===false&&<p>{result.notice}</p>}
    {position&&<button className="secondary" onClick={()=>sheet('报告原文',<DocumentReader scope={{...message.context!,origin:'company',focus:'public_price',selection_object:position}} onAsk={ask}/>)}>定位报告第 {position.page} 页<FileText size={14}/></button>}
    <details><summary>来源、方法与版本</summary><ResultView value={{证据:e,来源:result.sources}}/></details>
   </div>);
  }catch(e){toast((e as Error).message);}
 };
 const remember=(m:Message)=>{const record:Memory={id:crypto.randomUUID(),type:'行为发现',title:m.task?.question??'研究结论',body:m.text,date:new Date().toISOString().slice(0,10),source:{task_id:m.task?.task_id,selection:m.context}};sheet('确认加入长期记忆',<div className="detail-stack"><h3>{record.title}</h3><p className="message-text">{record.body}</p><small>研究结论 · 保存原任务和研究范围 · 今天确认</small><button className="primary" onClick={()=>{setMemories(ms=>[...ms,record]);closeSheet();toast('已保存研究及其来源，可在长期记忆中修订');}}>确认保存<Check size={14}/></button></div>);};
 if(!data)return <div className="boot"><Orb size="large"/><h1>正在唤醒你的投镜</h1><p>{error||'载入六年的行情、决策与投资记忆…'}</p>{error&&<button onClick={()=>location.reload()}>重新读取</button>}</div>;
 const finishEntry=(result:EntryResult)=>{const target:Nav=result.kind==='sample'?'investment':'data';setEntryImport(result.kind==='import'?result.preview:null);setNav(target);setTab('career');historyReplaceNav(target);setEntryVisible(false);};
 const discussEntry=(question:string)=>{
  newChat();
  finishEntry({kind:'sample'});
  const first=data.lifetime.adds[0];
  const fill=first&&data.paths[0].fills.find(f=>f.date===first.date&&f.ticker===first.ticker&&f.side==='BUY');
  if(fill)setResearchScope({...defaultScope(data,fill.ticker,'decision'),start:fill.date,end:fill.date,kind:'execution',execution_id:fill.execution_id});
  setDrawerOpen(false);setChatInput(fill?`${question}\n从 ${fill.date} 的${fill.name}买入记录开始。`:question);setChatOpen(true);
 };
 const openHere=(n:Nav,t?:Tab)=>{if(n==='investment'){sheet(t==='memory'?'长期记忆':t==='decisions'?'投资经历':'投资生涯',t==='memory'?<Memories/>:t==='decisions'?<Decisions/>:<Career/>);}else sheet(NAVS.find(x=>x.id===n)!.label,n==='strategies'?<Strategies/>:n==='company'?<Company/>:n==='community'?<Community/>:n==='data'?<DataPage/>:<SettingsPage/>);};
 const replayHere=(t=ticker,play=false,paths=[0,1,2,3,4,5],date?:string)=>{
  sheet('同场回放',<div className="inline-replay"><Replay initialTicker={t} initialDate={date} initialPlaying={play} initialPaths={paths}/></div>);
 };
 const openInvestmentEpisode=(id:string)=>{setEpisodeToOpen(id);setNav('investment');setTab('decisions');historyReplaceNav('investment');clearPanels();};
 const ctx:ContextType={data,toast,sheet,closeSheet,ask,prepareQuestion,setAssistantVisible:setChatOpen,openInvestmentEpisode,replay:replayHere,go:openHere,ticker,setTicker,customRule,setCustomRule,memories,setMemories,lowMotion,setLowMotion,researchScope:scope!,setResearchScope,openCapability,setExperiment:setData};

 const newChat=()=>{generation.current++;inFlight.current=false;if(activeTask)void runtime('workbench.research.cancel',{task_id:activeTask.task_id,...taskAccess(activeTask)}).catch(()=>{});setThinking(false);setActiveTask(null);if(messages.length&&!messages.some(m=>m.task?.library_conversation_id)){const previous=safeLoad<{id:string;title:string;messages:Message[]}[]>('chat-archives',[]);save('chat-archives',[...previous,{id:crypto.randomUUID(),title:messages.find(m=>m.role==='user')?.text||'投资研究',messages}]);}setMessages([]);};
 const loadConversation=(tasks:ResearchTask[])=>{
  newChat();
  const restored=tasks.slice().reverse().flatMap(task=>{
   const origin=task.origin_session_id?'company':task.selection.kind==='execution'?'decision':'replay';
   const context:ResearchScope={...defaultScope(data,task.selection.instrument_id,origin),...task.selection,
    origin,focus:task.origin_session_id||task.research_focus==='public_price'?'public_price':'personal_review'};
   const presented=presentTask(task,context,taskAccess(task));
   const label=scopeLabel(context);
   const items:Message[]=[
    {id:task.task_id+'-question',role:'user',text:task.question,scope:label,context},
    {id:task.task_id,role:'assistant',text:taskText(presented),scope:label,context,task:presented,error:task.error_code??undefined}
   ];
   return items;
  });
  setMessages(restored);
  if(restored.at(-1)?.context)setResearchScope(restored.at(-1)!.context!);
  clearPanels();
  setChatOpen(true);
 };
 const history=()=>sheet('本地对话',<div className="detail-stack">
  <button className="primary" onClick={()=>{newChat();closeSheet();setChatOpen(true);}}><Plus size={16}/>新建对话</button>
  <ResearchLibraryPanel onOpen={loadConversation} onDeleted={id=>{
   if(messages.some(m=>m.task?.library_conversation_id===id)){
    generation.current++;inFlight.current=false;setActiveTask(null);setThinking(false);setMessages([]);
   }
   save('chat-archives',safeLoad<{id:string;messages:Message[]}[]>('chat-archives',[])
    .filter(a=>!a.messages.some(m=>m.task?.library_conversation_id===id)));
  }}/>
  {safeLoad<{id:string;title:string;messages:Message[]}[]>('chat-archives',[]).some(a=>a.messages.every(m=>!m.task))&&<details><summary>此前的浏览器对话</summary>
   {safeLoad<{id:string;title:string;messages:Message[]}[]>('chat-archives',[]).filter(a=>a.messages.every(m=>!m.task)).map(a=><button className="history-item" key={a.id} onClick={()=>{newChat();setMessages(a.messages);closeSheet();}}><History size={16}/>{a.title}</button>)}
  </details>}
  <button className="text-button" onClick={()=>download('投镜-对话档案.json',JSON.stringify(messages,null,2))}>导出当前对话<ArrowDownToLine size={15}/></button>
 </div>);
 const tours=[
  {title:'我的投资',body:'投资生涯集中展示资产、持仓与交易数据；投资经历回到逐笔选择，问投镜负责解释与追问。'},
  {title:'同场回放',body:'在我的投资中播放六条路径，框选主图后直接解释。'},
  {title:'我的策略',body:'输入规则，确认计算，然后在当前页打开实验。'},
  {title:'公司研究',body:'查看经营节点的原文，继续核对财务与估值。'},
  {title:'研究社区',body:'在同一行情对照他人策略，预览独立模拟资金。'}
 ];
 return <Ctx.Provider value={ctx}><div className={`app ${collapsed?'nav-collapsed':''} ${tab==='replay'&&nav==='investment'?'replay-mode':''} ${tab==='career'&&nav==='investment'?'career-dashboard-mode':''}`}>
  <video className="backdrop-video" src={BG_VIDEO} autoPlay={!lowMotion&&!entryPlaybackPaused} muted loop playsInline preload="auto" aria-hidden="true" ref={v=>{if(v){if(lowMotion||entryPlaybackPaused)v.pause();else void v.play().catch(()=>{});}}}/>
  {entryVisible?<EntryExperience data={data} fills={data.paths[0].fills} reducedMotion={lowMotion} onFinish={finishEntry} onDiscuss={discussEntry} onPlaybackPause={setEntryPlaybackPaused} sampleInitially={entrySample}/>:<>
  <aside className="sidebar liquid-glass"><button className="brand" onClick={()=>go('investment','career')} title="回到投资生涯"><Orb/><span><strong>投镜</strong><small>你的个人投资 AI</small></span></button>
   <div className="nav-body"><div className="account-switch"><span className="avatar">林</span><span><b>林远的投资世界</b><small><i className="status-dot"/>本地演示档案</small></span><ChevronDown size={14}/></div>
    <nav aria-label="主导航">{NAVS.slice(0,4).map(n=><button key={n.id} className={nav===n.id?'active':''} onClick={()=>go(n.id,n.id==='investment'?'career':undefined)} title={n.label}><n.icon size={19} strokeWidth={1.6}/><span>{n.label}</span>{nav===n.id&&<span className="nav-light"/>}</button>)}</nav>
    <div className="sidebar-memory" onClick={()=>openHere('investment','memory')} role="button" tabIndex={0} onKeyDown={e=>e.key==='Enter'&&openHere('investment','memory')}><span className="memory-signal"><Brain size={16}/>共同记忆</span><strong>2,192<span>天</span></strong><p>每一次选择，都有迹可循。</p><div className="tiny-years"><span>2020</span><span>2025</span></div></div>
   </div>
   <div className="nav-bottom">{NAVS.slice(4).map(n=><button key={n.id} className={nav===n.id?'active':''} onClick={()=>go(n.id)} title={n.label}><n.icon size={18}/><span>{n.label}</span></button>)}<button className="collapse-toggle" onClick={()=>setCollapsed(v=>!v)} title={collapsed?'展开导航':'收起导航'}>{collapsed?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>}<span>收起导航</span></button></div>
  </aside>
  <div className="app-main"><header className="topbar"><div className="breadcrumb"><span>投镜</span><ChevronRight size={13}/><b>{NAVS.find(n=>n.id===nav)?.label}</b>{nav==='investment'&&tab==='replay'&&<><ChevronRight size={13}/><span>同场回放</span></>}</div><div className="top-actions"><button className="search-button" onClick={()=>setSearch(true)}><Search size={16}/><span>搜索公司、决策、记忆</span><kbd>⌘ K</kbd></button><button className="demo-tag" onClick={()=>sheet('功能与原软件对应',<FeatureDirectory onOpen={openCapability}/>)}>功能与数据</button><button className="text-button" onClick={()=>{setEntrySample(true);setEntryVisible(true);setChatOpen(false);clearPanels();}}><Play size={13}/>生涯唤醒</button><button className="text-button" onClick={()=>setTour(0)}><Play size={13}/>演示导览</button><button className={`assistant-toggle ${chatOpen?'active':''}`} onClick={()=>chatOpen?closeAssistant():setChatOpen(true)}><Orb size="tiny"/><span>问投镜</span></button></div></header>
   <div className={`workspace ${chatOpen?'with-chat':''}`}><main className="page" data-page={nav} data-tab={nav==='investment'?tab:undefined} key={nav}>
    {nav==='investment'&&<>{tab!=='replay'&&<div className="page-tabs">{([{id:'career',label:'投资生涯'},{id:'decisions',label:'投资经历'},{id:'ask',label:'问投镜'}]as const).map(t=><button key={t.id} className={tab===t.id?'selected':''} onClick={()=>setTab(t.id)}>{t.label}</button>)}<button className="tab-replay" onClick={()=>replay(ticker)}><Play size={13}/>同场回放<ArrowUpRight size={13}/></button></div>}{tab==='career'?<Career/>:tab==='decisions'?<Decisions main initialEpisodeId={episodeToOpen} onLeaveEpisode={()=>setEpisodeToOpen('')}/>:tab==='ask'?<AskToujing data={data} busy={thinking} onQuestion={prepareQuestion} onInvestments={()=>setTab('decisions')} onCareer={()=>setTab('career')} onReplay={()=>replay(ticker)} onMemory={()=>openHere('investment','memory')} onCompany={()=>go('company')}/>:tab==='memory'?<Memories/>:<Replay initialPlaying onBack={()=>setTab('career')}/>}</>}
    {nav==='strategies'&&<Strategies/>}{nav==='company'&&<Company/>}{nav==='community'&&<Community/>}{nav==='data'&&<DataPage initialImport={entryImport} onImported={setEntryImport}/>} {nav==='settings'&&<SettingsPage/>}
   </main>
   {chatOpen&&<aside className="chat-panel liquid-glass"><div className="chat-heading"><Orb size="tiny"/><div><b>投镜</b><small>原投镜研究工具 · 离线分析</small></div><IconButton label="新建对话" onClick={newChat}><Plus size={16}/></IconButton><IconButton label="对话历史" onClick={history}><History size={17}/></IconButton><IconButton label="收起助手" onClick={closeAssistant}><X size={17}/></IconButton></div>{drawer&&!drawerOpen&&<button className="return-artifact" onClick={()=>setDrawerOpen(true)}>继续：{drawer.title}<ArrowRight size={13}/></button>}<ScopeControl value={scope!} onChange={setResearchScope} data={data}/><div className="chat-messages">{!messages.length&&<div className="chat-welcome"><Orb size="large"/><h2>{scope?.origin==='decision'?<>看懂这轮投资，<br/>从一段行情开始。</>:<>从你的经历，<br/>找到下一次选择。</>}</h2><p>{scope?.origin==='decision'?'框选左侧行情，我会带着这段日期和你的买卖一起研究。':'我记得你的历史，也陪你检验新的想法。'}</p>{(scope?.origin==='decision'?['结合这段行情，复盘我的买卖','当时有哪些影响股价的信息？','这轮加减仓怎样改变了结果？']:['我有哪些重复的投资习惯？','把我的操作提炼成一套策略','回到当时，看看为什么涨跌']).map(q=><button onClick={()=>send(q)} key={q}>{q}<ArrowUpRight size={14}/></button>)}</div>}
    {messages.map(m=><article className={`message ${m.role}`} key={m.id}>{m.role==='assistant'&&<div className="message-author"><Orb size="tiny"/>投镜</div>}<small>{m.scope}</small><div className="message-text">{m.text}</div>{m.error&&<p className="form-error">{m.error}</p>}{m.task&&<><small>{statusLabel[m.task.status]??m.task.status} · {m.task.state.completed_tools?.length??0} 项工具已完成</small><ResearchResult task={m.task} onCitation={id=>void citation(m,id)} onRemember={()=>remember(m)} onFollowup={q=>ask(q,m.context)}/>{['cancelled','failed','interrupted'].includes(m.task.status)&&<button className="secondary small" disabled={thinking} onClick={()=>void resume(m)}>继续这个研究</button>}</>}{m.action&&<button className="message-action" onClick={()=>{if(m.action==='strategy')openHere('strategies');else if(m.action==='company')openHere('company');else if(m.action==='memory')openHere('investment','memory');else replayHere();}}>{m.action==='strategy'?'一起写成策略':m.action==='company'?'构建公司全貌':m.action==='memory'?'查看记忆与证据':'在行情上看见差异'}<ArrowRight size={15}/></button>}</article>)}{thinking&&<div className="thinking"><Orb size="tiny"/><span>正在运行原有研究工具<span className="thinking-dots">…</span></span></div>}<div ref={chatEnd}/></div>
    <form className="chat-composer" onSubmit={e=>{e.preventDefault();send(chatInput);}}><textarea ref={chatComposer} value={chatInput} onChange={e=>setChatInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send(chatInput);}}} placeholder={scope?.origin==='decision'?'解释选中的行情，或继续追问这轮投资…':'问问过去，也聊聊下一个想法…'} rows={3} aria-label="向投镜提问"/><div><span><span className="status-dot"/>教学账户 · 原运行时</span>{thinking&&<button type="button" className="text-button" disabled={!activeTask} onClick={()=>void cancel()}>取消研究</button>}<button className="send-button" type="submit" aria-label="发送问题" disabled={!chatInput.trim()||thinking}><ArrowRight size={18}/></button></div></form><div className="chat-footer">记忆属于你 · 对话保存在本机<ShieldCheck size={13}/></div></aside>}
   </div>
  </div>
  {panels.map((panel,index)=>{
    const visible=drawerOpen&&index===panels.length-1;
    return <div key={panel.id} hidden={!visible}><Drawer active={visible&&!search} title={panel.title} onClose={closeSheet}>{panel.content}</Drawer></div>;
  })}
  {search&&<Drawer title="搜索你的投资世界" onClose={()=>setSearch(false)}><input className="search-field" autoFocus placeholder="输入公司、日期或记忆关键词" value={searchText} onChange={e=>setSearchText(e.target.value)}/><div className="detail-stack">{data.assets.filter(a=>`${a.name}${a.symbol}`.includes(searchText)).map(a=><button className="search-result" key={a.ticker} onClick={()=>{setSearch(false);replayHere(a.ticker);}}><Building2 size={18}/><span>{a.name}<small>{a.symbol} · {a.sector}</small></span><ArrowUpRight size={15}/></button>)}{memories.filter(m=>!m.withdrawn&&m.title.includes(searchText)).map(m=><button className="search-result" key={m.id} onClick={()=>{setSearch(false);sheet(m.title,<MemoryDetails memory={m}/>);}}><Brain size={18}/><span>{m.title}<small>{m.type}</small></span></button>)}</div></Drawer>}
  {notice&&<div className="toast" role="status"><Check size={16}/>{notice}</div>}
  {tour>=0&&<div className="tour-popover liquid-glass"><button className="tour-close" aria-label="关闭导览" onClick={()=>setTour(-1)}><X size={16}/></button><div className="tour-dots">{tours.map((t,i)=><button key={i} title={t.title} className={i===tour?'active':''} onClick={()=>setTour(i)}/>)}</div><h3>{tours[tour].title}</h3><p>{tours[tour].body}</p><button className="text-button" onClick={()=>{if(tour===tours.length-1){setTour(-1);}else{setTour(tour+1);}}}>{tour===tours.length-1?'开始自由探索':'下一幕'}<ArrowRight size={16}/></button></div>}
  </>}
 </div></Ctx.Provider>;
}

export function Drawer({title,children,onClose,active=true}:{title:string;children:ReactNode;onClose:()=>void;active?:boolean}){
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(!active)return;
  const previous=document.activeElement as HTMLElement|null;
  ref.current?.focus();
  const onKey=(e:KeyboardEvent)=>{
   if(e.key==='Escape'){e.stopPropagation();onClose();return;}
   if(e.key!=='Tab')return;
   const items=Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),textarea:not([disabled]),select:not([disabled]),summary,[tabindex="0"]')??[])
    .filter(item=>item.getClientRects().length>0);
   const first=items[0],last=items.at(-1);
   if(!first||!last){e.preventDefault();return;}
   const outside=!items.includes(document.activeElement as HTMLElement);
   if(outside||(e.shiftKey?document.activeElement===first:document.activeElement===last)){
    e.preventDefault();
    (e.shiftKey?last:first).focus();
   }
  };
  document.addEventListener('keydown',onKey);
  return()=>{
   document.removeEventListener('keydown',onKey);
   if(previous?.isConnected&&previous.getClientRects().length)previous.focus();
  };
 },[active]);
 return <div className="drawer-backdrop" onClick={onClose}><div className="drawer liquid-glass" role="dialog" aria-modal={active} aria-label={title} tabIndex={-1} ref={ref} onClick={e=>e.stopPropagation()}><div className="drawer-heading"><h2>{title}</h2><IconButton label="关闭详情" onClick={onClose}><X size={20}/></IconButton></div><div className="drawer-body">{children}</div></div></div>;
}

function Career(){
 const {data,sheet,prepareQuestion,ticker,openInvestmentEpisode}=useDemo();
 return <CareerDashboard data={data} onDetails={sheet}
  onYear={year=>{save('decision-year',year);sheet(year+' 年的投资经历',<Decisions/>);}}
  onEpisode={openInvestmentEpisode}
  onQuestion={question=>prepareQuestion(question,defaultScope(data,ticker,'career'))}/>;
}

export function DecisionDetail({fill,onShowMarket}:{fill:Fill;onShowMarket?:()=>void}){
 const {data,replay,ask}=useDemo();
 const index=nearestIndex(data.dates,fill.date);
 const day=data.paths[0].days[index];
 const previous=index>0?data.paths[0].days[index-1]:null;
 const unit=fill.ticker==='sh510300'?'份':'股';
 const scope:ResearchScope={
  ...defaultScope(data,fill.ticker,'decision'),
  start:fill.date,end:fill.date,kind:'execution',execution_id:fill.execution_id
 };
 const action=fill.side==='BUY'?'买入':'卖出';
 return <div className="detail-stack">
  <span className="pill">历史决策 · 教学成交</span>
  <h3 className="detail-title">{action}{fill.name}<br/><span>{fill.date}</span></h3>
  <div className="detail-number">{money(fill.quantity,0)}<small>{unit} × ¥{money(fill.price,Math.max(2,fill.price.split('.')[1]?.length??0))}</small></div>
  <div className="detail-kvs">
   <div><span>成交费用</span><b>¥{money(fill.fee)}</b></div>
   <div><span>前一交易日资产</span><b>{previous?'¥'+money(previous.equity):'—'}</b></div>
   <div><span>当日收盘现金</span><b>¥{money(day.cash)}</b></div>
   <div><span>当日收盘持仓</span><b>{day.position_count} 只</b></div>
  </div>
  <p>按这笔成交的时间核对当时可用的信息，后续行情和披露单独列出。</p>
  <div className="button-row">
   <button className="primary" onClick={()=>ask(`回到 ${fill.date} ${action}${fill.name} 的时点，分析当时的行情、公司与账户状态，以及后续结果。`,scope)}>研究这笔选择<ArrowRight size={15}/></button>
   <button className="secondary" onClick={()=>onShowMarket?onShowMarket():replay(fill.ticker,false,undefined,fill.date)}>{onShowMarket?'返回行情':'看当日行情'}<ArrowRight size={15}/></button>
  </div>
 </div>;
}
function Decisions({main=false,initialEpisodeId,onLeaveEpisode}:{main?:boolean;initialEpisodeId?:string;onLeaveEpisode?:()=>void}={}){
 const {data,ask,openInvestmentEpisode}=useDemo();
 return <InvestmentExperiences data={data} initialEpisodeId={initialEpisodeId} onLeaveEpisode={onLeaveEpisode} onOpenEpisode={main?undefined:openInvestmentEpisode} renderDecision={(fill,onShowMarket)=><DecisionDetail fill={fill} onShowMarket={onShowMarket}/>} onResearch={episode=>{
  const scope:ResearchScope={...defaultScope(data,episode.ticker,'decision'),...episodeRange(episode),kind:'range',focus:'personal_review'};
  ask(`复盘${episode.name}第${episode.round}轮投资（${scope.start}至${scope.end}）：把建仓、加减仓、公司行动与结果串起来，分析当时的市场和公司环境。`,scope);
 }}/>;
}

function MemoryDetails({memory}:{memory:Memory}){
 const {ask}=useDemo();
 return <div className="detail-stack">
  <span className="pill">{memory.type} · {memory.date}</span>
  <p className="message-text">{memory.body}</p>
  {memory.source?.selection&&<p>原研究范围 · {scopeLabel(memory.source.selection)}</p>}
  {memory.revisions?.length?<details><summary>修订历史 · {memory.revisions.length} 次</summary>{memory.revisions.map((r,i)=><p key={i}>{r.date} · {r.body}</p>)}</details>:null}
  {!memory.withdrawn&&memory.source?.selection&&<button className="primary" onClick={()=>ask(`我保存过这条${memory.type}：“${memory.body.slice(0,1500)}”。请按原来的范围重新核对证据。`,memory.source!.selection)}>核对这条记忆<ArrowRight size={15}/></button>}
 </div>;
}

function Memories(){
 const {memories,setMemories,sheet,closeSheet,toast}=useDemo();
 const [filter,setFilter]=useState('全部');
 const visible=memories.filter(m=>filter==='已撤回'?m.withdrawn:!m.withdrawn&&(filter==='全部'||m.type===filter));
 const update=(memory:Memory)=>{
  setMemories(memories.map(m=>m.id===memory.id?memory:m));
  closeSheet();
 };
 const edit=(m:Memory)=>sheet('更新这段记忆',<MemoryEditor memory={m} onSave={body=>{
  if(body===m.body){closeSheet();return;}
  update({...m,body,date:new Date().toISOString().slice(0,10),revisions:[...(m.revisions??[]),{body:m.body,date:m.date}]});
  toast('记忆已更新，原文保存在修订历史。');
 }}/>);
 const withdraw=(m:Memory)=>sheet('撤回这段记忆',<div className="detail-stack"><p>{m.title}</p><p>可在「已撤回」中查看和恢复。</p><button className="secondary" onClick={()=>update({...m,withdrawn:true})}>确认撤回</button></div>);
 return <div className="memories-view">
  <div className="page-title"><div><h1>越来越懂你，也始终听你纠正。</h1><p>事实、想法、发现与假设，各自有自己的位置。</p></div><button className="secondary" onClick={()=>download('投镜-林远投资记忆.json',JSON.stringify(memories,null,2))}><ArrowDownToLine size={16}/>导出记忆</button></div>
  <div className="memory-layout">
   <div className="memory-orb-pane"><Orb size="large"/><h2>这份记忆，属于你。</h2><p>54 笔教学投资事实<br/>{memories.filter(m=>m.type!=='事实'&&!m.withdrawn).length} 条已保存的想法与发现</p></div>
   <div className="memory-list"><div className="segmented">{['全部','事实','用户想法','行为发现','策略假设','已撤回'].map(t=><button key={t} className={filter===t?'active':''} onClick={()=>setFilter(t)}>{t}</button>)}</div>
    <div className="memory-scroll">{visible.map(m=><article className="memory-entry liquid-glass" key={m.id}>
     <div className="memory-meta"><span className="pill">{m.type}</span><span>{m.date}</span></div><h3>{m.title}</h3><p>{m.body}</p>
     <div className="memory-entry-actions"><button className="text-button" onClick={()=>sheet(m.title,<MemoryDetails memory={m}/>)}>依据与版本</button>
      {m.withdrawn?<button className="text-button" onClick={()=>setMemories(memories.map(x=>x.id===m.id?{...x,withdrawn:false}:x))}>恢复</button>:<>
       {m.type!=='事实'&&<button className="text-button" onClick={()=>edit(m)}>纠正</button>}
       <button className="text-button" onClick={()=>withdraw(m)}>撤回</button>
      </>}
     </div>
    </article>)}{!visible.length&&<p className="empty-inline">这一类暂时没有记录。</p>}</div>
   </div>
  </div>
 </div>;
}
function MemoryEditor({memory,onSave}:{memory:Memory;onSave:(s:string)=>void}){
 const [body,setBody]=useState(memory.body);
 return <div className="detail-stack"><h3>{memory.title}</h3><textarea rows={7} value={body} onChange={e=>setBody(e.target.value)} aria-label="修改记忆内容"/><button className="primary" onClick={()=>onSave(body.trim())} disabled={!body.trim()}>保存修订<Check size={16}/></button></div>;
}
