import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Download, FileUp, Plus, ShieldCheck, X } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { downloadText } from '@/lib/download';
import { defaultInvestmentDisclosure, exampleInvestmentInputs, holdingsCsvTemplate, parseInvestmentFile, projectInvestmentShare, type InvestmentInput, type InvestmentKind, type PublishedInvestmentCard } from '@/data/investmentSharing';
import { InvestmentShareCard, investmentKindLabels, investmentSourceLabels } from './InvestmentShareCard';
import { communityCard } from '@/data/communityApi';
import '../community-demo.css';

export interface InvestmentNarrative { title:string; thesis:string; risk:string; watch:string }
interface Props { open:boolean; onOpenChange:(open:boolean)=>void; inputs?:InvestmentInput[]; destination?:'local'|'members'; onPublish:(card:PublishedInvestmentCard,narrative:InvestmentNarrative,requestId:string)=>void|Promise<void> }
const today=()=>new Date().toLocaleDateString('en-CA');
const numeric=(text:string,label:string)=>{ if(!text.trim())return undefined; if(!/^-?(?:\d+(?:\.\d+)?|\.\d+)$/.test(text.trim()))throw new Error(`${label}必须是有效数字`);const n=Number(text);if(!Number.isFinite(n))throw new Error(`${label}必须是有限数字`);return n; };

export function InvestmentShareDialog(props:Props) {
  return <Dialog open={props.open} onOpenChange={props.onOpenChange}><DialogContent className="cm-modal cm-investment-share-modal"><InvestmentShareForm {...props}/></DialogContent></Dialog>;
}

function InvestmentShareForm({inputs,onPublish,onOpenChange,destination='local'}:Props) {
  const remote=destination==='members';
  const [publishing,setPublishing]=useState(false);
  const requestId=useRef(crypto.randomUUID());
  const selectedCard=(input:InvestmentInput)=>{const card=projectInvestmentShare(input,disclosure);return remote?communityCard(card):card;};
  const [kind,setKind]=useState<InvestmentKind>(inputs?.[0]?.kind || 'episode');
  const [mode,setMode]=useState<'existing'|'manual'|'file'>(remote&&!inputs?.length?'manual':'existing');
  const pool=useMemo(()=>inputs ?? exampleInvestmentInputs(),[inputs]);
  const [selected,setSelected]=useState(0);
  const [imported,setImported]=useState<InvestmentInput|null>(null);
  const [step,setStep]=useState(0);
  const [disclosure,setDisclosure]=useState(defaultInvestmentDisclosure);
  const [error,setError]=useState('');const [loading,setLoading]=useState(false);
  const [narrative,setNarrative]=useState<InvestmentNarrative>({title:'',thesis:'',risk:'',watch:''});
  const [reviewCard,setReviewCard]=useState<PublishedInvestmentCard|null>(null);
  const generation=useRef(0),alive=useRef(true),titleRef=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
  useEffect(()=>{const heading=titleRef.current;if(!heading)return;heading.closest<HTMLElement>('[role=dialog]')?.scrollTo({top:0,behavior:'instant'});heading.focus({preventScroll:true});},[step]);
  const [manual,setManual]=useState({asOf:today(),start:'',end:'',currency:'CNY',instrument:'',status:'closed' as 'open'|'closed',returnPercent:'',drawdownPercent:'',pnl:'',equity:''});
  const [rows,setRows]=useState([{name:'',weight:'',value:''}]);
  const candidates=pool.filter(x=>x.kind===kind);
  const resetReview=()=>{setReviewCard(null);setError('');};
  const changeSource=(next:'existing'|'manual'|'file')=>{generation.current++;setLoading(false);setMode(next);setImported(null);setDisclosure(defaultInvestmentDisclosure());resetReview();};
  const readManual=():InvestmentInput=>{
    const performance=numeric(manual.returnPercent,'收益率'),drawdown=numeric(manual.drawdownPercent,'最大回撤'),pnl=numeric(manual.pnl,'盈亏金额'),equity=numeric(manual.equity,'资产金额');
    return {kind,source:'user_reported',asOf:manual.asOf,currency:manual.currency,...(manual.start?{start:manual.start}:{}),...(manual.end?{end:manual.end}:{}),...(kind==='episode'?{instrument:manual.instrument || undefined,status:manual.status}:{}),
      holdings:kind==='holdings'?rows.map((r,i)=>{if(!r.name.trim())throw new Error(`请填写第 ${i+1} 行持仓名称`);const weight=numeric(r.weight,'仓位百分比'),value=numeric(r.value,'持仓市值');if(weight===undefined)throw new Error(`请填写第 ${i+1} 行仓位百分比`);return {name:r.name,weight:weight/100,...(value===undefined?{}:{marketValue:value})};}):[],
      metrics:{...(kind!=='holdings'&&performance!==undefined?{returnValue:performance/100}:{}),...(kind==='period'&&drawdown!==undefined?{maxDrawdown:-Math.abs(drawdown)/100}:{}),...(pnl!==undefined?{pnl}:{}),...(equity!==undefined?{equity}:{}),...(kind==='holdings'?{holdingCount:rows.length}:{})},returnBasis:performance===undefined?'unavailable':'user_reported',pnlBasis:'user_reported',definitions:['个人手动填写，未经券商或第三方核验；收益与回撤按填写值展示，不由资产金额推算。',...(kind==='holdings'?['仓位百分比由提供者填写；未列出的现金或持仓不自动补齐。']:[])]};
  };
  const currentInput=()=>mode==='file'?imported:mode==='manual'?readManual():candidates[selected] || null;
  let liveCard:PublishedInvestmentCard|null=null;let sourceError='';
  try {const input=currentInput();if(input)liveCard=selectedCard(input);} catch(e){sourceError=e instanceof Error?e.message:'请检查投资数据';}
  const importFile=async(file:File|undefined)=>{
    const current=++generation.current;setImported(null);setError('');setReviewCard(null);if(!file)return;
    if(file.size>512*1024){setError('文件不能超过 512 KiB');return;}
    const extension=file.name.split('.').at(-1)?.toLowerCase();if(extension!=='csv'&&extension!=='json'){setError('请选择持仓模板 CSV 或投镜分享 JSON');return;}
    setLoading(true);
    try {const value=parseInvestmentFile(await file.text(),extension);if(!alive.current||current!==generation.current)return;setImported(value);setKind(value.kind);setSelected(0);setDisclosure(defaultInvestmentDisclosure());}
    catch(e){if(alive.current&&current===generation.current)setError(e instanceof Error?e.message:'导入失败');}
    finally{if(alive.current&&current===generation.current)setLoading(false);}
  };
  const advance=()=>{setError('');try {const input=currentInput();if(!input)throw new Error(mode==='file'?'请先选择有效的投资文件':'当前没有可用的投资记录，可导入文件或手动填写。');const card=selectedCard(input);if(step===1){if(!narrative.title.trim()||!narrative.thesis.trim()||!narrative.risk.trim()||!narrative.watch.trim())throw new Error('请填写分享标题、说明、风险与后续观察事项');if(!narrative.watch.split(/[\n；;]/).some(s=>s.trim())||narrative.watch.split(/[\n；;]/).some(s=>s.trim().length>240))throw new Error('每条观察事项请控制在 240 字以内');requestId.current=crypto.randomUUID();setReviewCard(card);}setStep(s=>s+1);}catch(e){setError(e instanceof Error?e.message:'请检查输入');}};
  return <>
    <DialogTitle ref={titleRef} tabIndex={-1}>分享我的投资</DialogTitle><DialogDescription>{remote?'先选择展示范围，再检查预览。确认后，全体已登录的社区成员都可以查看。':'先选投资记录，再选展示范围，最后核对完整分享。只加入本地社区。'}</DialogDescription>
    <ol className="cm-share-steps">{['投资记录','展示范围','预览分享'].map((label,i)=><li key={label} aria-current={step===i?'step':undefined}><span>{step>i?<Check size={11}/>:i+1}</span>{label}</li>)}</ol>
    {step===0&&<>
      <div className="cm-investment-kind" aria-label="投资分享类型">{(['episode','holdings','period'] as const).map(k=><button type="button" key={k} aria-pressed={kind===k} onClick={()=>{generation.current++;setLoading(false);setKind(k);setSelected(0);setImported(null);setManual(m=>({...m,start:'',end:'',instrument:'',returnPercent:'',drawdownPercent:'',pnl:'',equity:''}));setDisclosure(defaultInvestmentDisclosure());resetReview();}}>{investmentKindLabels[k]}</button>)}</div>
      <div className="cm-source-modes" aria-label="记录来源">{([['existing',inputs===undefined?'演示记录':'当前账户记录'],['file','导入文件'],['manual','手动填写']] as const).map(([id,label])=><button type="button" key={id} aria-pressed={mode===id} onClick={()=>changeSource(id)}>{label}</button>)}</div>
      {mode==='existing'&&<div className="cm-input-source"><label>{inputs===undefined?'选择虚构演示记录':'选择当前账户的记录'}<select aria-label="选择投资记录" value={selected} onChange={e=>{setSelected(Number(e.target.value));setDisclosure(defaultInvestmentDisclosure());resetReview();}}>{candidates.map((x,i)=><option key={i} value={i}>{investmentKindLabels[x.kind]} · {x.instrument || x.asOf} · {investmentSourceLabels[x.source]}</option>)}</select></label>{!candidates.length?<p>当前没有这种记录。可以切换分享类型，或导入文件、手动填写。</p>:<p>{inputs===undefined?'这里使用独立的虚构数据演示分享流程，不来自你的账户。':'仅使用当前账户已有的记录；缺失的收益率与回撤不会补算。'}</p>}</div>}
      {mode==='file'&&<div className="cm-investment-upload"><FileUp size={24}/><h3>导入你自己的投资记录</h3><p>支持下方模板的持仓 CSV，以及投镜导出的投资分享 JSON。文件在本机解析，原件不会加入社区。</p><label className="cm-file-pick">选择投资文件<input aria-label="选择投资文件" type="file" accept=".csv,.json,text/csv,application/json" disabled={loading} onChange={e=>void importFile(e.currentTarget.files?.[0])}/></label><button type="button" className="cm-rail-link" onClick={()=>downloadText('投镜-持仓分享模板.csv',holdingsCsvTemplate)}>下载持仓 CSV 模板<Download size={13}/></button>{loading&&<p role="status">正在本地解析…</p>}{imported&&<p role="status"><Check size={13}/>导入成功 · {investmentKindLabels[imported.kind]} · {imported.asOf} · 数据标为个人提供</p>}<small>暂不直接识别任意券商流水或截图；CSV 的仓位填写百分比，如 35 代表 35%。JSON 必须保留数据日期。</small></div>}
      {mode==='manual'&&<div className="cm-form-fields cm-manual-investment"><div className="cm-form-two"><label>数据截至日期<input aria-label="数据截至日期" placeholder="YYYY-MM-DD" value={manual.asOf} onChange={e=>setManual(m=>({...m,asOf:e.target.value}))}/></label><label>币种<select value={manual.currency} onChange={e=>setManual(m=>({...m,currency:e.target.value}))}><option>CNY</option><option>HKD</option><option>USD</option></select></label></div>{kind!=='holdings'&&<><div className="cm-form-two"><label>开始日期（可选）<input aria-label="开始日期" placeholder="YYYY-MM-DD" value={manual.start} onChange={e=>setManual(m=>({...m,start:e.target.value}))}/></label><label>结束日期（可选）<input aria-label="结束日期" placeholder="YYYY-MM-DD" value={manual.end} onChange={e=>setManual(m=>({...m,end:e.target.value}))}/></label></div>{kind==='episode'&&<div className="cm-form-two"><label>投资标的<input aria-label="投资标的" value={manual.instrument} onChange={e=>setManual(m=>({...m,instrument:e.target.value}))}/></label><label>经历状态<select value={manual.status} onChange={e=>setManual(m=>({...m,status:e.target.value as 'open'|'closed'}))}><option value="closed">已结束</option><option value="open">持有中</option></select></label></div>}<div className="cm-form-two"><label>收益率（%，可留空）<input aria-label="收益率百分比" placeholder="如 8.6" value={manual.returnPercent} onChange={e=>setManual(m=>({...m,returnPercent:e.target.value}))}/></label>{kind==='period'?<label>最大回撤（%，可留空）<input aria-label="最大回撤百分比" placeholder="如 9.1，显示为 -9.1%" value={manual.drawdownPercent} onChange={e=>setManual(m=>({...m,drawdownPercent:e.target.value}))}/></label>:<label>盈亏金额（可留空）<input aria-label="盈亏金额" value={manual.pnl} onChange={e=>setManual(m=>({...m,pnl:e.target.value}))}/></label>}</div>{kind==='period'&&<div className="cm-form-two"><label>账期盈亏金额（可留空）<input aria-label="账期盈亏金额" value={manual.pnl} onChange={e=>setManual(m=>({...m,pnl:e.target.value}))}/></label><label>期末资产（可留空）<input aria-label="期末资产" value={manual.equity} onChange={e=>setManual(m=>({...m,equity:e.target.value}))}/></label></div>}</>}{kind==='holdings'&&<><div className="cm-manual-holdings"><span>标的名称</span><span>仓位 %</span><span>市值（可选）</span><span/>{rows.map((r,i)=><div key={i}><input aria-label={`持仓 ${i+1} 名称`} value={r.name} onChange={e=>setRows(rs=>rs.map((v,j)=>i===j?{...v,name:e.target.value}:v))}/><input aria-label={`持仓 ${i+1} 仓位百分比`} value={r.weight} onChange={e=>setRows(rs=>rs.map((v,j)=>i===j?{...v,weight:e.target.value}:v))}/><input aria-label={`持仓 ${i+1} 市值`} value={r.value} onChange={e=>setRows(rs=>rs.map((v,j)=>i===j?{...v,value:e.target.value}:v))}/><button type="button" aria-label={`移除持仓 ${i+1}`} disabled={rows.length===1} onClick={()=>setRows(rs=>rs.filter((_,j)=>j!==i))}><X size={13}/></button></div>)}</div><button type="button" className="cm-button" disabled={rows.length>=100} onClick={()=>setRows(rs=>[...rs,{name:'',weight:'',value:''}])}><Plus size={13}/>增加持仓</button><small>仓位填写百分比，合计不能超过 100%。空白金额保留为未提供。</small></>}<p className="cm-manual-note">手动填写的数据会标记为“个人提供 · 未核验”。收益率与回撤不会根据你填写的资产金额推算。</p></div>}
      {liveCard&&<InvestmentShareCard card={liveCard} compact/>}
      {sourceError&&<p className="cm-input-hint">{sourceError}</p>}
    </>}
    {step===1&&<>
      <fieldset className="cm-disclosure"><legend><ShieldCheck size={15}/>选择这张卡展示什么</legend>{([['names','标的名称','名称关闭时会显示为“持仓 1”等匿名标签。'],['weights','仓位比例','展示来源记录中提供的比例与口径。'],['performance','收益率与回撤','仅展示已有或你填写的值，缺失不补零。'],['amounts','资金金额','包含所提供的资产、盈亏、净投入和持仓市值。'],['dates','投资日期','展示数据截至日期及所提供的区间。'],['counts','统计数字','控制持仓项目数和已结束经历数的数字；持仓列表仍按所选范围展示。']] as const).map(([key,label,description])=><label key={key}><input type="checkbox" checked={disclosure[key] ?? true} onChange={e=>{setDisclosure(d=>({...d,[key]:e.target.checked}));resetReview();}}/><span><strong>{label}</strong><small>{description}</small></span></label>)}</fieldset>
      {liveCard&&<InvestmentShareCard card={liveCard} compact/>}
      <div className="cm-form-fields cm-investment-narrative"><label>分享标题<input aria-label="投资分享标题" maxLength={160} placeholder={`例如：我的${investmentKindLabels[kind]}`} value={narrative.title} onChange={e=>setNarrative(n=>({...n,title:e.target.value}))}/></label><label>分享说明<textarea aria-label="投资分享说明" rows={3} maxLength={4000} placeholder="当时为什么这样投资？这次想分享什么？" value={narrative.thesis} onChange={e=>setNarrative(n=>({...n,thesis:e.target.value}))}/></label><div className="cm-form-two"><label>风险与反思<textarea aria-label="投资风险与反思" rows={3} maxLength={1600} value={narrative.risk} onChange={e=>setNarrative(n=>({...n,risk:e.target.value}))}/></label><label>后续观察事项<textarea aria-label="投资后续观察事项" rows={3} maxLength={1000} placeholder="每行一项，每项不超过 240 字" value={narrative.watch} onChange={e=>setNarrative(n=>({...n,watch:e.target.value}))}/></label></div><small>勾选项只控制数据卡。你手写的说明、反思和观察事项会原样显示，请在预览中一起核对。</small></div>
    </>}
    {step===2&&reviewCard&&<div className="cm-publish-preview"><h2>{narrative.title}</h2><InvestmentShareCard card={reviewCard}/><h3>分享说明</h3><p>{narrative.thesis}</p><h3>风险与反思</h3><p>{narrative.risk}</p><h3>后续观察</h3><ul className="cm-watch-list">{narrative.watch.split(/[\n；;]/).map(s=>s.trim()).filter(Boolean).map((w,i)=><li key={i}><span>{String(i+1).padStart(2,"0")}</span>{w}</li>)}</ul><p className="cm-share-final-notice">这就是加入社区的完整内容。原始文件、账户标识、持仓股数和逐笔成交流水不会附带加入。</p><button type="button" className="cm-button" onClick={()=>downloadText('投镜-投资分享.json',JSON.stringify(reviewCard,null,2),'application/json;charset=utf-8')}><Download size={13}/>导出这张数据卡</button>{!reviewCard.disclosure.dates&&<p className="cm-input-hint">日期已隐藏，这份文件可用于查看分享，不能重新导入为投资记录。需要再次导入时，请返回勾选投资日期。</p>}</div>}
    {error&&<p className="cm-inline-warning" role="alert">{error}</p>}
    <div className="cm-form-footer"><span>{remote?'发布给全体已登录成员，请核对数据与文字':'仅加入本地社区，不会向外部发送'}</span><div>{step>0&&<button type="button" className="cm-button" disabled={publishing} onClick={()=>{setStep(s=>s-1);setError('');}}><ArrowLeft size={12}/>返回</button>}{step<2?<button type="button" className="iw-primary" disabled={loading} onClick={advance}>{step===0?'选择展示范围':'预览完整分享'}<ArrowRight size={13}/></button>:<button type="button" className="iw-primary" disabled={publishing} onClick={async()=>{if(publishing)return;setPublishing(true);try{if(!reviewCard)throw new Error('请重新生成预览');await onPublish(reviewCard,narrative,requestId.current);onOpenChange(false);}catch(e){setError(e instanceof Error?e.message:'未能保存，请重试');}finally{setPublishing(false);}}}>{publishing?'正在发布…':remote?'确认发布给社区成员':'确认加入本地社区'}<Check size={13}/></button>}</div></div>
  </>;
}
