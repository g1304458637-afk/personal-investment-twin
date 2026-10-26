import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultInvestmentDisclosure, exampleInvestmentInputs, holdingsCsvTemplate, parseInvestmentFile, projectInvestmentShare, validatePublishedInvestmentCard } from '../src/data/investmentSharing.ts';

test('default projection is a fresh privacy whitelist across every nested object', () => {
  const input = exampleInvestmentInputs()[1];
  input.id = 'PRIVATE_ACCOUNT_ID';
  input.account = 'PRIVATE_ACCOUNT_ID';
  input.source_ref = 'PRIVATE_ACCOUNT_ID';
  input.holdings[0].account = 'PRIVATE_ACCOUNT_ID';
  input.metrics.account = 'PRIVATE_ACCOUNT_ID';
  const card = projectInvestmentShare(input, defaultInvestmentDisclosure());
  const serialized = JSON.stringify(card);
  assert.equal(validatePublishedInvestmentCard(card), true);
  assert.ok(!serialized.includes('PRIVATE_ACCOUNT_ID'));
  assert.ok(!serialized.includes('6000'));
  assert.ok(!serialized.includes('10000'));
  assert.ok(!serialized.includes('虚构资产 A'));
  assert.deepEqual(card.holdings.map(h => h.name), ['持仓 1', '持仓 2', '持仓 3']);
  assert.deepEqual(card.holdings.map(h => h.weight), [0.6, 0.25, 0.15]);
  input.holdings[0].weight = 0;
  assert.equal(card.holdings[0].weight, 0.6);
});

test('disclosure gates fields independently, including explicit amount opt-in', () => {
  const input = exampleInvestmentInputs()[2];
  const hidden = projectInvestmentShare(input, { names: false, weights: false, performance: false, amounts: false, dates: false });
  assert.deepEqual(hidden.metrics, {});
  assert.equal(hidden.asOf, undefined);
  assert.equal(hidden.start, undefined);
  assert.equal(hidden.end, undefined);
  assert.equal(validatePublishedInvestmentCard(hidden), true);
  const shown = projectInvestmentShare(input, { names: true, weights: true, performance: true, amounts: true, dates: true });
  assert.equal(shown.metrics.pnl, 1230);
  assert.equal(shown.metrics.returnValue, 0.123);
  assert.equal(shown.metrics.maxDrawdown, -0.091);
  assert.equal(shown.asOf, '2026-01-15');
  assert.equal(validatePublishedInvestmentCard(shown), true);
  assert.equal(validatePublishedInvestmentCard({ ...hidden, metrics: { pnl: 0 } }), false);
  assert.equal(validatePublishedInvestmentCard({ ...hidden, asOf: '2026-01-15' }), false);
  assert.equal(validatePublishedInvestmentCard({ ...hidden, holdings: [{ name: '秘密', weight: 0.5 }] }), false);
  assert.equal(validatePublishedInvestmentCard({ ...shown, account_id: 'secret' }), false);
  assert.equal(validatePublishedInvestmentCard({ ...shown, metrics: { ...shown.metrics, source_ref: 'secret' } }), false);
});

test('counts have independent consent and legacy cards without counts remain readable', () => {
  const input = exampleInvestmentInputs()[1];
  const allHidden = projectInvestmentShare(input, { names: false, weights: false, performance: false, amounts: false, dates: false, counts: false });
  assert.deepEqual(allHidden.metrics, {});
  assert.deepEqual(allHidden.holdings.map(h => Object.keys(h)), [['name'], ['name'], ['name']]);
  assert.equal(allHidden.disclosure.counts, false);
  assert.equal(allHidden.asOf, undefined);
  const json = JSON.stringify(allHidden);
  for (const field of ['holdingCount', 'closedCount', 'marketValue', 'equity', 'returnValue', 'maxDrawdown']) assert.ok(!json.includes(`"${field}"`));
  assert.equal(validatePublishedInvestmentCard(allHidden), true);
  assert.equal(validatePublishedInvestmentCard({ ...allHidden, metrics: { holdingCount: 3 } }), false);
  const defaultCard = projectInvestmentShare(input, defaultInvestmentDisclosure());
  assert.equal(defaultCard.disclosure.counts, true);
  assert.equal(defaultCard.metrics.holdingCount, 3);
  const legacy = structuredClone(defaultCard);
  delete legacy.disclosure.counts;
  assert.equal(validatePublishedInvestmentCard(legacy), true);
});

test('invalid scope and numeric/date data fail before a share is produced', () => {
  const base = exampleInvestmentInputs()[1];
  for (const changed of [
    { ...base, asOf: '2026-02-30' }, { ...base, currency: 'EUR' },
    { ...base, metrics: { returnValue: NaN } }, { ...base, metrics: { maxDrawdown: -1.1 } },
    { ...base, holdings: [{ name: 'A', weight: 0.8 }, { name: 'B', weight: 0.3 }] },
    { ...base, holdings: [{ name: 'A', weight: 1.01 }] },
  ]) assert.throws(() => projectInvestmentShare(changed, defaultInvestmentDisclosure()));
  assert.throws(() => projectInvestmentShare(base, { ...defaultInvestmentDisclosure(), amounts: 'yes' }));
});

test('JSON import accepts only a canonical share and resets untrusted source', () => {
  const card = projectInvestmentShare(exampleInvestmentInputs()[1], { names: true, weights: true, amounts: true, performance: true, dates: true });
  const imported = parseInvestmentFile(JSON.stringify(card), 'json');
  assert.equal(imported.source, 'user_reported');
  assert.deepEqual(imported.holdings, card.holdings);
  assert.equal(imported.returnBasis, 'unavailable');
  assert.equal(imported.pnlBasis, 'user_reported');
  assert.deepEqual(imported.definitions, ['个人分享文件导入，数据由提供者填写，未经券商核验；原文件的说明与核验声明未继承。']);
  const period = projectInvestmentShare(exampleInvestmentInputs()[2], defaultInvestmentDisclosure());
  const untrusted = { ...period, source: 'local_account', definitions: ['PRIVATE_ACCOUNT_9988 /tmp/raw-account.csv 已由券商核验'] };
  assert.equal(validatePublishedInvestmentCard(untrusted), true);
  const cleaned = parseInvestmentFile(JSON.stringify(untrusted), 'json');
  assert.equal(cleaned.source, 'user_reported');
  assert.equal(cleaned.returnBasis, 'user_reported');
  assert.equal(cleaned.pnlBasis, 'user_reported');
  assert.ok(!JSON.stringify(projectInvestmentShare(cleaned, defaultInvestmentDisclosure())).includes('PRIVATE_ACCOUNT_9988'));
  assert.ok(!JSON.stringify(projectInvestmentShare(cleaned, defaultInvestmentDisclosure())).includes('/tmp/raw-account.csv'));
  assert.throws(() => parseInvestmentFile(JSON.stringify({ ...card, account_id: 'raw-account' }), 'json'));
  assert.throws(() => parseInvestmentFile(JSON.stringify({ ...card, holdings: [{ ...card.holdings[0], id: 'secret' }] }), 'json'));
  const dateHidden = projectInvestmentShare(exampleInvestmentInputs()[0], { ...defaultInvestmentDisclosure(), dates: false });
  assert.equal(validatePublishedInvestmentCard(dateHidden), true);
  assert.throws(() => parseInvestmentFile(JSON.stringify(dateHidden), 'json'), {
    message: '此文件未包含数据日期，不能作为投资记录导入；请在导出时保留数据日期。',
  });
});

test('CSV import handles BOM, quotes and CRLF with all-or-nothing validation', () => {
  const csv = '\uFEFFname,weight_percent,market_value,currency,as_of\r\n"甲,""测试""",60,600,CNY,2026-01-15\r\n乙,40,,CNY,2026-01-15\r\n';
  const imported = parseInvestmentFile(csv, 'csv');
  assert.equal(imported.source, 'user_reported');
  assert.equal(imported.holdings[0].name, '甲,"测试"');
  assert.equal(imported.holdings[0].weight, 0.6);
  assert.equal(imported.holdings[1].marketValue, undefined);
  assert.ok(imported.definitions[0].includes('未经券商核验'));
  assert.equal(parseInvestmentFile(holdingsCsvTemplate, 'csv').holdings.length, 1);
  for (const bad of [
    'name,weight_percent,currency,as_of\nA,,CNY,2026-01-15',
    'name,weight_percent,currency,as_of\nA,101,CNY,2026-01-15',
    'name,weight_percent,currency,as_of\nA,60,CNY,2026-01-15\nB,50,CNY,2026-01-15',
    'name,weight_percent,currency,as_of\nA,60,CNY,2026-02-30',
    'name,weight_percent,currency,as_of\nA,60,CNY,2026-01-15\nB,30,USD,2026-01-15',
    'name,name,weight_percent,currency,as_of\nA,B,60,CNY,2026-01-15',
    'name,weight_percent,currency,as_of\n"A,60,CNY,2026-01-15',
    'name,weight_percent,currency,as_of\nA,60,CNY',
  ]) assert.throws(() => parseInvestmentFile(bad, 'csv'));
  assert.throws(() => parseInvestmentFile('x'.repeat(512 * 1024 + 1), 'csv'));
});
