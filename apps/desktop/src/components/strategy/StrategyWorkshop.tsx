import { useState } from "react";

import {
  conditionStatement,
  factorOption,
  FACTORS,
  type ConditionDraft,
} from "@/lib/strategyFactors";
import { WorkshopNumberInput } from "@/components/strategy/WorkshopNumberInput";
import { useLocale } from "@/locales/LocaleProvider";

/**
 * Strategy workshop: the five-slot fill-in builder.  Specs are plain data
 * (user_strategy.v1) validated again by the Python sidecar at run time —
 * no user code is ever produced or executed.  Factor list mirrors the
 * Python FACTOR_LIBRARY ids; the sidecar remains the source of truth.
 */

// The factor metadata, condition drafting shapes and statement rendering
// live in src/lib/strategyFactors.ts so saved-spec rendering and node
// tests can share them without importing component code.
export { conditionStatement, factorOption, FACTORS };
export type { ConditionDraft };

export interface WorkshopDraft {
  name: string;
  entry: ConditionDraft[];
  exitFactor: ConditionDraft | null;
  stopPct: number | null;
  atrMult: number | null;
  addsUnits: number | null;
  fraction: number;
  maxPositions: number;
}

// Values are locale keys (the English strings); translate at render with t().
const numericThresholdHint: Record<string, string> = {
  rsi: "RSI value, e.g. 30",
  sma_gap: "Deviation as a decimal, e.g. 0.05 means 5% above the moving average",
  roc: "Change as a decimal, e.g. 0.10 means 10%",
  atr_ratio: "Volatility share as a decimal, e.g. 0.03",
};

function newCondition(): ConditionDraft {
  return { factor: "breakout_high", op: "true", threshold: 0, window: 20 };
}

function conditionToSpec(draft: ConditionDraft): Record<string, unknown> {
  const params: Record<string, number> = {};
  const option = FACTORS.find((item) => item.id === draft.factor);
  if (option?.paramLabel) params.window = draft.window;
  if (draft.op === "true")
    return { factor: draft.factor, params, op: "true" };
  return { factor: draft.factor, params, op: draft.op, threshold: draft.threshold };
}

export function draftToSpec(draft: WorkshopDraft): Record<string, unknown> {
  return {
    schema_version: "user_strategy.v2",
    name: draft.name.trim(),
    entry: {
      all_of: draft.entry.filter((c) => !c.anyGroup).map(conditionToSpec),
      any_of: draft.entry.filter((c) => c.anyGroup).map(conditionToSpec),
    },
    exit: {
      any_of: draft.exitFactor ? [conditionToSpec(draft.exitFactor)] : [],
      stop_loss_pct: draft.stopPct === null ? null : draft.stopPct / 100,
      atr_trailing_mult: draft.atrMult ?? null,
    },
    adds: draft.addsUnits === null ? null : { max_units: draft.addsUnits },
    sizing: { mode: "equal_weight", fraction: draft.fraction / 100 },
    constraints: { max_positions: draft.maxPositions },
  };
}

function ConditionRow({ draft, onChange, onRemove, removable }: {
  draft: ConditionDraft;
  onChange: (next: ConditionDraft) => void;
  onRemove?: () => void;
  removable: boolean;
}) {
  const { t } = useLocale();
  const option = factorOption(draft.factor) ?? FACTORS[0];
  const hintKey = numericThresholdHint[draft.factor];
  return <div className="workshop-condition">
    <select aria-label={t("Factor")} value={draft.factor} onChange={(event) => {
      const next = factorOption(event.target.value) ?? FACTORS[0];
      onChange({ ...draft, factor: next.id, op: next.opType === "bool" ? "true" : "gt", window: next.paramDefault });
    }}>
      {FACTORS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
    </select>
    {option.paramLabel ? (
      <label className="workshop-param">
        {option.paramLabel}
        <WorkshopNumberInput value={draft.window} min={2} max={250}
          onCommit={(next) => onChange({ ...draft, window: next })} />
      </label>
    ) : null}
    {option.opType === "numeric" ? (
      <>
        <select aria-label={t("Comparison operator")} value={draft.op} onChange={(event) => onChange({ ...draft, op: event.target.value as "gt" | "lt" })}>
          <option value="gt">{t("At or above")}</option>
          <option value="lt">{t("Below")}</option>
        </select>
        <WorkshopNumberInput value={draft.threshold} step={0.01}
          title={hintKey ? t(hintKey) : undefined}
          onCommit={(next) => onChange({ ...draft, threshold: next })} />
      </>
    ) : null}
    {removable && onRemove ? <button type="button" className="workshop-remove" onClick={onRemove} aria-label={t("Remove condition")}>×</button> : null}
    <p className="workshop-misread">⚠ {option.misread}</p>
  </div>;
}

export function StrategyWorkshop({ onSave, onCancel, initialDraft }: {
  onSave: (draft: WorkshopDraft, spec: Record<string, unknown>) => void;
  onCancel: () => void;
  initialDraft?: WorkshopDraft | null;
}) {
  const [name, setName] = useState(initialDraft?.name ?? "");
  const [entry, setEntry] = useState<ConditionDraft[]>(initialDraft?.entry ?? [newCondition()]);
  const [exitFactor, setExitFactor] = useState<ConditionDraft | null>(initialDraft?.exitFactor ?? null);
  const [stopPct, setStopPct] = useState<number | null>(initialDraft?.stopPct ?? 10);
  const [atrMult, setAtrMult] = useState<number | null>(initialDraft?.atrMult ?? null);
  const [addsUnits, setAddsUnits] = useState<number | null>(initialDraft?.addsUnits ?? null);
  const [fraction, setFraction] = useState(25);
  const [maxPositions, setMaxPositions] = useState(4);
  const [error, setError] = useState<string | null>(null);
  const { t } = useLocale();

  const save = () => {
    if (!name.trim()) { setError(t("Give your strategy a name")); return; }
    if (entry.length === 0) { setError(t("At least one entry condition is required")); return; }
    if (exitFactor === null && stopPct === null) { setError(t("At least one exit mechanism is required")); return; }
    const draft: WorkshopDraft = { name, entry, exitFactor, stopPct, atrMult, addsUnits, fraction, maxPositions };
    try {
      const spec = draftToSpec(draft);
      JSON.stringify(spec);
      onSave(draft, spec);
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    }
  };

  return <div className="workshop">
    <label className="workshop-name">
      {t("Strategy name")}
      <input value={name} maxLength={60} placeholder={t("e.g. Buy the dip, sell the bounce")}
        onChange={(event) => setName(event.target.value)} />
    </label>
    <section>
      <p className="workshop-title">{t("① When to buy (all conditions must hold)")}</p>
      {entry.map((condition, index) => (
        <ConditionRow key={index} draft={condition} removable={entry.length > 1}
          onChange={(next) => setEntry(entry.map((item, i) => (i === index ? next : item)))}
          onRemove={() => setEntry(entry.filter((_, i) => i !== index))} />
      ))}
      {entry.length < 3 ? <button type="button" className="workshop-add" onClick={() => setEntry([...entry, newCondition()])}>{t("＋ Add condition")}</button> : null}
    </section>
    <section>
      <p className="workshop-title">{t("② When to sell")}</p>
      <label className="workshop-check">
        <input type="checkbox" checked={exitFactor !== null} onChange={(event) => setExitFactor(event.target.checked ? newCondition() : null)} />
        {t("Exit on reverse condition")}
      </label>
      {exitFactor ? <ConditionRow draft={exitFactor} removable={false} onChange={setExitFactor} /> : null}
      <label className="workshop-check">
        <input type="checkbox" checked={stopPct !== null} onChange={(event) => setStopPct(event.target.checked ? 10 : null)} />
        {t("Fixed stop-loss:")}
      </label>
      {stopPct !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={stopPct} min={1} max={50} onCommit={setStopPct} /> %
      </span> : null}
      <label className="workshop-check">
        <input type="checkbox" checked={atrMult !== null} onChange={(event) => setAtrMult(event.target.checked ? 2 : null)} />
        {t("ATR trailing stop: raised daily to prior close −")}
      </label>
      {atrMult !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={atrMult * 10} min={10} max={50} step={5}
          onCommit={(next) => setAtrMult(next / 10)} /> × ATR
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">{t("③ Add-on rules (optional)")}</p>
      <label className="workshop-check">
        <input type="checkbox" checked={addsUnits !== null} onChange={(event) => setAddsUnits(event.target.checked ? 2 : null)} />
        {t("Add 1 unit when the entry conditions trigger again, up to")}
      </label>
      {addsUnits !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={addsUnits} min={2} max={4} onCommit={setAddsUnits} /> {t("units")}
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">{t("④ How much per trade")}</p>
      <label className="workshop-inline-num">
        {t("Equal weight: each position = equity")}
        <WorkshopNumberInput value={fraction} min={5} max={100} onCommit={setFraction} /> %
      </label>
      <label className="workshop-inline-num">
        {t("Max simultaneous")}
        <WorkshopNumberInput value={maxPositions} min={1} max={8} onCommit={setMaxPositions} /> {t("positions")}
      </label>
    </section>
    <section>
      <p className="workshop-title">{t("⑤ Execution (fixed, not editable)")}</p>
      <p className="workshop-misread">{t("Signals confirm at close, fill at next open · round lots of 100 shares · commission 0.03% (min CNY 5) + 0.1% stamp duty on sells · no add-ons by default")}</p>
    </section>
    {error ? <p className="workshop-error" role="alert">{error}</p> : null}
    <div className="workshop-actions">
      <button type="button" className="workshop-save" onClick={save}>{t("Save strategy")}</button>
      <button type="button" onClick={onCancel}>{t("Cancel")}</button>
    </div>
  </div>;
}
