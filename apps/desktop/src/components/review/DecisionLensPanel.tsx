import { useLocale } from "@/locales/LocaleProvider";
import { formatLensDate as formatDate, type DecisionLensReport, type DecisionLensMethod, type DecisionLensCheck } from "@/data/episodeLens";
import type { PositionEpisodeEntryView } from "@/data/positionEpisode";

import "./decision-lens.css";

type LensMethodSelectorProps = {
  report: DecisionLensReport;
  methodId: string;
  onSelect: (methodId: string) => void;
};

type LensDecisionInspectorProps = {
  report: DecisionLensReport;
  onSelectMethod: (id: string) => void;
  method: DecisionLensMethod;
  check: DecisionLensCheck;
  currency: string | null;
  onViewActual: () => void;
};

type LensDecisionTimelineProps = {
  entry: PositionEpisodeEntryView;
  method: DecisionLensMethod;
  decisionId: string | null;
  onSelect: (decisionId: string) => void;
};

const verdictCopy = {
  aligned: "规则吻合",
  different: "规则分歧",
  insufficient: "资料不足",
  not_applicable: "不适用",
} as const;

function decisionCopy(type: PositionEpisodeEntryView["decisions"][number]["decisionType"]) {
  return ({ open_position: "建仓", add_position: "加仓", reduce_position: "减仓", close_position: "平仓" } as const)[type];
}

function conditionValue(value: number | null, unit: DecisionLensCheck["conditions"][number]["unit"], locale: string, currency: string | null) {
  if (value === null) return "—";
  if (unit === "ratio") return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value);
  if (unit === "price") return currency
    ? new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 4 }).format(value)
    : `${new Intl.NumberFormat(locale, {maximumFractionDigits: 4}).format(value)}（币种未知）`;
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
}

/** A method picker; it deliberately reports rules, not performance or a backtest. */
export function LensMethodSelector({ report, methodId, onSelect }: LensMethodSelectorProps) {
  return <section className="decision-lens-methods" aria-labelledby="decision-lens-title">
    <div className="decision-lens-heading">
      <p className="decision-lens-kicker">DECISION LENS / 策略复盘</p>
      <h2 id="decision-lens-title">同一段历史，三把核对尺——不是三个策略。</h2>
      <p>行情、成交与持仓保持原样。每张卡独立核对你已发生的操作；其中两把尺的条件后来被组合成完整策略 T1（见“策略历史模拟”页）。</p>
    </div>
    <details className="decision-lens-provenance"><summary>这三套方法怎样核对历史？</summary>
      <p>这是三套参数固定的教学规则，不是完整的名家策略，彼此也不是三个独立策略——它们是核对已发生操作的三个视角。日线信号只取操作日前的收盘观察；成本规则核对实际成交与操作前成本。</p>
      <p>其中「20日均线趋势」与「20日收盘突破」的条件已被组合为唯一一个完整策略 T1（突破趋势，见“策略历史模拟”页）；「成本加仓」是独立的成本纪律核对，未进入 T1——T1 明确声明不加仓。</p>
      {report.limitations.map((limitation, index) => <p key={index}>{limitation}</p>)}
    </details>
    <div className="decision-lens-method-grid" role="group" aria-label="选择复盘方法">
      {report.methods.map((method) => {
        const selected = method.id === methodId;
        return <button key={method.id} type="button" className="decision-lens-method" aria-pressed={selected} onClick={() => onSelect(method.id)}>
          <span className="decision-lens-method__state">{selected ? "当前核对尺" : "查看核对尺"}</span>
          <strong>{method.title}</strong>
          {method.id === "cost_addition"
            ? <em className="decision-lens-method__tag">纪律核对 · 未进入 T1</em>
            : <em className="decision-lens-method__tag">T1 规则来源</em>}
          <span>{method.description}</span>
          <code>{method.rule}</code>
          <small>规则版本 {method.version}</small>
        </button>;
      })}
    </div>
  </section>;
}

export function LensDecisionInspector({ report, onSelectMethod, method, check, currency, onViewActual }: LensDecisionInspectorProps) {
  const { locale } = useLocale();
  const actual = `${check.actual.side === "BUY" ? "买入" : "卖出"} ${conditionValue(check.actual.quantity, "count", locale, currency)} · ${conditionValue(check.actual.price, "price", locale, currency)}`;
  return <aside className="decision-lens-inspector" aria-labelledby="decision-lens-inspector-title">
    <label className="decision-lens-compact-switch"><span>切换观察方法</span><select aria-label="切换观察方法" value={method.id} onChange={event => onSelectMethod(event.target.value)}>{report.methods.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
    <div className="decision-lens-inspector__top">
      <div>
        <p className="decision-lens-kicker">逐笔核对</p>
        <h3 id="decision-lens-inspector-title">{check.market_date?.replaceAll("-", "/") ?? "市场日期待核对"}</h3>
      </div>
      <span className={`decision-lens-verdict decision-lens-verdict--${check.verdict}`}><span aria-hidden="true">{check.verdict === "aligned" ? "✓" : check.verdict === "different" ? "≠" : "·"}</span>{verdictCopy[check.verdict]}</span>
    </div>
    <div className="decision-lens-action-pair">
      <div><span>实际操作</span><strong>{actual}</strong></div>
      <div><span>按这套规则</span><strong>{check.expected_action}</strong></div>
    </div>
    <p className="decision-lens-explanation">{check.explanation}</p>
    <div className="decision-lens-conditions" aria-label="规则条件">
      {check.conditions.map((condition, index) => <div className="decision-lens-condition" key={`${condition.label}-${index}`}>
        <span className={`decision-lens-condition__mark ${condition.passed === true ? "is-passed" : condition.passed === false ? "is-failed" : "is-unknown"}`} aria-label={condition.passed === true ? "条件满足" : condition.passed === false ? "条件未满足" : "条件未知"}>{condition.passed === true ? "✓" : condition.passed === false ? "×" : "—"}</span>
        <span>{condition.label}</span>
        <strong>{conditionValue(condition.actual, condition.unit, locale, currency)} {condition.operator} {conditionValue(condition.threshold, condition.unit, locale, currency)}</strong>
      </div>)}
    </div>
    <div className="decision-lens-inspector__footer">
      <p>{check.observed_through ? <>日线截至 {formatDate(check.observed_through, locale)} · {check.observation_count} 个观测</> : method.id === "cost_addition" ? <>依据实际成交与操作前持仓</> : <>未取得可用的日前行情</>}</p>
      <button type="button" onClick={onViewActual}>查看实际操作<span aria-hidden="true"> →</span></button>
    </div>
    <details className="decision-lens-provenance">
      <summary>规则版本与数据依据</summary>
      <p>{method.id}@{method.version} · prior_daily_close_only</p>
      <p>{method.rule}</p>
      <p>状态引用：{check.state_before_ref}</p>
      <p>输入指纹：{check.input_fingerprint}</p>
      {check.limitations.length ? <p>限制：{check.limitations.join("；")}</p> : null}
    </details>
  </aside>;
}

export function LensDecisionTimeline({ entry, method, decisionId, onSelect }: LensDecisionTimelineProps) {
  const { locale } = useLocale();
  const checks = new Map(method.checks.map((check) => [check.decision_id, check]));
  return <nav className="decision-lens-timeline" aria-label="按时间选择历史操作">
    <div className="decision-lens-timeline__head"><p className="decision-lens-kicker">历史操作</p><span>{entry.decisions.length} 笔决策</span></div>
    <div className="decision-lens-timeline__items">
      {entry.decisions.map((decision, index) => {
        const check = checks.get(decision.decisionId);
        const selected = decision.decisionId === decisionId;
        return <button key={decision.decisionId} type="button" className="decision-lens-timeline__item" aria-pressed={selected} onClick={() => onSelect(decision.decisionId)}>
          <span className="decision-lens-timeline__number">{String(index + 1).padStart(2, "0")}</span>
          <strong>{decisionCopy(decision.decisionType)} · {new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(decision.executedQuantity)}</strong>
          <span>{formatDate(check?.market_date ?? decision.occurredAt, locale)} · {conditionValue(decision.executionPrice, "price", locale, entry.instrument.currency)}</span>
          <em className={`decision-lens-status decision-lens-status--${check?.verdict ?? "insufficient"}`}>{check ? verdictCopy[check.verdict] : "未核对"}</em>
        </button>;
      })}
    </div>
  </nav>;
}
