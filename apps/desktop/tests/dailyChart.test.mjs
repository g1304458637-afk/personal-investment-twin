import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const axis = await import("../src/components/charts/dailyTimeAxis.ts");

const {
  MS_PER_DAY,
  MIN_VISIBLE_DAILY_OBSERVATIONS,
  calendarDayTime,
  clampVisibleDailyWindow,
  countDailyObservationsInRange,
  dailyDataZoom,
  dailyTimeDomain,
  formatDailyAxisTick,
  minDailyZoomSpanMs,
  uniqueDailyObservationTimes,
} = axis;

function isoDays(values) {
  return uniqueDailyObservationTimes(values);
}

test("minimum daily zoom is five observations, not a hardcoded 14-day product rule", () => {
  assert.equal(MIN_VISIBLE_DAILY_OBSERVATIONS, 5);
  assert.equal("MIN_DAILY_ZOOM_SPAN_MS" in axis, false);
  const dense = isoDays([
    "2024-01-02T00:00:00",
    "2024-01-03T00:00:00",
    "2024-01-04T00:00:00",
    "2024-01-05T00:00:00",
    "2024-01-08T00:00:00",
    "2024-01-09T00:00:00",
  ]);
  const span = minDailyZoomSpanMs(dense);
  assert.equal(span, 6 * MS_PER_DAY);
  const zoom = dailyDataZoom(8, span);
  assert.equal(zoom[0].minValueSpan, span);
  assert.equal(zoom[1].minValueSpan, span);
  assert.equal(zoom[0].start, 0);
  assert.equal(zoom[0].end, 100);
  assert.ok(zoom[0].moveOnMouseMove);
  assert.equal(zoom[0].zoomOnMouseWheel, false);
  assert.equal(zoom[0].moveOnMouseWheel, false);
  assert.equal(zoom[0].zoomLock, true);
});

test("sparse holiday windows expand until five daily observations exist", () => {
  const times = isoDays([
    "2024-02-01T00:00:00",
    "2024-02-02T00:00:00",
    "2024-02-05T00:00:00",
    "2024-02-06T00:00:00",
    "2024-02-07T00:00:00",
    "2024-02-16T00:00:00",
  ]);
  const lonely = Date.parse("2024-02-16T00:00:00");
  const clamped = clampVisibleDailyWindow(lonely, lonely + MS_PER_DAY, times);
  assert.ok(countDailyObservationsInRange(times, clamped.start, clamped.end) >= 5);
  assert.notEqual(clamped.start, clamped.end);
});

test("cannot enter a sub-day domain and does not invent missing dates", () => {
  const times = isoDays(["2024-01-02T00:00:00", "2024-01-03T00:00:00", "2024-01-04T00:00:00", "2024-01-05T00:00:00", "2024-01-08T00:00:00"]);
  const start = Date.parse("2024-01-03T00:00:00");
  const clamped = clampVisibleDailyWindow(start, start + 3 * 60 * 60 * 1000, times);
  assert.ok(clamped.end - clamped.start >= MS_PER_DAY);
  assert.ok(countDailyObservationsInRange(times, clamped.start, clamped.end) >= 5);
  const domain = dailyTimeDomain(["2024-01-02", "2024-01-08"]);
  assert.deepEqual(domain, { min: "2024-01-02", max: "2024-01-08" });
});

test("daily axis ticks collapse sub-day instants to one calendar date and never emit clock time", () => {
  const midnight = Date.parse("2025-01-04T00:00:00");
  const later = midnight + 7 * 60 * 60 * 1000;
  const next = Date.parse("2025-01-05T00:00:00");
  const first = formatDailyAxisTick(midnight, "zh-CN");
  assert.equal(first, formatDailyAxisTick(later, "zh-CN"));
  assert.notEqual(first, formatDailyAxisTick(next, "zh-CN"));
  assert.equal(calendarDayTime(midnight), calendarDayTime(later));
  assert.doesNotMatch(first, /\d{1,2}:\d{2}/);
});

test("Episode charts lock observation-based zoom, persist across phase selection, and reset on Episode change", async () => {
  const axisSource = await readFile(new URL("../src/components/charts/dailyTimeAxis.ts", import.meta.url), "utf8");
  const chart = await readFile(new URL("../src/components/charts/EChart.tsx", import.meta.url), "utf8");
  const price = await readFile(new URL("../src/components/charts/PositionEpisodeTimeline.tsx", import.meta.url), "utf8");
  const quantity = await readFile(new URL("../src/components/charts/PositionQuantityTimeline.tsx", import.meta.url), "utf8");
  assert.match(axisSource, /MIN_VISIBLE_DAILY_OBSERVATIONS = 5/);
  assert.doesNotMatch(axisSource, /14 \* MS_PER_DAY/);
  assert.match(chart, /resetKey/);
  assert.match(chart, /observationTimes/);
  assert.match(chart, /clampVisibleDailyWindow/);
  assert.match(chart, /classifyTimeNavigationIntent/);
  assert.match(chart, /passive: false, capture: true/);
  assert.match(chart, /if \(intent === "page-scroll"\) return/);
  assert.match(chart, /timeNavigationRef.current\?\.reset\(\)/);
  assert.match(price, /resetKey=\{entry.episode.episodeId\}/);
  assert.match(quantity, /resetKey=\{entry.episode.episodeId\}/);
  assert.match(price, /createAdaptiveDailyAxisFormatter/);
  assert.match(quantity, /createAdaptiveDailyAxisFormatter/);
  assert.match(price, /minInterval: MS_PER_DAY/);
  assert.match(quantity, /minInterval: MS_PER_DAY/);
  assert.match(price, /dailyTimeDomain/);
  assert.match(quantity, /dailyTimeDomain/);
  assert.match(price, /timeNavigation/);
  assert.match(quantity, /timeNavigation/);
  assert.doesNotMatch(quantity, /hour:\s*"2-digit"/);
  assert.doesNotMatch(price, /sampling:/);
  assert.doesNotMatch(quantity, /sampling:/);
});
