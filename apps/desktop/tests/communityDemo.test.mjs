import test from 'node:test';
import assert from 'node:assert/strict';
import { addCommunityReply, addCommunityUpdate, createInitialCommunityState, evidences, loadCommunityState, publishCommunityPost, publishInvestmentPost, storeInvestmentPost, withdrawInvestmentPost } from '../src/data/communityDemo.ts';
import { defaultInvestmentDisclosure, exampleInvestmentInputs, projectInvestmentShare } from '../src/data/investmentSharing.ts';

test('community fixtures are synthetic, company-bound, and useful as a discussion seed', () => {
  const state = createInitialCommunityState();
  const featured = state.posts.find(post => post.id === 'catl-cashflow');
  assert.ok(featured);
  assert.equal(featured.topic, '财报研究');
  assert.ok(featured.evidenceIds.length >= 2);
  assert.ok(featured.replies.length >= 2);
  assert.ok(featured.updates.length >= 2);
  assert.ok(evidences.every(item => item.excerpt.includes('SYNTHETIC') && item.locator.includes('演示')));
  assert.equal(state.posts.find(post => post.id === 'my-research')?.isOwn, true);
});

test('reply and update append immutably while preserving the original thesis', () => {
  const initial = createInitialCommunityState();
  const original = initial.posts.find(post => post.id === 'catl-cashflow');
  const ownPost = initial.posts.find(post => post.id === 'my-research');
  const thesis = original.thesis;
  const ownThesis = ownPost.thesis;
  const replied = addCommunityReply(initial, original.id, { text: '补充一个待核对的问题。', stance: '交流观点', evidenceId: 'catl-e1' });
  const updated = addCommunityUpdate(replied, ownPost.id, { title: '记录边界', body: '继续等待材料验证。', status: '持续观察', evidenceId: 'moutai-e1' });
  assert.equal(initial.posts.find(post => post.id === original.id).replies.length, original.replies.length);
  assert.equal(initial.posts.find(post => post.id === original.id).thesis, thesis);
  assert.equal(updated.posts.find(post => post.id === original.id).thesis, thesis);
  assert.equal(updated.posts.find(post => post.id === original.id).replies.length, original.replies.length + 1);
  assert.equal(updated.posts.find(post => post.id === original.id).updates.length, original.updates.length);
  assert.equal(updated.posts.find(post => post.id === ownPost.id).thesis, ownThesis);
  assert.equal(updated.posts.find(post => post.id === ownPost.id).updates.length, ownPost.updates.length + 1);
  assert.throws(() => addCommunityUpdate(initial, original.id, { title: '不允许修改', body: '他人帖子', status: '持续观察' }), /只能更新自己的讨论/);
});

test('cross-company citations and incomplete drafts are rejected', () => {
  const initial = createInitialCommunityState();
  assert.throws(() => addCommunityReply(initial, 'catl-cashflow', { text: '不匹配的材料', stance: '补充证据', evidenceId: 'moutai-e1' }), /属于该讨论公司/);
  assert.throws(() => addCommunityUpdate(initial, 'my-research', { title: '修订', body: '正文', status: '持续观察', evidenceId: 'tencent-e1' }), /属于该讨论公司/);
  assert.throws(() => publishCommunityPost(initial, { companyId: 'catl', title: '', thesis: '论点', risk: '风险', watch: '观察', evidenceIds: [] }), /请填写公司/);
  assert.throws(() => publishCommunityPost(initial, { companyId: 'catl', title: '标题', thesis: '论点', risk: '风险', watch: '观察', evidenceIds: ['moutai-e1'] }), /属于所选公司/);
});

test('publication tracks the current user and persistence roundtrips safely', () => {
  const initial = createInitialCommunityState();
  const published = publishCommunityPost(initial, { companyId: 'catl', title: '现金流跟踪问题', thesis: '【虚构示例】持续观察现金流与营运资本。', risk: '只有演示材料，结论待验证。', watch: '营运资本变化；后续披露', evidenceIds: ['catl-e1'] });
  const own = published.posts.at(-1);
  assert.equal(own.author, '我');
  assert.equal(own.isOwn, true);
  const restored = loadCommunityState(JSON.stringify(published));
  assert.deepEqual(restored, published);
});

test('corrupt, stale, malformed, or foreign-bound persisted state falls back to fresh fixtures', () => {
  const fresh = createInitialCommunityState();
  assert.deepEqual(loadCommunityState('{bad json'), fresh);
  assert.deepEqual(loadCommunityState(JSON.stringify({ ...fresh, version: 2 })), fresh);
  const foreign = structuredClone(fresh);
  foreign.posts.find(post => post.id === 'catl-cashflow').evidenceIds[0] = 'moutai-e1';
  assert.deepEqual(loadCommunityState(JSON.stringify(foreign)), fresh);
  const malformed = structuredClone(fresh);
  malformed.posts[0].replies[0].evidenceId = 'tencent-e1';
  assert.deepEqual(loadCommunityState(JSON.stringify(malformed)), fresh);
  const malformedOwnership = structuredClone(fresh);
  malformedOwnership.posts.find(post => post.id === 'my-research').isOwn = 'yes';
  assert.deepEqual(loadCommunityState(JSON.stringify(malformedOwnership)), fresh);
});

const investmentNarrative = { title: '我的持仓快照', thesis: '记录所选范围的仓位。', risk: '样本和口径有限。', watch: '观察仓位变化；核对数据日期' };

test('investment post roundtrips beside existing research without persisting raw account fields', () => {
  const input = exampleInvestmentInputs()[1];
  input.account_id = 'PRIVATE_ACCOUNT_9988';
  input.holdings[0].source_ref = 'PRIVATE_ACCOUNT_9988';
  const card = projectInvestmentShare(input, defaultInvestmentDisclosure());
  const research = publishCommunityPost(createInitialCommunityState(), { companyId: 'catl', title: '额外研究', thesis: '待核验假设', risk: '资料有限', watch: '继续观察', evidenceIds: ['catl-e1'] });
  let persisted = JSON.stringify(research);
  const storage = { getItem: () => persisted, setItem: (_key, value) => { persisted = value; } };
  const updated = storeInvestmentPost(storage, card, investmentNarrative);
  const restored = loadCommunityState(persisted);
  assert.equal(restored.version, 1);
  assert.equal(restored.posts.length, research.posts.length + 1);
  assert.ok(restored.posts.some(p => p.title === '额外研究'));
  assert.deepEqual(restored, updated);
  assert.equal(restored.posts.at(-1).companyId, 'portfolio');
  assert.equal(restored.posts.at(-1).topic, '持仓快照');
  assert.deepEqual(restored.posts.at(-1).evidenceIds, []);
  assert.ok(!persisted.includes('PRIVATE_ACCOUNT_9988'));
  assert.ok(!persisted.includes('6000'));
  assert.ok(!persisted.includes('虚构资产 A'));
  card.holdings[0].weight = 0;
  assert.equal(restored.posts.at(-1).investment.holdings[0].weight, 0.6);
});

test('invalid investment cards and fictional evidence binding cannot enter persisted portfolio posts', () => {
  const card = projectInvestmentShare(exampleInvestmentInputs()[0], defaultInvestmentDisclosure());
  assert.throws(() => publishInvestmentPost(createInitialCommunityState(), { ...card, account_id: 'secret' }, investmentNarrative));
  assert.throws(() => publishInvestmentPost(createInitialCommunityState(), { ...card, metrics: { pnl: 1 } }, investmentNarrative));
  const state = publishInvestmentPost(createInitialCommunityState(), card, investmentNarrative);
  const post = state.posts.at(-1);
  assert.throws(() => addCommunityReply(state, post.id, { text: '引用演示材料', stance: '补充证据', evidenceId: 'catl-e1' }));
  assert.throws(() => addCommunityUpdate(state, post.id, { title: '虚构引证', body: '不可绑定', status: '持续观察', evidenceId: 'catl-e1' }));
  const forged = structuredClone(state);
  forged.posts.at(-1).replies.push({ id: 'fake', author: '我', text: '虚构引证', createdAt: '2026-10-23', stance: '补充证据', evidenceId: 'catl-e1' });
  assert.deepEqual(loadCommunityState(JSON.stringify(forged)), createInitialCommunityState());
  const extra = structuredClone(state);
  extra.posts.at(-1).rawAccount = 'PRIVATE_ACCOUNT_9988';
  assert.deepEqual(loadCommunityState(JSON.stringify(extra)), createInitialCommunityState());
});

test('failed storage write throws and withdrawal affects only an owned investment card', () => {
  const card = projectInvestmentShare(exampleInvestmentInputs()[2], defaultInvestmentDisclosure());
  const starting = createInitialCommunityState();
  const storage = { getItem: () => JSON.stringify(starting), setItem: () => { throw new Error('quota exceeded'); } };
  assert.throws(() => storeInvestmentPost(storage, card, investmentNarrative), /quota exceeded/);
  assert.deepEqual(loadCommunityState(storage.getItem()), starting);
  const published = publishInvestmentPost(starting, card, investmentNarrative);
  const id = published.posts.at(-1).id;
  const bookmarked = { ...published, followedPostIds: [...published.followedPostIds, id], savedPostIds: [...published.savedPostIds, id] };
  const withdrawn = withdrawInvestmentPost(bookmarked, id);
  assert.equal(withdrawn.posts.length, starting.posts.length);
  assert.deepEqual(withdrawn.posts, starting.posts);
  assert.ok(!withdrawn.followedPostIds.includes(id));
  assert.ok(!withdrawn.savedPostIds.includes(id));
  assert.throws(() => withdrawInvestmentPost(starting, 'my-research'), /只能撤回自己的投资分享/);
  const anotherAuthor = structuredClone(published);
  anotherAuthor.posts.at(-1).author = '其他人';
  assert.throws(() => withdrawInvestmentPost(anotherAuthor, id), /只能撤回自己的投资分享/);
});
