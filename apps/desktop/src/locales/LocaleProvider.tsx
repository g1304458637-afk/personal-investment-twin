import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";

import { formatCurrencyValue, formatNumberValue, formatPercentValue } from "@/lib/format";

import { enUS } from "./en-US";
import { zhCN } from "./zh-CN";

export type Locale = "zh-CN" | "en-US";
export type TranslationValues = Record<string, string | number>;

const dictionaries: Record<Locale, Record<string, string>> = {
  "zh-CN": zhCN,
  "en-US": enUS,
};

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (source: string, values?: TranslationValues) => string;
  formatCurrency: (value: number) => string;
  formatNumber: (value: number, digits?: number) => string;
  formatPercent: (value: number, digits?: number) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);
const CurrencyContext = createContext<string | null | undefined>(undefined);
export const CurrencyProvider = CurrencyContext.Provider;

const LOCALE_STORAGE_KEY = "toujing.locale";

function initialLocale(): Locale {
  // URL parameter is an explicit one-off override; the stored preference
  // (set in Settings) wins when present, otherwise the zh-CN default.
  const requested = new URLSearchParams(window.location.search).get("locale");
  if (requested === "en-US" || requested === "zh-CN") return requested;
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === "en-US" || stored === "zh-CN") return stored;
  } catch {
    // Storage unavailable: keep the default.
  }
  return "zh-CN";
}

function interpolate(message: string, values?: TranslationValues) {
  if (!values) return message;
  return message.replace(/\{(\w+)\}/g, (token, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : token,
  );
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // Private-mode storage denial keeps the session-only behavior.
    }
    setLocaleState(next);
  }, []);

  const t = useCallback(
    (source: string, values?: TranslationValues) =>
      interpolate(dictionaries[locale][source] ?? source, values),
    [locale],
  );

  useLayoutEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
    document.title = dictionaries[locale]["投镜 · Investment Twin"] ?? "投镜 · Investment Twin";
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      setLocale,
      t,
      formatCurrency: (amount) => formatCurrencyValue(amount, locale),
      formatNumber: (number, digits = 0) => formatNumberValue(number, locale, digits),
      formatPercent: (number, digits = 1) => formatPercentValue(number, locale, digits),
    }),
    [locale, t],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  const currency = useContext(CurrencyContext);
  if (!context) throw new Error("useLocale must be used within LocaleProvider");
  return currency === undefined ? context : { ...context,
    formatCurrency: (amount: number) => formatCurrencyValue(amount, context.locale, currency) };
}
