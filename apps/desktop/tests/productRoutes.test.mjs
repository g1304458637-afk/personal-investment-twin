import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const {
  PRODUCT_ROUTE_IDS,
  activeNavigationGroup,
  activeNavigationRouteId,
  activeRouteId,
  getSidebarNavigation,
  legacyRoutePaths,
  pageTitleKey,
  productRoutes,
  resolveLegacyRedirect,
} = await import("../src/routing/productRoutes.ts");

test("product route ids and canonical paths are unique", () => {
  assert.equal(new Set(PRODUCT_ROUTE_IDS).size, PRODUCT_ROUTE_IDS.length);
  assert.equal(new Set(productRoutes.map((route) => route.id)).size, productRoutes.length);
  assert.equal(new Set(productRoutes.map((route) => route.path)).size, productRoutes.length);
});

test("legacy routes are unique, deterministic, and cycle free", () => {
  const legacy = legacyRoutePaths();
  assert.equal(new Set(legacy).size, legacy.length);
  for (const path of legacy.filter((item) => !item.includes(":"))) {
    const target = resolveLegacyRedirect(path);
    assert.ok(target);
    assert.notEqual(target, path);
    assert.equal(resolveLegacyRedirect(target), null);
  }
});

test("legacy product URLs resolve to the confirmed Phase 1 routes", () => {
  assert.equal(resolveLegacyRedirect("/my-twin"), "/twin");
  assert.equal(resolveLegacyRedirect("/behavior"), "/review/patterns");
  assert.equal(resolveLegacyRedirect("/decision-check"), "/pretrade");
  assert.equal(resolveLegacyRedirect("/evidence"), "/advanced/evidence");
  assert.equal(resolveLegacyRedirect("/compare"), "/twin");
  assert.equal(resolveLegacyRedirect("/decisions"), "/review/decisions");
  assert.equal(
    resolveLegacyRedirect("/decisions/episodes/episode_123"),
    "/investments/episodes/episode_123",
  );
});

test("primary sidebar derives only ready routes from metadata", () => {
  const entries = getSidebarNavigation();
  const ids = entries.flatMap((entry) =>
    entry.type === "route" ? [entry.route.id] : entry.children.map((child) => child.id),
  );
  assert.deepEqual(ids, ["overview", "review_decisions", "review_patterns", "twin", "pretrade", "settings"]);
  assert.equal(ids.includes("advanced_evidence"), false);
  assert.equal(ids.includes("investments"), false);
  assert.equal(ids.includes("data_accounts"), false);
  assert.equal(entries.some((entry) => entry.type === "group" && entry.id === "review"), true);
});

test("review children, titles, and active state share route metadata", () => {
  assert.equal(activeNavigationGroup("/review/decisions"), "review");
  assert.equal(activeNavigationGroup("/review/patterns"), "review");
  assert.equal(activeRouteId("/review/decisions"), "review_decisions");
  assert.equal(activeRouteId("/investments/episodes/episode_123"), "investment_episode");
  assert.equal(activeNavigationRouteId("/investments/episodes/episode_123"), "investments");
  assert.equal(pageTitleKey("/pretrade"), "Trade impact check");
  assert.equal(pageTitleKey("/advanced/evidence"), "Evidence & Methods");
});

test("App, Sidebar, and Command Palette consume the metadata source", async () => {
  const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const navigation = await readFile(new URL("../src/components/layout/navigation.ts", import.meta.url), "utf8");
  const palette = await readFile(new URL("../src/components/layout/CommandPalette.tsx", import.meta.url), "utf8");
  const shell = await readFile(new URL("../src/components/layout/WorkspaceShell.tsx", import.meta.url), "utf8");
  assert.match(app, /productRoutes\.map/);
  assert.match(navigation, /getSidebarNavigation\(\)/);
  assert.match(palette, /commandNavigationItems/);
  assert.match(shell, /pageTitleKey\(location\.pathname\)/);
  assert.match(shell, /AgentPanel/);
  assert.match(shell, /Ask Twin/);
});
