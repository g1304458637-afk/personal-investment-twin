import type { ECElementEvent, EChartsCoreOption } from "echarts/core";
import { useCallback, useMemo } from "react";

import { EChart } from "@/components/charts/EChart";
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
  onSelectDecision,
}: {
  entry: PositionEpisodeEntryView;
  selectedDecisionId: string | null;
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
    const dateFormatter = new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
    });
    const timeFormatter = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
    const decisions = entry.decisions.map((decision) => ({
      value: [decision.occurredAt, decision.executionPrice],
      decisionId: decision.decisionId,
      decisionLabel: decisionLabel(decision.decisionType),
      executionPrice: decision.executionPrice,
      executedQuantity: decision.executedQuantity,
      beforeQuantity: decision.stateBefore.quantity,
      afterQuantity: decision.stateAfter.quantity,
      occurredAt: decision.occurredAt,
      symbol: markerStyle[decision.decisionType].symbol,
      symbolSize: decision.decisionId === selectedDecisionId
        ? 19
        : decision.decisionType === "close_position" ? 15 : 14,
      itemStyle: {
        color: decision.decisionId === selectedDecisionId
          ? "#f4fbff"
          : markerStyle[decision.decisionType].color,
        borderColor: "rgba(7, 14, 24, .82)",
        borderWidth: 2,
        shadowBlur: decision.decisionId === selectedDecisionId ? 22 : 14,
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
    }));
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

    return {
      animationDuration: 420,
      animationEasing: "cubicOut",
      grid: { left: 58, right: entry.snapshot ? 116 : 30, top: 48, bottom: 48 },
      tooltip: {
        trigger: "item",
        borderWidth: 1,
        borderColor: "rgba(142, 220, 255, .2)",
        backgroundColor: "rgba(8, 16, 27, .94)",
        textStyle: { color: "#eaf3fb", fontSize: 12 },
        extraCssText: "border-radius:10px;box-shadow:0 18px 50px rgba(0,0,0,.35);",
        formatter: (params: unknown) => {
          const point = params as {
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
              ? `${escapeHtml(dateFormatter.format(new Date(value[0])))}<br/>${escapeHtml(t("Average cost"))}: ${escapeHtml(formatCurrency(Number(value[1])))}`
              : "";
          }
          const value = point.value;
          return value
            ? `${escapeHtml(dateFormatter.format(new Date(value[0])))}<br/>${escapeHtml(formatCurrency(Number(value[1])))}`
            : "";
        },
      },
      xAxis: {
        type: "time",
        boundaryGap: ["4%", "8%"],
        axisLine: { lineStyle: { color: "rgba(148, 177, 204, .18)" } },
        axisTick: { show: false },
        axisLabel: {
          color: "rgba(177, 196, 214, .72)",
          formatter: (value: number) => dateFormatter.format(new Date(value)),
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
      series: [
        {
          id: "market-price",
          name: t("Market price"),
          type: "line",
          data: entry.pricePoints.map((point) => [point.observedAt, point.price]),
          showSymbol: false,
          connectNulls: false,
          smooth: 0.22,
          lineStyle: { color: "rgba(142, 220, 255, .72)", width: 2 },
          areaStyle: { color: "rgba(91, 179, 221, .08)" },
          emphasis: { focus: "series" },
          z: 2,
        },
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
  }, [decisionLabel, entry, formatCurrency, formatNumber, locale, selectedDecisionId, t]);

  const handleClick = useCallback(
    (event: ECElementEvent) => {
      if (event.seriesId !== "decision-events") return;
      const data = event.data as { decisionId?: unknown } | undefined;
      if (typeof data?.decisionId === "string") onSelectDecision(data.decisionId);
    },
    [onSelectDecision],
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-5 rounded-full bg-[#8edcff]" aria-hidden="true" />
          {t("Market price")}
        </span>
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
        label={t("Market price and actual position decision timeline for {symbol}", {
          symbol: entry.episode.instrumentId,
        })}
        className="h-[360px] w-full"
        onChartClick={handleClick}
      />
    </div>
  );
}
