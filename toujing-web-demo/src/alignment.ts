import type {DemoData, Fill} from './model';

export type ResearchScope={
  instrument_id:string;start:string;end:string;knowledge_at:string;
  mode:'hindsight'|'as_known_then';kind:'range'|'candle'|'execution'|'career'|'disclosure';
  focus:'public_price'|'personal_review';origin:'career'|'decision'|'replay'|'company'|'strategy'|'community';
  execution_id?:string;experiment_ref?:string;path_ids?:string[];
  historical_proof?:'hindsight'|'public_reconstruction'|'original_snapshot';
  selection_object?:{document_id:string;page:number;start:number;end:number};
};
export type Evidence={id:string;kind:string;text:string;source_url?:string;date?:string;[key:string]:unknown};
export type ResearchContext={selection_ref:string;selection:ResearchScope;stats:{price_return:string|null;max_close_drawdown:string|null;start_close:string|null;end_close:string|null};evidence:Evidence[];trades:Fill[];sources:{url?:string;sha256:string}[];[key:string]:unknown};
export type PriceAttribution={
  observed_return_pct:string;model_name?:string;summary?:string;evidence_id?:string;
  components:{key:string;label?:string;contribution_pp:string;parameter_interval_95_pp:[string,string];mechanism?:string}[];
  formula:string;link_formula?:string;interval_policy:string;interpretation:string;
};
export type ResearchTask={task_id:string;conversation_id:string;library_conversation_id?:string;origin_session_id?:string|null;question:string;selection:ResearchScope;status:string;error_code:string|null;state:{completed_tools?:string[];events?:{tool:string;record_count:number}[]};result:null|{sections:{kind:string;text:string;evidence_refs:string[]}[];evidence:Evidence[];next_questions:string[];model_called:boolean;calculation_receipts?:unknown[];price_attribution?:PriceAttribution;strategy_artifacts?:unknown[];[key:string]:unknown};[key:string]:unknown};
export type CapabilityId='career'|'episodes'|'historical'|'selection'|'factors'|'behavior'|'memory'|'research'|'strategy'|'replay'|'operating'|'financial'|'documents'|'valuation'|'decisions'|'watch'|'community'|'follow'|'import'|'projects'|'settings';
export const capabilities:{id:CapabilityId;name:string;owner:string;method:string;source:string;delivery:'runtime'|'archive'|'local'|'preview';description:string}[]=[
  {id:'career',name:'投资生涯',owner:'我的投资',method:'workbench.strategy.catalog',source:'src/research_workbench/strategy_studio.py',delivery:'archive',description:'六年账本归档、年度投入与损益，金额保留原始文本。'},
  {id:'episodes',name:'同一股票的投资经历',owner:'我的投资',method:'investment-episodes.json → 原账本 project() 投影',source:'src/ledger/engine.py / scripts/build-investment-episodes.py',delivery:'archive',description:'按证券与建仓至清仓分组，逐笔回到相应行情。'},
  {id:'historical',name:'历史信息环境',owner:'我的投资',method:'workbench.context → workbench.research.start',source:'toujing_core_runtime/decision_context.py',delivery:'runtime',description:'固定证券、区间、知识截止和成交标识，分别查看当时与后来的资料。'},
  {id:'selection',name:'框选行情解释',owner:'我的投资',method:'workbench.context → workbench.research.start',source:'apps/desktop/src/workspace/ResearchWorkbench.tsx',delivery:'runtime',description:'拖出区间，暂停回放，在原页解释和追问。'},
  {id:'factors',name:'价格因素与模型',owner:'我的投资',method:'workbench.joint_price_research',source:'src/research_workbench/joint_price_research.py',delivery:'runtime',description:'调用既有统计工具，查看结果、模型对照及计算来源。'},
  {id:'behavior',name:'行为规律与反例',owner:'我的投资',method:'workbench.strategy.discover',source:'src/research_workbench/strategy_studio.py',delivery:'runtime',description:'从教学记录重新读取行为样本、反例和规则候选。'},
  {id:'memory',name:'长期记忆与修订',owner:'我的投资',method:'ledger.memory / recall_research',source:'src/ledger/investment_memory.py',delivery:'local',description:'网页演示保存来源、范围和修订；与正式账户记忆分开。'},
  {id:'research',name:'同一个研究助手',owner:'所有页面',method:'workbench.research.start/status/cancel/resume/citation',source:'toujing_core_runtime/research_agent.py',delivery:'runtime',description:'原研究 Agent 的离线工具流程；任务和证据保存在隔离运行时。'},
  {id:'strategy',name:'策略共创与版本',owner:'我的策略',method:'workbench.strategy.propose/save/list/import/export',source:'toujing_core_runtime/strategy_studio.py',delivery:'runtime',description:'草稿、确认版本、导入导出使用原有策略合同。'},
  {id:'replay',name:'六路径同场回放',owner:'我的投资',method:'workbench.strategy.run/experiment.get',source:'src/research_workbench/strategy_studio.py',delivery:'runtime',description:'读取已有归档或原引擎新计算，行情与六路径共用时钟。'},
  {id:'operating',name:'公司经营结构',owner:'公司研究',method:'workbench.company.operating',source:'company/src/cot/analysis/operating_structure.py',delivery:'runtime',description:'原公司引擎的报告节点与关系，按原来源资格展示。'},
  {id:'financial',name:'财务与现金流',owner:'公司研究',method:'workbench.company.financials/cashflow',source:'toujing_core_runtime/public_company.py',delivery:'runtime',description:'原财务通路，保留主体、期间、单位和金融门禁。'},
  {id:'documents',name:'原文阅读与定位',owner:'公司研究',method:'workbench.company.source.page/search/locate',source:'company/src/cot/analysis/filing_research.py',delivery:'runtime',description:'页内搜索与原文定位，选段送入同一研究上下文。'},
  {id:'valuation',name:'估值实验',owner:'公司研究',method:'workbench.company.valuation',source:'company/src/cot/analysis/valuation.py',delivery:'runtime',description:'确认情景假设后调用现有 FCFF 模型，展示公式与敏感度。'},
  {id:'decisions',name:'判断与计划',owner:'我的投资 / 公司研究',method:'workbench.decision.preview/confirm/list',source:'src/research_workbench/decision_timeline.py',delivery:'runtime',description:'用户确认的时间与版本，保留旧判断。'},
  {id:'watch',name:'后续检查',owner:'我的投资 / 公司研究',method:'workbench.watch.enable/list/run_due',source:'src/research_workbench/decision_timeline.py',delivery:'runtime',description:'查看及运行已配置本地资料的检查任务。'},
  {id:'community',name:'分享与同图比较',owner:'研究社区',method:'/api/community/posts / workbench.shared.*',source:'toujing_community/service.py',delivery:'local',description:'本地演示身份和选定分享内容；不连接线上社区。'},
  {id:'follow',name:'模拟跟随',owner:'研究社区',method:'/api/community/paper-follows',source:'toujing_community/paper_follow.py',delivery:'preview',description:'本页演示资金比例和跟随状态；订单级执行与实盘尚未接入此网页。'},
  {id:'import',name:'导入与对账',owner:'资料与账户',method:'trades.preview/commit / ledger.reconcile',source:'toujing_core_runtime/ledger.py',delivery:'preview',description:'CSV 独立预览；不会把导入成功伪装成已生成正式账本。'},
  {id:'projects',name:'本地对话与项目',owner:'所有页面',method:'workbench.research.library',source:'src/research_workbench/library.py',delivery:'runtime',description:'研究任务持久化；当前网页另保留原对话记录。'},
  {id:'settings',name:'模型与权限',owner:'设置',method:'model.status / backup.*',source:'apps/desktop/src/data/modelService.ts',delivery:'preview',description:'网页只调用本地工具，不接收密钥，不代替原生 Keychain 和账户授权。'},
];
export const deliveryLabel={runtime:'原运行时',archive:'引擎归档',local:'本地演示',preview:'流程预览'};
export const statusLabel:Record<string,string>={running:'正在研究',cancel_requested:'正在取消',cancelled:'已取消',interrupted:'可继续研究',failed:'未完成',completed:'已完成',stale:'资料已更新'};
export function defaultScope(data:DemoData,ticker:string,origin:ResearchScope['origin']='replay'):ResearchScope{
  return {instrument_id:ticker,start:data.dates[0],end:data.dates.at(-1)!,knowledge_at:origin==='company'?new Date().toISOString():data.dates.at(-1)!+'T23:59:59+08:00',mode:'hindsight',kind:'range',focus:origin==='company'||origin==='replay'?'public_price':'personal_review',origin,historical_proof:'hindsight',experiment_ref:data.experiment_id};
}
export function selectionParams(s:ResearchScope){return {instrument_id:s.instrument_id,start:s.start,end:s.end,knowledge_at:s.knowledge_at,mode:s.mode,kind:s.kind,...(s.execution_id?{execution_id:s.execution_id}:{})};}
export function scopeLabel(s:ResearchScope){
  if(s.origin==='company')return `${s.instrument_id} · 公开公司资料 · 截至 ${s.knowledge_at.slice(0,10)}`;
  return `${s.instrument_id} · ${s.start}—${s.end} · ${s.focus==='personal_review'?'教学账户复盘':'公开资料'}${s.mode==='as_known_then'?' · 当时视角':''}`;
}
export function scopeKey(s:ResearchScope){return JSON.stringify([s.instrument_id,s.start,s.end,s.knowledge_at,s.mode,s.kind,s.focus,s.execution_id,s.origin,s.selection_object]);}
export async function runtime<T=any>(method:string,params:Record<string,unknown>={}):Promise<T>{
  let response:Response;
  try{response=await fetch('/api/toujing/runtime',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,params})});}catch{throw new Error('本机研究服务未连接，保留了当前输入。');}
  if(!(response.headers.get('content-type')??'').includes('application/json'))throw new Error('此静态预览没有运行时，请用本项目的本地启动入口。');
  const body=await response.json();
  if(!response.ok||body.ok!==true){const code=body.error?.message??body.error?.code??body.error??'研究未完成';throw new Error(typeof code==='string'?code:JSON.stringify(code));}
  return body.result as T;
}
export const contextFor=(s:ResearchScope)=>runtime<ResearchContext>('workbench.context',{selection:selectionParams(s)});
export function taskText(task:ResearchTask){
  const sections=task.result?.sections??[];
  const narrative=sections.filter(section=>section.kind==='analysis');
  return (narrative.length?narrative:sections).slice(0,3)
    .map(section=>section.text.length>400?section.text.slice(0,400)+'…':section.text).join('\n\n');
}
export function taskAccess(task:ResearchTask):Record<string,unknown>{
  return (task.web_access as Record<string,unknown>)??(task.origin_session_id?{research_session_id:task.origin_session_id,library_scope:{demo:true}}:{});
}
export function presentTask(task:ResearchTask,scope:ResearchScope,access:Record<string,unknown>={}):ResearchTask{return {...task,selection:scope,web_access:access};}
export async function beginResearch(question:string,s:ResearchScope,parent?:ResearchTask,conversation?:string){
  const params:Record<string,unknown>={question,use_model:false,operation_id:crypto.randomUUID()};
  const continued=parent?.status==='completed'&&scopeKey(parent.selection)===scopeKey(s);
  let access:Record<string,unknown>={};
  if(s.origin==='company'){
    let sessionId=continued?taskAccess(parent!).research_session_id:undefined;
    if(!sessionId){
      const result=await runtime<{session:{session_id:string}}>('workbench.session.create',{
        operation_id:crypto.randomUUID(),instrument_id:s.instrument_id,knowledge_at:s.knowledge_at,
        historical_proof:s.mode==='as_known_then'?'public_reconstruction':'hindsight',
        ...(s.selection_object?{selection_object:s.selection_object}:{})
      });
      sessionId=result.session.session_id;
    }else params.parent_task_id=parent!.task_id;
    access={research_session_id:sessionId,library_scope:{demo:true}};
    Object.assign(params,access);
  }else{
    const context=await contextFor(s);Object.assign(params,{selection_ref:context.selection_ref,research_focus:s.focus});
    if(continued)params.parent_task_id=parent!.task_id;
  }
  if(conversation)params.library_conversation_id=conversation;
  const result=await runtime<{task:ResearchTask}>('workbench.research.start',params);
  return {task:presentTask(result.task,s,access)};
}
export function normalizeExperiment(raw:any,previous:DemoData):DemoData{
  if(!Array.isArray(raw.dates)||!raw.dates.length||raw.paths?.length!==6||!raw.bars||!raw.source_fingerprint)throw new Error('实验结果不完整，保留原回放。');
  if(raw.paths.some((p:any)=>p.days?.length!==raw.dates.length||p.days.some((d:any,i:number)=>d.date!==raw.dates[i])))throw new Error('实验各路径日期不一致，保留原回放。');
  return {...previous,...raw,paths:raw.paths.map((p:any)=>({...p,rule_card:p.rule_card??[],days:p.days.map((d:any)=>({...d,position_count:d.position_count??Object.keys(d.holdings??{}).length}))})),events:previous.events,experiment_id:raw.artifact_ref??raw.experiment_id};
}
export function safeSource(url:unknown):string|undefined{if(typeof url!=='string')return;try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)?u.href:undefined;}catch{return;}}
