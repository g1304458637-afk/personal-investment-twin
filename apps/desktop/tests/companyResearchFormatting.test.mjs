import assert from 'node:assert/strict';
import test from 'node:test';
import { currencyInHundredMillions, displayValue } from '../src/data/companyResearchFormatting.ts';
test('report currency scales preserve the same monetary amount, including ten-thousand yuan', () => {
  for (const [unit, value] of [['CNY','100000000'], ['CNY_thousand','100000'], ['CNY_ten_thousand','10000'], ['CNY_million','100']]) {
    assert.equal(currencyInHundredMillions(value, unit), 1);
    assert.deepEqual(displayValue({unit}, {value}, true), {number:'1.00', unit:'亿元'});
  }
  assert.deepEqual(displayValue({unit:'CNY_ten_thousand'}, {value:'10000'}), {number:'10,000', unit:'万元'});
});
test('missing, nonnumeric and unknown-unit records are never plotted as zero or converted as yuan', () => {
  for (const value of [null, undefined, '', ' ', 'NaN', 'Infinity']) {
    assert.equal(currencyInHundredMillions(value, 'CNY'), null);
    assert.deepEqual(displayValue({unit:'CNY'}, {value}, true), {number:'—',unit:''});
  }
  assert.equal(currencyInHundredMillions('20', 'percent'), null);
  assert.deepEqual(displayValue({unit:'CNY'}, {value:'1',unit:'unmapped'}, true), {number:'1',unit:'unmapped'});
  assert.equal(currencyInHundredMillions('0', 'CNY'), 0);
});
