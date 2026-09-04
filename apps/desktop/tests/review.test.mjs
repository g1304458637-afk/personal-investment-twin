import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { buildReviewView } = await import("../src/data/review.ts");

function metric(id, index, status = "complete") {
  return {
    id,
    label: `technical-${id}`,
    eyebrow: `technical-context-${id}`,
    primary: `backend-result-${id}`,
    description: `backend-description-${id}`,
    observationCount: index,
    status,
    confidence: null,
    evidenceId: `ev_${id}`,
    trend: [],
  };
}

const decisionMetrics = [
  metric("friction", 4),
  metric("exit", 3),
  metric("selection", 1),
  metric("sizing", 2),
];
const behaviorMetrics = [
  metric("loss-averaging", 8),
  metric("disposition", 7, "experimental"),
  metric("turnover", 6),
  metric("hhi", 5),
];
const evidenceRecords = [...decisionMetrics, ...behaviorMetrics].map((item) => ({
  evidence_id: item.evidenceId,
  subject_id: "subject-1",
}));
const explainability = { evidenceViews: [] };

function build(overrides = {}) {
  return buildReviewView({
    decisionMetrics,
    behaviorMetrics,
    evidenceRecords,
    explainability,
    episodes: [],
    ...overrides,
  });
}

test("Review view uses stable product taxonomy and keeps friction outside decision categories", () => {
  const view = build();
  assert.deepEqual(view.decisions.map((item) => item.id), ["selection", "sizing", "exit"]);
  assert.deepEqual(view.execution.map((item) => item.id), ["friction"]);
  assert.deepEqual(view.patterns.map((item) => item.id), ["hhi", "turnover", "disposition", "loss-averaging"]);
  assert.equal(view.dataTier, "synthetic");
  assert.equal(view.execution[0].group, "execution");
});

test("Review observations copy backend status, result, and N without recalculation", () => {
  const view = build();
  const observations = [...view.decisions, ...view.execution, ...view.patterns];
  for (const observation of observations) {
    const source = [...decisionMetrics, ...behaviorMetrics].find((candidate) => candidate.id === observation.id);
    assert.ok(source);
    assert.equal(observation.status, source.status);
    assert.equal(observation.primary, source.primary);
    assert.equal(observation.description, source.description);
    assert.equal(observation.observationCount, source.observationCount);
  }
  assert.equal(view.patterns[0].titleKey, "Portfolio concentration");
  assert.equal(view.patterns[1].titleKey, "Turnover intensity");
  assert.equal(view.patterns[2].titleKey, "Sale outcome observation");
  assert.equal(view.patterns[3].titleKey, "Loss-state addition observation");
});

test("missing Evidence fails closed as unavailable without a fabricated result", () => {
  const view = build({
    evidenceRecords: evidenceRecords.filter((record) => record.evidence_id !== "ev_selection"),
  });
  assert.equal(view.decisions[0].status, "unavailable");
  assert.equal(view.decisions[0].primary, "Evidence unavailable");
  assert.equal(view.decisions[0].evidenceId, null);
  assert.equal(view.decisions[0].explainability, null);
  assert.equal(view.decisions[0].episodeId, null);
});

test("Episode linkage requires an explicit same-subject Evidence reference", () => {
  const explicitReference = {
    episode: { episodeId: "episode-1", subjectId: "subject-1" },
    evidenceReferences: [{ evidenceId: "ev_selection" }],
  };
  assert.equal(build({ episodes: [explicitReference] }).decisions[0].episodeId, "episode-1");

  const crossSubject = structuredClone(explicitReference);
  crossSubject.episode.subjectId = "subject-2";
  assert.equal(build({ episodes: [crossSubject] }).decisions[0].episodeId, null);

  const noReference = structuredClone(explicitReference);
  noReference.evidenceReferences = [];
  assert.equal(build({ episodes: [noReference] }).decisions[0].episodeId, null);
});

test("Review landing explains both domains and links to their canonical routes", async () => {
  const page = await readFile(new URL("../src/pages/ReviewPage.tsx", import.meta.url), "utf8");
  assert.match(page, /to="\/review\/decisions"/);
  assert.match(page, /to="\/review\/patterns"/);
  assert.match(page, /to="\/investments"/);
  assert.match(page, /Decision Event/);
  assert.match(page, /reviewView\.decisions/);
  assert.match(page, /reviewView\.patterns/);
  assert.doesNotMatch(page, /reviewScore|attentionScore|riskScore|ranking/i);
});

test("Decision and pattern pages use the shell Evidence Inspector and no local Sheet", async () => {
  const decisions = await readFile(new URL("../src/pages/DecisionsPage.tsx", import.meta.url), "utf8");
  const patterns = await readFile(new URL("../src/pages/BehaviorPage.tsx", import.meta.url), "utf8");
  const row = await readFile(new URL("../src/components/review/EvidenceObservationRow.tsx", import.meta.url), "utf8");
  const source = `${decisions}\n${patterns}\n${row}`;

  assert.match(row, /EvidenceExplainButton/);
  assert.doesNotMatch(decisions, /positionEpisodeDemo\.entries/);
  assert.doesNotMatch(decisions, /Sheet|EvidenceInspector\s*\(/);
  assert.doesNotMatch(patterns, /Sheet|EvidenceInspector\s*\(/);
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/);
});

test("Investment patterns retain real history without personality or Self calculations", async () => {
  const patterns = await readFile(new URL("../src/pages/BehaviorPage.tsx", import.meta.url), "utf8");
  const adapter = await readFile(new URL("../src/data/review.ts", import.meta.url), "utf8");
  const row = await readFile(new URL("../src/components/review/EvidenceObservationRow.tsx", import.meta.url), "utf8");
  const source = `${patterns}\n${adapter}\n${row}`;

  assert.match(patterns, /behaviorHistory\.hhi/);
  assert.match(patterns, /behaviorHistory\.turnover/);
  assert.match(patterns, /to="\/twin"/);
  assert.doesNotMatch(source, /Math\.|\.reduce\s*\(|calculate[A-Z]|SelfBaselineSection|percentileofscore/i);
  assert.doesNotMatch(source, /aggressive investor|fearful investor|disciplined investor/i);
  assert.doesNotMatch(row, /text-(green|red)|positive.*className|negative.*className/i);
});

test("backend adapter exposes Review from deterministic Evidence views", async () => {
  const backendSource = await readFile(new URL("../src/data/backendEvidence.ts", import.meta.url), "utf8");
  assert.match(backendSource, /buildReviewView\(\{/);
  assert.match(backendSource, /decisionMetrics,/);
  assert.match(backendSource, /behaviorMetrics,/);
  assert.match(backendSource, /evidenceRecords,/);
  assert.match(backendSource, /episodes: positionEpisodeDemo\.entries/);
});
