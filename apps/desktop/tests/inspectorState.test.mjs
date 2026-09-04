import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const {
  isSafeInspectorTargetId,
  parseInspectorState,
  withInspectorState,
  withoutInspectorState,
} = await import("../src/components/inspector/inspectorState.ts");

const evidenceId = `ev_${"a".repeat(64)}`;

test("allowlisted Evidence inspector state parses from semantic URL data", () => {
  assert.deepEqual(parseInspectorState(`?inspect=evidence&id=${evidenceId}`), {
    type: "evidence",
    targetId: evidenceId,
  });
  assert.equal(isSafeInspectorTargetId("portfolio_concentration_hhi"), true);
});

test("unknown inspector types and raw payload-like ids fail closed", () => {
  assert.equal(parseInspectorState(`?inspect=shell&id=${evidenceId}&action=run`), null);
  assert.equal(parseInspectorState("?action=run&command=python"), null);
  assert.equal(parseInspectorState("?inspect=evidence&id=%7B%22holdings%22%3A%5B1%5D%7D"), null);
  assert.equal(parseInspectorState("?inspect=evidence&id=../../account.json"), null);
});

test("opening and closing inspector state preserves unrelated semantic page state", () => {
  const opened = withInspectorState("?window=all", { type: "evidence", targetId: evidenceId });
  assert.deepEqual(parseInspectorState(opened), { type: "evidence", targetId: evidenceId });
  assert.equal(new URLSearchParams(opened).get("window"), "all");
  const closed = withoutInspectorState(opened);
  assert.equal(parseInspectorState(closed), null);
  assert.equal(new URLSearchParams(closed).get("window"), "all");
});

test("back and forward URL representations restore the same inspector deterministically", () => {
  const base = "?window=12m";
  const opened = withInspectorState(base, { type: "evidence", targetId: evidenceId });
  assert.equal(parseInspectorState(base), null);
  assert.deepEqual(parseInspectorState(opened), parseInspectorState(opened));
  assert.equal(parseInspectorState(withoutInspectorState(opened)), null);
});

test("Evidence buttons use the shell-level host rather than local open state", async () => {
  const inspector = await readFile(new URL("../src/components/evidence/EvidenceInspector.tsx", import.meta.url), "utf8");
  const shell = await readFile(new URL("../src/components/layout/WorkspaceShell.tsx", import.meta.url), "utf8");
  assert.match(inspector, /openEvidence\(view, context\)/);
  assert.doesNotMatch(inspector, /useState\(false\)/);
  assert.match(shell, /InspectorProvider/);
  assert.match(shell, /ContextualInspectorHost/);
});
