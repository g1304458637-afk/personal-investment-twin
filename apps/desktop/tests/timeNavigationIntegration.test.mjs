import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { init, use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, DataZoomComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { timeAtClientX } from "../src/components/charts/chartTimeCoordinate.ts";
import { createDailyTimeNavigationStore } from "../src/components/charts/useDailyTimeNavigation.ts";
import { anchoredZoomVisibleDomain, panVisibleDailyDomainByPixels, createAdaptiveDailyAxisFormatter, MS_PER_DAY } from "../src/components/charts/dailyTimeNavigation.ts";
import { adaptPositionEpisodeDemo } from "../src/data/positionEpisode.ts";

use([LineChart, GridComponent, DataZoomComponent, SVGRenderer]);
const times = Array.from({ length: 80 }, (_, i) => Date.UTC(2025, 0, 1) + i * MS_PER_DAY);
function chart() {
  const value = init(null, null, { renderer: "svg", ssr: true, width: 800, height: 250 });
  value.setOption({ animation: false, grid: { left: 50, right: 50 }, xAxis: { type: "time", min: times[0], max: times.at(-1) },
    yAxis: {}, dataZoom: [{ type: "inside", startValue: times[0], endValue: times.at(-1) }], series: [{ type: "line", data: times.map((t) => [t, 10]) }] });
  return value;
}

for (const pixel of [100, 400, 700]) test(`real ECharts scalar conversion preserves cursor anchor at pixel ${pixel}`, () => {
  const value = chart();
  try {
    const anchor = timeAtClientX(value, { getBoundingClientRect: () => ({ left: 100 }) }, pixel + 100);
    assert.ok(Number.isFinite(anchor));
    assert.ok(Number.isNaN(value.convertFromPixel({ xAxisIndex: 0 }, [250, 0])), "adversarial old tuple form is invalid");
    const next = anchoredZoomVisibleDomain({ start: times[0], end: times.at(-1) }, anchor, 2, times);
    value.dispatchAction({ type: "dataZoom", startValue: next.start, endValue: next.end });
    assert.ok(Math.abs(value.convertToPixel({ xAxisIndex: 0 }, anchor) - pixel) < 0.01);
  } finally { value.dispose(); }
});

test("100 tiny pans do not collapse the selected span; redraw labels are pure", () => {
  let domain = { start: times[10], end: times[30] };
  const span = domain.end - domain.start;
  for (let i = 0; i < 100; i++) {
    domain = panVisibleDailyDomainByPixels(domain, 2, 800, times);
    assert.equal(domain.end - domain.start, span);
  }
  assert.ok(domain.start > times[10]);
  const formatter = createAdaptiveDailyAxisFormatter("zh-CN", () => domain);
  assert.equal(formatter(times[15]), formatter(times[15]));
});

test("one frame dispatches one shared update per chart and preserves intraday execution boundary", () => {
  const pending = new Map(); let id = 0;
  const endpoint = times.at(-1) + 15 * 3600000;
  const store = createDailyTimeNavigationStore("shared", times, [endpoint], {
    request: (fn) => { pending.set(++id, fn); return id; }, cancel: (key) => pending.delete(key),
  });
  assert.equal(store.getDomain().end, endpoint);
  assert.equal(store.observationTimes.length, 80, "endpoint is not a fabricated market observation");
  const charts = [chart(), chart()], counts = [0, 0];
  const cleanup = charts.map((value, index) => store.subscribe((d) => {
    counts[index]++;
    value.dispatchAction({ type: "dataZoom", startValue: d.start, endValue: d.end, escapeConnect: true });
  }));
  try {
    for (let i = 0; i < 50; i++) store.schedule(anchoredZoomVisibleDomain(store.getDomain(), times[20], 1.005, times, store.fullDomain));
    assert.equal(pending.size, 1);
    assert.deepEqual(counts, [0, 0]);
    [...pending.values()][0](); pending.clear();
    assert.deepEqual(counts, [1, 1]);
    assert.deepEqual(charts[0].getOption().dataZoom[0].startValue, charts[1].getOption().dataZoom[0].startValue);
    store.schedule(anchoredZoomVisibleDomain(store.getDomain(), times[20], 1.1, times, store.fullDomain));
    store.cancelPending(); assert.equal(pending.size, 0);
  } finally { cleanup.forEach((fn) => fn()); charts.forEach((value) => value.dispose()); }
});

test("Open quantity/cost endpoint is copied from backend snapshot, not extended from a fill", () => {
  const raw = JSON.parse(readFileSync(new URL("../src/generated/backend-demo-evidence.json", import.meta.url)));
  const view = adaptPositionEpisodeDemo(raw.position_episode_demo);
  for (const entry of view.entries.filter((e) => e.episode.status === "open")) {
    const last = entry.pathAnalysis.positionPath.points.at(-1), state = entry.snapshot.positionState;
    assert.equal(last.boundary, "as_of_valuation");
    assert.equal(last.stateId, state.stateId);
    assert.equal(last.quantity, state.quantity);
    assert.equal(last.averageCost, state.averageCost);
    assert.equal(last.asOf, state.asOf);
    assert.equal(last.decisionId, null);
  }
});
