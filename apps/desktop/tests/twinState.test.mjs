import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptTwinPayload } = await import("../src/data/twinState.ts");
const generated = JSON.parse(await readFile(
  new URL("../src/generated/backend-demo-evidence.json", import.meta.url),
  "utf8",
));

function inputs(payload = structuredClone(generated)) {
  const historyOwners = Object.values(payload.historical_series).flatMap((series) =>
    series.points.map((point) => ({
      evidence_id: point.source_evidence_id,
      subject_id: series.subject_id,
    })),
  );
  return {
    payload,
    evidenceOwners: [...payload.evidence_records, ...historyOwners],
    episodeOwners: payload.position_episode_demo.entries.map((entry) => ({
      episodeId: entry.episode.episode_id,
      subjectId: entry.episode.subject_id,
      status: entry.episode.status,
    })),
  };
}

function adapt(source = inputs()) {
  return adaptTwinPayload(source.payload.twin, source.evidenceOwners, source.episodeOwners);
}

test("full replay-backed Twin reaches the Desktop with resolvable open Episodes", () => {
  const view = adapt();
  assert.equal(view.currentSnapshot.portfolioState.status, "available");
  assert.equal(view.currentSnapshot.episodes.open.length, 5);
  assert.equal(view.currentSnapshot.dataQuality.openEpisodeCount, 5);
  for (const episode of view.currentSnapshot.episodes.open) {
    assert.ok(episode.currentPositionState);
    assert.equal(episode.currentPositionStateRef, episode.currentPositionState.stateRef);
  }
});

test("closed Episode refs retain closed lifecycle semantics and route identity", () => {
  const source = inputs();
  const snapshot = source.payload.twin.current_snapshot;
  const episode = structuredClone(snapshot.episode_refs.open[0]);
  episode.status = "closed";
  episode.closed_at = snapshot.snapshot_at;
  episode.closing_execution_id = "execution-close";
  episode.current_position_state_ref = null;
  source.episodeOwners.find((item) => item.episodeId === episode.episode_id).status = "closed";
  snapshot.episode_refs.open = snapshot.episode_refs.open.slice(1);
  snapshot.episode_refs.closed = [episode];

  const closed = adapt(source).currentSnapshot.episodes.closed[0];
  assert.equal(closed.status, "closed");
  assert.equal(closed.closedAt, snapshot.snapshot_at);
  assert.equal(closed.currentPositionState, null);
  assert.ok(source.episodeOwners.some((item) => item.episodeId === closed.episodeId));
});

test("Evidence refs resolve only known same-subject Evidence", () => {
  const view = adapt();
  const source = inputs();
  const subject = view.currentSnapshot.subjectId;
  const owners = new Map(source.evidenceOwners.map((item) => [item.evidence_id, item.subject_id]));
  for (const reference of [...view.currentSnapshot.decisionEvidenceRefs, ...view.currentSnapshot.behaviorEvidenceRefs]) {
    assert.equal(owners.get(reference.evidenceId), subject);
  }

  const unknown = inputs();
  unknown.payload.twin.current_snapshot.decision_evidence_refs[0].evidence_id = "ev_unknown";
  assert.throws(() => adapt(unknown), /does not resolve to this subject/);

  const crossSubject = inputs();
  const id = crossSubject.payload.twin.current_snapshot.decision_evidence_refs[0].evidence_id;
  crossSubject.evidenceOwners.find((item) => item.evidence_id === id).subject_id = "another-subject";
  assert.throws(() => adapt(crossSubject), /does not resolve to this subject/);
});

test("insufficient and unavailable values remain explicit and never become zero", () => {
  const source = inputs();
  const snapshot = source.payload.twin.current_snapshot;
  snapshot.behavior_evidence_refs[0].evidence_status = "insufficient_evidence";
  snapshot.behavior_evidence_refs[0].evidence_reason = "More observations are required.";
  snapshot.behavior_state[0].evidence_status = "insufficient_evidence";
  snapshot.behavior_state[0].value = null;

  const view = adapt(source).currentSnapshot;
  assert.equal(view.behaviorEvidenceRefs[0].status, "insufficient_evidence");
  assert.equal(view.behaviorEvidenceRefs[0].reason, "More observations are required.");
  assert.equal(view.behaviorState[0].value, null);
  assert.notEqual(view.behaviorState[0].value, 0);
});

test("future capability refs remain empty and non-empty data fails closed in v1", () => {
  const source = inputs();
  const future = adapt(source).currentSnapshot.futureCapabilities;
  assert.deepEqual(future.selfBaselineRefs, []);
  assert.deepEqual(future.peerContextRefs, []);
  assert.deepEqual(future.notableChangeRefs, []);
  assert.equal(future.interventionHistoryRef, null);

  source.payload.twin.current_snapshot.peer_context_refs = ["peer-not-supported"];
  assert.throws(() => adapt(source), /unsupported future capability/);
});

test("malformed required Twin fields fail closed", () => {
  const missingVersion = inputs();
  delete missingVersion.payload.twin.current_snapshot.schema_version;
  assert.throws(() => adapt(missingVersion), /schema_version is required/);

  const badTimestamp = inputs();
  badTimestamp.payload.twin.current_snapshot.snapshot_at = "not-a-date";
  assert.throws(() => adapt(badTimestamp), /must be a timestamp/);
});

test("My Twin renders backend as-of, existing drill-down, and no financial formulas", async () => {
  const page = await readFile(new URL("../src/pages/MyTwinPage.tsx", import.meta.url), "utf8");
  const adapter = await readFile(new URL("../src/data/twinState.ts", import.meta.url), "utf8");
  assert.match(page, /currentSnapshot\.snapshotAt/);
  assert.match(page, /\/decisions\/episodes\/\$\{episode\.episodeId\}/);
  assert.match(page, /EvidenceExplainButton/);
  assert.equal(page.includes("historicalSnapshots"), false);
  assert.equal(page.includes("comparisons"), false);
  for (const forbidden of [/Math\.pow/, /percentileofscore/, /cum_returns/, /simple_returns/, /calculateHHI/i]) {
    assert.doesNotMatch(page, forbidden);
    assert.doesNotMatch(adapter, forbidden);
  }
});
