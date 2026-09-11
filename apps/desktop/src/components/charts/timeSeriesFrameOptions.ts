import { dailyDataZoom } from "./dailyTimeAxis";

/**
 * TimeSeriesFrame owns the one visible range control. ECharts still needs an
 * inside dataZoom action target so the shared navigation store can apply the
 * selected real-date domain to the rendered time axis.
 */
export function frameDataZoom(minValueSpan: number) {
  return [dailyDataZoom(0, minValueSpan)[0]];
}

/** Keep ECharts' time-axis bounds in the same local daily coordinates as the frame. */
export function frameDailyTimeDomain(observationTimes: number[]): { min?: number; max?: number } {
  if (observationTimes.length === 0) return {};
  return { min: observationTimes[0], max: observationTimes[observationTimes.length - 1] };
}
