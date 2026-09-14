import { useState } from "react";

import {
  conditionStatement,
  factorOption,
  FACTORS,
  type ConditionDraft,
} from "@/lib/strategyFactors";
import { WorkshopNumberInput } from "@/components/strategy/WorkshopNumberInput";

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

const numericThresholdHint: Record<string, string> = {
  rsi: "RSI 数值，如 30",
  sma_gap: "偏离度小数，如 0.05 表示高于均线 5%",
  roc: "涨跌幅小数，如 0.10 表示 10%",
  atr_ratio: "波动占比小数，如 0.03",
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
  const option = factorOption(draft.factor) ?? FACTORS[0];
  return <div className="workshop-condition">
    <select aria-label="因子" value={draft.factor} onChange={(event) => {
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
        <select aria-label="比较" value={draft.op} onChange={(event) => onChange({ ...draft, op: event.target.value as "gt" | "lt" })}>
          <option value="gt">高于或等于</option>
          <option value="lt">低于</option>
        </select>
        <WorkshopNumberInput value={draft.threshold} step={0.01}
          title={numericThresholdHint[draft.factor]}
          onCommit={(next) => onChange({ ...draft, threshold: next })} />
      </>
    ) : null}
    {removable && onRemove ? <button type="button" className="workshop-remove" onClick={onRemove} aria-label="移除条件">×</button> : null}
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

  const save = () => {
    if (!name.trim()) { setError("请给策略起个名字"); return; }
    if (entry.length === 0) { setError("至少需要一个入场条件"); return; }
    if (exitFactor === null && stopPct === null) { setError("至少需要一种退出机制"); return; }
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
      策略名称
      <input value={name} maxLength={60} placeholder="例如：跌了就买，反弹就走"
        onChange={(event) => setName(event.target.value)} />
    </label>
    <section>
      <p className="workshop-title">① 什么时候买入（条件需同时满足）</p>
      {entry.map((condition, index) => (
        <ConditionRow key={index} draft={condition} removable={entry.length > 1}
          onChange={(next) => setEntry(entry.map((item, i) => (i === index ? next : item)))}
          onRemove={() => setEntry(entry.filter((_, i) => i !== index))} />
      ))}
      {entry.length < 3 ? <button type="button" className="workshop-add" onClick={() => setEntry([...entry, newCondition()])}>＋ 加条件</button> : null}
    </section>
    <section>
      <p className="workshop-title">③ 什么时候卖出</p>
      <label className="workshop-check">
        <input type="checkbox" checked={exitFactor !== null} onChange={(event) => setExitFactor(event.target.checked ? newCondition() : null)} />
        反向条件退出
      </label>
      {exitFactor ? <ConditionRow draft={exitFactor} removable={false} onChange={setExitFactor} /> : null}
      <label className="workshop-check">
        <input type="checkbox" checked={stopPct !== null} onChange={(event) => setStopPct(event.target.checked ? 10 : null)} />
        固定止损：
      </label>
      {stopPct !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={stopPct} min={1} max={50} onCommit={setStopPct} /> %
      </span> : null}
      <label className="workshop-check">
        <input type="checkbox" checked={atrMult !== null} onChange={(event) => setAtrMult(event.target.checked ? 2 : null)} />
        ATR 跟踪止损：止损每日上移至 前收 −
      </label>
      {atrMult !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={atrMult * 10} min={10} max={50} step={5}
          onCommit={(next) => setAtrMult(next / 10)} /> × ATR
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">③b 加仓规则（可选）</p>
      <label className="workshop-check">
        <input type="checkbox" checked={addsUnits !== null} onChange={(event) => setAddsUnits(event.target.checked ? 2 : null)} />
        入场条件再次满足时追加 1 单元，最多
      </label>
      {addsUnits !== null ? <span className="workshop-inline-num">
        <WorkshopNumberInput value={addsUnits} min={2} max={4} onCommit={setAddsUnits} /> 单元
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">④ 每笔买多少</p>
      <label className="workshop-inline-num">
        等权：每仓 = 净值
        <WorkshopNumberInput value={fraction} min={5} max={100} onCommit={setFraction} /> %
      </label>
      <label className="workshop-inline-num">
        最多同时
        <WorkshopNumberInput value={maxPositions} min={1} max={8} onCommit={setMaxPositions} /> 仓
      </label>
    </section>
    <section>
      <p className="workshop-title">⑤ 执行（固定，不可修改）</p>
      <p className="workshop-misread">信号收盘确认 → 次日开盘成交 · 100 股整手 · 佣金 0.03%（最低 5 元）+ 卖出印花税 0.1% · 默认不加仓</p>
    </section>
    {error ? <p className="workshop-error" role="alert">{error}</p> : null}
    <div className="workshop-actions">
      <button type="button" className="workshop-save" onClick={save}>保存策略</button>
      <button type="button" onClick={onCancel}>取消</button>
    </div>
  </div>;
}
