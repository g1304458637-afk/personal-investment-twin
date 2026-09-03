import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const {
  TRACE_KINDS,
  adaptExplainabilityPayload,
  conceptOnlyView,
} = await import("../src/data/explainability.ts");
const enSource = await readFile(new URL("../src/locales/en-US.ts", import.meta.url), "utf8");
const zhSource = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");
const generated = JSON.parse(await readFile(
  new URL("../src/generated/backend-demo-evidence.json", import.meta.url),
  "utf8",
));

const catalog = adaptExplainabilityPayload(generated.explainability);

test("registered concepts remain user-facing metadata rather than raw calculations", () => {
  const concept = catalog.concepts.find((item) => item.conceptId === "portfolio_concentration_hhi");
  assert.equal(concept?.methodId, "hhi_security_weights_v1");
  assert.equal(concept?.titleKey, "evidence.concept.portfolio_concentration_hhi.title");
  assert.match(zhSource, /"evidence\.concept\.portfolio_concentration_hhi\.title": "持仓集中度 HHI"/);
});

test("every registered trace kind has a renderer branch", async () => {
  const source = await readFile(new URL("../src/components/evidence/CalculationRenderer.tsx", import.meta.url), "utf8");
  assert.deepEqual(TRACE_KINDS, [
    "formula_components",
    "rule_observations",
    "comparison",
    "before_after",
    "statistical_summary",
    "source_fact",
  ]);
  for (const kind of TRACE_KINDS) assert.match(source, new RegExp(`case "${kind}"`));
});

test("a registered concept without a trace never receives an inferred calculation", () => {
  const view = conceptOnlyView(catalog, "selection_episode_asset_return");
  assert.equal(view?.trace, null);
  assert.equal(view?.result, null);
  assert.equal(view?.unavailableReason, "calculation_trace_unavailable");
});

test("insufficient evidence retains no result and preserves required observations", () => {
  const view = catalog.evidenceViews.find((item) => item.trace?.status === "insufficient");
  assert.ok(view);
  assert.equal(view.trace.result, null);
  assert.equal(view.trace.requiredCondition, "completed_final_exit_and_20_subsequent_market_sessions");
  assert.equal(view.trace.availableObservation.window_price_count, 0);
});

test("fixed-window Exit starts from market price, not average execution price", () => {
  const view = catalog.evidenceViews.find((item) => item.concept.conceptId === "post_exit_fixed_window_return" && item.trace?.status === "complete");
  const exitPrice = view.trace.inputs.find((item) => item.semanticName === "episode_avg_exit_price");
  const firstMarket = view.trace.inputs.find((item) => item.id === "window_price:0");
  const operation = view.trace.operations.find((item) => item.id === "post_exit_fixed_window_return");
  assert.equal(exitPrice.value, 99.5);
  assert.equal(exitPrice.role, "context_not_return_formula");
  assert.equal(firstMarket.value, 100);
  assert.equal(firstMarket.role, "return_series_component");
  assert.equal(operation.attributes.episode_avg_exit_price_used_in_formula, false);
  assert.equal(operation.inputRefs.includes(exitPrice.id), false);
});

test("pre-trade execution and valuation prices remain separate backend inputs", () => {
  const trace = catalog.pretrade.trace;
  const execution = trace.inputs.find((item) => item.semanticName === "execution_price");
  const valuation = trace.inputs.find((item) => item.semanticName === "valuation_price");
  assert.equal(execution.role, "execution_assumption");
  assert.equal(valuation.role, "mark_not_execution");
  assert.notEqual(execution.id, valuation.id);
});

test("an open-position mark remains a valuation and not an Exit", () => {
  const open = generated.position_episode_demo.entries.find((entry) => entry.episode.status === "open");
  assert.ok(open.snapshot);
  assert.equal(open.episode.closed_at, null);
  assert.equal(open.decisions.some((decision) => decision.decision_type === "close_position"), false);
  assert.equal(open.states_by_ref[open.snapshot.position_state_ref].valuation_price !== null, true);
  assert.match(enSource, /A mark-to-market price used for portfolio valuation; it is not an executed exit price/);
});

test("method, version, limitations, and provenance survive adaptation", () => {
  const view = catalog.evidenceViews.find((item) => item.concept.conceptId === "portfolio_concentration_hhi");
  assert.equal(view.trace.methodId, view.concept.methodId);
  assert.equal(view.trace.methodVersion, view.concept.methodVersion);
  assert.ok(view.limitations.length > 0);
  assert.ok(view.provenance.some((item) => item.sourceType === "price_series"));
});

test("a malformed trace fails closed without crashing the whole catalog", () => {
  const malformed = structuredClone(generated.explainability);
  malformed.evidence_views[0].calculation_trace.trace_kind = "invented_renderer";
  const result = adaptExplainabilityPayload(malformed);
  assert.equal(result.evidenceViews.length, catalog.evidenceViews.length - 1);
  assert.match(result.invalidItems[0], /Unsupported trace kind/);
});

test("view boundary prefers the view contract and falls back to its embedded concept", () => {
  const explicit = structuredClone(generated.explainability);
  explicit.evidence_views[0].interpretation_boundary = {
    allowed_claims: ["view_specific_claim"],
    prohibited_claims: ["view_specific_boundary"],
  };
  assert.deepEqual(adaptExplainabilityPayload(explicit).evidenceViews[0].boundary.allowedClaims, ["view_specific_claim"]);

  const fallback = structuredClone(generated.explainability);
  delete fallback.evidence_views[0].interpretation_boundary;
  assert.deepEqual(
    adaptExplainabilityPayload(fallback).evidenceViews[0].boundary.allowedClaims,
    fallback.evidence_views[0].concept.interpretation_boundary.allowed_claims,
  );
});

test("both locales cover every Concept title and definition key", () => {
  for (const concept of catalog.concepts) {
    for (const key of [concept.titleKey, concept.shortDefinitionKey, concept.detailedDefinitionKey]) {
      assert.ok(enSource.includes(`${JSON.stringify(key)}:`), `missing en-US ${key}`);
      assert.ok(zhSource.includes(`${JSON.stringify(key)}:`), `missing zh-CN ${key}`);
    }
  }
});

test("frontend explainability code formats but does not recalculate financial results", async () => {
  const adapter = await readFile(new URL("../src/data/explainability.ts", import.meta.url), "utf8");
  const renderer = await readFile(new URL("../src/components/evidence/CalculationRenderer.tsx", import.meta.url), "utf8");
  for (const forbidden of [/Math\.pow/, /\.reduce\(/, /cum_returns/, /simple_returns/, /percentileofscore/]) {
    assert.doesNotMatch(adapter, forbidden);
    assert.doesNotMatch(renderer, forbidden);
  }
  assert.match(renderer, /trace\.result/);
  assert.match(renderer, /operation\.result/);
});
