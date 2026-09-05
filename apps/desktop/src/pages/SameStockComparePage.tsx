import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import generated from "@/generated/backend-demo-evidence.json";
import { adaptSameStock } from "@/data/sameStock";
import { SameStockComparisonPanel } from "@/components/review/SameStockComparisonPanel";
import { DecisionAnalysisWorkspace } from "@/components/review/DecisionAnalysisWorkspace";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/locales/LocaleProvider";


export function SameStockComparePage() {
  const [search] = useSearchParams();
  const { t } = useLocale();
  const view = useMemo(() => adaptSameStock(generated.same_stock_compare_demo), []);
  const [focusedDecisionId, setFocusedDecisionId] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (search.get("focus") === "analysis") document.querySelector("[data-decision-analysis]")?.scrollIntoView({ block: "start", behavior: "smooth" }); }, [search]);
  return <div className="page space-y-5">
    <Button asChild variant="quiet"><Link to="/investments">← {t("My Investments")}</Link></Button>
    <p className="text-sm text-warning">{t("Dedicated comparison example · Synthetic · not your account")}</p>
    <h1 className="text-2xl">{t("Same stock, different investment paths")}</h1>
    <p className="text-sm text-muted">{t("Compare recorded decisions, not investor ability.")}</p>
    <div ref={chartRef}><SameStockComparisonPanel view={view} focusedDecisionId={focusedDecisionId} /></div>
    <DecisionAnalysisWorkspace scope={{ subject_id: generated.same_stock_compare_demo.a.episode.subject_id, account_id: generated.same_stock_compare_demo.a.episode.account_id, episode_id: view.a.episodeId, data_mode: "synthetic_pair", pair_side: "A", compare_pair: true }} onDecision={(id) => { setFocusedDecisionId(id); chartRef.current?.scrollIntoView({block: "center", behavior: "smooth"}); }} />
  </div>;
}
