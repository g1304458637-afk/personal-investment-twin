import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { useTheme } from "@/components/layout/ThemeProvider";
import { portfolioHistory } from "@/demo/fixture";
import { useLocale } from "@/locales/LocaleProvider";

import { EChart } from "./EChart";
import {
  dailyTimeCoordinate,
  minDailyZoomSpanMs,
  uniqueDailyObservationTimes,
  MS_PER_DAY,
} from "./dailyTimeAxis";
import { createAdaptiveDailyAxisFormatter } from "./dailyTimeNavigation";
import { TimeSeriesFrame } from "./TimeSeriesFrame";
import { frameDailyTimeDomain, frameDataZoom } from "./timeSeriesFrameOptions";
import { useDailyTimeNavigation } from "./useDailyTimeNavigation";

export function PortfolioTrendChart() {
  const { theme } = useTheme();
  const { t, formatCurrency, locale } = useLocale();
  const dark = theme === "dark";
  const observationTimes = useMemo(
    () => uniqueDailyObservationTimes(portfolioHistory.map((point) => point.date)),
    [],
  );
  const timeNavigation = useDailyTimeNavigation("legacy-overview-portfolio", observationTimes);

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 620,
      animationEasing: "cubicOut",
      grid: { left: 8, right: 18, top: 42, bottom: 38, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: dark ? "rgba(13, 18, 28, .96)" : "rgba(252, 253, 254, .97)",
        borderColor: dark ? "rgba(255,255,255,.12)" : "rgba(32,50,63,.14)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: dark ? "#eef5f6" : "#17212a", fontSize: 12 },
        valueFormatter: (value: unknown) =>
          typeof value === "number" ? formatCurrency(value) : String(value),
        axisPointer: { lineStyle: { color: "rgba(143,221,228,.28)", width: 1 } },
      },
      xAxis: {
        type: "time",
        minInterval: MS_PER_DAY,
        ...frameDailyTimeDomain(observationTimes),
        boundaryGap: false,
        axisLine: { lineStyle: { color: dark ? "rgba(255,255,255,.09)" : "rgba(20,35,47,.12)" } },
        axisTick: { show: false },
        axisLabel: {
          color: dark ? "#778294" : "#74808c",
          fontSize: 11,
          margin: 12,
          hideOverlap: true,
          formatter: createAdaptiveDailyAxisFormatter(locale, () => timeNavigation.getDomain()),
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: dark ? "#778294" : "#74808c",
          fontSize: 11,
          formatter: (value: number) => `¥${Math.round(value / 1000)}k`,
        },
        splitLine: {
          lineStyle: { color: dark ? "rgba(255,255,255,.055)" : "rgba(20,35,47,.07)" },
        },
      },
      dataZoom: frameDataZoom(minDailyZoomSpanMs(observationTimes)),
      series: [
        {
          name: t("Demo portfolio"),
          type: "line",
          data: portfolioHistory.map((point) => [dailyTimeCoordinate(point.date), point.value] as [number, number]),
          showSymbol: false,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 2.5, color: "#8fdde4", shadowColor: "rgba(92,203,217,.25)", shadowBlur: 9 },
          itemStyle: { color: "#b9f5f7" },
          areaStyle: { color: "rgba(107, 210, 221, .08)" },
          emphasis: { focus: "series" },
        },
        {
          name: t("Reference baseline"),
          type: "line",
          data: portfolioHistory.map((point) => [dailyTimeCoordinate(point.date), point.reference] as [number, number]),
          showSymbol: false,
          connectNulls: false,
          smooth: false,
          lineStyle: { width: 1.4, color: dark ? "#727b9f" : "#727b9f", type: "dashed" },
          itemStyle: { color: "#8f97ba" },
          emphasis: { focus: "series" },
        },
      ],
    }),
    [dark, formatCurrency, locale, observationTimes, t, timeNavigation],
  );

  return (
    <TimeSeriesFrame
      title={t("Daily portfolio value")}
      navigation={timeNavigation}
      className="time-series-frame--single"
      toolbar={<div className="flex items-center gap-4 text-[11px] text-muted" aria-label={t("Chart legend")}>
        <span className="flex items-center gap-1.5"><i className="block w-4 border-t-2 border-accent" />{t("Demo portfolio")}</span>
        <span className="flex items-center gap-1.5"><i className="block w-4 border-t border-dashed border-[#727b9f]" />{t("Reference baseline")}</span>
      </div>}
    >
      <EChart
        option={option}
        timeNavigation={timeNavigation}
        observationTimes={observationTimes}
        label={t("Demo portfolio value trend with reference baseline")}
        className="h-[265px] w-full"
      />
    </TimeSeriesFrame>
  );
}
