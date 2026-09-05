/** Direct Time Navigation v1 — presentation-only visible-domain math. Not a financial calculator. */

import {
  MS_PER_DAY,
  MIN_VISIBLE_DAILY_OBSERVATIONS,
  clampVisibleDailyWindow,
  countDailyObservationsInRange,
} from "./dailyTimeAxis.ts";

export type EpisodeVisibleTimeDomain = {
  start: number;
  end: number;
};

export type TimeNavigationIntent = "pan" | "zoom" | "page-scroll";

export type WheelDeltaFields = {
  deltaX: number;
  deltaY: number;
  deltaMode: number;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
};

/** CSS-pixel equivalent of one WheelEvent LINE unit. Independent of Lightweight Charts' 32. */
export const WHEEL_LINE_DELTA_PIXELS = 16;

/** CSS-pixel equivalent of one WheelEvent PAGE unit. Independent of Lightweight Charts' 120. */
export const WHEEL_PAGE_DELTA_PIXELS = 800;

/**
 * Horizontal pan: one plot-width of normalized deltaX shifts one visible window.
 * Sign +1: positive deltaX (native overflow scroll-right) moves the window toward later dates.
 */
export const TIME_PAN_WINDOWS_PER_PLOT_WIDTH = 1;

/** ln(scale) per normalized zoom pixel. Chromium pinch events are small; this is a presentation gain. */
export const TIME_ZOOM_LN_PER_PIXEL = 0.0035;

/** |deltaX| must exceed |deltaY| by this ratio before a non-pinch wheel is treated as time pan. */
export const HORIZONTAL_PAN_DOMINANCE_RATIO = 1.25;

/** Ignore sub-pixel trackpad noise when deciding pan vs page-scroll. */
export const TIME_PAN_MIN_DELTA_PX = 0.5;

/** Visible span at or above this uses year-only axis labels. */
export const AXIS_MULTI_YEAR_SPAN_MS = 548 * MS_PER_DAY;

/** Visible span at or above this (and below multi-year) uses month labels. */
export const AXIS_MULTI_MONTH_SPAN_MS = 40 * MS_PER_DAY;

/** All-view line weight threshold. Markers stay at full size regardless. */
export const DENSE_DAILY_PATH_OBSERVATIONS = 400;

export const DOM_DELTA_PIXEL = 0;
export const DOM_DELTA_LINE = 1;
export const DOM_DELTA_PAGE = 2;

export function fullVisibleDomain(observationTimes: number[]): EpisodeVisibleTimeDomain {
  const times = [...new Set(observationTimes)].sort((left, right) => left - right);
  if (times.length === 0) {
    return { start: 0, end: MS_PER_DAY };
  }
  return {
    start: times[0],
    end: Math.max(times[times.length - 1], times[0] + MS_PER_DAY),
  };
}

export function domainsEqual(
  left: EpisodeVisibleTimeDomain,
  right: EpisodeVisibleTimeDomain,
  epsilon = 1,
): boolean {
  return Math.abs(left.start - right.start) <= epsilon && Math.abs(left.end - right.end) <= epsilon;
}

export function normalizeWheelDeltaPixels(delta: number, deltaMode: number): number {
  if (deltaMode === DOM_DELTA_LINE) return delta * WHEEL_LINE_DELTA_PIXELS;
  if (deltaMode === DOM_DELTA_PAGE) return delta * WHEEL_PAGE_DELTA_PIXELS;
  return delta;
}

export function classifyTimeNavigationIntent(event: WheelDeltaFields): TimeNavigationIntent {
  if (event.ctrlKey || event.metaKey) return "zoom";
  const deltaX = Math.abs(normalizeWheelDeltaPixels(event.deltaX, event.deltaMode));
  const deltaY = Math.abs(normalizeWheelDeltaPixels(event.deltaY, event.deltaMode));
  if (deltaX >= TIME_PAN_MIN_DELTA_PX && deltaX > deltaY * HORIZONTAL_PAN_DOMINANCE_RATIO) {
    return "pan";
  }
  return "page-scroll";
}

export function applyVisibleDailyDomain(
  candidate: EpisodeVisibleTimeDomain,
  observationTimes: number[],
  full = fullVisibleDomain(observationTimes),
): EpisodeVisibleTimeDomain {
  if (!Number.isFinite(candidate.start) || !Number.isFinite(candidate.end)) return full;
  const span = Math.min(full.end - full.start, Math.max(MS_PER_DAY, Math.abs(candidate.end - candidate.start)));
  const start = Math.max(full.start, Math.min(Math.min(candidate.start, candidate.end), full.end - span));
  let next = { start, end: start + span };
  // Only expand a genuinely undersized window. Never snap valid pan/zoom endpoints.
  if (countDailyObservationsInRange(observationTimes, next.start, next.end) < Math.min(MIN_VISIBLE_DAILY_OBSERVATIONS, observationTimes.length)) {
    const minimum = clampVisibleDailyWindow(next.start, next.end, observationTimes);
    next = { start: Math.max(full.start, Math.min(next.start, minimum.start)),
      end: Math.min(full.end, Math.max(next.end, minimum.end)) };
  }
  return next;
}

export function panVisibleDailyDomain(
  domain: EpisodeVisibleTimeDomain, panMs: number, observationTimes: number[],
  full = fullVisibleDomain(observationTimes),
): EpisodeVisibleTimeDomain {
  const span = domain.end - domain.start;
  const start = Math.max(full.start, Math.min(domain.start + panMs, full.end - span));
  const next = { start, end: start + span };
  // Sparse gaps do not silently resize the user's selected window.
  if (countDailyObservationsInRange(observationTimes, next.start, next.end) < Math.min(MIN_VISIBLE_DAILY_OBSERVATIONS, observationTimes.length)) return domain;
  return next;
}

export function panVisibleDailyDomainByPixels(
  domain: EpisodeVisibleTimeDomain, deltaXPixels: number, axisWidthPixels: number,
  observationTimes: number[], full = fullVisibleDomain(observationTimes),
): EpisodeVisibleTimeDomain {
  const panMs = (deltaXPixels / Math.max(1, axisWidthPixels)) * (domain.end - domain.start) * TIME_PAN_WINDOWS_PER_PLOT_WIDTH;
  return panVisibleDailyDomain(domain, panMs, observationTimes, full);
}

export function anchoredZoomVisibleDomain(
  domain: EpisodeVisibleTimeDomain, anchorTime: number, scale: number,
  observationTimes: number[], full = fullVisibleDomain(observationTimes),
): EpisodeVisibleTimeDomain {
  const span = Math.max(MS_PER_DAY, domain.end - domain.start);
  const safeScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  const nextSpan = Math.max(MS_PER_DAY, span / safeScale);
  const frac = Math.min(1, Math.max(0, (anchorTime - domain.start) / span));
  const start = anchorTime - frac * nextSpan;
  return applyVisibleDailyDomain({ start, end: start + nextSpan }, observationTimes, full);
}

export function zoomScaleFromWheelDelta(deltaYPixels: number): number {
  return Math.exp(-TIME_ZOOM_LN_PER_PIXEL * deltaYPixels);
}

export function dailyPathLineWidth(
  observationCount: number,
  role: "primary" | "secondary" | "muted",
): number {
  const dense = observationCount >= DENSE_DAILY_PATH_OBSERVATIONS;
  if (role === "primary") return dense ? 1.15 : 2.4;
  if (role === "secondary") return dense ? 0.95 : 1.6;
  return dense ? 0.8 : 1.5;
}

function calendarParts(value: number): { year: number; month: number; day: number } {
  const instant = new Date(value);
  return {
    year: instant.getFullYear(),
    month: instant.getMonth(),
    day: instant.getDate(),
  };
}

export function formatAdaptiveDailyAxisTick(
  value: number,
  locale: string,
  visibleStart: number,
  visibleEnd: number,
): string {
  const span = Math.max(0, visibleEnd - visibleStart);
  const parts = calendarParts(value);
  const zh = locale.toLowerCase().startsWith("zh");
  const clockFree = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(locale, options).format(
      new Date(parts.year, parts.month, parts.day),
    );

  if (span >= AXIS_MULTI_YEAR_SPAN_MS) {
    return zh ? `${parts.year}` : clockFree({ year: "numeric" });
  }

  if (span >= AXIS_MULTI_MONTH_SPAN_MS) {
    const startParts = calendarParts(visibleStart);
    const showYear = parts.month === 0 || (parts.year === startParts.year && parts.month === startParts.month);
    if (zh) {
      return showYear ? `${parts.year}年${parts.month + 1}月` : `${parts.month + 1}月`;
    }
    return clockFree(showYear ? { year: "numeric", month: "short" } : { month: "short" });
  }

  if (zh) return `${parts.month + 1}月${parts.day}日`;
  return clockFree({ month: "short", day: "numeric" });
}

export function visibleDomainObservationCount(
  domain: EpisodeVisibleTimeDomain,
  observationTimes: number[],
): number {
  return countDailyObservationsInRange(observationTimes, domain.start, domain.end);
}

export function isIntradayDomain(domain: EpisodeVisibleTimeDomain): boolean {
  return domain.end - domain.start < MS_PER_DAY;
}

export function createAdaptiveDailyAxisFormatter(
  locale: string,
  getDomain: () => EpisodeVisibleTimeDomain | undefined,
): (value: number) => string {
  return (value: number) => {
    const domain = getDomain();
    const parts = calendarParts(value);
    const span = domain ? domain.end - domain.start : 0;
    // Calendar gates are stable across redraws; no mutable last-label cache.
    if (span >= AXIS_MULTI_YEAR_SPAN_MS && (parts.month !== 0 || parts.day !== 1)) return "";
    if (span >= AXIS_MULTI_MONTH_SPAN_MS && parts.day !== 1) return "";
    return formatAdaptiveDailyAxisTick(value, locale, domain?.start ?? value, domain?.end ?? value);
  };
}

export { MIN_VISIBLE_DAILY_OBSERVATIONS, MS_PER_DAY };
