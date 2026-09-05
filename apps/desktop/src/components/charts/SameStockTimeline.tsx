import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { EChart } from "./EChart";
import { useLocale } from "@/locales/LocaleProvider";
import { comparisonHighlight, executionLaneOffset, type CompareView } from "@/data/sameStock";

export function SameStockTimeline({ view, selected, focusedDecisionId }: { view: CompareView; selected: string | null; focusedDecisionId?: string | null }) {
  const { locale, t } = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const focusedA = view.a.decisions.find((d) => d.id === focusedDecisionId);
    const focusedB = view.b.decisions.find((d) => d.id === focusedDecisionId);
    const focused = focusedA ?? focusedB;
    const highlight = comparisonHighlight(view, selected) ?? (focused ? {
      start: focused.at, end: focused.at, aRefs: focusedA ? [focusedA.id] : [], bRefs: focusedB ? [focusedB.id] : [],
    } : null);
    const times = [...view.prices.map((x) => Date.parse(x.at)), ...[view.a, view.b].flatMap((s) => s.decisions.map((d) => Date.parse(d.at)))];
    const min = Math.min(...times), max = Math.max(...times) + 86400000;
    const tick = (v: number) => new Intl.DateTimeFormat(locale, { month: "numeric", day: "numeric" }).format(v);
    const axes = [0, 1, 2].map((gridIndex) => ({ type: "time", gridIndex, min, max, axisLabel: { color: "#a3b5c6", hideOverlap: true, formatter: tick }, axisLine: { lineStyle: { color: "#334155" } }, splitLine: { show: false } }));
    const area = highlight ? { silent: true, itemStyle: { color: "rgba(122,204,237,0.09)" }, data: [[{ xAxis: Date.parse(highlight.start) }, { xAxis: Date.parse(highlight.end) }]] } : undefined;
    const colors = ["#8cdaf2", "#debfa1"];
    return {
      animationDuration: 240, axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [{ left: 58, right: 25, top: 30, height: 160 }, { left: 58, right: 25, top: 233, height: 75 }, { left: 58, right: 25, top: 354, height: 118 }],
      xAxis: axes,
      yAxis: [{ type: "value", scale: true, axisLabel: { color: "#a3b5c6" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.1)" } } }, { type: "category", gridIndex: 1, data: ["B", "A"], axisLabel: { color: "#e2e8f0" }, splitLine: { show: false } }, { type: "value", gridIndex: 2, min: 0, max: 1, interval: .5, axisLabel: { color: "#a3b5c6" }, splitLine: { lineStyle: { color: "rgba(148,163,184,.1)" } } }],
      tooltip: { trigger: "item", confine: true, renderMode: "richText", backgroundColor: "#101c29", textStyle: { color: "#edf2f7" }, formatter: (raw: unknown) => { const p = raw as { seriesName: string; data: { detail?: string; value?: unknown[] } | unknown[] }; if (!Array.isArray(p.data) && p.data.detail) return p.data.detail; const values = Array.isArray(p.data) ? p.data : p.data.value ?? []; return `${p.seriesName}\n${tick(Number(values[0]))}\n${values[1]}`; } },
      dataZoom: [{ type: "slider", xAxisIndex: [0, 1, 2], bottom: 2, height: 18, borderColor: "transparent", textStyle: { color: "#a3b5c6" } }, { type: "inside", xAxisIndex: [0, 1, 2], filterMode: "none" }],
      series: [
        { name: t("Shared recorded market price"), type: "line", showSymbol: view.prices.length <= 1, connectNulls: false, lineStyle: { color: "#a4b9c9", width: 1.6 }, data: view.prices.map((p) => [Date.parse(p.at), p.value]), markArea: area },
        ...[view.a, view.b].map((side, i) => ({ name: `${i === 0 ? "A" : "B"} · ${t("Recorded decisions")}`, type: "scatter", xAxisIndex: 1, yAxisIndex: 1,
          data: side.decisions.map((d, index) => ({ symbolOffset: [0, executionLaneOffset(side.decisions, index)], value: [Date.parse(d.at), i === 0 ? "A" : "B"], symbol: ({ open_position: "circle", add_position: "diamond", reduce_position: "triangle", close_position: "rect" } as Record<string, string>)[d.kind], symbolSize: (i === 0 ? highlight?.aRefs : highlight?.bRefs)?.includes(d.id) ? 19 : 12, itemStyle: { color: colors[i] }, detail: `${i === 0 ? "A" : "B"} · ${t(d.kind)}\n${d.at}\n${t("Position quantity")}: ${d.before} → ${d.after}\n${t("Execution price")}: ${d.price} ${side.currency}\n${t("Average cost")}: ${d.costBefore ?? "—"} → ${d.costAfter ?? "—"}` })), markArea: area })),
        ...[view.a, view.b].map((side, i) => ({ name: `${i === 0 ? "A" : "B"} · ${t("Position shape (not risk)")}`, type: "line", step: "end", xAxisIndex: 2, yAxisIndex: 2, showSymbol: false, lineStyle: { color: colors[i], width: 2 }, data: side.shape.map((p) => ({ value: [Date.parse(p.at), p.value], detail: `${i === 0 ? "A" : "B"}\n${p.at}\n${t("Position quantity")}: ${p.quantity}\n${t("Average cost")}: ${p.cost ?? "—"}\n${t("Position shape (not risk)")}: ${p.value}` })), markArea: area })),
      ],
    };
  }, [view, selected, focusedDecisionId, locale, t]);
  if (!view.prices.length || view.status === "unavailable") return null;
  return <EChart option={option} label={t("Shared market, two decision lanes and position shapes")} className="h-[530px] w-full" resetKey={view.id} />;
}
