import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");
const { selfComparisonCopy } = await import("../src/workspace/selfComparisonCopy.ts");

test("self comparison copy keeps the current-history and two-period views distinct in both locales", () => {
  for (const copy of Object.values(selfComparisonCopy)) {
    assert.ok(copy.currentHistory.length > 0);
    assert.ok(copy.periodTitle.length > 0);
    assert.notEqual(copy.currentHistory, copy.periodTitle);
    assert.match(copy.periodDetail, /backend|后端/);
  }
});

test("self history uses the registered baseline windows and recorded charts, not a fabricated before-and-after pair", async () => {
  const page = await source("workspace/SelfComparisonWorkspace.tsx");
  assert.match(page, /export function SelfHistoryComparison/);
  assert.match(page, /SelfBaselineSummaryView/);
  assert.match(page, /allWindowsUseSameObservations/);
  assert.match(page, /HistoricalMetricChart/);
  assert.match(page, /comparison\.p25/);
  assert.match(page, /comparison\.median/);
  assert.match(page, /comparison\.p75/);
  assert.match(page, /comparison\.selfHistoricalPercentile/);
  assert.match(page, /--sc-position/);
  assert.match(page, /rolling_3m/, "3-month baseline remains selectable");
  assert.match(page, /rolling_12m/, "12-month baseline remains selectable");
  assert.match(page, /lifetime/, "lifetime baseline remains selectable");
  assert.doesNotMatch(page, /metric\.referenceDate|metric\.pastValue|metric\.currentDate/);
  assert.doesNotMatch(page, /data\.twin|\.comparisons/);
  assert.doesNotMatch(page, /Math\.(?:round|floor|ceil)|reduce\(/);
});

test("the optional two-period view is independently slotted before account-scoped self history", async () => {
  const page = await source("workspace/SelfComparisonWorkspace.tsx");
  assert.match(page, /periodComparison\?: ReactNode/);
  assert.ok(page.indexOf("{periodComparison &&") < page.indexOf('className="sc-history__header"'));
  assert.match(page, /data\.availability === "ready"/);
  assert.match(page, /data\.availability === "real_unavailable"/);
});
