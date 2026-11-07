const currencyScales: Record<string, number> = {
  CNY: 1, CNY_thousand: 1000, CNY_ten_thousand: 10000, CNY_million: 1000000,
};
export const unitName = (unit?: string) => ({
  CNY: '元', CNY_thousand: '千元', CNY_ten_thousand: '万元', CNY_million: '百万元',
  percent: '%', ratio: '倍',
} as Record<string, string>)[unit || ''] || unit || '';

export function numericValue(value: string | null | undefined): number | null {
  if (value == null || !value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function currencyInHundredMillions(value: string | null | undefined, unit?: string): number | null {
  const number = numericValue(value), scale = currencyScales[unit || ''];
  return number === null || scale === undefined ? null : number * scale / 1e8;
}

export function displayValue(item: {unit?: string} | undefined, value: {value?: string | null; unit?: string} | undefined, compact = false) {
  const number = numericValue(value?.value), unit = value?.unit || item?.unit || '';
  if (number === null) return {number: '—', unit: ''};
  const converted = compact ? currencyInHundredMillions(value?.value, unit) : null;
  if (converted !== null) return {number: converted.toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2}), unit: '亿元'};
  return {number: number.toLocaleString('zh-CN', {maximumFractionDigits: 2, minimumFractionDigits: ['percent', 'ratio'].includes(unit) ? 2 : 0}), unit: unitName(unit)};
}
