import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { historyWorkspaceAvailability } from "../src/workspace/historyWorkspaceScope.ts";

const study = {
  subjectId: "demo-user:synthetic-behavior",
  accountId: "demo-account:behavior",
  asOf: "2025-01-08T23:59:00",
  historyMetricIds: ["portfolio_concentration_hhi", "mean_daily_turnover"],
};
const generated = JSON.parse(await readFile(new URL("../src/generated/backend-demo-evidence.json", import.meta.url), "utf8"));

test("history workspace opens only for the registered synthetic study", () => {
  assert.equal(historyWorkspaceAvailability({ mode: "demo", subjectId: study.subjectId, accountId: study.accountId }, study), "ready");
  assert.equal(historyWorkspaceAvailability({ mode: "demo", subjectId: "demo-user:another", accountId: study.accountId }, study), "dataset_mismatch");
  assert.equal(historyWorkspaceAvailability({ mode: "demo", subjectId: study.subjectId, accountId: "demo-account:another" }, study), "dataset_mismatch");
  assert.equal(historyWorkspaceAvailability({ mode: "demo", subjectId: null, accountId: null }, study), "dataset_mismatch");
});

test("real accounts never fall back to the deterministic study", () => {
  assert.equal(historyWorkspaceAvailability({ mode: "real_user", subjectId: study.subjectId, accountId: study.accountId }, study), "real_unavailable");
  assert.equal(historyWorkspaceAvailability({ mode: "real_user", subjectId: "real-subject", accountId: "real-account" }, study), "real_unavailable");
});

test("registered peer and behavior sources belong to the Twin subject and retain their observation scope", () => {
  const subjectId = generated.twin.current_snapshot.subject_id;
  const asOf = generated.twin.current_snapshot.snapshot_at;
  const behaviorIds = new Set([
    "portfolio_concentration_hhi", "mean_daily_turnover", "disposition_effect", "loss_averaging_event_rate",
  ]);
  const behavior = generated.evidence_records.filter((item) => behaviorIds.has(item.metric_id));
  assert.equal(behavior.length, 4);
  assert.ok(behavior.every((item) => item.subject_id === subjectId));
  const peerMetrics = Object.values(generated.peer_benchmark.metrics);
  assert.equal(peerMetrics.length, 3);
  assert.ok(peerMetrics.every((metric) => (
    metric.subject_id === subjectId
    && metric.metric_n > 0
    && metric.observation_start <= metric.observation_end
    && metric.observation_end <= asOf
  )));
});

test("workspace adapter keeps registered history references and a visible independent-study path", async () => {
  const adapter = await readFile(new URL("../src/workspace/historyWorkspaceData.ts", import.meta.url), "utf8");
  const page = await readFile(new URL("../src/workspace/HistoryWorkspace.tsx", import.meta.url), "utf8");
  assert.match(adapter, /portfolio_concentration_hhi/);
  assert.match(adapter, /mean_daily_turnover/);
  assert.match(adapter, /History study must have exactly one registered account/);
  assert.match(adapter, /historyWorkspaceAvailability\(scope, study\)/);
  assert.match(page, /c\.openStudy/);
  assert.match(page, /setExampleAccount\(registeredExample\)/);
  assert.doesNotMatch(page, /workspace=classic/);
  assert.match(page, /PeerRangeChart metric=\{metric\.chartMetric\}/);
  assert.doesNotMatch(adapter, /setMode\(|localStorage|Math\.pow|Math\.sqrt/);
});
