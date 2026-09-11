import { useEffect, useMemo, useState, type ReactNode } from "react";
import { PieChart } from "echarts/charts";
import { use, type EChartsCoreOption } from "echarts/core";
import { LegendComponent } from "echarts/components";
import { EChart } from "@/components/charts/EChart";
import {
  dailyTimeCoordinate,
  minDailyZoomSpanMs,
  uniqueDailyObservationTimes,
  MS_PER_DAY,
} from "@/components/charts/dailyTimeAxis";
import { createAdaptiveDailyAxisFormatter } from "@/components/charts/dailyTimeNavigation";
import { TimeSeriesFrame } from "@/components/charts/TimeSeriesFrame";
import { frameDailyTimeDomain, frameDataZoom } from "@/components/charts/timeSeriesFrameOptions";
import { useDailyTimeNavigation } from "@/components/charts/useDailyTimeNavigation";
import type { AllocationSlice, ComparisonResearch, ResearchOperation, ResearchPair, ResearchPeriod } from "@/data/comparisonResearch";
import { useLocale } from "@/locales/LocaleProvider";
import { researchComparisonCopy } from "./researchComparisonCopy";
import "./research-comparison.css";

use([PieChart, LegendComponent]);

type Props = { left: ResearchPeriod; right: ResearchPeriod; leftLabel: string; rightLabel: string; names: ComparisonResearch["names"]; samePeriod: boolean; comparison?: ResearchPair };
type Metric = "nav" | "drawdown";
const colours = ["#8cdaf2", "#debfa1", "#9bd8b0", "#b5a8f0", "#e69b9a", "#e9d37b", "#8ba4d8"];
const shortDate = (date: string) => date.slice(0, 10);

export function ResearchPortfolioComparison({ left, right, leftLabel, rightLabel, names, samePeriod, comparison }: Props) {
  const { locale } = useLocale();
  const c = researchComparisonCopy(locale);
  const [metric, setMetric] = useState<Metric>("nav");
  const [benchmark, setBenchmark] = useState(false);
  const [basis, setBasis] = useState<"direct" | "underlying">("direct");
  const [selectedHolding, setSelectedHolding] = useState<string | null>(null);
  const [selectedOperation, setSelectedOperation] = useState<{ side: "left" | "right"; operation: ResearchOperation } | null>(null);
  useEffect(() => { setSelectedOperation(null); }, [left.startDate, left.endDate, right.startDate, right.endDate]);
  useEffect(() => { setSelectedHolding(null); }, [basis, left.allocation.date, right.allocation.date]);
  const label = (id: string) => names[id]?.[locale === "zh-CN" ? "zh" : "en"] ?? id;
  const percent = (value: number | null, digits = 1) => value === null ? c.noValue : new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: digits }).format(value);
  const number = (value: number | null, digits = 2) => value === null ? c.noValue : new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value);
  const money = (value: number) => new Intl.NumberFormat(locale, { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(value);
  const periodItems = [{ period: left, label: leftLabel }, { period: right, label: rightLabel }];
  const selection = selectedHolding ? findUnderlying(selectedHolding, left, right) : null;
  const ids = useMemo(() => Array.from(new Set([...left.allocation.direct, ...left.allocation.underlying, ...right.allocation.direct, ...right.allocation.underlying].map((slice) => slice.id))), [left, right]);
  const visibleIds = Array.from(new Set([...(basis === "direct" ? left.allocation.direct : left.allocation.underlying), ...(basis === "direct" ? right.allocation.direct : right.allocation.underlying)].map(s => s.id)));
  const colour = (id: string) => colours[Math.max(0, ids.indexOf(id)) % colours.length];
  return <section className="research-comparison" aria-label={c.result}>
    <header className="research-comparison__intro"><div><h2>{c.result}</h2><p>{samePeriod ? c.samePeriod : c.separatePeriods}</p></div></header>
    {comparison && <div className="research-comparison__differences"><p>{c.differenceDirection}: {rightLabel} − {leftLabel}</p><div>
      {comparison.differences.filter(d => ["period_return", "max_drawdown_magnitude", "portfolio_hhi"].includes(d.id)).map(d => <button type="button" key={d.id} onClick={() => {
        document.getElementById(d.id === "portfolio_hhi" ? "comparison-allocation" : "comparison-performance")?.scrollIntoView({ block: "center", behavior: "auto" });
        if (d.id === "max_drawdown_magnitude") setMetric("drawdown");
        else if (d.id === "period_return") setMetric("nav");
      }}>
        <span>{({ period_return: c.return, max_drawdown_magnitude: c.drawdown, portfolio_hhi: c.hhi } as Record<string,string>)[d.id]}</span>
        <strong>{d.change === null ? c.noValue : `${d.change > 0 ? "+" : ""}${number(d.change, d.unit === "index" ? 3 : 2)}`}{d.unit === "percentage_points" ? ` ${c.pp}` : ""}</strong>
        <small>{c.viewChange} →</small>
      </button>)}
    </div></div>}
    <div className="research-comparison__result-grid">{periodItems.map(({ period, label }) => <PeriodCard key={label} period={period} label={label} c={c} percent={percent} number={number} />)}</div>
    <section id="comparison-performance" className="research-comparison__chart">
      {samePeriod ? <PerformanceSeriesChart periods={periodItems} title={c.performance} subtitle={c.samePeriod} metric={metric} includeBenchmark={metric === "nav" && benchmark} leftLabel={leftLabel} locale={locale} c={c} percent={percent} number={number} toolbar={<PerformanceToolbar metric={metric} benchmark={benchmark} c={c} onMetric={setMetric} onBenchmark={setBenchmark} />} /> : <><div className="research-comparison__chart-head"><div><h2>{c.performance}</h2><p className="research-comparison__note">{c.separatePeriods}</p></div><PerformanceToolbar metric={metric} benchmark={benchmark} c={c} onMetric={setMetric} onBenchmark={setBenchmark} /></div><div className="research-comparison__separate-series">{periodItems.map((item) => <PerformanceSeriesChart key={item.label} periods={[item]} title={item.label} subtitle={`${item.period.startDate} — ${item.period.endDate}`} metric={metric} includeBenchmark={metric === "nav" && benchmark} leftLabel={leftLabel} locale={locale} c={c} percent={percent} number={number} className="research-comparison__mini" />)}</div></>}
      <p className="research-comparison__note">{metric === "nav" ? c.navExplanation : c.drawdownExplanation}</p>
      {metric === "nav" && benchmark && <p className="research-comparison__note">{c.benchmarkExplanation}</p>}
    </section>
    <section id="comparison-allocation" className="research-comparison__allocation"><div className="research-comparison__allocation-head"><div><h2>{c.allocation}</h2><p className="research-comparison__note">{c.cashIncluded}</p></div><div className="research-comparison__switch" role="group" aria-label={c.allocation}>{(["direct", "underlying"] as const).map((item) => <button type="button" key={item} aria-pressed={basis === item} onClick={() => setBasis(item)}>{item === "direct" ? c.direct : c.underlying}</button>)}</div></div>
      <div className="research-comparison__allocation-grid">{periodItems.map(({ period, label: periodLabel }) => <AllocationPie key={periodLabel} period={period} periodLabel={periodLabel} basis={basis} selected={selectedHolding} onSelect={setSelectedHolding} label={label} percent={percent} colour={colour} c={c} />)}</div>
      <div className="research-comparison__legend">{visibleIds.map((id) => <button type="button" key={id} aria-pressed={selectedHolding === id} onClick={() => setSelectedHolding(id)}><i style={{ background: colour(id) }} /><span>{label(id)}</span></button>)}</div>
      {basis === "underlying" && periodItems.map(({ period, label: periodLabel }) => <p key={periodLabel} className="research-comparison__note">{periodLabel}{period.allocation.disclosures.map(d => ` · ${label(d.fundId)} · ${c.fundDisclosure}: ${d.publishedDate} (${c.holdingsAsOf}: ${d.effectiveDate})`).join("")}</p>)}
      {basis === "underlying" && selection ? <HoldingDetail selection={selection} label={label} leftLabel={leftLabel} rightLabel={rightLabel} c={c} percent={percent} /> : null}
    </section>
    <section className="research-comparison__operations"><div><h2>{c.operations}</h2><p className="research-comparison__note">{c.operationsDetail}</p></div><div className="research-comparison__operation-grid">{periodItems.map(({ period, label: periodLabel }, index) => <OperationList key={periodLabel} period={period} label={periodLabel} selected={selectedOperation?.operation.id ?? null} onSelect={(operation) => setSelectedOperation({ side: index === 0 ? "left" : "right", operation })} name={label} c={c} number={number} />)}</div>{selectedOperation ? <OperationDetail item={selectedOperation.operation} side={selectedOperation.side === "left" ? leftLabel : rightLabel} name={label} c={c} number={number} money={money} /> : null}</section>
    <section className="research-comparison__behavior"><div><h2>{c.behavior}</h2><p className="research-comparison__note">{c.hhiExplanation} {c.turnoverExplanation}</p></div><div className="research-comparison__result-grid">{periodItems.map(({ period, label: periodLabel }) => <BehaviorCard key={periodLabel} period={period} label={periodLabel} c={c} percent={percent} money={money} />)}</div><p className="research-comparison__note">{c.behaviorExplanation}</p></section>
  </section>;
}

function PerformanceToolbar({ metric, benchmark, c, onMetric, onBenchmark }: { metric: Metric; benchmark: boolean; c: ReturnType<typeof researchComparisonCopy>; onMetric: (metric: Metric) => void; onBenchmark: (benchmark: boolean) => void }) {
  return <div className="research-comparison__performance-tools"><div className="research-comparison__switch" role="group" aria-label={c.performance}>{(["nav", "drawdown"] as const).map((item) => <button type="button" key={item} aria-pressed={metric === item} onClick={() => onMetric(item)}>{item === "nav" ? c.nav : c.drawdownPath}</button>)}</div>{metric === "nav" && <label className="research-comparison__benchmark"><input type="checkbox" checked={benchmark} onChange={(event) => onBenchmark(event.target.checked)} />{c.benchmark}</label>}</div>;
}

function PerformanceSeriesChart({ periods, title, subtitle, metric, includeBenchmark, leftLabel, locale, c, percent, number, toolbar, className }: { periods: { period: ResearchPeriod; label: string }[]; title: string; subtitle: string; metric: Metric; includeBenchmark: boolean; leftLabel: string; locale: string; c: ReturnType<typeof researchComparisonCopy>; percent: (value: number | null, digits?: number) => string; number: (value: number | null, digits?: number) => string; toolbar?: ReactNode; className?: string }) {
  const observationTimes = useMemo(() => uniqueDailyObservationTimes(periods.flatMap(({ period }) => [
    ...period.performance.points.map((point) => point.date),
    ...period.benchmark.points.map((point) => point.date),
  ])), [periods]);
  const navigation = useDailyTimeNavigation(`research-performance:${periods.map(({ period }) => `${period.startDate}:${period.endDate}`).join("|")}`, observationTimes);
  const option = useMemo<EChartsCoreOption>(() => ({
    animationDuration: 220,
    tooltip: {
      trigger: "axis",
      confine: true,
      renderMode: "richText",
      formatter: (raw: unknown) => {
        const items = (Array.isArray(raw) ? raw : [raw]) as { seriesName: string; value: [number, number | null] }[];
        return items.map((point) => `${shortDate(new Date(point.value[0]).toISOString())} · ${point.seriesName}\n${metric === "drawdown" ? percent(point.value[1], 2) : number(point.value[1], 2)}`).join("\n");
      },
    },
    legend: { top: 2, textStyle: { color: "#a3b5c6" } },
    grid: { left: 48, right: 20, top: 36, bottom: 42 },
    xAxis: {
      type: "time",
      minInterval: MS_PER_DAY,
      ...frameDailyTimeDomain(observationTimes),
      splitNumber: 3,
      axisLabel: { color: "#a3b5c6", hideOverlap: true, formatter: createAdaptiveDailyAxisFormatter(locale, () => navigation.getDomain()) },
      axisLine: { lineStyle: { color: "#334155" } },
    },
    yAxis: { type: "value", scale: true, axisLabel: { color: "#a3b5c6", formatter: (value: number) => metric === "drawdown" ? percent(value, 0) : number(value, 0) }, splitLine: { lineStyle: { color: "rgba(148,163,184,.12)" } } },
    dataZoom: frameDataZoom(minDailyZoomSpanMs(observationTimes)),
    series: [
      ...periods.map(({ period, label }) => ({
        name: label,
        type: "line" as const,
        showSymbol: false,
        connectNulls: false,
        smooth: false,
        itemStyle: { color: label === leftLabel ? colours[0] : colours[1] },
        lineStyle: { width: 2, color: label === leftLabel ? colours[0] : colours[1] },
        data: period.performance.points.map((point) => [dailyTimeCoordinate(point.date), metric === "nav" ? point.nav : point.drawdown] as [number, number | null]),
      })),
      ...(includeBenchmark ? [{
        name: c.market,
        type: "line" as const,
        showSymbol: false,
        connectNulls: false,
        smooth: false,
        lineStyle: { width: 1.5, type: "dashed" as const, color: "#a7b2c0" },
        data: periods[0].period.benchmark.points.map((point) => [dailyTimeCoordinate(point.date), metric === "nav" ? point.nav : null] as [number, number | null]),
      }] : []),
    ],
  }), [c.market, includeBenchmark, leftLabel, locale, metric, navigation, number, observationTimes, percent, periods]);

  return <TimeSeriesFrame title={title} subtitle={subtitle} navigation={navigation} toolbar={toolbar} className={`time-series-frame--single ${className ?? ""}`}>
    <EChart option={option} label={`${title} ${c.performance}`} className="research-comparison__series" resetKey={title} timeNavigation={navigation} observationTimes={observationTimes} />
  </TimeSeriesFrame>;
}

function PeriodCard({ period, label, c, percent, number }: { period: ResearchPeriod; label: string; c: ReturnType<typeof researchComparisonCopy>; percent: (value: number | null, digits?: number) => string; number: (value: number | null, digits?: number) => string }) {
  const rows: [string, number | null, string][] = [[c.return, period.performance.periodReturn, "percent"], [c.drawdown, period.performance.maxDrawdown, "percent"], [c.volatility, period.performance.volatility, "percent"], [c.hhi, period.behavior.hhi, "number"], [c.turnover, period.behavior.turnover, "percent"]];
  return <article className="research-comparison__period"><div className="research-comparison__period-head"><h3>{label}</h3><p className="research-comparison__period-date">{period.startDate} — {period.endDate}</p></div><div className="research-comparison__metrics">{rows.map(([name, value, type]) => <div className={`research-comparison__metric ${value === null ? "research-comparison__metric--empty" : ""}`} key={name}><small>{name}</small><strong>{type === "percent" ? percent(value) : number(value)}</strong>{value === null ? <small>{c.unavailable}</small> : null}</div>)}</div><p className="research-comparison__note">{c.observation}: {period.performance.observationCount}</p><p className="research-comparison__recovery"><strong>{c.recovery}</strong> · {c.peak}: {period.performance.peakDate ?? c.noValue} · {c.trough}: {period.performance.troughDate ?? c.noValue} · {c.recovered}: {period.performance.recoveryDate ?? c.notRecovered}</p></article>;
}

function AllocationPie({ period, periodLabel, basis, selected, onSelect, label, percent, colour, c }: { period: ResearchPeriod; periodLabel: string; basis: "direct" | "underlying"; selected: string | null; onSelect: (id: string) => void; label: (id: string) => string; percent: (value: number | null, digits?: number) => string; colour: (id: string) => string; c: ReturnType<typeof researchComparisonCopy> }) {
  const slices = basis === "direct" ? period.allocation.direct : period.allocation.underlying;
  const chosen = slices.find((slice) => slice.id === selected) ?? (selected === null ? slices[0] : undefined);
  const option: EChartsCoreOption = { animationDuration: 220, tooltip: { trigger: "item", confine: true, renderMode: "richText", formatter: (raw: unknown) => { const dataIndex = Number((raw as { dataIndex?: number }).dataIndex); const slice = slices[dataIndex]; return slice ? `${label(slice.id)}\n${percent(slice.weight, 2)}` : ""; } }, series: [{ type: "pie", radius: ["58%", "82%"], label: { show: false }, labelLine: { show: false }, data: slices.map((slice) => ({ name: label(slice.id), value: slice.weight, itemStyle: { color: colour(slice.id), opacity: chosen?.id === slice.id ? 1 : .62 } })) }] };
  return <div><h3>{periodLabel}</h3><p className="research-comparison__period-date">{c.allocationDate}: {period.allocation.date}</p><div className="research-comparison__pie-wrap"><EChart option={option} label={`${periodLabel} ${c.allocation}`} className="research-comparison__pie" resetKey={`${periodLabel}-${basis}`} onChartClick={(event) => { const slice = slices[Number(event.dataIndex)]; if (slice) onSelect(slice.id); }} /><div className="research-comparison__pie-center"><span>{chosen ? label(chosen.id) : selected ? label(selected) : c.allocation}</span><strong>{chosen ? percent(chosen.weight, 1) : selected ? percent(0, 1) : c.noValue}</strong>{!chosen && selected ? <small>{c.notHeld}</small> : null}</div></div></div>;
}

function findUnderlying(id: string, left: ResearchPeriod, right: ResearchPeriod) { return [{ side: "left", slice: left.allocation.underlying.find((slice) => slice.id === id) }, { side: "right", slice: right.allocation.underlying.find((slice) => slice.id === id) }].filter((item): item is { side: string; slice: AllocationSlice } => Boolean(item.slice)); }
function HoldingDetail({ selection, label, leftLabel, rightLabel, c, percent }: { selection: { side: string; slice: AllocationSlice }[]; label: (id: string) => string; leftLabel: string; rightLabel: string; c: ReturnType<typeof researchComparisonCopy>; percent: (value: number | null, digits?: number) => string }) { const id = selection[0]?.slice.id; return <div className="research-comparison__holding-detail"><strong>{c.selectedHolding}: {id ? label(id) : c.noValue}</strong>{selection.map(({ side, slice }) => <dl key={side}><dt>{side === "left" ? leftLabel : rightLabel}</dt><dd>{percent(slice.weight, 2)}</dd><dt>{c.directWeight}</dt><dd>{percent(slice.directWeight ?? null, 2)}</dd><dt>{c.indirectWeight}</dt><dd>{percent(slice.indirectWeight ?? null, 2)}</dd><dt>{c.fundPath}</dt><dd>{slice.paths?.length ? slice.paths.map((path) => path.map(label).join(" → ")).join("; ") : c.noPath}</dd></dl>)}</div>; }
function OperationList({ period, label, selected, onSelect, name, c, number }: { period: ResearchPeriod; label: string; selected: string | null; onSelect: (operation: ResearchOperation) => void; name: (id: string) => string; c: ReturnType<typeof researchComparisonCopy>; number: (value: number | null, digits?: number) => string }) { return <div className="research-comparison__operation-list"><h3>{label}</h3>{period.operations.length ? period.operations.map((operation) => <button type="button" key={operation.id} className="research-comparison__operation" aria-pressed={selected === operation.id} onClick={() => onSelect(operation)}><small>{shortDate(operation.date)}</small><b>{name(operation.symbol)} · {(c.operationKinds as Record<string, string>)[operation.kind] ?? operation.kind}</b><span>{number(operation.quantity, 0)}</span></button>) : <p className="research-comparison__note">{c.noOperations}</p>}</div>; }
function OperationDetail({ item, side, name, c, number, money }: { item: ResearchOperation; side: string; name: (id: string) => string; c: ReturnType<typeof researchComparisonCopy>; number: (value: number | null, digits?: number) => string; money: (value: number) => string }) { return <article className="research-comparison__operation-detail" aria-live="polite"><h3>{side} · {name(item.symbol)} · {(c.operationKinds as Record<string, string>)[item.kind] ?? item.kind}</h3><dl><dt>{c.date}</dt><dd>{item.date.replace("T", " ")}</dd><dt>{c.beforeAfterQuantity}</dt><dd>{number(item.beforeQuantity, 0)} → {number(item.afterQuantity, 0)}</dd><dt>{c.beforeAfterCost}</dt><dd>{item.beforeCost === null ? c.noValue : money(item.beforeCost)} → {item.afterCost === null ? c.noValue : money(item.afterCost)}</dd><dt>{c.executionPrice}</dt><dd>{money(item.price)}</dd><dt>{c.fee}</dt><dd>{money(item.fee)}</dd></dl></article>; }
function BehaviorCard({ period, label, c, percent, money }: { period: ResearchPeriod; label: string; c: ReturnType<typeof researchComparisonCopy>; percent: (value: number | null, digits?: number) => string; money: (value: number) => string }) { return <article className="research-comparison__period research-comparison__behavior-card"><h3>{label}</h3><dl><dt>{c.fees}</dt><dd>{money(period.behavior.fees)}</dd><dt>{c.actionCount}</dt><dd>{period.behavior.actionCount}</dd><dt>{c.pgr}</dt><dd>{percent(period.behavior.pgr)}</dd><dt>{c.plr}</dt><dd>{period.behavior.plr === null ? c.noEligibleLossObservations : percent(period.behavior.plr)}</dd><dt>{c.pgrMinusPlr}</dt><dd>{percent(period.behavior.pgrMinusPlr)}</dd><dt>{c.lossAdds}</dt><dd>{period.behavior.lossEvents} / {period.behavior.eligibleAdds} · {percent(period.behavior.lossRate)}</dd></dl></article>; }
