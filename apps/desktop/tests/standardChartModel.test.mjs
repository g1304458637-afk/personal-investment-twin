import assert from "node:assert/strict";
import test from "node:test";

const model = await import("../src/components/charts/standardChartModel.ts");

const bars = [
  { date: "2024-01-29", open: 10, high: 12, low: 9, close: 11, volume: 10, amount: 100 },
  { date: "2024-01-31", open: 11, high: 15, low: 10, close: 14, volume: null, amount: 150 },
  { date: "2024-02-01", open: 14, high: 16, low: 13, close: 15, volume: 30, amount: 450 },
  { date: "2024-02-05", open: 15, high: 18, low: 14, close: 17, volume: 40, amount: 680 },
];

test("weekly/monthly aggregation preserves actual OHLC and null volume", () => {
  const month = model.aggregateStandardBars(bars, "month");
  assert.deepEqual(month[0], { date: "2024-01-29", open: 10, high: 15, low: 9, close: 14, volume: null, amount: 250 });
  const week = model.aggregateStandardBars(bars, "week");
  assert.deepEqual(week[0], { date: "2024-01-29", open: 10, high: 16, low: 9, close: 15, volume: null, amount: 700 });
  assert.equal(bars[0].close, 11, "source bars remain untouched");
});

test("UTC session dates remain stable around local timezone and holidays stay absent", () => {
  assert.equal(model.utcSessionDate("2024-02-05T00:30:00+08:00"), "2024-02-04");
  assert.deepEqual(model.aggregateStandardBars(bars, "day").map((bar) => bar.date), ["2024-01-29", "2024-01-31", "2024-02-01", "2024-02-05"]);
});

function decision(id, occurredAt, quantity, averageCost) {
  return { decisionId: id, occurredAt, stateAfter: { quantity, averageCost, asOf: occurredAt } };
}

test("same-day operations keep IDs/timestamps and daily state takes the last backend state", () => {
  const entry = { decisions: [
    decision("first", "2024-02-01T14:31:03.124Z", 10, 100),
    decision("second", "2024-02-01T20:01:02.002Z", 20, 110),
  ] };
  const groups = model.groupChartDecisions(entry);
  assert.equal(groups[0].decisions.length, 2);
  assert.equal(groups[0].decisions[0].decisionId, "first");
  assert.equal(groups[0].decisions[1].occurredAt, "2024-02-01T20:01:02.002Z");
  const steps = model.positionStepsForBars(entry, [{ ...bars[2] }, { ...bars[3] }]);
  assert.deepEqual(steps.map(({ quantity, averageCost }) => [quantity, averageCost]), [[20, 110], [20, 110]]);
});

test("week/month candles retain every operation in their period and exact session timestamps", () => {
  const entry = { decisions: [
    decision("wed", "2024-01-31T14:31:03.124Z", 10, 100),
    decision("thu", "2024-02-01T20:01:02.002Z", 20, 110),
  ] };
  const weekly = model.groupChartDecisionsForBars(entry, model.aggregateStandardBars(bars, "week"), "week");
  assert.equal(weekly[0].date, "2024-01-29");
  assert.deepEqual(weekly[0].sessionDates, ["2024-01-31", "2024-02-01"]);
  assert.deepEqual(weekly[0].decisions.map((item) => item.decisionId), ["wed", "thu"]);
  assert.equal(weekly[0].decisions[1].occurredAt, "2024-02-01T20:01:02.002Z");
});

test("cost is hidden once replay says the closing state has no holding", () => {
  const entry = { decisions: [decision("close", "2024-02-01T23:59:59.999Z", 0, 88)] };
  const steps = model.positionStepsForBars(entry, [{ ...bars[2] }]);
  assert.deepEqual(steps[0], { date: "2024-02-01", quantity: 0, averageCost: null, stateAsOf: "2024-02-01T23:59:59.999Z" });
});

test("focus windows include observation context and clamp to the historical range", () => {
  assert.deepEqual(model.clampFocusWindow(bars, { startAt: "2024-01-31T01:00:00Z", endAt: "2024-02-01T23:00:00Z" }, 1), { startIndex: 0, endIndex: 3 });
  assert.deepEqual(model.clampFocusWindow(bars, { startAt: "2010-01-01", endAt: "2010-01-02" }, 9), { startIndex: 0, endIndex: 3 });
});

test("focus context remains source sessions when switching to aggregated candles", () => {
  const weekly = model.aggregateStandardBars(bars, "week");
  assert.deepEqual(model.focusForChartBars(bars, weekly, { startAt: '2024-01-31', endAt: '2024-02-01' }, 1), { startIndex: 0, endIndex: 1 });
  assert.deepEqual(model.focusForChartBars(bars, weekly, { startAt: '2024-01-31', endAt: '2024-02-01' }, 0), { startIndex: 0, endIndex: 0 });
});
