import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowUpRight, Building2, FileText, LoaderCircle, MessageCircle, Send, X } from 'lucide-react';
import { GlassOrbLogo } from '@/components/common/GlassOrbLogo';
import { requestCompanyAnswer, type CompanyCapabilities, type CompanyCitation, type CompanyMessage, type ResearchAnswer, type ResearchCompany } from '@/data/companyResearch';

type Turn={question:string;reply?:ResearchAnswer;error?:string};
export function ResearchChat({company,period,capabilities,onClose,onCitation,active}:{active:boolean;company:ResearchCompany;period:string;capabilities:CompanyCapabilities|null;onClose:()=>void;onCitation:(c:CompanyCitation)=>void}){
 const [question,setQuestion]=useState(''),[turns,setTurns]=useState<Turn[]>([]),[asking,setAsking]=useState(false);
 const body=useRef<HTMLDivElement>(null),input=useRef<HTMLTextAreaElement>(null),flight=useRef<AbortController|null>(null),busy=useRef(false),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;input.current?.focus();return()=>{mounted.current=false;flight.current?.abort();};},[]);
 useEffect(()=>{if(active)input.current?.focus();},[active]);
 useEffect(()=>{body.current?.scrollTo({top:body.current.scrollHeight,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});},[turns,asking]);
 const send=async(q:string)=>{
  const text=q.trim();if(!text||busy.current)return;busy.current=true;setAsking(true);setQuestion('');
  const history:CompanyMessage[]=turns.flatMap(t=>[{role:'user' as const,content:t.question},...(t.reply?[{role:'assistant' as const,content:t.reply.content}]:[])]);
  history.push({role:'user',content:text});const controller=new AbortController();flight.current=controller;
  setTurns(p=>[...p,{question:text}]);
  try{const reply=await requestCompanyAnswer(company.buildId,history,controller.signal);if(mounted.current)setTurns(p=>p.map((t,i)=>i===p.length-1?{...t,reply}:t));}
  catch(error){if(mounted.current&&!controller.signal.aborted)setTurns(p=>p.map((t,i)=>i===p.length-1?{...t,error:error instanceof Error?error.message:'暂时无法回答，请稍后重试。'}:t));}
  finally{busy.current=false;if(mounted.current){setAsking(false);input.current?.focus();}}
 };
 const prompts=capabilities?.chat.configured?['这家公司主要做什么？',`${period}营业收入是多少？`,'哪些信息还需要核验？']:[`${period}营业收入是多少？`,'归母净利润是多少？','经营现金流是多少？'];
 return createPortal(<div className="cr-app cr-overlay-root" style={{display:active?undefined:'none'}}><aside className="cr-ask-panel" role="dialog" aria-label="问投镜公司研究" onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();onClose();}}}><header><div><MessageCircle size={19}/><h2>问投镜 · 公司研究</h2></div><button className="iw-icon-button" aria-label="关闭公司问答" onClick={onClose}><X size={18}/></button></header><div className="cr-ask-context"><Building2 size={15}/>{company.name}<span>当前模型</span></div><div className="cr-ask-body" ref={body} role="log" aria-live="polite"><div className="cr-ask-welcome"><GlassOrbLogo/><h3>从一个问题开始</h3><p>围绕这家公司，把资料和证据串起来。</p><small>{capabilities?.chat.configured?'依据当前模型回答 · 关键事实有引用':'AI 尚未配置 · 可查询已有财务记录'}</small></div><div className="cr-prompts">{prompts.map(q=><button key={q} onClick={()=>void send(q)} disabled={asking}>{q}<ArrowUpRight size={13}/></button>)}</div>{turns.map((t,i)=><div className="cr-conversation" key={i}><div className="cr-question">{t.question}</div>{t.reply&&<div className="cr-answer"><span className="iw-kicker">{t.reply.source==='model'?'公司模型问答':'确定性资料查询'}</span>{t.reply.notice&&<p className="cr-answer-notice">{t.reply.notice}</p>}<p className={t.reply.muted?'cr-answer-muted':''}>{t.reply.content}</p>{t.reply.citations.map(c=><button key={c.index} className="cr-citation" onClick={()=>onCitation(c)}><FileText size={12}/>[{c.index}] {c.label||c.metric_name||'模型证据'}<ArrowUpRight size={11}/></button>)}</div>}{t.error&&<p className="cr-inline-notice" role="alert">{t.error}</p>}</div>)}{asking&&<div className="cr-chat-pending" role="status"><LoaderCircle size={14} className="animate-spin"/>正在核对模型和证据…</div>}</div><form onSubmit={e=>{e.preventDefault();void send(question);}}><label htmlFor="company-question" className="sr-only">输入公司研究问题</label><textarea id="company-question" ref={input} rows={2} maxLength={4000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder={`关于${company.name}，你想了解什么？`} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send(question);}}}/><div><span>当前模型与证据 · 关键事实请核对原文</span><button type="submit" disabled={!question.trim()||asking} aria-label="发送公司研究问题"><Send size={16}/></button></div></form></aside></div>,document.body);
}
