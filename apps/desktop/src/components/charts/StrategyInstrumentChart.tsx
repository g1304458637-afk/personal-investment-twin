import { dispose, init, registerOverlay, type Chart } from "klinecharts";
import { useEffect, useRef } from "react";

let registered = false;

function ensureOverlay() {
  if (registered) return;
  registered = true;
  registerOverlay({
    name: "StrategyFillMarker", totalStep: 2, needDefaultPointFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      const point = coordinates[0];
      if (!point) return [];
      const meta = overlay.extendData as { side: "BUY" | "SELL"; label: string };
      const color = meta.side === "BUY" ? "#7ee2b8" : "#ffb0bc";
      const y = point.y + (meta.side === "BUY" ? 30 : -30);
      return [
        { type: "line", attrs: { coordinates: [point, { x: point.x, y }] }, styles: { color, style: "dashed" }, ignoreEvent: true },
        { type: "text", attrs: { x: point.x, y, text: meta.label, align: "center", baseline: "middle" }, styles: { color, backgroundColor: "rgba(30,49,65,.85)", borderRadius: 4, paddingLeft: 5, paddingRight: 5, paddingTop: 3, paddingBottom: 3, size: 11 }, ignoreEvent: false },
      ];
    },
  });
}

export function StrategyInstrumentChart({ bars, fills, height = 320 }: {
  bars: { date: string; open: number; high: number; low: number; close: number }[];
  fills: { day: string; side: "BUY" | "SELL"; price: number }[];
  height?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !bars.length) return undefined;
    ensureOverlay();
    const chart = init(host, { timezone: "UTC", styles: { grid: { horizontal: { show: false }, vertical: { show: false } } } });
    if (!chart) return undefined;
    chartRef.current = chart;
    chart.setSymbol({ ticker: "STRATEGY", pricePrecision: 2 });
    chart.setPeriod({ type: "day", span: 1 });
    chart.setDataLoader({ getBars: ({ callback }) => callback(
      bars.map((bar) => ({ timestamp: Date.parse(`${bar.date}T00:00:00Z`), open: bar.open, high: bar.high, low: bar.low, close: bar.close })), false) });
    for (const fill of fills) {
      const bar = bars.find((item) => item.date === fill.day);
      if (!bar) continue;
      const anchor = fill.side === "BUY" ? bar.low : bar.high;
      const point = { timestamp: Date.parse(`${fill.day}T00:00:00Z`), value: anchor };
      chart.createOverlay({
        name: "StrategyFillMarker", points: [point, point],
        extendData: { side: fill.side, label: fill.side === "BUY" ? "规买" : "规卖" },
        lock: true, fixedZLevel: true,
      });
    }
    chart.setBarSpace(6);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    return () => { observer.disconnect(); dispose(chart); if (chartRef.current === chart) chartRef.current = null; };
  }, [bars, fills]);
  return <div ref={hostRef} style={{ height, width: "100%" }} role="img" aria-label="策略个股操作图" />;
}
