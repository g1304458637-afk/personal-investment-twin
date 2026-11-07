import {useEffect,useState} from 'react';
import {Archive,ArrowRight,FolderOpen,Plus,Trash2} from 'lucide-react';
import {runtime,type ResearchTask} from './alignment';

type Conversation = {id:string;title:string;project_id:string|null;task_count:number;status:string};
type Project = {id:string;title:string};
type LibraryPage = {conversations:Conversation[];projects:Project[]};
type DeletePreview = {conversation_id:string;title:string;task_count:number;fingerprint:string};
const localLibrary=(action:string,params:Record<string,unknown>={})=>
 runtime('workbench.research.library',{action,library_scope:{demo:true},...params});

export function ResearchLibraryPanel({onOpen,onDeleted}:{onOpen:(tasks:ResearchTask[])=>void;onDeleted:(id:string)=>void}){
 const [status,setStatus]=useState<'active'|'archived'|'deleted'>('active');
 const [library,setLibrary]=useState<LibraryPage>({conversations:[],projects:[]});
 const [projectTitle,setProjectTitle]=useState('');
 const [revision,setRevision]=useState(0);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [preview,setPreview]=useState<DeletePreview|null>(null);
 useEffect(()=>{
  let active=true;
  setError('');
  setBusy(true);
  localLibrary('list',{status}).then(value=>{if(active)setLibrary(value);})
   .catch(e=>{if(active)setError(e.message);})
   .finally(()=>{if(active)setBusy(false);});
  return()=>{active=false;};
 },[status,revision]);
 const attempt=async(action:()=>Promise<void>)=>{
  setBusy(true);
  setError('');
  try{await action();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 };
 const write=(action:string,params:Record<string,unknown>)=>attempt(async()=>{
  await localLibrary(action,{...params,operation_id:crypto.randomUUID()});
  setRevision(n=>n+1);
 });
 return <div className="detail-stack research-library">
  <div className="small-segmented" role="group" aria-label="对话状态">
   {([{id:'active',name:'当前'},{id:'archived',name:'已归档'},{id:'deleted',name:'已删除'}]as const).map(item=>
    <button key={item.id} className={status===item.id?'active':''} disabled={busy} onClick={()=>{setPreview(null);setStatus(item.id);}}>{item.name}</button>)}
  </div>
  <details><summary>本地研究项目 · {library.projects.length}</summary>
   <form className="document-search" onSubmit={e=>{e.preventDefault();if(!projectTitle.trim()||busy)return;void write('project.create',{title:projectTitle.trim()});setProjectTitle('');}}>
    <input value={projectTitle} onChange={e=>setProjectTitle(e.target.value)} aria-label="研究项目名称" maxLength={80} placeholder="新项目名称"/>
    <button className="secondary small" disabled={busy||!projectTitle.trim()}><Plus size={14}/>新建</button>
   </form>
   {library.projects.map(project=><p key={project.id}>{project.title}</p>)}
  </details>
  {error&&<p className="form-error" role="alert">{error}</p>}
  {busy&&<p role="status">正在读取本地对话…</p>}
  {!busy&&!library.conversations.length&&<p>这里还没有对话。</p>}
  {library.conversations.map(conversation=><section className="library-conversation" key={conversation.id}>
   <button className="history-item" disabled={busy||status==='deleted'} onClick={()=>void attempt(async()=>{
    const result=await localLibrary('open',{conversation_id:conversation.id});
    if(!result.tasks.length){setError('这段对话没有可读取的研究。');return;}
    onOpen(result.tasks);
   })}><FolderOpen size={15}/><span>{conversation.title}<small>{conversation.task_count} 轮研究</small></span><ArrowRight size={14}/></button>
   {status==='deleted'?<button className="secondary small" disabled={busy} onClick={()=>void write('restore',{conversation_id:conversation.id})}>恢复对话</button>:<div className="library-actions">
    <select aria-label="移动对话到项目" value={conversation.project_id??''} disabled={busy} onChange={e=>void write('update',{conversation_id:conversation.id,project_id:e.target.value||null})}>
     <option value="">无项目</option>{library.projects.map(p=><option value={p.id} key={p.id}>{p.title}</option>)}
    </select>
    <button className="text-button" disabled={busy} onClick={()=>void write('update',{conversation_id:conversation.id,status:status==='active'?'archived':'active'})}><Archive size={14}/>{status==='active'?'归档':'移回当前'}</button>
    <button className="text-button" disabled={busy} onClick={()=>void attempt(async()=>setPreview(await localLibrary('preview_delete',{conversation_id:conversation.id})))}><Trash2 size={14}/>删除</button>
   </div>}
  </section>)}
  {preview&&<div className="decision-confirm">
   <p>将「{preview.title}」和其中 {preview.task_count} 轮研究移到已删除。可从「已删除」恢复。</p>
   <div className="button-row"><button className="secondary small" onClick={()=>setPreview(null)}>取消</button><button className="primary small" disabled={busy} onClick={()=>void attempt(async()=>{
    await localLibrary('delete',{conversation_id:preview.conversation_id,fingerprint:preview.fingerprint,confirmation:'DELETE_CONVERSATION',operation_id:crypto.randomUUID()});
    onDeleted(preview.conversation_id);
    setPreview(null);
    setRevision(n=>n+1);
   })}>确认删除</button></div>
  </div>}
 </div>;
}
