import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { sameStockCompareDemo } from "@/data/backendEvidence";
import { adaptSameStock } from "@/data/sameStock";
import { SameStockComparisonPanel } from "@/components/review/SameStockComparisonPanel";
import { DecisionAnalysisWorkspace } from "@/components/review/DecisionAnalysisWorkspace";
import { Button } from "@/components/ui/button";
import { ChartGuide } from "@/components/guidance/ChartGuide";
import { useLocale } from "@/locales/LocaleProvider";

function comparisonScope(source: unknown, side: "A" | "B", fallback: { subjectId: string; episodeId: string }) {
  if (!source || typeof source !== "object") throw new Error("Missing showcase comparison source.");
  const rawSide = (source as Record<string, unknown>)[side.toLowerCase()];
  if (!rawSide || typeof rawSide !== "object") throw new Error("Missing showcase comparison side.");
  const episode = (rawSide as Record<string, unknown>).episode;
  if (!episode || typeof episode !== "object") throw new Error("Missing showcase comparison episode.");
  const raw = episode as Record<string, unknown>;
  const subjectId = raw.subject_id;
  const accountId = raw.account_id;
  const episodeId = raw.episode_id;
  if (typeof subjectId !== "string" || typeof accountId !== "string" || typeof episodeId !== "string"
    || subjectId !== fallback.subjectId || episodeId !== fallback.episodeId) {
    throw new Error("Showcase comparison ownership mismatch.");
  }
  return { subject_id: subjectId, account_id: accountId, episode_id: episodeId, data_mode: "synthetic_showcase" as const, pair_side: side, compare_pair: true };
}

export function SameStockComparePage() {
  const [search, setSearch] = useSearchParams();
  const sameStockGuideActive = search.get("guide") === "same-stock";
  const { t } = useLocale();
  const view = useMemo(() => adaptSameStock(sameStockCompareDemo), []);
  const [reviewSide, setReviewSide] = useState<"A" | "B">("A");
  const reviewScope = useMemo(() => comparisonScope(
    sameStockCompareDemo,
    reviewSide,
    reviewSide === "A" ? view.a : view.b,
  ), [reviewSide, view]);
  const [focusedDecisionId, setFocusedDecisionId] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (search.get("focus") === "analysis") document.querySelector("[data-decision-analysis]")?.scrollIntoView({ block: "start", behavior: "smooth" }); }, [search]);
  const exitGuide = () => { const next = new URLSearchParams(search); next.delete("guide"); setSearch(next, { replace: true }); };
  return <div data-guide-scope="same-stock" className="iw-page lg-same-stock">
    <header className="iw-page-heading">
    <Button asChild variant="quiet"><Link to="/investments">← {t("My Investments")}</Link></Button>
    <p className="text-sm text-warning">{t("Showcase comparison · Synthetic")}</p>
    <h1 className="text-2xl">{t("Same stock, different investment paths")}</h1>
    <p className="text-sm text-muted">{t("Compare recorded decisions, not investor ability.")}</p>
    </header>
    {sameStockGuideActive ? <ChartGuide guideId="same-stock" onExit={exitGuide} /> : null}
    <div ref={chartRef} data-guide="same-stock-chart"><SameStockComparisonPanel view={view} reviewSide={reviewSide} onReviewSideChange={(side) => { setReviewSide(side); setFocusedDecisionId(null); }} focusedDecisionId={focusedDecisionId} /></div>
    <DecisionAnalysisWorkspace scope={reviewScope} onDecision={(id) => { setFocusedDecisionId(id); chartRef.current?.scrollIntoView({block: "center", behavior: "smooth"}); }} />
  </div>;
}
