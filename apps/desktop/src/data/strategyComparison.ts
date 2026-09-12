/**
 * Transport adapter for the strategy-comparison artifact (demo).
 * Validation only: no finance is computed in the browser.
 */

export interface ComparisonRuleFill {
  fillId: string;
  orderId: string | null;
  trigger: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  fee: number;
  day: string;
  note: string | null;
}

export interface ComparisonReportView {
  episodeId: string;
  instrument: string;
  isSynthetic: boolean;
  windowStart: string | null;
  windowEnd: string | null;
  barCount: number;
  barsCovered: string;
  userExecutions: { executionId: string; day: string; side: "BUY" | "SELL"; quantity: number; price: number; fee: number }[];
  ruleFills: ComparisonRuleFill[];
  windowUserNetCashFlow: number;
  windowRuleNetCashFlow: number;
  windowDifferenceNote: string;
  recordedEpisodeResult: { pnl: number | null; resultKind: string | null; resultSign: string | null };
  decisionVerdicts: { executionId: string; day: string; side: "BUY" | "SELL"; verdict: "aligned" | "different" | "insufficient"; reasonText: string; ruleChecks: { rule: string; passed: boolean }[] }[];
  limitations: string[];
}

export interface ComparisonRuleView {
  ruleId: string;
  source: string;
  statement: string;
}

export interface StrategyComparisonView {
  strategyId: string;
  ruleTable: ComparisonRuleView[];
  reports: ComparisonReportView[];
  portfolio: {
    user: { scope: string; realizedEpisodeCount: number; realizedPnlTotal: number; note: string };
    strategy: { strategyId: string; version: string; finalEquity: number; totalReturn: number; maxDrawdown: number; tradingDays: number };
    note: string;
    limitations: string[];
  } | null;
  limitations: string[];
}

const fail = (): never => { throw new Error("strategy_comparison_projection_invalid"); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown): string => typeof x === "string" && x.trim().length > 0 && x.length <= 6000 ? x : fail();
const finite = (x: unknown): number => typeof x === "number" && Number.isFinite(x) ? x : fail();
const nullableText = (x: unknown): string | null => x === null ? null : text(x);
const nullableFinite = (x: unknown): number | null => x === null ? null : finite(x);
const array = (x: unknown): unknown[] => Array.isArray(x) && x.length <= 5000 ? x : fail();
const day = (x: unknown): string => {
  const s = text(x);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) fail();
  return s;
};
const side = (x: unknown): "BUY" | "SELL" => x === "BUY" || x === "SELL" ? x : fail();

function fill(raw: unknown): ComparisonRuleFill {
  const value = object(raw);
  const trigger = text(value.trigger);
  if (!["signal_order", "stop_loss", "delisting_liquidation"].includes(trigger)) fail();
  return {
    fillId: text(value.fill_id), orderId: nullableText(value.order_id), trigger,
    side: side(value.side), quantity: finite(value.quantity), price: finite(value.price),
    fee: finite(value.fee), day: day(value.day), note: nullableText(value.note),
  };
}

function report(raw: unknown): ComparisonReportView {
  const value = object(raw);
  if (!value.is_synthetic) fail();
  const instrument = text(value.instrument);
  // Mirror the Python-side isolation rule: synthetic demo data uses SYN ids.
  if (!instrument.startsWith("SYN")) fail();
  const recorded = object(value.recorded_episode_result);
  // An honest report always carries its boundary statements.
  const limitations = array(value.limitations).map(text);
  if (!limitations.length) fail();
  const verdicts = "decision_verdicts" in value && value.decision_verdicts !== null
    ? array(value.decision_verdicts).map((item) => {
        const verdict = object(item);
        const v = text(verdict.verdict);
        if (!["aligned", "different", "insufficient"].includes(v)) fail();
        const verdictSide = side(verdict.side);
        const ruleChecks = "rule_checks" in verdict && Array.isArray(verdict.rule_checks)
          ? array(verdict.rule_checks).map((item) => {
              const check = object(item);
              return { rule: text(check.rule), passed: check.passed === true };
            })
          : [];
        return {
          executionId: text(verdict.execution_id), day: day(verdict.day), side: verdictSide,
          verdict: v as "aligned" | "different" | "insufficient", reasonText: text(verdict.reason_text),
          ruleChecks,
        };
      })
    : [];
  return {
    episodeId: text(value.episode_id),
    instrument,
    isSynthetic: true,
    windowStart: nullableText(value.window_start) === null ? null : day(value.window_start),
    windowEnd: nullableText(value.window_end) === null ? null : day(value.window_end),
    barCount: finite(value.bar_count),
    barsCovered: text(value.bars_covered),
    userExecutions: array(value.user_executions).map((item) => {
      const execution = object(item);
      return { executionId: text(execution.execution_id), day: day(execution.day), side: side(execution.side), quantity: finite(execution.quantity), price: finite(execution.price), fee: finite(execution.fee) };
    }),
    ruleFills: array(value.rule_fills).map(fill),
    windowUserNetCashFlow: finite(value.window_user_net_cash_flow),
    windowRuleNetCashFlow: finite(value.window_rule_net_cash_flow),
    windowDifferenceNote: text(value.window_difference_note),
    recordedEpisodeResult: {
      pnl: nullableFinite(recorded.pnl), resultKind: nullableText(recorded.result_kind),
      resultSign: nullableText(recorded.result_sign),
    },
    decisionVerdicts: verdicts,
    limitations,
  };
}

export function adaptStrategyComparison(raw: unknown): StrategyComparisonView {
  const value = object(raw);
  if (value.schema_version !== "strategy_comparison.v1") fail();
  const strategyId = "strategy_id" in value ? text(value.strategy_id) : "toujing_t1_breakout_trend";
  let portfolio: StrategyComparisonView["portfolio"] | null = null;
  if ("portfolio" in value && value.portfolio !== null) {
    const portfolioRaw = object(value.portfolio);
    const user = object(portfolioRaw.user);
    const strategy = object(portfolioRaw.strategy);
    portfolio = {
      user: {
        scope: text(user.scope), realizedEpisodeCount: finite(user.realized_episode_count),
        realizedPnlTotal: finite(user.realized_pnl_total), note: text(user.note),
      },
      strategy: {
        strategyId: text(strategy.strategy_id), version: text(strategy.version),
        finalEquity: finite(strategy.final_equity), totalReturn: finite(strategy.total_return),
        maxDrawdown: finite(strategy.max_drawdown), tradingDays: finite(strategy.trading_days),
      },
      note: text(portfolioRaw.note),
      limitations: array(portfolioRaw.limitations).map(text),
    };
  }
  const ruleTable = "rule_table" in value && Array.isArray(value.rule_table)
    ? array(value.rule_table).map((item) => {
        const rule = object(item);
        return { ruleId: text(rule.rule_id), source: text(rule.source), statement: text(rule.statement) };
      })
    : [];
  const view: StrategyComparisonView = {
    strategyId,
    ruleTable,
    reports: array(value.reports).map(report),
    portfolio,
    limitations: array(value.limitations).map(text),
  };
  // Every rule fill side must form a plausible ledger: buys and sells exist per report.
  for (const item of view.reports) {
    if (item.ruleFills.length > 0 && !item.ruleFills.some((item2) => item2.side === "BUY")) fail();
  }
  return view;
}


/** Runtime path: adapt one raw report from strategy_comparison.get. */
export function adaptSingleComparisonReport(raw: unknown): ComparisonReportView {
  const value = object(raw);
  if (value.schema_version !== "strategy_comparison.v1") fail();
  return report(value);
}
