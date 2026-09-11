import { ArrowUpRight, BookOpen, ChartNoAxesCombined, Compass, Search, GitCompareArrows, Calculator } from "lucide-react";
import { Link } from "react-router-dom";
import { capabilityCatalog, capabilityStatus, capabilityScopeTarget, type AgentServices } from "./agentCapabilityCatalog";

const icons = [ChartNoAxesCombined, GitCompareArrows, Calculator, Search, BookOpen, Compass];
export function AgentCapabilityOverview({ locale, services, busy, onQuestion, canCompose = true }: {
  locale: string; services: AgentServices; busy: boolean; onQuestion: (question: string) => void; canCompose?: boolean;
}) {
  const zh = locale === "zh-CN"; const lang = zh ? "zh" : "en";
  return <section className="agent-discovery" aria-labelledby="agent-discovery-title">
    <header><div><p>{zh ? "你的投资研究伙伴" : "YOUR INVESTMENT RESEARCH COMPANION"}</p>
      <h2 id="agent-discovery-title">{zh ? "从看懂数据，到带着依据继续分析。" : "Understand your data. Explore the evidence."}</h2></div>
      <Link to="/settings">{zh ? "AI与数据服务" : "AI & data services"}<ArrowUpRight size={14}/></Link></header>
    <div className="agent-discovery__grid">{capabilityCatalog.map((item, index) => {
      const Icon = icons[index];
      const scopeTarget = capabilityScopeTarget(item.needs, services);
      return <article key={item.id}>
        <div className="agent-discovery__card-heading"><Icon size={18} strokeWidth={1.5} aria-hidden="true"/><h3>{item.title[lang]}</h3></div>
        <p>{item.benefit[lang]}</p><small>{item.includes[lang]}</small>
        <span className="agent-discovery__status">{canCompose ? capabilityStatus(item.needs, services, zh)
          : (zh ? "选择账户后检查服务状态" : "Select an account to check services")}</span>
        {!canCompose ? <Link to="/data">{zh ? "先选择账户或示例" : "Choose an account or example"}<ArrowUpRight size={14}/></Link>
          : scopeTarget ? <Link to={scopeTarget}>{scopeTarget === "/ask" ? (zh ? "切换到整个账户" : "Use whole account") : (zh ? "前往选择示例账户" : "Choose an example account")}<ArrowUpRight size={14}/></Link>
          : <button type="button" disabled={busy} onClick={() => onQuestion(item.prompt[lang])}>
            {zh ? "试试这样问" : "Try a question"}<ArrowUpRight size={14}/><span className="sr-only">{item.prompt[lang]}</span>
          </button>}
      </article>;
    })}</div>
    <div className="agent-discovery__next"><span>{zh ? "也可以直接使用" : "Also in Toujing"}</span>
      <Link to="/pretrade">{zh ? "决策准备 · 计算交易前后变化" : "Decision preparation · Before / after"}<ArrowUpRight size={13}/></Link>
      <Link to="/analysis">{zh ? "三个对比工作区" : "Three comparison workspaces"}<ArrowUpRight size={13}/></Link>
      <small>{zh ? "专业人员全盘对比在对比工作区查看；尚未接入对话。策略方法库仍在规划。" : "Professional portfolio comparisons live in the comparison workspace, not in chat yet. The strategy Lens Library is planned."}</small>
    </div>
    <p className="agent-discovery__footnote">{zh ? "示例问题只填入输入框，由你确认发送。服务状态表示本机配置，具体资料以每次查询结果为准。" : "Examples fill the composer; you decide when to send. Status reflects local setup; source availability is checked on each query."}</p>
  </section>;
}
