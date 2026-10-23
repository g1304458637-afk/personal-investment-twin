import assert from 'node:assert/strict';
import test from 'node:test';
import { relationNeighborhood } from '../src/data/companyResearchGraph.ts';
test('relationship drill-down uses only original same-model nodes and directed edges',()=>{
 const graph={nodes:{a:{id:'a'},b:{id:'b'},c:{id:'c'}},relations:{ab:{id:'ab',source:'a',target:'b'},bc:{id:'bc',source:'b',target:'c'},foreign:{id:'foreign',source:'a',target:'foreign-account'}}};
 const view=relationNeighborhood(graph,'a');assert.deepEqual(view.nodes.map(n=>n.id),['a','b']);assert.deepEqual(view.relations,[graph.relations.ab]);
 const next=relationNeighborhood(graph,'b');assert.deepEqual(new Set(next.nodes.map(n=>n.id)),new Set(['a','b','c']));assert.equal(next.relations.length,2);
});
test('a missing record or absent relationship registry never fabricates a graph',()=>{
 assert.deepEqual(relationNeighborhood({nodes:{},relations:{}},'missing'),{nodes:[],relations:[]});
 const node={id:'alone'};assert.deepEqual(relationNeighborhood({nodes:{alone:node}},'alone'),{nodes:[node],relations:[]});
});
