export type TraceRecord = { date: string; side: string };
export type TracePoint = { position: number; sell: boolean };

/** The animation is a visual sample of the actual dates, never an account calculation. */
export function makeTrace(records: TraceRecord[], maximumPoints = 144) {
  const sorted = records
    .filter(record => /^\d{4}-\d{2}-\d{2}$/.test(record.date))
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
  if (!sorted.length) return { points: [] as TracePoint[], start: '', end: '', years: [] as string[], count: 0 };

  const start = sorted[0].date;
  const end = sorted[sorted.length - 1].date;
  const first = Date.parse(start + 'T00:00:00Z');
  const last = Date.parse(end + 'T00:00:00Z');
  const limit = Math.max(2, Math.floor(maximumPoints));
  const sample = sorted.length <= limit ? sorted : Array.from({ length: limit }, (_, i) => sorted[Math.floor(i * (sorted.length - 1) / (limit - 1))]);
  const points = sample.map(record => ({
    position: last === first ? .5 : (Date.parse(record.date + 'T00:00:00Z') - first) / (last - first),
    sell: record.side === 'SELL',
  }));

  const firstYear = Number(start.slice(0, 4));
  const lastYear = Number(end.slice(0, 4));
  const yearCount = Math.min(6, lastYear - firstYear + 1);
  const years = Array.from({ length: yearCount }, (_, i) => String(firstYear + (yearCount === 1 ? 0 : Math.round(i * (lastYear - firstYear) / (yearCount - 1)))));
  return { points, start, end, years, count: sorted.length };
}
