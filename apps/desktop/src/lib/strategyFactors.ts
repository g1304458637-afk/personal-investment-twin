/**
 * Factor library metadata and condition statements shared by the strategy
 * workshop and saved user-strategy specs.  Plain data + pure functions, no
 * JSX: both the app and the node test runner can import this directly.
 * Factor ids mirror the Python FACTOR_LIBRARY ids; the Python sidecar
 * remains the source of truth for what a factor may accept.
 */

type OpType = "numeric" | "bool";

export type FactorLocale = "zh-CN" | "en-US";

interface FactorOption {
  id: string;
  /** zh-CN display label; never persisted — saved specs key on factor id. */
  label: string;
  labelEn: string;
  opType: OpType;
  /** Data key inside saved spec params objects; must stay stable. */
  paramLabel: string | null;
  paramDefault: number;
  misread: string;
  misreadEn: string;
}

export const FACTORS: FactorOption[] = [
  { id: "rsi", label: "RSI 相对强弱", labelEn: "RSI relative strength", opType: "numeric", paramLabel: "窗口", paramDefault: 14,
    misread: "趋势市里 RSI 可以连续数周低于 30——超卖不等于会反弹。",
    misreadEn: "Trend markets can hold RSI below 30 for weeks — oversold does not mean a rebound is due." },
  { id: "sma_gap", label: "价格相对均线（偏离%）", labelEn: "Price vs moving average (% gap)", opType: "numeric", paramLabel: "均线窗口", paramDefault: 20,
    misread: "均线有滞后性：偏离度刚转正时行情往往已走了一段。",
    misreadEn: "Moving averages lag: by the time the gap turns positive the move has often been underway for a while." },
  { id: "breakout_high", label: "创 N 日新高", labelEn: "New N-day high", opType: "bool", paramLabel: "回看窗口", paramDefault: 20,
    misread: "突破有假信号：突破后回落是最常见的亏损来源之一。",
    misreadEn: "Breakouts fail: a pullback right after a new high is one of the most common loss sources." },
  { id: "breakdown_low", label: "跌破 N 日新低", labelEn: "New N-day low", opType: "bool", paramLabel: "回看窗口", paramDefault: 10,
    misread: "破位既是止损信号也是抄底信号——方向由你的体系决定，工坊不替你选。",
    misreadEn: "A breakdown is both a stop signal and a dip-buy signal — the direction belongs to your system, not the workshop." },
  { id: "roc", label: "动量（N 日涨跌幅 %）", labelEn: "Momentum (N-day % change)", opType: "numeric", paramLabel: "回看窗口", paramDefault: 20,
    misread: "追动量买在高点、杀动量卖在低点，是最常见的误用。",
    misreadEn: "Chasing momentum at highs and dumping it at lows is the most common misuse." },
  { id: "atr_ratio", label: "波动率（ATR 占价 %）", labelEn: "Volatility (ATR as % of price)", opType: "numeric", paramLabel: "窗口", paramDefault: 14,
    misread: "高波动同时放大盈利与亏损，不等于机会。",
    misreadEn: "High volatility amplifies gains and losses alike; it is not an opportunity by itself." },
  { id: "ma_cross_up", label: "均线金叉", labelEn: "Moving-average golden cross", opType: "bool", paramLabel: null, paramDefault: 0,
    misread: "震荡市里金叉会反复出现和消失（骗线）。",
    misreadEn: "In ranging markets golden crosses appear and vanish repeatedly (whipsaws)." },
  { id: "ma_cross_down", label: "均线死叉", labelEn: "Moving-average death cross", opType: "bool", paramLabel: null, paramDefault: 0,
    misread: "死叉确认时价格通常已低于交叉点。",
    misreadEn: "By the time a death cross confirms, price is usually already below the crossing point." },
  { id: "volume_ratio", label: "量比（成交量/均量）", labelEn: "Volume ratio (volume / average volume)", opType: "numeric", paramLabel: "均量窗口", paramDefault: 20,
    misread: "合成示例股票池没有量数据——该因子只在真实行情运行时有效。",
    misreadEn: "The synthetic sample universe has no volume data — this factor only works on real market data." },
  { id: "range_position", label: "N 日区间位置", labelEn: "N-day range position", opType: "numeric", paramLabel: "回看窗口", paramDefault: 20,
    misread: "区间位置只描述在哪里，不预测方向。",
    misreadEn: "Range position describes where price is; it does not predict direction." },
  { id: "streak_down", label: "连续下跌天数", labelEn: "Consecutive down days", opType: "bool", paramLabel: null, paramDefault: 0,
    misread: "连跌不意味着见底——跌势中连跌十几天并不罕见。",
    misreadEn: "A losing streak is not a bottom — streaks of ten-plus down days do happen." },
  { id: "ema_gap", label: "价格相对 EMA（偏离%）", labelEn: "Price vs EMA (% gap)", opType: "numeric", paramLabel: "EMA 窗口", paramDefault: 20,
    misread: "EMA 比 SMA 更贴价，信号更频繁，噪声也更多。",
    misreadEn: "The EMA hugs price more closely than the SMA: more signals, more noise." },
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

export function factorLabel(option: FactorOption, locale: FactorLocale): string {
  return locale === "en-US" ? option.labelEn : option.label;
}

export function factorMisread(option: FactorOption, locale: FactorLocale): string {
  return locale === "en-US" ? option.misreadEn : option.misread;
}

/** Display-side wording for the persisted paramLabel data key. */
export function paramLabelText(paramLabel: string, locale: FactorLocale): string {
  if (locale !== "en-US") return paramLabel;
  const enLabels: Record<string, string> = {
    "窗口": "window",
    "均线窗口": "MA window",
    "回看窗口": "lookback window",
    "均量窗口": "volume-average window",
    "EMA 窗口": "EMA window",
  };
  return enLabels[paramLabel] ?? paramLabel;
}

export function conditionStatement(
  draft: ConditionDraft | Record<string, unknown>,
  locale: FactorLocale = "zh-CN",
): string {
  // Accepts both the workshop draft shape ({window, threshold}) and the
  // saved spec shape ({params: {window...}, threshold}).  Statements are
  // display-only; zh-CN output stays byte-identical for saved specs.
  const raw = draft as ConditionDraft & { params?: Record<string, number> };
  const option = factorOption(raw.factor);
  if (!option) return "";
  const label = factorLabel(option, locale);
  const window = raw.window ?? raw.params?.[option.paramLabel === null ? "" : option.paramLabel] ?? raw.params?.window;
  if (locale === "en-US") {
    const windowText = option.paramLabel ? ` (${paramLabelText(option.paramLabel, locale)} ${window ?? option.paramDefault})` : "";
    if (raw.op === "true") return `${label}${windowText} holds`;
    const symbol = raw.op === "gt" ? "≥" : "≤";
    return `${label}${windowText} ${symbol} ${raw.threshold}`;
  }
  const windowText = option.paramLabel ? `（${option.paramLabel} ${window ?? option.paramDefault}）` : "";
  if (raw.op === "true") return `${label}${windowText}成立`;
  const symbol = raw.op === "gt" ? "≥" : "≤";
  return `${label}${windowText} ${symbol} ${raw.threshold}`;
}
