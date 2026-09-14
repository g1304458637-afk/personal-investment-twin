/**
 * Factor library metadata and condition statements shared by the strategy
 * workshop and saved user-strategy specs.  Plain data + pure functions, no
 * JSX: both the app and the node test runner can import this directly.
 * Factor ids mirror the Python FACTOR_LIBRARY ids; the Python sidecar
 * remains the source of truth for what a factor may accept.
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

export function factorOption(id: string): FactorOption | undefined {
  return FACTORS.find((item) => item.id === id);
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
