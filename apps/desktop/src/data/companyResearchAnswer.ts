import type { CompanyMessage,CompanyReply,ResearchAnswer } from './companyResearch.ts';
export class CompanyRequestError extends Error {
 code:string;status:number;
 constructor(code:string,message:string,status=503){super(message);this.code=code;this.status=status;}
}
function validateReply(reply:CompanyReply){
 if(!['ANSWERED','NOT_IN_MODEL','UNKNOWN'].includes(reply.status)||typeof reply.answer!=='string'||!Array.isArray(reply.citations)||(reply.status==='ANSWERED'&&!reply.citations.length))throw new Error('回答未通过证据格式检查。');
 return reply;
}
export async function requestGroundedCompanyAnswer(buildId:string,history:CompanyMessage[],call:<T>(action:string,params:Record<string,unknown>)=>Promise<T>,signal?:AbortSignal):Promise<ResearchAnswer>{
 let notice:string|undefined;
 try{
  const reply=validateReply(await call<CompanyReply>('chat',{build_id:buildId,messages:history.slice(-11)}));
  if(!(reply.status==='NOT_IN_MODEL'&&reply.reason_code==='ANSWER_VALIDATION_FAILED'))return {content:reply.display_answer||reply.answer,citations:reply.citations,source:'model',muted:reply.status!=='ANSWERED'};
  notice='模型回答未通过证据核验，已改用确定性资料查询。';
 }catch(error){
  if(signal?.aborted)throw error;
  const unavailable=error instanceof CompanyRequestError&&['company_model_unavailable','company_provider_failed'].includes(error.code);
  const nativeUnavailable=error instanceof Error&&/company_model_unavailable|company_provider_failed/.test(error.message);
  if(!unavailable&&!nativeUnavailable)throw error;
  notice='AI 模型暂不可用，以下为当前模型的确定性资料查询。';
 }
 const question=history.filter(m=>m.role==='user').at(-1)?.content||'';
 if(question.length>500)throw new Error('资料查询仅支持 500 字以内的问题，请缩短后重试。');
 const reply=validateReply(await call<CompanyReply>('ask',{build_id:buildId,question}));
 return {content:reply.display_answer||reply.answer,citations:reply.citations,source:'lookup',muted:reply.status!=='ANSWERED',notice};
}
