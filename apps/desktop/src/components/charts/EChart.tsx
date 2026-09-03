import { LineChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import {
  init,
  use,
  type ECElementEvent,
  type EChartsCoreOption,
} from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

use([LineChart, ScatterChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function EChart({
  option,
  label,
  className,
  onChartClick,
}: {
  option: EChartsCoreOption;
  label: string;
  className?: string;
  onChartClick?: (event: ECElementEvent) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof init> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const chart = init(container, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);

    return () => {
      observer.disconnect();
      chartRef.current = null;
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

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
