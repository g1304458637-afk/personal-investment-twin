import { AlertCircle, FlaskConical, LoaderCircle, Scale } from "lucide-react";
import { useMemo, useReducer, useState } from "react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { pretradeDemo, pretradeExplainability } from "@/data/backendEvidence";
import {
  checkPretrade,
  createPretradeRequestId,
  currentPretradeRuntime,
  emptyPretradeRequestState,
  inputFromDemo,
  matchesOfflineDemo,
  PretradeServiceError,
  pretradeRequestReducer,
} from "@/data/pretradeService";
import { useLocale } from "@/locales/LocaleProvider";

export function DecisionCheckPage() {
  const { formatNumber, formatPercent, locale, t } = useLocale();
  const runtime = useMemo(currentPretradeRuntime, []);
  const [symbol, setSymbol] = useState(pretradeDemo.symbol);
  const [side, setSide] = useState<"BUY" | "SELL">(pretradeDemo.side);
  const [quantity, setQuantity] = useState(String(pretradeDemo.quantity));
  const [executionPrice, setExecutionPrice] = useState(String(pretradeDemo.executionPrice));
  const [fees, setFees] = useState(String(pretradeDemo.fees));
  const [requestState, dispatch] = useReducer(
    pretradeRequestReducer,
    emptyPretradeRequestState,
  );
  const impact = requestState.phase === "success" ? requestState.outcome.impact : null;
  // The generated explanation belongs only to its registered input, not a changed live scenario.
  const hasRegisteredExplanation = matchesOfflineDemo({
    ...inputFromDemo(pretradeDemo), symbol, side,
    quantity: Number(quantity), executionPrice: Number(executionPrice), fees: Number(fees),
  }, pretradeDemo);

  const markInputChanged = (update: () => void) => {
    dispatch({ type: "input_changed" });
    update();
  };

  const runCheck = async () => {
    const requestId = createPretradeRequestId();
    dispatch({ type: "started", requestId });
    try {
      const outcome = await checkPretrade(
        {
          ...inputFromDemo(pretradeDemo),
          symbol,
          side,
          quantity: Number(quantity),
          executionPrice: Number(executionPrice),
          fees: Number(fees),
        },
        { runtime, requestId, offlineDemo: pretradeDemo },
      );
      dispatch({ type: "succeeded", requestId, outcome });
    } catch (error) {
      const serviceError = error instanceof PretradeServiceError
        ? error
        : new PretradeServiceError(
            "unexpected_frontend_error",
            error instanceof Error ? error.message : String(error),
            requestId,
          );
      dispatch({ type: "failed", requestId, error: serviceError });
    }
  };

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
  const complete = impact?.status === "complete"
    && impact.before
    && impact.after
    && impact.delta
    && impact.selfContext
    && impact.peerContext
    ? {
        before: impact.before,
        after: impact.after,
        delta: impact.delta,
        selfContext: impact.selfContext,
        peerContext: impact.peerContext,
        executionPrice: impact.executionPrice,
        symbol: impact.symbol,
      }
    : null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Pre-decision context")}
        title={t("Decision Check")}
        description={t("Review deterministic evidence context before a proposed action. This interface does not provide a buy or sell recommendation.")}
      />

      <GlassPanel className="p-6">
        <SectionHeading
          eyebrow={runtime === "tauri_local" ? t("Local Python Runtime") : t("Demo / Offline Runtime")}
          title={t("Describe the proposed action")}
          description={runtime === "tauri_local"
            ? t("The desktop runtime sends this proposed action through a fixed local bridge to the existing deterministic engine.")
            : t("Browser mode cannot invoke local Python. Only the registered generated scenario is available as an offline demo.")}
        />
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <label className="grid gap-2 text-sm font-medium">
            {t("Symbol")}
            <Input
              value={symbol}
              onChange={(event) => markInputChanged(() => setSymbol(event.target.value))}
              aria-label={t("Symbol")}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Side")}
            <select
              className="h-10 rounded-md border border-border/80 bg-black/[0.08] px-3 text-sm text-foreground outline-none focus:border-accent/45 focus:ring-2 focus:ring-accent/15 dark:bg-white/[0.035]"
              value={side}
              onChange={(event) => markInputChanged(() => setSide(event.target.value as "BUY" | "SELL"))}
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
              onChange={(event) => markInputChanged(() => setQuantity(event.target.value))}
              aria-label={t("Quantity")}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Proposed execution price (CNY)")}
            <Input
              inputMode="decimal"
              value={executionPrice}
              onChange={(event) => markInputChanged(() => setExecutionPrice(event.target.value))}
              aria-label={t("Proposed execution price in CNY")}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Recorded fees (CNY)")}
            <Input
              inputMode="decimal"
              value={fees}
              onChange={(event) => markInputChanged(() => setFees(event.target.value))}
              aria-label={t("Recorded fees in CNY")}
            />
          </label>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            onClick={runCheck}
            disabled={requestState.phase === "loading"}
          >
            {requestState.phase === "loading" ? (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            ) : null}
            {requestState.phase === "loading" ? t("Checking changes…") : t("Check changes")}
          </Button>
          <span className="text-xs text-muted">
            {runtime === "tauri_local" ? t("Tauri → local Python → deterministic engine") : t("Synthetic generated fallback; not a live Python result")}
          </span>
        </div>
        <p className="mt-4 text-xs leading-5 text-muted">
          {t("Registered offline scenario: {side} {quantity} {symbol} at CNY {price}, recorded fees CNY {fees}, at {time}.", {
            side: t(pretradeDemo.side === "BUY" ? "Buy" : "Sell"),
            quantity: formatNumber(pretradeDemo.quantity),
            symbol: pretradeDemo.symbol,
            price: formatNumber(pretradeDemo.executionPrice, 2),
            fees: formatNumber(pretradeDemo.fees, 2),
            time: proposedAt,
          })}
        </p>
      </GlassPanel>

      {complete ? (
        <GlassPanel className="overflow-hidden">
          <div className="p-6 pb-4">
            <SectionHeading
              eyebrow={runtime === "tauri_local" ? t("Live deterministic vectorbt replay") : t("Generated offline deterministic replay")}
              title={t("Current → proposed trade")}
              description={t("If executed at the stated proposed price and quantity, the portfolio would change as follows. No future return or price is estimated.")}
              action={hasRegisteredExplanation ? (
                <EvidenceExplainButton
                  view={pretradeExplainability}
                  label="Explain this change"
                  context={{
                    label: t("Pre-trade evidence"),
                    title: complete.symbol,
                    detail: t("Current → proposed trade"),
                  }}
                />
              ) : undefined}
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

          <div className="border-b border-border/60 px-5 py-3 text-sm">
            <span className="text-muted">{t("Assumed execution price")}: </span>
            <span className="font-medium tabular-nums">{currency(complete.executionPrice)}</span>
            <span className="px-2 text-muted">·</span>
            <span className="text-muted">{t("Portfolio valuation price")}: </span>
            <span className="font-medium tabular-nums">{currency(complete.after.valuationPrice)}</span>
          </div>
          {complete.executionPrice !== complete.after.valuationPrice ? (
            <p className="border-b border-border/60 px-5 py-3 text-xs leading-5 text-muted">
              {t("After the trade, the portfolio is revalued at the current valuation price. A difference between the assumed execution price and valuation price creates an immediate mark-to-market difference; it is not a future return forecast and does not mean the assumed price can necessarily be executed.")}
            </p>
          ) : null}

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
            title={runtime === "tauri_local" ? t("Synthetic local-runtime boundary") : t("Synthetic offline-runtime boundary")}
            detail={runtime === "tauri_local"
              ? t("This result was generated now by the local deterministic engine from synthetic data. It is not a recommendation and does not predict price or return.")
              : t("This result is the registered generated offline demo, not a live Python calculation. It is not a recommendation and does not predict price or return.")}
          />
        </GlassPanel>
      ) : impact ? (
        <StateNotice
          state="insufficient"
          title={impact.status === "rejected" ? t("Proposed trade rejected") : t("Scenario evidence unavailable")}
          detail={impact.reason ?? t("The deterministic backend could not produce complete pre-trade evidence for this scenario.")}
        />
      ) : requestState.phase === "error" ? (
        <StateNotice
          state="insufficient"
          title={t("Pre-trade check failed")}
          detail={runtime === "browser_offline_demo" && requestState.error.code === "offline_demo_only"
            ? t("Browser mode cannot run local Python. Restore the registered offline scenario or open the Tauri desktop app for a live check.")
            : requestState.error.message}
        />
      ) : requestState.phase === "loading" ? (
        <StateNotice
          state="loading"
          title={t("Checking deterministic changes")}
          detail={t("The local engine is replaying the current and proposed states.")}
        />
      ) : (
        <StateNotice
          state="empty"
          title={requestState.stale ? t("Inputs changed") : t("Ready to check")}
          detail={requestState.stale
            ? t("The previous result was cleared because it no longer matches the current input. Run the check again to refresh it.")
            : runtime === "tauri_local"
              ? t("Run the check to calculate the current and proposed states with the local deterministic engine.")
              : t("Run the registered scenario to view the generated offline result. Live recalculation requires the Tauri desktop runtime.")}
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
