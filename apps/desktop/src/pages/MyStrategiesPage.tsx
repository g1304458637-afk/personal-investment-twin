import { useMemo, useState } from "react";

import { StrategyWorkshop, type WorkshopDraft } from "@/components/strategy/StrategyWorkshop";
import { strategyLibrary } from "@/data/strategyLibrary";
import { isTauriRuntime, runtimeRequest } from "@/data/runtimeService";
import { adaptStrategySimulation, type StrategySimulationView } from "@/data/strategySimulation";
import { useDataMode } from "@/data/DataModeProvider";
import { useLocale } from "@/locales/LocaleProvider";
import { EChart } from "@/components/charts/EChart";
import { useTheme } from "@/components/layout/ThemeProvider";
import { formatCurrencyValue } from "@/lib/format";
import { cn } from "@/lib/utils";

import "./my-strategies.css";
import "./strategy-simulation.css";

const TEMPLATE_PREFILL: Record<string, Partial<WorkshopDraft>> = {
  toujing_t1_breakout_trend: {
    entry: [{ factor: "breakout_high", op: "true", threshold: 0, window: 20 },
            { factor: "sma_gap", op: "gt", threshold: 0, window: 20 }],
    exitFactor: { factor: "breakdown_low", op: "true", threshold: 0, window: 10 },
    stopPct: 8,
  },
  toujing_dual_ma: {
    entry: [{ factor: "ma_cross_up", op: "true", threshold: 0, window: 0 }],
    exitFactor: { factor: "ma_cross_down", op: "true", threshold: 0, window: 0 },
    stopPct: null,
  },
  toujing_rsi_mean_reversion: {
    entry: [{ factor: "rsi", op: "lt", threshold: 30, window: 14 }],
    exitFactor: { factor: "rsi", op: "gt", threshold: 70, window: 14 },
    stopPct: null,
  },
  toujing_turtle_s2_long: {
    entry: [{ factor: "breakout_high", op: "true", threshold: 0, window: 55 }],
    exitFactor: { factor: "breakdown_low", op: "true", threshold: 0, window: 20 },
    stopPct: null,
    addsUnits: 3,
    atrMult: 2,
  },
};

function loadSaved(): { id: string; name: string; savedAt: string; spec: Record<string, unknown> }[] {
  try { return JSON.parse(localStorage.getItem("toujing.userStrategies") ?? "[]"); } catch { return []; }
}

export function MyStrategiesPage() {
  const { t, locale } = useLocale();
  const { theme } = useTheme();
  const dark = theme === "dark";
  const data = useDataMode();
  const [saved, setSaved] = useState(loadSaved);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workshopDraft, setWorkshopDraft] = useState<WorkshopDraft | null>(null);
  const [runStateMap, setRunState] = useState<Record<string, "loading" | "ready">>({});
  const [runErrors, setRunErrors] = useState<Record<string, string>>({});
  const [artifacts, setArtifacts] = useState<Record<string, StrategySimulationView>>({});

  const currency = "CNY";
  const money = (value: number) => formatCurrencyValue(value, locale, currency);
  const selected = saved.find((item) => item.id === selectedId) ?? null;
  const artifact = selectedId ? artifacts[selectedId] ?? null : null;
  const runState: "loading" | "ready" | null = selectedId ? runStateMap[selectedId] ?? null : null;
  const runError = selectedId ? runErrors[selectedId] ?? null : null;

  const persist = (next: typeof saved) => {
    setSaved(next);
    localStorage.setItem("toujing.userStrategies", JSON.stringify(next));
  };

  const onWorkshopSave = (draft: WorkshopDraft, spec: Record<string, unknown>) => {
    const id = `user_${JSON.stringify(spec).length}_${Math.abs(draft.name.length)}_${Date.now().toString(36)}`;
    persist([...saved, { id, name: draft.name.trim(), savedAt: new Date().toISOString().slice(0, 10), spec }]);
    setWorkshopDraft(null);
    setSelectedId(id);
  };

  const remove = (id: string) => {
    persist(saved.filter((item) => item.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const run = (entry: { id: string; spec: Record<string, unknown> }) => {
    setRunState((state) => ({ ...state, [entry.id]: "loading" }));
    setRunErrors((state) => ({ ...state, [entry.id]: "" }));
    const base: Record<string, unknown> = { strategy: entry.spec, universe: "own_account" };
    if (data.activeAccount) {
      base.subject_id = data.activeAccount.subject_id;
      base.account_id = data.activeAccount.account_id;
    }
    runtimeRequest<{ status: string; reason: string | null; artifact: unknown }>(
      "strategy_simulation.run_custom", base)
      .then((result) => {
        if (result.status === "available" && result.artifact) {
          setArtifacts((state) => ({ ...state, [entry.id]: adaptStrategySimulation(result.artifact) }));
          setRunState((state) => ({ ...state, [entry.id]: "ready" }));
        } else {
          setRunErrors((state) => ({ ...state, [entry.id]: result.reason ?? "运行失败" }));
          setRunState((state) => ({ ...state, [entry.id]: "loading" }));
        }
      })
      .catch((value) => {
        setRunErrors((state) => ({ ...state, [entry.id]: value instanceof Error ? value.message : String(value) }));
        setRunState((state) => ({ ...state, [entry.id]: "loading" }));
      });
  };

  const equityOption = useMemo(() => {
    if (!artifact) return null;
    const points = artifact.equity;
    return {
      animationDuration: 400,
      grid: { left: 10, right: 12, top: 20, bottom: 30, containLabel: true },
      xAxis: { type: "time",
        axisLabel: { color: dark ? "rgba(205,220,234,.72)" : "rgba(23,33,42,.72)", fontSize: 11 } },
      yAxis: { type: "value", scale: true,
        axisLabel: { color: dark ? "rgba(205,220,234,.72)" : "rgba(23,33,42,.72)", fontSize: 11 } },
      series: [{ type: "line", showSymbol: false,
        data: points.map((point) => [Date.parse(`${point.date}T00:00:00Z`), point.equity]),
        lineStyle: { color: "#83d8ff", width: 1.8 } }],
    };
  }, [artifact, dark, locale, currency]);

  return <div className="my-strategies space-y-5 pb-8">
    <header className="iw-inset my-strategies-hero">
      <div>
        <p className="iw-kicker">{t("My strategies")}</p>
        <h1 className="strategy-hero__title">{t("Your rules, runnable on history")}</h1>
        <p className="strategy-hero__desc">{t("Compose rules from the factor library, save them here, and replay them on real or synthetic history. Specs are data — deterministic, explainable, never advice.")}</p>
      </div>
    </header>

    {workshopDraft ? (
      <section className="iw-inset strategy-panel">
        <div className="strategy-panel__head">
          <p className="iw-kicker">{t("Strategy workshop")}</p>
          <button type="button" onClick={() => setWorkshopDraft(null)}>{t("Close")}</button>
        </div>
        <StrategyWorkshop initialDraft={workshopDraft} onCancel={() => setWorkshopDraft(null)} onSave={onWorkshopSave} />
      </section>
    ) : null}

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("My strategy list")}</p>
        <button type="button" className="workshop-save" onClick={() => setWorkshopDraft(workshopDraft ?? {
          name: "", entry: [{ factor: "breakout_high", op: "true", threshold: 0, window: 20 }],
          exitFactor: null, stopPct: 10, atrMult: null, addsUnits: null, fraction: 25, maxPositions: 4,
        })}>＋ {t("Build your own")}</button>
      </div>
      {saved.length === 0 ? <p className="strategy-comparison-note">{t("No custom strategies yet — build one, or start from a library template below.")}</p> : (
        <div className="my-strategy-list">
          {saved.map((item) => (
            <div key={item.id} className={cn("my-strategy-item", selectedId === item.id && "is-active")}>
              <button type="button" className="my-strategy-item__main" onClick={() => setSelectedId(item.id)}>
                <strong>{item.name}</strong>
                <span>{item.savedAt} · {item.id.slice(0, 14)}…</span>
              </button>
              <button type="button" className="workshop-remove" onClick={() => remove(item.id)}>{t("Delete")}</button>
            </div>
          ))}
        </div>
      )}
    </section>

    {selected ? (
      <section className="iw-inset strategy-panel">
        <div className="strategy-panel__head">
          <p className="iw-kicker">{t("Custom strategy")} · {selected.name}</p>
        </div>
        {!isTauriRuntime() ? <p className="strategy-comparison-note">{t("Running custom strategies needs the desktop app (browser preview cannot execute them).")}</p>
          : runState === "loading" ? <p className="strategy-comparison-note">{t("Running on history…")}</p>
          : runState === "ready" && artifact ? null
          : <div>
              <button type="button" className="workshop-save" onClick={() => run(selected)}>{t("Run on history")}</button>
              {runError ? <p className="strategy-compare__note">{t("Run failed")}: {runError}</p> : null}
            </div>}
        {artifact ? (
          <div className="space-y-4">
            <div className="strategy-stats">
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Final equity")}</p><p className="strategy-stat__value">{money(artifact.summary.finalEquity)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Total return")}</p><p className={cn("strategy-stat__value", artifact.summary.totalReturn > 0 && "is-positive", artifact.summary.totalReturn < 0 && "is-negative")}>{percent(artifact.summary.totalReturn)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Max drawdown")}</p><p className="strategy-stat__value is-negative">{percent(artifact.summary.maxDrawdown)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Fills")}</p><p className="strategy-stat__value">{artifact.summary.fillCount}</p></div>
            </div>
            {equityOption ? <EChart option={equityOption} label={t("Equity curve")} className="strategy-equity-chart" /> : null}
            {artifact.limitations ? <ul className="strategy-comparison-limits">{artifact.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
          </div>
        ) : null}
      </section>
    ) : null}

    <section className="iw-inset strategy-panel">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Reference strategy library")}</p>
        <span className="iw-subtle">{strategyLibrary.strategies.length}</span>
      </div>
      <p className="strategy-comparison-note">{t("Read-only reference: how the built-in strategies define their rules. Use a template to start your own.")}</p>
      <div className="my-strategy-library">
        {strategyLibrary.strategies.map((entry) => (
          <details key={entry.strategyId} className="strategy-compare">
            <summary><strong>{entry.title}</strong><span>{entry.strategyId}@{entry.version}</span></summary>
            <div className="strategy-compare__body">
              <p className="strategy-compare__note">{entry.description}</p>
              <ul className="strategy-rule-group">
                {entry.ruleTable.map((rule) => (
                  <li key={rule.ruleId}><code>{rule.ruleId}</code><span>{rule.statement}</span></li>
                ))}
              </ul>
              <button type="button" className="workshop-save" onClick={() => {
                setWorkshopDraft({ ...(TEMPLATE_PREFILL[entry.strategyId] ?? {}), name: "", entry: (TEMPLATE_PREFILL[entry.strategyId]?.entry ?? [{ factor: "breakout_high", op: "true", threshold: 0, window: 20 }]) as WorkshopDraft["entry"], exitFactor: (TEMPLATE_PREFILL[entry.strategyId]?.exitFactor ?? null), stopPct: (TEMPLATE_PREFILL[entry.strategyId]?.stopPct ?? 10), atrMult: (TEMPLATE_PREFILL[entry.strategyId]?.atrMult ?? null), addsUnits: (TEMPLATE_PREFILL[entry.strategyId]?.addsUnits ?? null), fraction: 25, maxPositions: 4 });
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}>{t("Use as template")}</button>
            </div>
          </details>
        ))}
      </div>
    </section>
  </div>;
}

function percent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}
