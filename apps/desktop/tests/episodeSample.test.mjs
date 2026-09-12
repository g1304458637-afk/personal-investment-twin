import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { episodeSections, episodeSampleSearch, isEpisodeSample, episodeSampleCopy, isVisibleReviewPattern } from '../src/workspace/episodeSample.ts';
test('review cards only expose consecutive additions and reductions', () => {
  assert.equal(isVisibleReviewPattern('consecutive_scaling_in'), true);
  assert.equal(isVisibleReviewPattern('consecutive_scaling_out'), true);
  for (const code of ['high_quantity_during_daily_price_drawdown', 'long_no_execution_interval', 'add_after_positive_market_move', undefined]) {
    assert.equal(isVisibleReviewPattern(code), false);
  }
});
test('approved review is default and legacy links preserve decision/fact scope', () => {
  const original=new URLSearchParams('decision=owned&fact=recorded');
  assert.equal(isEpisodeSample(original),true);
  assert.equal(isEpisodeSample(new URLSearchParams('layout=review-sample')),true);
  const next=episodeSampleSearch(original,true);
  assert.equal(isEpisodeSample(next),true);
  assert.equal(next.get('decision'),'owned'); assert.equal(next.get('fact'),'recorded');
  assert.equal(original.has('layout'),false);
  const legacy = episodeSampleSearch(next,false);
  assert.equal(isEpisodeSample(legacy),true);
  assert.equal(isEpisodeSample(new URLSearchParams("layout=classic&decision=owned")),true);
  assert.equal(legacy.get("decision"),"owned");
  assert.equal(episodeSampleSearch(legacy,true).toString(),original.toString());
});
test('both locales describe the same four sections and honest model availability', () => {
  assert.deepEqual(episodeSections,['process','lens','executions','analysis','evidence']);
  for (const copy of Object.values(episodeSampleCopy)) for(const section of episodeSections) assert.ok(copy[section]);
  assert.match(episodeSampleCopy['zh-CN'].demoHint,/没有接通/);
  assert.match(episodeSampleCopy['en-US'].demoHint,/not connected/);
});
test('sample retains authoritative values, chart navigation, ownership and source links', async () => {
  const page=await readFile(new URL('../src/pages/PositionEpisodePage.tsx',import.meta.url),'utf8');
  assert.match(page,/timeNavigation\.reset\(\)/);
  assert.match(page,/belongsToExample\(demoEntry, data.exampleAccount\)/);
  assert.match(page,/formatCurrency\(result.pnl\)/);
  assert.match(page,/episode\.evidenceRefs.includes\(reference.evidenceId\)/);
  assert.match(page,/hidden=\{sample && sampleSection !== "process" && !lensMode\}/);
  assert.doesNotMatch(page,/selectLensDecision/);
  assert.match(page,/data.mode === "real_user" && episode.accountId/);
  assert.doesNotMatch(page,/setExampleAccount|calculatePnl|calculateReturn/);
  assert.doesNotMatch(page,/c\.leave|episodeSampleSearch/);
});
