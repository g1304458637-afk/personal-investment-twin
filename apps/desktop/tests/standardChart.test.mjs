import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { adaptStandardChartDemo } from '../src/data/standardChart.ts';

const payload = JSON.parse(readFileSync(new URL('../src/generated/standard-chart-demo.json', import.meta.url), 'utf8'));
const original = JSON.parse(readFileSync(new URL('../src/generated/backend-demo-evidence.json', import.meta.url), 'utf8'));

test('standard chart is a separate simulated ledger with matched historical marks', () => {
  const view = adaptStandardChartDemo(payload);
  assert.equal(view.market.instrumentId, 'AAPL');
  assert.equal(view.market.currency, 'USD');
  assert.equal(view.market.bars.length, 252);
  assert.equal(view.entry.decisions.length, 6);
  assert.equal(view.entry.episode.subjectId, 'demo-user:standard-chart');
  assert.notEqual(view.entry.episode.episodeId, original.position_episode_demo.default_episode_id);
  for (const point of view.entry.pricePoints) {
    assert.equal(point.price, view.market.bars.find(bar => bar.date === point.observedAt.slice(0, 10)).close);
  }
});

test('chart adapter rejects wrong ownership instrument, currency, or price basis', () => {
  for (const mutate of [
    data => { data.market.replay_instrument_id = 'UNRELATED'; },
    data => { data.market.currency = 'CNY'; },
    data => { data.market.bars.forEach(bar => { bar.close += 0.01; bar.high += 0.01; }); },
    data => { data.data_tier = 'real'; },
  ]) {
    const changed = structuredClone(payload); mutate(changed);
    assert.throws(() => adaptStandardChartDemo(changed));
  }
});

test('market bars reject missing/invalid/duplicated dates and invalid OHLC', () => {
  for (const mutate of [
    data => { data.market.bars[1].date = data.market.bars[0].date; },
    data => { data.market.bars[0].date = '2016-02-30'; },
    data => { data.market.bars[0].high = 1; },
    data => { data.market.bars[0].close = NaN; },
    data => { data.market.bars[0].volume = -1; },
  ]) {
    const changed = structuredClone(payload); mutate(changed);
    assert.throws(() => adaptStandardChartDemo(changed));
  }
  const unavailable = structuredClone(payload);
  unavailable.market.bars[0].volume = null;
  assert.equal(adaptStandardChartDemo(unavailable).market.bars[0].volume, null);
});

test('legacy candlestick fixture is no longer wired into the production showcase catalog', () => {
  const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
  const catalog = read('../src/data/backendEvidence.ts');
  assert.match(catalog, /export const positionEpisodeDemo[^=]*= adaptPositionEpisodeDemo\(\s*backend.position_episode_demo,?\s*\)/);
  assert.doesNotMatch(catalog, /standardChartDemo|standard-chart-demo/);
  assert.match(read('../src/data/showcaseDemo.ts'), /showcaseCharts.*map\(adaptStandardChartDemo\)/s);
  assert.match(read('../src/pages/PositionEpisodePage.tsx'), /belongsToExample\(demoEntry, data.exampleAccount\)/);
  assert.match(read('../src/pages/PositionEpisodePage.tsx'), /showcaseChartForEpisode/);
});
