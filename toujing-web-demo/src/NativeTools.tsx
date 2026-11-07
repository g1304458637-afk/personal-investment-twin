import {useEffect,useState,useRef} from 'react';
import {ArrowRight,Check,ChevronDown,FileText,RefreshCw,Search} from 'lucide-react';
import {capabilities,contextFor,deliveryLabel,runtime,safeSource,scopeLabel,type CapabilityId,type PriceAttribution,type ResearchScope,type ResearchTask} from './alignment';
import {download,money,pct,type DemoData} from './model';
import {loadEpisodeArchive} from './episodes';
import {locatedPassage} from './documentSelection';

const names:Record<string,string>={instrument_id:'证券',title:'名称',name:'名称',text:'内容',value:'数值',unit:'单位',year:'年度',date:'日期',status:'状态',formula:'公式',method_version:'方法版本',knowledge_at:'资料截止',historical_proof:'时点口径',period_type:'期间',scope:'报表范围',review_status:'核对状态',source_url:'原始来源',rule:'规则',card:'条件',facts:'事实',comparisons:'跨期比较',bridges:'现金流核对',contributions:'分项变化',years:'各年结果',summary:'摘要',evidence_refs:'交易依据',counterexamples:'相反样本',count:'样本数',sample_count:'样本数',description:'说明',principle:'方法',hypothesis:'判断',risk:'风险',invalidate_if:'重新检查条件',reported_cfo:'披露经营现金流',net_profit:'净利润',known_adjustments:'已核对调整',unexplained_amount:'待核对差额',calculated_cfo:'核对现金流',company:'公司',publication_date:'披露日期',page:'页码',row_label:'原文项目',original_value:'原值',value_cny:'人民币金额',currency:'币种',basis:'报告口径',reason:'原因',limitations:'使用范围',qualification_issues:'资料核对事项',records:'已保存记录',events:'本地检查结果',rules:'已启用规则'};
const ignored=new Set(['sha256','source_sha256','source_fingerprint','context_hash','snapshot_hash','payload_hash','record_hash','input_hash','result_hash','bridge_id','fact_id','document_id','comparison_group']);
export function ResultView({value,level=0}:{value:unknown;level?:number}){
  if(value==null)return <span className="muted">—</span>;
  if(typeof value==='boolean')return <span>{value?'是':'否'}</span>;
  if(typeof value!=='object')return <span className="result-text">{String(value)}</span>;
  if(Array.isArray(value))return <div className="result-list">{value.length?value.map((v,i)=><div key={i}><ResultView value={v} level={level+1}/></div>):<p className="muted">当前范围没有记录。</p>}</div>;
  const entries=Object.entries(value).filter(([k])=>!ignored.has(k));
  return <div className="result-object">{entries.map(([k,v])=>{
    if(k==='source_url'||k==='url'){const url=safeSource(v);return url?<a key={k} href={url} target="_blank" rel="noreferrer">查看公开原件 ↗</a>:null;}
    const label=names[k]??k;
    return typeof v==='object'&&v!==null?<details key={k} open={level<1}><summary>{label}{Array.isArray(v)?` · ${v.length} 项`:''}</summary><ResultView value={v} level={level+1}/></details>:<div className="result-field" key={k}><span>{label}</span><ResultView value={v} level={level+1}/></div>;
  })}</div>;
}
export function ScopeControl({value,onChange,data}:{value:ResearchScope;onChange:(s:ResearchScope)=>void;data:DemoData}){
  const patch=(change:Partial<ResearchScope>)=>onChange({...value,...change});
  const company=value.origin==='company';
  const asset=data.assets.find(a=>a.ticker===value.instrument_id)?.name;
  const label=company?`${asset??value.instrument_id} · 公开资料 · ${value.knowledge_at.slice(0,10)}`:
    `${asset??value.instrument_id} · ${value.start} — ${value.end}`;
  return <details className="scope-control"><summary>{label}<ChevronDown size={13}/></summary>{company&&value.selection_object&&<p className="scope-source-selection">已带入 PDF 第 {value.selection_object.page} 页的原文选段</p>}<div className="scope-fields">
    {!company&&<>
      <label>证券<select value={value.instrument_id} onChange={e=>patch({instrument_id:e.target.value,execution_id:undefined,kind:'range'})}>{data.assets.map(a=><option value={a.ticker} key={a.ticker}>{a.name}</option>)}</select></label>
      <label>开始<input aria-label="研究开始日期" type="date" min={data.dates[0]} max={value.end} value={value.start} onChange={e=>e.target.value&&e.target.value<=value.end&&patch({start:e.target.value,kind:'range',execution_id:undefined})}/></label>
      <label>结束<input aria-label="研究结束日期" type="date" min={value.start} max={data.dates.at(-1)} value={value.end} onChange={e=>e.target.value>=value.start&&patch({end:e.target.value,kind:'range',execution_id:undefined})}/></label>
      <label>带入资料<select value={value.focus} onChange={e=>patch({focus:e.target.value as ResearchScope['focus']})}><option value="public_price">公开行情</option><option value="personal_review">教学账户与操作</option></select></label>
    </>}
    <label>研究视角<select value={value.mode} onChange={e=>{
      const mode=e.target.value as ResearchScope['mode'];
      patch({mode,historical_proof:mode==='as_known_then'?'public_reconstruction':'hindsight',
        ...(!company&&mode==='as_known_then'?{knowledge_at:value.end+'T23:59:59+08:00'}:{})});
    }}><option value="hindsight">事后复盘</option><option value="as_known_then">回到当时</option></select></label>
    <label>资料截止<input aria-label="资料截止日期" type="date" value={value.knowledge_at.slice(0,10)} onChange={e=>e.target.value&&patch({knowledge_at:e.target.value+'T23:59:59+08:00'})}/></label>
  </div></details>;
}
export function FeatureDirectory({onOpen}:{onOpen:(id:CapabilityId)=>void}){
  return <div className="feature-directory"><p>每项能力保留原来的页面归属。点击在当前页查看，不改变正在研究的内容。</p>{['我的投资','我的策略','公司研究','研究社区','资料与账户','设置','所有页面','我的投资 / 公司研究'].map(owner=><section key={owner}><h3>{owner}</h3>{capabilities.filter(c=>c.owner===owner).map(c=><details key={c.id}><summary><span>{c.name}</span><small>{deliveryLabel[c.delivery]}</small></summary><p>{c.description}</p><button className="secondary small" onClick={()=>onOpen(c.id)}>在此查看<ArrowRight size={14}/></button><details><summary>接口与源码对应</summary><code>{c.method}</code><p className="muted">{c.source}</p></details></details>)}</section>)}</div>;
}
export function RuntimePanel({id,scope,data,onAsk}:{id:CapabilityId;scope:ResearchScope;data:DemoData;onAsk:(q:string,s?:ResearchScope)=>void}){
  const [value,setValue]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const request=useRef(0);const info=capabilities.find(c=>c.id===id)!;
  const read=async()=>{const stamp=++request.current;setBusy(true);setValue(null);setError('');try{
    const p={instrument_id:scope.instrument_id,knowledge_at:scope.knowledge_at,historical_proof:scope.mode==='as_known_then'?'public_reconstruction':'hindsight'};let v:any;
    if(id==='historical'||id==='selection')v=await contextFor(scope);
    else if(id==='factors'){const c=await contextFor(scope);v=await runtime('workbench.joint_price_research',{selection_ref:c.selection_ref});}
    else if(id==='behavior')v=await runtime('workbench.strategy.discover');
    else if(id==='financial')v={财务比较:await runtime('workbench.company.financials',p),现金流核对:await runtime('workbench.company.cashflow',p)};
    else if(id==='operating')v=await runtime('workbench.company.operating',p);
    else if(id==='watch')v=await runtime('workbench.watch.list');
    else if(id==='projects')v=await runtime('workbench.research.library',{action:'list',library_scope:{demo:true}});
    else if(id==='research')v=await runtime('workbench.research.list',{metadata_only:true});
    else if(id==='strategy')v=await runtime('workbench.strategy.list');
    else if(id==='career')v=data.lifetime;
    else if(id==='episodes'){const archive=await loadEpisodeArchive(data);v={证券:data.assets.find(a=>a.ticker===scope.instrument_id)?.name,投资经历:archive.episodes.filter(e=>e.ticker===scope.instrument_id),口径:archive.method.formula};}
    else v={说明:info.description,当前交付:deliveryLabel[info.delivery]};
    if(stamp===request.current)setValue(v);
  }catch(e){if(stamp===request.current)setError((e as Error).message);}finally{if(stamp===request.current)setBusy(false);}};
  useEffect(()=>{if(!['documents','valuation','decisions'].includes(id))void read();return()=>{request.current++;};},[id,scope.instrument_id,scope.start,scope.end,scope.mode,scope.knowledge_at]);
  if(id==='documents')return <DocumentReader scope={scope} onAsk={onAsk}/>;
  if(id==='valuation')return <ValuationLab scope={scope} onAsk={onAsk}/>;
  if(id==='decisions')return <DecisionEditor scope={scope}/>;
  return <div className="native-panel"><div className="section-line"><span className="quiet-tag">{deliveryLabel[info.delivery]}</span><button className="text-button" onClick={read} disabled={busy}><RefreshCw size={14}/>重新读取</button></div><p className="scope-caption">{scopeLabel(scope)}</p><p>{info.description}</p>{busy&&<p role="status">正在读取投镜已有计算与资料…</p>}{error&&<div className="form-error" role="alert"><p>{error}</p><button className="secondary small" onClick={read}>重试读取</button></div>}{value&&<ResultView value={id==='historical'||id==='selection'?{区间结果:value.stats,区间成交:value.trades,可用依据:value.evidence}:value}/>}{id==='watch'&&<button className="primary" disabled={busy} onClick={async()=>{setBusy(true);try{setValue(await runtime('workbench.watch.run_due'));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>检查本地资料更新<RefreshCw size={15}/></button>}<button className="secondary" onClick={()=>onAsk(`结合${info.name}，解释这段经历及值得继续检验的地方`,scope)}>带着这些资料继续问<ArrowRight size={15}/></button><details className="technical-details"><summary>接口与来源身份</summary><code>{info.method}</code><p>{info.source}</p></details></div>;
}

export function DocumentReader({scope,onAsk}:{scope:ResearchScope;onAsk:(q:string,s?:ResearchScope)=>void}){
 const [docs,setDocs]=useState<any[]>([]),[doc,setDoc]=useState(''),[page,setPage]=useState(1),[query,setQuery]=useState(''),[content,setContent]=useState<any>(null),[hits,setHits]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState('');const request=useRef(0);
 useEffect(()=>{let active=true;setDocs([]);setDoc('');setContent(null);runtime('workbench.company.catalog').then(v=>{if(!active)return;const ds=(v.companies.find((c:any)=>c.instrument_id===scope.instrument_id)?.documents??[]).filter((d:any)=>d.available_at&&Date.parse(d.available_at)<=Date.parse(scope.knowledge_at));setDocs(ds);const chosen=ds.find((d:any)=>d.document_id===scope.selection_object?.document_id);setDoc(chosen?.document_id??ds[0]?.document_id??'');setPage(chosen?scope.selection_object!.page:1);}).catch(e=>active&&setError(e.message));return()=>{active=false;};},[scope.instrument_id,scope.knowledge_at,scope.selection_object]);
 useEffect(()=>{const stamp=++request.current;if(!doc)return;setBusy(true);setContent(null);setSelected('');setError('');runtime('workbench.company.source.page',{document_id:doc,page}).then(v=>{if(stamp===request.current)setContent(v);}).catch(e=>stamp===request.current&&setError(e.message)).finally(()=>stamp===request.current&&setBusy(false));return()=>{request.current++;};},[doc,page]);
 const passage=content?.text?locatedPassage(content.text,doc,page,scope.selection_object):null;
 const focusedPassage=useRef<HTMLElement>(null);
 useEffect(()=>{focusedPassage.current?.scrollIntoView({block:'center',behavior:'instant'});},[content,doc,page,scope.selection_object]);
 const explain=async()=>{try{const text=selected||passage?.text||content?.text?.trim().slice(0,1800);if(!text)return;const located=await runtime('workbench.company.source.locate',{document_id:doc,page,text});onAsk(`解释${docs.find(d=>d.document_id===doc)?.title}第${page}页的所选原文`,{...scope,origin:'company',focus:'public_price',selection_object:located.selection_object});}catch(e){setError((e as Error).message);}};
 return <div className="document-reader"><div className="document-toolbar"><select aria-label="选择原文报告" value={doc} onChange={e=>{setDoc(e.target.value);setPage(1);setHits(null);}}>{docs.map(d=><option key={d.document_id} value={d.document_id}>{d.title}</option>)}</select><label>第<input type="number" aria-label="原文页码" min={1} max={docs.find(d=>d.document_id===doc)?.page_count??999} value={page} onChange={e=>setPage(Math.min(docs.find(d=>d.document_id===doc)?.page_count??999,Math.max(1,Number(e.target.value))))}/>页</label></div><form className="document-search" onSubmit={async e=>{e.preventDefault();setError('');try{const stamp=request.current;const found=await runtime('workbench.company.source.search',{document_id:doc,query});if(stamp===request.current)setHits(found);}catch(e){setError((e as Error).message);}}}><input placeholder="搜索报告中的文字" value={query} onChange={e=>setQuery(e.target.value)} aria-label="搜索原文"/><button className="secondary small" disabled={!query.trim()||!doc}><Search size={14}/>查找</button></form>{error&&<p className="form-error">{error}</p>}{!docs.length&&!error&&<p>当前范围尚无已入库的报告。可切换到美的、格力或海尔查看已有原件。</p>}{busy?<p role="status">正在读取原件文本…</p>:<pre className="document-text" onMouseUp={()=>setSelected(window.getSelection()?.toString().trim()??'')}>{passage?<>{passage.before}<mark ref={focusedPassage} className="document-source-highlight" aria-label="当前研究引用的原文">{passage.text}</mark>{passage.after}</>:content?.text??''}</pre>}{hits&&<details open><summary>搜索命中</summary><div className="document-hits">{hits.hits.length?hits.hits.map((hit:{page:number;excerpt:string})=><button className="secondary small" key={hit.page} title={hit.excerpt} onClick={()=>setPage(hit.page)}>第 {hit.page} 页</button>):<p>没有找到匹配文字。</p>}</div></details>}<button className="primary" disabled={!content?.text||busy} onClick={()=>void explain()}>{selected?'解释所选文字':passage?'解释已定位原文':'解释这一页'}<ArrowRight size={15}/></button><small>原文定位经过服务端校验，保留报告、页码和起止位置。</small></div>;
}
const initialAssumptions={base_revenue:'10000000000',growth:'0.05',margin:'0.12',tax_rate:'0.25',da_ratio:'0.02',capex_ratio:'0.03',nwc_ratio:'0.10',wacc:'0.09',terminal_growth:'0.02',net_debt:'0',non_operating_assets:'0',minority_interest:'0',shares:'1000000000',years:5};
export function ValuationLab({scope,onAsk}:{scope:ResearchScope;onAsk:(q:string,s?:ResearchScope)=>void}){
  const [a,setA]=useState(initialAssumptions),[result,setResult]=useState<any>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const labels:Record<string,string>={base_revenue:'基准收入（元）',growth:'收入增长率',margin:'经营利润率',tax_rate:'税率',da_ratio:'折旧摊销 / 收入',capex_ratio:'资本开支 / 收入',nwc_ratio:'营运资本 / 收入',wacc:'折现率 WACC',terminal_growth:'永续增长率',net_debt:'净债务（元）',non_operating_assets:'非经营资产（元）',minority_interest:'少数股东权益（元）',shares:'总股数',years:'预测年数'};
  return <div className="native-panel"><p>以下初值是教学假设。修改并确认后，由投镜原估值引擎计算。</p><div className="valuation-fields">{Object.entries(a).map(([key,v])=><label key={key}>{labels[key]}<input type="number" step="any" value={v} onChange={e=>setA({...a,[key]:key==='years'?Number(e.target.value):e.target.value})}/></label>)}</div><button className="primary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{setResult(await runtime('workbench.company.valuation',{instrument_id:scope.instrument_id,assumptions:a,confirm_user_assumptions:true}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>{busy?'正在计算…':'确认假设，计算情景'}<Check size={15}/></button>{error&&<p className="form-error">{error}</p>}{result&&<><ResultView value={result}/><button className="secondary" onClick={()=>onAsk(`请检查我的估值假设：${JSON.stringify(a)}，并解释其敏感性。`,{...scope,origin:'company',focus:'public_price'})}>把假设带回讨论</button></>}</div>;
}
export function DecisionEditor({scope}:{scope:ResearchScope}){
 const [title,setTitle]=useState(''),[hypothesis,setHypothesis]=useState(''),[risk,setRisk]=useState(''),[check,setCheck]=useState(''),[records,setRecords]=useState<any[]>([]),[preview,setPreview]=useState<any>(null),[saved,setSaved]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[watch,setWatch]=useState(false);const operation=useRef(crypto.randomUUID());
 useEffect(()=>{let active=true;setPreview(null);setSaved(null);setWatch(false);runtime('workbench.decision.list',{instrument_id:scope.instrument_id}).then(v=>active&&setRecords(v.records)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[scope.instrument_id]);
 const attempt=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <div className="native-panel"><p>记录今天确认的判断，后续修订保留版本与原始依据。</p>{[['判断标题',title,setTitle],['我的判断',hypothesis,setHypothesis],['主要风险',risk,setRisk],['什么变化需要重新检查',check,setCheck]].map(([label,value,setter])=><label className="field" key={label as string}>{label as string}<textarea rows={2} value={value as string} onChange={e=>{(setter as (s:string)=>void)(e.target.value);setPreview(null);setSaved(null);}}/></label>)}<button className="primary" disabled={busy||![title,hypothesis,risk,check].every(v=>v.trim())} onClick={()=>void attempt(async()=>{const s=await runtime('workbench.session.create',{operation_id:crypto.randomUUID(),instrument_id:scope.instrument_id,knowledge_at:scope.knowledge_at,historical_proof:scope.mode==='as_known_then'?'public_reconstruction':'hindsight'});setPreview(await runtime('workbench.decision.preview',{research_session_id:s.session.session_id,kind:'thesis',title,hypothesis,risk,reevaluate_if:check,horizon:'下一份相关公开资料出现时重新核对'}));operation.current=crypto.randomUUID();setSaved(null);})}>预览这份判断<ArrowRight size={15}/></button>{error&&<p className="form-error">{error}</p>}{preview&&!saved&&<div className="decision-confirm"><h3>确认保存</h3><p>{preview.notice}</p><p>{preview.record.payload.hypothesis}</p><button className="primary" disabled={busy} onClick={()=>void attempt(async()=>{const r=await runtime('workbench.decision.confirm',{preview_ref:preview.preview_ref,preview_fingerprint:preview.preview_fingerprint,operation_id:operation.current,confirmation:'CONFIRM_CURRENT_DECISION'});setSaved(r.record);setRecords((await runtime('workbench.decision.list',{instrument_id:scope.instrument_id})).records);})}>确认，保存这一版<Check size={15}/></button></div>}{saved&&<section><p>判断已保存 · {saved.created_at} · 第 {saved.revision} 版</p><button className="secondary" disabled={busy||watch} onClick={()=>void attempt(async()=>{await runtime('workbench.watch.enable',{record_id:saved.record_id,revision:saved.revision,operation_id:crypto.randomUUID(),confirmation:'ENABLE_LOCAL_SOURCE_WATCH'});setWatch(true);})}>{watch?'已启用本机资料检查':'确认启用后续资料检查'}</button><small>应用运行时检查本机新入库资料。</small></section>}<details><summary>已保存的判断 · {records.length} 版</summary>{records.map(r=><section key={r.record_hash}><b>{r.payload.title}</b><p>{r.payload.hypothesis}</p><small>第 {r.revision} 版 · {r.created_at}</small></section>)}</details></div>;
}

const componentNames:Record<string,string>={market:'市场共同变化',sector:'行业代理',peers:'同行',intercept:'模型常数',unexplained:'未解释项'};
const points=(value:string)=>`${Number(value)>0?'+':''}${Number(value).toFixed(2)}`;

function Attribution({value,onCitation}:{value:PriceAttribution;onCitation:(id:string)=>void}){
  const extent=Math.max(1,...value.components.flatMap(r=>[r.contribution_pp,...r.parameter_interval_95_pp]).map(v=>Math.abs(Number(v))));
  const x=(value:string)=>110+Number(value)/extent*97;
  return <section className="attribution-preview" aria-label="价格统计分解">
   <div className="section-line"><b>股价统计分解</b><span>{points(value.observed_return_pct)}%</span></div>
   <p>{value.model_name??'固定市场基准'} · 分项单位为百分点</p>
   {value.components.map(row=><div className="attribution-row" key={row.key}>
    <span>{row.label??componentNames[row.key]??row.key}</span>
    <svg viewBox="0 0 220 18" role="img" aria-label={`${points(row.contribution_pp)} 个百分点`}>
     <line x1="110" x2="110" y2="18" stroke="#adc9df80"/>
     <rect x={Math.min(110,x(row.contribution_pp))} y="4" width={Math.max(1,Math.abs(x(row.contribution_pp)-110))} height="10" rx="3" fill={Number(row.contribution_pp)>=0?'#9fddff':'#ffb17e'}/>
     <line x1={x(row.parameter_interval_95_pp[0])} x2={x(row.parameter_interval_95_pp[1])} y1="9" y2="9" stroke="#f0f5fc"/>
    </svg>
    <b>{points(row.contribution_pp)}</b>
   </div>)}
   <details><summary>模型、公式和参数区间</summary>
    <p>{value.interpretation}</p><code>{value.formula}</code>{value.link_formula&&<p>{value.link_formula}</p>}<p>{value.interval_policy}</p>
    {value.components.map(row=><p key={row.key}>{row.label??componentNames[row.key]??row.key} · {row.parameter_interval_95_pp.map(points).join(' 至 ')} 点{row.mechanism?' · '+row.mechanism:''}</p>)}
    {value.evidence_id&&<button className="text-button" onClick={()=>onCitation(value.evidence_id!)}>查看计算来源<ArrowRight size={12}/></button>}
   </details>
  </section>;
}

export function ResearchResult({task,onCitation,onRemember,onFollowup}:{task:ResearchTask;onCitation:(id:string)=>void;onRemember:()=>void;onFollowup:(question:string)=>void}){
  const result=task.result;
  if(!result)return null;
  const evidence=result.evidence??[];
  return <div className="research-result">
   {result.price_attribution&&<Attribution value={result.price_attribution} onCitation={onCitation}/>}
   <div className="citation-chips">{evidence.slice(0,3).map((e,i)=><button key={e.id} onClick={()=>onCitation(e.id)} title={e.text}><FileText size={12}/>{typeof e.title==='string'?e.title:e.kind.includes('trade')?'成交记录':e.kind.includes('price')?'行情计算':`依据 ${i+1}`}</button>)}</div>
   <details><summary>完整研究 · 计算与证据</summary>
    {result.sections.map((section,i)=><p key={i}>{section.text}</p>)}
    {result.calculation_receipts?.length?<details><summary>计算回执</summary><ResultView value={result.calculation_receipts}/></details>:null}
    <div className="citation-list">{evidence.map(e=><button onClick={()=>onCitation(e.id)} key={e.id}>{typeof e.title==='string'?e.title:e.text.slice(0,140)}<ArrowRight size={12}/></button>)}</div>
   </details>
   <div className="research-actions">
    <button onClick={onRemember}>加入长期记忆</button>
    <button onClick={()=>download('投镜-研究报告.md',`# ${task.question}\n\n${scopeLabel(task.selection)}\n\n${result.sections.map(s=>s.text).join('\n\n')}\n\n## 原始依据\n${evidence.map(e=>`- ${e.text}${safeSource(e.source_url)?` [来源](${safeSource(e.source_url)})`:''}`).join('\n')}`, 'text/markdown;charset=utf-8')}>导出报告</button>
   </div>
   {result.next_questions?.length>0&&<details><summary>继续研究</summary><div className="citation-list">{result.next_questions.slice(0,3).map(question=><button key={question} onClick={()=>onFollowup(question)}>{question}<ArrowRight size={12}/></button>)}</div></details>}
  </div>;
}
