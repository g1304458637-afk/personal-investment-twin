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
import { useEffect, useRef, useState } from "react";

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
import { publishChartCursor, subscribeChartCursor } from "./chartCursor.ts";
import { forwardChartPageScroll } from "./chartPageScroll.ts";
import { useLocale } from "@/locales/LocaleProvider";
import { downloadPngDataUrl } from "@/lib/download";
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
  exportable = false,
}: {
  option: EChartsCoreOption;
  label: string;
  className?: string;
  onChartClick?: (event: ECElementEvent) => void;
  group?: string;
  resetKey?: string;
  observationTimes?: number[];
  timeNavigation?: DailyTimeNavigationStore;
  /** Render a "save as PNG" button using the chart's own rendered pixels. */
  exportable?: boolean;
}) {
  const { locale } = useLocale();
  const [linkedCursor, setLinkedCursor] = useState<{ x: number; top: number; height: number } | null>(null);
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
      if (intent === "page-scroll") {
        // Do not let a canvas wheel listener swallow vertical page navigation.
        event.stopPropagation();
        forwardChartPageScroll(container, event);
        return;
      }
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
    if (!chart || !timeNavigation) return;
    const source = chart;
    let linkedTime: number | null = null;
    const move = (event: { offsetX: number; offsetY: number }) => {
      linkedTime = null;
      setLinkedCursor(null);
      if (!chart.containPixel({ gridIndex: 0 }, [event.offsetX, event.offsetY])) {
        publishChartCursor(timeNavigation, null, source);
        return;
      }
    };
    const pointer = (raw: unknown) => {
      const event = raw as { axesInfo?: Array<{ axisDim: string; axisIndex: number; value: number }> };
      // ECharts may snap its active readout to an observed session. Broadcast
      // that displayed date, rather than the raw mouse pixel before snapping.
      const axis = event.axesInfo?.find((item) => item.axisDim === "x" && item.axisIndex === 0);
      if (axis) publishChartCursor(timeNavigation, Number(axis.value), source);
    };
    const leave = () => publishChartCursor(timeNavigation, null, source);
    const renderGuide = () => {
      if (chart.isDisposed()) return;
      const time = linkedTime;
      const visible = timeNavigation.getDomain();
      chart.dispatchAction({ type: "updateAxisPointer", currTrigger: "leave" }, { silent: true });
      chart.dispatchAction({ type: "hideTip" }, { silent: true });
      if (time === null || time < visible.start || time > visible.end) {
        setLinkedCursor(null);
        return;
      }
      const x = Number(chart.convertToPixel({ xAxisIndex: 0 }, time));
      // A coordinate guide must not snap to the nearest execution in another
      // pane, or label that old event as a new observation at the cursor date.
      let top = -1, bottom = -1;
      for (let y = 0; y < chart.getHeight(); y += 2) {
        if (chart.containPixel({ gridIndex: 0 }, [x, y])) { if (top < 0) top = y; bottom = y; }
      }
      setLinkedCursor(top >= 0 ? { x, top, height: bottom - top } : null);
    };
    const unsubscribe = subscribeChartCursor(timeNavigation, (time, origin) => {
      if (origin === source) return;
      linkedTime = time;
      renderGuide();
    });
    const unsubscribeDomain = timeNavigation.subscribe(renderGuide);
    chart.getZr().on("mousemove", move);
    chart.getZr().on("globalout", leave);
    chart.on("updateAxisPointer", pointer);
    return () => {
      unsubscribe();
      unsubscribeDomain();
      publishChartCursor(timeNavigation, null, source);
      if (!chart.isDisposed()) { chart.getZr().off("mousemove", move); chart.getZr().off("globalout", leave); chart.off("updateAxisPointer", pointer); }
    };
  }, [timeNavigation]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const keyChanged = resetKeyRef.current !== resetKey;
    resetKeyRef.current = resetKey;
    if (keyChanged) timeNavigationRef.current?.reset();
    const datePointer = (axis: Record<string, unknown>) => {
      const pointer = (axis.axisPointer ?? {}) as Record<string, unknown>;
      return { ...axis, axisPointer: { ...pointer, snap: true, label: {
        ...((pointer.label ?? {}) as Record<string, unknown>),
        formatter: ({ value }: { value: number }) => new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(value),
      } } };
    };
    const xAxis = option.xAxis as Record<string, unknown> | Record<string, unknown>[] | undefined;
    const datedOption = timeNavigation && xAxis ? { ...option, xAxis: Array.isArray(xAxis) ? xAxis.map(datePointer) : datePointer(xAxis) } : option;
    chart.setOption(datedOption, { notMerge: true });
    setLinkedCursor(null);
    const domain = timeNavigationRef.current?.getDomain();
    if (domain) applyChartDomain(domain);
  }, [option, resetKey, locale, timeNavigation]);

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
  const exportPng = () => {
    const chart = chartRef.current;
    if (!chart) return;
    const background = getComputedStyle(containerRef.current ?? document.body).backgroundColor || "#ffffff";
    const dataUrl = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: background });
    const safeName = label.replace(/[^\w\u4e00-\u9fff.-]+/g, "_");
    downloadPngDataUrl(dataUrl, `${safeName}.png`);
  };

  return <div tabIndex={timeNavigation ? 0 : undefined} onKeyDown={onKeyDown} ref={containerRef} className={cn("echart", className)} style={{ position: "relative" }} role="img" aria-label={label}>
    {linkedCursor && <div aria-hidden="true" data-linked-time-cursor style={{ position: "absolute", pointerEvents: "none", zIndex: 2,
      left: linkedCursor.x, top: linkedCursor.top, height: linkedCursor.height, borderLeft: "1px dashed rgba(170,210,234,.65)" }} />}
    {exportable && <button
      type="button"
      onClick={exportPng}
      className="absolute right-2 top-2 z-[3] rounded-md border border-border/60 bg-background/70 px-2 py-1 text-xs text-muted backdrop-blur hover:text-foreground"
      aria-label={`${label} · PNG`}
      title="PNG"
    >PNG ↓</button>}
  </div>;
}
