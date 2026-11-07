import {test} from 'node:test';
import assert from 'node:assert/strict';
import {operatingCompany, operatingEvidenceScope, type OperatingProjection} from '../src/company/companyProjection.ts';
import {locatedPassage} from '../src/documentSelection.ts';
import type {ResearchScope} from '../src/alignment.ts';

const scope: ResearchScope = {instrument_id:'sz000333', start:'2020-01-01', end:'2025-12-31', knowledge_at:'2026-11-07T00:00:00Z', mode:'hindsight',kind:'range',focus:'public_price',origin:'company',selection_object:{document_id:'old',page:8,start:1,end:10}};
const projection: OperatingProjection = {
  status:'source_grounded_candidates',instrument_id:'sz000333',document_id:'report',document_title:'教学年报',source_year:2025,source_sha256:'version-a',
  graph:{modelVersion:{id:'graph-a',twinId:'sz000333'},nodes:{},sources:{},coverage:{entities:0,metrics:0}},
  evidence:{quote:{id:'quote',text:'经营证据',document_id:'report',document_title:'教学年报',page:249,start:12,end:16,source_version:'version-a'}},
  held_count:0,unknown_count:1,boundary:'候选',model_called_for_artifact:false,
};

test('company node questions preserve issuer, cutoff and original quote coordinates',()=>{
  const next=operatingEvidenceScope(scope,projection,'quote');
  assert.deepEqual(next.selection_object,{document_id:'report',page:249,start:12,end:16});
  assert.equal(next.instrument_id,scope.instrument_id);assert.equal(next.knowledge_at,scope.knowledge_at);
  assert.equal(next.origin,'company');assert.equal(next.kind,'disclosure');assert.equal(scope.selection_object?.document_id,'old');
  assert.equal(operatingEvidenceScope(scope,projection).selection_object,undefined,'whole-graph questions must drop an earlier node selection');
});
test('cross-company, changed source version and invalid quote coordinates cannot enter the assistant',()=>{
  assert.throws(()=>operatingEvidenceScope({...scope,instrument_id:'sh600690'},projection,'quote'),/另一家/);
  assert.throws(()=>operatingCompany(projection,'sh600690','海尔'),/不一致/);
  for(const patch of [{source_version:'changed'},{document_id:'another-report'},{page:0},{start:-1},{end:12},{start:1.5}]){
    const changed={...projection,evidence:{quote:{...projection.evidence.quote,...patch}}};
    assert.throws(()=>operatingEvidenceScope(scope,changed,'quote'),/不完整/);
  }
  assert.throws(()=>operatingEvidenceScope(scope,projection,'missing'),/不完整/);
});
test('source graph adapter preserves qualification and missing graphs remain missing',()=>{
  const result=operatingCompany(projection,scope.instrument_id,'美的');
  assert.equal(result?.graph,projection.graph);assert.deepEqual(result?.analysis.facts,[]);
  assert.equal(result?.analysis.quality.historical_validation_status,'not_financially_admitted');
  assert.equal(operatingCompany({...projection,graph:undefined,status:'missing'},scope.instrument_id,'美的'),null);
});
test('source highlighting follows Python code points and never spills into another document or page',()=>{
  const text='开头𠮷😀经营证据结尾';const location={document_id:'report',page:249,start:4,end:8};
  const result=locatedPassage(text,'report',249,location);
  assert.deepEqual(result,{before:'开头𠮷😀',text:'经营证据',after:'结尾'});
  assert.equal(result!.before+result!.text+result!.after,text);
  assert.equal(locatedPassage(text,'other',249,location),null);
  assert.equal(locatedPassage(text,'report',248,location),null);
  for(const patch of [{start:-1},{end:100},{start:8},{end:4.5}])assert.equal(locatedPassage(text,'report',249,{...location,...patch}),null);
});
