import { BriefcaseBusiness, Clock3, LockKeyhole } from 'lucide-react';
import type { InvestmentKind, InvestmentSource, PublishedInvestmentCard } from '@/data/investmentSharing';

export const investmentKindLabels: Record<InvestmentKind, string> = { episode: '一轮投资复盘', holdings: '持仓组合快照', period: '阶段投资报告' };
export const investmentSourceLabels: Record<InvestmentSource, string> = { synthetic: '演示数据', local_account: '本机账户生成', user_reported: '个人提供 · 未核验' };
const percent = (value: number) => `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`;

export function InvestmentShareCard({ card, compact = false }: { card: PublishedInvestmentCard; compact?: boolean }) {
  const money = (value: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: card.currency, maximumFractionDigits:2 }).format(value);
  const metrics: [string, string][] = [];
  const m = card.metrics;
  if (card.disclosure.performance && card.kind !== 'holdings') {
    metrics.push([card.kind === 'episode' ? '本轮收益率' : '期间收益率', m.returnValue === undefined ? '未提供' : percent(m.returnValue)]);
    if (card.kind === 'period') metrics.push(['最大回撤', m.maxDrawdown === undefined ? '未提供' : percent(m.maxDrawdown)]);
  }
  if (m.pnl !== undefined) metrics.push([card.pnlBasis === 'realized' ? '账面已实现盈亏' : card.pnlBasis === 'period' ? '本账期盈亏' : '盈亏金额', money(m.pnl)]);
  if (m.equity !== undefined) metrics.push(['资产金额', money(m.equity)]);
  if (m.netContributions !== undefined) metrics.push(['净投入', money(m.netContributions)]);
  if (m.holdingCount !== undefined) metrics.push(['持仓项目', String(m.holdingCount)]);
  if (m.closedCount !== undefined) metrics.push(['已结束经历', String(m.closedCount)]);
  const visibleHoldings = compact ? card.holdings.slice(0,3) : card.holdings;
  return <section className={`cm-investment-card ${compact ? 'is-compact' : ''}`} aria-label="投资分享数据卡">
    <div className="cm-investment-card-title"><BriefcaseBusiness size={17}/><strong>{investmentKindLabels[card.kind]}</strong><span className={`cm-state-tag ${card.source === 'user_reported' ? 'is-caution' : ''}`}>{investmentSourceLabels[card.source]}</span></div>
    <div className="cm-investment-card-context">{card.instrument && <span>{card.instrument}</span>}{card.status && <span>{card.status === 'open' ? '持有中' : '已结束'}</span>}{card.asOf ? <span><Clock3 size={11}/>截至 {card.asOf}</span> : <span>日期已隐藏</span>}{card.start && <span>{card.start} → {card.end || card.asOf || '未提供'}</span>}</div>
    {!!metrics.length && <dl className="cm-investment-metrics">{metrics.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
    {!!visibleHoldings.length && <div className="cm-shared-holdings">{visibleHoldings.map((h,i) => <div key={i}><span>{h.name}</span>{h.weight !== undefined && <><span className="cm-holding-bar"><i style={{width:`${h.weight*100}%`}}/></span><strong>{(h.weight*100).toFixed(1)}%</strong></>}{h.marketValue !== undefined && <small>{money(h.marketValue)}</small>}</div>)}{compact && card.holdings.length > 3 && <small>另有 {card.holdings.length-3} 项，打开查看完整分享</small>}</div>}
    <div className="cm-investment-boundary"><LockKeyhole size={12}/><span>{card.disclosure.names ? '已展示标的名称' : '标的名称已隐藏'} · {card.disclosure.amounts ? '已展示所选金额' : '资金金额已隐藏'}</span></div>
    {!compact && <div className="cm-investment-definitions"><strong>数据口径</strong>{card.definitions.map((d,i) => <p key={i}>{d}</p>)}{card.metrics.returnValue !== undefined && <p>收益口径：{({ episode_cost:'本轮投资成本口径',time_weighted:'时间加权口径',user_reported:'提供者填写，未经核验',unavailable:'未提供可核验收益口径' })[card.returnBasis]}。</p>}{card.source === 'local_account' && <p>本机账户记录生成，不代表券商或第三方认证。</p>}</div>}
  </section>;
}
