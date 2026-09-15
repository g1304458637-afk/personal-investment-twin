import { createContext, useContext, useLayoutEffect, useMemo, useState } from "react";
import { applyTheme, resolveTheme, storeTheme, type Theme } from "@/lib/theme";

export type { Theme } from "@/lib/theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialTheme(): Theme {
  return resolveTheme(window.location.search);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useLayoutEffect(() => {
    applyTheme(document.documentElement, theme);
  }, [theme]);

  const updateTheme = (next: Theme) => {
    storeTheme(next);
    setTheme(next);
  };

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: updateTheme,
      toggleTheme: () => setTheme((current) => {
        const next = current === "dark" ? "light" : "dark";
        storeTheme(next);
        return next;
      }),
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
