import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { sourceWebUrl, openDesktopSource } from "../src/data/externalLinks.ts";

test("sources permit web URLs, not executable, file or credential-bearing URLs", () => {
  assert.equal(sourceWebUrl("https://example.com/article?x=1&y=2#report"), "https://example.com/article?x=1&y=2#report");
  for (const value of ["javascript:alert(1)", "file:///etc/passwd", "data:text/plain,x", "//example.com", "https://user:pass@example.com", "https://example.com/\n", "https://example.com/" + "x".repeat(8192)]) assert.equal(sourceWebUrl(value), null);
});
test("desktop sends the exact article URL to the narrow native opener", async () => {
  const calls = [];
  await openDesktopSource("https://example.com/article?x=1#section", async (...args) => calls.push(args));
  assert.deepEqual(calls, [["open_source_url", {url:"https://example.com/article?x=1#section"}]]);
  await assert.rejects(openDesktopSource("file:///tmp/test", async () => assert.fail("must not invoke")));
  await assert.rejects(openDesktopSource("https://example.com", async () => { throw Error("failed"); }));
});
test("source component keeps web fallback and visible failure recovery", async () => {
  const source = await readFile(new URL("../src/components/common/SourceLink.tsx", import.meta.url), "utf8");
  assert.match(source, /event.preventDefault\(\)/);
  assert.match(source, /openDesktopSource\(href\)/);
  assert.match(source, /role="alert"/);
  assert.match(source, /input readOnly/);
  assert.match(source, /noopener noreferrer/);
  const workspace = await readFile(new URL("../src/workspace/AgentWorkspace.tsx", import.meta.url), "utf8");
  assert.match(workspace, /<SourceLink url=\{source.url\}/);
});
