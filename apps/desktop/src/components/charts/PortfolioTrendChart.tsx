import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { useTheme } from "@/components/layout/ThemeProvider";
import { portfolioHistory } from "@/demo/fixture";
import { useLocale } from "@/locales/LocaleProvider";

import { EChart } from "./EChart";

export function PortfolioTrendChart() {
  const { theme } = useTheme();
  const { t, formatCurrency } = useLocale();
  const dark = theme === "dark";

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 620,
      animationEasing: "cubicOut",
      grid: { left: 8, right: 18, top: 42, bottom: 28, containLabel: true },
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
        type: "category",
        boundaryGap: false,
        data: portfolioHistory.map((point) => point.date.slice(5)),
        axisLine: { lineStyle: { color: dark ? "rgba(255,255,255,.09)" : "rgba(20,35,47,.12)" } },
        axisTick: { show: false },
        axisLabel: { color: dark ? "#778294" : "#74808c", fontSize: 11, margin: 12 },
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
      series: [
        {
          name: t("Demo portfolio"),
          type: "line",
          data: portfolioHistory.map((point) => point.value),
          showSymbol: false,
          smooth: 0.28,
          lineStyle: { width: 2.5, color: "#8fdde4", shadowColor: "rgba(92,203,217,.25)", shadowBlur: 9 },
          itemStyle: { color: "#b9f5f7" },
          areaStyle: { color: "rgba(107, 210, 221, .08)" },
          emphasis: { focus: "series" },
        },
        {
          name: t("Reference baseline"),
          type: "line",
          data: portfolioHistory.map((point) => point.reference),
          showSymbol: false,
          smooth: 0.22,
          lineStyle: { width: 1.4, color: dark ? "#727b9f" : "#727b9f", type: "dashed" },
          itemStyle: { color: "#8f97ba" },
          emphasis: { focus: "series" },
        },
      ],
    }),
    [dark, formatCurrency, t],
  );

  return (
    <div className="relative">
      <div className="absolute right-2 top-1 z-[1] flex items-center gap-4 text-[11px] text-muted" aria-label={t("Chart legend")}>
        <span className="flex items-center gap-1.5"><i className="block w-4 border-t-2 border-accent" />{t("Demo portfolio")}</span>
        <span className="flex items-center gap-1.5"><i className="block w-4 border-t border-dashed border-[#727b9f]" />{t("Reference baseline")}</span>
      </div>
      <EChart
        option={option}
        label={t("Demo portfolio value trend with reference baseline")}
        className="h-[265px] w-full"
      />
    </div>
  );
}
