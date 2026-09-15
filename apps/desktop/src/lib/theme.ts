export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "toujing.theme";

/** The URL parameter is an explicit one-off override; the stored preference
 * (set in Settings) wins when present, otherwise the dark default applies. */
export function resolveTheme(search: string): Theme {
  const requested = new URLSearchParams(search).get("theme");
  if (requested === "light" || requested === "dark") return requested;
  return storedTheme() ?? "dark";
}

export function storedTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

export function storeTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private-mode storage denial keeps the session-only behavior.
  }
}

export function applyTheme(root: Pick<HTMLElement, "dataset" | "classList">, theme: Theme) {
  root.classList.toggle("dark", theme === "dark");
  root.dataset.theme = theme;
}
