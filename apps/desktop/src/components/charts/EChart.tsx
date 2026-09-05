import { timeAtClientX } from "./chartTimeCoordinate";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
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

import { clampVisibleDailyWindow } from "./dailyTimeAxis.ts";
import {
  classifyTimeNavigationIntent,
  normalizeWheelDeltaPixels,
  panVisibleDailyDomainByPixels,
  anchoredZoomVisibleDomain,
  zoomScaleFromWheelDelta,
  type EpisodeVisibleTimeDomain,
} from "./dailyTimeNavigation.ts";
import type { DailyTimeNavigationStore } from "./useDailyTimeNavigation.ts";
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

function readZoomDomain(chart: ReturnType<typeof init>): EpisodeVisibleTimeDomain | null {
  const current = chart.getOption() as {
    dataZoom?: Array<{ startValue?: number; endValue?: number }>;
  };
  const zoom = current.dataZoom?.[0];
  if (!zoom) return null;
  const start = Number(zoom.startValue);
  const end = Number(zoom.endValue);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return { start, end };
}

function axisWidthPixels(chart: ReturnType<typeof init>, domain: EpisodeVisibleTimeDomain): number {
  try {
    const start = chart.convertToPixel({ xAxisIndex: 0 }, domain.start);
    const end = chart.convertToPixel({ xAxisIndex: 0 }, domain.end);
    const width = Math.abs(Number(end) - Number(start));
    if (Number.isFinite(width) && width > 1) return width;
  } catch {
    /* convertToPixel can throw before the first layout */
  }
  return Math.max(1, chart.getWidth());
}

export function EChart({
  option,
  label,
  className,
  onChartClick,
  group,
  resetKey,
  observationTimes,
  timeNavigation,
}: {
  option: EChartsCoreOption;
  label: string;
  className?: string;
  onChartClick?: (event: ECElementEvent) => void;
  group?: string;
  resetKey?: string;
  observationTimes?: number[];
  timeNavigation?: DailyTimeNavigationStore;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof init> | null>(null);
  const resetKeyRef = useRef(resetKey);
  const observationTimesRef = useRef(observationTimes);
  const timeNavigationRef = useRef(timeNavigation);
  const applyingRef = useRef(false);
  observationTimesRef.current = observationTimes;
  timeNavigationRef.current = timeNavigation;

  const applyChartDomain = (domain: EpisodeVisibleTimeDomain) => {
    const chart = chartRef.current;
    if (!chart) return;
    applyingRef.current = true;
    chart.dispatchAction({
      type: "dataZoom",
      startValue: domain.start,
      endValue: domain.end,
      animation: { duration: 0 },
      escapeConnect: true,
    });
    applyingRef.current = false;
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const chart = init(container, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);

    const onZoom = () => {
      if (applyingRef.current) return;
      const current = readZoomDomain(chart);
      const times = observationTimesRef.current;
      const navigation = timeNavigationRef.current;
      if (!current || !times || times.length === 0) return;
      if (navigation) {
        navigation.apply(current, "slider");
        applyChartDomain(navigation.getDomain());
      } else applyChartDomain(clampVisibleDailyWindow(current.start, current.end, times));
    };
    chart.on("datazoom", onZoom);

    const onWheel = (event: WheelEvent) => {
      const navigation = timeNavigationRef.current;
      const times = observationTimesRef.current;
      if (!navigation || !times || times.length === 0) return;
      const intent = classifyTimeNavigationIntent(event);
      if (intent === "page-scroll") return;
      if (!event.cancelable) return;
      if (gestureActive && intent === "zoom") { event.preventDefault(); event.stopPropagation(); return; }
      if (event.cancelable) {
        event.preventDefault();
        event.stopPropagation();
      }
      const domain = navigation.getDomain();
      const rendered = readZoomDomain(chart) ?? domain;
      if (intent === "pan") {
        const deltaX = normalizeWheelDeltaPixels(event.deltaX, event.deltaMode);
        const next = panVisibleDailyDomainByPixels(
          domain,
          deltaX,
          axisWidthPixels(chart, rendered),
          times, navigation.fullDomain,
        );
        navigation.schedule(next);
        return;
      }
      const deltaY = normalizeWheelDeltaPixels(event.deltaY, event.deltaMode);
      const scale = zoomScaleFromWheelDelta(deltaY);
      const position = timeAtClientX(chart, container, event.clientX);
      if (position === null) return;
      const anchor = domain.start + (position - rendered.start) / (rendered.end - rendered.start) * (domain.end - domain.start);
      const next = anchoredZoomVisibleDomain(domain, anchor, scale, times, navigation.fullDomain);
      navigation.schedule(next);
    };
    container.addEventListener("wheel", onWheel, { passive: false, capture: true });

    let gestureScale = 1;
    let gestureActive = false;
    const onGestureStart = (event: Event) => {
      if (!timeNavigationRef.current || !event.cancelable) return;
      gestureScale = 1;
      gestureActive = true;
      if (event.cancelable) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const onGestureChange = (event: Event) => {
      const navigation = timeNavigationRef.current;
      const times = observationTimesRef.current;
      const gesture = event as Event & { scale?: number; clientX?: number };
      if (!navigation || !times || times.length === 0 || typeof gesture.scale !== "number" || !event.cancelable) return;
      if (event.cancelable) {
        event.preventDefault();
        event.stopPropagation();
      }
      const ratio = gesture.scale / (gestureScale || 1);
      gestureScale = gesture.scale;
      if (!Number.isFinite(ratio) || ratio <= 0 || Math.abs(ratio - 1) < 0.002) return;
      const domain = navigation.getDomain();
      const clientX = typeof gesture.clientX === "number" ? gesture.clientX : container.getBoundingClientRect().left + container.clientWidth / 2;
      const rendered = readZoomDomain(chart) ?? domain;
      const position = timeAtClientX(chart, container, clientX);
      if (position === null) return;
      const anchor = domain.start + (position - rendered.start) / (rendered.end - rendered.start) * (domain.end - domain.start);
      navigation.schedule(anchoredZoomVisibleDomain(domain, anchor, ratio, times, navigation.fullDomain));
    };
    const onGestureEnd = () => {
      gestureActive = false;
      gestureScale = 1;
    };
    container.addEventListener("gesturestart", onGestureStart, { passive: false, capture: true });
    container.addEventListener("gesturechange", onGestureChange, { passive: false, capture: true });
    container.addEventListener("gestureend", onGestureEnd, { capture: true });

    return () => {
      observer.disconnect();
      container.removeEventListener("wheel", onWheel, { capture: true });
      container.removeEventListener("gesturestart", onGestureStart, { capture: true });
      container.removeEventListener("gesturechange", onGestureChange, { capture: true });
      container.removeEventListener("gestureend", onGestureEnd, { capture: true });
      timeNavigationRef.current?.cancelPending();
      chart.off("datazoom", onZoom);
      chartRef.current = null;
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !timeNavigation) return undefined;
    applyChartDomain(timeNavigation.getDomain());
    return timeNavigation.subscribe((domain) => {
      applyChartDomain(domain);
    });
  }, [timeNavigation]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const keyChanged = resetKeyRef.current !== resetKey;
    resetKeyRef.current = resetKey;
    if (keyChanged) timeNavigationRef.current?.reset();
    chart.setOption(option, { notMerge: true });
    const domain = timeNavigationRef.current?.getDomain();
    if (domain) applyChartDomain(domain);
  }, [option, resetKey]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !group) return undefined;
    // Shared visible-domain store is the only dataZoom synchronization owner.
    // Do not also echarts.connect the same charts (duplicate propagation).
    chart.group = "";
    return undefined;
  }, [group]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onChartClick) return undefined;
    chart.on("click", onChartClick);
    return () => {
      if (!chart.isDisposed()) chart.off("click", onChartClick);
    };
  }, [onChartClick]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!timeNavigation) return;
    const domain = timeNavigation.getDomain(), times = timeNavigation.observationTimes;
    if (event.key === "Home") timeNavigation.reset();
    else if (event.key === "ArrowLeft" || event.key === "ArrowRight") timeNavigation.apply(
      panVisibleDailyDomainByPixels(domain, event.key === "ArrowRight" ? 100 : -100, 800, times, timeNavigation.fullDomain), "drag");
    else if (event.key === "+" || event.key === "-" || event.key === "=") timeNavigation.apply(
      anchoredZoomVisibleDomain(domain, (domain.start + domain.end) / 2, event.key === "-" ? 0.8 : 1.25, times, timeNavigation.fullDomain), "slider");
    else return;
    event.preventDefault();
  };
  return <div tabIndex={timeNavigation ? 0 : undefined} onKeyDown={onKeyDown} ref={containerRef} className={cn("echart", className)} role="img" aria-label={label} />;
}
