import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/charts/EChart";
import { InvestmentChartWorkspace } from "@/components/charts/InvestmentChartWorkspace";
import { useTheme } from "@/components/layout/ThemeProvider";
import { isTauriRuntime, runtimeRequest, type SensitivityReportView } from "@/data/runtimeService";
import { useDataMode } from "@/data/DataModeProvider";
import { adaptStrategySimulation, type StrategySimulationView } from "@/data/strategySimulation";
import { StrategyWorkshop, conditionStatement, type ConditionDraft, type WorkshopDraft } from "@/components/strategy/StrategyWorkshop";
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

const STRATEGY_FILES: Record<string, { title: string; load: () => Promise<{ default: unknown }> }> = {
  toujing_t1_breakout_trend: { title: "T1 · 突破趋势", load: () => import("@/generated/strategy-simulation-demo.json") },
  toujing_dual_ma: { title: "双均线交叉 5/20", load: () => import("@/generated/strategy-simulation-dual-ma.json") },
  toujing_rsi_mean_reversion: { title: "RSI 均值回归 14", load: () => import("@/generated/strategy-simulation-rsi-mean-reversion.json") },
  toujing_turtle_s2_long: { title: "海龟 S2（55日/ATR 加仓）", load: () => import("@/generated/strategy-simulation-turtle.json") },
};

export function StrategySimulationPage() {
  const { t, locale } = useLocale();
  const data = useDataMode();
  const { theme } = useTheme();
  const dark = theme === "dark";
  const [search, setSearch] = useSearchParams();
  const [userStrategies, setUserStrategies] = useState<{ id: string; name: string; savedAt: string; spec: Record<string, unknown> }[]>(() => {
    try { return JSON.parse(localStorage.getItem("toujing.userStrategies") ?? "[]"); } catch { return []; }
  });
  const [workshopOpen, setWorkshopOpen] = useState(false);
  const [userArtifacts, setUserArtifacts] = useState<Record<string, StrategySimulationView>>({});
  const [userRunState, setUserRunState] = useState<Record<string, "loading" | "ready">>({});
  const [userRunError, setUserRunError] = useState<Record<string, string>>({});
  const defaultStrategyId = (() => {
    const fromUrl = search.get("strategy");
    if (fromUrl && fromUrl in STRATEGY_FILES) return fromUrl;
    const stored = localStorage.getItem("toujing.strategy");
    if (stored && stored in STRATEGY_FILES) return stored;
    return "toujing_t1_breakout_trend";
  })();
  const [strategyId, setStrategyIdState] = useState<string>(defaultStrategyId);
  const setStrategyId = (id: string) => {
    setStrategyIdState(id);
    localStorage.setItem("toujing.strategy", id);
    const next = new URLSearchParams(search);
    next.set("strategy", id);
    setSearch(next, { replace: true });
  };
  const [simulation, setSimulation] = useState<StrategySimulationView>(strategySimulation);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  useEffect(() => {
    if (strategyId.startsWith("user_")) {
      const artifact = userArtifacts[strategyId];
      if (artifact) setSimulation(artifact);
      return;
    }
    if (strategyId === "toujing_t1_breakout_trend") { setSimulation(strategySimulation); return; }
    const entry = STRATEGY_FILES[strategyId];
    if (!entry) return;
    let cancelled = false;
    setLoadingStrategy(true);
    entry.load().then((module) => {
      if (!cancelled) setSimulation(adaptStrategySimulation(module.default));
    }).finally(() => { if (!cancelled) setLoadingStrategy(false); });
    return () => { cancelled = true; };
  }, [strategyId, userArtifacts]);
  const isT1 = simulation.strategy.strategyId === "toujing_t1_breakout_trend";
  const isUserStrategy = strategyId.startsWith("user_");
  // A user strategy that has not been run yet must NOT show another
  // strategy's stale numbers: gate every data section on readiness.
  const simulationReady = !isUserStrategy || !!userArtifacts[strategyId];
  const selectedUserStrategy = isUserStrategy
    ? userStrategies.find((item) => item.id === strategyId) ?? null : null;
  // Hero identity must follow the selection even before the first run.
  const hero = isUserStrategy && selectedUserStrategy ? {
    title: `自建策略：${selectedUserStrategy.name}`,
    description: "你在因子库内自建的规则组合；保存后可在桌面应用中于真实行情或合成历史上运行。",
    meta: `${selectedUserStrategy.id} · 保存于 ${selectedUserStrategy.savedAt}`,
  } : {
    title: simulation.strategy.title,
    description: simulation.strategy.description,
    meta: `${simulation.strategy.strategyId}@${simulation.strategy.version} · ${t("Data fingerprint")} ${simulation.dataFingerprint.slice(0, 12)}…`,
  };
  const saveWorkshopStrategy = (draft: WorkshopDraft, spec: Record<string, unknown>) => {
    const id = `user_${JSON.stringify(spec).length}_${Math.abs(draft.name.length)}_${Date.now().toString(36)}`;
    const entry = { id, name: draft.name.trim(), savedAt: new Date().toISOString().slice(0, 10), spec };
    const next = [...userStrategies, entry];
    setUserStrategies(next);
    localStorage.setItem("toujing.userStrategies", JSON.stringify(next));
    setWorkshopOpen(false);
    setStrategyId(id);
  };
  const [userRunUniverse, setUserRunUniverse] = useState<"synthetic" | "own_account">("own_account");
  const runUserStrategy = (entry: { id: string; spec: Record<string, unknown> }) => {
    setUserRunState((state) => ({ ...state, [entry.id]: "loading" }));
    setUserRunError((state) => ({ ...state, [entry.id]: "" }));
    const base: Record<string, unknown> = { strategy: entry.spec, universe: userRunUniverse };
    if (userRunUniverse === "own_account" && data.activeAccount) {
      base.subject_id = data.activeAccount.subject_id;
      base.account_id = data.activeAccount.account_id;
    }
    runtimeRequest<{ status: string; reason: string | null; artifact: unknown }>(
      "strategy_simulation.run_custom", base)
      .then((result) => {
        if (result.status !== "available" || !result.artifact) {
          setUserRunError((state) => ({ ...state, [entry.id]: result.reason ?? "运行失败" }));
          return;
        }
        setUserArtifacts((state) => ({ ...state, [entry.id]: adaptStrategySimulation(result.artifact) }));
        setUserRunState((state) => ({ ...state, [entry.id]: "ready" }));
      })
      .catch((value) => {
        setUserRunError((state) => ({ ...state, [entry.id]: value instanceof Error ? value.message : String(value) }));
        setUserRunState((state) => ({ ...state, [entry.id]: "loading" }));
      });
  };
  const deleteUserStrategy = (id: string) => {
    const next = userStrategies.filter((item) => item.id !== id);
    setUserStrategies(next);
    localStorage.setItem("toujing.userStrategies", JSON.stringify(next));
    if (strategyId === id) setStrategyId("toujing_t1_breakout_trend");
  };
  const currency = typeof simulation.strategy.params.currency === "string" ? simulation.strategy.params.currency : "CNY";
  const money = (value: number) => formatCurrencyValue(value, locale, currency);
  const [instrument, setInstrument] = useState<string>("all");
  const [chartInstrument, setChartInstrument] = useState<string | null>(null);
  const SENSITIVITY_PARAMS = [
    { id: "stop_loss_pct", label: "止损比例" },
    { id: "position_fraction", label: "每仓占比" },
    { id: "max_positions", label: "最多持仓数" },
    { id: "commission_rate", label: "佣金率" },
    { id: "slippage_rate", label: "滑点" },
  ] as const;
  const [sensitivityParam, setSensitivityParam] = useState<string>("stop_loss_pct");
  const [sensitivityValues, setSensitivityValues] = useState("0.05, 0.1, 0.2, 0.3");
  const [sensitivityResult, setSensitivityResult] = useState<SensitivityReportView | null>(null);
  const [sensitivityBusy, setSensitivityBusy] = useState(false);
  const [sensitivityError, setSensitivityError] = useState<string | null>(null);
  const runSensitivity = () => {
    if (!isTauriRuntime()) {
      setSensitivityError("需要桌面应用环境（浏览器预览不运行变体）。");
      return;
    }
    const values = sensitivityValues.split(",").map((text) => Number(text.trim())).filter((value) => Number.isFinite(value));
    if (values.length < 2) { setSensitivityError("请至少输入两个取值，用逗号分隔。"); return; }
    setSensitivityBusy(true);
    setSensitivityError(null);
    const request = strategyId.startsWith("user_")
      ? { strategy: selectedUserStrategy?.spec, parameter: sensitivityParam, values }
      : { strategy_id: strategyId, parameter: sensitivityParam, values };
    runtimeRequest<{ status: string; reason: string | null; report: SensitivityReportView | null }>(
      "strategy_sensitivity.run", request)
      .then((result) => {
        if (result.status === "available" && result.report) setSensitivityResult(result.report);
        else setSensitivityError(result.reason ?? "运行失败");
      })
      .catch((value) => setSensitivityError(value instanceof Error ? value.message : String(value)))
      .finally(() => setSensitivityBusy(false));
  };
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
      data: [t("Equity curve"), ...(simulation.summary.benchmarkBuyHold.length ? [t("Buy and hold")] : []), t("Drawdown from peak")],
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
      ...(simulation.summary.benchmarkBuyHold.length ? [{
        name: t("Buy and hold"), type: "line", showSymbol: false, yAxisIndex: 0,
        data: simulation.summary.benchmarkBuyHold.map((point: { date: string; equity: number }) =>
          [Date.parse(`${point.date}T00:00:00Z`), point.equity]),
        lineStyle: { color: "rgba(250,202,112,.7)", width: 1.5, type: "dashed" as const },
        itemStyle: { color: "rgba(250,202,112,.7)" },
      }] : []),
      { name: t("Drawdown from peak"), type: "line", showSymbol: false, yAxisIndex: 1,
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
        <div className="strategy-selector" role="tablist" aria-label={t("Choose a strategy")}>
          {Object.entries(STRATEGY_FILES).map(([id, meta]) => (
            <button key={id} type="button" role="tab" aria-selected={strategyId === id}
              className={strategyId === id ? "is-active" : ""}
              onClick={() => setStrategyId(id)}>{meta.title}</button>
          ))}
          {userStrategies.map((item) => (
            <button key={item.id} type="button" role="tab" aria-selected={strategyId === item.id}
              className={strategyId === item.id ? "is-active" : ""}
              onClick={() => setStrategyId(item.id)}>{t("Custom")} · {item.name}</button>
          ))}
          <button type="button" role="tab" aria-selected={workshopOpen}
            className={workshopOpen ? "is-active" : ""}
            onClick={() => { setWorkshopOpen(true); }}>＋ {t("Build your own")}</button>
          {loadingStrategy ? <span className="iw-subtle">{t("Loading…")}</span> : null}
        </div>
        <div className="strategy-anchor-nav">
          {[["#rules", t("Rules")], ["#results", t("Results")], ["#charts", t("Charts")],
            ["#trades", t("Trades")], ["#comparison", t("Comparison")]].map(([id, label]) => (
            <a key={id} href={`javascript:void(0)`} className="strategy-anchor-link"
              onClick={(e) => { e.preventDefault(); document.querySelector(id)?.scrollIntoView({ behavior: "smooth" }); }}>
              {label}
            </a>
          ))}
        </div>
        <h1 className="strategy-hero__title">{hero.title}</h1>
        <p className="strategy-hero__desc">{hero.description}</p>
        <p className="strategy-hero__meta">{hero.meta}</p>
      </div>
      <div className="strategy-hero__boundary">
        <p>{t("This path is replayed by deterministic code on synthetic prices. It is not advice, not a prediction, and not real market performance.")}</p>
        <p>{t("The strategy account has its own cash, holdings and fees. It never reads or changes your records.")}</p>
      </div>
    </header>
    {workshopOpen ? <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Strategy workshop")}</p>
        <button type="button" onClick={() => setWorkshopOpen(false)}>{t("Close")}</button>
      </div>
      <StrategyWorkshop onCancel={() => setWorkshopOpen(false)} onSave={saveWorkshopStrategy} />
    </section> : null}
    {isUserStrategy && selectedUserStrategy ? <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Custom strategy")}</p>
        <button type="button" onClick={() => deleteUserStrategy(selectedUserStrategy.id)}>{t("Delete")}</button>
      </div>
      <p className="strategy-comparison-note">{t("Custom strategies are data specs, run by the deterministic interpreter on the bundled synthetic universe. They are never advice and never touch real accounts.")}</p>
      <ul className="strategy-rule-group">
        {((selectedUserStrategy.spec.entry as { all_of: Record<string, unknown>[] }).all_of).map((condition, index) => (
          <li key={index}><code>{t("Entry")} {index + 1}</code><span>{conditionStatement(condition as unknown as ConditionDraft)}</span></li>
        ))}
        {((selectedUserStrategy.spec.exit as { any_of: Record<string, unknown>[] }).any_of).map((condition, index) => (
          <li key={`exit-${index}`}><code>{t("Exit")} {index + 1}</code><span>{conditionStatement(condition as unknown as ConditionDraft)}</span></li>
        ))}
      </ul>
      {isTauriRuntime() ? (
        userRunState[selectedUserStrategy.id] === "ready" && userArtifacts[selectedUserStrategy.id] ? (
          <>
            {userArtifacts[selectedUserStrategy.id].limitations ? (
              <ul className="strategy-comparison-limits">
                {userArtifacts[selectedUserStrategy.id].limitations!.map((limitation, index) => <li key={index}>{limitation}</li>)}
              </ul>
            ) : null}
          </>
        ) : userRunState[selectedUserStrategy.id] === "loading" ? (
          <p className="strategy-compare__note">{t("Running on history…")}</p>
        ) : (
          <div>
            <label className="workshop-inline-num">
              {t("Run on")}
              <select aria-label={t("Run on")} value={userRunUniverse} onChange={(event) => setUserRunUniverse(event.target.value as "synthetic" | "own_account")}>
                <option value="own_account">{t("My own traded instruments (real market, hfq)")}</option>
                <option value="synthetic">{t("Synthetic demo universe")}</option>
              </select>
            </label>
            <button type="button" className="workshop-save" onClick={() => runUserStrategy(selectedUserStrategy)}>{t("Run on history")}</button>
            {userRunError[selectedUserStrategy.id] ? <p className="strategy-compare__note">{t("Run failed")}: {userRunError[selectedUserStrategy.id]}</p> : null}
          </div>
        )
      ) : <div className="strategy-compare__note">
        <p>{t("Running custom strategies needs the desktop app (browser preview cannot execute them).")}</p>
        <p>{t("Open the desktop app → Strategy Simulation → select this strategy → Run on history.")}</p>
      </div>}
    </section> : null}
{simulationReady ? <>
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

      <section className="iw-inset strategy-panel">

        <div className="strategy-panel__head">

          <p className="iw-kicker">{t("Read the rules first")}</p>

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





      <section id="results" className="strategy-stats" aria-label={t("Final equity")}>

        <StatCard label={t("Final equity")} value={money(summary.finalEquity)}

          detail={`${t("Total return")} ${percentLabel(summary.totalReturn)}`} tone={returnTone} />
        <StatCard label={t("Annualized return")} value={summary.annualizedReturn === null ? "—" : percentLabel(summary.annualizedReturn)}
          detail={`${t("Trading days")} ${summary.tradingDays}`} tone={summary.annualizedReturn !== null && summary.annualizedReturn > 0 ? "positive" : "negative"} />
        <StatCard label={t("Sharpe ratio")} value={summary.sharpeRatio === null ? "—" : summary.sharpeRatio.toFixed(2)}
          detail={summary.sharpeRatio !== null && summary.sharpeRatio > 1 ? t("Good risk-adjusted return") : t("Low risk-adjusted return")} />

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



      {isT1 ? <section className="iw-inset strategy-panel">

        <div className="strategy-panel__head">

          <p className="iw-kicker">{t("Showcase episode comparison")}</p>

          <span className="iw-subtle">{strategyComparison.reports.length}</span>

        </div>

        <p className="strategy-comparison-note">{strategyComparison.portfolio?.note}</p>

        <div className="strategy-compare-parallel">

          <div>

            <span>{t("Recorded side")}</span>

            <strong>{money(strategyComparison.portfolio?.user.realizedPnlTotal ?? 0)}</strong>

            <small>{t("Realized PnL total")} · {strategyComparison.portfolio?.user.realizedEpisodeCount ?? 0}</small>

          </div>

          <div>

            <span>{t("Rule side")}</span>

            <strong>{money(strategyComparison.portfolio?.strategy.finalEquity ?? 0)}</strong>

            <small>{t("Total return")} {percentLabel(strategyComparison.portfolio?.strategy.totalReturn ?? 0)}</small>

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

      </section> : null}



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



      <section className="iw-inset strategy-panel">

        <div className="strategy-panel__head">

          <p className="iw-kicker">{t("Parameter sensitivity")}</p>

          <span className="iw-subtle">{t("Facts only: the rows keep your order, nothing is ranked")}</span>

        </div>

        <p className="strategy-comparison-note">{t("See how fragile a conclusion is: change one parameter, rerun the same history, compare. High sensitivity means the historical result leans on that assumption.")}</p>

        <div className="strategy-sensitivity-controls">

          <select aria-label={t("Parameter")} value={sensitivityParam} onChange={(event) => setSensitivityParam(event.target.value)}>

            {SENSITIVITY_PARAMS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}

          </select>

          <input aria-label={t("Values")} value={sensitivityValues}

            onChange={(event) => setSensitivityValues(event.target.value)}

            placeholder="0.05, 0.1, 0.2" />

          <button type="button" className="workshop-save" disabled={sensitivityBusy}

            onClick={() => { setSensitivityResult(null); runSensitivity(); }}>

            {sensitivityBusy ? t("Running on history…") : t("Run variants")}

          </button>

        </div>

        {sensitivityError ? <p className="strategy-comparison-note">{sensitivityError}</p> : null}

        {sensitivityResult ? <div className="strategy-sensitivity">

          {sensitivityResult.allVariantsIdentical ? <p className="strategy-comparison-note">{sensitivityResult.limitations[0]}</p> : null}

          <table className="sensitivity-table">

            <thead><tr>

              <th>{t("Parameter")}</th><th>{t("Final equity")}</th><th>{t("Total return")}</th>

              <th>{t("Max drawdown")}</th><th>{t("Fills")}</th><th>{t("Win rate")}</th>

            </tr></thead>

            <tbody>

              {sensitivityResult.rows.map((row) => (

                <tr key={row.value}>

                  <td className="sensitivity-value">{row.value}</td>

                  <td>{money(row.finalEquity)}</td>

                  <td className={row.totalReturn > 0 ? "is-positive" : row.totalReturn < 0 ? "is-negative" : ""}>{percentLabel(row.totalReturn)}</td>

                  <td>{percentLabel(row.maxDrawdown)}</td>

                  <td>{row.fillCount}</td>

                  <td>{row.winRate === null ? "—" : percentLabel(row.winRate)}</td>

                </tr>

              ))}

            </tbody>

          </table>

          <ul className="strategy-comparison-limits">{sensitivityResult.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>

        </div> : null}

      </section>



      <footer className="iw-inset strategy-provenance">

        <p className="iw-kicker">{t("Method and provenance")}</p>

        <p>{simulation.strategy.strategyId}@{simulation.strategy.version} · schema strategy_simulation.v1</p>

        <p>{t("Data fingerprint")}: {simulation.dataFingerprint}</p>

        <p>{t("Regenerate via scripts/run_strategy_simulation.py")}</p>

      </footer>
</> : null}

  </div>;
}
