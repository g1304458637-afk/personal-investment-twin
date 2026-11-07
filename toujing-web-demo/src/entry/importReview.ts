import type { Fill } from '../model.ts';

export type ImportedPreview = { name: string; rows: Record<string, string>[] };
export type ImportReview = ReturnType<typeof buildImportReview>;

/** Only facts supported by the supplied executions; no account or market assumptions. */
export function buildImportReview(preview: ImportedPreview) {
  if (!preview.rows.length) throw new Error('文件中没有可回顾的成交记录。');
  const fills: Fill[] = preview.rows.map((row, index) => {
    const parsed = new Date(row.date + 'T00:00:00Z');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== row.date || !row.ticker?.trim() || !['BUY', 'SELL'].includes(row.side) || !Number.isFinite(Number(row.price)) || Number(row.price) <= 0 || !Number.isFinite(Number(row.quantity)) || Number(row.quantity) <= 0) {
      throw new Error(`第 ${index + 2} 行的成交记录需要核对。`);
    }
    return { date: row.date, ticker: row.ticker, name: row.name?.trim() || row.ticker, side: row.side, quantity: row.quantity, price: row.price, fee: row.fee || '', execution_id: `csv-row-${index + 2}` };
  }).sort((a, b) => a.date.localeCompare(b.date));
  const dates = [...new Set(fills.map(fill => fill.date))];
  const buys = fills.filter(fill => fill.side === 'BUY').length;
  const securities = [...new Set(fills.map(fill => fill.ticker))];
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const grouped = new Map<string, { year: string; index: number; tradeCount: number; buyCount: number; sellCount: number }>();
  for (const fill of fills) {
    const year = fill.date.slice(0, 4);
    const group = grouped.get(year) ?? { year, index: 0, tradeCount: 0, buyCount: 0, sellCount: 0 };
    group.index = dateIndex.get(fill.date)!;
    group.tradeCount++;
    if (fill.side === 'BUY') group.buyCount++; else group.sellCount++;
    grouped.set(year, group);
  }
  const years = [...grouped.values()];
  return { fileName: preview.name, fills, dates, years, tradeCount: fills.length, buys, sells: fills.length - buys, securities, start: dates[0], end: dates.at(-1)! };
}
