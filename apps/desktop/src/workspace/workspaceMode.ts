/** Retired presentation flag: old bookmarks always open the current workspace. */
export const isClassicWorkspace = (_search = "") => false;

/** Set before React renders; keep the same appearance through welcome/route transitions. */
export function initializeWorkspaceAppearance(root: { dataset: { workspace?: string } }, _search: string) {
  root.dataset.workspace = "intelligence";
}

export const workspaceDestinations = [
  { path: "/investments", label: "investments", group: "work" },
  { path: "/review", label: "review", group: "work" },
  { path: "/history", label: "history", group: "work" },
  { path: "/comparison", label: "comparison", group: "work" },
  { path: "/pretrade", label: "pretrade", group: "work" },
  { path: "/journal", label: "journal", group: "record" },
  { path: "/data", label: "data", group: "manage" },
  { path: "/settings", label: "settings", group: "manage" },
] as const;

export function workspaceSection(path: string): string {
  if (path.startsWith("/investments/compare")) return "/comparison";
  if (path.startsWith("/investments")) return "/investments";
  if (path.startsWith("/review")) return "/review";
  if (path === "/twin") return "/history";
  return path;
}
