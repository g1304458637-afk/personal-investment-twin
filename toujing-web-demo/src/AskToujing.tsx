import {useEffect, useRef, useState} from 'react';
import {ArrowUpRight, BookOpen, Brain, Calculator, ChartNoAxesCombined, Compass, GitCompareArrows, Search, X} from 'lucide-react';
import type {DemoData} from './model';
import {defaultScope, type ResearchScope} from './alignment';
import './ask-toujing.css';

type Guide = 'scenario' | 'learn' | 'chart' | 'services';
type Props = {
  data: DemoData;
  busy: boolean;
  onQuestion: (question: string, scope: ResearchScope) => void;
  onInvestments: () => void;
  onCareer: () => void;
  onReplay: () => void;
  onMemory: () => void;
  onCompany: () => void;
};

// Adapted from the competition app's AgentCapabilityOverview and
// agentCapabilityCatalog. Keep the six entry points, but describe the services
// this web demo actually has. A link to a page is not an Agent tool.
export function AskToujing({data, busy, onQuestion, onInvestments, onCareer, onReplay, onMemory, onCompany}: Props) {
  const [guide, setGuide] = useState<Guide | null>(null);
  const details = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const actual = data.paths.find(path => path.id === 'actual');
  const company = data.assets.find(asset => asset.ticker === 'sz000333') ?? data.assets[0];
  const scope = defaultScope(data, company.ticker, 'career');
  const showGuide = (next: Guide) => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setGuide(next);
  };
  const closeGuide = () => {setGuide(null); opener.current?.focus({preventScroll: true});};
  useEffect(() => {
    if (!guide) return;
    details.current?.focus({preventScroll: true});
    details.current?.scrollIntoView({block: 'nearest', behavior: 'instant'});
  }, [guide]);

  const cards = [
    {id: 'analyze', icon: ChartNoAxesCombined, title: '看清我的投资',
      benefit: '找到具体亏损的投资，读懂持仓与交易变化。',
      includes: '收益与回撤 · 单轮复盘 · 操作与成本',
      status: '教学档案已载入 · 可按股票复盘', action: '试试这样问', question: true,
      run: () => onQuestion(`复盘我在${company.name}的投资：对照实际成交、持仓与成本变化，找到值得回看的操作，并列出对应记录。`, scope)},
    {id: 'compare', icon: GitCompareArrows, title: '对照过去的自己',
      benefit: '回到同一只股票的不同轮次，逐次看清自己的选择。',
      includes: '同股多轮 · 实际日期 · 加减仓与退出',
      status: '各轮记录可查看 · 并排对比待接入', action: '查看投资经历',
      run: onInvestments},
    {id: 'scenario', icon: Calculator, title: '试算一笔交易',
      benefit: '先看交易会怎样改变现金、仓位和集中度。',
      includes: '买卖数量与价格 · 显式费用 · 前后状态',
      status: '单笔试算尚未接入当前演示', action: '了解试算方式', pending: true,
      run: () => showGuide('scenario')},
    {id: 'research', icon: Search, title: '研究一只股票',
      benefit: '把历史行情、公开事件和经营资料放在一起理解。',
      includes: '历史价格 · 财务报表 · 经营资料与原文',
      status: '本地行情与报告 · 非实时资料', action: '试试这样问', question: true,
      run: () => onQuestion(`研究${company.name}：结合当前已收录的行情、经营资料和财务报告，列出主要发现、原文依据及尚待核对的问题。`, defaultScope(data, company.ticker, 'company'))},
    {id: 'learn', icon: BookOpen, title: '学懂股票知识',
      benefit: '从读懂价格、成本和回撤开始，理解投资里的数字。',
      includes: 'K线 · 成本与仓位 · 回撤 · 收益口径',
      status: '基础指南可读 · AI知识问答待接入', action: '打开知识指南',
      run: () => showGuide('learn')},
    {id: 'chart', icon: Compass, title: '带我看懂图表',
      benefit: '解释图里的数字，定位到对应的投资过程。',
      includes: '投资生涯 · 价格与成交 · 六条路径读法',
      status: '生涯与回放图表可用', action: '打开读图指南',
      run: () => showGuide('chart')},
  ];

  return <section className="ask-view" aria-labelledby="ask-title">
    <div className="ask-overview-heading">
    <div className="ask-context"><span><i className="status-dot"/>林远的教学档案</span><span>{data.dates[0].slice(0, 4)}—{data.dates.at(-1)?.slice(0, 4)} · {actual?.fills.length ?? 0} 笔成交</span></div>
    <header className="ask-intro"><h1 id="ask-title">问投镜</h1><p>聊你的投资，回看历史行情，学懂知识，也带你看懂图表。</p></header>
      <header className="ask-discovery-heading"><h2 id="ask-discovery-title">从看懂数据，到带着依据继续分析。</h2><button className="ask-link" onClick={() => showGuide('services')}>AI与数据服务<ArrowUpRight size={15}/></button></header>
    </div>
    <section className="ask-discovery" aria-labelledby="ask-discovery-title">
      <div className="ask-grid">{cards.map(card => <article className="ask-card" key={card.id} data-capability={card.id}>
        <div className="ask-card-heading"><card.icon size={23} strokeWidth={1.5} aria-hidden="true"/><h3>{card.title}</h3></div>
        <p>{card.benefit}</p><small>{card.includes}</small>
        <div className="ask-card-bottom"><span className={`ask-card-status ${card.pending ? 'is-pending' : ''}`}>{card.status}</span>
          <button className="ask-link" disabled={Boolean(card.question && busy)} onClick={card.run} aria-label={`${card.action}：${card.title}`} aria-expanded={['scenario','learn','chart'].includes(card.id) ? guide === card.id : undefined} aria-controls={['scenario','learn','chart'].includes(card.id) ? 'ask-detail' : undefined}>{card.question && busy ? '研究进行中' : card.action}<ArrowUpRight size={16}/></button>
        </div>
      </article>)}</div>
    </section>
    {guide && <section id="ask-detail" ref={details} tabIndex={-1} className="ask-detail" aria-label={guideTitles[guide]}>
      <header><h2>{guideTitles[guide]}</h2><button className="icon-button" aria-label="收起指南" onClick={closeGuide}><X size={18}/></button></header>
      {guide === 'services' ? <ServiceStatus/> : guide === 'scenario' ? <>
        <p>交易试算先确认标的、买卖方向、数量、价格与费用，再比较交易前后的现金、持仓和集中度。</p>
        <p>当前演示还未接入单笔试算。你可以先在「同场回放」中，查看已有操作与不同规则形成的历史路径。</p>
        <button className="ask-link" onClick={onReplay}>查看同场回放<ArrowUpRight size={15}/></button>
      </> : guide === 'learn' ? <>
        <dl className="ask-guide-list">
          <div><dt>K线：一天的价格范围</dt><dd>实体连接开盘价与收盘价，影线延伸到最高价和最低价。先看图例的涨跌配色，再看价格范围；一根K线不直接说明涨跌原因。</dd></div>
          <div><dt>持仓成本与市场价格</dt><dd>持仓成本来自你的成交与成本核算，市场价格来自行情记录。两者的差额、持有数量和费用共同影响盈亏；成本口径可在投资经历中查看。</dd></div>
          <div><dt>收益、投入与回撤</dt><dd>新投入资金会增加账户资产，但本身不是投资收益。当前生涯页将资产与累计净投入分开，并按净值口径展示回撤。</dd></div>
        </dl><button className="ask-link" onClick={onCareer}>结合投资生涯看一看<ArrowUpRight size={15}/></button>
      </> : <>
        <dl className="ask-guide-list">
          <div><dt>投资生涯：先分清资产和投入</dt><dd>实线显示账户资产，虚线显示累计净投入。点击时间线上的一天，可以查看现金和持仓快照。</dd></div>
          <div><dt>同场回放：先看共同的历史行情</dt><dd>六条路径使用同一段历史行情和资金计划。图中的操作标记可以打开对应记录，再比较各路径的操作与持仓变化。</dd></div>
          <div><dt>投资经历：沿着记录回到当时</dt><dd>从建仓、加仓、减仓到清仓逐笔查看；重新建仓会形成新一轮经历。每笔成交都可以带着日期和证券继续研究。</dd></div>
        </dl><div className="ask-guide-actions"><button className="ask-link" onClick={onCareer}>打开投资生涯<ArrowUpRight size={15}/></button><button className="ask-link" onClick={onReplay}>打开同场回放<ArrowUpRight size={15}/></button></div>
      </>}
    </section>}
    <footer className="ask-footer"><div><span>也可以直接使用</span><button className="ask-link" onClick={onCareer}>投资生涯<ArrowUpRight size={14}/></button><button className="ask-link" onClick={onCompany}>公司研究<ArrowUpRight size={14}/></button><button className="ask-link" onClick={onMemory}><Brain size={14}/>长期记忆<ArrowUpRight size={14}/></button></div><p>示例问题只填入输入框，由你确认发送。当前使用教学档案与本地收录资料。</p></footer>
  </section>;
}

const guideTitles: Record<Guide, string> = {scenario: '交易试算怎样使用', learn: '先读懂这三个概念', chart: '带着问题，回到图上', services: 'AI与数据服务'};

function ServiceStatus() {
  const [status, setStatus] = useState('正在检查本地研究服务…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setStatus('正在检查本地研究服务…');
    fetch('/api/toujing/health', {signal: abort.signal}).then(async response => {
      if (!response.ok) throw new Error('服务状态暂时无法读取');
      const health = await response.json();
      if (!health.available) setStatus('本地研究运行环境暂不可用');
      else if (health.error) setStatus('研究服务曾报告错误，可重新检查后再发起研究');
      else setStatus(health.running ? '本地研究服务正在运行' : '本地研究环境已找到，将在发送问题后启动');
    }).catch(() => {if (!abort.signal.aborted) setStatus('无法连接本地研究服务，请检查演示服务后重试');});
    return () => abort.abort();
  }, [attempt]);
  return <div className="ask-service-status"><p role="status">{status}</p><dl className="ask-guide-list">
    <div><dt>当前可用</dt><dd>林远教学档案、投资经历、本地行情与报告、研究工具、六条路径回放，以及可修订的长期记忆。</dd></div>
    <div><dt>当前研究方式</dt><dd>使用本地工具整理资料与依据。没有调用在线语言模型，也不查询实时行情或网络新闻。</dd></div>
    <div><dt>尚未接入</dt><dd>单笔交易试算、两轮投资并排对比和通用知识问答。基础知识与读图指南可以直接阅读。</dd></div>
  </dl><button className="ask-link" onClick={() => setAttempt(value => value + 1)}>重新检查服务<ArrowUpRight size={15}/></button></div>;
}
