import assert from "node:assert/strict";
import test from "node:test";
import { agentTurnPhase, agentTurnStatusContent, safeDiagnosticId } from "../src/workspace/agentTurnStatusModel.ts";

test("maps every reported working phase to a user-facing status", () => {
  for (const phase of ["researching", "reading", "searching", "quoting", "writing", "checking"]) {
    const status = agentTurnStatusContent({ status: "running", phase }, "en");
    assert.equal(status.kind, "running");
    assert.ok(status.title.length > 0);
    assert.ok(status.detail.length > 0);
    assert.equal(agentTurnPhase(phase), phase);
  }
});

test("unknown or missing phases use a safe working fallback", () => {
  assert.equal(agentTurnPhase("internal_reasoning"), undefined);
  assert.deepEqual(agentTurnStatusContent({ status: "running", phase: "internal_reasoning" }, "en"), {
    kind: "running", title: "Working on your request", detail: "Preparing an answer that can be checked.",
  });
  assert.equal(agentTurnStatusContent({ status: "running" }, "zh").title, "正在处理请求");
});

test("failure categories use the existing safe public error copy", () => {
  const timeout = agentTurnStatusContent({ status: "failed", reason: "account_model_timeout" }, "en");
  assert.equal(timeout.detail, "This analysis timed out. Please retry shortly.");
  const grounding = agentTurnStatusContent({ status: "failed", reason: "account_grounding_failed" }, "zh");
  assert.match(grounding.detail, /一致性核对/);
  assert.match(agentTurnStatusContent({ status: "failed", reason: "unknown_backend_code" }, "en").detail, /did not complete/);
});

test("stopped and diagnostic states do not expose unsanitized backend values", () => {
  assert.match(agentTurnStatusContent({ status: "stopped" }, "en").detail, /Retry this answer/);
  assert.equal(safeDiagnosticId("ab12cd34ef56"), "ab12cd34ef56");
  assert.equal(safeDiagnosticId("trace: ab12cd34ef56"), undefined);
  assert.equal(agentTurnStatusContent({ status: "failed", diagnosticId: "not-safe" }, "en").diagnosticId, undefined);
});
