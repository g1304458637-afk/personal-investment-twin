import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { StateNotice } from "@/components/common/StateNotice";
import { useTheme } from "@/components/layout/ThemeProvider";
import {
  historyDisplayMode,
  validHistoryPoints,
  type BehaviorHistorySeries,
} from "@/data/behaviorHistory";
import { useLocale } from "@/locales/LocaleProvider";

import { EChart } from "./EChart";

export function HistoricalMetricChart({
  series,
  label,
  singleValueLabel,
  percent = false,
}: {
  series: BehaviorHistorySeries;
  label: string;
  singleValueLabel: string;
  percent?: boolean;
}) {
  const { theme } = useTheme();
  const { locale, t } = useLocale();
  const dark = theme === "dark";
  const mode = historyDisplayMode(series);
  const valid = validHistoryPoints(series);
  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }),
    [locale],
  );

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 520,
      animationEasing: "cubicOut",
      grid: { left: 8, right: 12, top: 10, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: unknown) => {
          if (typeof value !== "number") return "—";
          return percent ? `${(value * 100).toFixed(4)}%` : value.toFixed(6);
        },
        backgroundColor: dark ? "rgba(13, 18, 28, .96)" : "rgba(252, 253, 254, .97)",
        borderColor: dark ? "rgba(255,255,255,.12)" : "rgba(32,50,63,.14)",
        textStyle: { color: dark ? "#eef5f6" : "#17212a", fontSize: 12 },
        axisPointer: { lineStyle: { color: "rgba(143,221,228,.25)" } },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.points.map((point) =>
          dateFormatter.format(new Date(point.date)),
        ),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: dark ? "rgba(255,255,255,.08)" : "rgba(20,35,47,.10)" } },
        axisLabel: { color: dark ? "#717c8d" : "#74808c", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 3,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: dark ? "#717c8d" : "#74808c",
          fontSize: 10,
          formatter: percent ? (value: number) => `${(value * 100).toFixed(1)}%` : undefined,
        },
        splitLine: { lineStyle: { color: dark ? "rgba(255,255,255,.05)" : "rgba(20,35,47,.06)" } },
      },
      series: [
        {
          name: label,
          type: "line",
          data: series.points.map((point) => point.value),
          connectNulls: false,
          showSymbol: true,
          symbolSize: 5,
          smooth: 0.24,
          lineStyle: { width: 2, color: "#8fdde4" },
          itemStyle: { color: "#baf5f7", borderColor: dark ? "#172531" : "#ffffff", borderWidth: 2 },
          areaStyle: { color: "rgba(112, 211, 221, .065)" },
        },
      ],
    }),
    [dark, dateFormatter, label, percent, series.points],
  );

  if (mode === "insufficient") {
    return (
      <StateNotice
        state="insufficient"
        title={t("Evidence insufficient")}
        detail={t("No valid historical snapshots are available; missing values remain gaps.")}
      />
    );
  }
  if (mode === "single") {
    return (
      <StateNotice
        state="insufficient"
        title={singleValueLabel}
        detail={t("Historical snapshots are insufficient to form a trend.")}
      />
    );
  }

  return (
    <EChart
      option={option}
      label={t("{metric} historical evidence on real dates: {values}", {
        metric: label,
        values: valid.map((point) => `${point.date}: ${point.value}`).join(", "),
      })}
      className="h-[210px] w-full"
    />
  );
}
