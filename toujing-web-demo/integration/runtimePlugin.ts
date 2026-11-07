import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {existsSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import type {Plugin} from 'vite';

// Reuse the product protocol and its scheduling/financial gates. Only public
// research and the isolated teaching portfolio can be addressed by this host.
const groups: Record<string, string[]> = {
  'workbench': ['catalog', 'context', 'joint_price_research'],
  'workbench.research': ['start','status','list','cancel','resume','citation','library'],
  'workbench.strategy': ['catalog','discover','propose','save','list','run','export','import','experiment.get','report.save','source.save'],
  'workbench.company': ['catalog','financials','cashflow','operating','source.page','source.search','source.locate','valuation'],
  'workbench.session': ['create'],
  'workbench.decision': ['preview','confirm','list','operation'],
  'workbench.watch': ['enable','list','run_due'],
};
export const allowedMethods = new Set(Object.entries(groups).flatMap(([prefix, names]) => names.map(n => `${prefix}.${n}`)));
export function allowedRequest(method: unknown, params: unknown): boolean {
  if (typeof method !== 'string' || !allowedMethods.has(method) || !params || typeof params !== 'object' || Array.isArray(params)) return false;
  const p=params as Record<string,unknown>;
  if ('use_model' in p && p.use_model !== false) return false;
  if ('library_scope' in p && JSON.stringify(p.library_scope)!==JSON.stringify({demo:true})) return false;
  const forbidden=new Set(['subject_id','account_id','paper_ref','shared_ref','file_path','api_key','token','password','_desktop_model_key','_desktop_search_key']);
  const inspect=(v:unknown):boolean => !v || typeof v!=='object' || Object.entries(v).every(([k,x])=>!forbidden.has(k.toLowerCase())&&inspect(x));
  return inspect(p);
}
export default function runtimePlugin():Plugin {
  let child:ChildProcessWithoutNullStreams|undefined;
  let buffer=''; let count=0; let failure='';
  const pending=new Map<string,{resolve:(v:unknown)=>void;reject:(e:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
  function detach(process:ChildProcessWithoutNullStreams, reason:string){
    if(child!==process)return;
    child=undefined;
    failure=reason;
    for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error(reason));}
    pending.clear();
  }
  function stop(){
    if(!child)return;
    const process=child;
    detach(process,'runtime_stopped');
    process.stdin.end();
    process.kill('SIGTERM');
  }
  return {name:'toujing-existing-runtime',configureServer(server){
    const root=server.config.root;
    const product=resolve(root,'../../投镜_R6_开发候选_20261028/product');
    const python=resolve(product,'.venv/bin/python');
    const origins=new Set(['http://127.0.0.1:18042','http://localhost:18042']);
    const boot=()=>{
      if(child)return child;
      if(!existsSync(python))throw new Error('product_python_unavailable');
      const state=resolve(root,'.local/aligned-runtime');mkdirSync(state,{recursive:true});
      const inherited=['PATH','LANG','LC_ALL','TMPDIR','TZ'];
      const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>inherited.includes(key)));
      const runtime=spawn(python,['-u','-m','toujing_core_runtime','--db-path',resolve(state,'demo.sqlite3')],{
        cwd:product,env:{...env,PYTHONDONTWRITEBYTECODE:'1',PYTHONNOUSERSITE:'1'}
      });
      child=runtime;
      buffer=''; failure='';
      runtime.stdout.on('data',chunk=>{if(child!==runtime)return;buffer+=chunk;let i:number;while((i=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,i);buffer=buffer.slice(i+1);try{const value=JSON.parse(line);const item=pending.get(value.request_id);if(item){clearTimeout(item.timer);pending.delete(value.request_id);item.resolve(value);}}catch{/* Protocol diagnostics never become results. */}}});
      runtime.stderr.on('data',()=>{});
      runtime.on('error',()=>detach(runtime,'runtime_start_failed'));
      runtime.stdin.on('error',()=>detach(runtime,'runtime_connection_closed'));
      runtime.on('exit',()=>detach(runtime,'runtime_stopped'));
      return runtime;
    };
    server.httpServer?.once('close',stop);
    server.middlewares.use('/api/toujing',async(req,res,next)=>{
      const send=(status:number,data:unknown)=>{res.statusCode=status;res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.end(JSON.stringify(data));};
      if(!['127.0.0.1:18042','localhost:18042'].includes(req.headers.host??''))return send(403,{error:'invalid_host'});
      if(req.method==='GET'&&req.url==='/health')return send(200,{available:existsSync(python),running:!!child,mode:'isolated_demo',model_calls:false,real_accounts:false,error:failure||null});
      if(req.url!=='/runtime')return next();
      if(req.method!=='POST'||!origins.has(req.headers.origin??'')||req.headers['sec-fetch-site']==='cross-site')return send(403,{error:'invalid_origin'});
      if(!req.headers['content-type']?.startsWith('application/json'))return send(415,{error:'json_required'});
      try{
        let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>1024*1024)return send(413,{error:'request_too_large'});}
        const input=JSON.parse(body);
        if(Object.keys(input).sort().join(',')!=='method,params'||!allowedRequest(input.method,input.params))return send(403,{error:'demo_scope_required'});
        if(pending.size>=16)return send(429,{error:'runtime_busy'});
        const p=boot();const id=`web-demo-${++count}-${Date.now()}`;
        const result=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error('request_result_unknown'));},120000);pending.set(id,{resolve,reject,timer});p.stdin.write(JSON.stringify({protocol_version:'1',request_id:id,method:input.method,params:input.params})+'\n');});
        send(200,result);
      }catch(e){send(503,{error:e instanceof Error?e.message:'runtime_unavailable'});}
    });
  }};
}
