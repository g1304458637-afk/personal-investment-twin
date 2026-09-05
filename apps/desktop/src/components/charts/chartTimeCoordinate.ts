/** Public single-axis ECharts conversion: one CSS pixel, not an [x,y] tuple. */
export function timeAtClientX(
  chart: { convertFromPixel: (finder: { xAxisIndex: number }, value: number) => unknown },
  container: { getBoundingClientRect: () => { left: number } },
  clientX: number,
): number | null {
  try {
    const value = Number(chart.convertFromPixel({ xAxisIndex: 0 }, clientX - container.getBoundingClientRect().left));
    return Number.isFinite(value) ? value : null;
  } catch { return null; }
}
