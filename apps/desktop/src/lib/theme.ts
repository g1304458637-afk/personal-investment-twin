export type Theme = "dark" | "light";

/** The existing URL-only preference, shared by startup and the React provider. */
export function resolveTheme(search: string): Theme {
  return new URLSearchParams(search).get("theme") === "light" ? "light" : "dark";
}

export function applyTheme(root: Pick<HTMLElement, "dataset" | "classList">, theme: Theme) {
  root.classList.toggle("dark", theme === "dark");
  root.dataset.theme = theme;
}
