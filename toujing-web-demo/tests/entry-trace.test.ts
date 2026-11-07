import test from 'node:test';
import assert from 'node:assert/strict';
import { makeTrace } from '../src/entry/trace.ts';

test('the wake timeline uses the selected records and their actual dates', () => {
  const trace = makeTrace([
    { date: '2022-06-30', side: 'SELL' },
    { date: '2019-01-01', side: 'BUY' },
    { date: '2024-12-31', side: 'BUY' },
  ]);
  assert.equal(trace.count, 3);
  assert.equal(trace.start, '2019-01-01');
  assert.equal(trace.end, '2024-12-31');
  assert.equal(trace.points[0].position, 0);
  assert.equal(trace.points.at(-1)?.position, 1);
  assert.equal(trace.points[1].sell, true);
  assert.deepEqual(trace.years, ['2019', '2020', '2021', '2022', '2023', '2024']);
});

test('a one-day import remains visible and does not divide by zero', () => {
  const trace = makeTrace([{ date: '2024-02-29', side: 'BUY' }, { date: '2024-02-29', side: 'SELL' }]);
  assert.deepEqual(trace.points.map(point => point.position), [.5, .5]);
  assert.deepEqual(trace.years, ['2024']);
});

test('a large history keeps its full count while limiting animation work', () => {
  const rows = Array.from({ length: 5000 }, (_, i) => ({ date: i < 2500 ? '2020-01-02' : '2025-12-31', side: i % 2 ? 'SELL' : 'BUY' }));
  const trace = makeTrace(rows);
  assert.equal(trace.count, 5000);
  assert.equal(trace.points.length, 144);
  assert.equal(trace.points[0].position, 0);
  assert.equal(trace.points.at(-1)?.position, 1);
});
