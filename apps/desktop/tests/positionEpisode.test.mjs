import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptPositionEpisodeDemo } = await import("../src/data/positionEpisode.ts");

function state(id, overrides = {}) {
  return {
    state_id: id,
    subject_id: "demo-user",
    account_id: "demo-account",
    instrument_id: "SYN",
    as_of: "2025-01-02T00:00:00",
    boundary: "after_execution",
    execution_id: "execution-1",
    quantity: 100,
    average_cost: 10,
    valuation_at: "2025-01-02T00:00:00",
    valuation_price: 11,
    market_value: 1100,
    replay_method_id: "vectorbt_portfolio_replay_v1",
    ...overrides,
  };
}

function source(kind, id, executionRefs) {
  return {
    source_kind: kind,
    source_record_id: id,
    replay_scope_id: "scope-test",
    vectorbt_record_id: 0,
    execution_refs: executionRefs,
  };
}

function result(kind, status, pnl, sourceValue) {
  return {
    result_kind: kind,
    result_basis: "net_pnl",
    pnl,
    return_value: kind === "counterfactual" ? null : 0.1,
    result_sign: pnl > 0 ? "profit" : pnl < 0 ? "loss" : "flat",
    position_status: status,
    recorded_entry_fees: 0,
    recorded_exit_fees: 0,
    valuation_at: status === "open" ? "2025-01-08T00:00:00" : null,
    valuation_price: status === "open" ? 10 : null,
    source: sourceValue,
  };
}

function outcomeStory(entry) {
  const episodeResult = result("marked", "open", 100, source("vectorbt_position", "position-0", ["execution-1", "execution-2"]));
  const episodeOutcome = {
    outcome_id: "outcome-episode",
    episode_id: "episode-open",
    subject_id: "demo-user",
    account_id: "demo-account",
    instrument_id: "SYN",
    episode_status: "open",
    analysis_as_of: "2025-01-08T23:59:00",
    relation_type: "marked_position_result",
    actual_result: episodeResult,
    decision_event_refs: ["decision-open", "decision-reduce"],
    execution_refs: ["execution-1", "execution-2"],
    duration_days: 6,
    duration_kind: "so_far",
    method_id: "historical_decision_outcome_v1",
    method_version: "1",
    calculation_code_version: "test-v1",
    limitations: ["Recorded history only."],
  };
  return {
    episode_outcome: episodeOutcome,
    decision_outcomes: entry.decisions.map((decision) => {
      const before = entry.states_by_ref[decision.state_before_ref];
      const after = entry.states_by_ref[decision.state_after_ref];
      return {
        outcome_id: `outcome-${decision.decision_id}`,
        subject_id: "demo-user",
        account_id: "demo-account",
        instrument_id: "SYN",
        episode_id: "episode-open",
        decision_event_id: decision.decision_id,
        event_type: decision.decision_type,
        event_time: decision.occurred_at,
        relation_types: decision.side === "SELL" ? ["deterministic_state_transition", "accounting_realized_result"] : ["deterministic_state_transition"],
        before: { state_ref: before.state_id, quantity: before.quantity, average_cost: before.average_cost, position_status: before.quantity === 0 ? "flat" : "open" },
        execution_id: decision.execution_id,
        side: decision.side,
        executed_quantity: decision.executed_quantity,
        execution_price: decision.execution_price,
        execution_fee: decision.fees,
        execution_source: source("vectorbt_order", `order-${decision.execution_id}`, [decision.execution_id]),
        after: { state_ref: after.state_id, quantity: after.quantity, average_cost: after.average_cost, position_status: after.quantity === 0 ? "flat" : "open" },
        immediate_result: decision.side === "SELL" ? result("realized", "closed", 100, source("vectorbt_exit_trade", "trade-0", [decision.execution_id])) : null,
        episode_result_ref: "outcome-episode",
        evidence_refs: [],
        method_id: "historical_decision_outcome_v1",
        method_version: "1",
        calculation_code_version: "test-v1",
        limitations: ["Recorded history only."],
      };
    }),
    counterfactuals: [],
    exit_followup: null,
  };
}

function demo(overrides = {}) {
  const before = state("state-before", {
    boundary: "before_execution",
    quantity: 0,
    average_cost: null,
    valuation_at: null,
    valuation_price: null,
    market_value: null,
  });
  const after = state("state-after");
  const snapshot = state("state-snapshot", {
    boundary: "as_of_valuation",
    execution_id: null,
    quantity: 50,
    valuation_at: "2025-01-08T00:00:00",
    valuation_price: 10,
    market_value: 500,
  });
  const payload = {
    data_tier: "synthetic",
    default_episode_id: "episode-open",
    entries: [
      {
        instrument: {
          instrument_id: "SYN",
          display_name: "Demo Security",
          is_synthetic: true,
          data_tier: "synthetic",
        },
        episode: {
          episode_id: "episode-open",
          subject_id: "demo-user",
          account_id: "demo-account",
          instrument_id: "SYN",
          status: "open",
          opened_at: "2025-01-02T00:00:00",
          closed_at: null,
          opening_execution_id: "execution-1",
          closing_execution_id: null,
          execution_refs: ["execution-1", "execution-2"],
          decision_refs: ["decision-open", "decision-reduce"],
          evidence_refs: ["evidence-insufficient"],
          duration_days: 6,
          duration_kind: "so_far",
          replay_method_id: "vectorbt_portfolio_replay_v1",
          calculation_code_version: "test-v1",
          data_tier: "synthetic",
          limitations: ["Open valuation is a mark, not an exit."],
        },
        decisions: [
          {
            decision_id: "decision-open",
            episode_id: "episode-open",
            execution_id: "execution-1",
            occurred_at: "2025-01-02T00:00:00",
            decision_type: "open_position",
            side: "BUY",
            executed_quantity: 100,
            execution_price: 10,
            fees: 0,
            state_before_ref: "state-before",
            state_after_ref: "state-after",
            evidence_refs: [],
          },
          {
            decision_id: "decision-reduce",
            episode_id: "episode-open",
            execution_id: "execution-2",
            occurred_at: "2025-01-07T00:00:00",
            decision_type: "reduce_position",
            side: "SELL",
            executed_quantity: 50,
            execution_price: 12,
            fees: 0,
            state_before_ref: "state-after",
            state_after_ref: "state-snapshot",
            evidence_refs: [],
          },
        ],
        states_by_ref: {
          "state-before": before,
          "state-after": after,
          "state-snapshot": snapshot,
        },
        snapshot: {
          episode_id: "episode-open",
          as_of: "2025-01-08T23:59:00",
          position_state_ref: "state-snapshot",
        },
        evidence_references: [
          {
            evidence_id: "evidence-insufficient",
            metric_id: "selection",
            method_id: "selection-v1",
            method_version: "1",
            evidence_status: "insufficient_evidence",
            evidence_reason: "Required benchmark is unavailable.",
            available_at: "2025-01-08T00:00:00",
          },
        ],
        price_points: [
          { observed_at: "2025-01-02T00:00:00", price: 10, segment: "episode" },
          { observed_at: "2025-01-08T00:00:00", price: 10, segment: "episode" },
        ],
      },
    ],
    ...overrides,
  };
  payload.entries[0].outcome_story = outcomeStory(payload.entries[0]);
  payload.entries[0].path_analysis = pathAnalysis(payload.entries[0]);
  return payload;
}

function observation(at, price) {
  return {
    observed_at: at,
    price,
    instrument_id: "SYN",
    price_type: "adjusted_close",
    data_source: "test",
    data_version: "v1",
  };
}

function pathAnalysis(entry) {
  const episodeId = entry.episode.episode_id;
  const open = entry.decisions[0];
  const later = entry.decisions[1];
  const phases = [
    {
      phase_id: "phase-entry",
      episode_id: episodeId,
      phase_type: "entry",
      taxonomy_version: "1",
      started_at: open.occurred_at,
      ended_at: open.occurred_at,
      decision_event_ids: [open.decision_id],
      execution_ids: [open.execution_id],
      quantity_before: 0,
      quantity_after: 100,
      average_cost_before: null,
      average_cost_after: 10,
      state_before_ref: open.state_before_ref,
      state_after_ref: open.state_after_ref,
      method_version: "1",
    },
    {
      phase_id: "phase-reduce",
      episode_id: episodeId,
      phase_type: "scaling_out",
      taxonomy_version: "1",
      started_at: later.occurred_at,
      ended_at: later.occurred_at,
      decision_event_ids: [later.decision_id],
      execution_ids: [later.execution_id],
      quantity_before: 100,
      quantity_after: 50,
      average_cost_before: 10,
      average_cost_after: 10,
      state_before_ref: later.state_before_ref,
      state_after_ref: later.state_after_ref,
      method_version: "1",
    },
  ];
  return {
    episode_id: episodeId,
    method_id: "episode_path_analysis_v1",
    method_version: "1",
    market_path: {
      episode_id: episodeId,
      subject_id: entry.episode.subject_id,
      account_id: entry.episode.account_id,
      instrument_id: "SYN",
      pre_entry_context_status: "insufficient",
      episode_context_status: "complete",
      post_exit_context_status: "insufficient",
      pre_entry_context: {
        status: "insufficient",
        observations: [],
        valid_observation_count: 0,
        requested_observation_count: 20,
        start_observation: null,
        end_observation: null,
        price_change: null,
        price_return: null,
        method_version: "1",
      },
      episode_market_path: {
        segment: "episode",
        status: "complete",
        observations: [observation("2025-01-02T00:00:00", 10), observation("2025-01-08T00:00:00", 10)],
        valid_observation_count: 2,
        requested_observation_count: null,
        daily_path_max: observation("2025-01-08T00:00:00", 10),
        daily_path_min: observation("2025-01-02T00:00:00", 10),
      },
      post_exit_context: {
        segment: "post_exit",
        status: "insufficient",
        observations: [],
        valid_observation_count: 0,
        requested_observation_count: 20,
        daily_path_max: null,
        daily_path_min: null,
      },
      decision_interval_moves: [],
      trailing_hold_observation: null,
      market_path_segments: [],
      daily_price_peak_drawdown: null,
      method_id: "episode_path_analysis_v1",
      method_version: "1",
      limitations: [],
    },
    position_path: {
      episode_id: episodeId,
      points: [],
      max_quantity: 100,
      max_quantity_as_of: open.occurred_at,
      max_quantity_state_id: open.state_after_ref,
      quantity_at_drawdown: null,
    },
    phases,
    patterns: [],
    phase_counterfactuals: [],
    presentation_items: [
      { item_id: "phase-reduce", kind: "phase", phase_id: "phase-reduce", pattern_id: null, reason_code: "large_quantity_change" },
      { item_id: "phase-entry", kind: "phase", phase_id: "phase-entry", pattern_id: null, reason_code: "episode_path_phase" },
    ],
    limitations: [],
  };
}

test("position episode adapter preserves backend decision order, refs, and explicit evidence state", () => {
  const source = demo();
  const view = adaptPositionEpisodeDemo(source);
  const entry = view.entries[0];

  assert.equal(view.defaultEpisodeId, source.default_episode_id);
  assert.deepEqual(entry.decisions.map((decision) => decision.decisionType), ["open_position", "reduce_position"]);
  assert.equal(entry.decisions[1].stateBefore, entry.statesByRef["state-after"]);
  assert.equal(entry.decisions[1].stateAfterRef, "state-snapshot");
  assert.equal(entry.evidenceReferences[0].status, "insufficient_evidence");
  assert.equal(entry.evidenceReferences[0].reason, "Required benchmark is unavailable.");
});

test("open episode retains a valuation snapshot separate from execution facts", () => {
  const entry = adaptPositionEpisodeDemo(demo()).entries[0];

  assert.equal(entry.episode.closedAt, null);
  assert.equal(entry.episode.closingExecutionId, null);
  assert.equal(entry.snapshot?.positionState.valuationPrice, 10);
  assert.equal(entry.decisions[1].executionPrice, 12);
  assert.notEqual(entry.snapshot?.positionState.valuationPrice, entry.decisions[1].executionPrice);
  assert.equal(entry.decisions.some((decision) => decision.decisionType === "close_position"), false);
});

test("adapter rejects invalid open lifecycle semantics and missing state references", () => {
  const closedAt = demo();
  closedAt.entries[0].episode.closed_at = "2025-01-08T00:00:00";
  assert.throws(() => adaptPositionEpisodeDemo(closedAt), /must not expose a close timestamp/);

  const missingSnapshot = demo();
  missingSnapshot.entries[0].snapshot = null;
  assert.throws(() => adaptPositionEpisodeDemo(missingSnapshot), /must provide an as-of valuation snapshot/);

  const closeDecision = demo();
  closeDecision.entries[0].decisions[1].decision_type = "close_position";
  assert.throws(() => adaptPositionEpisodeDemo(closeDecision), /does not resolve|must not contain a close decision/);

  const missingState = demo();
  missingState.entries[0].decisions[0].state_after_ref = "not-present";
  assert.throws(() => adaptPositionEpisodeDemo(missingState), /references missing state/);

  const foreignDecision = demo();
  foreignDecision.entries[0].decisions[0].episode_id = "another-episode";
  assert.throws(() => adaptPositionEpisodeDemo(foreignDecision), /belongs to another Episode/);

  const foreignSnapshot = demo();
  foreignSnapshot.entries[0].snapshot.episode_id = "another-episode";
  assert.throws(() => adaptPositionEpisodeDemo(foreignSnapshot), /snapshot belongs to another Episode/);
});

test("generated synthetic episode demo has a stable default, and backend exposes a null-safe lookup", async () => {
  const raw = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
  const view = adaptPositionEpisodeDemo(raw.position_episode_demo);
  const backendAdapter = await readFile(new URL("../src/data/backendEvidence.ts", import.meta.url), "utf8");

  assert.equal(view.dataTier, "synthetic");
  assert.ok(view.entries.find((entry) => entry.episode.episodeId === view.defaultEpisodeId));
  assert.match(backendAdapter, /getPositionEpisodeById\(episodeId: string\).*\?\? null/s);
});

test("generated demo preserves distinct Closed and Open visual semantics", async () => {
  const raw = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));
  const view = adaptPositionEpisodeDemo(raw.position_episode_demo);
  const closed = view.entries.find((entry) => entry.episode.status === "closed");
  const open = view.entries.find((entry) => entry.episode.status === "open");

  assert.ok(closed);
  assert.ok(open);
  assert.equal(closed.snapshot, null);
  assert.equal(closed.decisions.at(-1)?.decisionType, "close_position");
  assert.ok(closed.episode.closingExecutionId);
  assert.ok(open.snapshot);
  assert.equal(open.episode.closedAt, null);
  assert.equal(open.decisions.some((decision) => decision.decisionType === "close_position"), false);
  assert.notEqual(open.snapshot.positionState.valuationPrice, open.decisions.at(-1)?.executionPrice);
});

test("presentation metadata preserves canonical identity and falls back safely", () => {
  const source = demo();
  source.entries[0].instrument.display_name = "<untrusted demo name>";
  const named = adaptPositionEpisodeDemo(source).entries[0];
  assert.equal(named.instrument.displayName, "<untrusted demo name>");
  assert.equal(named.instrument.instrumentId, "SYN");
  assert.equal(named.episode.instrumentId, "SYN");

  const unnamed = demo();
  unnamed.entries[0].instrument.display_name = null;
  assert.equal(adaptPositionEpisodeDemo(unnamed).entries[0].instrument.displayName, "SYN");

  const mismatched = demo();
  mismatched.entries[0].instrument.instrument_id = "OTHER";
  assert.throws(() => adaptPositionEpisodeDemo(mismatched), /metadata must match/);
});

test("Episode UI uses backend facts and labels current valuation as not an exit", async () => {
  const page = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  const chart = await readFile(new URL("../src/components/charts/PositionEpisodeTimeline.tsx", import.meta.url), "utf8");
  const chinese = await readFile(new URL("../src/locales/zh-CN.ts", import.meta.url), "utf8");

  assert.equal(page.includes("@/demo/fixture"), false);
  assert.equal(page.includes("dangerouslySetInnerHTML"), false);
  assert.match(page, /outcome\.before\.quantity/);
  assert.match(page, /outcome\.after\.quantity/);
  assert.match(chart, /seriesId !== "decision-events"/);
  assert.match(chart, /silent: true/);
  assert.match(chinese, /"Open position": "建仓"/);
  assert.match(chinese, /"Add position": "加仓"/);
  assert.match(chinese, /"Reduce position": "减仓"/);
  assert.match(chinese, /"Close position \/ final sale": "清仓 \/ 最终卖出"/);
  assert.match(chinese, /"Latest valid valuation · not an exit": "最近有效估值 · 不是退出"/);
});

test("adapter requires path_analysis and fails closed on unknown phase refs", () => {
  const missing = demo();
  delete missing.entries[0].path_analysis;
  assert.throws(() => adaptPositionEpisodeDemo(missing), /path_analysis/);

  const unknownPhase = demo();
  unknownPhase.entries[0].path_analysis.presentation_items[0].phase_id = "phase-missing";
  assert.throws(() => adaptPositionEpisodeDemo(unknownPhase), /unknown phase/);
});

test("selectPrimaryPathItems only reads backend presentation_items", async () => {
  const { selectPrimaryPathItems } = await import("../src/data/positionEpisode.ts");
  const source = await readFile(new URL("../src/data/positionEpisode.ts", import.meta.url), "utf8");
  const entry = adaptPositionEpisodeDemo(demo()).entries[0];
  assert.deepEqual(
    selectPrimaryPathItems(entry.pathAnalysis).map((item) => item.itemId),
    entry.pathAnalysis.presentationItems.slice(0, 6).map((item) => item.itemId),
  );
  const selector = source.slice(
    source.indexOf("export function selectPrimaryPathItems"),
    source.indexOf("function finite"),
  );
  assert.match(selector, /return path.presentationItems.slice\(0, 6\)/);
  assert.doesNotMatch(selector, /VWAP|price_return|group\(/);
});
