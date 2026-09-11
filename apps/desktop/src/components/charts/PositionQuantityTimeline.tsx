import type { ECElementEvent, EChartsCoreOption } from "echarts/core";
import { useCallback, useMemo } from "react";

import { EChart } from "@/components/charts/EChart";
import {
  dailyDataZoom,
  dailyTimeDomain,
  formatDailyAxisTick,
  minDailyZoomSpanMs,
  uniqueDailyObservationTimes,
  MS_PER_DAY,
} from "@/components/charts/dailyTimeAxis";
import {
  dailyPathLineWidth,
  createAdaptiveDailyAxisFormatter,
} from "@/components/charts/dailyTimeNavigation";
import type { DailyTimeNavigationStore } from "@/components/charts/useDailyTimeNavigation";
import type { PositionEpisodeEntryView } from "@/data/positionEpisode";
import { useLocale } from "@/locales/LocaleProvider";

export function PositionQuantityTimeline({
  entry,
  selectedDecisionId,
  emphasizedDecisionIds,
  highlightStart,
  highlightEnd,
  chartGroup,
  timeNavigation,
  onSelectDecision,
  showNavigator = true,
  className = "h-[190px] w-full",
}: {
  entry: PositionEpisodeEntryView;
  className?: string;
  selectedDecisionId: string | null;
  emphasizedDecisionIds?: string[];
  highlightStart?: string | null;
  highlightEnd?: string | null;
  chartGroup?: string;
  timeNavigation?: DailyTimeNavigationStore;
  onSelectDecision: (decisionId: string) => void;
  /** The enclosing workspace owns the sole range control when false. */
  showNavigator?: boolean;
}) {
  const { locale, t, formatNumber } = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const quantityPoints = entry.pathAnalysis.positionPath.points.map((point) => [point.asOf, point.quantity]);
    const emphasized = new Set(emphasizedDecisionIds ?? []);
    const events = entry.decisions.map((decision) => {
      const active = decision.decisionId === selectedDecisionId || emphasized.has(decision.decisionId);
      return {
        value: [decision.occurredAt, decision.outcome.after.quantity],
        decisionId: decision.decisionId,
        quantity: decision.outcome.after.quantity,
        symbolSize: active ? 14 : 9,
        itemStyle: {
          color: active ? "#e9f7ff" : "#8edcff",
          borderColor: "rgba(8, 16, 27, .9)",
          borderWidth: 2,
          shadowBlur: active ? 16 : 6,
          shadowColor: "rgba(142, 220, 255, .42)",
        },
      };
    });
    const observationTimes = uniqueDailyObservationTimes(entry.pricePoints.map((point) => point.observedAt));
    const minValueSpan = minDailyZoomSpanMs(observationTimes);
    const quantityLineWidth = dailyPathLineWidth(observationTimes.length, "primary");
    const holdingEnd = entry.episode.closedAt ?? entry.snapshot?.positionState.valuationAt ?? entry.episode.openedAt;
    return {
      animationDuration: 360,
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      // Keep the plot rails identical to the price pane: day-to-pixel mapping matches.
      grid: { left: 64, right: 116, top: 16, bottom: showNavigator ? 46 : 30 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        borderWidth: 1,
        borderColor: "rgba(142, 220, 255, .2)",
        backgroundColor: "rgba(8, 16, 27, .94)",
        textStyle: { color: "#eaf3fb", fontSize: 12 },
        formatter: (params: unknown) => {
          const source = Array.isArray(params) ? params[0] : params;
          const point = source as { value?: [string, number] };
          return point.value
            ? `${formatDailyAxisTick(Date.parse(point.value[0]), locale)}<br/>${t("Position quantity")}: ${formatNumber(point.value[1], 0)}`
            : "";
        },
      },
      xAxis: {
        type: "time",
        minInterval: MS_PER_DAY,
        ...dailyTimeDomain([
          ...entry.pricePoints.map((point) => point.observedAt),
          ...entry.decisions.map((decision) => decision.occurredAt),
          ...entry.pathAnalysis.positionPath.points.map((point) => point.asOf),
        ]),
        boundaryGap: ["4%", "8%"],
        axisLine: { lineStyle: { color: "rgba(148, 177, 204, .18)" } },
        axisTick: { show: false },
        axisLabel: {
          color: "rgba(177, 196, 214, .72)",
          hideOverlap: true,
          formatter: createAdaptiveDailyAxisFormatter(locale, () => timeNavigation?.getDomain()),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: { color: "rgba(177, 196, 214, .72)", formatter: (value: number) => formatNumber(value, 0) },
        splitLine: { lineStyle: { color: "rgba(148, 177, 204, .09)" } },
      },
      // Retain inside zoom for the shared store, but remove the duplicate slider.
      dataZoom: showNavigator
        ? dailyDataZoom(6, minValueSpan)
        : dailyDataZoom(6, minValueSpan).filter((control) => control.type !== "slider"),
      series: [
        {
          id: "position-quantity",
          type: "line",
          data: quantityPoints,
          step: "end",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "rgba(142, 220, 255, .9)", width: quantityLineWidth },
          markArea: {
            silent: true,
            data: [
              [
                { xAxis: entry.episode.openedAt, itemStyle: { color: "rgba(142, 220, 255, 0.014)" } },
                { xAxis: holdingEnd },
              ],
              ...(highlightStart && highlightEnd
                ? [[{ xAxis: highlightStart, itemStyle: { color: "rgba(188, 169, 255, 0.11)" } }, { xAxis: highlightEnd }]]
                : []),
            ],
          },
          z: 2,
        },
        { id: "quantity-events", type: "scatter", data: events, z: 4 },
      ],
    };
  }, [emphasizedDecisionIds, entry, formatNumber, highlightEnd, highlightStart, locale, selectedDecisionId, showNavigator, t, timeNavigation]);

  const onClick = useCallback((event: ECElementEvent) => {
    if (event.seriesId !== "quantity-events") return;
    const decisionId = (event.data as { decisionId?: unknown } | undefined)?.decisionId;
    if (typeof decisionId === "string") onSelectDecision(decisionId);
  }, [onSelectDecision]);

  return (
    <EChart
      option={option}
      group={chartGroup}
      resetKey={entry.episode.episodeId}
      timeNavigation={timeNavigation}
      observationTimes={uniqueDailyObservationTimes(entry.pricePoints.map((point) => point.observedAt))}
      label={t("Position quantity evolution for {symbol}", { symbol: entry.episode.instrumentId })}
      className={className}
      onChartClick={onClick}
    />
  );
}
