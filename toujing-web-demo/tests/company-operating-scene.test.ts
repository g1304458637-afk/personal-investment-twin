// Reused R6 topology / qualification / layout regressions.
import assert from 'node:assert/strict';
import test from 'node:test';
import {operatingScene,operatingModuleRecords} from '../src/company/companyOperatingScene.ts';
import {layoutOperatingScene,operatingNodeSize} from '../src/company/companyOperatingLayout.ts';

function graph(){return {projectionKind:'operating_source_candidates',fingerprint:'public-model-1',modelVersion:{id:'v1',twinId:'company'},coverage:{entities:4,metrics:0},sources:{s:{id:'s',title:'正式报告',locator:'公开来源 · 第10页'}},nodes:{
 company:{id:'company',label:'样本公司',kind:'company'},
 home:{id:'home',label:'家居业务',kind:'entity',groupIds:['sm-products','sm-commercial'],evidenceIds:['s'],knowledge:'INFERRED'},
 industrial:{id:'industrial',label:'工业技术',kind:'entity',groupIds:['sm-products','sm-supply'],evidenceIds:['s']},
 compressor:{id:'compressor',label:'压缩机',kind:'entity',groupIds:['sm-products'],evidenceIds:['s']},
 delivery:{id:'delivery',label:'交付服务',kind:'entity',groupIds:['sm-operations'],evidenceIds:['s']},
 },relations:{
 membership:{id:'membership',source:'company',target:'home',kind:'structural',evidenceIds:['s']},
 actual:{id:'actual',source:'industrial',target:'compressor',kind:'structural',label:'结构候选 · 同段原文',evidenceIds:['s']},
 invalid:{id:'invalid',source:'industrial',target:'foreign',kind:'influence'},
 }};}
function freeze(value){if(value&&typeof value==='object'){Object.freeze(value);for(const v of Object.values(value))freeze(v);}return value;}
function noOverlaps(scene,layout){
 assert.equal(Object.keys(layout.positions).length,scene.nodes.length);
 for(let i=0;i<scene.nodes.length;i++)for(let j=i+1;j<scene.nodes.length;j++){
  const a=scene.nodes[i],b=scene.nodes[j],ap=layout.positions[a.id],bp=layout.positions[b.id],as=operatingNodeSize(a),bs=operatingNodeSize(b);
  assert.ok(ap.x+as.width<=bp.x||bp.x+bs.width<=ap.x||ap.y+as.height<=bp.y||bp.y+bs.height<=ap.y,`${a.id} overlaps ${b.id}`);
 }
}

test('overview restores all twelve modules, with actual membership counts and no record pagination',()=>{
 const g=graph(),scene=operatingScene(g,'样本公司',{kind:'overview'}),modules=scene.nodes.filter(n=>n.role==='module');
 assert.equal(modules.length,12);assert.equal(scene.nodes.length,16);
 assert.equal(modules.find(n=>n.groupId==='sm-products').count,3);
 assert.equal(modules.find(n=>n.groupId==='sm-finance').empty,true);
 assert.equal(scene.entityCount,4);assert.equal(scene.relationCount,1);
 assert.ok(scene.edges.every(e=>e.presentation&&!e.relation));
});
test('module opens every original member and preserves only real directed relationships',()=>{
 const g=graph(),scene=operatingScene(g,'样本公司',{kind:'module',id:'sm-products'});
 assert.deepEqual(scene.nodes.map(n=>n.id),['home','industrial','compressor']);
 assert.deepEqual(scene.edges.map(e=>e.relation),[g.relations.actual]);
 assert.equal(scene.edges[0].label,'结构候选 · 同段原文');
 assert.ok(scene.edges.every(e=>!e.presentation));
 assert.equal(scene.nodes[0].record,g.nodes.home);
 assert.deepEqual(operatingModuleRecords(g,'sm-finance'),[]);
});
test('entity view neither invents membership links nor includes dangling/private endpoints',()=>{
 const g=graph(),scene=operatingScene(g,'样本公司',{kind:'relations'});
 assert.equal(scene.nodes.length,4);assert.deepEqual(scene.edges.map(e=>e.id),['actual']);
 const focused=operatingScene(g,'样本公司',{kind:'focus',id:'industrial'});
 assert.deepEqual(focused.nodes.map(n=>n.id),['industrial','compressor']);
 assert.deepEqual(focused.edges.map(e=>e.relation?.evidenceIds),[['s']]);
});
test('graph browsing leaves frozen source evidence, precision and qualification untouched',async()=>{
 const g=freeze(graph()),before=JSON.stringify(g);
 for(const view of [{kind:'overview'},{kind:'module',id:'sm-products'},{kind:'relations'},{kind:'focus',id:'home'}])await layoutOperatingScene(operatingScene(g,'样本公司',view));
 assert.equal(JSON.stringify(g),before);assert.equal(g.nodes.home.knowledge,'INFERRED');assert.equal(g.coverage.metrics,0);
});
test('unclassified and additional original modules remain reachable; invalid navigation returns to overview',()=>{
 const g=graph();g.nodes.unclassified={id:'unclassified',label:'未分组',kind:'unknown'};
 g.nodes.other={id:'other',label:'原模型其他记录',kind:'entity',groupIds:['custom']};
 const scene=operatingScene(g,'样本公司',{kind:'overview'});
 assert.equal(scene.nodes.filter(n=>n.role==='module').length,14);
 assert.deepEqual(operatingModuleRecords(g,'view:unclassified').map(n=>n.id),['unclassified']);
 assert.equal(operatingScene(g,'样本公司',{kind:'module',id:'missing'}).view.kind,'overview');
 assert.equal(operatingScene(g,'样本公司',{kind:'focus',id:'missing'}).view.kind,'overview');
});
test('legacy operating modules and exact registered financial observations remain browsable',()=>{
 const g=graph();delete g.projectionKind;
 g.nodes.metric={id:'metric',kind:'metric',label:'原始观测',groupIds:['sm-accounting'],value:'123456789.012345',unit:'CNY',knowledge:'OBSERVED'};
 const scene=operatingScene(g,'样本公司',{kind:'module',id:'sm-accounting'});
 assert.equal(scene.nodes[0].record.value,'123456789.012345');
 assert.equal(operatingScene(g,'样本公司',{kind:'overview'}).groups.some(g=>g.id==='sm-manufacturing'),true);
});
test('semantic overview places every category without overlap',async()=>{
 const scene=operatingScene(graph(),'样本公司',{kind:'overview'}),layout=await layoutOperatingScene(scene);
 noOverlaps(scene,layout);assert.equal(layout.width,500);assert.ok(layout.height>=420);
});
test('wide demo overview retains all modules and leaves readable space in a short canvas',async()=>{
 const scene=operatingScene(graph(),'样本公司',{kind:'overview'}),layout=await layoutOperatingScene(scene,{wideOverview:true});
 noOverlaps(scene,layout);assert.equal(scene.nodes.filter(n=>n.role==='module').length,12);
 assert.ok(layout.width>900);assert.ok(layout.height<300);
});
test('original ELK engine lays out all entities and disconnected components, reusing the same topology cache',async()=>{
 const scene=operatingScene(graph(),'样本公司',{kind:'relations'});
 const first=layoutOperatingScene(scene),second=layoutOperatingScene(scene);
 assert.equal(first,second);noOverlaps(scene,await first);
 const empty=operatingScene(graph(),'样本公司',{kind:'module',id:'sm-finance'});
 assert.deepEqual((await layoutOperatingScene(empty)).positions,{});
});
test('sixteen source entities use a spacious landscape layout instead of a squeezed vertical stack',async()=>{
 const g=graph();for(let i=0;i<12;i++)g.nodes['extra'+i]={id:'extra'+i,kind:'entity',label:'独立原文实体'+i,groupIds:['sm-products']};
 const scene=operatingScene(g,'样本公司',{kind:'relations'}),layout=await layoutOperatingScene(scene);
 assert.equal(scene.nodes.length,16);assert.equal(scene.edges.length,1);noOverlaps(scene,layout);
 assert.ok(layout.width>layout.height,'use landscape packing for the actual wide workbench');
 for(let i=0;i<scene.nodes.length;i++)for(let j=i+1;j<scene.nodes.length;j++){
  const a=scene.nodes[i],b=scene.nodes[j],ap=layout.positions[a.id],bp=layout.positions[b.id],as=operatingNodeSize(a),bs=operatingNodeSize(b);
  const xGap=Math.max(bp.x-ap.x-as.width,ap.x-bp.x-bs.width),yGap=Math.max(bp.y-ap.y-as.height,ap.y-bp.y-bs.height);
  assert.ok(xGap>=44||yGap>=44,'unrelated source cards retain at least 44 scene units of breathing room');
 }
});
