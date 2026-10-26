import type { InvestmentsView, InvestmentEpisodeRowView } from "./investments";
import type { RuntimeAllocation } from "./runtimeService";
import type { LedgerData, LedgerSnapshot, Row } from "./ledger";
import type { InvestmentInput, InvestmentHolding } from "./investmentSharing";

const currencies = new Set(["CNY", "HKD", "USD"]);
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const positive = (value: unknown): value is number => finite(value) && value > 0;
const nonNegative = (value: unknown): value is number => finite(value) && value >= 0;

function day(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const candidate = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate)) return null;
  const [year, month, date] = candidate.split("-").map(Number);
  if (month < 1 || month > 12 || date < 1 || date > new Date(Date.UTC(year, month, 0)).getUTCDate()) return null;
  return candidate;
}

function currency(value: unknown): string | null {
  return typeof value === "string" && currencies.has(value) ? value : null;
}

function safeLabel(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value !== "string") continue;
    const label = value.replace(/[\u0000-\u001f\u007f<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, 120);
    if (label) return label;
  }
  return "未命名标的";
}

function safeCount(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

function episodeInput(row: InvestmentEpisodeRowView, asOf: string, source: InvestmentInput["source"]): InvestmentInput | null {
  const result = row.outcome;
  const resultDate = day(result.result_at) ?? day(row.closedAt) ?? asOf;
  if (result.availability !== "available" || !["realized", "marked"].includes(result.result_kind) || !currency(row.currency)) return null;
  const metrics: InvestmentInput["metrics"] = {};
  if (finite(result.pnl)) metrics.pnl = result.pnl;
  if (finite(result.return_value) && result.return_value >= -1) metrics.returnValue = result.return_value;
  if (metrics.pnl === undefined && metrics.returnValue === undefined) return null;
  return {
    kind: "episode", source, asOf: resultDate, start: day(row.openedAt) ?? undefined,
    ...(day(row.closedAt) ? { end: day(row.closedAt)! } : {}), currency: currency(row.currency)!,
    instrument: safeLabel(row.instrumentId, row.displayName), status: row.status, holdings: [], metrics,
    returnBasis: metrics.returnValue === undefined ? "unavailable" : "episode_cost", pnlBasis: "episode",
    definitions: [result.result_kind === "marked"
      ? "单次投资经历结果为持仓估值，属于持有中结果，不是已实现收益。"
      : "单次投资经历结果来自已记录的已实现结果；此指标不代表整个账户的期间表现。"],
  };
}

function viewHoldings(view: InvestmentsView, asOf: string, source: InvestmentInput["source"]): InvestmentInput | null {
  const open = view.openEpisodes;
  if (!open.length) return null;
  const dates = open.map(row => day(row.valuationAt));
  const currenciesInRows = open.map(row => currency(row.currency));
  const oneDate = dates[0] !== null && dates.every(value => value === dates[0]);
  const oneCurrency = currenciesInRows[0] !== null && currenciesInRows.every(value => value === currenciesInRows[0]);
  if (!oneCurrency) return null;
  const validValues = open.every(row => nonNegative(row.marketValue));
  const actualAsOf = oneDate ? dates[0]! : asOf;
  const total = validValues ? open.reduce((sum, row) => sum + row.marketValue!, 0) : 0;
  const canWeight = oneDate && oneCurrency && validValues && total > 0;
  const holdings: InvestmentHolding[] = open.map(row => ({
    name: safeLabel(row.instrumentId, row.displayName),
    ...(nonNegative(row.marketValue) ? { marketValue: row.marketValue } : {}),
    ...(canWeight ? { weight: row.marketValue! / total } : {}),
  }));
  const definitions = [source === "synthetic"
    ? "合成数据账户的当前持仓快照；只含持有中的证券，不含现金。"
    : "本地账户的当前持仓快照；只含持有中的证券，不含现金。"];
  if (!oneDate) definitions.push("持仓估值日期不一致，未计算仓位比例。"
  );
  if (!oneCurrency) definitions.push("持仓币种不一致或未知，未合并计算仓位比例。");
  if (!validValues) definitions.push("至少一项持仓缺少有效市值，未计算仓位比例；缺失金额没有补成零。");
  if (oneDate && oneCurrency && validValues && total <= 0) definitions.push("证券市值合计为零，未计算仓位比例。");
  return {
    kind: "holdings", source, asOf: actualAsOf, currency: currenciesInRows[0]!,
    holdings, metrics: { holdingCount: open.length }, returnBasis: "unavailable", pnlBasis: "user_reported", definitions,
  };
}

function allocationHoldings(allocation: RuntimeAllocation, asOf: string): InvestmentInput | null {
  if (!Array.isArray(allocation.positions) || allocation.positions.length === 0) return null;
  const currenciesInRows = allocation.positions.map(position => currency(position.currency));
  const oneCurrency = currenciesInRows[0] !== null && currenciesInRows.every(value => value === currenciesInRows[0]);
  if (!oneCurrency) return null;
  const dates = allocation.positions.map(position => position.as_of == null ? null : day(position.as_of));
  const oneDate = dates[0] !== null && dates.every(value => value === dates[0]);
  const allMarketValues = allocation.positions.every(position => nonNegative(position.market_value));
  const allWeights = allocation.positions.every(position => finite(position.weight) && position.weight >= 0 && position.weight <= 1);
  const canShareWeights = oneDate && allMarketValues && allWeights;
  const holdings: InvestmentHolding[] = allocation.positions.map(position => ({
    name: safeLabel(position.instrument_id, position.display_name),
    ...(nonNegative(position.market_value) ? { marketValue: position.market_value } : {}),
    ...(canShareWeights ? { weight: position.weight! } : {}),
  }));
  const definitions = ["持仓比例来自本地账户的证券配置结果，分母为有可用估值的证券市值，不含现金。"];
  if (allocation.skipped_no_market_value > 0) definitions.push("部分证券因缺少市值而未纳入配置结果，比例仅覆盖可估值证券。");
  if (!allMarketValues) definitions.push("至少一项证券市值缺失或无效，未展示任何仓位比例；金额缺失没有补成零。");
  if (!allWeights) definitions.push("配置结果中的比例不完整或无效，未展示任何仓位比例。");
  if (!oneDate) definitions.push("持仓估值日期缺失或不一致，未展示任何仓位比例；卡片日期采用账户快照日期。");
  if (!oneCurrency) definitions.push("持仓币种不一致或未知；金额不应跨币种比较。");
  return {
    kind: "holdings", source: "local_account", asOf: oneDate ? dates[0]! : asOf,
    currency: currenciesInRows[0]!, holdings,
    metrics: { holdingCount: allocation.positions.length }, returnBasis: "unavailable", pnlBasis: "user_reported", definitions,
  };
}

export function investmentInputsFromView(
  view: InvestmentsView,
  allocation: RuntimeAllocation | null,
  expectedSubjectId: string,
): InvestmentInput[] {
  if (!expectedSubjectId || view.subjectId !== expectedSubjectId) throw new Error("investment_share_subject_mismatch");
  if (view.portfolioState.status !== "available") throw new Error("investment_share_portfolio_unavailable");
  const asOf = day(view.asOf);
  if (!asOf) throw new Error("investment_share_invalid_as_of");
  const source: InvestmentInput["source"] = view.dataTier === "synthetic" ? "synthetic" : "local_account";
  const rows = [...view.openEpisodes, ...view.closedEpisodes];
  if (rows.some(row => row.subjectId !== expectedSubjectId)) throw new Error("investment_share_subject_mismatch");
  if (view.dataTier === "synthetic" && rows.some(row => !row.isSynthetic)) throw new Error("investment_share_source_mismatch");
  if (view.dataTier === "authorized_beta" && rows.some(row => row.isSynthetic)) throw new Error("investment_share_source_mismatch");
  const result = rows.map(row => episodeInput(row, asOf, source)).filter((item): item is InvestmentInput => item !== null);
  const holdings = source === "local_account" && allocation
    ? allocationHoldings(allocation, asOf)
    : viewHoldings(view, asOf, source);
  if (holdings) result.push(holdings);
  const opened = rows.map(row => day(row.openedAt)).filter((value): value is string => value !== null).sort();
  const closedCount = rows.filter(row => row.status === "closed").length;
  const holdingCount = safeCount(view.summary.currentPositionCount);
  result.push({
    kind: "period", source, asOf, ...(opened[0] ? { start: opened[0] } : {}), end: asOf,
    currency: currency(rows[0]?.currency) ?? "CNY", holdings: [],
    metrics: { ...(holdingCount === undefined ? {} : { holdingCount }), closedCount },
    returnBasis: "unavailable", pnlBasis: "user_reported",
    definitions: ["账户投资经历统计；当前数据没有可分享的全账户期间收益率或最大回撤。"],
  });
  return result;
}

function ledgerSnapshot(data: LedgerData, subject: string, account: string): LedgerSnapshot {
  if (data.subject_id !== subject || data.account_id !== account) throw new Error("investment_share_account_mismatch");
  if (data.enabled !== true || !data.snapshot) throw new Error("investment_share_ledger_unavailable");
  const snapshot = data.snapshot;
  if (!currency(snapshot.currency)) throw new Error("investment_share_currency_unavailable");
  if (snapshot.status === "invalid" || !["available", "needs_attention"].includes(String(snapshot.status)) || !Array.isArray(snapshot.errors) || snapshot.errors.length > 0) {
    throw new Error("investment_share_ledger_invalid");
  }
  if (!Array.isArray(snapshot.positions) || !Array.isArray(snapshot.episodes)) throw new Error("investment_share_ledger_invalid");
  if (snapshot.positions.some(position => position.currency !== undefined && position.currency !== null && position.currency !== snapshot.currency)) {
    throw new Error("investment_share_currency_mismatch");
  }
  return snapshot;
}

function ledgerPeriod(data: LedgerData, snapshot: LedgerSnapshot): InvestmentInput {
  const asOf = day(snapshot.as_of);
  if (!asOf) throw new Error("investment_share_invalid_as_of");
  const profile = data.profile;
  const start = day(profile?.opening_date);
  const currencyCode = currency(snapshot.currency) ?? "CNY";
  const metrics: InvestmentInput["metrics"] = {};
  if (finite(snapshot.period_pnl)) metrics.pnl = snapshot.period_pnl;
  if (finite(snapshot.equity)) metrics.equity = snapshot.equity;
  if (finite(snapshot.net_contributions)) metrics.netContributions = snapshot.net_contributions;
  metrics.holdingCount = snapshot.positions.filter(position => positive(position.quantity)).length;
  metrics.closedCount = snapshot.episodes.filter(episode => day(episode.closed_at) !== null).length;
  return {
    kind: "period", source: "local_account", asOf, ...(start ? { start } : {}), end: asOf,
    currency: currencyCode, holdings: [], metrics, returnBasis: "unavailable",
    pnlBasis: finite(snapshot.period_pnl) ? "period" : "user_reported",
    definitions: ["账期盈亏、期末资产和净投入来自本地账本原值；未从资产变化推算收益率或最大回撤。", "总资产曲线可能包含外部资金流；当前没有可分享的时间加权收益率或最大回撤。"],
  };
}

function ledgerHoldings(snapshot: LedgerSnapshot): InvestmentInput {
  const asOf = day(snapshot.as_of);
  if (!asOf) throw new Error("investment_share_invalid_as_of");
  const rows = snapshot.positions.filter(position => positive(position.quantity));
  const valuesValid = rows.every(position => nonNegative(position.market_value));
  const total = valuesValid ? rows.reduce((sum, position) => sum + Number(position.market_value), 0) : 0;
  const canWeight = rows.length > 0 && valuesValid && total > 0;
  const holdings: InvestmentHolding[] = rows.map(position => ({
    name: safeLabel(position.symbol),
    ...(nonNegative(position.market_value) ? { marketValue: position.market_value as number } : {}),
    ...(canWeight ? { weight: (position.market_value as number) / total } : {}),
  }));
  const definitions = ["当前本地账本持仓快照；仓位比例分母为所有正持仓的证券市值之和，不含现金。"];
  if (!valuesValid) definitions.push("至少一项持仓缺少有效估值，未计算任何仓位比例；缺失金额没有补成零。");
  if (valuesValid && total <= 0) definitions.push("证券市值合计为零，未计算仓位比例。");
  return {
    kind: "holdings", source: "local_account", asOf, currency: currency(snapshot.currency) ?? "CNY",
    holdings, metrics: { holdingCount: rows.length }, returnBasis: "unavailable", pnlBasis: "user_reported", definitions,
  };
}

function ledgerEpisode(snapshot: LedgerSnapshot, episode: Row, asOf: string): InvestmentInput | null {
  const start = day(episode.opened_at);
  const end = day(episode.closed_at);
  const realizedPnl = finite(episode.realized_pnl) ? episode.realized_pnl : undefined;
  const status = episode.status === "closed" ? "closed" : episode.status === "open" ? "open" : null;
  if (!status || !start) return null;
  const metrics: InvestmentInput["metrics"] = {};
  if (realizedPnl !== undefined) metrics.pnl = realizedPnl;
  return {
    kind: "episode", source: "local_account", asOf: end ?? asOf, start, ...(end ? { end } : {}),
    currency: currency(snapshot.currency) ?? "CNY", instrument: safeLabel(episode.symbol), status,
    holdings: [], metrics, returnBasis: "unavailable", pnlBasis: "realized",
    definitions: [status === "open"
      ? "此经历只展示账本已记录的已实现盈亏；持有中浮盈未合并，也没有单次经历收益率。"
      : "此经历只展示账本已记录的已实现盈亏；没有从成本或账户资产变化推算收益率。"],
  };
}

export function investmentInputsFromLedger(
  data: LedgerData,
  subject: string,
  account: string,
  episodeId?: string,
): InvestmentInput[] {
  const snapshot = ledgerSnapshot(data, subject, account);
  const asOf = day(snapshot.as_of);
  if (!asOf) throw new Error("investment_share_invalid_as_of");
  const selected = episodeId === undefined ? snapshot.episodes : snapshot.episodes.filter(episode => episode.episode_id === episodeId);
  if (episodeId !== undefined && selected.length !== 1) throw new Error("investment_share_episode_unavailable");
  const episodes = selected.map(episode => ledgerEpisode(snapshot, episode, asOf)).filter((item): item is InvestmentInput => item !== null);
  if (episodeId !== undefined) return episodes;
  return [ledgerHoldings(snapshot), ledgerPeriod(data, snapshot), ...episodes];
}
