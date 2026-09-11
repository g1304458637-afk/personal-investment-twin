import assert from 'node:assert/strict';
import test from 'node:test';
import { factFocusDomain } from '../src/components/charts/factFocusDomain.ts';
test('fact viewport includes five real observations either side without changing inputs', () => {
  const times=Array.from({length:20},(_,i)=>i*10);
  assert.deepEqual(factFocusDomain(70,110,times),{start:20,end:160});
  assert.equal(times.length,20);
});
test('context respects available boundaries, sparse observations and canonical display ordering', () => {
  assert.deepEqual(factFocusDomain(0,190,[190,0,70,70]),{start:0,end:190});
  assert.deepEqual(factFocusDomain(70,110,[0,50,70,110,200]),{start:0,end:200});
  assert.deepEqual(factFocusDomain(70,110,[]),{start:70,end:110});
});
