import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { adaptStrategySimulation } from '../src/data/strategySimulation.ts';

const artifactUrl = new URL('../src/generated/strategy-simulation-demo.json', import.meta.url);

async function loadRaw() {
  return JSON.parse(await readFile(artifactUrl, 'utf8'));
}

test('r_multiple_stats is optional: artifacts without the field adapt with a null field', async () => {
  const raw = await loadRaw();
  delete raw.summary.r_multiple_stats;
  const view = adaptStrategySimulation(raw);
  assert.equal(view.summary.rMultipleStats, null);
});

test('a present r_multiple_stats block is transported verbatim, never recomputed', async () => {
  const raw = await loadRaw();
  raw.summary.r_multiple_stats = {
    count: 42, avg_r: 0.31, median_r: 0.25, max_r: 3.5, min_r: -1.0,
    skipped_no_stop: 7, definition: 'R = realized PnL / initial risk per unit.',
  };
  const stats = adaptStrategySimulation(raw).summary.rMultipleStats;
  assert.deepEqual(stats, {
    count: 42, avgR: 0.31, medianR: 0.25, maxR: 3.5, minR: -1.0,
    skippedNoStop: 7, definition: 'R = realized PnL / initial risk per unit.',
  });
});

test('a malformed r_multiple_stats block fails closed instead of rendering guesses', async () => {
  const good = await loadRaw();
  const mutations = [
    (r) => { r.summary.r_multiple_stats = { count: -1, skipped_no_stop: 0, definition: 'x' }; },
    (r) => { r.summary.r_multiple_stats.avg_r = Number.NaN; },
    (r) => { r.summary.r_multiple_stats.skipped_no_stop = 'many'; },
    (r) => { delete r.summary.r_multiple_stats.definition; },
  ];
  for (const mutate of mutations) {
    const raw = JSON.parse(JSON.stringify(good));
    raw.summary.r_multiple_stats = raw.summary.r_multiple_stats
      ?? { count: 1, avg_r: 0, median_r: 0, max_r: 0, min_r: 0, skipped_no_stop: 0, definition: 'd' };
    mutate(raw);
    assert.throws(() => adaptStrategySimulation(raw), `mutation should fail: ${mutate}`);
  }
});

test('both simulation pages render the R multiple block with its definition', async () => {
  for (const path of ['../src/pages/StrategySimulationPage.tsx', '../src/pages/MyStrategiesPage.tsx']) {
    const page = await readFile(new URL(path, import.meta.url), 'utf8');
    assert.match(page, /"R multiple"/);
    assert.match(page, /rMultipleStats/);
    assert.match(page, /"R multiple definition"/);
  }
});
