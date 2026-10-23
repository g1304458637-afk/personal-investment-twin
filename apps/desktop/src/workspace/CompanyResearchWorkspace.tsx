import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Building2, ChevronRight, Download, History, LoaderCircle, RefreshCw, Search } from 'lucide-react';
import { downloadText } from '@/lib/download';
import { StateNotice } from '@/components/common/StateNotice';
import { companyApi, type CompanyBuild, type CompanyCapabilities, type CompanyResolution, type CompanySnapshot, type ResearchCompany } from '@/data/companyResearch';
import { Modal } from './company-research/ResearchParts';
import { CompanyResearchDetail } from './company-research/ResearchDetail';
import './company-research/company-research.css';

const preferenceKey='toujing-company-research-v1';
function preferences():{saved:string[];lastBuild?:string}{try{const p=JSON.parse(localStorage.getItem(preferenceKey)||'{}');return {saved:Array.isArray(p.saved)?p.saved.filter((s:unknown)=>typeof s==='string').slice(0,1000):[],lastBuild:typeof p.lastBuild==='string'?p.lastBuild:undefined};}catch{return {saved:[]};}}
const issuerKey=(build:CompanyBuild)=>build.identity?.company_id||build.company||build.query;
const errorText=(error:unknown)=>error instanceof Error?error.message:'公司研究暂不可用，请稍后重试。';
const stageNames:Record<string,string>={BuildStarted:'开始公司研究',CompanyResolved:'已识别公司',AnnualReportFound:'已找到官方年报',ArtifactArchived:'报告已留存',DocumentParsed:'报告解析完成',ParseProgress:'正在解析报告',ExtractionStarted:'正在提取经营资料',CandidateAccepted:'经营记录已写入模型',ModelVersionCreated:'模型版本已生成',BuildCompleted:'公司研究已完成',BuildFailed:'本次建模未完成'};

export function CompanyResearchWorkspace(){
 const [params,setParams]=useSearchParams();
 const [catalog,setCatalog]=useState<CompanyBuild[]>([]),[capabilities,setCapabilities]=useState<CompanyCapabilities|null>(null);
 const [selectedId,setSelectedId]=useState(()=>params.get('build')||preferences().lastBuild||''),[company,setCompany]=useState<ResearchCompany|null>(null);
 const [loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[refresh,setRefresh]=useState(0);
 const [search,setSearch]=useState<string|null>(null),[resolution,setResolution]=useState<CompanyResolution|null>(null),[resolving,setResolving]=useState(false),[searchError,setSearchError]=useState('');
 const [pendingBuild,setPendingBuild]=useState<string|null>(null),[snapshot,setSnapshot]=useState<CompanySnapshot|null>(null),[buildBusy,setBuildBusy]=useState(false),[buildError,setBuildError]=useState('');
 const [saved,setSaved]=useState(()=>preferences().saved),[versionsOpen,setVersionsOpen]=useState(false),[reporting,setReporting]=useState(false),[notice,setNotice]=useState(''),[historySnapshot,setHistorySnapshot]=useState<CompanySnapshot|null>(null);
 const resolver=useRef<AbortController|null>(null),resolverGeneration=useRef(0),beginning=useRef(false);
 const selected=catalog.find(b=>b.build_id===selectedId);
 const latest=[...new Map([...catalog].reverse().filter(b=>b.status==='COMPLETED').map(b=>[issuerKey(b),b])).values()].reverse();
 const versions=selected?catalog.filter(b=>issuerKey(b)===issuerKey(selected)):[];
 const select=(id:string)=>{setSelectedId(id);setSearch(null);setVersionsOpen(false);setParams(previous=>{const next=new URLSearchParams(previous);next.set('build',id);next.delete('ask');return next;});};
 useEffect(()=>{try{localStorage.setItem(preferenceKey,JSON.stringify({saved,lastBuild:selectedId||undefined}));}catch{/* Browsing remains available if local preferences cannot be stored. */}},[saved,selectedId]);
 useEffect(()=>{const id=params.get('build');if(id)setSelectedId(id);},[params]);
 useEffect(()=>{
  const controller=new AbortController();let active=true;setLoading(true);setLoadError('');
  void Promise.all([companyApi.list(controller.signal),companyApi.status(controller.signal)]).then(([data,status])=>{
   if(!active)return;setCatalog(data.builds);setCapabilities(status);
   const complete=data.builds.filter(b=>b.status==='COMPLETED');
   const requested=params.get('build');if(requested&&!complete.some(b=>b.build_id===requested)){setLoadError('指定的公司模型不存在或尚未完成，请从查找公司中选择可用模型。');setLoading(false);return;}
   setSelectedId(current=>complete.find(b=>b.build_id===current)?.build_id||complete.find(b=>b.company==='宁德时代')?.build_id||complete[0]?.build_id||'');
   const running=data.builds.find(b=>['PENDING','RUNNING'].includes(b.status));if(running)setPendingBuild(running.build_id);
   setLoading(false);
  }).catch(error=>{if(active){setLoadError(errorText(error));setLoading(false);}});
  return()=>{active=false;controller.abort();};
 },[refresh]);
 useEffect(()=>{
  if(!selected||selected.status!=='COMPLETED'){if(!loading&&!loadError)setCompany(null);return;}
  let active=true;const controller=new AbortController();setLoading(true);setLoadError('');setCompany(null);
  void companyApi.load(selected.build_id,controller.signal).then(model=>{
   if(!active)return;setCompany({...model,key:selected.build_id,buildId:selected.build_id,name:selected.company||selected.identity?.short_name||selected.query,ticker:selected.identity?.listings?.map(l=>[l.ticker,l.exchange].filter(Boolean).join(' · ')).join(' / ')||selected.query});setLoading(false);
  }).catch(error=>{if(active){setLoadError(errorText(error));setLoading(false);}});
  return()=>{active=false;controller.abort();};
 },[selected]);
 useEffect(()=>{
  if(!pendingBuild)return;const controller=new AbortController();let active=true;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const next=await companyApi.snapshot(pendingBuild,controller.signal);if(!active)return;setSnapshot(next);
   if(next.status==='COMPLETED'){setPendingBuild(null);setSelectedId(next.build_id);setParams(p=>{const n=new URLSearchParams(p);n.set('build',next.build_id);n.delete('ask');return n;});setRefresh(n=>n+1);return;}
   if(next.status==='FAILED'){setBuildError('本次公司建模未完成，已有模型和投资数据仍可继续查看。');setPendingBuild(null);setRefresh(n=>n+1);return;}
  }catch(error){if(active)setBuildError(errorText(error));}if(active)timer=setTimeout(()=>void poll(),1800);};void poll();
  return()=>{active=false;controller.abort();clearTimeout(timer);};
 },[pendingBuild,setParams]);
 useEffect(()=>()=>resolver.current?.abort(),[]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();e.stopImmediatePropagation();setSearch('');setResolution(null);}};window.addEventListener('keydown',key,{capture:true});return()=>window.removeEventListener('keydown',key,{capture:true});},[]);
 const closeSearch=()=>{resolver.current?.abort();resolverGeneration.current++;setResolving(false);setSearch(null);};
 const searchOfficial=async(query:string)=>{
  resolver.current?.abort();const controller=new AbortController();resolver.current=controller;const generation=++resolverGeneration.current;
  setResolving(true);setSearchError('');setResolution(null);
  try{const data=await companyApi.resolve(query,controller.signal);if(generation===resolverGeneration.current)setResolution(data);}catch(error){if(!controller.signal.aborted)setSearchError(errorText(error));}finally{if(generation===resolverGeneration.current)setResolving(false);}
 };
 const beginBuild=async()=>{
  if(!resolution||resolution.status!=='RESOLVED'||beginning.current)return;beginning.current=true;setBuildBusy(true);setSearchError('');setBuildError('');
  try{const started=await companyApi.build(resolution.query);setPendingBuild(started.build_id);setSnapshot(null);setSearch(null);setResolution(null);}catch(error){setSearchError(errorText(error));setRefresh(n=>n+1);}finally{beginning.current=false;setBuildBusy(false);}
 };
 const exportReport=async()=>{
  if(!company||reporting)return;setReporting(true);setNotice('');try{const result=await companyApi.report(company.buildId);downloadText(`投镜-${company.name.replace(/[\\/:*?"<>|]/g,'_')}-研究报告.html`,result.html,'text/html;charset=utf-8');}catch(error){setNotice(errorText(error));}finally{setReporting(false);}
 };
 const matched=latest.filter(b=>`${b.company} ${b.query} ${b.identity?.listings?.map(l=>l.ticker).join(' ')||''}`.toLowerCase().includes((search||'').toLowerCase()));
 const snapshotStage=snapshot?.events.at(-1);
 return <div className="iw-page cr-page cr-app">
  <div className="cr-page-title"><div className="iw-page-heading"><span className="iw-kicker">投资决策工作台</span><h1>公司研究</h1><p>理解一家公司，再形成自己的判断。把经营、财务与原始证据放在一起。</p></div><button className="cr-button cr-switch-company" onClick={()=>{setSearch('');setSearchError('');setResolution(null);}}><Search size={15}/>查找公司<span>⌘ K</span></button></div>
  {(pendingBuild||buildError)&&<section className="iw-panel cr-build-status" role="status"><div>{pendingBuild?<LoaderCircle size={19} className="animate-spin"/>:<RefreshCw size={19}/>}<strong>{pendingBuild?(stageNames[snapshotStage?.type||'']||'正在建立公司研究'): '建模状态'}</strong><span>{snapshot?.company_node?.label||''}</span></div><p>{buildError||'正在检索官方披露并生成有据模型。可以继续查看已有研究，完成后会在这里打开。'}</p>{snapshot&&<small>已记录 {snapshot.events.length} 个处理事件 · {snapshot.build_id.slice(-8)}</small>}{!pendingBuild&&<button className="cr-text-link" onClick={()=>{setBuildError('');setSnapshot(null);}}>收起状态</button>}</section>}
  {loadError&&<StateNotice state="disconnected" title="公司研究暂不可用" detail={loadError} onRetry={()=>setRefresh(n=>n+1)}/>}
  {loading&&!loadError&&<StateNotice state="loading" title="正在打开公司研究…" detail="读取本地引擎中的公司模型和证据。"/>}
  {!loading&&!loadError&&!company&&<StateNotice state="empty" title="从一家公司开始研究" detail="查找公司名称或证券代码，建立基于官方报告的公司模型。"/>}
  {!loading&&!loadError&&company&&<><div className="cr-model-actions"><span><i className="cr-dot"/>本地公司引擎 · 公开报告资料</span><div><button className="cr-text-link" onClick={()=>setVersionsOpen(true)}><History size={13}/>模型版本 {versions.length}</button><button className="cr-text-link" onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={13}/>刷新</button><button className="cr-text-link" disabled={reporting} onClick={()=>void exportReport()}>{reporting?<LoaderCircle size={13} className="animate-spin"/>:<Download size={13}/>}导出研究报告</button></div></div><CompanyResearchDetail key={company.buildId} company={company} capabilities={capabilities} saved={saved.includes(issuerKey(selected!))} onSave={()=>setSaved(p=>p.includes(issuerKey(selected!))?p.filter(k=>k!==issuerKey(selected!)):[...p,issuerKey(selected!)])}/></>}
  {notice&&<p role="alert" className="cr-inline-notice">{notice}</p>}
  {search!==null&&<Modal title="查找公司" onClose={closeSearch} className="cr-search-modal"><form className="cr-company-search" onSubmit={e=>{e.preventDefault();if(search.trim())void searchOfficial(search.trim());}}><Search size={18}/><input autoFocus aria-label="公司名称或代码" placeholder="输入公司名称或证券代码" maxLength={200} value={search} onChange={e=>{resolver.current?.abort();resolverGeneration.current++;setResolving(false);setSearch(e.target.value);setResolution(null);setSearchError('');}}/><button className="cr-text-link" type="submit" disabled={!search.trim()||resolving}>{resolving?'识别中…':'查找新公司'}</button></form><p className="cr-search-caption">已有公司模型 <span>{latest.length} 家</span></p><div className="cr-company-results">{matched.map(b=><button key={b.build_id} onClick={()=>select(b.build_id)}><span className="cr-result-icon"><Building2 size={19}/></span><span><strong>{b.company||b.query}</strong><small>{b.identity?.listings?.map(l=>l.ticker).join(' / ')||b.query} · 已有模型{saved.includes(issuerKey(b))?' · 已收藏':''}</small></span><ChevronRight size={16}/></button>)}</div>{!matched.length&&<p className="cr-fine">已有模型中没有匹配项，可查找官方公司身份并建立研究。</p>}{resolution&&<div className="cr-resolution"><span className="iw-kicker">公司身份识别</span>{resolution.status==='NOT_FOUND'?<p>没有找到明确的公司身份，请使用完整公司名称或证券代码。</p>:(resolution.status==='RESOLVED'?resolution.candidates.slice(0,1):resolution.candidates).map(c=><div key={c.identity.company_id}><strong>{c.identity.short_name}</strong><small>{c.identity.legal_name} · {c.identity.listings?.map(l=>l.ticker).join(' / ')}</small>{resolution.status==='AMBIGUOUS'&&<button className="cr-text-link" onClick={()=>void searchOfficial(c.identity.listings?.[0]?.ticker||c.identity.short_name)}>选择这家公司<ArrowUpRight size={12}/></button>}</div>)}{resolution.status==='RESOLVED'&&<><p>从官方披露提取经营与财务资料，会使用已配置的模型；可能需要数分钟。</p><button className="cr-button" disabled={buildBusy||!!pendingBuild||!capabilities?.chat.configured} onClick={()=>void beginBuild()}>{buildBusy?'正在开始…':pendingBuild?'已有建模任务运行':'建立公司研究'}<ArrowUpRight size={13}/></button>{!capabilities?.chat.configured&&<p>建模需要先配置公司研究引擎的模型服务；已有模型可直接查看。</p>}</>}</div>}{searchError&&<p role="alert" className="cr-inline-notice">{searchError}</p>}<p className="cr-fine">公司资料独立于投资账户。切换公司会同步切换财务、图谱和证据。</p></Modal>}
  {versionsOpen&&<Modal title="公司模型版本" onClose={()=>setVersionsOpen(false)}><div className="cr-company-results">{versions.map((b,i)=><button key={b.build_id} onClick={()=>{if(b.status==='COMPLETED')select(b.build_id);else{setVersionsOpen(false);void companyApi.snapshot(b.build_id).then(setHistorySnapshot).catch(error=>setNotice(errorText(error)));}}}><span className="cr-result-icon"><History size={18}/></span><span><strong>{b.company} · {b.status==='COMPLETED'?'已完成':b.status==='FAILED'?'未完成':'运行中'} {i===0?'· 最近记录':''}</strong><small>{b.started_at||b.build_id.slice(-8)} {b.version_id?`· ${b.version_id.slice(-8)}`:''}{b.build_id===selectedId?' · 当前查看':''}</small></span><ChevronRight size={14}/></button>)}</div><p className="cr-fine">每个版本保留对应财务、图谱和证据，不混用不同模型版本。</p></Modal>}
 {historySnapshot&&<Modal title="公司建模记录" onClose={()=>setHistorySnapshot(null)}><p className="cr-fine">状态：{historySnapshot.status} · {historySnapshot.build_id}</p><div className="cr-build-events">{historySnapshot.events.map(e=><div key={e.seq}><small>{String(e.seq).padStart(2,'0')}</small><span>{stageNames[e.type]||e.message}</span></div>)}</div><p className="cr-fine">任务未完成时不会加载为可用公司模型。</p></Modal>}
 </div>;
}
