export type InvestmentKind = 'episode' | 'holdings' | 'period';
export type InvestmentSource = 'synthetic' | 'local_account' | 'user_reported';
export interface InvestmentDisclosure { names: boolean; weights: boolean; performance: boolean; amounts: boolean; dates: boolean; counts?: boolean }
export interface InvestmentMetrics { returnValue?: number; maxDrawdown?: number; pnl?: number; equity?: number; netContributions?: number; holdingCount?: number; closedCount?: number }
export interface InvestmentHolding { name: string; weight?: number; marketValue?: number }
export interface InvestmentInput {
  kind: InvestmentKind; source: InvestmentSource; asOf: string; start?: string; end?: string;
  currency: string; instrument?: string; status?: 'open' | 'closed'; holdings: InvestmentHolding[];
  metrics: InvestmentMetrics; returnBasis: 'episode_cost' | 'time_weighted' | 'user_reported' | 'unavailable';
  pnlBasis: 'period' | 'episode' | 'realized' | 'user_reported'; definitions: string[];
}
export interface PublishedInvestmentCard {
  schema: 'toujing-investment-share'; version: 1; kind: InvestmentKind; source: InvestmentSource;
  currency: string; asOf?: string; start?: string; end?: string; instrument?: string;
  status?: 'open' | 'closed'; holdings: InvestmentHolding[]; metrics: InvestmentMetrics;
  returnBasis: InvestmentInput['returnBasis']; pnlBasis: InvestmentInput['pnlBasis'];
  definitions: string[]; disclosure: InvestmentDisclosure;
}

export const defaultInvestmentDisclosure = (): InvestmentDisclosure => ({ names: false, weights: true, performance: true, amounts: false, dates: true, counts: true });

const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
const keysOnly = (v: Record<string, unknown>, keys: readonly string[]) => Object.keys(v).every(k => keys.includes(k));
const nonblank = (v: unknown, max = 240): v is string => typeof v === 'string' && v.trim().length > 0 && v.length <= max;
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const optional = (v: unknown, test: (x: unknown) => boolean) => v === undefined || test(v);
const choice = (v: unknown, values: readonly string[]) => typeof v === 'string' && values.includes(v);
const date = (v: unknown): v is string => {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const [year, month, day] = v.split('-').map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const last = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  return day <= last;
};
const disclosureKeys = ['names', 'weights', 'performance', 'amounts', 'dates', 'counts'] as const;
const metricKeys = ['returnValue', 'maxDrawdown', 'pnl', 'equity', 'netContributions', 'holdingCount', 'closedCount'] as const;
const holdingKeys = ['name', 'weight', 'marketValue'] as const;
const cardKeys = ['schema', 'version', 'kind', 'source', 'currency', 'asOf', 'start', 'end', 'instrument', 'status', 'holdings', 'metrics', 'returnBasis', 'pnlBasis', 'definitions', 'disclosure'] as const;
const disclosureValid = (v: unknown): v is InvestmentDisclosure => object(v) && keysOnly(v, disclosureKeys) &&
  disclosureKeys.filter(k => k !== 'counts').every(k => typeof v[k] === 'boolean') && optional(v.counts, x => typeof x === 'boolean');
const metricsValid = (v: unknown, exact: boolean): v is InvestmentMetrics => object(v) && (!exact || keysOnly(v, metricKeys)) &&
  metricKeys.every(k => optional(v[k], finite)) &&
  optional(v.returnValue, x => finite(x) && x >= -1) &&
  optional(v.maxDrawdown, x => finite(x) && x >= -1 && x <= 0) &&
  ['holdingCount', 'closedCount'].every(k => optional(v[k], x => Number.isSafeInteger(x) && (x as number) >= 0));
const holdingsValid = (v: unknown, exact: boolean): v is InvestmentHolding[] => Array.isArray(v) && v.length <= 100 && v.every(h => object(h) &&
  (!exact || keysOnly(h, holdingKeys)) && nonblank(h.name, 120) &&
  optional(h.weight, x => finite(x) && x >= 0 && x <= 1) && optional(h.marketValue, x => finite(x) && x >= 0)) &&
  v.reduce((sum: number, h: InvestmentHolding) => sum + (h.weight ?? 0), 0) <= 1 + 1e-6;
const definitionsValid = (v: unknown): v is string[] => Array.isArray(v) && v.length <= 20 && v.every(x => nonblank(x, 500));
const datesValid = (v: Record<string, unknown>, requireAsOf: boolean) =>
  (requireAsOf ? date(v.asOf) : optional(v.asOf, date)) && optional(v.start, date) && optional(v.end, date) &&
  (v.start === undefined || v.end === undefined || (v.start as string) <= (v.end as string)) &&
  (v.start === undefined || v.asOf === undefined || (v.start as string) <= (v.asOf as string)) &&
  (v.end === undefined || v.asOf === undefined || (v.end as string) <= (v.asOf as string));
const commonValid = (v: Record<string, unknown>, exact: boolean, requireAsOf: boolean) =>
  choice(v.kind, ['episode', 'holdings', 'period']) && choice(v.source, ['synthetic', 'local_account', 'user_reported']) &&
  choice(v.currency, ['CNY', 'HKD', 'USD']) && datesValid(v, requireAsOf) &&
  optional(v.instrument, x => nonblank(x, 120)) && optional(v.status, x => choice(x, ['open', 'closed'])) &&
  holdingsValid(v.holdings, exact) && metricsValid(v.metrics, exact) &&
  choice(v.returnBasis, ['episode_cost', 'time_weighted', 'user_reported', 'unavailable']) &&
  choice(v.pnlBasis, ['period', 'episode', 'realized', 'user_reported']) && definitionsValid(v.definitions);

export function validatePublishedInvestmentCard(value: unknown): value is PublishedInvestmentCard {
  if (!object(value) || !keysOnly(value, cardKeys) || value.schema !== 'toujing-investment-share' || value.version !== 1 || !disclosureValid(value.disclosure) || !commonValid(value, true, value.disclosure.dates)) return false;
  const d = value.disclosure;
  if (!d.dates && ['asOf', 'start', 'end'].some(k => k in value)) return false;
  if (!d.names && ('instrument' in value || (value.holdings as InvestmentHolding[]).some((h, i) => h.name !== `持仓 ${i + 1}`))) return false;
  if (!d.weights && (value.holdings as InvestmentHolding[]).some(h => 'weight' in h)) return false;
  if (!d.amounts && (['pnl', 'equity', 'netContributions'].some(k => k in (value.metrics as object)) || (value.holdings as InvestmentHolding[]).some(h => 'marketValue' in h))) return false;
  if (!d.performance && ['returnValue', 'maxDrawdown'].some(k => k in (value.metrics as object))) return false;
  if (d.counts === false && ['holdingCount', 'closedCount'].some(k => k in (value.metrics as object))) return false;
  return true;
}

export function projectInvestmentShare(input: InvestmentInput, disclosure: InvestmentDisclosure): PublishedInvestmentCard {
  if (!object(input) || !commonValid(input, false, true) || !disclosureValid(disclosure)) throw new Error('投资分享数据或公开范围无效');
  const metrics: InvestmentMetrics = {};
  const copy = (key: keyof InvestmentMetrics) => { const value = input.metrics[key]; if (value !== undefined) metrics[key] = value; };
  if (disclosure.performance) { copy('returnValue'); copy('maxDrawdown'); }
  if (disclosure.amounts) { copy('pnl'); copy('equity'); copy('netContributions'); }
  if (disclosure.counts !== false) { copy('holdingCount'); copy('closedCount'); }
  const card: PublishedInvestmentCard = {
    schema: 'toujing-investment-share', version: 1, kind: input.kind, source: input.source, currency: input.currency,
    holdings: input.holdings.map((h, i) => ({ name: disclosure.names ? h.name.trim() : `持仓 ${i + 1}`,
      ...(disclosure.weights && h.weight !== undefined ? { weight: h.weight } : {}),
      ...(disclosure.amounts && h.marketValue !== undefined ? { marketValue: h.marketValue } : {}) })),
    metrics, returnBasis: input.returnBasis, pnlBasis: input.pnlBasis, definitions: input.definitions.map(x => x.trim()),
    disclosure: { names: disclosure.names, weights: disclosure.weights, performance: disclosure.performance, amounts: disclosure.amounts, dates: disclosure.dates, counts: disclosure.counts !== false },
    ...(disclosure.names && input.instrument !== undefined ? { instrument: input.instrument.trim() } : {}),
    ...(input.status !== undefined ? { status: input.status } : {}),
    ...(disclosure.dates ? { asOf: input.asOf, ...(input.start !== undefined ? { start: input.start } : {}), ...(input.end !== undefined ? { end: input.end } : {}) } : {}),
  };
  if (!validatePublishedInvestmentCard(card)) throw new Error('投资分享数据无法通过公开校验');
  return card;
}

const maxImportBytes = 512 * 1024;
const checkSize = (text: string) => { if (new TextEncoder().encode(text).length > maxImportBytes) throw new Error('文件超过 512 KiB 限制'); };

function csvRows(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = []; let field = ''; let quoted = false; let afterQuote = false; let fieldStarted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; afterQuote = true; }
      else field += c;
    } else if (afterQuote) {
      if (c === ',') { row.push(field); field = ''; afterQuote = false; fieldStarted = false; }
      else if (c === '\n' || c === '\r') { row.push(field); rows.push(row); row = []; field = ''; afterQuote = false; fieldStarted = false; if (c === '\r' && text[i + 1] === '\n') i++; }
      else throw new Error('CSV 引号后存在无效字符');
    } else if (c === '"') {
      if (fieldStarted || field !== '') throw new Error('CSV 引号位置无效');
      quoted = true; fieldStarted = true;
    } else if (c === ',') { row.push(field); field = ''; fieldStarted = false; }
    else if (c === '\n' || c === '\r') { row.push(field); rows.push(row); row = []; field = ''; fieldStarted = false; if (c === '\r' && text[i + 1] === '\n') i++; }
    else { field += c; fieldStarted = true; }
  }
  if (quoted) throw new Error('CSV 引号未闭合');
  if (field !== '' || fieldStarted || afterQuote || row.length) { row.push(field); rows.push(row); }
  return rows;
}

const parseDecimal = (raw: string) => {
  const trimmed = raw.trim();
  if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(trimmed)) throw new Error('CSV 数值为空或无效');
  const value = Number(trimmed);
  if (!Number.isFinite(value)) throw new Error('CSV 数值无效');
  return value;
};

export function parseInvestmentFile(text: string, format: 'json' | 'csv'): InvestmentInput {
  checkSize(text);
  if (format === 'json') {
    let value: unknown;
    try { value = JSON.parse(text.replace(/^\uFEFF/, '')); } catch { throw new Error('JSON 文件无效'); }
    if (!validatePublishedInvestmentCard(value)) throw new Error('JSON 必须是有效的投镜投资分享卡片');
    if (value.asOf === undefined) throw new Error('此文件未包含数据日期，不能作为投资记录导入；请在导出时保留数据日期。');
    return { kind: value.kind, source: 'user_reported', asOf: value.asOf,
      ...(value.start !== undefined ? { start: value.start } : {}), ...(value.end !== undefined ? { end: value.end } : {}),
      currency: value.currency, ...(value.instrument !== undefined ? { instrument: value.instrument } : {}),
      ...(value.status !== undefined ? { status: value.status } : {}), holdings: value.holdings.map(h => ({ name: h.name,
        ...(h.weight !== undefined ? { weight: h.weight } : {}), ...(h.marketValue !== undefined ? { marketValue: h.marketValue } : {}) })),
      metrics: { ...value.metrics }, returnBasis: value.metrics.returnValue !== undefined ? 'user_reported' : 'unavailable',
      pnlBasis: 'user_reported',
      definitions: ['个人分享文件导入，数据由提供者填写，未经券商核验；原文件的说明与核验声明未继承。'] };
  }
  if (format !== 'csv') throw new Error('不支持的文件格式');
  const rows = csvRows(text.replace(/^\uFEFF/, ''));
  if (rows.length < 2 || rows.length > 101) throw new Error('CSV 需要 1 到 100 行持仓');
  const headers = rows[0].map(x => x.trim());
  const allowed = ['name', 'weight_percent', 'market_value', 'currency', 'as_of'];
  if (headers.length !== new Set(headers).size || !headers.every(x => allowed.includes(x)) || !['name', 'weight_percent', 'currency', 'as_of'].every(x => headers.includes(x))) throw new Error('CSV 表头无效');
  const cells = rows.slice(1).map(row => {
    if (row.length !== headers.length) throw new Error('CSV 行列数不一致');
    return Object.fromEntries(headers.map((h, i) => [h, row[i].trim()]));
  });
  const currency = cells[0].currency; const asOf = cells[0].as_of;
  if (!choice(currency, ['CNY', 'HKD', 'USD']) || !date(asOf)) throw new Error('CSV 币种或日期无效');
  const holdings = cells.map(cell => {
    if (!nonblank(cell.name, 120) || cell.currency !== currency || cell.as_of !== asOf) throw new Error('CSV 持仓、币种或日期无效');
    const percent = parseDecimal(cell.weight_percent);
    if (percent < 0 || percent > 100) throw new Error('CSV 仓位比例超出范围');
    return { name: cell.name, weight: percent / 100,
      ...(cell.market_value !== undefined && cell.market_value !== '' ? { marketValue: parseDecimal(cell.market_value) } : {}) };
  });
  if (!holdingsValid(holdings, true)) throw new Error('CSV 仓位总和超出 100%');
  return { kind: 'holdings', source: 'user_reported', asOf, currency, holdings, metrics: { holdingCount: holdings.length },
    returnBasis: 'unavailable', pnlBasis: 'user_reported', definitions: ['个人文件导入，未经券商核验；仓位按文件中的百分比展示，不含未提供的现金。'] };
}

export const holdingsCsvTemplate = 'name,weight_percent,market_value,currency,as_of\r\n虚构资产 A（SYNTHETIC）,60,,CNY,2026-01-01\r\n';

export function exampleInvestmentInputs(): InvestmentInput[] {
  return [
    { kind: 'episode', source: 'synthetic', asOf: '2026-01-15', start: '2025-02-03', end: '2026-01-15', currency: 'CNY', instrument: '宁德时代（SYNTHETIC）', status: 'closed', holdings: [], metrics: { returnValue: 0.086, pnl: 860, closedCount: 1 }, returnBasis: 'episode_cost', pnlBasis: 'episode', definitions: ['SYNTHETIC 虚构持仓经历；收益率按示例成本计算，盈亏为示例期间金额。'] },
    { kind: 'holdings', source: 'synthetic', asOf: '2026-01-15', currency: 'CNY', holdings: [{ name: '虚构资产 A（SYNTHETIC）', weight: 0.6, marketValue: 6000 }, { name: '虚构资产 B（SYNTHETIC）', weight: 0.25, marketValue: 2500 }, { name: '虚构现金（SYNTHETIC）', weight: 0.15, marketValue: 1500 }], metrics: { equity: 10000, holdingCount: 3 }, returnBasis: 'unavailable', pnlBasis: 'user_reported', definitions: ['SYNTHETIC 虚构持仓快照；权重以示例总资产为分母。'] },
    { kind: 'period', source: 'synthetic', asOf: '2026-01-15', start: '2025-01-01', end: '2025-12-31', currency: 'CNY', holdings: [], metrics: { returnValue: 0.123, maxDrawdown: -0.091, pnl: 1230, equity: 11230, netContributions: 10000 }, returnBasis: 'time_weighted', pnlBasis: 'period', definitions: ['SYNTHETIC 虚构年度表现；收益率为时间加权示例，最大回撤按示例净值峰谷计算。'] },
  ];
}
