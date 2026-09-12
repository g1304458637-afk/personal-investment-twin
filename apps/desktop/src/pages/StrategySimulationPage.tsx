import { useMemo, useState } from "react";

import { EChart } from "@/components/charts/EChart";
import { InvestmentChartWorkspace } from "@/components/charts/InvestmentChartWorkspace";
import { useTheme } from "@/components/layout/ThemeProvider";
import { isTauriRuntime, runtimeRequest } from "@/data/runtimeService";
import { rawComparisonReportFor, strategyComparison } from "@/data/strategyComparisonDemo";
import { strategySimulation } from "@/data/strategySimulationDemo";
import { useLocale } from "@/locales/LocaleProvider";
import { formatCurrencyValue } from "@/lib/format";
import { cn } from "@/lib/utils";

import "./strategy-simulation.css";

const MS_PER_DAY = 86_400_000;

const triggerKey = {
  signal_order: "Signal order",
  stop_loss: "Stop loss",
  delisting_liquidation: "Delisting liquidation",
} as const;

function percentLabel(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function StatCard({ label, value, detail, tone }: {
  label: string; value: string; detail?: string | null;
  tone?: "positive" | "negative";
}) {
  return <div className="strategy-stat">
    <p className="strategy-stat__label">{label}</p>
    <p className={cn("strategy-stat__value", tone === "positive" && "is-positive", tone === "negative" && "is-negative")}>{value}</p>
    {detail ? <p className="strategy-stat__detail">{detail}</p> : null}
  </div>;
}

export function StrategySimulationPage() {
  const { t, locale } = useLocale();
  const { theme } = useTheme();
  const dark = theme === "dark";
  const simulation = strategySimulation;
  const currency = typeof simulation.strategy.params.currency === "string" ? simulation.strategy.params.currency : "CNY";
  const money = (value: number) => formatCurrencyValue(value, locale, currency);
  const [instrument, setInstrument] = useState<string>("all");
  const [chartInstrument, setChartInstrument] = useState<string | null>(null);
  const [teaching, setTeaching] = useState<Record<string, { status: string; texts: string[]; reason: string | null } | "loading">>({});
  const explain = async (episodeId: string) => {
    if (!isTauriRuntime()) {
      setTeaching((state) => ({ ...state, [episodeId]: { status: "unavailable", texts: [], reason: "需要桌面应用环境与本地模型设置（浏览器预览不调用模型）。" } }));
      return;
    }
    const report = rawComparisonReportFor(episodeId);
    if (!report) return;
    setTeaching((state) => ({ ...state, [episodeId]: "loading" }));
    try {
      const result = await runtimeRequest<{ status: string; reason: string | null; texts: string[] }>(
        "strategy_teaching.explain", { report, focus: null });
      setTeaching((state) => ({ ...state, [episodeId]: result }));
    } catch (value) {
      setTeaching((state) => ({ ...state, [episodeId]: { status: "unavailable", texts: [], reason: value instanceof Error ? value.message : String(value) } }));
    }
  };

  const instruments = useMemo(
    () => [...new Set(simulation.fills.map((fill) => fill.instrument))].sort(),
    [simulation.fills],
  );
  const visibleFills = useMemo(
    () => instrument === "all" ? simulation.fills : simulation.fills.filter((fill) => fill.instrument === instrument),
    [instrument, simulation.fills],
  );
  const barsByInstrument = simulation.barsByInstrument;
  const fillsByInstrument = useMemo(() => {
    const grouped: Record<string, { day: string; side: "BUY" | "SELL"; price: number }[]> = {};
    for (const fill of simulation.fills) {
      (grouped[fill.instrument] ??= []).push({ day: fill.day, side: fill.side, price: fill.price });
    }
    return grouped;
  }, [simulation.fills]);
  const chartInstruments = useMemo(
    () => Object.keys(barsByInstrument).filter((name) => (fillsByInstrument[name] ?? []).length > 0).sort(),
    [barsByInstrument, fillsByInstrument],
  );
  const effectiveChartInstrument = chartInstrument ?? chartInstruments[0] ?? null;
  const reasonByOrderId = useMemo(
    () => new Map(simulation.orders.map((order) => [order.orderId, order])),
    [simulation.orders],
  );
  const unfilledOrders = useMemo(
    () => simulation.orders.filter((order) => order.status !== "filled"),
    [simulation.orders],
  );
  const lensRules = simulation.strategy.ruleTable.filter((rule) => rule.source.startsWith("lens_rule"));
  const adaptations = simulation.strategy.ruleTable.filter((rule) => rule.source === "adaptation");

  const observationTimes = useMemo(
    () => simulation.equity.map((point) => Date.parse(point.date)),
    [simulation.equity],
  );
  const equityOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 10, right: 12, top: 30, bottom: 58, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(13, 18, 28, .96)" : "rgba(252, 253, 254, .97)",
      borderColor: dark ? "rgba(255,255,255,.12)" : "rgba(32,50,63,.14)",
      borderWidth: 1,
      textStyle: { color: dark ? "#eef5f6" : "#17212a", fontSize: 12 },
      axisPointer: { lineStyle: { color: "rgba(143,221,228,.28)", width: 1 } },
    },
    legend: {
      top: 0, textStyle: { color: dark ? "rgba(205,220,234,.8)" : "rgba(23,33,42,.8)", fontSize: 11 },
      data: [t("Equity curve"), t("Drawdown from peak")],
    },
    dataZoom: [{ type: "slider", height: 22, bottom: 12 }],
    xAxis: {
      type: "time", minInterval: MS_PER_DAY,
      axisLabel: { color: dark ? "rgba(205,220,234,.72)" : "rgba(23,33,42,.72)", fontSize: 11,
        formatter: (value: number) => new Intl.DateTimeFormat(locale, { year: "2-digit", month: "short" }).format(value) },
      splitLine: { show: false },
      axisLine: { lineStyle: { color: dark ? "rgba(160,184,210,.18)" : "rgba(32,50,63,.18)" } },
    },
    yAxis: [
      { type: "value", scale: true,
        axisLabel: { color: dark ? "rgba(205,220,234,.72)" : "rgba(23,33,42,.72)", fontSize: 11,
          formatter: (value: number) => formatCurrencyValue(value, locale, currency) },
        splitLine: { lineStyle: { color: dark ? "rgba(160,184,210,.09)" : "rgba(32,50,63,.08)" } } },
      { type: "value", position: "right", max: 0,
        axisLabel: { color: dark ? "rgba(205,220,234,.6)" : "rgba(23,33,42,.6)", fontSize: 11,
          formatter: (value: number) => `${(value * 100).toFixed(0)}%` },
        splitLine: { show: false } },
    ],
    series: [
      {
        name: t("Equity curve"), type: "line", showSymbol: false, yAxisIndex: 0,
        data: observationTimes.map((time, index) => [time, simulation.equity[index].equity]),
        lineStyle: { color: "#83d8ff", width: 1.8 }, itemStyle: { color: "#83d8ff" },
        markLine: {
          silent: true, symbol: "none", label: { show: false },
          lineStyle: { color: "rgba(250,202,112,.6)", type: "dashed", width: 1 },
          data: [{ yAxis: simulation.summary.initialCash }],
        },
      },
      {
        name: t("Drawdown from peak"), type: "line", showSymbol: false, yAxisIndex: 1,
        data: observationTimes.map((time, index) => [time, simulation.equity[index].drawdownFromPeak]),
        lineStyle: { color: "rgba(255,143,156,.8)", width: 1 },
        areaStyle: { color: "rgba(255,143,156,.14)" }, itemStyle: { color: "rgba(255,143,156,.8)" },
      },
    ],
  }), [dark, locale, observationTimes, simulation, t, currency]);

  const summary = simulation.summary;
  const returnTone = summary.totalReturn > 0 ? "positive" : summary.totalReturn < 0 ? "negative" : undefined;

  return <div className="strategy-simulation space-y-5 pb-8">
    <header className="iw-inset strategy-hero">
      <div>
        <p className="iw-kicker">{t("Strategy history simulation")}</p>
        <h1 className="strategy-hero__title">{simulation.strategy.title}</h1>
        <p className="strategy-hero__desc">{simulation.strategy.description}</p>
        <p className="strategy-hero__meta">{simulation.strategy.strategyId}@{simulation.strategy.version} · {t("Data fingerprint")} {simulation.dataFingerprint.slice(0, 12)}…</p>
      </div>
      <div className="strategy-hero__boundary">
        <p>{t("This path is replayed by deterministic code on synthetic prices. It is not advice, not a prediction, and not real market performance.")}</p>
        <p>{t("The strategy account has its own cash, holdings and fees. It never reads or changes your records.")}</p>
      </div>
    </header>
    <section className="iw-inset strategy-purpose" aria-label={t("What this page answers")}>
      <p className="strategy-purpose__question">{t("What this page answers")}</p>
      <h2>{t("If one fixed, fully public set of rules ran independently in the same market, where would it have gone?")}</h2>
      <p className="strategy-purpose__answer">{t("This path is the reference group for your own history: same synthetic market, fixed rules, every fill explained. The performance numbers above are on synthetic prices — read the rule behavior (when it enters, exits, or stands aside), not the profit.")}</p>
      <ol className="strategy-purpose__steps">
        <li>{t("Read the rule table: A-rules come from your existing Decision Lens checks; B-rules are declared adaptations that make them executable.")}</li>
        <li>{t("Scroll to the showcase comparison: your recorded episodes side by side with the same rules replayed on each instrument's own history.")}</li>
        <li>{t("Open any showcase episode and switch on the rule overlay: your decisions and the rule's fills on the same chart.")}</li>
      </ol>
    </section>

    <section className="strategy-stats" aria-label={t("Final equity")}>
      <StatCard label={t("Final equity")} value={money(summary.finalEquity)}
        detail={`${t("Total return")} ${percentLabel(summary.totalReturn)}`} tone={returnTone} />
      <StatCard label={t("Max drawdown")} value={percentLabel(summary.maxDrawdown)}
        detail={`${summary.maxDrawdownPeakDate} → ${summary.maxDrawdownTroughDate}`} tone="negative" />
      <StatCard label={t("Total fees")} value={money(summary.totalFees)}
        detail={`${t("Round trips")} ${summary.roundTripCount}`} />
      <StatCard label={t("Win rate")} value={summary.winRate === null ? "—" : percentLabel(summary.winRate)}
        detail={`${t("Round trips")} ${summary.roundTripCount}`} />
      <StatCard label={t("Orders")} value={String(summary.orderCount)}
        detail={`${t("Fills")} ${summary.fillCount}`} />
      <StatCard label={t("Rejected / cancelled")} value={String(summary.rejectedOrderCount + summary.cancelledOrderCount)}
        detail={`${summary.rejectedOrderCount} / ${summary.cancelledOrderCount}`} />
      <StatCard label={t("Avg exposure")} value={percentLabel(summary.averageInvestedFraction)}
        detail={`${summary.tradingDays} · CNY`} />
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Equity curve")}</p>
        <span className="iw-subtle">{t("Initial cash")} {money(summary.initialCash)}</span>
      </div>
      <EChart option={equityOption} label={t("Equity curve")} className="strategy-equity-chart" />
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Per-instrument operations")}</p>
        <label className="strategy-filter">
          <span className="iw-subtle">{chartInstrument ?? t("All instruments")}</span>
          <select aria-label={t("Per-instrument operations")} value={effectiveChartInstrument ?? ""} onChange={(event) => setChartInstrument(event.target.value)}>
            {chartInstruments.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      {effectiveChartInstrument && barsByInstrument[effectiveChartInstrument]
        ? <InvestmentChartWorkspace
            market={{
              instrumentId: effectiveChartInstrument, replayInstrumentId: effectiveChartInstrument,
              displayName: effectiveChartInstrument, currency: "CNY",
              priceBasis: "synthetic_unadjusted", sourceUrl: "", sourceSha256: "",
              bars: barsByInstrument[effectiveChartInstrument].map((bar) => ({
                date: bar.date, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
                volume: null, amount: null,
              })),
            }}
            ruleFills={(fillsByInstrument[effectiveChartInstrument] ?? []).map((fill) => ({ ...fill, trigger: "signal_order" }))}
          />
        : null}
      <p className="strategy-compare__note">{t("Each marker is one strategy fill on this instrument; reasons live in the trades list below.")}</p>
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Rule table")}</p>
        <span className="iw-subtle">{simulation.strategy.ruleTable.length} · {t("Parameters")} {Object.keys(simulation.strategy.params).length}</span>
      </div>
      <div className="strategy-rules">
        {[{ label: t("Lifted from the recorded Decision Lens rules"), rules: lensRules, tone: "lens" as const },
          { label: t("Adaptation added for full execution"), rules: adaptations, tone: "adapt" as const }].map((group) => (
          <div className="strategy-rule-group" key={group.tone}>
            <p className={cn("strategy-rule-group__label", `is-${group.tone}`)}>{group.label}</p>
            <ul>
              {group.rules.map((rule) => (
                <li key={rule.ruleId}>
                  <code>{rule.ruleId}</code>
                  <span>{rule.statement}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <details className="strategy-params">
        <summary>{t("Parameters")}</summary>
        <dl>
          {Object.entries(simulation.strategy.params).map(([key, value]) => (
            <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
          ))}
        </dl>
      </details>
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Showcase episode comparison")}</p>
        <span className="iw-subtle">{strategyComparison.reports.length}</span>
      </div>
      <p className="strategy-comparison-note">{strategyComparison.portfolio.note}</p>
      <div className="strategy-compare-parallel">
        <div>
          <span>{t("Recorded side")}</span>
          <strong>{money(strategyComparison.portfolio.user.realizedPnlTotal)}</strong>
          <small>{t("Realized PnL total")} · {strategyComparison.portfolio.user.realizedEpisodeCount}</small>
        </div>
        <div>
          <span>{t("Rule side")}</span>
          <strong>{money(strategyComparison.portfolio.strategy.finalEquity)}</strong>
          <small>{t("Total return")} {percentLabel(strategyComparison.portfolio.strategy.totalReturn)}</small>
        </div>
      </div>
      <div className="strategy-comparisons">
        {strategyComparison.reports.map((item) => (
          <details key={item.episodeId} className="strategy-compare">
            <summary>
              <strong>{item.instrument}</strong>
              <button type="button" className="strategy-why" onClick={(event) => { event.preventDefault(); void explain(item.episodeId); }}>{t("Why?")}</button>
              <span>{item.windowStart ?? "—"} → {item.windowEnd ?? t("Window open-ended")}</span>
              <span>{t("Recorded result")} {item.recordedEpisodeResult.pnl === null ? "—" : money(item.recordedEpisodeResult.pnl)}</span>
              <span>{t("Rule trades in window")} {item.ruleFills.length}</span>
            </summary>
            <div className="strategy-compare__body">
              {(() => {
                const state = teaching[item.episodeId];
                if (!state) return null;
                if (state === "loading") return <p className="strategy-compare__note">{t("Preparing explanation…")}</p>;
                if (state.status === "available") return <div className="strategy-teaching">{state.texts.map((line, index) => <p key={index}>{line}</p>)}<p className="strategy-compare__note">{strategyComparison.limitations[1] ?? ""}</p></div>;
                return <p className="strategy-compare__note">{t("Explanation unavailable")}: {state.reason}</p>;
              })()}
              <div className="strategy-compare__flows">
                <div><span>{t("Recorded side")}</span><strong>{money(item.windowUserNetCashFlow)}</strong></div>
                <div><span>{t("Rule side")}</span><strong>{money(item.windowRuleNetCashFlow)}</strong></div>
              </div>
              <p className="strategy-compare__note">{item.windowDifferenceNote}</p>
              <ul className="strategy-compare__fills">
                {item.ruleFills.map((ruleFill) => (
                  <li key={ruleFill.fillId}>
                    <span>{ruleFill.day}</span>
                    <strong className={ruleFill.side === "BUY" ? "is-buy" : "is-sell"}>{ruleFill.side === "BUY" ? t("Buy") : t("Sell")}</strong>
                    <span>{ruleFill.quantity.toLocaleString(locale)} × {money(ruleFill.price)}</span>
                    <em>{t(triggerKey[ruleFill.trigger as keyof typeof triggerKey] ?? "Signal order")}</em>
                  </li>
                ))}
              </ul>
              <details className="strategy-compare__limits">
                <summary>{t("Method and provenance")}</summary>
                <ul>{item.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
                <p>{t("Data fingerprint")}: {item.barsCovered} · {item.barCount}</p>
              </details>
            </div>
          </details>
        ))}
      </div>
      <ul className="strategy-comparison-limits">{strategyComparison.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Trades")}</p>
        <label className="strategy-filter">
          <span className="iw-subtle">{instrument === "all" ? t("All instruments") : instrument}</span>
          <select aria-label={t("All instruments")} value={instrument} onChange={(event) => setInstrument(event.target.value)}>
            <option value="all">{t("All instruments")}</option>
            {instruments.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      <div className="strategy-trades">
        {visibleFills.map((fill) => {
          const order = fill.orderId ? reasonByOrderId.get(fill.orderId) : undefined;
          return <div key={fill.fillId} className="strategy-trade">
            <span className="strategy-trade__day">{fill.day}</span>
            <strong className={fill.side === "BUY" ? "is-buy" : "is-sell"}>{fill.side === "BUY" ? t("Buy") : t("Sell")}</strong>
            <span className="strategy-trade__instrument">{fill.instrument}</span>
            <span className="strategy-trade__qty">{fill.quantity.toLocaleString(locale)} × {money(fill.price)}</span>
            <span className="strategy-trade__fee">{t("Fee")} {money(fill.fee)}</span>
            <em>{t(triggerKey[fill.trigger])}{fill.note ? ` · ${fill.note.replaceAll("_", " ")}` : ""}</em>
            {order ? <p className="strategy-trade__reason">{order.reasonText}</p> : null}
          </div>;
        })}
      </div>
    </section>

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Unfilled orders")}</p>
        <span className="iw-subtle">{unfilledOrders.length}</span>
      </div>
      {unfilledOrders.length === 0 ? <p className="iw-subtle">—</p> :
        <div className="strategy-trades">
          {unfilledOrders.map((order) => (
            <div key={order.orderId} className="strategy-trade">
              <span className="strategy-trade__day">{order.signalDate}</span>
              <strong className={order.side === "BUY" ? "is-buy" : "is-sell"}>{order.side}</strong>
              <span className="strategy-trade__instrument">{order.instrument}</span>
              <em className="strategy-trade__status">{order.status} · {order.resolutionReason}</em>
              <p className="strategy-trade__reason">{order.reasonText}</p>
            </div>
          ))}
        </div>}
    </section>

    <footer className="iw-inset strategy-provenance">
      <p className="iw-kicker">{t("Method and provenance")}</p>
      <p>{simulation.strategy.strategyId}@{simulation.strategy.version} · schema strategy_simulation.v1</p>
      <p>{t("Data fingerprint")}: {simulation.dataFingerprint}</p>
      <p>{t("Regenerate via scripts/run_strategy_simulation.py")}</p>
    </footer>
  </div>;
}
