import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { adaptStrategyComparison } from '../src/data/strategyComparison.ts';

const artifactUrl = new URL('../src/generated/strategy-comparison-demo.json', import.meta.url);

async function load() {
  return adaptStrategyComparison(JSON.parse(await readFile(artifactUrl, 'utf8')));
}

test('comparison artifact exposes showcase episodes with honest windows', async () => {
  const view = await load();
  assert.equal(view.schemaGuard, undefined);
  assert.ok(view.reports.length >= 3);
  for (const item of view.reports) {
    assert.equal(item.isSynthetic, true);
    assert.match(item.instrument, /^SYN_/);
    assert.ok(item.limitations.some((limitation) => limitation.includes('不构成任何买卖结论')));
    assert.ok(item.limitations.some((limitation) => limitation.includes('不可直接相减')));
    for (const ruleFill of item.ruleFills) {
      assert.ok(['signal_order', 'stop_loss', 'delisting_liquidation'].includes(ruleFill.trigger));
    }
  }
});

test('comparison adapter fails closed on tampering', async () => {
  const good = JSON.parse(await readFile(artifactUrl, 'utf8'));
  const mutations = [
    (r) => { r.schema_version = 'strategy_comparison.v2'; },
    (r) => { r.reports[0].is_synthetic = false; },
    (r) => { r.reports[0].instrument = '600000.SH'; },
    (r) => { r.reports[0].window_user_net_cash_flow = 'n/a'; },
    (r) => { r.reports[0].limitations = []; },
    (r) => { r.reports[0].rule_fills[0].trigger = 'magic'; },
    (r) => { r.portfolio.strategy.final_equity = Number.NaN; },
  ];
  for (const mutate of mutations) {
    const raw = JSON.parse(JSON.stringify(good));
    mutate(raw);
    assert.throws(() => adaptStrategyComparison(raw), `mutation should fail: ${mutate}`);
  }
});

test('comparison source stays static, deterministic, and verdict-free', async () => {
  const dataModule = await readFile(new URL('../src/data/strategyComparison.ts', import.meta.url), 'utf8');
  const demoModule = await readFile(new URL('../src/data/strategyComparisonDemo.ts', import.meta.url), 'utf8');
  assert.match(demoModule, /import source from "@\/generated\/strategy-comparison-demo\.json"/);
  assert.doesNotMatch(dataModule, /realUserApi|fetch\(|invoke\(|import source/);
  const payload = JSON.parse(await readFile(artifactUrl, 'utf8'));
  for (const limitation of payload.limitations) {
    assert.ok(!/应该买入|应该卖出|建议/.test(limitation), 'no verdict language in shipped limitations');
  }
});
