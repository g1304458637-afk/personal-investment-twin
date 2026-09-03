import type { EChartsCoreOption } from "echarts/core";
import { useMemo } from "react";

import { useTheme } from "@/components/layout/ThemeProvider";
import type { PeerMetric } from "@/demo/types";
import { useLocale } from "@/locales/LocaleProvider";

import { EChart } from "./EChart";
import { getPeerRangeDomain } from "./PeerRangeChartDomain";

export function PeerRangeChart({ metric }: { metric: PeerMetric }) {
  const { theme } = useTheme();
  const { formatNumber, t } = useLocale();
  const dark = theme === "dark";

  const formatValue = (value: number) => {
    const formatted = formatNumber(value, Number.isInteger(value) ? 0 : 2);
    return metric.unit === "×" ? `${formatted}×` : formatted;
  };

  const option = useMemo<EChartsCoreOption>(() => {
    const domain = getPeerRangeDomain(metric);
    const benchmarkColor = dark ? "rgba(164, 177, 193, .66)" : "rgba(75, 91, 105, .62)";
    const rangeColor = dark ? "rgba(115, 205, 217, .28)" : "rgba(48, 139, 151, .24)";
    const tooltipBackground = dark ? "rgba(13, 18, 28, .97)" : "rgba(252, 253, 254, .98)";
    const tooltipBorder = dark ? "rgba(255,255,255,.13)" : "rgba(32,50,63,.15)";
    const tooltipText = dark ? "#eef5f6" : "#17212a";
    const labelColor = dark ? "#8d98a8" : "#667480";
    const quartiles = [
      { label: "P25", value: metric.p25 },
      { label: t("P50 · Median"), value: metric.median },
      { label: "P75", value: metric.p75 },
    ];

    return {
      animationDuration: 520,
      animationDurationUpdate: 320,
      animationEasing: "cubicOut",
      grid: { left: 28, right: 28, top: 28, bottom: 29 },
      tooltip: {
        trigger: "item",
        confine: true,
        backgroundColor: tooltipBackground,
        borderColor: tooltipBorder,
        borderWidth: 1,
        padding: [9, 11],
        textStyle: { color: tooltipText, fontSize: 12 },
        extraCssText: "max-width:240px;box-shadow:0 14px 36px rgba(0,0,0,.28);",
      },
      xAxis: {
        type: "value",
        min: domain.min,
        max: domain.max,
        show: false,
      },
      yAxis: {
        type: "category",
        data: [""],
        show: false,
      },
      series: [
        {
          name: t("P25 to P75 range"),
          type: "line",
          data: [[metric.p25, 0], [metric.p75, 0]],
          showSymbol: false,
          silent: true,
          lineStyle: {
            width: 7,
            color: rangeColor,
            cap: "round",
          },
          z: 1,
        },
        ...quartiles.map((quartile) => ({
          name: quartile.label,
          type: "line",
          data: [[quartile.value, 0]],
          showSymbol: true,
          symbol: "rect",
          symbolSize: quartile.value === metric.median ? [4, 22] : [3, 18],
          lineStyle: { opacity: 0 },
          itemStyle: {
            color: quartile.value === metric.median ? (dark ? "#d1d8e0" : "#465461") : benchmarkColor,
          },
          label: {
            show: true,
            position: "top",
            distance: 7,
            color: labelColor,
            fontSize: 10,
            lineHeight: 14,
            formatter: `${quartile.label}\n${formatValue(quartile.value)}`,
          },
          tooltip: {
            formatter: () => `${quartile.label}<br/><strong>${formatValue(quartile.value)}</strong>`,
          },
          emphasis: {
            scale: 1.15,
            itemStyle: { shadowBlur: 8, shadowColor: "rgba(135, 224, 233, .22)" },
          },
          z: 3,
        })),
        {
          name: t("Demo User"),
          type: "line",
          data: [[metric.user, 0]],
          showSymbol: true,
          symbol: "circle",
          symbolSize: 15,
          lineStyle: { opacity: 0 },
          itemStyle: {
            color: "#b9f5f7",
            borderColor: dark ? "#15313a" : "#ffffff",
            borderWidth: 3,
            shadowBlur: 12,
            shadowColor: "rgba(94, 211, 223, .42)",
          },
          label: {
            show: true,
            position: "bottom",
            distance: 8,
            color: dark ? "#e8f4f5" : "#20313a",
            fontSize: 11,
            fontWeight: 600,
            formatter: t("You {value} · {percentile}", {
              value: formatValue(metric.user),
              percentile: t("Percentile {percentile}", { percentile: formatNumber(metric.percentile) }),
            }),
          },
          tooltip: {
            formatter: () => [
              `<strong>${t("Demo User")}</strong>`,
              `${t("Value")}: ${formatValue(metric.user)}`,
              `${t("Percentile")}: ${formatNumber(metric.percentile)}`,
              `P25: ${formatValue(metric.p25)}`,
              `${t("Median")}: ${formatValue(metric.median)}`,
              `P75: ${formatValue(metric.p75)}`,
            ].join("<br/>"),
          },
          emphasis: {
            scale: 1.22,
            itemStyle: {
              shadowBlur: 18,
              shadowColor: "rgba(94, 211, 223, .58)",
            },
          },
          z: 5,
        },
      ],
    };
  }, [dark, formatNumber, metric, t]);

  return (
    <EChart
      option={option}
      label={t("{metric} cohort range: P25 {p25}, median {median}, P75 {p75}; you {user}, {percentile}.", {
        metric: t(metric.label),
        p25: formatValue(metric.p25),
        median: formatValue(metric.median),
        p75: formatValue(metric.p75),
        user: formatValue(metric.user),
        percentile: t("Percentile {percentile}", { percentile: formatNumber(metric.percentile) }),
      })}
      className="h-[84px] w-full"
    />
  );
}
