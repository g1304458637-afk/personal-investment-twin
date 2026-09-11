import { ArrowUpRight, ArrowDownUp, History, BriefcaseBusiness } from "lucide-react";
import { Link } from "react-router-dom";
import { useLiquidCopy } from "./liquidCopy";

/** Task navigation, not an analytics adapter. Destination ownership/consent gates are unchanged. */
export function AnalysisWorkspace() {
  const c = useLiquidCopy();
  const cards = [
    { to: "/comparison/history", title: c.selfTitle, detail: c.selfDetail, status: c.gated, Icon: History },
    { to: "/investments/compare-example", title: c.pairTitle, detail: c.pairDetail, status: c.synthetic, Icon: ArrowDownUp },
    { to: "/comparison/professional", title: c.professionalTitle, detail: c.professionalDetail, status: c.professionalStatus, Icon: BriefcaseBusiness },
  ];
  return <div className="iw-page lg-analysis">
    <header className="lg-editorial-heading"><span className="iw-kicker">{c.comparison}</span><h1>{c.compareIntro}</h1><p>{c.compareDescription}</p></header>
    <div className="lg-task-grid lg-task-grid--three">{cards.map(({ to, title, detail, status, Icon }, index) => <Link className="lg-task-card lg-interactive" to={to} key={to}>
      <div className="lg-task-top"><Icon size={25} strokeWidth={1.35} /><span>0{index + 1}</span></div><div><span className="lg-task-status">{status}</span><h2>{title}</h2><p>{detail}</p></div><div className="lg-task-footer"><span>{c.open}</span><ArrowUpRight size={20} /></div>
    </Link>)}</div>
  </div>;
}
