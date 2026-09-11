import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { agentChatCopy } from "../src/workspace/agentChatCopy.ts";

test("capability bar lives outside the transcript and empty-state conditional", async () => {
  const page = await readFile(new URL("../src/workspace/AgentWorkspace.tsx", import.meta.url), "utf8");
  const start = page.indexOf('<div className="agent-chat__capabilities"');
  const end = page.indexOf('<form className="agent-chat__composer"');
  assert.ok(start > page.indexOf("{turns.map(turn"));
  assert.ok(end > start);
  const bar = page.slice(start, end);
  assert.doesNotMatch(bar, /!turns.length|isAccountScope/);
  assert.match(bar, /aria-expanded=/);
  assert.match(bar, /setActiveEntry/);
  assert.match(bar, /setDraft\(question\)/);
  assert.match(bar, /focus\(\{ preventScroll: true \}\)/);
  assert.doesNotMatch(bar, /submit\(|newChat\(|update\(|setConsent\(|runChatTurn\(/);
  assert.match(bar, /disabled=\{busy\}/);
});

test("both locales provide scoped examples without claiming search is required for quotes", () => {
  for (const locale of ["zh-CN", "en-US"]) {
    const copy = agentChatCopy[locale];
  assert.equal(copy.entries.length, 6);
  assert.deepEqual(copy.entries.map(item => item.id), ["analyze", "compare", "scenario", "research", "learn", "chart"]);
    for (const id of ["research", "learn", "chart"]) {
      assert.ok(copy.suggestions[id].length >= 2);
      assert.ok(copy.suggestions[id].every(text => text.length > 0 && text.length < 2000));
    }
    assert.equal(copy.accountPrompts.length, 4);
    assert.equal(copy.episodePrompts.length, 3);
  }
  assert.match(agentChatCopy["zh-CN"].searchNeeded, /行情查询不受/);
});

test("capabilities do not scroll away with the transcript and support narrow screens", async () => {
  const css = await readFile(new URL("../src/workspace/agent-chat.css", import.meta.url), "utf8");
  assert.match(css, /\.agent-chat__capabilities\s*\{ flex: 0 0 auto/);
  assert.match(css, /\.agent-chat__capability-examples\s*\{[^}]*max-height: 180px; overflow-y: auto/);
  assert.match(css, /\.agent-chat__capability-bar \{ display: grid; grid-template-columns: 1fr 1fr/);
});
