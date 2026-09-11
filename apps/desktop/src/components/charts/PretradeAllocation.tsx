import { useState } from "react";
import { use } from "echarts/core";
import { PieChart } from "echarts/charts";
import type { EChartsOption } from "echarts";
import { EChart } from "./EChart";
import { allocationRows, allocationShare, type AllocationBasis } from "@/data/allocationComparison";
import type { PretradeImpactStateView } from "@/data/pretradeImpact";
import { showcaseInstrumentName } from "@/data/showcaseDemo";
import { useLocale } from "@/locales/LocaleProvider";
import { pretradeCopy } from "@/locales/pretrade";
import "./pretrade-allocation.css";

use([PieChart]);

export function PretradeAllocation({ before, after, symbol }: {
  before: PretradeImpactStateView; after: PretradeImpactStateView; symbol: string;
}) {
  const { locale, formatPercent } = useLocale();
  const c = pretradeCopy[locale];
  const [basis, setBasis] = useState<AllocationBasis>("account");
  const [selected, setSelected] = useState(`security:${symbol}`);
  const currency = (value: number) => new Intl.NumberFormat(locale, { style: "currency", currency: "CNY" }).format(value);
  if (!before.allocations || !after.allocations) return <p className="p-6 text-sm text-muted">{c.unavailable}</p>;
  const rows = allocationRows(before.allocations, after.allocations, basis);
  const chosen = rows.find((row) => row.id === selected) ?? rows[0];
  const name = (row: typeof rows[number]) => showcaseInstrumentName(
    row.identity.kind === "cash" ? "cash" : row.identity.symbol!,
    locale,
    row.identity.kind === "cash" ? c.cash : row.identity.symbol!,
  );
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const option = (side: "before" | "after"): EChartsOption => ({
    animation: !reduced, animationDuration: 550, animationDurationUpdate: 350,
    tooltip: { trigger: "item", confine: true, renderMode: "richText",
      formatter: (params: unknown) => {
        const row = rows[(params as { dataIndex: number }).dataIndex];
        const point = row?.[side];
        return row ? `${name(row)}\n${c.value}  ${currency(point?.value ?? 0)}\n${c.share}  ${formatPercent(allocationShare(point, basis), 2)}` : "";
      },
    },
    series: [{ type: "pie", id: "allocation", radius: ["64%", "86%"], center: ["50%", "50%"],
      startAngle: 90, clockwise: true, padAngle: 1.2, stillShowZeroSum: false,
      label: { show: false }, labelLine: { show: false },
      emphasis: { scale: true, scaleSize: 4 },
      data: rows.map((row) => ({ id: row.id, name: name(row), value: allocationShare(row[side], basis),
        itemStyle: { color: row.colour, opacity: row.id === chosen?.id ? 1 : 0.62, borderRadius: 4 },
      })),
    }],
  });
  return <section className="pretrade-allocation" aria-label={c.title}>
    <header><h2>{c.title}</h2><p>{c.detail}</p></header>
    <div className="allocation-basis" role="group" aria-label={c.held}>
      <button type="button" aria-pressed={basis === "account"} onClick={() => setBasis("account")}>{c.account}</button>
      <button type="button" aria-pressed={basis === "securities"} onClick={() => setBasis("securities")}>{c.securities}</button>
    </div>
    <p className="allocation-caption">{basis === "account" ? c.accountBasis : c.securityBasis}</p>
    <div className="allocation-pair">
      {(["before", "after"] as const).map((side) => <div className="allocation-state" key={side}>
        <h3>{c[side]}</h3>
        <div className="allocation-ring">
          <EChart option={option(side)} label={`${c[side]} · ${c.held}`} className="allocation-chart"
            onChartClick={(event) => { const row = rows[event.dataIndex]; if (row) setSelected(row.id); }} />
          <div className="allocation-center"><span>{chosen ? name(chosen) : c.held}</span>
            <strong>{formatPercent(allocationShare(chosen?.[side] ?? null, basis), 2)}</strong>
            <small>{chosen?.identity.symbol === symbol ? c.target : c.selected}</small>
          </div>
        </div>
        <p className="allocation-caption">{c.date} · {(side === "before" ? before : after).valuationDate ?? "—"}</p>
      </div>)}
    </div>
    <div className="allocation-legend" aria-label={c.selected}>
      {rows.map((row) => <button type="button" key={row.id} aria-pressed={chosen?.id === row.id} onClick={() => setSelected(row.id)}>
        <i style={{ background: row.colour }} /><span>{name(row)}</span>
        <small>{formatPercent(allocationShare(row.before, basis), 2)} → {formatPercent(allocationShare(row.after, basis), 2)}</small>
      </button>)}
    </div>
    {chosen && <div className="allocation-detail" aria-live="polite">
      <strong>{name(chosen)}</strong><span>{c.value}</span>
      <b>{chosen.before ? currency(chosen.before.value) : c.noPosition} → {chosen.after ? currency(chosen.after.value) : c.noPosition}</b>
    </div>}
    <footer><strong>{c.scope}</strong><p>{c.scopeDetail}</p></footer>
  </section>;
}
