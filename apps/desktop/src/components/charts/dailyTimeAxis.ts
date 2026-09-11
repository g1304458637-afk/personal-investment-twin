/** Daily Market Data Contract helpers for Episode charts. Not a financial calculator. */

export const MS_PER_DAY = 24 * 60 * 60 * 1000;
export const MIN_VISIBLE_DAILY_OBSERVATIONS = 5;

export function formatDailyAxisTick(value: number, locale: string): string {
  const instant = new Date(value);
  const calendar = new Date(instant.getFullYear(), instant.getMonth(), instant.getDate());
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }).format(calendar);
}

export function calendarDayTime(value: number): number {
  const instant = new Date(value);
  return new Date(instant.getFullYear(), instant.getMonth(), instant.getDate()).getTime();
}

/**
 * Daily-only backend series use a calendar date, not a UTC instant. Keep that
 * date at local midnight so ECharts coordinates match the navigation domain.
 * Full execution timestamps continue through Date.parse unchanged.
 */
export function dailyTimeCoordinate(value: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return Date.parse(value);
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const local = new Date(year, month, day);
  return local.getFullYear() === year && local.getMonth() === month && local.getDate() === day
    ? local.getTime()
    : Number.NaN;
}

export function uniqueDailyObservationTimes(timestamps: Array<string | null | undefined>): number[] {
  const days = new Set<number>();
  for (const item of timestamps) {
    if (!item) continue;
    const parsed = dailyTimeCoordinate(item);
    if (Number.isNaN(parsed)) continue;
    days.add(calendarDayTime(parsed));
  }
  return [...days].sort((left, right) => left - right);
}

export function dailyTimeDomain(timestamps: Array<string | null | undefined>): {
  min?: string;
  max?: string;
} {
  const values = timestamps.filter((item): item is string => typeof item === "string" && item.length > 0);
  if (values.length === 0) return {};
  let min = values[0];
  let max = values[0];
  for (const item of values) {
    if (item < min) min = item;
    if (item > max) max = item;
  }
  return { min, max };
}

export function minDailyZoomSpanMs(observationTimes: number[]): number {
  const times = [...new Set(observationTimes)].sort((left, right) => left - right);
  if (times.length === 0) return MS_PER_DAY;
  if (times.length < MIN_VISIBLE_DAILY_OBSERVATIONS) {
    return Math.max(MS_PER_DAY, times[times.length - 1] - times[0]);
  }
  let densest = Number.POSITIVE_INFINITY;
  for (let index = 0; index + MIN_VISIBLE_DAILY_OBSERVATIONS - 1 < times.length; index += 1) {
    const span = times[index + MIN_VISIBLE_DAILY_OBSERVATIONS - 1] - times[index];
    if (span < densest) densest = span;
  }
  return Math.max(MS_PER_DAY, densest);
}

export function countDailyObservationsInRange(
  observationTimes: number[],
  start: number,
  end: number,
): number {
  const low = Math.min(start, end);
  const high = Math.max(start, end);
  return observationTimes.filter((item) => item >= low && item <= high).length;
}

export function clampVisibleDailyWindow(
  start: number,
  end: number,
  observationTimes: number[],
  minCount = MIN_VISIBLE_DAILY_OBSERVATIONS,
): { start: number; end: number } {
  const times = [...new Set(observationTimes)].sort((left, right) => left - right);
  let low = Math.min(start, end);
  let high = Math.max(start, end);
  if (high - low < MS_PER_DAY) {
    high = low + MS_PER_DAY;
  }
  if (times.length === 0) {
    return { start: low, end: high };
  }
  const domainStart = times[0];
  const domainEnd = times[times.length - 1];
  if (times.length <= minCount) {
    return { start: domainStart, end: Math.max(domainEnd, domainStart + MS_PER_DAY) };
  }
  const inRange = times
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item >= low && item <= high);
  let startIndex: number;
  let endIndex: number;
  if (inRange.length === 0) {
    const midpoint = (low + high) / 2;
    let nearest = 0;
    for (let index = 1; index < times.length; index += 1) {
      if (Math.abs(times[index] - midpoint) < Math.abs(times[nearest] - midpoint)) {
        nearest = index;
      }
    }
    startIndex = nearest;
    endIndex = nearest;
  } else {
    startIndex = inRange[0].index;
    endIndex = inRange[inRange.length - 1].index;
  }
  while (endIndex - startIndex + 1 < minCount) {
    const canLeft = startIndex > 0;
    const canRight = endIndex < times.length - 1;
    if (!canLeft && !canRight) break;
    if (canLeft && canRight) {
      const leftGap = times[startIndex] - times[startIndex - 1];
      const rightGap = times[endIndex + 1] - times[endIndex];
      if (leftGap <= rightGap) startIndex -= 1;
      else endIndex += 1;
    } else if (canLeft) {
      startIndex -= 1;
    } else {
      endIndex += 1;
    }
  }
  return {
    start: times[startIndex],
    end: Math.max(times[endIndex], times[startIndex] + MS_PER_DAY),
  };
}

export function dailyDataZoom(sliderBottom: number, minValueSpan: number) {
  return [
    {
      type: "inside" as const,
      xAxisIndex: 0,
      filterMode: "none" as const,
      start: 0,
      end: 100,
      minValueSpan,
      zoomLock: true,
      zoomOnMouseWheel: false,
      moveOnMouseWheel: false,
      moveOnMouseMove: true,
      preventDefaultMouseMove: true,
    },
    {
      type: "slider" as const,
      xAxisIndex: 0,
      height: 16,
      bottom: sliderBottom,
      start: 0,
      end: 100,
      minValueSpan,
      filterMode: "none" as const,
      borderColor: "rgba(148, 177, 204, .18)",
      fillerColor: "rgba(142, 220, 255, .08)",
      handleStyle: { color: "#8edcff" },
      textStyle: { color: "rgba(177, 196, 214, .72)" },
    },
  ];
}
