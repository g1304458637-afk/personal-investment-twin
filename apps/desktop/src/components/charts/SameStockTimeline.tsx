import { useCallback, useMemo } from "react";
import type { ECElementEvent, EChartsCoreOption } from "echarts/core";

import { EChart } from "./EChart";
import { dailyDataZoom, dailyTimeDomain, formatDailyAxisTick, minDailyZoomSpanMs, MS_PER_DAY } from "./dailyTimeAxis";
import type { DailyTimeNavigationStore } from "./useDailyTimeNavigation";
import { comparisonHighlight, executionLaneOffset, type CompareView } from "@/data/sameStock";
import { useLocale } from "@/locales/LocaleProvider";
import { sameStockCopy } from "@/components/review/sameStockCompareCopy";
import { sameStockParties, sameStockPartyLabel, sameStockTimelineTimes } from "./sameStockTimelineModel";
import { showcaseInstrumentName } from "@/data/showcaseDemo";

const executionSymbols: Record<string, string> = {
  open_position: "circle",
  add_position: "diamond",
  reduce_position: "triangle",
  close_position: "rect",
};

export function SameStockTimeline({
  view,
  selected,
  pathMode,
  focusedDecisionId,
  selectedDecisionId,
  timeNavigation,
  onSelectDecision,
}: {
  view: CompareView;
  selected: string | null;
  pathMode: "quantity" | "cost";
  focusedDecisionId?: string | null;
  selectedDecisionId?: string | null;
  timeNavigation?: DailyTimeNavigationStore;
  onSelectDecision?: (decisionId: string) => void;
}) {
  const { locale, t, formatNumber } = useLocale();
  const c = sameStockCopy(locale);
  const displaySymbol = (symbol: string) => showcaseInstrumentName(symbol, locale, symbol);
  const partyLabel = (party: ReturnType<typeof sameStockParties>[number]) => sameStockPartyLabel(party, c.record, displaySymbol(party.symbol));
  const operationLabel = (kind: string) => c.operationKinds[kind as keyof typeof c.operationKinds] ?? t(kind);
  const { observationTimes } = useMemo(() => sameStockTimelineTimes(view), [view]);
  const option = useMemo<EChartsCoreOption>(() => {
    const parties = sameStockParties(view);
    const highlighted = comparisonHighlight(view, selected);
    const activeDecisionIds = new Set([focusedDecisionId, selectedDecisionId].filter((id): id is string => typeof id === "string"));
    const timeValues = [
      ...view.prices.map((point) => point.at),
      ...parties.flatMap((party) => [
        ...party.side.decisions.map((decision) => decision.at),
        ...party.side.shape.map((point) => point.at),
      ]),
    ];
    const xDomain = dailyTimeDomain(timeValues);
    const markerHighlight = (partyId: "A" | "B", decisionId: string) =>
      activeDecisionIds.has(decisionId) || (partyId === "A" ? highlighted?.aRefs : highlighted?.bRefs)?.includes(decisionId);
    const area = highlighted ? {
      silent: true,
      itemStyle: { color: "rgba(122,204,237,0.09)" },
      data: [[{ xAxis: Date.parse(highlighted.start) }, { xAxis: Date.parse(highlighted.end) }]],
    } : undefined;
    const pathLabel = pathMode === "quantity" ? c.quantityPath : c.averageCostPath;
    const axes = [0, 1, 2].map((gridIndex) => ({
      type: "time" as const,
      gridIndex,
      minInterval: MS_PER_DAY,
      ...xDomain,
      axisLine: { lineStyle: { color: "rgba(148,177,204,.2)" } },
      axisTick: { show: false },
      axisLabel: { color: "rgba(177,196,214,.72)", hideOverlap: true, formatter: (value: number) => formatDailyAxisTick(value, locale) },
      splitLine: { show: false },
    }));
    const zoom = dailyDataZoom(4, minDailyZoomSpanMs(observationTimes))
      .filter((control) => control.type !== "slider")
      .map((control) => ({ ...control, xAxisIndex: [0, 1, 2] }));
    return {
      animationDuration: 260,
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [
        // Identical plot rails keep every timestamp vertically aligned across the three panes.
        { left: 120, right: 24, top: 28, height: 200, outerBoundsMode: "none" },
        { left: 120, right: 24, top: 270, height: 85, outerBoundsMode: "none" },
        { left: 120, right: 24, top: 398, height: 135, outerBoundsMode: "none" },
      ],
      xAxis: axes,
      yAxis: [
        { type: "value", name: c.marketPriceUnit, nameTextStyle: { color: "rgba(177,196,214,.58)", fontSize: 10 }, scale: true, axisLabel: { color: "rgba(177,196,214,.72)", formatter: (value: number) => `${formatNumber(value, 2)} ${view.a.currency}` }, splitLine: { lineStyle: { color: "rgba(148,163,184,.1)" } } },
        { type: "category", gridIndex: 1, data: parties.map(partyLabel), axisLabel: { color: "#e2e8f0", fontSize: 11, formatter: (value: string) => value.split(" · ")[0] }, axisTick: { show: false }, splitLine: { show: false } },
        { type: "value", gridIndex: 2, name: pathLabel, nameTextStyle: { color: "rgba(177,196,214,.58)", fontSize: 10 }, min: pathMode === "quantity" ? 0 : undefined, scale: pathMode === "cost", axisLabel: { color: "rgba(177,196,214,.72)", formatter: (value: number) => pathMode === "quantity" ? formatNumber(value, 0) : `${formatNumber(value, 2)} ${view.a.currency}` }, splitLine: { lineStyle: { color: "rgba(148,163,184,.1)" } } },
      ],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        confine: true,
        renderMode: "richText",
        backgroundColor: "#101c29",
        textStyle: { color: "#edf2f7" },
        formatter: (raw: unknown) => {
          const points = Array.isArray(raw) ? raw : [raw];
          const marker = points.find((point) => typeof (point as { data?: { decisionId?: unknown } }).data?.decisionId === "string");
          const detail = (marker ?? points.find((point) => Boolean((point as { data?: { detail?: string } }).data?.detail))) as { data?: { detail?: string } } | undefined;
          return detail?.data?.detail ?? "";
        },
      },
      // The shared frame owns the sole visible range control; this inside zoom feeds the shared store.
      dataZoom: zoom,
      series: [
        {
          id: "common-market-close", name: c.commonMarket, type: view.prices.length === 1 ? "scatter" : "line", showSymbol: view.prices.length <= 1, connectNulls: false,
          lineStyle: { color: "#a4b9c9", width: 1.7 }, itemStyle: { color: "#a4b9c9" },
          data: view.prices.map((point) => ({ value: [Date.parse(point.at), point.value], detail: `${c.commonMarket}\n${c.dailyLabel}: ${point.at.slice(0, 10)}\n${c.marketPriceUnit}: ${formatNumber(point.value, 2)} ${view.a.currency}` })), markArea: area, z: 2,
        },
        ...parties.map((party) => ({
          id: `execution-${party.id}`, name: `${partyLabel(party)} · ${c.executionMarkers}`, type: "scatter" as const, xAxisIndex: 1, yAxisIndex: 1, z: 5,
          data: party.side.decisions.map((decision, index) => ({
            decisionId: decision.id, symbolOffset: [0, executionLaneOffset(party.side.decisions, index)], value: [Date.parse(decision.at), partyLabel(party)], symbol: executionSymbols[decision.kind] ?? "circle", symbolSize: markerHighlight(party.id, decision.id) ? 19 : 12,
            itemStyle: { color: party.color, borderColor: "rgba(8,16,27,.9)", borderWidth: 1.5, shadowBlur: markerHighlight(party.id, decision.id) ? 14 : 0, shadowColor: party.color },
            detail: `${partyLabel(party)} · ${operationLabel(decision.kind)}\n${c.exactTime}: ${decision.at.replace("T", " ")}\n${c.executionQuantity}: ${formatNumber(decision.quantity, 0)}\n${c.positionQuantity}: ${formatNumber(decision.before, 0)} → ${formatNumber(decision.after, 0)}\n${t("Execution price")}: ${formatNumber(decision.price, 2)} ${party.currency}\n${c.averageCost}: ${decision.costBefore === null ? "—" : `${formatNumber(decision.costBefore, 2)} ${party.currency}`} → ${decision.costAfter === null ? "—" : `${formatNumber(decision.costAfter, 2)} ${party.currency}`}`,
          })), markArea: area,
        })),
        ...parties.map((party) => ({
          id: `path-${party.id}`, name: `${partyLabel(party)} · ${pathLabel}`, type: "line" as const, step: "end" as const, xAxisIndex: 2, yAxisIndex: 2, showSymbol: false, connectNulls: false, lineStyle: { color: party.color, width: 2 },
          data: party.side.shape.map((point) => ({ value: [Date.parse(point.at), pathMode === "quantity" ? point.quantity : point.cost], detail: `${partyLabel(party)}\n${c.exactTime}: ${point.at.replace("T", " ")}\n${c.positionQuantity}: ${formatNumber(point.quantity, 0)}\n${c.averageCost}: ${point.cost === null ? "—" : `${formatNumber(point.cost, 2)} ${party.currency}`}` })), markArea: area, z: 3,
        })),
      ],
    };
  }, [focusedDecisionId, formatNumber, locale, observationTimes, pathMode, selected, selectedDecisionId, t, view, c]);

  const handleClick = useCallback((event: ECElementEvent) => {
    if (!String(event.seriesId ?? "").startsWith("execution-")) return;
    const decisionId = (event.data as { decisionId?: unknown } | undefined)?.decisionId;
    if (typeof decisionId === "string") onSelectDecision?.(decisionId);
  }, [onSelectDecision]);

  if (!view.prices.length || view.status === "unavailable") return null;
  return <EChart option={option} label={`${c.pricePane}, ${c.operationPane}, ${pathMode === "quantity" ? c.quantityPath : c.averageCostPath}`} className="h-[590px] w-full" resetKey={view.id} timeNavigation={timeNavigation} observationTimes={observationTimes} onChartClick={handleClick} />;
}
