import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { dispose, init, registerIndicator, registerOverlay, type Chart, type IndicatorDrawCallback, type IndicatorDrawParams, type KLineData } from "klinecharts";

import type { PositionDecisionView, PositionEpisodeEntryView } from "@/data/positionEpisode";
import type { CompareView } from "@/data/sameStock";
import { comparisonBarGroups, comparisonBarStates, type ComparisonBarGroup } from "./sameStockStandardModel";
import { useLocale } from "@/locales/LocaleProvider";
import { showcaseInstrumentName } from "@/data/showcaseDemo";
import {
  aggregateStandardBars,
  barTimestamp,
  focusForChartBars,
  groupChartDecisionsForBars,
  positionStepsForChartBars,
  utcSessionDate,
  type ChartDecisionGroup,
  type StandardChartInterval,
  type StandardChartMarket,
} from "./standardChartModel";

import "./investment-chart-workspace.css";

export type { StandardBar, StandardChartMarket } from "./standardChartModel";

type ChartData = KLineData & { quantity?: number | null; averageCost?: number | null; quantityB?: number | null; averageCostB?: number | null; chartIndex?: number };

let backendIndicatorsRegistered = false;

function ensureBackendIndicators() {
  if (backendIndicatorsRegistered) return;
  backendIndicatorsRegistered = true;
  for (const key of ["quantity", "averageCost", "quantityB", "averageCostB"] as const) {
    const cost = key.startsWith("averageCost");
    registerIndicator({
      name: `Compare_${key}`, shortName: `${key.endsWith("B") ? "B" : "A"} ${cost ? "Cost" : "Qty"}`,
      series: cost ? "price" : "normal", precision: cost ? 2 : 0,
      ...(cost ? {} : { minValue: 0 }),
      figures: [{ key, type: "line", styles: () => ({ color: "transparent", size: 0 }) }],
      calc: (data: KLineData[]) => data.map(item => ({ [key]: (item as ChartData)[key] ?? null })),
      draw: drawStepSeries<Record<string, number | null>, string>(key, key.endsWith("B") ? "#debfa1" : "#8cdaf2", cost ? (key.endsWith("B") ? [8, 4] : [3, 3]) : (key.endsWith("B") ? [7, 3] : [])),
    });
  }
  registerOverlay({
    name: "ToujingComparisonTrade", totalStep: 2, needDefaultPointFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      const point = coordinates[0];
      if (!point) return [];
      const meta = overlay.extendData as { label: string; party: "A" | "B"; highlighted: boolean };
      const color = meta.party === "A" ? "#8cdaf2" : "#debfa1";
      // A labels above and B below the candle, never shifted along the time axis.
      const y = point.y + (meta.party === "A" ? -28 : 28);
      return [
        { type: "line", attrs: { coordinates: [point, { x: point.x, y }] }, styles: { color, style: "solid" }, ignoreEvent: true },
        { type: "text", attrs: { x: point.x, y, text: meta.label, align: "center", baseline: "middle" }, styles: { color, backgroundColor: "rgba(30,49,65,.85)", borderColor: meta.highlighted ? color : "transparent", borderSize: meta.highlighted ? 1 : 0, borderRadius: 4, paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4, size: meta.highlighted ? 14 : 12 }, ignoreEvent: false },
      ];
    },
  });
  registerIndicator({
    name: "BackendQuantity",
    shortName: "Held quantity",
    series: "normal",
    precision: 0,
    minValue: 0,
    // The transparent figure is still required by KLineChart's y-axis range calculator;
    // custom draw returns true so the visible path remains our step path.
    figures: [{ key: "quantity", type: "line", styles: () => ({ color: "transparent", size: 0 }) }],
    calc: (data: KLineData[]) => data.map((item) => ({ quantity: (item as ChartData).quantity ?? null })),
    draw: drawStepSeries<{ quantity: number | null }, "quantity">("quantity", "rgba(144, 222, 253, .95)", []),
  });
  registerIndicator({
    name: "BackendAverageCost",
    shortName: "Back-end average cost",
    series: "price",
    precision: 2,
    figures: [{ key: "averageCost", type: "line", styles: () => ({ color: "transparent", size: 0 }) }],
    calc: (data: KLineData[]) => data.map((item) => ({ averageCost: (item as ChartData).averageCost ?? null })),
    // A step is intentional: values are replay states at daily close, not a price-derived path.
    draw: drawStepSeries<{ averageCost: number | null }, "averageCost">("averageCost", "rgba(250, 202, 112, .9)", [5, 3]),
  });
  registerOverlay({
    name: "ToujingTradeMarker", totalStep: 2, needDefaultPointFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      const point = coordinates[0];
      if (!point) return [];
      const labelY = point.y - 24;
      return [
        { type: "line", attrs: { coordinates: [point, { x: point.x, y: labelY + 6 }] }, styles: { color: "#9cdcf6", style: "solid" }, ignoreEvent: true },
        { type: "text", attrs: { x: point.x, y: labelY, text: String(overlay.extendData), align: "center", baseline: "middle" }, styles: { color: "#d8f3ff", backgroundColor: "#213e54", borderRadius: 4, paddingLeft: 5, paddingRight: 5, paddingTop: 3, paddingBottom: 3, size: 11 }, ignoreEvent: false },
      ];
    },
  });
  registerOverlay({
    name: "ToujingCostLabel", totalStep: 2, needDefaultPointFigure: false,
    createPointFigures: ({ coordinates, overlay, bounding }) => {
      const point = coordinates[0];
      if (!point) return [];
      const x = Math.min(bounding.width - 8, Math.max(130, point.x));
      return [{ type: "text", attrs: { x, y: point.y - 8, text: `${String(overlay.extendData)} ↙`, align: "right", baseline: "bottom" }, styles: { color: "#faca70", backgroundColor: "rgba(10,22,34,.85)", borderRadius: 3, paddingLeft: 4, paddingRight: 4, size: 11 }, ignoreEvent: true }];
    },
  });
}

function dateLabel(date: string, locale: string) {
  const timestamp = barTimestamp(date);
  return Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }).format(timestamp)
    : date;
}

function fixed(value: number | null | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function drawStepSeries<D extends Record<K, number | null>, K extends string>(key: K, color: string, dashed: number[]): IndicatorDrawCallback<D, unknown, unknown> {
  return ({ ctx, chart, indicator, xAxis, yAxis }: IndicatorDrawParams<D, unknown, unknown>) => {
    const points = chart.getDataList() as ChartData[];
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash(dashed);
    let previous: { x: number; y: number } | null = null;
    ctx.beginPath();
    indicator.result.forEach((result, index) => {
      const value = result?.[key];
      if (typeof value !== "number" || !Number.isFinite(value) || !points[index]) { previous = null; return; }
      const current = { x: xAxis.convertTimestampToPixel(points[index].timestamp), y: yAxis.convertToPixel(value) };
      if (previous) { ctx.lineTo(current.x, previous.y); ctx.lineTo(current.x, current.y); }
      else ctx.moveTo(current.x, current.y);
      previous = current;
    });
    ctx.stroke();
    ctx.restore();
    return true;
  };
}

function decisionTitle(decision: PositionDecisionView, chinese: boolean) {
  const labels = chinese
    ? { open_position: "建仓", add_position: "加仓", reduce_position: "减仓", close_position: "平仓" }
    : { open_position: "Open", add_position: "Add", reduce_position: "Reduce", close_position: "Close" };
  return labels[decision.decisionType];
}

function operationGroup(group: ChartDecisionGroup | null, locale: string, currency: string, onSelectDecision?: (id: string) => void) {
  if (!group) return null;
  const chinese = locale.startsWith("zh");
  const money = new Intl.NumberFormat(locale, { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sessions = group.sessionDates.map((date) => dateLabel(date, locale));
  return <section className="investment-chart-operations" aria-live="polite">
    <div className="investment-chart-operations-title">
      <span>{sessions.length === 1 ? sessions[0] : `${sessions[0]} – ${sessions[sessions.length - 1]}`}</span>
      <span>{chinese ? `${group.decisions.length} 笔模拟操作` : `${group.decisions.length} simulated operation${group.decisions.length === 1 ? "" : "s"}`}</span>
    </div>
    <div className="investment-chart-operation-list">
      {group.decisions.map((decision) => <button key={decision.decisionId} type="button" className="investment-chart-operation" onClick={() => onSelectDecision?.(decision.decisionId)}>
        <span className="investment-chart-operation-time">{utcSessionDate(decision.occurredAt)} · {decision.occurredAt.slice(11)}</span>
        <strong>{decisionTitle(decision, chinese)}</strong>
        <span>{chinese ? "数量" : "Qty"} {fixed(decision.executedQuantity, 0)} · {money.format(decision.executionPrice)}</span>
        <span>{chinese ? "持仓" : "Holding"} {fixed(decision.stateBefore.quantity, 0)} → {fixed(decision.stateAfter.quantity, 0)}</span>
        <span>{chinese ? "成本" : "Cost"} {decision.stateBefore.averageCost === null ? "—" : money.format(decision.stateBefore.averageCost)} → {decision.stateAfter.averageCost === null ? "—" : money.format(decision.stateAfter.averageCost)}</span>
      </button>)}
    </div>
  </section>;
}

export function InvestmentChartWorkspace({
  entry,
  market,
  focus = null,
  onSelectDecision,
  comparison,
}: {
  entry: PositionEpisodeEntryView;
  market: StandardChartMarket;
  focus?: { id: string; startAt: string; endAt: string } | null;
  onSelectDecision?: (id: string) => void;
  comparison?: { view: CompareView; labelA: string; labelB: string; highlightedIds: string[] };
}) {
  const { locale } = useLocale();
  const chinese = locale.startsWith("zh");
  const displayName = showcaseInstrumentName(market.instrumentId, locale, market.displayName);
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const [interval, setInterval] = useState<StandardChartInterval>("day");
  const [lineMode, setLineMode] = useState(false);
  const [showMa, setShowMa] = useState(false);
  const [showVolume, setShowVolume] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<ChartDecisionGroup | null>(null);
  const [readout, setReadout] = useState<ChartData | null>(null);
  const [selectedComparisonGroups, setSelectedComparisonGroups] = useState<ComparisonBarGroup[]>([]);
  const [showCosts, setShowCosts] = useState(true);
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 0 });

  useEffect(() => {
    if (!fullScreen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setFullScreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullScreen]);

  useEffect(() => {
    if (!fullScreen || !comparison) return;
    const shell = document.querySelector<HTMLElement>(".workspace-shell");
    if (!shell) return;
    const wasInert = shell.inert;
    shell.inert = true;
    shell.classList.add("comparison-focus-active");
    return () => { shell.inert = wasInert; shell.classList.remove("comparison-focus-active"); };
  }, [fullScreen, comparison]);

  const bars = useMemo(() => aggregateStandardBars(market.bars, interval), [interval, market.bars]);
  const steps = useMemo(() => comparison ? comparisonBarStates(comparison.view.a, market.bars, bars) : positionStepsForChartBars(entry, market.bars, bars, interval), [bars, entry, interval, market.bars, comparison]);
  const stepsB = useMemo(() => comparison ? comparisonBarStates(comparison.view.b, market.bars, bars) : [], [bars, market.bars, comparison]);
  const comparisonGroups = useMemo(() => comparison ? comparisonBarGroups(comparison.view, market.bars, bars) : [], [comparison, market.bars, bars]);
  const groups = useMemo(() => groupChartDecisionsForBars(entry, bars, interval), [bars, entry, interval]);
  const visibleTicker = market.instrumentId.replace(/^SYN_/, "").replace(/_HISTORY$/, "") || market.displayName;
  const data = useMemo<ChartData[]>(() => bars.map((bar, index) => ({
    timestamp: barTimestamp(bar.date), open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    ...(bar.volume === null ? {} : { volume: bar.volume }),
    ...(bar.amount === null ? {} : { turnover: bar.amount }),
    quantity: steps[index]?.quantity ?? null,
    averageCost: steps[index]?.averageCost ?? null,
    quantityB: stepsB[index]?.quantity ?? null,
    averageCostB: stepsB[index]?.averageCost ?? null,
    chartIndex: index,
  })), [bars, steps, stepsB]);
  const focusWindow = useMemo(() => focusForChartBars(market.bars, bars, focus ?? {
    startAt: entry.episode.openedAt,
    endAt: entry.episode.closedAt ?? entry.snapshot?.positionState.valuationAt ?? entry.episode.openedAt,
  }, 7), [market.bars, bars, entry.episode.closedAt, entry.episode.openedAt, entry.snapshot?.positionState.valuationAt, focus]);
  const groupByTimestamp = useMemo(() => new Map(groups.map((group) => [barTimestamp(group.date), group])), [groups]);

  useEffect(() => {
    const initial = focusWindow ?? { startIndex: 0, endIndex: Math.max(0, data.length - 1) };
    setVisibleRange({ start: initial.startIndex, end: initial.endIndex });
  }, [data.length, focusWindow]);

  const applyVisibleRange = useCallback((start: number, end: number) => {
    const chart = chartRef.current;
    const host = hostRef.current;
    const nextStart = Math.max(0, Math.min(start, Math.max(0, data.length - 1)));
    const nextEnd = Math.max(nextStart, Math.min(end, Math.max(0, data.length - 1)));
    setVisibleRange({ start: nextStart, end: nextEnd });
    if (!chart || !host || !data.length) return;
    const plotWidth = chart.getSize("candle_pane", "main")?.width ?? host.clientWidth - 60;
    chart.setBarSpace(Math.max(0.25, Math.min(160, plotWidth / Math.max(1, nextEnd - nextStart + 1))));
    // KLineChart's scrollToDataIndex puts the requested candle at the right edge.
    chart.scrollToDataIndex(nextEnd);
  }, [data.length]);

  const resetView = useCallback((mode: "episode" | "all" = "episode") => {
    const target = mode === "episode" && focusWindow ? focusWindow : { startIndex: 0, endIndex: Math.max(0, data.length - 1) };
    applyVisibleRange(target.startIndex, target.endIndex);
  }, [applyVisibleRange, data.length, focusWindow]);

  useEffect(() => {
    setSelectedGroup(null);
    setSelectedComparisonGroups([]);
    setReadout(null);
  }, [market.instrumentId, entry.episode.episodeId, interval]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !data.length) return undefined;
    ensureBackendIndicators();
    const chart = init(host, {
      locale: chinese ? "zh-CN" : "en-US",
      timezone: "UTC",
      zoomAnchor: "cursor",
      layout: { barSpaceLimit: { min: 0.25, max: 160 } },
      styles: {
        grid: { horizontal: { show: true, color: "rgba(160, 184, 210, .09)" }, vertical: { show: true, color: "rgba(160, 184, 210, .06)" } },
        candle: {
          type: lineMode ? "area" : "candle_solid",
          bar: { upColor: "#69d5bb", downColor: "#ff8f9c", noChangeColor: "#9aadbf", upBorderColor: "#69d5bb", downBorderColor: "#ff8f9c", noChangeBorderColor: "#9aadbf", upWickColor: "#8ae6ce", downWickColor: "#ffabb4", noChangeWickColor: "#9aadbf", compareRule: "current_open" },
          area: { lineColor: "#83d8ff", lineSize: 2, value: "close", smooth: false, backgroundColor: "rgba(89, 183, 232, .12)", point: { show: false, color: "#83d8ff", radius: 2 } },
          tooltip: { showRule: "none" },
          priceMark: { last: { show: false } },
        },
        indicator: { tooltip: { showRule: "follow_cross" } },
        xAxis: { tickText: { color: "rgba(205, 220, 234, .72)", size: 11 }, axisLine: { color: "rgba(160, 184, 210, .18)", show: true }, tickLine: { show: false } },
        yAxis: { tickText: { color: "rgba(205, 220, 234, .72)", size: 11 }, axisLine: { color: "rgba(160, 184, 210, .18)", show: true }, tickLine: { show: false } },
        crosshair: { horizontal: { line: { color: "rgba(157, 219, 255, .46)", size: 1, style: "dashed", dashedValue: [4, 2], show: true }, text: { color: "#05101a", size: 11, family: "ui-monospace", weight: "500", backgroundColor: "#b9e9ff", paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2, borderRadius: 2, borderSize: 0, borderColor: "transparent", style: "fill" }, show: true, features: [] }, vertical: { line: { color: "rgba(157, 219, 255, .3)", size: 1, style: "dashed", dashedValue: [4, 2], show: true }, text: { color: "#05101a", size: 11, family: "ui-monospace", weight: "500", backgroundColor: "#b9e9ff", paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2, borderRadius: 2, borderSize: 0, borderColor: "transparent", style: "fill" }, show: true } },
      },
    });
    if (!chart) return undefined;
    chartRef.current = chart;
    chart.setSymbol({ ticker: visibleTicker, pricePrecision: 2, volumePrecision: 0 });
    chart.setPeriod({ type: "day", span: 1 });
    chart.setDataLoader({ getBars: ({ callback }) => callback(data, false) });
    if (comparison) chart.overrideYAxis({ paneId: "candle_pane", gap: { top: 0.22, bottom: 0.22 } });
    if (comparison) {
      for (const key of ["quantity", "quantityB", ...(showCosts ? ["averageCost", "averageCostB"] : [])]) {
        chart.createIndicator({ name: `Compare_${key}`, paneId: key.startsWith("quantity") ? "quantity-pane" : "candle_pane", styles: { tooltip: { showRule: "none" } } }, true);
      }
    } else {
      chart.createIndicator({ name: "BackendQuantity", paneId: "quantity-pane", shortName: chinese ? "持仓数量" : "Held quantity" });
      chart.createIndicator({ name: "BackendAverageCost", paneId: "candle_pane", shortName: chinese ? "平均成本（周期末）" : "Avg cost (period end)" });
    }
    if (showVolume) chart.createIndicator({ name: "VOL", paneId: "volume-pane", styles: { tooltip: { showRule: "follow_cross" } } });
    if (showMa) chart.createIndicator({ name: "MA", paneId: "candle_pane", calcParams: [5, 10, 20], styles: { tooltip: { showRule: "follow_cross" } } }, true);
    chart.setPaneOptions({ id: "quantity-pane", height: 115, minHeight: 84, dragEnabled: false });
    if (showVolume) chart.setPaneOptions({ id: "volume-pane", height: 95, minHeight: 72, dragEnabled: false });
    chart.setOffsetRightDistance(0);
    chart.setMaxOffsetLeftDistance(0);
    chart.setMaxOffsetRightDistance(0);

    for (const group of comparison ? [] : groups) {
      const bar = bars.find((candidate) => candidate.date === group.date);
      if (!bar) continue;
      const point = { timestamp: barTimestamp(group.date), value: bar.high };
      chart.createOverlay({ name: "ToujingTradeMarker", points: [point, point], extendData: group.decisions.length > 1 ? `${group.decisions.length}×` : decisionTitle(group.decisions[0], chinese), lock: true, fixedZLevel: true, onClick: () => setSelectedGroup(group) });
    }
    for (const group of comparisonGroups) {
      const bar = bars.find(candidate => candidate.date === group.date);
      if (!bar) continue;
      const title = group.decisions.length > 1 ? `${group.decisions.length} ${chinese ? "笔操作" : "trades"}` : decisionTitle({ decisionType: group.decisions[0].kind } as PositionDecisionView, chinese);
      const point = { timestamp: barTimestamp(group.date), value: group.party === "A" ? bar.high : bar.low };
      chart.createOverlay({ name: "ToujingComparisonTrade", points: [point, point], extendData: { party: group.party, label: `${group.party} ${title}`, highlighted: group.decisions.some(decision => comparison?.highlightedIds.includes(decision.id)) }, lock: true, fixedZLevel: true, onClick: () => {
        setSelectedComparisonGroups(comparisonGroups.filter(item => item.date === group.date));
        onSelectDecision?.(group.decisions[0].id);
      } });
    }
    const updateCostLabel = (lastIndex: number) => {
      if (comparison) return;
      let index = Math.min(lastIndex, steps.length - 1);
      while (index >= 0 && steps[index]?.averageCost === null) index -= 1;
      const cost = index >= 0 ? steps[index]?.averageCost : null;
      if (cost === null || cost === undefined || !bars[index]) return;
      const point = { timestamp: barTimestamp(bars[index].date), value: cost };
      chart.overrideOverlay({ id: "avg-cost-label", points: [point, point], extendData: `${chinese ? "平均成本" : "Avg cost"} ${fixed(cost)}`, visible: true });
    };
    let initialCostIndex = steps.length - 1;
    while (initialCostIndex >= 0 && steps[initialCostIndex]?.averageCost === null) initialCostIndex -= 1;
    const initialCost = initialCostIndex >= 0 ? steps[initialCostIndex]?.averageCost : null;
    if (!comparison && typeof initialCost === "number" && bars[initialCostIndex]) {
      const point = { timestamp: barTimestamp(bars[initialCostIndex].date), value: initialCost };
      chart.createOverlay({ id: "avg-cost-label", name: "ToujingCostLabel", points: [point, point], extendData: `${chinese ? "平均成本" : "Avg cost"} ${fixed(initialCost)}`, lock: true, fixedZLevel: true });
    }

    const onCrosshair = (value?: unknown) => {
      // KLine v10 action callbacks receive only the incoming x/y/paneId.
      // Convert the coordinate back through the live chart instead of expecting kLineData.
      const event = value as { x?: number } | undefined;
      if (typeof event?.x !== "number") { setReadout(null); return; }
      const converted = chart.convertFromPixel([{ x: event.x }], { paneId: "candle_pane" });
      const index = Array.isArray(converted) ? converted[0]?.dataIndex : undefined;
      setReadout(typeof index === "number" ? data[Math.round(index)] ?? null : null);
    };
    const onCandleClick = (value?: unknown) => {
      const event = value as { timestamp?: number } | undefined;
      if (comparison && typeof event?.timestamp === "number") {
        setSelectedComparisonGroups(comparisonGroups.filter(group => barTimestamp(group.date) === event.timestamp));
        return;
      }
      if (typeof event?.timestamp === "number") setSelectedGroup(groupByTimestamp.get(event.timestamp) ?? null);
    };
    chart.subscribeAction("onCrosshairChange", onCrosshair);
    chart.subscribeAction("onCandleBarClick", onCandleClick);
    const onVisibleRange = (value?: unknown) => {
      const range = value as { from?: number; to?: number } | undefined;
      if (typeof range?.from === "number" && typeof range?.to === "number") {
        setVisibleRange({ start: range.from, end: Math.max(range.from, range.to - 1) });
        updateCostLabel(range.to - 1);
      }
    };
    chart.subscribeAction("onVisibleRangeChange", onVisibleRange);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    let gestureActive = false;
    let gestureScale = 1;
    const wheelHost = host.parentElement ?? host;
    const onWheel = (event: WheelEvent) => {
      if (!(event.target instanceof Node) || !host.contains(event.target)) return;
      const chartGesture = gestureActive || Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.ctrlKey || event.metaKey;
      // The KLine canvas also listens for wheel input. Stop it at this outer
      // capture boundary so vertical wheels still perform their native page scroll.
      event.stopImmediatePropagation();
      if (!chartGesture) {
        // Explicitly pass vertical movement to the enclosing page. Some WebKit
        // canvas hosts otherwise consume the wheel despite a non-cancelled event.
        let scroller: HTMLElement | null = host.parentElement;
        while (scroller) {
          const movable = event.deltaY < 0 ? scroller.scrollTop > 0 : scroller.scrollTop + scroller.clientHeight < scroller.scrollHeight;
          if (movable && /auto|scroll/.test(getComputedStyle(scroller).overflowY)) {
            if (event.cancelable) {
              event.preventDefault();
              const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? scroller.clientHeight : 1;
              scroller.scrollBy({ top: event.deltaY * factor, behavior: "instant" });
            }
            return;
          }
          scroller = scroller.parentElement;
        }
        return;
      }
      if (!event.cancelable) return;
      event.preventDefault();
      if (gestureActive) return;
      if (event.ctrlKey || event.metaKey) {
        chart.zoomAtCoordinate(Math.exp(-event.deltaY / 360), { x: event.clientX - host.getBoundingClientRect().left, y: event.clientY - host.getBoundingClientRect().top });
      } else chart.scrollByDistance(-event.deltaX);
    };
    const onGestureStart = (event: Event) => { gestureActive = true; gestureScale = 1; event.stopPropagation(); if (event.cancelable) event.preventDefault(); };
    const onGestureChange = (event: Event) => {
      const gesture = event as Event & { scale?: number; clientX?: number; clientY?: number };
      if (!gestureActive || typeof gesture.scale !== "number") return;
      event.stopPropagation(); if (event.cancelable) event.preventDefault();
      chart.zoomAtCoordinate(gesture.scale / gestureScale, { x: (gesture.clientX ?? host.getBoundingClientRect().left + host.clientWidth / 2) - host.getBoundingClientRect().left, y: (gesture.clientY ?? host.getBoundingClientRect().top + host.clientHeight / 2) - host.getBoundingClientRect().top });
      gestureScale = gesture.scale;
    };
    const onGestureEnd = () => { gestureActive = false; gestureScale = 1; };
    wheelHost.addEventListener("wheel", onWheel, { passive: false, capture: true });
    host.addEventListener("gesturestart", onGestureStart, { passive: false, capture: true });
    host.addEventListener("gesturechange", onGestureChange, { passive: false, capture: true });
    host.addEventListener("gestureend", onGestureEnd, true);
    const frame = requestAnimationFrame(() => {
      const initial = focusWindow ?? { startIndex: 0, endIndex: Math.max(0, data.length - 1) };
      const plotWidth = chart.getSize("candle_pane", "main")?.width ?? host.clientWidth - 60;
      chart.setBarSpace(Math.max(0.25, Math.min(160, plotWidth / Math.max(1, initial.endIndex - initial.startIndex + 1))));
      chart.scrollToDataIndex(initial.endIndex);
      updateCostLabel(chart.getVisibleRange().to - 1);
    });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      wheelHost.removeEventListener("wheel", onWheel, true);
      host.removeEventListener("gesturestart", onGestureStart, true);
      host.removeEventListener("gesturechange", onGestureChange, true);
      host.removeEventListener("gestureend", onGestureEnd, true);
      chart.unsubscribeAction("onCrosshairChange", onCrosshair);
      chart.unsubscribeAction("onCandleBarClick", onCandleClick);
      chart.unsubscribeAction("onVisibleRangeChange", onVisibleRange);
      dispose(chart);
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [bars, chinese, data, focusWindow, fullScreen, groupByTimestamp, groups, lineMode, showMa, showVolume, steps, visibleTicker, comparison, comparisonGroups, showCosts, onSelectDecision]);

  const price = readout?.close ?? null;
  const step = typeof readout?.chartIndex === "number" ? steps[readout.chartIndex] ?? null : null;
  const money = new Intl.NumberFormat(locale, { style: "currency", currency: market.currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const activeInterval = (value: StandardChartInterval) => interval === value ? "is-active" : "";

  const workspace = <section className={`investment-chart-workspace ${comparison ? "is-comparison" : ""} ${fullScreen ? "is-fullscreen" : ""}`} role={fullScreen ? "dialog" : undefined} aria-modal={fullScreen || undefined} aria-label={chinese ? `${displayName} 标准历史图表` : `${displayName} standard historical chart`}>
    <header className="investment-chart-head">
      <div><p className="investment-chart-kicker">{market.priceBasis === "synthetic_unadjusted" ? (chinese ? "模拟行情 · 模拟交易" : "Simulated prices · simulated trades") : (chinese ? "历史市场数据 · 模拟交易" : "Historical market data · simulated trades")}</p><h2>{displayName}</h2></div>
      <div className="investment-chart-boundary">{market.currency} · {market.priceBasis === "synthetic_unadjusted" ? (chinese ? "模拟未复权价格" : "Simulated unadjusted prices") : (chinese ? "历史复权口径" : "Source-adjusted history")} · {bars.length} {chinese ? "根" : "bars"}</div>
    </header>
    {comparison ? <div className="comparison-chart-identities">
      <span className="comparison-party-a"><strong>A</strong> {comparison.labelA}</span>
      <span className="comparison-party-b"><strong>B</strong> {comparison.labelB}</span>
      <span>{chinese ? "同一行情 · 上方标签 A / 下方标签 B · 点击查看成交" : "Shared market · A above / B below · Click to inspect trades"}</span>
    </div> : null}
    <div className="investment-chart-toolbar" role="toolbar" aria-label={chinese ? "图表工具" : "Chart tools"}>
      <div className="investment-chart-tool-group"><button type="button" className={activeInterval("day")} onClick={() => setInterval("day")}>{chinese ? "日K" : "Day"}</button><button type="button" className={activeInterval("week")} onClick={() => setInterval("week")}>{chinese ? "周K" : "Week"}</button><button type="button" className={activeInterval("month")} onClick={() => setInterval("month")}>{chinese ? "月K" : "Month"}</button><button type="button" className={lineMode ? "is-active" : ""} onClick={() => setLineMode((value) => !value)}>{chinese ? "折线" : "Line"}</button></div>
      <div className="investment-chart-tool-group"><button type="button" className={showMa ? "is-active" : ""} aria-pressed={showMa} onClick={() => setShowMa((value) => !value)}>MA {chinese ? "(价格)" : "(price)"}</button>{comparison ? <button type="button" className={showCosts ? "is-active" : ""} aria-pressed={showCosts} onClick={() => setShowCosts(value => !value)}>{chinese ? "双方平均成本" : "Both avg costs"}</button> : null}<button type="button" className="is-active" aria-pressed="true">{comparison ? (chinese ? "双方持仓数量" : "Both holdings") : (chinese ? "持仓数量" : "Held qty")}</button><button type="button" className={showVolume ? "is-active" : ""} aria-pressed={showVolume} onClick={() => setShowVolume((value) => !value)}>{chinese ? "成交量" : "Volume"}</button></div>
      <div className="investment-chart-tool-group investment-chart-view-tools"><button type="button" onClick={() => chartRef.current?.zoomAtCoordinate(1.05)} aria-label={chinese ? "放大" : "Zoom in"}>+</button><button type="button" onClick={() => chartRef.current?.zoomAtCoordinate(0.95)} aria-label={chinese ? "缩小" : "Zoom out"}>−</button><button type="button" onClick={() => resetView("episode")}>{chinese ? "重置" : "Reset"}</button><button type="button" onClick={() => resetView("all")}>{chinese ? "全历史" : "All history"}</button><button type="button" aria-pressed={fullScreen} onClick={() => setFullScreen((value) => !value)}>{fullScreen ? (chinese ? "退出全屏" : "Exit focus") : (chinese ? "专注" : "Focus")}</button></div>
    </div>
    <div className="investment-chart-readout"><span>{readout ? dateLabel(new Date(readout.timestamp).toISOString().slice(0, 10), locale) : (chinese ? "移动光标查看" : "Move cursor to inspect")}</span><span>{comparison && chinese ? "开" : "O"} {fixed(readout?.open)} {comparison && chinese ? "高" : "H"} {fixed(readout?.high)} {comparison && chinese ? "低" : "L"} {fixed(readout?.low)} {comparison && chinese ? "收" : "C"} {price === null ? "—" : money.format(price)}</span><span>{chinese ? "量" : "Vol"} {fixed(readout?.volume ?? null, 0)}</span>{!comparison ? <span>{chinese ? "持仓" : "Held"} {fixed(step?.quantity, 0)} · {chinese ? "平均成本" : "Avg cost"} {step?.averageCost === null || step?.averageCost === undefined ? "—" : money.format(step.averageCost)}</span> : null}</div>
    {comparison ? <div className="comparison-chart-readouts" data-guide="same-stock-quantity">
      {(["A", "B"] as const).map(party => <div key={party} className={party === "A" ? "comparison-party-a" : "comparison-party-b"}>
        <strong>{party}</strong><span>{chinese ? "持仓" : "Held"} {fixed(party === "A" ? readout?.quantity : readout?.quantityB, 0)} {chinese ? "股" : "shares"}</span>
        <span>{chinese ? "平均成本" : "Avg cost"} {fixed(party === "A" ? readout?.averageCost : readout?.averageCostB)} {market.currency}</span>
        <span>{party === "A" ? (chinese ? "实线持仓 · 短虚线成本" : "Solid holdings · short-dash cost") : (chinese ? "虚线持仓 · 长虚线成本" : "Dashed holdings · long-dash cost")}</span>
      </div>)}
    </div> : null}
    <div data-guide={comparison ? "same-stock-price" : "episode-price-cost"} className="investment-chart-canvas-guide">
      <div ref={hostRef} className="investment-chart-canvas" />
      <div data-guide="episode-quantity" className="investment-chart-quantity-guide-target" />
    </div>
    <div className="investment-chart-navigator" aria-label={chinese ? "历史范围" : "Historical range"}>
      <span>{dateLabel(bars[Math.max(0, visibleRange.start)]?.date ?? "", locale)}</span>
      <div className="investment-chart-range-controls">
        <input type="range" min={0} max={Math.max(0, data.length - 1)} value={Math.min(visibleRange.start, Math.max(0, visibleRange.end - 1))} aria-label={chinese ? "范围开始" : "Range start"} onChange={(event) => applyVisibleRange(Math.min(Number(event.target.value), visibleRange.end - 1), visibleRange.end)} />
        <input type="range" min={0} max={Math.max(0, data.length - 1)} value={Math.max(visibleRange.end, Math.min(data.length - 1, visibleRange.start + 1))} aria-label={chinese ? "范围结束" : "Range end"} onChange={(event) => applyVisibleRange(visibleRange.start, Math.max(Number(event.target.value), visibleRange.start + 1))} />
      </div>
      <span>{dateLabel(bars[Math.max(0, visibleRange.end)]?.date ?? "", locale)}</span>
    </div>
    <p className="investment-chart-hint">{chinese ? "横向双指滑动或拖动平移；捏合或 ⌘/Ctrl + 滚轮缩放；垂直滚动页面。数量与平均成本表示所选周期末的持仓状态。" : "Horizontal two-finger scroll or drag pans; pinch or Ctrl/⌘ + wheel zooms; vertical scroll moves the page. Quantity and average cost show period-end holdings."}</p>
    {comparison ? <section className="investment-chart-operations" data-guide="same-stock-trades">
      <div className="investment-chart-operations-title">{chinese ? "双方成交明细" : "Trades from both records"}<span>{chinese ? "选择图中标签，核对当时的价格与持仓变化" : "Select a label to inspect execution price and holdings"}</span></div>
      <div className="investment-chart-operation-list">
        {(selectedComparisonGroups.length ? selectedComparisonGroups : comparisonGroups).flatMap(group => group.decisions.map(decision => <button key={`${group.party}:${decision.id}`} className="investment-chart-operation" type="button" onClick={() => { setSelectedComparisonGroups(comparisonGroups.filter(item => item.date === group.date)); applyVisibleRange(Math.max(0, bars.findIndex(bar => bar.date === group.date) - 7), Math.min(bars.length - 1, bars.findIndex(bar => bar.date === group.date) + 7)); onSelectDecision?.(decision.id); }}>
          <span>{decision.at.replace("T", " ")}</span><strong className={group.party === "A" ? "comparison-party-a" : "comparison-party-b"}>{group.party} {decisionTitle({ decisionType: decision.kind } as PositionDecisionView, chinese)}</strong>
          <span>{fixed(decision.quantity, 0)} {chinese ? "股" : "shares"} · {money.format(decision.price)}</span><span>{chinese ? "持仓" : "Held"} {decision.before} → {decision.after}</span>
          <span>{chinese ? "成本" : "Cost"} {fixed(decision.costBefore)} → {fixed(decision.costAfter)}</span>
        </button>))}
      </div>
      {selectedComparisonGroups.length ? <button className="comparison-show-trades" type="button" onClick={() => setSelectedComparisonGroups([])}>{chinese ? "查看全部成交" : "Show all trades"}</button> : null}
    </section> : operationGroup(selectedGroup, locale, market.currency, onSelectDecision)}
    <footer className="investment-chart-source"><span>{market.priceBasis === "synthetic_unadjusted"
      ? (chinese ? "模拟行情与模拟成交 · 共用年度示例数据" : "Simulated prices and trades · Shared annual example")
      : (chinese ? "历史市场数据与模拟交易" : "Historical market data and simulated trades")}</span>{/^https:\/\//.test(market.sourceUrl) ? <a href={market.sourceUrl} target="_blank" rel="noreferrer">{chinese ? "来源与数据边界" : "Source and data boundary"}</a> : <span>{chinese ? "非真实证券行情" : "Not real security prices"}</span>}</footer>
  </section>;
  return fullScreen ? createPortal(workspace, document.body) : workspace;
}
