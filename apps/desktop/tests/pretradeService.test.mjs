import assert from "node:assert/strict";
import test from "node:test";

const { adaptPretradeImpact } = await import("../src/data/pretradeImpact.ts");
const {
  checkPretrade,
  emptyPretradeRequestState,
  inputFromDemo,
  PretradeServiceError,
  pretradeRequestReducer,
} = await import("../src/data/pretradeService.ts");

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

function backendImpact(overrides = {}) {
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

const offlineDemo = adaptPretradeImpact(backendImpact());
const input = inputFromDemo(offlineDemo);

test("request reducer exposes loading, success, and stale-clearing states", () => {
  const loading = pretradeRequestReducer(emptyPretradeRequestState, {
    type: "started",
    requestId: "A",
  });
  assert.equal(loading.phase, "loading");

  const outcome = {
    requestId: "A",
    runtime: "tauri_local",
    impact: offlineDemo,
  };
  const success = pretradeRequestReducer(loading, {
    type: "succeeded",
    requestId: "A",
    outcome,
  });
  assert.equal(success.phase, "success");
  assert.equal(success.outcome.impact.after.hhi, 0.56);

  const stale = pretradeRequestReducer(success, { type: "input_changed" });
  assert.equal(stale.phase, "idle");
  assert.equal(stale.outcome, null);
  assert.equal(stale.stale, true);
});

test("a rejected engine result remains a successful bridge response with rejection facts", async () => {
  const rejected = backendImpact({
    after: null,
    delta: null,
    self_context: null,
    peer_context: null,
    simulation_status: "rejected",
    simulation_reason: "Proposed BUY cannot be executed because cash is insufficient",
  });
  const outcome = await checkPretrade(input, {
    runtime: "tauri_local",
    requestId: "rejected-request",
    invokePretrade: async () => ({
      request_id: "rejected-request",
      ok: true,
      result: rejected,
      error: null,
    }),
  });

  assert.equal(outcome.impact.status, "rejected");
  assert.match(outcome.impact.reason, /cash is insufficient/);
  assert.equal(outcome.impact.after, null);
});

test("service invokes only the registered Tauri command and preserves request ID", async () => {
  let observed;
  const outcome = await checkPretrade({ ...input, quantity: 250 }, {
    runtime: "tauri_local",
    requestId: "live-request",
    invokePretrade: async (command, args) => {
      observed = { command, args };
      const result = backendImpact();
      result.proposed_trade.quantity = 250;
      return {
        request_id: "live-request",
        ok: true,
        result,
        error: null,
      };
    },
  });

  assert.equal(observed.command, "run_pretrade_check");
  assert.deepEqual(Object.keys(observed.args), ["request"]);
  assert.equal(observed.args.request.action, "pretrade_check");
  assert.equal(observed.args.request.payload.quantity, 250);
  assert.equal(outcome.requestId, "live-request");
});

test("error state preserves a bridge rejection", () => {
  const loading = pretradeRequestReducer(emptyPretradeRequestState, {
    type: "started",
    requestId: "A",
  });
  const error = new PretradeServiceError("bridge_error", "Bridge unavailable", "A");
  const failed = pretradeRequestReducer(loading, {
    type: "failed",
    requestId: "A",
    error,
  });

  assert.equal(failed.phase, "error");
  assert.equal(failed.error.message, "Bridge unavailable");
});

test("an older response cannot overwrite a newer request", () => {
  const requestA = pretradeRequestReducer(emptyPretradeRequestState, {
    type: "started",
    requestId: "A",
  });
  const requestB = pretradeRequestReducer(requestA, {
    type: "started",
    requestId: "B",
  });
  const oldOutcome = {
    requestId: "A",
    runtime: "tauri_local",
    impact: offlineDemo,
  };

  const unchanged = pretradeRequestReducer(requestB, {
    type: "succeeded",
    requestId: "A",
    outcome: oldOutcome,
  });

  assert.equal(unchanged, requestB);
  assert.equal(unchanged.activeRequestId, "B");
  assert.equal(unchanged.phase, "loading");
});

test("browser fallback is explicitly offline and refuses changed inputs", async () => {
  const outcome = await checkPretrade(input, {
    runtime: "browser_offline_demo",
    requestId: "offline-request",
    offlineDemo,
  });
  assert.equal(outcome.runtime, "browser_offline_demo");
  assert.equal(outcome.impact, offlineDemo);

  await assert.rejects(
    checkPretrade(
      { ...input, quantity: input.quantity + 1 },
      {
        runtime: "browser_offline_demo",
        requestId: "offline-changed",
        offlineDemo,
      },
    ),
    (error) => error instanceof PretradeServiceError && error.code === "offline_demo_only",
  );
});

test("request ID mismatch is rejected before a result can reach the page", async () => {
  await assert.rejects(
    checkPretrade(input, {
      runtime: "tauri_local",
      requestId: "expected",
      invokePretrade: async () => ({
        request_id: "unexpected",
        ok: true,
        result: backendImpact(),
        error: null,
      }),
    }),
    (error) => error instanceof PretradeServiceError && error.code === "request_id_mismatch",
  );
});
