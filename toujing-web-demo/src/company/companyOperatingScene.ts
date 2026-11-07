import type {CompanyGraph,CompanyGraphNode,CompanyRelation} from './companyResearch.ts';
import {relationNeighborhood} from './companyResearchGraph.ts';

export type OperatingRegion='resources'|'operations'|'commercial';
export interface OperatingGroup {id:string;label:string;description:string;region:OperatingRegion}
export const operatingGroups:OperatingGroup[]=[
 {id:'sm-products',label:'产品与服务',description:'向客户提供什么',region:'operations'},
 {id:'sm-supply',label:'供应链与存货',description:'采购和存货如何组织',region:'operations'},
 {id:'sm-commercial',label:'客户与市场',description:'服务哪些客户与市场',region:'commercial'},
 {id:'sm-operations',label:'运营与交付',description:'如何运营和交付',region:'operations'},
 {id:'sm-people',label:'人员与组织',description:'如何分工与组织',region:'resources'},
 {id:'sm-assets',label:'资产与产能',description:'依赖哪些经营资产',region:'resources'},
 {id:'sm-marketing',label:'营销与销售',description:'如何触达和服务客户',region:'commercial'},
 {id:'sm-rd',label:'研发与技术',description:'如何研发和创新',region:'resources'},
 {id:'sm-finance',label:'融资与资本',description:'资本来源与安排',region:'resources'},
 {id:'sm-compliance',label:'税务与合规',description:'税务与合规背景',region:'commercial'},
 {id:'sm-external',label:'外部环境',description:'行业与外部环境',region:'commercial'},
 {id:'sm-accounting',label:'财务与会计',description:'报告中的财务与会计背景',region:'operations'},
];
export const legacyOperatingGroups=[
 ['sm-products','产品与服务','公司向市场提供什么'],['sm-manufacturing','生产与交付','产品如何生产和交付'],
 ['sm-assets','资产与产能','经营依赖哪些资产'],['sm-rd','研发与创新','长期竞争力从哪里来'],
 ['sm-commercial','客户与市场','收入来自哪些市场'],['sm-accounting','财务与现金流','经营如何反映到财务'],['sm-external','外部环境','政策和行业有哪些影响'],
];
export const operatingRegions:{id:OperatingRegion;label:string}[]=[
 {id:'resources',label:'资源与能力'},{id:'operations',label:'产品与运营'},{id:'commercial',label:'客户与环境'},
];
export type OperatingView={kind:'overview'}|{kind:'module';id:string}|{kind:'relations'}|{kind:'focus';id:string};
export interface OperatingSceneNode {id:string;role:'company'|'region'|'module'|'record';label:string;caption:string;detail:string;region?:OperatingRegion;groupId?:string;record?:CompanyGraphNode;count?:number;empty?:boolean}
export interface OperatingSceneEdge {id:string;source:string;target:string;kind:string;label:string;presentation:boolean;relation?:CompanyRelation}
export interface OperatingScene {key:string;title:string;view:OperatingView;nodes:OperatingSceneNode[];edges:OperatingSceneEdge[];groups:OperatingGroup[];recordCount:number;relationCount:number;entityCount:number}
const recordKinds=new Set(['entity','metric','equation','unknown']);
const captions:Record<string,string>={company:'公司主体',entity:'经营实体',metric:'观测数据',equation:'计算关系',source:'报告原文',unknown:'待核查记录',submodel:'研究模块'};
export const operatingRelationNames:Record<string,string>={structural:'结构关联',process:'经营流程',executable:'计算依赖',influence:'影响关系',evidence:'来源证据'};

export function operatingCatalog(graph:CompanyGraph):OperatingGroup[]{
 const groups=graph.projectionKind==='operating_source_candidates'?operatingGroups:legacyOperatingGroups.map(([id,label,description])=>({id,label,description,region:(id==='sm-assets'||id==='sm-rd'?'resources':id==='sm-commercial'||id==='sm-external'?'commercial':'operations') as OperatingRegion}));
 const known=new Set(groups.map(g=>g.id));const extras:OperatingGroup[]=[];
 for(const node of Object.values(graph.nodes))for(const id of node.groupIds??[]){
  if(!known.has(id)){known.add(id);extras.push({id,label:graph.nodes[id]?.label??id,description:'原模型登记分组',region:'operations'});}
 }
 if(Object.values(graph.nodes).some(n=>recordKinds.has(n.kind)&&!(n.groupIds?.length)))extras.push({id:'view:unclassified',label:'未分类记录',description:'原模型未登记模块归属',region:'operations'});
 return [...groups,...extras];
}
export function operatingModuleRecords(graph:CompanyGraph,id:string){
 return Object.values(graph.nodes).filter(n=>recordKinds.has(n.kind)&&(id==='view:unclassified'?!(n.groupIds?.length):n.groupIds?.includes(id)));
}
function recordNode(node:CompanyGraphNode):OperatingSceneNode{return {id:node.id,role:node.kind==='company'?'company':'record',label:node.label,caption:captions[node.kind]??'模型记录',detail:node.detail??'',record:node};}
function existingEdges(graph:CompanyGraph,ids:Set<string>):OperatingSceneEdge[]{
 return Object.values(graph.relations??{}).filter(r=>ids.has(r.source)&&ids.has(r.target)&&graph.nodes[r.source]&&graph.nodes[r.target])
  .map(r=>({id:r.id,source:r.source,target:r.target,kind:r.kind,label:r.id.startsWith('membership:')?'原文归属':r.label??operatingRelationNames[r.kind]??r.kind,presentation:false,relation:r}));
}
/** Restore the original overview / module / relation exploration. Presentation
 * categories never enter the source graph, its evidence or financial facts. */
export function operatingScene(graph:CompanyGraph,companyName:string,requested:OperatingView):OperatingScene{
 const groups=operatingCatalog(graph),records=Object.values(graph.nodes).filter(n=>recordKinds.has(n.kind));
 const root=Object.values(graph.nodes).find(n=>n.kind==='company');
 const recordIds=new Set(records.map(n=>n.id));const allRelations=existingEdges(graph,recordIds);
 const missingModule=requested.kind==='module'&&!groups.some(g=>g.id===requested.id);
 const missingFocus=requested.kind==='focus'&&!graph.nodes[requested.id];
 const view:OperatingView=missingModule||missingFocus?{kind:'overview'}:requested;
 let nodes:OperatingSceneNode[]=[],edges:OperatingSceneEdge[]=[],title='经营总览';
 if(view.kind==='overview'){
  const rootId=root?.id??'view:company';
  nodes.push({id:rootId,role:'company',label:companyName,caption:'公司主体',detail:`${records.filter(n=>n.kind==='entity').length} 项经营实体 · ${groups.length} 个研究模块`,record:root});
  for(const region of operatingRegions){
   const id='view:region:'+region.id;nodes.push({id,role:'region',label:region.label,caption:'研究视角',detail:'',region:region.id});
   edges.push({id:'view:category:'+id,source:rootId,target:id,kind:'category',label:'',presentation:true});
  }
  for(const group of groups){
   const items=operatingModuleRecords(graph,group.id),id='view:module:'+group.id;
   nodes.push({id,role:'module',groupId:group.id,region:group.region,label:group.label,caption:'研究模块',detail:items.length?`${items.length} 项原文记录`:'暂无登记记录',count:items.length,empty:!items.length});
   edges.push({id:'view:category:'+id,source:'view:region:'+group.region,target:id,kind:'category',label:'',presentation:true});
  }
 }else if(view.kind==='module'){
  const group=groups.find(g=>g.id===view.id)!;title=group.label;nodes=operatingModuleRecords(graph,view.id).map(recordNode);edges=existingEdges(graph,new Set(nodes.map(n=>n.id)));
 }else if(view.kind==='focus'){
  const actual=relationNeighborhood(graph,view.id);title=graph.nodes[view.id].label;nodes=actual.nodes.map(recordNode);edges=existingEdges(graph,new Set(nodes.map(n=>n.id)));
 }else{title='经营实体与关系';nodes=records.map(recordNode);edges=allRelations;}
 return {key:JSON.stringify([graph.fingerprint??graph.modelVersion.id,view,nodes.map(n=>n.id)]),title,view,nodes,edges,groups,recordCount:records.length,entityCount:records.filter(n=>n.kind==='entity').length,relationCount:allRelations.length};
}
