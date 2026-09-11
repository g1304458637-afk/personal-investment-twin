import assert from 'node:assert/strict';
import test from 'node:test';
import { projectReviewAnswer, answerCopy } from '../src/data/reviewAnswer.ts';

const scope = { subject_id: 'synthetic-own', account_id: 'synthetic-account', episode_id: 'synthetic-episode' };
const local = value => ({ zh: value, en: `English: ${value}` });
const context = { scope, records: [
  { ...scope, ref: 'comparison-1', kind: 'historical_comparison', value: {} },
  { ...scope, ref: 'operation-1', kind: 'decision', value: { decision_event_id: 'decision-1' } },
] };
const answer = { scope, invalidated: false, answer: {
  version: 'question_driven_review_answer_v2', focus: 'operation_impact',
  comparison_summary: [],
  summary: local('最终实现结果 -283.50 CNY'), qualification: local('不是整轮损益拆分'),
  findings: [{ option_id: 'finding-1', kind: 'local_comparison', evidence_ref: 'comparison-1', decision_id: 'decision-1',
    title: local('2 月 20 日操作'), body: local('局部账面结果 -770.50 / -256.00 CNY'), qualification: local('统一使用 3 月 17 日价格') }],
} };

test('answer copies exact backend text and canonical decision navigation, no arithmetic', () => {
  const view = projectReviewAnswer(answer, context, 'zh-CN');
  assert.equal(view.summary, answer.answer.summary.zh);
  assert.equal(view.findings[0].body, answer.answer.findings[0].body.zh);
  assert.equal(view.findings[0].qualification, answer.answer.findings[0].qualification.zh);
  assert.equal(view.findings[0].decisionId, 'decision-1');
});
test('English uses the corresponding backend text and centralized interface copy', () => {
  assert.equal(projectReviewAnswer(answer, context, 'en-US').summary, answer.answer.summary.en);
  assert.equal(answerCopy.en.open, 'View this operation');
  assert.equal(answerCopy.zh.open, '查看这次操作');
});
test('legacy or invalidated answers cannot become a new generated answer', () => {
  assert.equal(projectReviewAnswer({ possible_explanations: [] }, context, 'zh-CN'), null);
  assert.equal(projectReviewAnswer({ ...answer, invalidated: true }, context, 'zh-CN'), null);
  assert.equal(projectReviewAnswer({ ...answer, answer: { ...answer.answer, version: 'future-version' } }, context, 'zh-CN'), null);
});
for (const field of ['subject_id', 'account_id', 'episode_id']) {
  test(`answer cannot borrow another ${field}`, () => {
    assert.equal(projectReviewAnswer({ ...answer, scope: { ...scope, [field]: 'other' } }, context, 'zh-CN'), null);
    const foreign = { ...context, records: [{ ...context.records[0], [field]: 'other' }, context.records[1]] };
    assert.equal(projectReviewAnswer(answer, foreign, 'zh-CN'), null);
  });
}
test('unknown record or unresolvable operation fails instead of generating a link', () => {
  for (const change of [{ evidence_ref: 'unknown' }, { decision_id: 'foreign-operation' }]) {
    const candidate = { ...answer, answer: { ...answer.answer, findings: [{ ...answer.answer.findings[0], ...change }] } };
    assert.equal(projectReviewAnswer(candidate, context, 'zh-CN'), null);
  }
});
test('duplicate finding is rejected, not displayed twice', () => {
  const candidate = { ...answer, answer: { ...answer.answer, findings: [answer.answer.findings[0], answer.answer.findings[0]] } };
  assert.equal(projectReviewAnswer(candidate, context, 'zh-CN'), null);
});

test('all cited evidence remains expandable independently of the highlight count', () => {
  const facts = Array.from({length: 15}, (_, i) => ({...scope, ref: `fact-${i}`, kind: 'decision', title: '记录', value: {}}));
  const history = Array.from({length: 7}, (_, i) => ({...scope, ref: `history-${i}`, kind: 'historical_comparison', value: {}}));
  const candidate = {...answer, facts, historical_comparisons: history, possible_explanations: [
    {supporting_evidence_refs: [facts[0].ref], contradictory_evidence_refs: [facts[1].ref]},
  ]};
  const current = {...context, records: [...context.records, ...facts, ...history]};
  const view = projectReviewAnswer(candidate, current, 'zh-CN');
  assert.equal(view.findings.length, 1);
  assert.equal(view.evidence.length, 23);
  assert.equal(new Set(view.evidence.map(r => r.ref)).size, 23);
  assert.strictEqual(view.evidence.find(r => r.ref === facts[0].ref), facts[0]);
  const forged = {...candidate, facts: [{...facts[0], value: {pnl: 999999}}]};
  assert.deepEqual(projectReviewAnswer(forged, current, 'zh-CN').evidence.find(r => r.ref === facts[0].ref).value, {});
});

test('expanded evidence cannot introduce unread or unauthorized account records', () => {
  assert.equal(projectReviewAnswer({...answer, facts: [{ref: 'not-in-context'}]}, context, 'zh-CN'), null);
  const foreign = {...scope, account_id: 'foreign', ref: 'other', kind: 'episode', value: {}};
  assert.equal(projectReviewAnswer({...answer, facts: [foreign]}, {...context, records: [...context.records, foreign]}, 'zh-CN'), null);
});

test('expanded evidence stays collapsed by default and uses canonical row formatting', async () => {
  const {readFile} = await import('node:fs/promises');
  const source = await readFile(new URL('../src/components/review/ReviewAnswer.tsx', import.meta.url), 'utf8');
  assert.match(source, /<details[^>]+data-review-evidence>/);
  assert.match(source, /view\.evidence\.map/);
  assert.match(source, /reviewRows\(record\)/);
  assert.doesNotMatch(source, /<details[^>]+\bopen(?:[\s=>])/);
});
