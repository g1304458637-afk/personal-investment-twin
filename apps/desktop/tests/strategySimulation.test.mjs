import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { adaptStrategySimulation } from '../src/data/strategySimulation.ts';

const artifactUrl = new URL('../src/generated/strategy-simulation-demo.json', import.meta.url);

async function load() {
  return adaptStrategySimulation(JSON.parse(await readFile(artifactUrl, 'utf8')));
}

test('adapter exposes the deterministic artifact with full trade path intact', async () => {
  const view = await load();
  assert.equal(view.strategy.strategyId, 'toujing_t1_breakout_trend');
  assert.ok(view.equity.length > 700);
  assert.ok(view.fills.length > 300);
  assert.ok(view.orders.length > 300);
  assert.equal(view.summary.fillCount, view.fills.length);
  const daySet = new Set(view.equity.map((point) => point.date));
  assert.equal(daySet.size, view.equity.length);
  assert.ok(view.summary.roundTrips.length > 0);
});

test('adapter fails closed on tampering', async () => {
  const good = JSON.parse(await readFile(artifactUrl, 'utf8'));
  const mutations = [
    (r) => { r.schema_version = 'strategy_simulation.v2'; },
    (r) => { r.data_fingerprint = 'unknown'; },
    (r) => { r.summary.final_equity += 1; },
    (r) => { r.equity[5].equity = Number.NaN; },
    (r) => { r.equity[5].date = '2030-01-01'; },
    (r) => { r.fills[0].fee_detail.commission += 1; },
    (r) => { r.fills[0].side = 'SHORT'; },
    (r) => { r.orders[0].status = 'cancelled_by_user'; },
    // Note: removing one rule_table entry is a spec-completeness concern the
    // transport cannot know (versioned rule counts live in the Python spec
    // tests); the adapter only enforces structure and provenance classes.
  ];
  for (const mutate of mutations) {
    const raw = JSON.parse(JSON.stringify(good));
    mutate(raw);
    assert.throws(() => adaptStrategySimulation(raw), `mutation should fail: ${mutate}`);
  }
});

test('the artifact keeps simulated facts separate from real accounts', async () => {
  const page = await readFile(new URL('../src/pages/StrategySimulationPage.tsx', import.meta.url), 'utf8');
  const dataModule = await readFile(new URL('../src/data/strategySimulation.ts', import.meta.url), 'utf8');
  const demoModule = await readFile(new URL('../src/data/strategySimulationDemo.ts', import.meta.url), 'utf8');
  // Only the vite-only demo wrapper binds the generated artifact.
  assert.match(demoModule, /import source from "@\/generated\/strategy-simulation-demo\.json"/);
  assert.doesNotMatch(dataModule, /generated\/|import source/);
  assert.doesNotMatch(dataModule + page, /realUserApi|fetch\(|invoke\(|runtimeRequest/);
  assert.match(page, /strategySimulationDemo/);
  // The route is registered and reachable from navigation.
  const routes = await readFile(new URL('../src/routing/productRoutes.ts', import.meta.url), 'utf8');
  assert.match(routes, /"strategy_simulation"/);
  assert.match(routes, /path: "\/strategy-simulation"/);
});

test('the shipped artifact reconciles cash and equity day by day', async () => {
  const view = await load();
  let cash = view.summary.initialCash;
  const cashByDay = new Map();
  for (const fill of view.fills) {
    const amount = fill.quantity * fill.price;
    cash += fill.side === 'BUY' ? -amount - fill.fee : amount - fill.fee;
    cashByDay.set(fill.day, cash);
  }
  let lastCash = view.summary.initialCash;
  for (const point of view.equity) {
    lastCash = cashByDay.get(point.date) ?? lastCash;
    assert.ok(Math.abs(point.cash - lastCash) < 1e-6, `cash mismatch on ${point.date}`);
    const holdingsValue = point.equity - point.cash;
    assert.ok(holdingsValue >= -1e-6, `negative holdings value on ${point.date}`);
  }
  assert.ok(Math.abs(view.equity.at(-1).equity - view.summary.finalEquity) < 1e-9);
});

test('max drawdown summary matches the daily series', async () => {
  const view = await load();
  const min = Math.min(...view.equity.map((point) => point.drawdownFromPeak));
  assert.ok(Math.abs(min - view.summary.maxDrawdown) < 1e-9);
});
