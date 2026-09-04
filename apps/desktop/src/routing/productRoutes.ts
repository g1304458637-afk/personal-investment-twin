import type { LocaleMessage } from "@/locales/en-US";

export const PRODUCT_ROUTE_IDS = [
  "overview",
  "investments",
  "review",
  "review_decisions",
  "review_patterns",
  "twin",
  "pretrade",
  "data_accounts",
  "settings",
  "advanced_evidence",
  "investment_episode",
] as const;

export type ProductRouteId = (typeof PRODUCT_ROUTE_IDS)[number];
export type RouteAvailability = "available" | "hidden_until_ready" | "advanced";
export type NavigationSection = "work" | "manage";
export type NavigationGroupId = "review";
export type ProductIconKey =
  | "overview"
  | "investments"
  | "review"
  | "twin"
  | "pretrade"
  | "data"
  | "settings"
  | "evidence"
  | "episode";

export interface ProductRouteDefinition {
  readonly id: ProductRouteId;
  readonly path: string;
  readonly legacyPaths: readonly string[];
  readonly labelKey: LocaleMessage;
  readonly pageTitleKey: LocaleMessage;
  readonly descriptionKey: LocaleMessage;
  readonly icon: ProductIconKey;
  readonly navigationSection: NavigationSection | null;
  readonly navigationGroup: NavigationGroupId | null;
  readonly navigationOrder: number;
  readonly showInSidebar: boolean;
  readonly availability: RouteAvailability;
  readonly parentId: ProductRouteId | null;
  readonly inspectorPolicy: "supported" | "none";
}

export interface ProductNavigationRoute {
  readonly type: "route";
  readonly route: ProductRouteDefinition;
}

export interface ProductNavigationGroup {
  readonly type: "group";
  readonly id: NavigationGroupId;
  readonly labelKey: LocaleMessage;
  readonly icon: ProductIconKey;
  readonly navigationSection: NavigationSection;
  readonly navigationOrder: number;
  readonly route: ProductRouteDefinition;
  readonly children: readonly ProductRouteDefinition[];
}

export type ProductNavigationEntry = ProductNavigationRoute | ProductNavigationGroup;

const route = (definition: ProductRouteDefinition) => definition;

export const productRoutes: readonly ProductRouteDefinition[] = [
  route({
    id: "overview",
    path: "/overview",
    legacyPaths: [],
    labelKey: "Overview",
    pageTitleKey: "Overview",
    descriptionKey: "Portfolio and evidence at a glance",
    icon: "overview",
    navigationSection: "work",
    navigationGroup: null,
    navigationOrder: 0,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "investments",
    path: "/investments",
    legacyPaths: [],
    labelKey: "My Investments",
    pageTitleKey: "My Investments",
    descriptionKey: "Positions and investment episodes",
    icon: "investments",
    navigationSection: "work",
    navigationGroup: null,
    navigationOrder: 10,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "review",
    path: "/review",
    legacyPaths: [],
    labelKey: "Review",
    pageTitleKey: "Review",
    descriptionKey: "Review decisions and observable investment patterns",
    icon: "review",
    navigationSection: "work",
    navigationGroup: "review",
    navigationOrder: 20,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "review_decisions",
    path: "/review/decisions",
    legacyPaths: ["/decisions"],
    labelKey: "Decision",
    pageTitleKey: "Decision review",
    descriptionKey: "Selection, sizing, exit and friction evidence",
    icon: "review",
    navigationSection: "work",
    navigationGroup: "review",
    navigationOrder: 21,
    showInSidebar: true,
    availability: "available",
    parentId: "review",
    inspectorPolicy: "supported",
  }),
  route({
    id: "review_patterns",
    path: "/review/patterns",
    legacyPaths: ["/behavior"],
    labelKey: "Investment patterns",
    pageTitleKey: "Investment patterns",
    descriptionKey: "Descriptive portfolio behavior evidence",
    icon: "review",
    navigationSection: "work",
    navigationGroup: "review",
    navigationOrder: 22,
    showInSidebar: true,
    availability: "available",
    parentId: "review",
    inspectorPolicy: "supported",
  }),
  route({
    id: "twin",
    path: "/twin",
    legacyPaths: ["/my-twin", "/compare"],
    labelKey: "My Twin",
    pageTitleKey: "My Twin",
    descriptionKey: "Demo twin snapshots over time",
    icon: "twin",
    navigationSection: "work",
    navigationGroup: null,
    navigationOrder: 30,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "pretrade",
    path: "/pretrade",
    legacyPaths: ["/decision-check"],
    labelKey: "Pre-decision",
    pageTitleKey: "Trade impact check",
    descriptionKey: "Pre-decision evidence context preview",
    icon: "pretrade",
    navigationSection: "work",
    navigationGroup: null,
    navigationOrder: 40,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "data_accounts",
    path: "/data",
    legacyPaths: [],
    labelKey: "Data & Accounts",
    pageTitleKey: "Data & Accounts",
    descriptionKey: "Accounts, imports, data quality and consent",
    icon: "data",
    navigationSection: "manage",
    navigationGroup: null,
    navigationOrder: 90,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "settings",
    path: "/settings",
    legacyPaths: [],
    labelKey: "Settings",
    pageTitleKey: "Settings",
    descriptionKey: "Appearance, privacy and permissions UI",
    icon: "settings",
    navigationSection: "manage",
    navigationGroup: null,
    navigationOrder: 100,
    showInSidebar: true,
    availability: "available",
    parentId: null,
    inspectorPolicy: "none",
  }),
  route({
    id: "advanced_evidence",
    path: "/advanced/evidence",
    legacyPaths: ["/evidence"],
    labelKey: "Evidence",
    pageTitleKey: "Evidence & Methods",
    descriptionKey: "Search and inspect evidence provenance",
    icon: "evidence",
    navigationSection: null,
    navigationGroup: null,
    navigationOrder: 200,
    showInSidebar: false,
    availability: "advanced",
    parentId: null,
    inspectorPolicy: "supported",
  }),
  route({
    id: "investment_episode",
    path: "/investments/episodes/:episodeId",
    legacyPaths: ["/decisions/episodes/:episodeId"],
    labelKey: "Investment Episode",
    pageTitleKey: "Investment Episode",
    descriptionKey: "Position lifecycle and linked decisions",
    icon: "episode",
    navigationSection: null,
    navigationGroup: null,
    navigationOrder: 11,
    showInSidebar: false,
    availability: "available",
    parentId: "investments",
    inspectorPolicy: "supported",
  }),
] as const;

export const navigationGroups: Readonly<Record<NavigationGroupId, Omit<ProductNavigationGroup, "type" | "children" | "route">>> = {
  review: {
    id: "review",
    labelKey: "Review",
    icon: "review",
    navigationSection: "work",
    navigationOrder: 20,
  },
};

function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const patternParts = pattern.split("/");
  const pathParts = pathname.split("/");
  if (patternParts.length !== pathParts.length) return null;
  const params: Record<string, string> = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const expected = patternParts[index];
    const actual = pathParts[index];
    if (expected.startsWith(":")) {
      if (!actual) return null;
      params[expected.slice(1)] = actual;
    } else if (expected !== actual) {
      return null;
    }
  }
  return params;
}

function fillPath(pattern: string, params: Readonly<Record<string, string>>): string {
  return pattern.replace(/:([A-Za-z0-9_]+)/g, (_match, key: string) => params[key] ?? "");
}

export function routeById(id: ProductRouteId): ProductRouteDefinition {
  const definition = productRoutes.find((item) => item.id === id);
  if (!definition) throw new Error(`Unknown product route: ${id}`);
  return definition;
}

export function resolveProductRoute(pathname: string): ProductRouteDefinition | null {
  return productRoutes.find((definition) => matchPath(definition.path, pathname) !== null) ?? null;
}

export function resolveLegacyRedirect(pathname: string): string | null {
  for (const definition of productRoutes) {
    for (const legacyPath of definition.legacyPaths) {
      const params = matchPath(legacyPath, pathname);
      if (params) return fillPath(definition.path, params);
    }
  }
  return null;
}

export function getSidebarNavigation(): readonly ProductNavigationEntry[] {
  const visible = productRoutes.filter(
    (definition) => definition.showInSidebar && definition.availability === "available",
  );
  const grouped = new Set<NavigationGroupId>();
  const entries: ProductNavigationEntry[] = [];

  for (const definition of [...visible].sort((a, b) => a.navigationOrder - b.navigationOrder)) {
    if (!definition.navigationGroup) {
      entries.push({ type: "route", route: definition });
      continue;
    }
    if (grouped.has(definition.navigationGroup)) continue;
    grouped.add(definition.navigationGroup);
    const group = navigationGroups[definition.navigationGroup];
    const groupRoute = visible.find((candidate) => candidate.id === group.id);
    if (!groupRoute) throw new Error(`Navigation group ${group.id} is missing its route.`);
    entries.push({
      type: "group",
      ...group,
      route: groupRoute,
      children: visible
        .filter((candidate) => candidate.parentId === groupRoute.id)
        .sort((a, b) => a.navigationOrder - b.navigationOrder),
    });
  }

  const orderOf = (entry: ProductNavigationEntry) =>
    entry.type === "route" ? entry.route.navigationOrder : entry.navigationOrder;
  return entries.sort((left, right) => orderOf(left) - orderOf(right));
}

export function activeRouteId(pathname: string): ProductRouteId | null {
  return resolveProductRoute(pathname)?.id ?? null;
}

export function activeNavigationRouteId(pathname: string): ProductRouteId | null {
  let definition = resolveProductRoute(pathname);
  while (definition?.parentId) definition = routeById(definition.parentId);
  return definition?.id ?? null;
}

export function activeNavigationGroup(pathname: string): NavigationGroupId | null {
  return resolveProductRoute(pathname)?.navigationGroup ?? null;
}

export function pageTitleKey(pathname: string): LocaleMessage {
  return resolveProductRoute(pathname)?.pageTitleKey ?? "Workspace";
}

export function legacyRoutePaths(): readonly string[] {
  return productRoutes.flatMap((definition) => definition.legacyPaths);
}
