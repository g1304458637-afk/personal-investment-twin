import test from 'node:test';
import assert from 'node:assert/strict';
import { buildImportReview } from '../src/entry/importReview.ts';

const row = (date: string, ticker: string, side = 'BUY') => ({ date, ticker, side, quantity: '100', price: '12.5' });
test('uploaded history stays independent of the teaching archive and preserves source rows', () => {
  const rows = [row('2025-03-04', 'MY_TWO', 'SELL'), row('2018-01-02', 'MY_ONE'), row('2025-03-04', 'MY_TWO')];
  const original = structuredClone(rows);
  const review = buildImportReview({ name: '我的成交.csv', rows });
  assert.deepEqual(rows, original);
  assert.equal(review.tradeCount, 3); assert.equal(review.buys, 2); assert.equal(review.sells, 1);
  assert.deepEqual(review.dates, ['2018-01-02', '2025-03-04']);
  assert.deepEqual(review.securities, ['MY_ONE', 'MY_TWO']);
  assert.deepEqual(review.years.map(y => [y.year, y.tradeCount, y.buyCount, y.sellCount, y.index]), [['2018', 1, 1, 0, 0], ['2025', 2, 1, 1, 1]]);
  assert.equal(review.fills[0].execution_id, 'csv-row-3');
  assert.equal(review.fileName, '我的成交.csv');
  assert.equal('pnl' in review, false); assert.equal('maxDrawdown' in review, false); assert.equal('equity' in review, false);
});
test('single-day records and invalid imports have explicit outcomes', () => {
  const review = buildImportReview({ name: '一天.csv', rows: [row('2024-02-29', 'ONE', 'SELL')] });
  assert.deepEqual(review.dates, ['2024-02-29']); assert.equal(review.years[0].index, 0); assert.equal(review.buys, 0);
  assert.throws(() => buildImportReview({ name: '空.csv', rows: [] }), /没有/);
  for (const invalid of [{ ...row('2024-02-30', 'ONE') }, { ...row('2024-02-29', 'ONE'), price: 'Infinity' }, { ...row('2024-02-29', 'ONE'), side: 'UNKNOWN' }]) {
    assert.throws(() => buildImportReview({ name: '异常.csv', rows: [invalid] }), /需要核对/);
  }
});
