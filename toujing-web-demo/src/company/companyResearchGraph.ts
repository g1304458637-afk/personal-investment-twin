import type {CompanyGraph} from './companyResearch.ts';
/** Only return registered edges whose two endpoints exist in this model. */
export function relationNeighborhood(graph:CompanyGraph,focusId:string){
 if(!graph.nodes[focusId])return {nodes:[],relations:[]};
 const relations=Object.values(graph.relations||{}).filter(r=>(r.source===focusId||r.target===focusId)&&graph.nodes[r.source]&&graph.nodes[r.target]);
 const ids=new Set([focusId,...relations.flatMap(r=>[r.source,r.target])]);
 return {nodes:[...ids].map(id=>graph.nodes[id]),relations};
}
