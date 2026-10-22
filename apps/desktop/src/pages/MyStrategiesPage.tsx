import { useEffect, useMemo, useRef, useState } from "react";

import { StrategyWorkshop, type WorkshopDraft } from "@/components/strategy/StrategyWorkshop";
import { WorkshopNumberInput } from "@/components/strategy/WorkshopNumberInput";
import { strategyLibrary } from "@/data/strategyLibrary";
import { isTauriRuntime, LONG_TIMEOUT_MS, runtimeRequest } from "@/data/runtimeService";
import { adaptStrategySimulation, type StrategySimulationView } from "@/data/strategySimulation";
import { strategySimulation } from "@/data/strategySimulationDemo";
import { useDataMode } from "@/data/DataModeProvider";
import { onRuntimeDataChange } from "@/data/runtimeInvalidation";
import { useLocale } from "@/locales/LocaleProvider";
import { newUserStrategyId, readUserStrategies, type SavedUserStrategy } from "@/lib/userStrategyLibrary";
import {
  buildSpecExportFile,
  dedupeStrategyName,
  parseSpecImport,
  type SpecImportReason,
} from "@/lib/strategySpecTransfer";
import { EChart } from "@/components/charts/EChart";
import { useTheme } from "@/components/layout/ThemeProvider";
import { formatCurrencyValue } from "@/lib/format";
import { cn } from "@/lib/utils";
import { accountIdentity, confirmedActiveAccount, LatestRunGate, ScopeRevision, strategyRunKey } from "@/lib/strategyRunContext";

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

function loadSaved() {
  // Shared, shape-checked reader: malformed or corrupted entries are
  // dropped instead of crashing the page (or poisoning later writes).
  return readUserStrategies(typeof localStorage === "undefined" ? undefined : localStorage);
}

/** Import failure reasons surface as one inline, localized line. */
const IMPORT_REASON_KEYS: Record<SpecImportReason, string> = {
  not_json: "The file is not valid JSON.",
  not_object: "The file does not match the strategy spec export format.",
  unsupported_schema: "Unsupported strategy schema version.",
  bad_name: "Strategy name is missing or too long.",
  bad_spec: "The spec payload is malformed.",
  schema_mismatch: "Schema versions disagree between file header and spec.",
};

export function MyStrategiesPage() {
  const { t, locale } = useLocale();
  const { theme } = useTheme();
  const dark = theme === "dark";
  const data = useDataMode();
  const [saved, setSaved] = useState(loadSaved);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workshopDraft, setWorkshopDraft] = useState<WorkshopDraft | null>(null);
  const [formulaMode, setFormulaMode] = useState(false);
  const [formulaName, setFormulaName] = useState("");
  const [entryFormula, setEntryFormula] = useState("close > highest(20)");
  const [exitFormula, setExitFormula] = useState("close < lowest(10)");
  const [formulaStopPct, setFormulaStopPct] = useState<number | null>(null);
  const [formulaAtrMult, setFormulaAtrMult] = useState<number | null>(null);
  const [formulaError, setFormulaError] = useState<string | null>(null);

  const FORMULA_PRESETS: Record<string, { entry: string; exit: string; label: string }> = {
    toujing_t1_breakout_trend: { label: "T1 · 突破趋势", entry: "close > highest(20) and close > sma(20)", exit: "close < lowest(10)" },
    toujing_dual_ma: { label: "双均线交叉", entry: "cross_up(5, 20)", exit: "cross_down(5, 20)" },
    toujing_rsi_mean_reversion: { label: "RSI 均值回归", entry: "rsi(14) < 30", exit: "rsi(14) > 70" },
    toujing_turtle_s2_long: { label: "海龟 S2", entry: "close > highest(55)", exit: "close < lowest(20)" },
  };


  const [runStateMap, setRunState] = useState<Record<string, "loading" | "ready" | "error">>({});
  const [runErrors, setRunErrors] = useState<Record<string, string>>({});
  const [artifacts, setArtifacts] = useState<Record<string, StrategySimulationView>>({});
  const scopeRevisionRef = useRef(new ScopeRevision());
  const globalScope = JSON.stringify([data.mode, data.activeAccount?.subject_id ?? null,
    data.activeAccount?.account_id ?? null, data.mode === "demo" ? data.exampleAccount.key : null]);
  const scopeRevision = scopeRevisionRef.current.update(globalScope);
  const [runAccountConfirmation, setRunAccountConfirmation] = useState<{ key: string; scopeRevision: number } | null>(null);
  const runAccount = confirmedActiveAccount(runAccountConfirmation, data.activeAccount, scopeRevision);
  const [sourceRevision, setSourceRevision] = useState(0);
  useEffect(() => onRuntimeDataChange((change) => {
    if (change.subject === runAccount?.subject_id && change.account === runAccount?.account_id) {
      setSourceRevision((value) => value + 1);
    }
  }), [runAccount?.subject_id, runAccount?.account_id]);
  const runGate = useRef(new LatestRunGate());

  const currency = "CNY";
  const money = (value: number) => formatCurrencyValue(value, locale, currency);
  const selected = saved.find((item) => item.id === selectedId) ?? null;
  const runKey = selected ? strategyRunKey({
    strategyId: selected.id, spec: selected.spec, mode: data.mode,
    subjectId: data.mode === "demo" ? data.exampleAccount.subjectId : runAccount?.subject_id ?? null,
    accountId: data.mode === "demo" ? data.exampleAccount.accountId : runAccount?.account_id ?? null,
    sourceFingerprint: `${data.mode === "demo" ? strategySimulation.dataFingerprint : `${runAccount?.updated_at ?? "missing"}:${sourceRevision}`}:${scopeRevision}`,
    universe: data.mode === "demo" ? "synthetic" : "own_account",
  }) : "";
  runGate.current.setContext(runKey);
  useEffect(() => () => runGate.current.invalidate(), []);
  const artifact = runKey ? artifacts[runKey] ?? null : null;
  const runState: "loading" | "ready" | "error" | null = runKey ? runStateMap[runKey] ?? null : null;
  const runError = runKey ? runErrors[runKey] ?? null : null;

  const persist = (next: typeof saved) => {
    setSaved(next);
    localStorage.setItem("toujing.userStrategies", JSON.stringify(next));
  };

  const onWorkshopSave = (draft: WorkshopDraft, spec: Record<string, unknown>) => {
    const id = newUserStrategyId();
    persist([...saved, { id, name: draft.name.trim(), savedAt: new Date().toISOString().slice(0, 10), spec }]);
    setWorkshopDraft(null);
    setSelectedId(id);
  };

  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const remove = (id: string) => {
    if (pendingDelete !== id) { setPendingDelete(id); return; }
    setPendingDelete(null);
    persist(saved.filter((item) => item.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const downloadSpec = (item: SavedUserStrategy) => {
    const payload = JSON.stringify(buildSpecExportFile(item), null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `toujing-strategy-${item.name.replace(/[^\w.-]+/g, "_") || item.id}.json`;
    anchor.click();
    // Revoking synchronously can abort the download before WebKit's WebView
    // has started it; release the URL asynchronously instead.
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };
  const importSpecFile = async (file: File) => {
    setImportError(null);
    const result = parseSpecImport(await file.text());
    if (!result.ok) {
      setImportError(`${t("Import failed")}: ${t(IMPORT_REASON_KEYS[result.reason])}`);
      return;
    }
    // Duplicate names get a numeric suffix so an import can never overwrite
    // or visually collide with an existing saved strategy.
    const name = dedupeStrategyName(saved.map((item) => item.name), result.name);
    const id = newUserStrategyId("import");
    persist([...saved, { id, name, savedAt: new Date().toISOString().slice(0, 10), spec: result.spec }]);
    setSelectedId(id);
  };

  const run = (entry: { id: string; spec: Record<string, unknown> }) => {
    if (!runKey || (data.mode === "real_user" && !runAccount)) return;
    const generation = runGate.current.begin(runKey);
    setArtifacts((state) => { const next = { ...state }; delete next[runKey]; return next; });
    setRunState((state) => ({ ...state, [runKey]: "loading" }));
    setRunErrors((state) => ({ ...state, [runKey]: "" }));
    const base: Record<string, unknown> = { strategy: entry.spec,
      universe: data.mode === "demo" ? "synthetic" : "own_account" };
    if (data.mode === "real_user" && runAccount) {
      base.subject_id = runAccount.subject_id;
      base.account_id = runAccount.account_id;
    }
    runtimeRequest<{ status: string; reason: string | null; artifact: unknown }>(
      "strategy_simulation.run_custom", base, LONG_TIMEOUT_MS)
      .then((result) => {
        if (!runGate.current.accepts(runKey, generation)) return;
        if (result.status === "available" && result.artifact) {
          setArtifacts((state) => ({ ...state, [runKey]: adaptStrategySimulation(result.artifact) }));
          setRunState((state) => ({ ...state, [runKey]: "ready" }));
        } else {
          // Failure lands in the "error" run state so the run button and
          // the reason stay visible and the strategy can be re-run.
          setRunErrors((state) => ({ ...state, [runKey]: result.reason ?? "运行失败" }));
          setRunState((state) => ({ ...state, [runKey]: "error" }));
        }
      })
      .catch((value) => {
        if (!runGate.current.accepts(runKey, generation)) return;
        setRunErrors((state) => ({ ...state, [runKey]: value instanceof Error ? value.message : String(value) }));
        setRunState((state) => ({ ...state, [runKey]: "error" }));
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

    {formulaMode ? (
      <section className="iw-inset strategy-panel">
        <div className="strategy-panel__head">
          <p className="iw-kicker">{t("Formula mode")}</p>
        </div>
        <div className="formula-form space-y-3">
          <label className="workshop-name">{t("Strategy name")}
            <input value={formulaName} maxLength={60} placeholder="例如：超卖买入"
              onChange={(event) => setFormulaName(event.target.value)} />
          </label>
          <label className="workshop-name">{t("Entry formula")}
            <textarea className="formula-input" rows={2} value={entryFormula}
              onChange={(event) => setEntryFormula(event.target.value)} />
          </label>
          <label className="workshop-name">{t("Exit formula")}
            <textarea className="formula-input" rows={2} value={exitFormula}
              onChange={(event) => setExitFormula(event.target.value)} />
          </label>
          <label className="workshop-check">
            <input type="checkbox" checked={formulaStopPct !== null}
              onChange={(event) => setFormulaStopPct(event.target.checked ? 10 : null)} />
            {t("Fixed stop-loss")}：
          </label>
          {formulaStopPct !== null ? <span className="workshop-inline-num">
            <WorkshopNumberInput value={formulaStopPct} min={1} max={50} onCommit={setFormulaStopPct} /> %
          </span> : null}
          <label className="workshop-check">
            <input type="checkbox" checked={formulaAtrMult !== null}
              onChange={(event) => setFormulaAtrMult(event.target.checked ? 2 : null)} />
            ATR 跟踪止损：前收 −
          </label>
          {formulaAtrMult !== null ? <span className="workshop-inline-num">
            <WorkshopNumberInput value={formulaAtrMult * 10} min={10} max={50} step={5}
              onCommit={(next) => setFormulaAtrMult(next / 10)} /> × ATR(14)
          </span> : null}
          <p className="workshop-misread">{t("Available functions: sma(n) ema(n) highest(n) lowest(n) rsi(n) roc(n) atr(n) atr_ratio(n) volume_ratio(n) range_pos(n) streak_down() cross_up(s,l) cross_down(s,l). Fields: close, entry_price (exit formula only).")}</p>
          <div className="formula-presets">
            {Object.entries(FORMULA_PRESETS).map(([id, preset]) => (
              <button key={id} type="button" className="workshop-remove" title={preset.entry}
                onClick={() => { setEntryFormula(preset.entry); setExitFormula(preset.exit); }}>
                {preset.label}
              </button>
            ))}
          </div>
          <p className="workshop-misread">{t("All functions are strictly backward-looking; formulas cannot access files, network, or your account data.")}</p>
          <div className="workshop-actions">
            <button type="button" className="workshop-save" onClick={() => {
              if (!isTauriRuntime()) { setFormulaError(t("Running custom strategies needs the desktop app (browser preview cannot execute them).")); return; }
              const spec = {
                schema_version: "user_strategy_formula.v1",
                name: formulaName.trim() || "公式策略",
                entry_formula: entryFormula,
                exit_formula: exitFormula,
                stop_loss_pct: formulaStopPct,
                sizing: { mode: "equal_weight", fraction: 0.25 },
                constraints: { max_positions: 4 },
              };
              const id = newUserStrategyId("formula");
              persist([...saved, { id, name: formulaName.trim() || "公式策略", savedAt: new Date().toISOString().slice(0, 10), spec }]);
              setSelectedId(id);
            }}>{t("Save and validate")}</button>
            <button type="button" onClick={() => setFormulaMode(false)}>{t("Cancel")}</button>
          </div>
          {formulaError ? <p className="workshop-error" role="alert">{formulaError}</p> : null}
        </div>
      </section>
    ) : null}

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
        <button type="button" className="workshop-save" onClick={() => {
          setFormulaMode(true);
          if (!formulaName) setFormulaName("我的公式策略");
        }}>λ {t("Write a formula")}</button>
        <button type="button" className="workshop-save" onClick={() => { setImportError(null); fileInputRef.current?.click(); }}>
          ⤓ {t("Import spec")}
        </button>
        <input ref={fileInputRef} type="file" accept="application/json,.json" className="sr-only" aria-hidden="true" tabIndex={-1}
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            event.target.value = "";
            if (chosen) void importSpecFile(chosen);
          }} />
      </div>
      {importError ? <p className="workshop-error" role="alert">{importError}</p> : null}
      {saved.length === 0 ? <p className="strategy-comparison-note">{t("No custom strategies yet — build one, or start from a library template below.")}</p> : (
        <div className="my-strategy-list">
          {saved.map((item) => (
            <div key={item.id} className={cn("my-strategy-item", selectedId === item.id && "is-active")}>
              <button type="button" className="my-strategy-item__main" onClick={() => setSelectedId(item.id)}>
                <strong>{item.name}</strong>
                <span>{item.savedAt} · {item.id.slice(0, 14)}…</span>
              </button>
              <button type="button" className="workshop-remove" onClick={() => downloadSpec(item)}>
                {t("Export spec")}
              </button>
              <button type="button" className="workshop-remove" onClick={() => remove(item.id)}>
                {pendingDelete === item.id ? t("Click again to confirm") : t("Delete")}
              </button>
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
        {isTauriRuntime() && data.mode === "real_user" ? <label className="workshop-inline-num">
          {locale === "zh-CN" ? "运行账户" : "Run account"}
          <select aria-label={locale === "zh-CN" ? "运行账户" : "Run account"} value={runAccount ? accountIdentity(runAccount) : ""}
            onChange={(event) => setRunAccountConfirmation(event.target.value ? { key: event.target.value, scopeRevision } : null)}>
            <option value="">{locale === "zh-CN" ? "请选择账户" : "Select an account"}</option>
            {data.activeAccount ? <option value={accountIdentity(data.activeAccount)}>{data.activeAccount.display_name} · {data.activeAccount.account_id}</option> : null}
          </select>
        </label> : null}
        {!isTauriRuntime() ? <p className="strategy-comparison-note">{t("Running custom strategies needs the desktop app (browser preview cannot execute them).")}</p>
          : data.mode === "real_user" && !runAccount ? <p className="strategy-comparison-note" role="alert">{locale === "zh-CN" ? "请先选择真实账户。" : "Select a real account before running."}</p>
          : runState === "loading" ? <p className="strategy-comparison-note">{t("Running on history…")}</p>
          : <div>
              <button type="button" className="workshop-save" onClick={() => run(selected)}>{t("Run on history")}</button>
              {runError ? <p role="alert" className="strategy-compare__note">{t("Run failed")}: {runError}</p> : null}
            </div>}
        {artifact ? (
          <div className="space-y-4">
            <p className="strategy-comparison-note">{data.mode === "demo" ? t("Synthetic demo universe") : t("My own traded instruments (real market, hfq)")} · {data.mode === "real_user" && runAccount ? `${runAccount.display_name} (${runAccount.subject_id}/${runAccount.account_id}) · ` : ""}{t("Data fingerprint")}: {artifact.dataFingerprint}</p>
            <div className="strategy-stats">
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Final equity")}</p><p className="strategy-stat__value">{money(artifact.summary.finalEquity)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Total return")}</p><p className={cn("strategy-stat__value", artifact.summary.totalReturn > 0 && "is-positive", artifact.summary.totalReturn < 0 && "is-negative")}>{percent(artifact.summary.totalReturn)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Max drawdown")}</p><p className="strategy-stat__value is-negative">{percent(artifact.summary.maxDrawdown)}</p></div>
              <div className="strategy-stat"><p className="strategy-stat__label">{t("Fills")}</p><p className="strategy-stat__value">{artifact.summary.fillCount}</p></div>
              {artifact.summary.rMultipleStats ? <div className="strategy-stat">
                <p className="strategy-stat__label">{t("R multiple")}</p>
                <p className="strategy-stat__value">{artifact.summary.rMultipleStats.avgR === null ? "—" : `${artifact.summary.rMultipleStats.avgR.toFixed(2)}R`}</p>
                <p className="strategy-stat__detail">{t("Median")} {artifact.summary.rMultipleStats.medianR === null ? "—" : `${artifact.summary.rMultipleStats.medianR.toFixed(2)}R`} · {t("Min")} {artifact.summary.rMultipleStats.minR === null ? "—" : `${artifact.summary.rMultipleStats.minR.toFixed(2)}R`} · {t("Max")} {artifact.summary.rMultipleStats.maxR === null ? "—" : `${artifact.summary.rMultipleStats.maxR.toFixed(2)}R`} · {t("Skipped (no stop-loss)")} {artifact.summary.rMultipleStats.skippedNoStop}</p>
              </div> : null}
            </div>
            {artifact.summary.rMultipleStats ? <p className="strategy-comparison-note">{t("R multiple definition")}: {artifact.summary.rMultipleStats.definition}</p> : null}
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
