import { LineChart, ScatterChart } from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  TooltipComponent,
} from "echarts/components";
import {
  connect,
  init,
  use,
  type ECElementEvent,
  type EChartsCoreOption,
} from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { clampVisibleDailyWindow } from "@/components/charts/dailyTimeAxis";
import { cn } from "@/lib/utils";

use([
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  MarkAreaComponent,
  DataZoomComponent,
  AxisPointerComponent,
  CanvasRenderer,
]);

type ZoomState = {
  start: number;
  end: number;
  startValue?: number;
  endValue?: number;
};

export function EChart({
  option,
  label,
  className,
  onChartClick,
  group,
  resetKey,
  observationTimes,
}: {
  option: EChartsCoreOption;
  label: string;
  className?: string;
  onChartClick?: (event: ECElementEvent) => void;
  group?: string;
  resetKey?: string;
  observationTimes?: number[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof init> | null>(null);
  const zoomRef = useRef<ZoomState | null>(null);
  const resetKeyRef = useRef(resetKey);
  const observationTimesRef = useRef(observationTimes);
  observationTimesRef.current = observationTimes;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const chart = init(container, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);

    const onZoom = () => {
      const current = chart.getOption() as {
        dataZoom?: Array<{ start?: number; end?: number; startValue?: number; endValue?: number }>;
      };
      const zoom = current.dataZoom?.[0];
      if (!zoom) return;
      const startValue = Number(zoom.startValue);
      const endValue = Number(zoom.endValue);
      const times = observationTimesRef.current;
      if (times && times.length > 0 && Number.isFinite(startValue) && Number.isFinite(endValue)) {
        const clamped = clampVisibleDailyWindow(startValue, endValue, times);
        if (Math.abs(clamped.start - startValue) > 1 || Math.abs(clamped.end - endValue) > 1) {
          chart.dispatchAction({
            type: "dataZoom",
            startValue: clamped.start,
            endValue: clamped.end,
          });
          return;
        }
      }
      zoomRef.current = {
        start: Number(zoom.start),
        end: Number(zoom.end),
        startValue,
        endValue,
      };
    };
    chart.on("datazoom", onZoom);

    return () => {
      observer.disconnect();
      chart.off("datazoom", onZoom);
      chartRef.current = null;
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const keyChanged = resetKeyRef.current !== resetKey;
    resetKeyRef.current = resetKey;
    if (keyChanged) zoomRef.current = null;
    chart.setOption(option, { notMerge: true });
    const saved = zoomRef.current;
    if (!keyChanged && saved) {
      chart.dispatchAction({
        type: "dataZoom",
        start: saved.start,
        end: saved.end,
        startValue: saved.startValue,
        endValue: saved.endValue,
      });
    }
  }, [option, resetKey]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !group) return undefined;
    chart.group = group;
    connect(group);
    return undefined;
  }, [group]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onChartClick) return undefined;
    chart.on("click", onChartClick);
    return () => {
      chart.off("click", onChartClick);
    };
  }, [onChartClick]);

  return <div ref={containerRef} className={cn("echart", className)} role="img" aria-label={label} />;
}
