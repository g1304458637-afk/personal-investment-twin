import assert from 'node:assert/strict';
import test from 'node:test';
import { reviewCandidatesFromLedger } from '../src/workspace/reviewWorkspaceData.ts';

test('ledger chat catalog uses authoritative episodes and rejects foreign account payloads', () => {
 const value={subject_id:'s',account_id:'a',enabled:true,snapshot:{episodes:[
  {episode_id:'le_old',instrument_id:'stock',symbol:'600000',opened_at:'2025-01-01',closed_at:'2025-01-03',status:'closed',origin:'opening_position'},
  {episode_id:'le_new',instrument_id:'stock',symbol:'600000',opened_at:'2025-01-04',closed_at:null,status:'open',origin:'trade'},
 ]}};
 assert.deepEqual(reviewCandidatesFromLedger(value,'s','a').map(e=>e.episodeId),['le_new','le_old']);
 assert.equal(reviewCandidatesFromLedger(value,'s','a')[0].decisionCount,null);
 assert.deepEqual(reviewCandidatesFromLedger(value,'s','other'),[]);
 assert.deepEqual(reviewCandidatesFromLedger({...value,enabled:false},'s','a'),[]);
});

import { capabilitiesFor, capabilityScopeTarget } from '../src/workspace/agentCapabilityCatalog.ts';
test('ledger discovery describes available records and routes scenario checks to the ledger workspace', () => {
 const services={ledger:true,wholeAccount:true,synthetic:false};
 const catalog=capabilitiesFor(services);
 assert.match(catalog.find(c=>c.id==='compare').prompt.zh,/出入金.*公司行动.*券商对账/);
 assert.doesNotMatch(catalog.find(c=>c.id==='analyze').includes.zh,/收益与回撤/);
 assert.equal(capabilityScopeTarget('scenario',services),'/pretrade');
 assert.equal(capabilityScopeTarget('account',{...services,wholeAccount:false}),'/ask');
 assert.match(capabilitiesFor({...services,wholeAccount:false}).find(c=>c.id==='chart').prompt.zh,/这轮投资/);
});
