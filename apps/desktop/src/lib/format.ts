import type { EvidenceStatus } from "@/demo/types";

export type FormattingLocale = "zh-CN" | "en-US";

export const formatCurrencyValue = (value: number, locale: FormattingLocale = "zh-CN", currency: string | null = "CNY") =>
  currency === null ? `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value)} (${locale === "zh-CN" ? "币种未知" : "currency unknown"})` : new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);

export const formatPercentValue = (value: number, locale: FormattingLocale = "zh-CN", digits = 1) =>
  new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);

export const formatNumberValue = (value: number, locale: FormattingLocale = "zh-CN", digits = 0) =>
  new Intl.NumberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);

export const formatCurrency = (value: number) => formatCurrencyValue(value);
export const formatPercent = (value: number, digits = 1) => formatPercentValue(value, "zh-CN", digits);
export const formatNumber = (value: number, digits = 0) => formatNumberValue(value, "zh-CN", digits);

export const statusLabel: Record<EvidenceStatus, string> = {
  complete: "Complete",
  partial: "Partial",
  insufficient_evidence: "Insufficient evidence",
  experimental: "Experimental",
};

export function displayEvidenceValue(
  value: string | number | boolean | null,
  locale: FormattingLocale = "zh-CN",
) {
  if (value === null) return locale === "zh-CN" ? "不可用" : "Not available";
  if (typeof value === "boolean") return locale === "zh-CN" ? (value ? "是" : "否") : value ? "True" : "False";
  if (typeof value === "number") {
    return formatNumberValue(value, locale, Number.isInteger(value) ? 0 : 3);
  }
  return value;
}
