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
  calendarDayTime,
} from "@/components/charts/dailyTimeAxis";
import type {
  PositionDecisionType,
  PositionEpisodeEntryView,
} from "@/data/positionEpisode";
import { useLocale } from "@/locales/LocaleProvider";

const markerStyle: Record<
  PositionDecisionType,
  { color: string; symbol: "circle" | "diamond" | "triangle" | "rect" }
> = {
  open_position: { color: "#8edcff", symbol: "circle" },
  add_position: { color: "#bca9ff", symbol: "diamond" },
  reduce_position: { color: "#f0ca83", symbol: "triangle" },
  close_position: { color: "#efa5a5", symbol: "rect" },
};

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        character
      ] ?? character,
  );
}

export function PositionEpisodeTimeline({
  entry,
  selectedDecisionId,
  emphasizedDecisionIds,
  highlightStart,
  highlightEnd,
  chartGroup,
  onSelectDecision,
}: {
  entry: PositionEpisodeEntryView;
  selectedDecisionId: string | null;
  emphasizedDecisionIds?: string[];
  highlightStart?: string | null;
  highlightEnd?: string | null;
  chartGroup?: string;
  onSelectDecision: (decisionId: string) => void;
}) {
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  const decisionLabel = useCallback(
    (type: PositionDecisionType) => {
      const labels: Record<PositionDecisionType, string> = {
        open_position: t("Open position"),
        add_position: t("Add position"),
        reduce_position: t("Reduce position"),
        close_position: t("Close position / final sale"),
      };
      return labels[type];
    },
    [t],
  );

  const option = useMemo<EChartsCoreOption>(() => {
    const timeFormatter = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
    const emphasized = new Set(emphasizedDecisionIds ?? []);
    const decisions = entry.decisions.map((decision) => {
      const active = decision.decisionId === selectedDecisionId || emphasized.has(decision.decisionId);
      return {
        value: [decision.occurredAt, decision.executionPrice],
        decisionId: decision.decisionId,
        decisionLabel: decisionLabel(decision.decisionType),
        executionPrice: decision.executionPrice,
        executedQuantity: decision.executedQuantity,
        beforeQuantity: decision.stateBefore.quantity,
        afterQuantity: decision.stateAfter.quantity,
        occurredAt: decision.occurredAt,
        symbol: markerStyle[decision.decisionType].symbol,
        symbolSize: active ? 19 : decision.decisionType === "close_position" ? 15 : 14,
        itemStyle: {
          color: active ? "#f4fbff" : markerStyle[decision.decisionType].color,
          borderColor: "rgba(7, 14, 24, .82)",
          borderWidth: 2,
          shadowBlur: active ? 22 : 14,
          shadowColor: `${markerStyle[decision.decisionType].color}55`,
        },
        label: {
          show: true,
          position: "top",
          distance: 8,
          color: "rgba(235, 243, 252, .88)",
          fontSize: 11,
          formatter: decisionLabel(decision.decisionType),
        },
      };
    });
    const averageCost = entry.decisions.map((decision) => ({
      value: [decision.occurredAt, decision.outcome.after.averageCost],
      decisionId: decision.decisionId,
    }));
    const current = entry.snapshot?.positionState;
    const valuation =
      current?.valuationAt && current.valuationPrice !== null
        ? [
            {
              value: [current.valuationAt, current.valuationPrice],
              valuationAt: current.valuationAt,
              valuationPrice: current.valuationPrice,
              symbol: "emptyCircle",
              symbolSize: 18,
              itemStyle: {
                color: "rgba(142, 220, 255, .08)",
                borderColor: "#8edcff",
                borderWidth: 3,
                shadowBlur: 18,
                shadowColor: "rgba(142, 220, 255, .35)",
              },
              label: {
                show: true,
                position: "right",
                distance: 9,
                color: "rgba(142, 220, 255, .95)",
                fontSize: 11,
                formatter: t("Latest valid valuation"),
              },
            },
          ]
        : [];
    const holdingEnd = entry.episode.closedAt ?? current?.valuationAt ?? entry.episode.openedAt;
    const markArea = {
      silent: true,
      data: [
        [
          {
            xAxis: entry.episode.openedAt,
            itemStyle: { color: "rgba(142, 220, 255, 0.016)" },
            label: {
              show: true,
              formatter: t("Holding period"),
              color: "rgba(177, 196, 214, .42)",
              fontSize: 9,
              position: "insideTopLeft",
            },
          },
          { xAxis: holdingEnd },
        ],
        ...(highlightStart && highlightEnd
          ? [[
              {
                xAxis: highlightStart,
                itemStyle: { color: "rgba(188, 169, 255, 0.11)" },
              },
              { xAxis: highlightEnd },
            ]]
          : []),
      ],
    };
    const observationTimes = uniqueDailyObservationTimes(entry.pricePoints.map((point) => point.observedAt));
    const minValueSpan = minDailyZoomSpanMs(observationTimes);
    const executionDays = new Set(
      entry.decisions.map((decision) => calendarDayTime(Date.parse(decision.occurredAt))),
    );
    const bySegment = (segment: "pre_entry" | "episode" | "post_exit") =>
      entry.pricePoints
        .filter((point) => point.segment === segment)
        .map((point) => [point.observedAt, point.price] as [string, number]);

    return {
      animationDuration: 420,
      animationEasing: "cubicOut",
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: { left: 58, right: entry.snapshot ? 116 : 30, top: 48, bottom: 58 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        borderWidth: 1,
        borderColor: "rgba(142, 220, 255, .2)",
        backgroundColor: "rgba(8, 16, 27, .94)",
        textStyle: { color: "#eaf3fb", fontSize: 12 },
        extraCssText: "border-radius:10px;box-shadow:0 18px 50px rgba(0,0,0,.35);",
        formatter: (params: unknown) => {
          const source = Array.isArray(params)
            ? (params.find((item) => (item as { seriesId?: string }).seriesId === "decision-events") ?? params[0])
            : params;
          const point = source as {
            seriesId?: string;
            data?: Record<string, unknown>;
            value?: [string, number | null];
          };
          const data = point.data ?? {};
          if (point.seriesId === "decision-events") {
            return [
              `<strong>${escapeHtml(String(data.decisionLabel ?? ""))}</strong>`,
              escapeHtml(timeFormatter.format(new Date(String(data.occurredAt)))),
              `${escapeHtml(t("Execution price"))}: ${escapeHtml(formatCurrency(Number(data.executionPrice)))}`,
              `${escapeHtml(t("Execution quantity"))}: ${escapeHtml(formatNumber(Number(data.executedQuantity), 0))}`,
              `${escapeHtml(t("Position quantity"))}: ${escapeHtml(formatNumber(Number(data.beforeQuantity), 0))} → ${escapeHtml(formatNumber(Number(data.afterQuantity), 0))}`,
            ].join("<br/>");
          }
          if (point.seriesId === "current-valuation") {
            return [
              `<strong>${escapeHtml(t("Latest valid valuation"))}</strong>`,
              escapeHtml(timeFormatter.format(new Date(String(data.valuationAt)))),
              `${escapeHtml(t("Valuation price"))}: ${escapeHtml(formatCurrency(Number(data.valuationPrice)))}`,
              escapeHtml(t("This mark is not an exit or sale.")),
            ].join("<br/>");
          }
          if (point.seriesId === "average-cost") {
            const value = point.value;
            return value && value[1] !== null
              ? `${escapeHtml(formatDailyAxisTick(Date.parse(value[0]), locale))}<br/>${escapeHtml(t("Average cost"))}: ${escapeHtml(formatCurrency(Number(value[1])))}`
              : "";
          }
          const value = point.value;
          if (!value) return "";
          const stamp = Date.parse(value[0]);
          const day = calendarDayTime(stamp);
          const sameDayExecution = executionDays.has(day);
          const prior = [...entry.decisions]
            .reverse()
            .find((decision) => calendarDayTime(Date.parse(decision.occurredAt)) < day);
          const lines = [
            escapeHtml(formatDailyAxisTick(stamp, locale)),
            `${escapeHtml(t("Market price"))}: ${escapeHtml(formatCurrency(Number(value[1])))}`,
          ];
          if (sameDayExecution) {
            lines.push(escapeHtml(t("A recorded execution falls on this calendar date; quantity at close is not assigned.")));
          } else if (prior) {
            if (prior.outcome.after.averageCost !== null) {
              lines.push(`${escapeHtml(t("Average cost"))}: ${escapeHtml(formatCurrency(prior.outcome.after.averageCost))}`);
            }
            lines.push(`${escapeHtml(t("Position quantity"))}: ${escapeHtml(formatNumber(prior.outcome.after.quantity, 0))}`);
          }
          return lines.join("<br/>");
        },
      },
      xAxis: {
        type: "time",
        minInterval: MS_PER_DAY,
        ...dailyTimeDomain([
          ...entry.pricePoints.map((point) => point.observedAt),
          ...entry.decisions.map((decision) => decision.occurredAt),
        ]),
        boundaryGap: ["4%", "8%"],
        axisLine: { lineStyle: { color: "rgba(148, 177, 204, .18)" } },
        axisTick: { show: false },
        axisLabel: {
          color: "rgba(177, 196, 214, .72)",
          hideOverlap: true,
          formatter: (value: number) => formatDailyAxisTick(value, locale),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          color: "rgba(177, 196, 214, .72)",
          formatter: (value: number) => formatCurrency(value),
        },
        splitLine: { lineStyle: { color: "rgba(148, 177, 204, .09)" } },
      },
      dataZoom: dailyDataZoom(8, minValueSpan),
      series: [
        ...(bySegment("pre_entry").length
          ? [{
              id: "pre-entry-price",
              name: t("Pre-entry market path"),
              type: "line" as const,
              data: bySegment("pre_entry"),
              showSymbol: false,
              connectNulls: false,
              smooth: false,
              lineStyle: { color: "rgba(142, 220, 255, .42)", width: 1.6 },
              z: 1,
            }]
          : []),
        {
          id: "market-price",
          name: t("Market price"),
          type: "line",
          data: bySegment("episode"),
          showSymbol: false,
          connectNulls: false,
          smooth: false,
          lineStyle: { color: "rgba(142, 220, 255, .92)", width: 2.4 },
          markArea,
          emphasis: { focus: "series" },
          z: 2,
        },
        ...(bySegment("post_exit").length
          ? [{
              id: "post-exit-price",
              name: t("Post-exit market path"),
              type: "line" as const,
              data: bySegment("post_exit"),
              showSymbol: false,
              connectNulls: false,
              smooth: false,
              lineStyle: { color: "rgba(240, 202, 131, .55)", width: 1.5, type: "dotted" as const },
              z: 1,
            }]
          : []),
        {
          id: "average-cost",
          name: t("Average cost"),
          type: "line",
          data: averageCost,
          step: "end",
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "rgba(188, 169, 255, .78)", width: 1.6, type: "dashed" },
          z: 3,
        },
        {
          id: "decision-events",
          name: t("Actual executions"),
          type: "scatter",
          data: decisions,
          z: 5,
        },
        {
          id: "current-valuation",
          name: t("Latest valid valuation"),
          type: "scatter",
          data: valuation,
          silent: true,
          z: 6,
        },
      ],
    };
  }, [
    decisionLabel,
    emphasizedDecisionIds,
    entry,
    formatCurrency,
    formatNumber,
    highlightEnd,
    highlightStart,
    locale,
    selectedDecisionId,
    t,
  ]);

  const handleClick = useCallback(
    (event: ECElementEvent) => {
      if (event.seriesId !== "decision-events") return;
      const data = event.data as { decisionId?: unknown } | undefined;
      if (typeof data?.decisionId === "string") onSelectDecision(data.decisionId);
    },
    [onSelectDecision],
  );

  const hasPreEntryPath = entry.pricePoints.some((point) => point.segment === "pre_entry");
  const hasPostExitPath = entry.pricePoints.some((point) => point.segment === "post_exit");

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        {hasPreEntryPath ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-5 rounded-full bg-[#8edcff]/40" aria-hidden="true" />
            {t("Pre-entry market path")}
          </span>
        ) : null}
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-5 rounded-full bg-[#8edcff]" aria-hidden="true" />
          {t("Market price")}
        </span>
        {hasPostExitPath ? (
          <span className="inline-flex items-center gap-2">
            <span className="w-5 border-t border-dotted border-[#f0ca83]" aria-hidden="true" />
            {t("Post-exit market path")}
          </span>
        ) : null}
        <span className="inline-flex items-center gap-2">
          <span className="size-2.5 rounded-full bg-[#bca9ff]" aria-hidden="true" />
          {t("Actual execution")}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="w-5 border-t border-dashed border-[#bca9ff]" aria-hidden="true" />
          {t("Average cost")}
        </span>
        {entry.snapshot ? (
          <span className="inline-flex items-center gap-2 text-accent">
            <span className="size-3 rounded-full border-2 border-accent bg-transparent" aria-hidden="true" />
            {t("Latest valid valuation · not an exit")}
          </span>
        ) : null}
      </div>
      <EChart
        option={option}
        group={chartGroup}
        resetKey={entry.episode.episodeId}
        observationTimes={uniqueDailyObservationTimes(entry.pricePoints.map((point) => point.observedAt))}
        label={t("Market price and actual position decision timeline for {symbol}", {
          symbol: entry.episode.instrumentId,
        })}
        className="h-[360px] w-full"
        onChartClick={handleClick}
      />
    </div>
  );
}
