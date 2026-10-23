import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ArrowUpRight, ChevronRight, X } from 'lucide-react';
import * as echarts from 'echarts';
import { ReactFlow, Background, Controls, Handle, Position, MarkerType, type Node, type NodeProps, type Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { relationNeighborhood } from '@/data/companyResearchGraph';
import { currencyInHundredMillions, displayValue, unitName } from '@/data/companyResearchFormatting';
import type { CompanyRelation, ResearchCompany, CompanyMetric, CompanySource, CompanyGraphNode } from '@/data/companyResearch';
type OperatingData = { root?:boolean; caption:string; label:string; detail:string; [key:string]:unknown };
type OperatingNode = Node<OperatingData, 'research'>;
const groups = [
 ['sm-products','产品与服务','公司向市场提供什么'], ['sm-manufacturing','生产与交付','产品如何生产和交付'],
 ['sm-assets','资产与产能','经营依赖哪些资产'], ['sm-rd','研发与创新','长期竞争力从哪里来'],
 ['sm-commercial','客户与市场','收入来自哪些市场'], ['sm-accounting','财务与现金流','经营如何反映到财务'], ['sm-external','外部环境','政策和行业有哪些影响']
];
const tabs=[['overview','公司概览'],['financial','财务分析'],['graph','经营图谱'],['evidence','证据资料']];
const metricKeys=['revenue','net_profit_attributable','operating_cash_flow','roe_weighted'];
const shortNames:Record<string,string>={revenue:'营业收入',net_profit_attributable:'归母净利润',operating_cash_flow:'经营现金流',roe_weighted:'加权净资产收益率'};
const excerpt=(s:CompanySource|undefined)=>s?.note?.split('Source excerpt: ')[1]?.split(' Raw artifact SHA-256:')[0]||s?.note||'此记录未提供摘录。';
const sourceUrl=(s:CompanySource|undefined)=>{const url=s?.locator?.split(' · ')[0];return /^https:\/\//.test(url||'')?url:null;};
const allMetrics=(c:ResearchCompany)=>[...c.analysis.facts,...c.analysis.ratios];
const metric=(c:ResearchCompany,key:string)=>allMetrics(c).find(m=>m.key===key);
const valueAt=(m:CompanyMetric|undefined,y:string)=>m?.values?.find(v=>/^20\d{2}$/.test(y)?new RegExp(`^${y}年(?:末)?$`).test(v.period):v.period===y);
function TrendChart({company,selected,theme}:{company:ResearchCompany;selected:string;theme:string}){
 const el=useRef<HTMLDivElement>(null),item=metric(company,selected);
 const values=item?.values.filter(v=>/^20\d{2}年$/.test(v.period))||[];
 const hasAnnualData=values.some(v=>currencyInHundredMillions(v.value,v.unit||item?.unit)!==null);
 useEffect(()=>{
  if(!el.current||!item||!hasAnnualData)return;
  const chart=echarts.init(el.current),dark=theme==='dark',color=dark?'#b6ddf5':'#245b7d';
  chart.setOption({animationDuration:400,grid:{left:12,right:20,top:32,bottom:22,containLabel:true},tooltip:{trigger:'axis',backgroundColor:dark?'#182637':'#f5f9fd',borderColor:color,textStyle:{color:dark?'#f2f6fb':'#203044'},formatter:(p:unknown)=>{const first=(Array.isArray(p)?p[0]:p) as {axisValue:string;value:number};return `${first.axisValue}<br/>${shortNames[selected]||'财务指标'}：${first.value==null?'未覆盖':first.value.toLocaleString('zh-CN',{maximumFractionDigits:2})+' 亿元'}`;}},xAxis:{type:'category',boundaryGap:false,data:values.map(v=>v.period),axisLine:{show:false},axisTick:{show:false},axisLabel:{color:dark?'#b6c3d3':'#4c6076',margin:15,fontSize:11}},yAxis:{type:'value',splitNumber:3,axisLabel:{color:dark?'#b6c3d3':'#4c6076',fontSize:10},splitLine:{lineStyle:{color:dark?'rgba(232,244,255,.09)':'rgba(25,53,81,.12)',type:'dashed'}}},series:[{name:item.name,type:'line',data:values.map(v=>currencyInHundredMillions(v.value,v.unit||item.unit)),smooth:.25,symbol:'circle',symbolSize:8,lineStyle:{width:2.5,color},itemStyle:{color,borderColor:dark?'#1d3347':'#fff',borderWidth:3},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:dark?'rgba(182,221,245,.19)':'rgba(36,91,125,.15)'},{offset:1,color:'rgba(182,221,245,0)'}])}}]});
  const observer=new ResizeObserver(()=>chart.resize());observer.observe(el.current);return()=>{observer.disconnect();chart.dispose();};
 },[company,selected,theme,item,hasAnnualData]);
 return item&&hasAnnualData?<div key="chart" className="cr-chart" ref={el} role="img" aria-label={`${company.name}${item.name}趋势，单位亿元`}/>:<div key="empty" className="cr-empty">当前模型没有可比年度数据。<small>保留缺失，等待补充报告。</small></div>;
}
function GraphNode({data}:NodeProps<OperatingNode>){return <div className={`cr-graph-node ${data.root?'is-root':''}`}><Handle type="target" position={Position.Top}/><small>{data.caption}</small><strong>{data.label}</strong><span>{data.detail}</span><Handle type="source" position={data.root?Position.Bottom:Position.Right}/></div>;}
const nodeTypes={research:GraphNode};
function OperatingGraph({company,onSource}:{company:ResearchCompany;onSource:(id:string)=>void}){
 const [selected,setSelected]=useState(groups[0][0]),[focus,setFocus]=useState<CompanyGraphNode|null>(null),[relationFocus,setRelationFocus]=useState<string|null>(null),[relation,setRelation]=useState<CompanyRelation|null>(null),[recordQuery,setRecordQuery]=useState('');
 useEffect(()=>{setSelected(groups[0][0]);setFocus(null);setRelationFocus(null);setRelation(null);setRecordQuery('');},[company]);
 const entities=Object.values(company.graph.nodes).filter(n=>['entity','metric','equation'].includes(n.kind)&&n.groupIds?.includes(selected));
 const kindLabel:Record<string,string>={structural:'结构关联',process:'经营流程',executable:'计算依赖',influence:'影响关系',evidence:'来源证据'};
 const graph=useMemo(()=>{
  if(relationFocus){
   const actual=relationNeighborhood(company.graph,relationFocus);
   const neighbors=actual.nodes.filter(n=>n.id!==relationFocus);
   const nodes:OperatingNode[]=actual.nodes.map(n=>{
    const i=neighbors.findIndex(x=>x.id===n.id),angle=2*Math.PI*i/Math.max(1,neighbors.length),radius=neighbors.length>10?390:270;
    return {id:n.id,type:'research',position:n.id===relationFocus?{x:300,y:300}:{x:300+Math.cos(angle)*radius,y:300+Math.sin(angle)*radius},data:{root:n.id===relationFocus,caption:n.period?.label||({entity:'经营实体',company:'公司',metric:'观测数据',equation:'计算关系',submodel:'经营模块',source:'报告来源'} as Record<string,string>)[n.kind]||'模型记录',label:groups.find(g=>g[0]===n.id)?.[1]||n.label,detail:n.kind==='metric'?`${displayValue(n,n).number} ${unitName(n.unit)}`:n.kind==='source'?'报告来源记录':n.detail==='PARTIAL'?'资料部分覆盖':n.detail||'点击继续追溯关联'}};
   });
   const edges:Edge[]=actual.relations.map(r=>({id:r.id,source:r.source,target:r.target,label:kindLabel[r.kind]||r.label||r.kind,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed,color:'var(--iw-mint)'},style:{stroke:'var(--iw-mint)',strokeWidth:1.5},labelStyle:{fill:'var(--iw-soft)',fontSize:10},labelBgStyle:{fill:'var(--iw-surface)'},labelBgPadding:[6,4]}));
   return {nodes,edges};
  }
  const rootId=Object.values(company.graph.nodes).find(n=>n.kind==='company')?.id||'company';
  const nodes:OperatingNode[]=[{id:rootId,type:'research',position:{x:145,y:0},data:{root:true,caption:'研究对象',label:company.name,detail:'点击经营模块展开'}}];const edges:Edge[]=[];
  groups.forEach(([id,label],i)=>{
   const count=Object.values(company.graph.nodes).filter(n=>['entity','metric','equation'].includes(n.kind)&&n.groupIds?.includes(id)).length;
   nodes.push({id,type:'research',position:{x:(i%2)*290,y:150+Math.floor(i/2)*115},data:{caption:`0${i+1} / 经营模块`,label,detail:count?`${count} 条模型记录`:'尚待补充资料'},selected:id===selected});
   edges.push({id:`membership-${id}`,source:rootId,target:id,type:'smoothstep',style:{stroke:id===selected?'#b6ddf5':'#63758a',strokeWidth:id===selected?1.8:1,opacity:id===selected?1:.45}});
  });return {nodes,edges};
 },[company,selected,relationFocus]);
 return <section className="cr-graph-layout"><div className="iw-panel cr-graph-canvas"><div className="cr-graph-toolbar"><span><i className="cr-dot"/>{relationFocus?'模型实际关系':'经营结构'} · {company.name}</span>{relationFocus?<button className="cr-text-link" onClick={()=>{setRelationFocus(null);setRelation(null);}}>返回经营结构</button>:<small>按模型归属分组 · 可拖动、缩放</small>}</div><ReactFlow key={`${company.key}:${relationFocus||'modules'}`} nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'放大图谱','controls.zoomOut.ariaLabel':'缩小图谱','controls.fitView.ariaLabel':'适应画布'}} fitView fitViewOptions={{padding:.12}} minZoom={.4} maxZoom={1.4} nodesDraggable={false} onNodeClick={(_,n)=>{setRelation(null);if(relationFocus){setFocus(company.graph.nodes[n.id]||null);setRelationFocus(n.id);}else if(n.id.startsWith('sm-')){setSelected(n.id);setFocus(null);setRecordQuery('');}}} onEdgeClick={(_,edge)=>setRelation(company.graph.relations?.[edge.id]||null)}><Background color="rgba(180,200,220,.2)" gap={22} size={1}/><Controls showInteractive={false}/></ReactFlow></div><aside className="iw-panel cr-graph-detail"><span className="iw-kicker">模块详情</span><h3>{groups.find(g=>g[0]===selected)?.[1]}</h3><p>{groups.find(g=>g[0]===selected)?.[2]}</p>{focus&&<div className="cr-entity-inspect"><strong>{focus.label}</strong><small>{focus.knowledge==='INFERRED'?'模型推断 · 待核验':focus.knowledge==='DERIVED'?'模型计算 · 待核验':'模型提取 · 待核验'}</small>{focus.kind==='metric'&&<div className="cr-node-value">{displayValue(focus,focus).number}<small>{unitName(focus.unit)} · {focus.period?.label}</small></div>}{focus.kind==='equation'?<p>计算关系：{focus.detail}。请结合财务记录核对输入数据和期间。</p>:<p>查看来源摘录，核对这条记录与公司的关系。</p>}<button className="cr-button" onClick={()=>{setRelationFocus(focus.id);setRelation(null);}}>展开模型实际关系<ArrowUpRight size={13}/></button>{focus.evidenceIds?.map(id=><button className="cr-text-link" key={id} onClick={()=>onSource(id)}>查看关联证据 <ArrowUpRight size={13}/></button>)}</div>}{relation&&<div className="cr-entity-inspect"><strong>{kindLabel[relation.kind]||relation.kind}</strong><p>{company.graph.nodes[relation.source]?.label} → {company.graph.nodes[relation.target]?.label}</p><small>{relation.label}</small>{relation.evidenceIds?.map(id=><button className="cr-text-link" key={id} onClick={()=>onSource(id)}>查看关系证据<ArrowUpRight size={12}/></button>)}</div>}<input className="cr-entity-filter" aria-label="筛选模块记录" placeholder="筛选模块记录" value={recordQuery} onChange={e=>setRecordQuery(e.target.value)}/><div className="cr-entity-list">{entities.filter(n=>`${n.label} ${n.period?.label||''}`.includes(recordQuery)).map(n=><button key={n.id} className={focus?.id===n.id?'is-selected':''} onClick={()=>{setFocus(n);setRelation(null);if(relationFocus)setRelationFocus(n.id);}}><span>{n.label}{n.kind!=='entity'&&<small>{n.period?.label||n.detail||'模型记录'} · {n.kind==='equation'?'计算关系':'观测数据'}</small>}</span><ChevronRight size={13}/></button>)}</div>{!entities.length&&<div className="cr-empty">此模块尚无模型记录。</div>}{entities.length>0&&!entities.some(n=>`${n.label} ${n.period?.label||''}`.includes(recordQuery))&&<p className="cr-fine">没有匹配的模块记录，试试其他关键词。</p>}<p className="cr-fine">{relationFocus?'此视图仅显示当前模型登记的直接关系；点击记录可继续追溯。':'连线表示模块归属；不代表因果关系或收益预测。'}</p></aside></section>;
}
function Modal({children,title,onClose,className=''}:{children:ReactNode;title:string;onClose:()=>void;className?:string}){
 const closeRef=useRef<HTMLButtonElement>(null);
 useEffect(()=>{
  const prior=document.activeElement instanceof HTMLElement?document.activeElement:null;
  (closeRef.current?.closest('[role=dialog]')?.querySelector<HTMLInputElement>('input')||closeRef.current)?.focus();
  const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();if(e.key==='Tab'){
   const dialog=closeRef.current?.closest('[role=dialog]');
   const els=[...(dialog?.querySelectorAll<HTMLElement>('button,a[href],input,select,textarea')||[])].filter(x=>!x.hasAttribute('disabled'));
   if(e.shiftKey&&document.activeElement===els[0]){e.preventDefault();els.at(-1)?.focus();}
   else if(!e.shiftKey&&document.activeElement===els.at(-1)){e.preventDefault();els[0]?.focus();}
  }};
  window.addEventListener('keydown',key);return()=>{window.removeEventListener('keydown',key);prior?.focus();};
 },[]);

 return createPortal(<div className="cr-app cr-modal-backdrop" onClick={onClose}><section role="dialog" aria-modal="true" aria-label={title} className={`cr-modal ${className}`} onClick={e=>e.stopPropagation()}><header><div><span className="iw-kicker">TOUJING · 公司研究</span><h2>{title}</h2></div><button ref={closeRef} className="iw-icon-button" aria-label="关闭弹窗" onClick={onClose}><X size={20}/></button></header>{children}</section></div>,document.body);
}

export { groups,tabs,metricKeys,shortNames,unitName,excerpt,sourceUrl,allMetrics,metric,valueAt,displayValue,TrendChart,OperatingGraph,Modal };
