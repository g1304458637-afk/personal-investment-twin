import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const modulePath = (stem) => [stem, `${stem}.ts`, `${stem}.tsx`, `${stem}.json`, resolve(stem, "index.ts")].find(existsSync);

// Exercise the actual adapter module with its Vite-style aliases and generated JSON,
// instead of duplicating its registry check in a source-text assertion.
registerHooks({
  resolve(specifier, context, nextResolve) {
    const stem = specifier.startsWith("@/")
      ? resolve(root, "src", specifier.slice(2))
      : specifier.startsWith(".") && context.parentURL?.startsWith("file:")
        ? resolve(dirname(fileURLToPath(context.parentURL)), specifier)
        : null;
    const path = stem && modulePath(stem);
    return path ? nextResolve(pathToFileURL(path).href, context) : nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".json")) {
      return { format: "module", source: `export default ${readFileSync(fileURLToPath(url), "utf8")}`, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const { historyWorkspaceData, registeredHistoryStudy } = await import("../src/workspace/historyWorkspaceData.ts");
const generated = (await import("../src/generated/showcase-demo.json")).default;

const scope = {
  mode: "demo",
  subjectId: generated.showcase.subject_id,
  accountId: generated.showcase.account_id,
};

test("current showcase history is ready with explicitly unavailable peer statistics", () => {
  const data = historyWorkspaceData(scope);
  assert.equal(data.availability, "ready");
  assert.ok(data.history && data.selfBaseline);
  assert.equal(data.peer, null);
});

test("history registry rejects a peer source with another subject", () => {
  const metric = generated.peer_benchmark.metrics.portfolio_hhi;
  const original = metric.subject_id;
  try {
    metric.subject_id = "SYN_STUDY_SHOWCASE_REFERENCE";
    assert.throws(registeredHistoryStudy, /source references are not registered/);
  } finally {
    metric.subject_id = original;
  }
});

test("history registry rejects a malformed complete peer metric with zero observations", () => {
  const metric = generated.peer_benchmark.metrics.portfolio_hhi;
  const original = metric.benchmark_status;
  try {
    metric.benchmark_status = "complete";
    assert.throws(registeredHistoryStudy, /source references are not registered/);
  } finally {
    metric.benchmark_status = original;
  }
});
