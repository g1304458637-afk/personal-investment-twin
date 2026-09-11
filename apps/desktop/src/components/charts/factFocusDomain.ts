/** Viewport context only. The fact's actual highlight boundaries stay unchanged. */
export function factFocusDomain(start: number, end: number, observations: readonly number[]) {
  const times = [...new Set(observations.filter(Number.isFinite))].sort((a, b) => a - b);
  const before = times.filter((time) => time < start);
  const after = times.filter((time) => time > end);
  // Show up to five existing observations on each side; never fabricate prices/dates.
  return {
    start: before.length ? before[Math.max(0, before.length - 5)] : start,
    end: after.length ? after[Math.min(4, after.length - 1)] : end,
  };
}
