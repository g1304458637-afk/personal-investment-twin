import type {ElkNode} from 'elkjs/lib/elk-api';
import type {OperatingScene,OperatingSceneNode} from './companyOperatingScene.ts';
import {operatingRegions} from './companyOperatingScene.ts';
export interface OperatingLayout {positions:Record<string,{x:number;y:number}>;width:number;height:number}
export function operatingNodeSize(node:OperatingSceneNode){return node.role==='company'?{width:196,height:68}:node.role==='region'?{width:148,height:28}:node.role==='module'?{width:148,height:58}:{width:180,height:82};}
const cache=new Map<string,Promise<OperatingLayout>>();
/** Connectivity is only a layout concern. This never inserts an edge into
 * the scene: disconnected source records stay disconnected. */
function components(scene:OperatingScene){
 const links=new Map(scene.nodes.map(n=>[n.id,new Set<string>()]));
 for(const edge of scene.edges){links.get(edge.source)?.add(edge.target);links.get(edge.target)?.add(edge.source);}
 const seen=new Set<string>(),result:OperatingSceneNode[][]=[];
 for(const node of scene.nodes){if(seen.has(node.id))continue;const queue=[node.id],ids=new Set<string>();seen.add(node.id);
  for(let i=0;i<queue.length;i++){const id=queue[i];ids.add(id);for(const other of links.get(id)??[]){if(!seen.has(other)){seen.add(other);queue.push(other);}}}
  result.push(scene.nodes.filter(n=>ids.has(n.id)));
 }return result;
}
/** Adapted from Company Operating Twin's layout.ts / exploreLayout.ts:
 * retain semantic regions for overview, ELK for actual model relationships. */
export function layoutOperatingScene(scene:OperatingScene,options:{wideOverview?:boolean;aspectRatio?:number}={}):Promise<OperatingLayout>{
 const key=JSON.stringify([scene.key,scene.edges.map(e=>[e.id,e.source,e.target]),options]);const prior=cache.get(key);if(prior)return prior;
 const pending=(async()=>{
  if(scene.view.kind==='overview'){
   // The R6 source uses a narrow center pane. The web demo has a wide canvas:
   // retain the same three semantic regions and distribute each region's
   // modules in two columns, so the default view need not shrink its labels.
   if(options.wideOverview){
    const positions:OperatingLayout['positions']={};const root=scene.nodes.find(n=>n.role==='company');
    const width=1016;if(root)positions[root.id]={x:(width-196)/2,y:0};let bottom=136;
    operatingRegions.forEach((region,column)=>{
     const x=column*344;positions['view:region:'+region.id]={x:x+90,y:90};
     scene.nodes.filter(n=>n.role==='module'&&n.region===region.id).forEach((node,index)=>{
      positions[node.id]={x:x+(index%2)*180,y:136+Math.floor(index/2)*76};
      bottom=Math.max(bottom,positions[node.id].y+58);
     });
    });return {positions,width,height:bottom};
   }
   const positions:OperatingLayout['positions']={};const root=scene.nodes.find(n=>n.role==='company');if(root)positions[root.id]={x:152,y:0};let bottom=140;
   operatingRegions.forEach((region,column)=>{
    const x=column*176;positions['view:region:'+region.id]={x,y:94};
    scene.nodes.filter(n=>n.role==='module'&&n.region===region.id).forEach((n,row)=>{positions[n.id]={x,y:140+row*76};bottom=Math.max(bottom,140+row*76+58);});
   });return {positions,width:500,height:bottom};
  }
  if(!scene.nodes.length)return {positions:{},width:400,height:200};
  const {default:ELK}=await import('elkjs/lib/elk.bundled.js');const elk=new ELK();
  // ELK's default disconnected-component packing made the 16-record source
  // graph a tall column. Layout the actual connected parts with ELK, then
  // pack those parts into a landscape scene with explicit breathing room.
  const parts=[];
  for(const [index,items] of components(scene).entries()){
   if(items.length===1){const item=items[0];parts.push({width:operatingNodeSize(item).width,height:operatingNodeSize(item).height,positions:{[item.id]:{x:0,y:0}}});continue;}
   const ids=new Set(items.map(n=>n.id));
   const result=await elk.layout<ElkNode>({id:'operating-part-'+index,layoutOptions:{
    'elk.algorithm':'layered','elk.direction':'RIGHT','elk.spacing.nodeNode':'44',
    'elk.layered.spacing.nodeNodeBetweenLayers':'88','elk.padding':'[top=0,left=0,bottom=0,right=0]',
   },children:items.map(n=>({id:n.id,...operatingNodeSize(n)})),edges:scene.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({id:e.id,sources:[e.source],targets:[e.target]}))});
   parts.push({positions:Object.fromEntries((result.children??[]).map(n=>[n.id,{x:n.x??0,y:n.y??0}])),width:result.width??180,height:result.height??82});
  }
  const gap=44,pad=20,area=parts.reduce((sum,p)=>sum+(p.width+gap)*(p.height+gap),0);
  const rowWidth=Math.max(...parts.map(p=>p.width),Math.sqrt(area*(options.aspectRatio??1.9)));
  const positions:OperatingLayout['positions']={};let x=pad,y=pad,rowHeight=0,right=pad;
  for(const part of parts.sort((a,b)=>b.height-a.height||b.width-a.width)){
   if(x>pad&&x+part.width>rowWidth+pad){x=pad;y+=rowHeight+gap;rowHeight=0;}
   for(const [id,point] of Object.entries(part.positions))positions[id]={x:x+point.x,y:y+point.y};
   right=Math.max(right,x+part.width);rowHeight=Math.max(rowHeight,part.height);x+=part.width+gap;
  }
  return {positions,width:right+pad,height:y+rowHeight+pad};
 })();cache.set(key,pending);if(cache.size>60)cache.delete(cache.keys().next().value!);pending.catch(()=>cache.delete(key));return pending;
}
