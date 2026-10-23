import { CompanyRequestError,requestGroundedCompanyAnswer } from './companyResearchAnswer.ts';
export { CompanyRequestError } from './companyResearchAnswer.ts';
import { isTauriRuntime, runtimeRequest } from './runtimeService';

export interface CompanyIdentity { company_id: string; short_name: string; legal_name?: string; listings?: {ticker:string;exchange?:string;market?:string}[] }
export interface CompanyBuild { build_id:string; company:string; query:string; identity?:CompanyIdentity|null; status:string; version_id:string|null; started_at:string|null; event_count:number }
export interface CompanyValue { period:string; value:string|null; display_value?:string; unit?:string; knowledge_status:string; validation_status:string; evidence_ids:string[] }
export interface CompanyMetric { key:string; name:string; unit:string; kind:string; values:CompanyValue[] }
export interface CompanySource { id:string; title:string; locator:string; note?:string }
export interface CompanyGraphNode { id:string; label:string; kind:string; detail?:string; note?:string; groupIds?:string[]; evidenceIds?:string[]; knowledge?:string; period?:{label:string}; value?:string|null; unit?:string }
export interface CompanyAnalysis { version_id:string; fingerprint:string; facts:CompanyMetric[]; ratios:CompanyMetric[]; quality: {numeric_observations:number; historical_validation_status:string; observation_validation_counts:Record<string,number>}; yoy?:Record<string,unknown> }
export interface CompanyRelation { id:string;source:string;target:string;kind:string;label?:string;evidenceIds?:string[] }
export interface CompanyGraph { relations?:Record<string,CompanyRelation>; modelVersion:{id:string;twinId:string}; nodes:Record<string,CompanyGraphNode>; sources:Record<string,CompanySource>; coverage:{entities:number;metrics:number}; fingerprint?:string }
export interface CompanyModel { build_id:string; analysis:CompanyAnalysis; graph:CompanyGraph }
export interface ResearchCompany extends CompanyModel { key:string; buildId:string; name:string; ticker:string }
export interface CompanyCapabilities { application:string; protocol_version:number; generic_builds:boolean; deterministic_qa:boolean; chat:{configured:boolean;provider:string;model:string;connectivity_verified:boolean} }
export interface CompanyResolution { query:string; status:'RESOLVED'|'AMBIGUOUS'|'NOT_FOUND'; candidates:{identity:CompanyIdentity;score:number;method:string}[] }
export interface CompanySnapshot { build_id:string; status:string; company_node:{id:string;label:string}|null; events:{seq:number;type:string;message:string;payload:Record<string,unknown>}[]; summary:Record<string,unknown>|null }
export interface CompanyCitation { index:number; entry_id?:number|string; observation_id?:string; label?:string; metric_name?:string; period?:string|null; detail?:string; display_detail?:string; evidence_ids?:string[]; locators?:string[]; validation_status?:string|null; knowledge_status?:string|null }
export interface CompanyReply { status:'ANSWERED'|'NOT_IN_MODEL'|'UNKNOWN'; answer:string; display_answer?:string; reason_code?:string|null; validation_issue?:string|null; citations:CompanyCitation[] }
export interface ResearchAnswer { content:string; citations:CompanyCitation[]; source:'model'|'lookup'; muted?:boolean; notice?:string }
export interface CompanyMessage { role:'user'|'assistant'; content:string }
export async function companyRequest<T>(action:string,params:Record<string,unknown>={},signal?:AbortSignal):Promise<T>{
 const method=`company_research.${action}`;
 if(isTauriRuntime())return runtimeRequest<T>(method,params);
 const controller=new AbortController();const abort=()=>controller.abort();
 if(signal?.aborted)controller.abort();else signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(()=>controller.abort(),action==='chat'?170_000:100_000);
 try{
  const response=await fetch('/api/company-research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,params}),signal:controller.signal});
  const payload=await response.json().catch(()=>null);
  if(!response.ok||!payload?.ok)throw new CompanyRequestError(payload?.error?.code||'company_engine_unavailable',payload?.error?.message||'公司研究引擎未连接，请从整合版启动入口打开投镜。',response.status);
  return payload.result as T;
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export async function requestCompanyAnswer(buildId:string,history:CompanyMessage[],signal?:AbortSignal):Promise<ResearchAnswer>{
 return requestGroundedCompanyAnswer(buildId,history,(action,params)=>companyRequest(action,params,signal),signal);
}

export const companyApi={
 status:(signal?:AbortSignal)=>companyRequest<CompanyCapabilities>('status',{},signal),
 list:(signal?:AbortSignal)=>companyRequest<{builds:CompanyBuild[]}>('list',{},signal),
 load:(buildId:string,signal?:AbortSignal)=>companyRequest<CompanyModel>('load',{build_id:buildId},signal),
 resolve:(query:string,signal?:AbortSignal)=>companyRequest<CompanyResolution>('resolve',{query},signal),
 build:(query:string)=>companyRequest<{build_id:string;status:string}>('build',{query}),
 snapshot:(buildId:string,signal?:AbortSignal)=>companyRequest<CompanySnapshot>('snapshot',{build_id:buildId},signal),
 report:(buildId:string)=>companyRequest<{html:string}>('report',{build_id:buildId}),
};
