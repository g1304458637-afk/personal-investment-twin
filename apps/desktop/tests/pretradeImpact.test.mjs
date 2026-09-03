import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptPretradeImpact } = await import("../src/data/pretradeImpact.ts");

function state(overrides = {}) {
  return {
    cash: 90_000,
    portfolio_value: 100_000,
    symbol_quantity: 500,
    symbol_weight: 0.065,
    valuation_price: 13,
    hhi: 0.48,
    active_assets: 5,
    ...overrides,
  };
}

function payload(overrides = {}) {
  return {
    proposed_trade: {
      subject_id: "demo-user:synthetic-behavior",
      proposed_time: "2025-01-08T23:59:00",
      symbol: "SYN_PAPER_WIN",
      side: "BUY",
      quantity: 200,
      execution_price: 13,
      fees: 5,
    },
    before: state(),
    after: state({ cash: 87_395, symbol_quantity: 700, symbol_weight: 0.09, hhi: 0.56 }),
    delta: { cash: -2_605, symbol_weight: 0.025, hhi: 0.08 },
    self_context: {
      historical_hhi_median: 0.34,
      current_hhi: 0.48,
      proposed_hhi: 0.56,
      historical_observation_count: 5,
      history_method_id: "hhi_security_weights_v1",
    },
    peer_context: {
      cohort_id: "synthetic-cn-equity-long-only-2025-01-v1",
      cohort_n: 72,
      metric_n: 72,
      cohort_hhi_median: 0.43,
      current_percentile: 66.7,
      proposed_percentile: 83.3,
      percentile_method: "scipy_percentileofscore_rank_v1",
    },
    simulation_status: "complete",
    simulation_reason: null,
    data_tier: "synthetic",
    limitations: ["No prediction."],
    ...overrides,
  };
}

test("pre-trade adapter maps complete backend facts without calculating them", () => {
  const source = payload();
  const view = adaptPretradeImpact(source);

  assert.equal(view.symbol, "SYN_PAPER_WIN");
  assert.equal(view.before?.symbolWeight, source.before.symbol_weight);
  assert.equal(view.after?.hhi, source.after.hhi);
  assert.equal(view.delta?.cash, source.delta.cash);
  assert.equal(view.selfContext?.historicalHhiMedian, source.self_context.historical_hhi_median);
  assert.equal(view.peerContext?.proposedPercentile, source.peer_context.proposed_percentile);
});

test("pre-trade adapter keeps assumed execution and valuation prices distinct", () => {
  const source = payload({
    proposed_trade: {
      ...payload().proposed_trade,
      execution_price: 12.5,
    },
    before: state({ valuation_price: 13 }),
    after: state({ valuation_price: 13 }),
  });
  const view = adaptPretradeImpact(source);

  assert.equal(view.executionPrice, 12.5);
  assert.equal(view.after?.valuationPrice, 13);
  assert.notEqual(view.executionPrice, view.after?.valuationPrice);
});

test("pre-trade adapter preserves a rejected result without inventing after state", () => {
  const source = payload({
    after: null,
    delta: null,
    self_context: null,
    peer_context: null,
    simulation_status: "rejected",
    simulation_reason: "Cash is insufficient.",
  });
  const view = adaptPretradeImpact(source);

  assert.equal(view.status, "rejected");
  assert.equal(view.reason, "Cash is insufficient.");
  assert.equal(view.after, null);
  assert.equal(view.peerContext, null);
});

test("pre-trade adapter rejects non-synthetic or incompatible percentile facts", () => {
  assert.throws(
    () => adaptPretradeImpact(payload({ data_tier: "production" })),
    /synthetic/,
  );
  const wrongMethod = payload();
  wrongMethod.peer_context.percentile_method = "custom_percentile";
  assert.throws(() => adaptPretradeImpact(wrongMethod), /rank percentile/);
});

test("Decision Check no longer contains the handwritten scenario fixture", async () => {
  const fixture = await readFile(new URL("../src/demo/fixture.ts", import.meta.url), "utf8");
  const page = await readFile(new URL("../src/pages/DecisionCheckPage.tsx", import.meta.url), "utf8");

  assert.equal(fixture.includes("decisionCheckScenario"), false);
  assert.equal(fixture.includes("26.4% deterministic scenario exposure"), false);
  assert.equal(page.includes("@/data/backendEvidence"), true);
  assert.equal(page.includes("@/demo/fixture"), false);
});

test("Decision Check labels valuation differences as mark-to-market, not future return", async () => {
  const page = await readFile(new URL("../src/pages/DecisionCheckPage.tsx", import.meta.url), "utf8");
  const english = await readFile(new URL("../src/locales/en-US.ts", import.meta.url), "utf8");
  const chinese = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");

  assert.match(page, /Assumed execution price/);
  assert.match(page, /Portfolio valuation price/);
  assert.match(page, /not a future return forecast/);
  assert.doesNotMatch(page, /expected return|anticipated profit|arbitrage profit/i);
  assert.match(english, /"Assumed execution price": "Assumed execution price"/);
  assert.match(english, /"Portfolio valuation price": "Portfolio valuation price"/);
  assert.match(chinese, /"Assumed execution price": "假设成交价"/);
  assert.match(chinese, /"Portfolio valuation price": "组合估值价"/);
  assert.match(chinese, /不是未来收益预测/);
});
