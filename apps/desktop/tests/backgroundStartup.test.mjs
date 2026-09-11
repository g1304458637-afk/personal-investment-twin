import assert from "node:assert/strict";
import test from "node:test";
import { readFile, stat } from "node:fs/promises";
import { initializeWorkspaceAppearance } from "../src/workspace/workspaceMode.ts";
import { applyTheme, resolveTheme } from "../src/lib/theme.ts";

const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("startup and React share the existing light/dark URL preference", () => {
  for (const [search, expected] of [["", "dark"], ["?theme=light", "light"], ["?theme=dark", "dark"], ["?theme=unknown", "dark"]]) {
    const classes = new Set(["dark"]);
    const root = { dataset: {}, classList: { toggle: (key, on) => on ? classes.add(key) : classes.delete(key) } };
    const theme = resolveTheme(search);
    applyTheme(root, theme);
    assert.equal(theme, expected);
    assert.equal(root.dataset.theme, expected);
    assert.equal(classes.has("dark"), expected === "dark");
  }
});

test("modern appearance is synchronous and retired classic links stay modern", () => {
  for (const search of ["", "?theme=light", "?workspace=unknown", "?workspace=intelligence"]) {
    const root = { dataset: {} };
    initializeWorkspaceAppearance(root, search);
    assert.equal(root.dataset.workspace, "intelligence");
    initializeWorkspaceAppearance(root, search);
    assert.equal(root.dataset.workspace, "intelligence");
  }
  const root = { dataset: { workspace: "intelligence", theme: "light" } };
  initializeWorkspaceAppearance(root, "?workspace=classic&theme=light");
  assert.deepEqual(root.dataset, { workspace: "intelligence", theme: "light" });
});

test("appearance is applied before React; shell unmount cannot briefly remove it", async () => {
  const main = await source("src/main.tsx");
  assert.ok(main.indexOf("initializeWorkspaceAppearance(document") < main.indexOf("createRoot(root)"));
  assert.ok(main.indexOf("applyTheme(document") < main.indexOf("createRoot(root)"));
  assert.ok(main.indexOf('import "./index.css"') < main.indexOf('import "./workspace/liquid-workspace.css"'));
  const shell = await source("src/workspace/IntelligenceShell.tsx");
  assert.doesNotMatch(shell, /dataset.workspace/);
});

test("local first frame is preloaded, compact and retained independently of video state", async () => {
  const html = await source("index.html");
  assert.match(html, /rel="preload" as="image" href="\/src\/assets\/liquid-backdrop-poster.jpg" fetchpriority="high"/);
  const poster = await stat(new URL("../src/assets/liquid-backdrop-poster.jpg", import.meta.url));
  assert.ok(poster.size > 1000 && poster.size < 120000);
  const component = await source("src/workspace/LiquidBackdrop.tsx");
  assert.match(component, /import liquidPoster from "@\/assets\/liquid-backdrop-poster.jpg"/);
  assert.match(component, /<img className="lg-backdrop-poster" src=\{liquidPoster\} alt="" fetchPriority="high"/);
  assert.ok(component.indexOf('<img className="lg-backdrop-poster"') < component.indexOf("{!failed && <video"));
  assert.match(component, /poster=\{liquidPoster\}/);
});

test("only playing reveals video; decode reset and error retain a static fallback", async () => {
  const component = await source("src/workspace/LiquidBackdrop.tsx");
  assert.match(component, /\[ready, setReady\] = useState\(false\)/);
  assert.match(component, /onPlaying=\{\(\) => setReady\(true\)\}/);
  assert.match(component, /onEmptied=\{\(\) => setReady\(false\)\}/);
  assert.match(component, /preload=\{paused \? "none" : "auto"\}/);
  assert.match(component, /!disposed && currentAttempt === attempt/);
  assert.match(component, /\}, \[paused, failed\]\)/);
  const css = await source("src/workspace/liquid-workspace.css");
  assert.match(css, /\.lg-backdrop video \{ opacity:0; transition:opacity/);
  assert.match(css, /\.lg-backdrop video.is-ready \{ opacity:1;/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\) \{ \.lg-backdrop video \{ transition:none;/);
  assert.match(css, /\.lg-backdrop-poster,\.lg-backdrop video \{[^}]*object-position:62% center/);
});
