import assert from "node:assert/strict";
import test from "node:test";

const nav = await import("../src/components/charts/dailyTimeNavigation.ts");
const { createDailyTimeNavigationStore } = await import("../src/components/charts/useDailyTimeNavigation.ts");
const axis = await import("../src/components/charts/dailyTimeAxis.ts");

const {
  AXIS_MULTI_MONTH_SPAN_MS,
  AXIS_MULTI_YEAR_SPAN_MS,
  DOM_DELTA_LINE,
  DOM_DELTA_PAGE,
  DOM_DELTA_PIXEL,
  HORIZONTAL_PAN_DOMINANCE_RATIO,
  MIN_VISIBLE_DAILY_OBSERVATIONS,
  MS_PER_DAY,
  TIME_PAN_WINDOWS_PER_PLOT_WIDTH,
  TIME_ZOOM_LN_PER_PIXEL,
  WHEEL_LINE_DELTA_PIXELS,
  WHEEL_PAGE_DELTA_PIXELS,
  anchoredZoomVisibleDomain,
  applyVisibleDailyDomain,
  classifyTimeNavigationIntent,
  dailyPathLineWidth,
  domainsEqual,
  formatAdaptiveDailyAxisTick,
  fullVisibleDomain,
  isIntradayDomain,
  normalizeWheelDeltaPixels,
  panVisibleDailyDomain,
  panVisibleDailyDomainByPixels,
  visibleDomainObservationCount,
  zoomScaleFromWheelDelta,
} = nav;

function weekdayTimes(startIso, count) {
  const start = Date.parse(startIso);
  return Array.from({ length: count }, (_, index) => start + index * MS_PER_DAY);
}

test("delta normalization uses named line/page constants and does not assume pixel mode", () => {
  assert.equal(normalizeWheelDeltaPixels(40, DOM_DELTA_PIXEL), 40);
  assert.equal(normalizeWheelDeltaPixels(2, DOM_DELTA_LINE), 2 * WHEEL_LINE_DELTA_PIXELS);
  assert.equal(normalizeWheelDeltaPixels(1, DOM_DELTA_PAGE), WHEEL_PAGE_DELTA_PIXELS);
  assert.equal(WHEEL_LINE_DELTA_PIXELS, 16);
  assert.equal(WHEEL_PAGE_DELTA_PIXELS, 800);
  assert.equal(TIME_PAN_WINDOWS_PER_PLOT_WIDTH, 1);
  assert.equal(TIME_ZOOM_LN_PER_PIXEL, 0.0035);
});

test("horizontal two-finger wheel pans; ordinary vertical wheel is page-scroll; ctrl/meta is zoom", () => {
  assert.equal(classifyTimeNavigationIntent({
    deltaX: 18, deltaY: 2, deltaMode: 0, ctrlKey: false, metaKey: false, shiftKey: false,
  }), "pan");
  assert.equal(classifyTimeNavigationIntent({
    deltaX: 0, deltaY: 24, deltaMode: 0, ctrlKey: false, metaKey: false, shiftKey: false,
  }), "page-scroll");
  assert.equal(classifyTimeNavigationIntent({
    deltaX: 8, deltaY: 8 / HORIZONTAL_PAN_DOMINANCE_RATIO, deltaMode: 0, ctrlKey: false, metaKey: false, shiftKey: false,
  }), "page-scroll");
  assert.equal(classifyTimeNavigationIntent({
    deltaX: 0, deltaY: -12, deltaMode: 0, ctrlKey: true, metaKey: false, shiftKey: false,
  }), "zoom");
  assert.equal(classifyTimeNavigationIntent({
    deltaX: 30, deltaY: 0, deltaMode: 0, ctrlKey: false, metaKey: true, shiftKey: false,
  }), "zoom");
});

test("pan clamps at both edges without inventing dates or entering intraday", () => {
  const times = weekdayTimes("2021-03-01T00:00:00", 40);
  const full = fullVisibleDomain(times);
  const inner = applyVisibleDailyDomain({
    start: times[10],
    end: times[20],
  }, times);
  const left = panVisibleDailyDomain(inner, -400 * MS_PER_DAY, times);
  assert.equal(left.start, full.start);
  assert.ok(visibleDomainObservationCount(left, times) >= MIN_VISIBLE_DAILY_OBSERVATIONS);
  assert.equal(isIntradayDomain(left), false);
  const right = panVisibleDailyDomain(inner, 400 * MS_PER_DAY, times);
  assert.equal(right.end, full.end);
  assert.equal(isIntradayDomain(right), false);
  const byPixels = panVisibleDailyDomainByPixels(inner, 200, 200, times);
  assert.ok(byPixels.start > inner.start);
});

test("anchored zoom keeps the anchor fraction and refuses intraday", () => {
  const times = weekdayTimes("2022-01-03T00:00:00", 80);
  const domain = { start: times[0], end: times[79] };
  const anchor = times[20];
  const frac = (anchor - domain.start) / (domain.end - domain.start);
  const zoomed = anchoredZoomVisibleDomain(domain, anchor, 4, times);
  const nextFrac = (anchor - zoomed.start) / (zoomed.end - zoomed.start);
  assert.ok(Math.abs(nextFrac - frac) < 1e-10);
  assert.ok(zoomed.end - zoomed.start < domain.end - domain.start);
  assert.equal(isIntradayDomain(zoomed), false);
  assert.ok(visibleDomainObservationCount(zoomed, times) >= MIN_VISIBLE_DAILY_OBSERVATIONS);
  const scale = zoomScaleFromWheelDelta(-20);
  assert.ok(scale > 1);
});

test("minimum five valid daily observations and sparse holiday windows", () => {
  const times = [
    Date.parse("2024-02-01T00:00:00"),
    Date.parse("2024-02-02T00:00:00"),
    Date.parse("2024-02-05T00:00:00"),
    Date.parse("2024-02-06T00:00:00"),
    Date.parse("2024-02-07T00:00:00"),
    Date.parse("2024-02-16T00:00:00"),
  ];
  const lonely = {
    start: Date.parse("2024-02-16T00:00:00"),
    end: Date.parse("2024-02-16T00:00:00") + MS_PER_DAY,
  };
  const clamped = applyVisibleDailyDomain(lonely, times);
  assert.ok(visibleDomainObservationCount(clamped, times) >= 5);
  assert.ok(!times.includes(Date.parse("2024-02-10T00:00:00")));
  const tooSmall = anchoredZoomVisibleDomain(clamped, clamped.end, 50, times);
  assert.ok(visibleDomainObservationCount(tooSmall, times) >= 5);
  assert.equal(isIntradayDomain(tooSmall), false);
});

test("full-domain reset and one logical update per distinct domain", () => {
  const times = weekdayTimes("2021-01-04T00:00:00", 30);
  const store = createDailyTimeNavigationStore("ep-a", times);
  const seen = [];
  store.subscribe((domain) => seen.push(domain));
  const full = store.getDomain();
  assert.equal(store.apply(full, "wheel"), false);
  assert.equal(seen.length, 0);
  const zoomed = anchoredZoomVisibleDomain(full, times[10], 3, times);
  assert.equal(store.apply(zoomed, "wheel"), true);
  assert.equal(store.apply(zoomed, "wheel"), false);
  assert.equal(seen.length, 1);
  assert.equal(store.reset(), true);
  assert.ok(domainsEqual(store.getDomain(), full));
});

test("Price and Quantity share one store domain", () => {
  const times = weekdayTimes("2023-06-01T00:00:00", 20);
  const store = createDailyTimeNavigationStore("shared", times);
  const price = [];
  const quantity = [];
  store.subscribe((domain) => price.push(domain));
  store.subscribe((domain) => quantity.push(domain));
  store.apply(anchoredZoomVisibleDomain(store.getDomain(), times[8], 2, times), "wheel");
  assert.equal(price.length, 1);
  assert.equal(quantity.length, 1);
  assert.deepEqual(price[0], quantity[0]);
});

test("adaptive axis labels follow visible span, never clock time", () => {
  const jan = Date.parse("2023-01-01T00:00:00");
  const may = Date.parse("2024-05-15T00:00:00");
  const years = formatAdaptiveDailyAxisTick(may, "zh-CN", jan, jan + AXIS_MULTI_YEAR_SPAN_MS);
  assert.equal(years, "2024");
  assert.doesNotMatch(years, /\d{1,2}:\d{2}/);
  const monthStart = Date.parse("2024-05-01T00:00:00");
  const monthEnd = monthStart + AXIS_MULTI_MONTH_SPAN_MS;
  assert.equal(formatAdaptiveDailyAxisTick(monthStart, "zh-CN", monthStart, monthEnd), "2024年5月");
  const july = Date.parse("2024-07-01T00:00:00");
  assert.equal(formatAdaptiveDailyAxisTick(july, "zh-CN", monthStart, monthEnd), "7月");
  const week = Date.parse("2024-01-03T00:00:00");
  assert.equal(formatAdaptiveDailyAxisTick(week, "zh-CN", week, week + 14 * MS_PER_DAY), "1月3日");
  assert.doesNotMatch(formatAdaptiveDailyAxisTick(week, "en-US", week, week + 14 * MS_PER_DAY), /\d{1,2}:\d{2}/);
  const formatter = nav.createAdaptiveDailyAxisFormatter("zh-CN", () => ({
    start: jan,
    end: jan + AXIS_MULTI_YEAR_SPAN_MS,
  }));
  assert.equal(formatter(Date.parse("2022-01-01T00:00:00")), "2022");
  assert.equal(formatter(Date.parse("2022-07-01T00:00:00")), "");
  assert.equal(formatter(Date.parse("2022-01-01T00:00:00")), "2022");
  assert.equal(formatter(Date.parse("2023-01-01T00:00:00")), "2023");
});

test("dense All-view line weight does not sample or interpolate", () => {
  assert.ok(dailyPathLineWidth(1113, "primary") < dailyPathLineWidth(80, "primary"));
  assert.equal(axis.MIN_VISIBLE_DAILY_OBSERVATIONS, 5);
});
