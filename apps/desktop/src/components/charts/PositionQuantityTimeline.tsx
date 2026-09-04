import type { ECElementEvent, EChartsCoreOption } from "echarts/core";
import { useCallback, useMemo } from "react";

import { EChart } from "@/components/charts/EChart";
import type { PositionEpisodeEntryView } from "@/data/positionEpisode";
import { useLocale } from "@/locales/LocaleProvider";

export function PositionQuantityTimeline({
  entry,
  selectedDecisionId,
  onSelectDecision,
}: {
  entry: PositionEpisodeEntryView;
  selectedDecisionId: string | null;
  onSelectDecision: (decisionId: string) => void;
}) {
  const { locale, t, formatNumber } = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const date = new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" });
    const first = entry.decisions[0];
    const quantityPoints = first
      ? [
          [first.occurredAt, first.outcome.before.quantity],
          ...entry.decisions.map((decision) => [decision.occurredAt, decision.outcome.after.quantity]),
        ]
      : [];
    const events = entry.decisions.map((decision) => ({
      value: [decision.occurredAt, decision.outcome.after.quantity],
      decisionId: decision.decisionId,
      quantity: decision.outcome.after.quantity,
      symbolSize: decision.decisionId === selectedDecisionId ? 14 : 9,
      itemStyle: {
        color: decision.decisionId === selectedDecisionId ? "#e9f7ff" : "#8edcff",
        borderColor: "rgba(8, 16, 27, .9)",
        borderWidth: 2,
        shadowBlur: decision.decisionId === selectedDecisionId ? 16 : 6,
        shadowColor: "rgba(142, 220, 255, .42)",
      },
    }));
    return {
      animationDuration: 360,
      grid: { left: 54, right: 24, top: 16, bottom: 38 },
      tooltip: {
        trigger: "item",
        borderWidth: 1,
        borderColor: "rgba(142, 220, 255, .2)",
        backgroundColor: "rgba(8, 16, 27, .94)",
        textStyle: { color: "#eaf3fb", fontSize: 12 },
        formatter: (params: unknown) => {
          const point = params as { value?: [string, number] };
          return point.value
            ? `${date.format(new Date(point.value[0]))}<br/>${t("Position quantity")}: ${formatNumber(point.value[1], 0)}`
            : "";
        },
      },
      xAxis: {
        type: "time",
        boundaryGap: ["4%", "6%"],
        axisLine: { lineStyle: { color: "rgba(148, 177, 204, .18)" } },
        axisTick: { show: false },
        axisLabel: { color: "rgba(177, 196, 214, .72)", formatter: (value: number) => date.format(new Date(value)) },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: { color: "rgba(177, 196, 214, .72)", formatter: (value: number) => formatNumber(value, 0) },
        splitLine: { lineStyle: { color: "rgba(148, 177, 204, .09)" } },
      },
      series: [
        {
          id: "position-quantity",
          type: "line",
          data: quantityPoints,
          step: "end",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "rgba(142, 220, 255, .78)", width: 2 },
          areaStyle: { color: "rgba(91, 179, 221, .08)" },
          z: 2,
        },
        { id: "quantity-events", type: "scatter", data: events, z: 4 },
      ],
    };
  }, [entry, formatNumber, locale, selectedDecisionId, t]);

  const onClick = useCallback((event: ECElementEvent) => {
    if (event.seriesId !== "quantity-events") return;
    const decisionId = (event.data as { decisionId?: unknown } | undefined)?.decisionId;
    if (typeof decisionId === "string") onSelectDecision(decisionId);
  }, [onSelectDecision]);

  return (
    <EChart
      option={option}
      label={t("Position quantity evolution for {symbol}", { symbol: entry.episode.instrumentId })}
      className="h-[190px] w-full"
      onChartClick={onClick}
    />
  );
}
