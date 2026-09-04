import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("real-user transport uses the allowlisted runtime and never generated JSON", async () => {
  const service = await readFile(new URL("../src/data/runtimeService.ts", import.meta.url), "utf8");
  const investments = await readFile(new URL("../src/pages/InvestmentsPage.tsx", import.meta.url), "utf8");
  const episode = await readFile(new URL("../src/pages/PositionEpisodePage.tsx", import.meta.url), "utf8");
  assert.match(service, /runtime_product_request/);
  assert.doesNotMatch(service, /backend-demo-evidence/);
  assert.match(investments, /realUserApi\.investments/);
  assert.match(episode, /realUserApi\.episode/);
  assert.match(episode, /data\.mode === "demo"/);
  assert.match(episode, /adaptRuntimePositionEpisodeEntry/);
});

test("data import uses native CSV dialog and exposes no shell or SQL API", async () => {
  const service = await readFile(new URL("../src/data/runtimeService.ts", import.meta.url), "utf8");
  assert.match(service, /@tauri-apps\/plugin-dialog/);
  assert.match(service, /extensions: \["csv"\]/);
  assert.doesNotMatch(service, /plugin-shell|Command\.create|sql/i);
});

test("Episode market and cost series are unsmoothed, gapped, and zoomable", async () => {
  const price = await readFile(new URL("../src/components/charts/PositionEpisodeTimeline.tsx", import.meta.url), "utf8");
  const quantity = await readFile(new URL("../src/components/charts/PositionQuantityTimeline.tsx", import.meta.url), "utf8");
  const axis = await readFile(new URL("../src/components/charts/dailyTimeAxis.ts", import.meta.url), "utf8");
  assert.doesNotMatch(price, /smooth:\s*0\./);
  assert.match(price, /smooth:\s*false/);
  assert.match(price, /connectNulls:\s*false/);
  assert.match(price, /type:\s*"cross"/);
  assert.match(axis, /type: "inside"/);
  assert.match(axis, /minValueSpan,/);
  assert.match(quantity, /smooth:\s*false/);
  assert.match(quantity, /connectNulls:\s*false/);
  assert.match(quantity, /dailyDataZoom/);
});
