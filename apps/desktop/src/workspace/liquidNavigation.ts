/** Presentation hierarchy only; existing account/runtime gates remain in each destination. */
export const liquidNavigation = [
  { path: "/investments", label: "investments", icon: "investments", group: "work" },
  { path: "/strategy-simulation", label: "strategy", icon: "review", group: "work" },
  { path: "/analysis", label: "analysis", icon: "comparison", group: "work" },
  { path: "/pretrade", label: "prepare", icon: "pretrade", group: "work" },
  { path: "/ask", label: "ask", icon: "ask", group: "work" },
  { path: "/data", label: "data", icon: "data", group: "manage" },
  { path: "/settings", label: "settings", icon: "settings", group: "manage" },
] as const;

export function liquidSection(path: string) {
  if (path.startsWith("/investments/compare") || ["/analysis", "/review", "/history", "/comparison", "/twin", "/advanced"].some((root) => path === root || path.startsWith(`${root}/`))) return "/analysis";
  if (path === "/journal" || path === "/pretrade") return "/pretrade";
  if (path.startsWith("/investments")) return "/investments";
  return path;
}

export const analysisLinks = [
  { path: "/comparison/history", label: "selfTitle" },
  { path: "/investments/compare-example", label: "pairTitle" },
  { path: "/comparison/professional", label: "professionalTitle" },
] as const;
