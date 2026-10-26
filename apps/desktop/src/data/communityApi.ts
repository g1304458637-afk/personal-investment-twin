import type { PublishedInvestmentCard } from './investmentSharing';
export interface Member { id:string; username:string; name:string }
export interface MemberPost { id:number; author:Member; created:number; isOwn:boolean; following:boolean; commentsCount:number; updatesCount:number; card:PublishedInvestmentCard; title:string; thesis:string; risk:string; watchpoints:string[] }
export interface MemberText { id:number; author:Member; body:string; created:number; isOwn:boolean }
export interface MemberActivity {id:number;postId:number;kind:'comments'|'updates';created:number;name:string;username:string;title:string}
export interface Page<T> {items:T[];next:number|null}
let csrf='';
export class CommunityError extends Error { status:number; constructor(status:number,message:string){super(message);this.status=status;} }
export async function communityApi<T>(path:string, body?:unknown, signal?:AbortSignal):Promise<T> {
  const response=await fetch(`/api/community/${path}`,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal,headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await response.json().catch(()=>({error:'社区服务暂不可用，请检查服务是否启动。'}));
  if(!response.ok)throw new CommunityError(response.status,result.error || '社区请求失败，请重试。');
  if(typeof result.csrf==='string')csrf=result.csrf;
  if(path==='logout')csrf='';
  return result as T;
}
/** Match the server's unverified-public-source normalization before preview/consent. */
export function communityCard(card:PublishedInvestmentCard):PublishedInvestmentCard {
  return {...structuredClone(card),source:card.source==='synthetic'?'synthetic':'user_reported',returnBasis:'returnValue' in card.metrics?'user_reported':'unavailable',pnlBasis:'user_reported',definitions:[card.source==='synthetic'?'演示数据，不代表真实投资表现。':'由发布者提供，未经券商或第三方核验；仅展示发布者选择的数据。']};
}
