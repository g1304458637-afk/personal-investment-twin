import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptDecisionOutcomeStory, selectPrimaryCounterfactuals } = await import("../src/data/decisionOutcome.ts");
const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));

function context(entry) {
  return {
    subjectId: entry.episode.subject_id,
    accountId: entry.episode.account_id,
    instrumentId: entry.episode.instrument_id,
    episodeId: entry.episode.episode_id,
    episodeStatus: entry.episode.status,
    decisions: entry.decisions.map((item) => ({ decisionId: item.decision_id, executionId: item.execution_id, side: item.side })),
  };
}

function adapt(entry) {
  return adaptDecisionOutcomeStory(structuredClone(entry.outcome_story), context(entry));
}

test("strict v2 preserves prior observation metadata and rejects mixed valuation bases", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const story = adapt(entry);
  const strict = story.counterfactuals.find((item) => item.scenarioId === "omit_event_until_next_decision_v2" && item.feasibilityStatus === "complete");
  assert.ok(strict);
  assert.equal(strict.scenarioVersion, "2");
  assert.equal(strict.actualResult.valuationAt, strict.valuationObservationDate);
  assert.equal(strict.counterfactualResult.valuationAt, strict.valuationObservationDate);
  assert.ok(strict.heldConstant.some((item) => item.includes("not an intraday quote")));
  const broken = structuredClone(entry);
  const raw = broken.outcome_story.counterfactuals.find((item) => item.counterfactual_id === strict.counterfactualId);
  raw.counterfactual_result.valuation_price += 1;
  assert.throws(() => adapt(broken), /valuation basis/);
});

test("valid generated stories preserve Closed realized and Open marked Episode outcomes", () => {
  const closedEntry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const openEntry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "SYN_PAPER_LOSS");
  const closed = adapt(closedEntry).episodeOutcome;
  const open = adapt(openEntry).episodeOutcome;
  assert.equal(closed.actualResult.resultKind, "realized");
  assert.equal(closed.actualResult.positionStatus, "closed");
  assert.equal(closed.actualResult.pnl, 3369.1);
  assert.equal(open.actualResult.resultKind, "marked");
  assert.equal(open.actualResult.positionStatus, "open");
  assert.equal(open.actualResult.pnl, -400);
});

test("product relevance hides structural opening omissions and keeps at most one primary result", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const story = adapt(entry);
  const decisions = story.decisionOutcomes.map((item) => ({ decisionId: item.decisionEventId, eventType: item.eventType }));
  const primary = selectPrimaryCounterfactuals(story.counterfactuals, decisions);
  assert.equal(primary.some((item) => decisions.find((decision) => decision.decisionId === item.decisionEventId)?.eventType === "open_position"), false);
  assert.equal(new Set(primary.map((item) => item.decisionEventId)).size, primary.length);
  assert.ok(primary.some((item) => decisions.find((decision) => decision.decisionId === item.decisionEventId)?.eventType === "add_position"));
  assert.ok(primary.some((item) => decisions.find((decision) => decision.decisionId === item.decisionEventId)?.eventType === "reduce_position"));
});

test("primary counterfactual selection preserves backend result values unchanged", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const story = adapt(entry);
  const primary = selectPrimaryCounterfactuals(story.counterfactuals, story.decisionOutcomes.map((item) => ({ decisionId: item.decisionEventId, eventType: item.eventType })));
  for (const item of primary) {
    const source = story.counterfactuals.find((candidate) => candidate.counterfactualId === item.counterfactualId);
    assert.equal(item.actualResult?.pnl, source.actualResult?.pnl);
    assert.equal(item.counterfactualResult?.pnl, source.counterfactualResult?.pnl);
    assert.equal(item.comparison.pnlDifference, source.comparison.pnlDifference);
  }
});

test("SELL outcomes preserve authoritative realized PnL while BUY outcomes have none", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const story = adapt(entry);
  const buys = story.decisionOutcomes.filter((item) => item.side === "BUY");
  const sells = story.decisionOutcomes.filter((item) => item.side === "SELL");
  assert.ok(buys.every((item) => item.immediateResult === null));
  assert.ok(sells.every((item) => item.immediateResult?.resultKind === "realized"));
  assert.ok(sells.every((item) => item.immediateResult?.source.sourceKind === "vectorbt_exit_trade"));
  assert.ok(story.episodeOutcome.actualResult.source.sourceRecordId);
});

test("wrong subject, Episode, event, and result kind fail closed", () => {
  const entry = generated.position_episode_demo.entries[0];
  const wrongSubject = structuredClone(entry.outcome_story);
  wrongSubject.episode_outcome.subject_id = "another-subject";
  assert.throws(() => adaptDecisionOutcomeStory(wrongSubject, context(entry)), /ownership/);

  const wrongEpisode = structuredClone(entry.outcome_story);
  wrongEpisode.decision_outcomes[0].episode_id = "another-episode";
  assert.throws(() => adaptDecisionOutcomeStory(wrongEpisode, context(entry)), /ownership/);

  const unknownEvent = structuredClone(entry.outcome_story);
  unknownEvent.counterfactuals[0].decision_event_id = "unknown-event";
  assert.throws(() => adaptDecisionOutcomeStory(unknownEvent, context(entry)), /unknown event/);

  const badKind = structuredClone(entry.outcome_story);
  badKind.episode_outcome.actual_result.result_kind = "estimated";
  assert.throws(() => adaptDecisionOutcomeStory(badKind, context(entry)), /result_kind is unsupported/);
});

test("basis mismatch and infeasible downstream paths remain explicit", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "600000.SH");
  const mismatch = structuredClone(entry.outcome_story);
  const complete = mismatch.counterfactuals.find((item) => item.comparison.comparison_status === "complete");
  complete.comparison = {
    comparison_status: "unavailable_result_basis_mismatch",
    result_basis: null,
    pnl_difference: null,
    actual_result_sign: complete.actual_result.result_sign,
    counterfactual_result_sign: complete.counterfactual_result.result_sign,
    result_transition: null,
  };
  complete.counterfactual_result.result_basis = "gross_pnl_before_incremental_friction";
  const view = adaptDecisionOutcomeStory(mismatch, context(entry));
  assert.equal(view.counterfactuals[0].comparison.status, "unavailable_result_basis_mismatch");
  assert.equal(view.counterfactuals[0].comparison.pnlDifference, null);

  const actual = adapt(entry);
  const infeasible = actual.counterfactuals.find((item) => item.feasibilityStatus === "infeasible_downstream_execution");
  assert.ok(infeasible);
  assert.ok(infeasible.firstConflictingExecutionId);
  assert.equal(infeasible.counterfactualResult, null);
});

test("registered comparison transitions and backend differences are parsed unchanged", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "SYN_PAPER_LOSS");
  const complete = adapt(entry).counterfactuals.find((item) => item.comparison.resultTransition === "loss_reduced");
  assert.ok(complete);
  assert.equal(complete.scenarioId, "omit_event_until_next_decision_v2");
  const raw = entry.outcome_story.counterfactuals.find((item) => item.counterfactual_id === complete.counterfactualId);
  assert.equal(complete.comparison.pnlDifference, raw.comparison.pnl_difference);
  assert.equal(complete.comparison.pnlDifference, 50);
  assert.equal(complete.comparison.resultTransition, "loss_reduced");
});

test("Exit follow-up retains separate execution and market price bases", () => {
  const entry = generated.position_episode_demo.entries.find((item) => item.instrument.instrument_id === "SYN_EXIT_UP");
  const story = adapt(entry);
  assert.equal(story.exitFollowup.actualExitPrice, 99.5);
  assert.equal(story.exitFollowup.exitSessionMarketPrice, 100);
  assert.equal(story.exitFollowup.postExitAssetReturn, 0.19999999999999973);
  assert.ok(story.counterfactuals.some((item) => item.baselineEvidenceRef === story.exitFollowup.evidenceId));
});

test("Desktop Outcome adapter maps frozen fields and contains no financial calculator", async () => {
  const source = await readFile(new URL("../src/data/decisionOutcome.ts", import.meta.url), "utf8");
  assert.match(source, /pnl_difference/);
  assert.match(source, /result_transition/);
  assert.doesNotMatch(source, /calculatePnL|costBasis|simple_returns|cum_returns|percentileofscore/);
  assert.doesNotMatch(source, /Math\.(abs|pow|round)|\.reduce\s*\(/);
});
