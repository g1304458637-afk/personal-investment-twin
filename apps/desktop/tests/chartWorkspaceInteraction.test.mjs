import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { subscribeChartCursor, publishChartCursor } from "../src/components/charts/chartCursor.ts";
import { forwardChartPageScroll } from "../src/components/charts/chartPageScroll.ts";

test("cursor coordinates are scoped to the same workspace and clean up without filling values", () => {
  const scope = {}, another = {}, price = {}, quantity = {}, received = [], foreign = [];
  const unprice = subscribeChartCursor(scope, (time, origin) => { if (origin !== price) received.push(["price", time]); });
  const unquantity = subscribeChartCursor(scope, (time, origin) => { if (origin !== quantity) received.push(["quantity", time]); });
  const unforeign = subscribeChartCursor(another, (time) => foreign.push(time));
  publishChartCursor(scope, 1736092800000, price);
  publishChartCursor(scope, NaN, price);
  publishChartCursor(scope, null, quantity);
  assert.deepEqual(received, [["quantity", 1736092800000], ["price", null]]);
  assert.deepEqual(foreign, []);
  unprice(); unquantity(); unforeign();
  publishChartCursor(scope, 1, price);
  assert.equal(received.length, 2);
});

function scrollNode(top, max, parentElement = null) {
  return { scrollTop: top, clientHeight: 100, scrollHeight: max + 100, parentElement,
    calls: [], scrollBy(value) { this.calls.push(value); } };
}
function wheel(deltaY, deltaMode = 0, cancelable = true) {
  return { deltaY, deltaMode, cancelable, prevented: false, preventDefault() { this.prevented = true; } };
}
test("vertical wheel scrolls the nearest movable page and normalizes line units", () => {
  const page = scrollNode(50, 600), container = { parentElement: page }, event = wheel(2, 1);
  assert.equal(forwardChartPageScroll(container, event, () => "auto"), true);
  assert.deepEqual(page.calls, [{ top: 32, behavior: "instant" }]);
  assert.equal(event.prevented, true);
});
test("page wheel bubbles past a pane at its boundary and is not cancelled without a scroll target", () => {
  const outer = scrollNode(0, 800), inner = scrollNode(100, 100, outer);
  assert.equal(forwardChartPageScroll({ parentElement: inner }, wheel(60), () => "auto"), true);
  assert.equal(inner.calls.length, 0); assert.equal(outer.calls[0].top, 60);
  const up = wheel(-40);
  assert.equal(forwardChartPageScroll({ parentElement: outer }, up, () => "auto"), false);
  assert.equal(up.prevented, false);
  const uncancelable = wheel(30, 0, false);
  assert.equal(forwardChartPageScroll({ parentElement: outer }, uncancelable, () => "auto"), false);
});
test("shared frame includes labelled range controls, fullscreen focus restoration, and keyboard exit", () => {
  const frame = readFileSync(new URL("../src/components/charts/TimeSeriesFrame.tsx", import.meta.url), "utf8");
  assert.match(frame, /useSyncExternalStore\(navigation.subscribe, navigation.getDomain/);
  assert.match(frame, /createPortal\(workspace, document.body\)/);
  assert.match(frame, /aria-modal/);
  assert.match(frame, /event.key === "Escape"/);
  assert.match(frame, /restoreFocus/);
  assert.match(frame, /Range start date/);
  assert.match(frame, /Range end date/);
});
