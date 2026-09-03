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

function initialLocale(): Locale {
  const requested = new URLSearchParams(window.location.search).get("locale");
  return requested === "en-US" ? "en-US" : "zh-CN";
}

function interpolate(message: string, values?: TranslationValues) {
  if (!values) return message;
  return message.replace(/\{(\w+)\}/g, (token, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : token,
  );
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

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
  if (!context) throw new Error("useLocale must be used within LocaleProvider");
  return context;
}
