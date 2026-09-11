import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useLocale } from "@/locales/LocaleProvider";
import { useLiquidCopy } from "./liquidCopy";
import { researchStudyCopy } from "./researchStudyCopy";
import { ResearchComparisonStudy } from "./ResearchComparisonStudy";

/** Complete synthetic portfolios, never a cohort relabelled as real professionals. */
export function ProfessionalComparisonWorkspace() {
  const { locale } = useLocale(); const c = researchStudyCopy[locale]; const l = useLiquidCopy();
  return <div className="iw-page research-study-page">
    <Link className="iw-action" to="/analysis"><ArrowLeft size={16} />{l.analysis}</Link>
    <header className="lg-editorial-heading"><span className="iw-kicker">{l.comparison}</span><h1>{l.professionalTitle}</h1><p>{c.professionalIntro}</p></header>
    <ResearchComparisonStudy kind="professional" />
  </div>;
}
