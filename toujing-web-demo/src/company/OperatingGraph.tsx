import {useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowLeft,ArrowUpRight,Building2,ChevronRight,Focus,Layers3,Maximize2,Minus,Network,Plus,X} from 'lucide-react';
import {Background,Handle,MarkerType,Position,ReactFlow,type Edge,type Node,type NodeProps,type ReactFlowInstance,type Viewport} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {CompanyRelation,ResearchCompany} from './companyResearch';
import {operatingModuleRecords,operatingRelationNames,operatingScene,type OperatingSceneNode,type OperatingView} from './companyOperatingScene';
import {layoutOperatingScene,operatingNodeSize,type OperatingLayout} from './companyOperatingLayout';
import {displayValue,unitName} from './companyResearchFormatting';
import './operating-graph.css';

type GraphData={item:OperatingSceneNode;overview:boolean;activate:(item:OperatingSceneNode)=>void;[key:string]:unknown};
type FlowNode=Node<GraphData,'operating'>;
function OperatingNode({data,selected}:NodeProps<FlowNode>){
 const {item,overview}=data;const region=item.role==='region';
 const target=region?Position.Top:overview&&item.role==='module'?Position.Left:Position.Left;
 const source=item.role==='company'&&overview?Position.Bottom:region?Position.Left:Position.Right;
 return <div className={`og-node og-node--${item.role} og-region-${item.region??'company'}${item.empty?' is-empty':''}${selected?' is-selected':''}`} title={[item.label,item.detail].filter(Boolean).join(' · ')}>
  {!region&&<button type="button" className="og-node-activate nodrag nopan" aria-label={`${item.label}，${item.role==='module'?'展开研究模块':item.role==='company'&&overview?'查看经营总览':'查看详情与原文'}`} onClick={event=>{event.stopPropagation();data.activate(item);}}/>}
  <Handle id="in" type="target" position={target}/>
  {region?<strong>{item.label}</strong>:item.role==='module'?<><Layers3 size={15}/><div><strong>{item.label}</strong><span>{item.detail}</span></div><ChevronRight size={12}/></>:<>
   <small>{item.role==='company'?<Building2 size={12}/>:null}{item.caption}</small><strong>{item.label}</strong><span>{item.record?.kind==='metric'?`${displayValue(item.record,item.record).number} ${unitName(item.record.unit)}`:item.role==='company'?item.detail:`${item.record?.evidenceIds?.length??0} 处原文 · 点击查看`}</span>
  </>}
  <Handle id="out" type="source" position={source}/>
 </div>;
}
const nodeTypes={operating:OperatingNode};
// Keep the full registered relationship in the inspector. Long edge labels
// must not span the gap and collide with either source node.
function shortRelationLabel(label:string){const headline=label.split(' · ')[0];return headline.length>5?headline.slice(0,5)+'…':headline;}
interface Props {company:ResearchCompany;active?:boolean;onSource:(id:string)=>void;onAsk?:(question:string,sourceIds:string[])=>void;initialFocus?:string}
/** The original Twin's overview / module / relationship exploration in the
 * existing 投镜 workspace. View state stays mounted during source navigation. */
export function OperatingGraph({company,active=true,onSource,onAsk,initialFocus}:Props){
 const initialView=():OperatingView=>initialFocus&&company.graph.nodes[initialFocus]?.kind!=='company'?{kind:'focus',id:initialFocus}:{kind:'overview'};
 const [view,setView]=useState<OperatingView>(initialView),[selectedId,setSelectedId]=useState<string|null>(null),[selectedRelation,setSelectedRelation]=useState<CompanyRelation|null>(null);
 const [inspector,setInspector]=useState(false),[expanded,setExpanded]=useState(false),[query,setQuery]=useState(''),[zoom,setZoom]=useState(1);
 const [layout,setLayout]=useState<{key:string;value:OperatingLayout}|null>(null),[layoutError,setLayoutError]=useState('');
 const viewport=useRef<ReactFlowInstance<FlowNode,Edge>|null>(null),restoreViewport=useRef<Viewport|null>(null),expandedButton=useRef<HTMLButtonElement>(null);
 const stageRef=useRef<HTMLDivElement>(null);
 const lastViewport=useRef<{key:string;value:Viewport}|null>(null),resumeViewport=useRef<{key:string;value:Viewport}|null>(null);
 const [canvasSize,setCanvasSize]=useState({width:0,height:0});
 const scene=useMemo(()=>operatingScene(company.graph,company.name,view),[company.graph,company.name,view]);
 const layoutOptions=scene.view.kind==='overview'?{wideOverview:canvasSize.width>=760}:{aspectRatio:Math.max(1,Math.min(5,Math.round(canvasSize.width/Math.max(1,canvasSize.height)*2)/2))};
 const layoutKey=JSON.stringify([scene.key,layoutOptions]);
 useEffect(()=>{if(!active){resumeViewport.current=lastViewport.current;setExpanded(false);}},[active]);
 const selected=selectedId?company.graph.nodes[selectedId]:null;
 useEffect(()=>{setView(initialView());setSelectedId(null);setSelectedRelation(null);setInspector(false);setQuery('');},[company.key,company.graph.fingerprint,initialFocus]);
 useEffect(()=>{let alive=true;setLayoutError('');void layoutOperatingScene(scene,layoutOptions).then(value=>{if(alive)setLayout({key:layoutKey,value});}).catch(()=>{if(alive)setLayoutError('图谱布局未完成，可返回总览重新查看。');});return()=>{alive=false;};},[layoutKey]);
 useEffect(()=>{const element=stageRef.current;if(!element)return;const observer=new ResizeObserver(([entry])=>{const {width,height}=entry.contentRect;if(width>0&&height>0)setCanvasSize(previous=>Math.abs(previous.width-width)>8||Math.abs(previous.height-height)>8?{width,height}:previous);});observer.observe(element);return()=>observer.disconnect();},[expanded]);
 useEffect(()=>{
  if(!expanded)return;
  const before=document.activeElement instanceof HTMLElement?document.activeElement:null;
  const key=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){event.preventDefault();setExpanded(false);}
   if(event.key==='Tab'){
    const controls=[...document.querySelectorAll<HTMLElement>('.og-fullscreen button:not(:disabled),.og-fullscreen select,.og-fullscreen input:not(:disabled),.og-fullscreen [tabindex="0"]')].filter(x=>x.getClientRects().length);
    if(event.shiftKey&&document.activeElement===controls[0]){event.preventDefault();controls.at(-1)?.focus();}
    else if(!event.shiftKey&&document.activeElement===controls.at(-1)){event.preventDefault();controls[0]?.focus();}
   }
  };window.addEventListener('keydown',key);requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.og-fullscreen .og-expand')?.focus());
  return()=>{window.removeEventListener('keydown',key);before?.focus();};
 },[expanded]);
 const nodes=useMemo<FlowNode[]>(()=>scene.nodes.map(item=>({id:item.id,type:'operating',position:layout?.key===layoutKey?layout.value.positions[item.id]??{x:0,y:0}:{x:0,y:0},...operatingNodeSize(item),selected:item.id===selectedId,draggable:false,focusable:false,data:{item,overview:scene.view.kind==='overview',activate:inspect}})),[scene,layout,layoutKey,selectedId]);
 const edges=useMemo<Edge[]>(()=>scene.edges.map(edge=>({id:edge.id,source:edge.source,target:edge.target,sourceHandle:'out',targetHandle:'in',type:'smoothstep',
  label:edge.presentation?'':shortRelationLabel(edge.label),markerEnd:edge.presentation?undefined:{type:MarkerType.ArrowClosed,color:edge.kind==='influence'?'#d4b47d':'var(--iw-mint)'},
  style:{stroke:edge.presentation?'var(--iw-soft)':edge.kind==='influence'?'#d4b47d':'var(--iw-mint)',strokeWidth:edge.presentation?1.1:1.6,strokeDasharray:edge.presentation?'3 5':undefined,opacity:edge.presentation ? .34 : 1},
  labelStyle:{fill:'var(--iw-ink)',fontSize:11},labelBgStyle:{fill:'var(--iw-surface)'},labelBgPadding:[6,4] as [number,number],
 })),[scene]);
 function go(next:OperatingView){setView(next);setSelectedId(null);setSelectedRelation(null);setInspector(false);setQuery('');restoreViewport.current=null;}
 function inspect(item:OperatingSceneNode){
  if(item.role==='module'&&item.groupId){go({kind:'module',id:item.groupId});return;}
  if(item.role==='company'&&scene.view.kind==='overview'){go({kind:'overview'});return;}
  if(item.role==='region')return;
  setSelectedId(item.id);setSelectedRelation(null);setInspector(true);
 }
 function toggleExpanded(){
  if(!expanded)restoreViewport.current=viewport.current?.getViewport()??null;
  setExpanded(value=>!value);
 }
 function source(id:string){setExpanded(false);onSource(id);}
 function initialize(instance:ReactFlowInstance<FlowNode,Edge>){
  viewport.current=instance;
  if(resumeViewport.current?.key===layoutKey){const saved=resumeViewport.current.value;resumeViewport.current=null;requestAnimationFrame(()=>void instance.setViewport(saved));return;}
  if(!expanded&&restoreViewport.current){const saved=restoreViewport.current;restoreViewport.current=null;requestAnimationFrame(()=>void instance.setViewport(saved));}
 }
 const moduleItems=scene.view.kind==='module'?operatingModuleRecords(company.graph,scene.view.id):[];
 const sourceIds=[...new Set(selectedRelation?.evidenceIds??selected?.evidenceIds??[])].filter(id=>company.graph.sources[id]);
 function inspectorBody(){return <aside className="og-inspector" aria-label="图谱节点与原文来源">
  <header><div><small>{selectedRelation?'登记关系':selected?'经营记录':'模块记录'}</small><h3>{selectedRelation?operatingRelationNames[selectedRelation.kind]??selectedRelation.kind:selected?.label??scene.title}</h3></div><button className="og-icon" aria-label="关闭节点详情" onClick={()=>setInspector(false)}><X size={16}/></button></header>
  {selectedRelation?<><p>{company.graph.nodes[selectedRelation.source]?.label} → {company.graph.nodes[selectedRelation.target]?.label}</p>{selectedRelation.label&&<p className="og-record-status">{selectedRelation.label}</p>}</>:selected?<>
   <p className="og-record-status">{selected.knowledge==='INFERRED'?'原文候选 · 待复核':selected.knowledge==='DERIVED'?'已登记计算记录':'原模型记录'}</p>
   {selected.kind==='metric'&&<p>{displayValue(selected,selected).number} {unitName(selected.unit)} · {selected.period?.label}</p>}
   {selected.detail&&<p>{selected.detail}</p>}
   <button className="og-text-button" onClick={()=>go({kind:'focus',id:selected.id})}><Network size={14}/>展开已登记关系<ArrowUpRight size={13}/></button>
  </>:<><p>{scene.groups.find(g=>scene.view.kind==='module'&&g.id===scene.view.id)?.description}</p><input aria-label="筛选当前模块记录" value={query} onChange={e=>setQuery(e.target.value)} placeholder="查找模块内记录"/>{moduleItems.filter(n=>n.label.includes(query)).map(n=><button className="og-record-row" key={n.id} onClick={()=>{setSelectedId(n.id);setSelectedRelation(null);}}>{n.label}<ChevronRight size={13}/></button>)}</>}
  {sourceIds.length>0&&<div className="og-source-list"><h4>原文来源</h4>{sourceIds.map(id=>{const item=company.graph.sources[id];return <article key={id}><button onClick={()=>source(id)}>{item.title}<span>{item.locator?.split(' · ').slice(1).join(' · ')||'查看原文'}<ArrowUpRight size={12}/></span></button><p>{item.note?.split('Source excerpt: ')[1]?.split(' Raw artifact SHA-256:')[0]??item.note}</p></article>;})}</div>}
  {(selected||selectedRelation)&&!sourceIds.length&&<p className="og-record-status">这条模型记录未登记可打开的原文位置。</p>}
  {onAsk&&(selected||selectedRelation)&&<button className="og-text-button" onClick={()=>{setExpanded(false);onAsk(selectedRelation?`核对${company.graph.nodes[selectedRelation.source]?.label}与${company.graph.nodes[selectedRelation.target]?.label}的已登记关系：列出原文依据，区分原文陈述和待核实的推断。`:`结合已定位的原文，研究${selected!.label}在${company.name}经营中的角色，列出依据与待核实的问题。`,sourceIds);}}>带着{selectedRelation?'关系':'节点'}问投镜<ArrowUpRight size={13}/></button>}
 </aside>;}
 function canvas(){return <div className={`og-workspace${expanded?' is-expanded':''}`}>
  <div className="og-toolbar"><div className="og-breadcrumb"><button onClick={()=>go({kind:'overview'})} aria-label="返回公司经营总览"><Building2 size={14}/>{company.name}</button>{scene.view.kind!=='overview'&&<><ChevronRight size={12}/><strong>{scene.title}</strong></>}</div><div className="og-view-actions"><button aria-pressed={scene.view.kind==='overview'} onClick={()=>go({kind:'overview'})}>总览</button><button aria-pressed={scene.view.kind==='relations'} onClick={()=>go({kind:'relations'})}>实体关系</button><button ref={expandedButton} className="og-icon og-expand" aria-label={expanded?'退出图谱全屏':'全屏查看经营图谱'} title={expanded?'退出全屏 · Esc':'全屏查看'} onClick={toggleExpanded}>{expanded?<X size={15}/>:<Maximize2 size={15}/>}</button></div></div>
  {scene.view.kind!=='overview'&&<div className="og-detail-bar"><button className="og-text-button" onClick={()=>go({kind:'overview'})}><ArrowLeft size={13}/>返回经营总览</button><span>{scene.nodes.length} 条记录 · {scene.edges.length} 条登记关系</span>{scene.view.kind==='module'&&<button className="og-text-button" onClick={()=>setInspector(v=>!v)}>记录列表<ChevronRight size={12}/></button>}</div>}
  <div className="og-module-picker"><label>研究模块<select aria-label="选择经营研究模块" value={scene.view.kind==='module'?scene.view.id:''} onChange={e=>e.target.value?go({kind:'module',id:e.target.value}):go({kind:'overview'})}><option value="">全部模块总览</option>{scene.groups.map(group=><option key={group.id} value={group.id}>{group.label} · {operatingModuleRecords(company.graph,group.id).length} 项</option>)}</select></label></div>
  <div ref={stageRef} className="og-stage" aria-label={`${company.name} · ${scene.title}`}>
   {layoutError?<div className="og-empty" role="alert">{layoutError}<button onClick={()=>go({kind:'overview'})}>返回总览</button></div>:!scene.nodes.length?<div className="og-empty"><Layers3 size={26}/><h3>{scene.title}</h3><p>这个研究模块暂无登记记录。</p><button onClick={()=>go({kind:'overview'})}>返回经营总览</button></div>:(!active||!canvasSize.width||layout?.key!==layoutKey)?<div className="og-empty" role="status">正在展开经营结构…</div>:<ReactFlow<FlowNode,Edge> key={`${layoutKey}:${expanded}`} nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={initialize} onMove={(_,value)=>{setZoom(value.zoom);lastViewport.current={key:layoutKey,value};}}
    fitView fitViewOptions={{padding:.075,minZoom:.18,maxZoom:1.1}} minZoom={.18} maxZoom={2.4} nodesDraggable={false} nodesConnectable={false} elementsSelectable onNodeClick={(_,node)=>inspect(node.data.item)}
    onNodeDoubleClick={(_,node)=>{if(node.data.item.role==='record')go({kind:'focus',id:node.id});}} onEdgeClick={(_,edge)=>{const relation=company.graph.relations?.[edge.id];if(relation){setSelectedRelation(relation);setSelectedId(null);setInspector(true);}}}
    ariaLabelConfig={{'controls.zoomIn.ariaLabel':'放大图谱','controls.zoomOut.ariaLabel':'缩小图谱','controls.fitView.ariaLabel':'适应画布'}}><Background color="rgba(170,200,220,.17)" gap={24} size={1}/></ReactFlow>}
   {inspector&&inspectorBody()}
  </div>
  <footer className="og-canvas-footer"><div className="og-zoom-controls"><button className="og-icon" aria-label="缩小经营图谱" onClick={()=>void viewport.current?.zoomOut()}><Minus size={14}/></button><span>{Math.round(zoom*100)}%</span><button className="og-icon" aria-label="放大经营图谱" onClick={()=>void viewport.current?.zoomIn()}><Plus size={14}/></button><button className="og-icon" aria-label="适配完整经营图谱" title="适配完整图谱" onClick={()=>{restoreViewport.current=null;void viewport.current?.fitView({padding:.075,maxZoom:1.1});}}><Focus size={15}/></button></div>
   <div className="og-legend"><span><i className="is-category"/>研究分类</span>{scene.view.kind!=='overview'&&<span><i/>已登记关系</span>}<small>拖动画布 · 滚轮缩放</small></div>
  </footer>
 </div>;}
 return <section className="og-root" aria-label="公司经营图谱">{expanded?createPortal(<div className="og-fullscreen" role="dialog" aria-modal="true" aria-label={`${company.name}经营图谱全屏`}>
  <div className="og-fullscreen-frame"><header><span>公司研究 · 经营结构</span><strong>{company.name}</strong><small>图谱来源与研究资格沿用当前公司范围</small></header>{canvas()}</div>
 </div>,document.body):canvas()}</section>;
}
