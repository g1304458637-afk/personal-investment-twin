import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const { adaptDemoInvestmentsCatalog, adaptInvestmentsPayload } = await import("../src/data/investments.ts");
const { adaptPositionEpisodeDemo } = await import("../src/data/positionEpisode.ts");
const generated = JSON.parse(await readFile(
  new URL("../src/generated/backend-demo-evidence.json", import.meta.url),
  "utf8",
));

function views() {
  return adaptPositionEpisodeDemo(structuredClone(generated.position_episode_demo));
}

test("generated investments maps authoritative open rows for one subject", () => {
  const view = adaptInvestmentsPayload(structuredClone(generated.investments), views());

  assert.equal(view.dataTier, "synthetic");
  assert.equal(view.portfolioState.status, "available");
  assert.equal(view.openEpisodes.length, 5);
  assert.equal(view.closedEpisodes.length, 0);
  assert.equal(view.primaryEpisodeId, null);
  assert.equal(view.openEpisodes[0].episodeId, "pe_460a70738da94f7dca7f03f18c47168c855a0f23bde32111af10e8d74612b9bf");
  assert.equal(view.summary.openEpisodeCount, 5);
  assert.equal(view.summary.closedEpisodeCount, 0);
  assert.equal(view.summary.currentPositionCount, 5);
  for (const episode of view.openEpisodes) {
    assert.equal(episode.subjectId, view.subjectId);
    assert.equal(episode.status, "open");
    assert.equal(typeof episode.quantity, "number");
    assert.equal(typeof episode.averageCost, "number");
    assert.equal(typeof episode.valuationPrice, "number");
    assert.equal(episode.isSynthetic, true);
  }
});

test("Demo catalog leads with the complex Product Demo rather than the behavior fixture", () => {
  const catalog = adaptDemoInvestmentsCatalog(views());
  const product = views().entries.find((entry) => entry.instrument.instrumentId === "SYN_PRODUCT");
  assert.equal(catalog.primaryEpisodeId, generated.position_episode_demo.default_episode_id);
  assert.equal(catalog.primaryEpisodeId, product.episode.episodeId);
  assert.equal(catalog.closedEpisodes[0].instrumentId, "SYN_PRODUCT");
  assert.equal(catalog.closedEpisodes[0].status, "closed");
  assert.notEqual(catalog.closedEpisodes[0].episodeId, "pe_460a70738da94f7dca7f03f18c47168c855a0f23bde32111af10e8d74612b9bf");
  assert.ok(catalog.openEpisodes.some((episode) => episode.episodeId === "pe_460a70738da94f7dca7f03f18c47168c855a0f23bde32111af10e8d74612b9bf"));
});

test("closed rows use explicit lifecycle status and are not borrowed into another subject", () => {
  const episodes = views();
  const closed = episodes.entries.find((entry) => entry.episode.status === "closed");
  assert.ok(closed);
  const payload = {
    subject_id: closed.episode.subjectId,
    as_of: closed.episode.closedAt,
    data_tier: "synthetic",
    portfolio_state_status: "available",
    portfolio_state_reason: null,
    summary: { open_episode_count: 0, closed_episode_count: 1, current_position_count: 0 },
    open_episode_ids: [],
    closed_episode_ids: [closed.episode.episodeId],
  };
  const view = adaptInvestmentsPayload(payload, episodes);

  assert.equal(view.closedEpisodes[0].status, "closed");
  assert.equal(view.closedEpisodes[0].closedAt, closed.episode.closedAt);
  assert.equal(view.closedEpisodes[0].quantity, null);
  assert.equal(view.openEpisodes.length, 0);
});

test("unknown, cross-subject, and status-mismatched Episode references fail closed", () => {
  const unknown = structuredClone(generated.investments);
  unknown.open_episode_ids[0] = "episode-not-present";
  assert.throws(() => adaptInvestmentsPayload(unknown, views()), /does not resolve/);

  const crossSubject = structuredClone(generated.investments);
  const foreign = views().entries.find((entry) => entry.episode.status === "closed");
  crossSubject.open_episode_ids[0] = foreign.episode.episodeId;
  assert.throws(() => adaptInvestmentsPayload(crossSubject, views()), /does not resolve/);

  const wrongCount = structuredClone(generated.investments);
  wrongCount.summary.open_episode_count = 99;
  assert.throws(() => adaptInvestmentsPayload(wrongCount, views()), /summary counts/);
});

test("empty and unavailable investments remain distinct presentation states", () => {
  const payload = {
    subject_id: generated.investments.subject_id,
    as_of: generated.investments.as_of,
    data_tier: "synthetic",
    portfolio_state_status: "unavailable",
    portfolio_state_reason: "Required prices are unavailable.",
    summary: { open_episode_count: 0, closed_episode_count: 0, current_position_count: 0 },
    open_episode_ids: [],
    closed_episode_ids: [],
  };
  const view = adaptInvestmentsPayload(payload, views());
  assert.equal(view.portfolioState.status, "unavailable");
  assert.equal(view.portfolioState.reason, "Required prices are unavailable.");
  assert.deepEqual(view.openEpisodes, []);
  assert.deepEqual(view.closedEpisodes, []);
});

test("Investments and Overview render backend view models without financial calculators", async () => {
  const page = await readFile(new URL("../src/pages/InvestmentsPage.tsx", import.meta.url), "utf8");
  const overview = await readFile(new URL("../src/pages/OverviewHomePage.tsx", import.meta.url), "utf8");
  const row = await readFile(new URL("../src/components/investments/FinancialObjectRow.tsx", import.meta.url), "utf8");
  const adapter = await readFile(new URL("../src/data/investments.ts", import.meta.url), "utf8");
  const source = `${page}\n${overview}\n${row}\n${adapter}`;

  assert.match(page, /view\.openEpisodes/);
  assert.match(page, /view\.closedEpisodes/);
  assert.match(page, /view\.primaryEpisodeId/);
  assert.match(page, /realUserApi\.investments/);
  assert.match(row, /to=\{`\/investments\/episodes\/\$\{episode\.episodeId\}`\}/);
  assert.match(row, /data-primary-demo/);
  assert.match(overview, /investments\.primaryEpisodeId/);
  assert.match(overview, /Primary Product Demo/);
  assert.equal(source.includes("@/demo/fixture"), false);
  assert.equal(source.includes("dangerouslySetInnerHTML"), false);
  for (const forbidden of [/calculate/i, /average\s*=/i, /marketValue\s*=/i, /reduce\s*\(/, /Math\./]) {
    assert.doesNotMatch(source, forbidden);
  }
});

test("Overview is a current-state entry point, not a module-card or attention-ranking dashboard", async () => {
  const overview = await readFile(new URL("../src/pages/OverviewHomePage.tsx", import.meta.url), "utf8");
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

  assert.match(app, /@\/pages\/OverviewHomePage/);
  assert.match(overview, /investments\.summary\.openEpisodeCount/);
  assert.match(overview, /to="\/twin"/);
  assert.match(overview, /to="\/pretrade"/);
  assert.doesNotMatch(overview, /decisionMetrics|behaviorMetrics|recentEvidence|PortfolioTrendChart|MetricRail|attentionScore|riskScore/);
  assert.doesNotMatch(overview, /SelfBaselineSection|historicalSnapshots|comparisons/);
});

test("Decision review retains Evidence but no longer owns the Episode browser", async () => {
  const decisions = await readFile(new URL("../src/pages/DecisionsPage.tsx", import.meta.url), "utf8");
  const episode = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  const row = await readFile(new URL("../src/components/review/EvidenceObservationRow.tsx", import.meta.url), "utf8");

  assert.match(decisions, /reviewView\.decisions/);
  assert.match(row, /EvidenceExplainButton/);
  assert.doesNotMatch(decisions, /positionEpisodeDemo\.entries/);
  assert.match(decisions, /to="\/investments"/);
  assert.match(episode, /to="\/investments"/);
  assert.match(episode, /getPositionEpisodeById/);
});
