import { AlertCircle, FlaskConical, Scale } from "lucide-react";
import { useMemo, useState } from "react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Input } from "@/components/ui/input";
import { pretradeDemo } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";

export function DecisionCheckPage() {
  const { formatNumber, formatPercent, locale, t } = useLocale();
  const [symbol, setSymbol] = useState(pretradeDemo.symbol);
  const [side, setSide] = useState<"BUY" | "SELL">(pretradeDemo.side);
  const [quantity, setQuantity] = useState(String(pretradeDemo.quantity));
  const [executionPrice, setExecutionPrice] = useState(String(pretradeDemo.executionPrice));
  const isFixedScenario = useMemo(
    () =>
      symbol.trim().toUpperCase() === pretradeDemo.symbol
      && side === pretradeDemo.side
      && Number(quantity) === pretradeDemo.quantity
      && Number(executionPrice) === pretradeDemo.executionPrice,
    [executionPrice, quantity, side, symbol],
  );
  const currency = (value: number) => new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(value);
  const signed = (value: number, formatter: (number: number) => string) => (
    `${value > 0 ? "+" : ""}${formatter(value)}`
  );
  const proposedAt = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(pretradeDemo.proposedTime));
  const complete = pretradeDemo.status === "complete"
    && pretradeDemo.before
    && pretradeDemo.after
    && pretradeDemo.delta
    && pretradeDemo.selfContext
    && pretradeDemo.peerContext
    ? {
        before: pretradeDemo.before,
        after: pretradeDemo.after,
        delta: pretradeDemo.delta,
        selfContext: pretradeDemo.selfContext,
        peerContext: pretradeDemo.peerContext,
      }
    : null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Pre-decision context")}
        title={t("Decision Check")}
        description={t("A deterministic demo scenario for reviewing evidence context before a proposed action. This interface does not provide a buy or sell recommendation.")}
      />

      <GlassPanel className="p-6">
        <SectionHeading
          eyebrow={t("Backend-generated synthetic scenario")}
          title={t("Describe the proposed action")}
          description={t("Only the registered quantity and proposed execution price below have deterministic backend context. Changing an input clears the displayed result.")}
        />
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="grid gap-2 text-sm font-medium">
            {t("Symbol")}
            <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-label={t("Symbol")} />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Side")}
            <select
              className="h-10 rounded-md border border-border/80 bg-black/[0.08] px-3 text-sm text-foreground outline-none focus:border-accent/45 focus:ring-2 focus:ring-accent/15 dark:bg-white/[0.035]"
              value={side}
              onChange={(event) => setSide(event.target.value as "BUY" | "SELL")}
              aria-label={t("Side")}
            >
              <option value="BUY">{t("Buy")}</option>
              <option value="SELL">{t("Sell")}</option>
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Quantity")}
            <Input
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              aria-label={t("Quantity")}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Proposed execution price (CNY)")}
            <Input
              inputMode="decimal"
              value={executionPrice}
              onChange={(event) => setExecutionPrice(event.target.value)}
              aria-label={t("Proposed execution price in CNY")}
            />
          </label>
        </div>
        <p className="mt-4 text-xs leading-5 text-muted">
          {t("Registered scenario: {side} {quantity} {symbol} at CNY {price}, recorded fees CNY {fees}, at {time}.", {
            side: t(pretradeDemo.side === "BUY" ? "Buy" : "Sell"),
            quantity: formatNumber(pretradeDemo.quantity),
            symbol: pretradeDemo.symbol,
            price: formatNumber(pretradeDemo.executionPrice, 2),
            fees: formatNumber(pretradeDemo.fees, 2),
            time: proposedAt,
          })}
        </p>
      </GlassPanel>

      {isFixedScenario && complete ? (
        <GlassPanel className="overflow-hidden">
          <div className="p-6 pb-4">
            <SectionHeading
              eyebrow={t("Deterministic vectorbt replay")}
              title={t("Current → proposed trade")}
              description={t("If executed at the stated proposed price and quantity, the portfolio would change as follows. No future return or price is estimated.")}
            />
          </div>
          <dl className="grid border-t border-border/60 md:grid-cols-3">
            {[
              {
                label: t("Target symbol weight"),
                before: formatPercent(complete.before.symbolWeight, 2),
                after: formatPercent(complete.after.symbolWeight, 2),
                delta: signed(complete.delta.symbolWeight * 100, (value) => `${formatNumber(value, 2)} pp`),
              },
              {
                label: t("Cash"),
                before: currency(complete.before.cash),
                after: currency(complete.after.cash),
                delta: signed(complete.delta.cash, currency),
              },
              {
                label: "HHI",
                before: formatNumber(complete.before.hhi, 4),
                after: formatNumber(complete.after.hhi, 4),
                delta: signed(complete.delta.hhi, (value) => formatNumber(value, 4)),
              },
            ].map((item) => (
              <div key={item.label} className="border-b border-r border-border/60 p-5 last:border-r-0">
                <dt className="text-xs uppercase tracking-[0.1em] text-muted">{item.label}</dt>
                <dd className="mt-2 text-lg font-semibold tabular-nums text-foreground">
                  {item.before} <span className="px-1 text-muted">→</span> {item.after}
                </dd>
                <p className="mt-1 text-xs tabular-nums text-muted">{t("Change {value}", { value: item.delta })}</p>
              </div>
            ))}
          </dl>

          <dl className="grid border-b border-border/60 md:grid-cols-3">
            {[
              [t("Portfolio value"), `${currency(complete.before.portfolioValue)} → ${currency(complete.after.portfolioValue)}`],
              [t("Target symbol quantity"), `${formatNumber(complete.before.symbolQuantity)} → ${formatNumber(complete.after.symbolQuantity)}`],
              [t("Active assets"), `${formatNumber(complete.before.activeAssets)} → ${formatNumber(complete.after.activeAssets)}`],
            ].map(([label, value]) => (
              <div key={label} className="border-r border-border/60 px-5 py-3 last:border-r-0">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-1 text-sm font-medium tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="grid gap-4 p-6 lg:grid-cols-2">
            <div className="rounded-md border border-border/70 bg-white/[0.025] p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Scale className="size-4 text-accent" aria-hidden="true" />
                {t("Self HHI context")}
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Historical HHI median")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.selfContext.historicalHhiMedian, 4)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Current HHI")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.selfContext.currentHhi, 4)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Proposed-trade HHI")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.selfContext.proposedHhi, 4)}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-muted">
                {t("{count} valid historical HHI observations · {method}", {
                  count: formatNumber(complete.selfContext.historicalObservationCount),
                  method: complete.selfContext.historyMethodId,
                })}
              </p>
            </div>

            <div className="rounded-md border border-border/70 bg-white/[0.025] p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <FlaskConical className="size-4 text-accent" aria-hidden="true" />
                {t("Synthetic peer HHI context")}
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Cohort HHI median")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.peerContext.cohortHhiMedian, 4)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Current percentile")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.peerContext.currentPercentile, 1)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">{t("Proposed-trade percentile")}</dt>
                  <dd className="font-medium tabular-nums">{formatNumber(complete.peerContext.proposedPercentile, 1)}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-muted">
                {t("Synthetic cohort N={cohortN} · metric N={metricN} · {method}", {
                  cohortN: formatNumber(complete.peerContext.cohortN),
                  metricN: formatNumber(complete.peerContext.metricN),
                  method: complete.peerContext.percentileMethod,
                })}
              </p>
            </div>
          </div>

          <StateNotice
            state="demo"
            compact
            title={t("Synthetic scenario boundary")}
            detail={t("This backend-generated scenario is deterministic demo evidence. It is not a recommendation and does not predict price or return.")}
          />
        </GlassPanel>
      ) : isFixedScenario ? (
        <StateNotice
          state="insufficient"
          title={t("Scenario evidence unavailable")}
          detail={pretradeDemo.reason ?? t("The deterministic backend could not produce complete pre-trade evidence for this scenario.")}
        />
      ) : (
        <StateNotice
          state="empty"
          title={t("No deterministic output for this input")}
          detail={t("This demo does not calculate changed inputs in the browser. Return to the registered symbol, side, quantity, and proposed execution price to view backend-generated evidence.")}
        />
      )}

      <div className="flex items-start gap-3 rounded-md border border-border/70 bg-white/[0.025] p-4 text-sm leading-6 text-muted">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
        <p>
          <span className="font-medium text-foreground">{t("No recommendation.")}</span>{" "}
          {t("This check surfaces evidence context only; it does not tell you to buy, sell, hold, or change an order.")}
        </p>
      </div>
    </div>
  );
}
