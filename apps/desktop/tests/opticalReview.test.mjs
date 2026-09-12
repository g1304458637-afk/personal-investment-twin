import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import postcss from "postcss";
import { isOpticalReview, opticalReviewSearch } from "../src/experiments/optical-review/experiment.ts";

const source = async path => readFile(new URL(path, import.meta.url), "utf8");

test("optical experiment is explicitly opt-in, not a new default or stored preference", () => {
  for (const query of ["", "visual=true", "visual=optical", "visual=other", "theme=optical-v1"]) {
    assert.equal(isOpticalReview(new URLSearchParams(query)), false);
  }
  assert.equal(isOpticalReview(new URLSearchParams("visual=optical-v1")), true);
});

test("switching the experiment preserves unrelated route parameters and never mutates the input", () => {
  const original = new URLSearchParams("source=evidence&decision=A&decision=B");
  const next = opticalReviewSearch(original, true);
  assert.equal(original.toString(), "source=evidence&decision=A&decision=B");
  assert.deepEqual(next.getAll("decision"), ["A", "B"]);
  assert.equal(isOpticalReview(next), true);
  assert.equal(opticalReviewSearch(next, false).toString(), original.toString());
});

test("the single Episode page retains existing chart state and decision Drawer behavior", async () => {
  const page = await source("../src/pages/PositionEpisodePage.tsx");
  const workspace = await source("../src/components/charts/EpisodeChartWorkspace.tsx");
  assert.equal((page.match(/<EpisodeChartWorkspace/g) ?? []).length, 1);
  assert.equal((workspace.match(/<PositionEpisodeTimeline/g) ?? []).length, 1);
  assert.equal((workspace.match(/<PositionQuantityTimeline/g) ?? []).length, 1);
  assert.doesNotMatch(page, /selectLensDecision/);
  assert.match(page, /open=\{selectedDecision !== null\}/);
  assert.match(page, /!open && setSelectedDecisionId\(null\)/);
  assert.match(page, /<Sheet open=\{open\} onOpenChange=\{onOpenChange\}>/);
  assert.match(page, /optical \? <OpticalDecisionFocus timestamp=\{timestamp\}/);
  assert.match(page, /optical && data.mode === "demo" \? <OpticalExampleBoundary/);
  assert.match(page, /data.mode === "real_user" && episode.accountId \? <DecisionAnalysisWorkspace/);
});

test("Lens is decorative, deterministic and cannot intercept chart gestures or render financial facts", async () => {
  const component = await source("../src/experiments/optical-review/OpticalReview.tsx");
  const lens = component.slice(component.indexOf("export function DecisionLens"), component.indexOf("export function OpticalReviewSwitch"));
  assert.match(lens, /aria-hidden="true"/);
  assert.match(lens, /in="SourceGraphic"/);
  assert.match(lens, /useId\(\)/);
  assert.doesNotMatch(lens, /executionPrice|pnl|returnValue|quantity|onClick|onPointer|Math\.random/);
  assert.doesNotMatch(component, /requestAnimationFrame|addEventListener|setInterval|from ["'](three|ogl|gsap)|reviewService|fetch\(|runtimeRequest/);
});

test("the experiment does not attach an unrelated comparison or invent an Agent response", async () => {
  const component = await source("../src/experiments/optical-review/OpticalReview.tsx");
  assert.match(component, /No model has been called/);
  assert.match(component, /not this investment/);
  assert.match(component, /key=\{label\} disabled/);
  assert.doesNotMatch(component, /same_stock_compare_demo|possible_explanations|claim_options|adaptSameStock|generated\/backend/);
});

test("all experiment CSS rules are scoped; no data deformation or perpetual animation is added", async () => {
  const css = await source("../src/experiments/optical-review/optical-review.css");
  const tree = postcss.parse(css);
  tree.walkRules(rule => {
    if (rule.parent.type === "atrule" && rule.parent.name === "keyframes") return;
    for (const selector of rule.selectors) assert.match(selector, /\.optical-|\.episode-review--optical/, selector);
    if (rule.selector.includes("[data-price-path]")) {
      rule.walkDecls(declaration => assert.ok(!["transform", "filter", "backdrop-filter", "opacity"].includes(declaration.prop), declaration.toString()));
    }
  });
  assert.doesNotMatch(css, /\binfinite\b|will-change|perspective|rotate[XYZ]|backdrop-filter:\s*url/);
  assert.match(css, /pointer-events: none/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /animation: none !important; transition: none !important/);
});

test("experiment copy is available in both locales", async () => {
  const enUS = await source("../src/locales/en-US.ts");
  const zhCN = await source("../src/locales/zh-CN.ts");
  for (const key of ["Try Optical visual experiment", "In focus · Recorded execution", "What is not established here", "Ask Toujing · Not connected in this example", "Open separate A/B Synthetic example · not this investment"]) {
    const prefix = `${JSON.stringify(key)}: `;
    assert.ok(enUS.includes(prefix)); assert.ok(zhCN.includes(prefix));
    assert.ok(!zhCN.includes(`${prefix}${JSON.stringify(key)},`));
  }
});
