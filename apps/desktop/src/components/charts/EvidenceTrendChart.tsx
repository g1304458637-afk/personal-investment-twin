import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";

import { useTheme } from "@/components/layout/ThemeProvider";
import type { EvidenceMetric } from "@/demo/types";
import { useLocale } from "@/locales/LocaleProvider";

import { EChart } from "./EChart";

export function EvidenceTrendChart({ metric }: { metric: EvidenceMetric }) {
  const { theme } = useTheme();
  const { t } = useLocale();
  const dark = theme === "dark";

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animationDuration: 520,
      animationEasing: "cubicOut",
      grid: { left: 8, right: 12, top: 10, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: dark ? "rgba(13, 18, 28, .96)" : "rgba(252, 253, 254, .97)",
        borderColor: dark ? "rgba(255,255,255,.12)" : "rgba(32,50,63,.14)",
        textStyle: { color: dark ? "#eef5f6" : "#17212a", fontSize: 12 },
        axisPointer: { lineStyle: { color: "rgba(143,221,228,.25)" } },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: metric.trend.map((_, index) => `O${index + 1}`),
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
        axisLabel: { color: dark ? "#717c8d" : "#74808c", fontSize: 10 },
        splitLine: { lineStyle: { color: dark ? "rgba(255,255,255,.05)" : "rgba(20,35,47,.06)" } },
      },
      series: [
        {
          name: t(metric.label),
          type: "line",
          data: metric.trend,
          showSymbol: true,
          symbolSize: 5,
          smooth: 0.24,
          lineStyle: { width: 2, color: "#8fdde4" },
          itemStyle: { color: "#baf5f7", borderColor: dark ? "#172531" : "#ffffff", borderWidth: 2 },
          areaStyle: { color: "rgba(112, 211, 221, .065)" },
        },
      ],
    }),
    [dark, metric, t],
  );

  return <EChart option={option} label={t("{metric} deterministic demo observations: {values}", { metric: t(metric.label), values: metric.trend.join(", ") })} className="h-[210px] w-full" />;
}
