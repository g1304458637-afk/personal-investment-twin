import { useState } from "react";

/**
 * Strategy workshop: the five-slot fill-in builder.  Specs are plain data
 * (user_strategy.v1) validated again by the Python sidecar at run time —
 * no user code is ever produced or executed.  Factor list mirrors the
 * Python FACTOR_LIBRARY ids; the sidecar remains the source of truth.
 */

type OpType = "numeric" | "bool";

interface FactorOption {
  id: string;
  label: string;
  opType: OpType;
  paramLabel: string | null;
  paramDefault: number;
  misread: string;
}

export const FACTORS: FactorOption[] = [
  { id: "rsi", label: "RSI 相对强弱", opType: "numeric", paramLabel: "窗口", paramDefault: 14,
    misread: "趋势市里 RSI 可以连续数周低于 30——超卖不等于会反弹。" },
  { id: "sma_gap", label: "价格相对均线（偏离%）", opType: "numeric", paramLabel: "均线窗口", paramDefault: 20,
    misread: "均线有滞后性：偏离度刚转正时行情往往已走了一段。" },
  { id: "breakout_high", label: "创 N 日新高", opType: "bool", paramLabel: "回看窗口", paramDefault: 20,
    misread: "突破有假信号：突破后回落是最常见的亏损来源之一。" },
  { id: "breakdown_low", label: "跌破 N 日新低", opType: "bool", paramLabel: "回看窗口", paramDefault: 10,
    misread: "破位既是止损信号也是抄底信号——方向由你的体系决定，工坊不替你选。" },
  { id: "roc", label: "动量（N 日涨跌幅 %）", opType: "numeric", paramLabel: "回看窗口", paramDefault: 20,
    misread: "追动量买在高点、杀动量卖在低点，是最常见的误用。" },
  { id: "atr_ratio", label: "波动率（ATR 占价 %）", opType: "numeric", paramLabel: "窗口", paramDefault: 14,
    misread: "高波动同时放大盈利与亏损，不等于机会。" },
  { id: "ma_cross_up", label: "均线金叉", opType: "bool", paramLabel: null, paramDefault: 0,
    misread: "震荡市里金叉会反复出现和消失（骗线）。" },
  { id: "ma_cross_down", label: "均线死叉", opType: "bool", paramLabel: null, paramDefault: 0,
    misread: "死叉确认时价格通常已低于交叉点。" },
  { id: "volume_ratio", label: "量比（成交量/均量）", opType: "numeric", paramLabel: "均量窗口", paramDefault: 20,
    misread: "合成示例股票池没有量数据——该因子只在真实行情运行时有效。" },
  { id: "range_position", label: "N 日区间位置", opType: "numeric", paramLabel: "回看窗口", paramDefault: 20,
    misread: "区间位置只描述在哪里，不预测方向。" },
  { id: "streak_down", label: "连续下跌天数", opType: "numeric", paramLabel: null, paramDefault: 0,
    misread: "连跌不意味着见底——跌势中连跌十几天并不罕见。" },
  { id: "ema_gap", label: "价格相对 EMA（偏离%）", opType: "numeric", paramLabel: "EMA 窗口", paramDefault: 20,
    misread: "EMA 比 SMA 更贴价，信号更频繁，噪声也更多。" },
];

export interface ConditionDraft {
  factor: string;
  op: "gt" | "lt" | "true";
  threshold: number;
  window: number;
  anyGroup?: boolean;
}

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

export function factorOption(id: string): FactorOption | undefined {
  return FACTORS.find((item) => item.id === id);
}

function newCondition(): ConditionDraft {
  return { factor: "breakout_high", op: "true", threshold: 0, window: 20 };
}

export function conditionStatement(draft: ConditionDraft | Record<string, unknown>): string {
  // Accepts both the workshop draft shape ({window, threshold}) and the
  // saved spec shape ({params: {window...}, threshold}).
  const raw = draft as ConditionDraft & { params?: Record<string, number> };
  const option = factorOption(raw.factor);
  if (!option) return "";
  const window = raw.window ?? raw.params?.[option.paramLabel === null ? "" : option.paramLabel] ?? raw.params?.window;
  const windowText = option.paramLabel ? `（${option.paramLabel} ${window ?? option.paramDefault}）` : "";
  if (raw.op === "true") return `${option.label}${windowText}成立`;
  const symbol = raw.op === "gt" ? "≥" : "≤";
  return `${option.label}${windowText} ${symbol} ${raw.threshold}`;
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
        <input type="number" min={2} value={draft.window}
          onChange={(event) => onChange({ ...draft, window: Number(event.target.value) || 2 })} />
      </label>
    ) : null}
    {option.opType === "numeric" ? (
      <>
        <select aria-label="比较" value={draft.op} onChange={(event) => onChange({ ...draft, op: event.target.value as "gt" | "lt" })}>
          <option value="gt">高于或等于</option>
          <option value="lt">低于</option>
        </select>
        <input aria-label="阈值" type="number" step="0.01" value={draft.threshold}
          title={numericThresholdHint[draft.factor]}
          onChange={(event) => onChange({ ...draft, threshold: Number(event.target.value) || 0 })} />
      </>
    ) : null}
    {removable && onRemove ? <button type="button" className="workshop-remove" onClick={onRemove} aria-label="移除条件">×</button> : null}
    <p className="workshop-misread">⚠ {option.misread}</p>
  </div>;
}

export function StrategyWorkshop({ onSave, onCancel }: {
  onSave: (draft: WorkshopDraft, spec: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [entry, setEntry] = useState<ConditionDraft[]>([newCondition()]);
  const [exitFactor, setExitFactor] = useState<ConditionDraft | null>(null);
  const [stopPct, setStopPct] = useState<number | null>(10);
  const [atrMult, setAtrMult] = useState<number | null>(null);
  const [addsUnits, setAddsUnits] = useState<number | null>(null);
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
      {stopPct !== null ? <span className="workshop-inline-num"><input type="number" min={1} max={50} value={stopPct}
        onChange={(event) => setStopPct(Number(event.target.value) || 1)} /> %</span> : null}
      <label className="workshop-check">
        <input type="checkbox" checked={atrMult !== null} onChange={(event) => setAtrMult(event.target.checked ? 2 : null)} />
        ATR 跟踪止损：止损每日上移至 前收 −
      </label>
      {atrMult !== null ? <span className="workshop-inline-num">
        <input type="number" min={10} max={50} step={5} value={atrMult * 10}
          onChange={(event) => setAtrMult((Number(event.target.value) || 20) / 10)} /> × ATR
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">③b 加仓规则（可选）</p>
      <label className="workshop-check">
        <input type="checkbox" checked={addsUnits !== null} onChange={(event) => setAddsUnits(event.target.checked ? 2 : null)} />
        入场条件再次满足时追加 1 单元，最多
      </label>
      {addsUnits !== null ? <span className="workshop-inline-num">
        <input type="number" min={2} max={4} value={addsUnits}
          onChange={(event) => setAddsUnits(Math.min(4, Math.max(2, Number(event.target.value) || 2)))} /> 单元
      </span> : null}
    </section>
    <section>
      <p className="workshop-title">④ 每笔买多少</p>
      <label className="workshop-inline-num">
        等权：每仓 = 净值
        <input type="number" min={5} max={100} value={fraction}
          onChange={(event) => setFraction(Number(event.target.value) || 25)} /> %
      </label>
      <label className="workshop-inline-num">
        最多同时
        <input type="number" min={1} max={8} value={maxPositions}
          onChange={(event) => setMaxPositions(Number(event.target.value) || 4)} /> 仓
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
