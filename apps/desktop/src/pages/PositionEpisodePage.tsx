import { formatCurrencyValue } from "@/lib/format";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { OpticalDecisionFocus, OpticalExampleBoundary } from "@/experiments/optical-review/OpticalReview";
import { isOpticalReview } from "@/experiments/optical-review/experiment";

import { EpisodeChartWorkspace } from "@/components/charts/EpisodeChartWorkspace";
import { InvestmentChartWorkspace } from "@/components/charts/InvestmentChartWorkspace";
import { adaptSingleComparisonReport, type ComparisonReportView } from "@/data/strategyComparison";
import { buildReviewCard } from "@/lib/reviewCard";
import { adaptStrategyComparison, type StrategyComparisonView } from "@/data/strategyComparison";
import { strategyComparison } from "@/data/strategyComparisonDemo";
import { showcaseChartForEpisode, showcaseInstrumentName } from "@/data/showcaseDemo";
import { uniqueDailyObservationTimes } from "@/components/charts/dailyTimeAxis";
import { useDailyTimeNavigation } from "@/components/charts/useDailyTimeNavigation";
import { factFocusDomain } from "@/components/charts/factFocusDomain";
import { StateNotice } from "@/components/common/StateNotice";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import { ChartGuide } from "@/components/guidance/ChartGuide";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { explainabilityForEvidence, getPositionEpisodeById } from "@/data/backendEvidence";
import { belongsToExample, exampleAccountLabel } from "@/data/accountContext";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi } from "@/data/runtimeService";
import {
  EPISODE_TAG_MAX_COUNT,
  EPISODE_TAG_MAX_LENGTH,
  addEpisodeTag,
  episodeExitQuality,
  episodeTagsFor,
  playbookTagFor,
  removeEpisodeTag,
  type ReviewPackExitEpisodeView,
  type ReviewPackView,
} from "@/data/reviewPack";
import { useAccountReviewPack } from "@/pages/AccountReviewPack";
import { selectPrimaryCounterfactuals, type HistoricalCounterfactualView, type OutcomeResultSign, type OutcomeResultView, type OutcomeTransition } from "@/data/decisionOutcome";
import { adaptRuntimePositionEpisodeEntry, type DecisionPhaseView, type EpisodePatternObservationView, type PathPresentationItemView, type PositionDecisionType, type PositionDecisionView, type PositionEpisodeEntryView, type PositionEvidenceReferenceView, type PositionStateView } from "@/data/positionEpisode";
import { CurrencyProvider, useLocale } from "@/locales/LocaleProvider";
import { cn } from "@/lib/utils";

import "./episode-workspace.css";
import "./episode-review-sample.css";
import "./review-pack.css";
import { episodeSections, episodeSection, episodeSampleCopy, isEpisodeSample, isVisibleReviewPattern, type EpisodeSection } from "@/workspace/episodeSample";
import { isClassicWorkspace } from "@/workspace/workspaceMode";

function DecisionName({ type }: { type: PositionDecisionType }) {
  const { t } = useLocale();
  return <>{{ open_position: t("Open position"), add_position: t("Add position"), reduce_position: t("Reduce position"), close_position: t("Close position / final sale") }[type]}</>;
}

/** Built-in strategies the rule replay can load; mirrors the demo artifacts. */
const RULE_REPLAY_STRATEGY_IDS: readonly string[] = [
  "toujing_t1_breakout_trend",
  "toujing_dual_ma",
  "toujing_rsi_mean_reversion",
  "toujing_turtle_s2_long",
];

function numericFact(facts: Record<string, unknown>, key: string): number | null {
  const value = facts[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textFact(facts: Record<string, unknown>, key: string): string | null {
  const value = facts[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function pathItemCopy(
  item: PathPresentationItemView,
  phases: DecisionPhaseView[],
  patterns: EpisodePatternObservationView[],
  t: (key: string, values?: Record<string, string | number>) => string,
  formatPercent: (value: number, digits?: number) => string,
  formatNumber: (value: number, digits?: number) => string,
): { title: string; detail: string } {
  const optionalNumber = (value: number | null) => value === null ? "—" : formatNumber(value, 0);
  const phase = item.phaseId ? phases.find((candidate) => candidate.phaseId === item.phaseId) : undefined;
  const pattern = item.patternId ? patterns.find((candidate) => candidate.patternId === item.patternId) : undefined;
  if (pattern?.patternCode === "add_after_positive_market_move") {
    const ret = numericFact(pattern.facts, "price_return");
    return {
      title: t("Add after a recorded positive market move"),
      detail: ret === null
        ? t("An add occurred after a recorded positive market path between the previous decision and this one.")
        : t("After the previous decision, the recorded market path rose {percent}, then an add occurred.", { percent: formatPercent(ret, 1) }),
    };
  }
  if (pattern?.patternCode === "reduce_after_negative_market_move") {
    const ret = numericFact(pattern.facts, "price_return");
    return {
      title: t("Reduce after a recorded negative market move"),
      detail: ret === null
        ? t("A reduce occurred after a recorded negative market path between the previous decision and this one.")
        : t("After the previous decision, the recorded market path fell {percent}, then a reduce occurred.", { percent: formatPercent(ret < 0 ? -ret : ret, 1) }),
    };
  }
  if (pattern?.patternCode === "exit_after_negative_market_move") {
    const ret = numericFact(pattern.facts, "price_return");
    return {
      title: t("Exit after a recorded negative market move"),
      detail: ret === null
        ? t("The exit occurred after a recorded negative market path between the previous decision and this one.")
        : t("After the previous decision, the recorded market path fell {percent}, then the position was closed.", { percent: formatPercent(ret < 0 ? -ret : ret, 1) }),
    };
  }
  if (pattern?.patternCode === "consecutive_scaling_in") {
    return { title: t("Consecutive scaling in"), detail: t("{count} additions changed quantity from {before} to {after}.", { count: numericFact(pattern.facts, "decision_count") ?? "—", before: optionalNumber(numericFact(pattern.facts, "quantity_before")), after: optionalNumber(numericFact(pattern.facts, "quantity_after")) }) };
  }
  if (pattern?.patternCode === "consecutive_scaling_out") {
    return { title: t("Consecutive scaling out"), detail: t("{count} reductions changed quantity from {before} to {after}.", { count: numericFact(pattern.facts, "decision_count") ?? "—", before: optionalNumber(numericFact(pattern.facts, "quantity_before")), after: optionalNumber(numericFact(pattern.facts, "quantity_after")) }) };
  }
  if (pattern?.patternCode === "price_following_scale_sequence") {
    return { title: t("Scaling sequence aligned with the recorded price path"), detail: t("This episode recorded an add after a rising market path, then a later reduce or exit after a falling market path.") };
  }
  if (pattern?.patternCode === "high_quantity_during_daily_price_drawdown") {
    const qty = numericFact(pattern.facts, "quantity_at_daily_price_drawdown");
    const status = textFact(pattern.facts, "quantity_at_trough_status");
    const maxQty = numericFact(pattern.facts, "episode_max_quantity");
    const detail = status === "available" && qty !== null
      ? t("At the daily price-path trough, recorded quantity was {quantity}. Episode maximum quantity was {maxQuantity}.", { quantity: formatNumber(qty, 0), maxQuantity: optionalNumber(maxQty) })
      : t("The daily price-path trough falls on a date where quantity cannot be assigned without guessing same-day order.");
    return { title: t("Recorded quantity during the daily price peak-to-trough path"), detail };
  }
  if (pattern?.patternCode === "long_no_execution_interval") {
    const days = numericFact(pattern.facts, "calendar_days");
    const quantity = numericFact(pattern.facts, "quantity_held");
    const recovered = pattern.facts.recovered_prior_high === true;
    const detail = days === null
      ? t("No additional executions were recorded during this interval. Position quantity stayed unchanged.")
      : quantity === null
        ? t("No additional executions were recorded for {count} calendar days.", { count: days })
        : t("No additional executions were recorded for {count} calendar days. Position quantity stayed at {quantity}.", { count: days, quantity: formatNumber(quantity, 0) });
    return {
      title: t("Long interval with no additional executions"),
      detail: recovered
        ? `${detail} ${t("The recorded market path later recovered a prior daily high.")}`
        : detail,
    };
  }
  if (pattern?.patternCode === "loss_state_addition_reused") {
    return { title: t("Existing loss-state Evidence reused"), detail: t("An existing loss-state Evidence record is linked; Path does not recalculate that Evidence.") };
  }
  if (phase) {
    return {
      title: ({ entry: t("Entry phase"), scaling_in: t("Scaling in"), scaling_out: t("Scaling out"), exit: t("Exit phase") } as const)[phase.phaseType],
      detail: t("Position quantity {before} → {after}", { before: formatNumber(phase.quantityBefore, 0), after: formatNumber(phase.quantityAfter, 0) }),
    };
  }
  return { title: t("Episode path item"), detail: item.reasonCode };
}

function resultTone(sign: OutcomeResultSign) {
  return sign === "profit" ? "text-positive" : sign === "loss" ? "text-negative" : "text-foreground";
}

function ResultLabel({ result, scope }: { result: OutcomeResultView; scope: "episode" | "sale" }) {
  const { t } = useLocale();
  if (scope === "sale") return <>{t(result.resultSign === "profit" ? "This sale realized a profit" : result.resultSign === "loss" ? "This sale realized a loss" : "This sale realized a flat result")}</>;
  if (result.resultKind === "marked") return <>{t(result.resultSign === "profit" ? "Current marked total profit" : result.resultSign === "loss" ? "Current marked total loss" : "Current marked result is flat")}</>;
  return <>{t(result.resultSign === "profit" ? "Episode realized profit" : result.resultSign === "loss" ? "Episode realized loss" : "Episode realized result is flat")}</>;
}

function StateFacts({ state, label }: { state: PositionStateView; label: string }) {
  const { t, formatCurrency, formatNumber } = useLocale();
  return <div className="rounded-lg border border-border/70 bg-white/[0.025] p-4"><p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{label}</p><dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs"><div><dt className="text-muted">{t("Position quantity")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatNumber(state.quantity, 0)}</dd></div><div><dt className="text-muted">{t("Average cost")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{state.averageCost === null ? "—" : formatCurrency(state.averageCost)}</dd></div><div><dt className="text-muted">{t("Valuation price")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{state.valuationPrice === null ? "—" : formatCurrency(state.valuationPrice)}</dd></div><div><dt className="text-muted">{t("Market value")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{state.marketValue === null ? "—" : formatCurrency(state.marketValue)}</dd></div></dl></div>;
}

function EvidenceLinks({ references }: { references: PositionEvidenceReferenceView[] }) {
  const { t } = useLocale();
  if (!references.length) return <StateNotice state="insufficient" compact title={t("No decision-level Evidence is linked")} detail={t("The Episode remains valid. Evidence is shown only when an existing deterministic record is explicitly linked to this execution.")} />;
  return <div className="space-y-2">{references.map((reference) => {
    const explanation = explainabilityForEvidence(reference.evidenceId);
    return <div key={reference.evidenceId} className="flex items-start justify-between gap-3 rounded-lg border border-border/70 bg-white/[0.025] p-3"><span className="min-w-0"><strong className="block truncate text-xs font-medium text-foreground">{reference.metricId}</strong><span className="mt-1 block break-all font-mono text-[10px] text-muted">{reference.evidenceId}</span></span><span className="flex shrink-0 items-center gap-2"><StatusBadge status={reference.status} compact />{explanation ? <EvidenceExplainButton view={explanation} context={{ label: t("Position Episode") }} label="View evidence" className="h-7 px-2 text-[11px]" /> : <Button asChild variant="quiet" size="sm" className="h-7 px-2 text-[11px]"><Link to={`/advanced/evidence?selected=${reference.evidenceId}`}>{t("View evidence")}</Link></Button>}</span></div>;
  })}</div>;
}

const transitionKeys: Record<OutcomeTransition, string> = {
  matched: "The historical alternative matched the actual result.", loss_reduced: "The historical alternative had a smaller loss.", loss_increased: "The historical alternative had a larger loss.", loss_to_flat: "The historical alternative changed the result from a loss to flat.", loss_to_profit: "The historical alternative changed the result from a loss to a profit.", profit_increased: "The historical alternative had a larger profit.", profit_reduced: "The historical alternative had a smaller profit.", profit_to_flat: "The historical alternative changed the result from a profit to flat.", profit_to_loss: "The historical alternative changed the result from a profit to a loss.", flat_to_profit: "The historical alternative changed the result from flat to a profit.", flat_to_loss: "The historical alternative changed the result from flat to a loss.",
};

function CounterfactualBlock({ item, scope = "event" }: { item: HistoricalCounterfactualView; scope?: "event" | "phase" }) {
  const { locale, t, formatCurrency } = useLocale();
  const horizon = item.evaluationEnd ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(item.evaluationEnd)) : null;
  if (item.feasibilityStatus === "infeasible_downstream_execution") return <div className="rounded-lg border border-warning/25 bg-warning/[0.055] p-4"><p className="text-sm font-medium text-foreground">{t("A full historical alternative cannot be calculated")}</p><p className="mt-2 text-xs leading-5 text-muted">{t(scope === "phase" ? "After removing this phase, a later actual sale would exceed the available position. The engine does not resize or delete that order." : "After removing this execution, a later actual sale would exceed the available position. The engine does not resize or delete that order.")}</p>{item.firstConflictingExecutionId ? <p className="mt-2 break-all font-mono text-[10px] text-muted">{t("First conflicting execution")}: {item.firstConflictingExecutionId}</p> : null}</div>;
  if (item.feasibilityStatus !== "complete") return <StateNotice state="insufficient" compact title={t("No complete historical alternative is available")} detail={item.infeasibleReason ? t(item.infeasibleReason) : t("The registered scenario could not form a complete result.")} />;
  if (item.relationType === "registered_baseline_comparison") return null;
  if (item.comparison.status === "unavailable_result_basis_mismatch") return <StateNotice state="insufficient" compact title={t("Results use different accounting bases")} detail={t("The backend preserved both results but did not compare them.")} />;
  if (!item.actualResult || !item.counterfactualResult || item.comparison.status !== "complete") return null;
  const local = ["omit_event_until_next_decision_v1", "omit_decision_phase_until_next_decision_v1", "omit_event_until_next_decision_v2", "omit_decision_phase_until_next_decision_v2"].includes(item.scenarioId);
  return <div className="rounded-lg border border-accent/20 bg-accent/[0.045] p-4"><p className="text-[11px] font-medium uppercase tracking-[0.13em] text-accent">{t(scope === "phase" ? "If this scaling phase had been omitted" : "If this execution had been omitted")}</p><p className="mt-2 text-sm font-medium leading-6 text-foreground">{t(transitionKeys[item.comparison.resultTransition!])}</p><p className="mt-1 text-xs leading-5 text-muted">{t(scope === "phase" ? "This is one whole-phase replay, not the sum of single-event alternatives." : local ? "Measured through the next decision boundary on the recorded historical path." : "All later actual executions remain unchanged in this full-Episode historical path.")}</p><dl className="mt-3 grid grid-cols-3 gap-3 text-xs"><div><dt className="text-muted">{t("Actual")}</dt><dd className={cn("mt-1 font-mono text-sm", resultTone(item.actualResult.resultSign))}>{formatCurrency(item.actualResult.pnl)}</dd></div><div><dt className="text-muted">{t(scope === "phase" ? "Without this phase" : "Without this execution")}</dt><dd className={cn("mt-1 font-mono text-sm", resultTone(item.counterfactualResult.resultSign))}>{formatCurrency(item.counterfactualResult.pnl)}</dd></div><div><dt className="text-muted">{t("Difference · alternative − actual")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatCurrency(item.comparison.pnlDifference!)}</dd></div></dl><p className="mt-3 text-xs text-warning">{t("This is the result for this comparison window, not the final result of the investment.")}</p>{item.nextDecisionAt ? <p className="mt-2 text-xs text-muted">{t("Next decision")}: {item.nextDecisionAt}</p> : null}{item.valuationObservationDate ? <p className="mt-1 text-xs text-muted">{t("Valuation observation")}: {item.valuationObservationDate} · {t("A daily market mark, not an intraday execution price.")}</p> : null}{horizon ? <p className="mt-3 text-[11px] text-muted">{t("Evaluation horizon")}: {horizon}</p> : null}<details className="mt-3 border-t border-border/60 pt-3 text-xs text-muted"><summary className="cursor-pointer font-medium text-foreground">{t("Scenario assumptions and method")}</summary><ul className="mt-2 space-y-1.5 leading-5">{item.heldConstant.map((fact) => <li key={fact}>· {t(fact)}</li>)}</ul><p className="mt-2 break-all font-mono text-[10px]">{item.scenarioId}@{item.scenarioVersion} · {item.priceBasis} · {item.frictionBasis}</p></details></div>;
}

function ExitFollowup({ entry }: { entry: PositionEpisodeEntryView }) {
  const { locale, t, formatCurrency, formatPercent } = useLocale();
  const item = entry.outcomeStory.exitFollowup;
  if (!item) return null;
  const explanation = explainabilityForEvidence(item.evidenceId);
  if (item.evidenceStatus !== "complete" || item.postExitAssetReturn === null) return <StateNotice state="insufficient" compact title={t("Exit follow-up Evidence is incomplete")} detail={item.evidenceReason ? t(item.evidenceReason) : t("The registered observation window is incomplete.")} />;
  return <div className="rounded-lg border border-border/70 bg-white/[0.025] p-4"><p className="text-[11px] font-medium uppercase tracking-[0.13em] text-accent">{t("Post-exit fixed-window market result")}</p><p className="mt-2 text-sm leading-6 text-foreground">{t("Over the registered {count}-session window after the exit, the asset market price returned {returnValue}.", { count: item.policySessions ?? "—", returnValue: formatPercent(item.postExitAssetReturn, 1) })}</p><dl className="mt-3 grid grid-cols-2 gap-3 text-xs"><div><dt className="text-muted">{t("Actual execution price at exit")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.actualExitPrice === null ? "—" : formatCurrency(item.actualExitPrice)}</dd></div><div><dt className="text-muted">{t("Exit-session market start price")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.exitSessionMarketPrice === null ? "—" : formatCurrency(item.exitSessionMarketPrice)}</dd></div><div><dt className="text-muted">{t("Fixed-window market end price")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.counterfactualExitPrice === null ? "—" : formatCurrency(item.counterfactualExitPrice)}</dd></div><div><dt className="text-muted">{t("Window end")}</dt><dd className="mt-1 text-sm text-foreground">{item.counterfactualExitTime ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(item.counterfactualExitTime)) : "—"}</dd></div></dl><p className="mt-3 text-xs leading-5 text-muted">{t("The fixed-window return starts from the market price on the exit session, not the actual execution price.")}</p><EvidenceExplainButton view={explanation} context={{ label: t("Position Episode") }} label="View evidence" className="mt-3" /></div>;
}

function DecisionDrawer({ entry, decision, open, onOpenChange, optical = false }: { entry: PositionEpisodeEntryView; decision: PositionDecisionView | null; open: boolean; onOpenChange: (open: boolean) => void; optical?: boolean }) {
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  if (!decision) return null;
  const timestamp = new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(decision.occurredAt));
  const referenceById = new Map(entry.evidenceReferences.map((reference) => [reference.evidenceId, reference]));
  const references = decision.evidenceRefs.flatMap((id) => referenceById.get(id) ?? []);
  const counterfactuals = selectPrimaryCounterfactuals(entry.outcomeStory.counterfactuals, entry.decisions.map((item) => ({ decisionId: item.decisionId, eventType: item.decisionType }))).filter((item) => item.decisionEventId === decision.decisionId);
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent data-optical-decision={optical ? decision.decisionId : undefined} className={cn("w-[min(96vw,680px)] overflow-y-auto", optical && "optical-review-scope optical-decision-drawer")}>{optical ? <OpticalDecisionFocus timestamp={timestamp} /> : null}<div className="pr-10"><p className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent">{t("Actual execution")}</p><SheetTitle className="mt-2 text-xl font-semibold text-foreground"><DecisionName type={decision.decisionType} /></SheetTitle><SheetDescription className="mt-2 text-sm leading-6 text-muted">{t("Before, action, after, and result are copied from deterministic replay and Outcome records.")}</SheetDescription></div><dl className="mt-6 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-border/70 py-5 text-xs"><div className="col-span-2"><dt className="text-muted">{t("Occurred at")}</dt><dd className="mt-1 text-sm text-foreground">{timestamp}</dd></div><div><dt className="text-muted">{t("Execution price")}</dt><dd className="mt-1 font-mono text-base text-foreground">{formatCurrency(decision.outcome.executionPrice)}</dd></div><div><dt className="text-muted">{t("Execution quantity")}</dt><dd className="mt-1 font-mono text-base text-foreground">{formatNumber(decision.outcome.executedQuantity, 0)}</dd></div><div><dt className="text-muted">{t("Recorded fee")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatCurrency(decision.outcome.executionFee)}</dd></div><div><dt className="text-muted">Execution ID</dt><dd className="mt-1 break-all font-mono text-[10px] text-foreground">{decision.executionId}</dd></div></dl><div className="mt-6 grid gap-3 sm:grid-cols-2"><StateFacts state={decision.stateBefore} label={t("Before execution")} /><StateFacts state={decision.stateAfter} label={t("After execution")} /></div>{decision.outcome.immediateResult ? <div className="mt-4 rounded-lg border border-border/70 bg-white/[0.025] p-4"><p className="text-xs text-muted"><ResultLabel result={decision.outcome.immediateResult} scope="sale" /></p><p className={cn("mt-1 font-mono text-xl font-semibold", resultTone(decision.outcome.immediateResult.resultSign))}>{formatCurrency(decision.outcome.immediateResult.pnl)}</p></div> : null}{counterfactuals.length ? <div className="mt-7"><h3 className="text-sm font-semibold text-foreground">{t("Historical alternatives")}</h3><div className="mt-3 space-y-3">{counterfactuals.map((item) => <CounterfactualBlock key={item.counterfactualId} item={item} />)}</div></div> : null}{decision.decisionType === "close_position" ? <div className="mt-7"><ExitFollowup entry={entry} /></div> : null}<div className="mt-7"><h3 className="text-sm font-semibold text-foreground">{t("Linked decision Evidence")}</h3><div className="mt-3"><EvidenceLinks references={references} /></div></div><details className="mt-7 border-t border-border/70 pt-4 text-xs text-muted"><summary className="cursor-pointer font-medium text-foreground">{t("Technical details")}</summary><p className="mt-3 break-all font-mono text-[10px] leading-5">{decision.outcome.outcomeId}<br />{decision.outcome.methodId}@{decision.outcome.methodVersion}<br />{decision.outcome.executionSource.sourceRecordId}</p></details></SheetContent></Sheet>;
}

/** One exit-quality fact; a null backend value is shown honestly as insufficient. */
function ExitQualityFact({ label, value, title }: { label: string; value: string; title?: string }) {
  return <div><dt className="text-muted" title={title}>{label}</dt><dd className="mt-1 break-words font-mono text-sm text-foreground">{value}</dd></div>;
}

function ExitQualityBlock({ item }: { item: ReviewPackExitEpisodeView }) {
  const { t, formatCurrency, formatPercent } = useLocale();
  const insufficient = t("Insufficient data");
  const amount = (value: number | null) => value === null ? insufficient : formatCurrency(value);
  const amountWithPct = (value: number | null, pct: number | null) =>
    value === null ? insufficient : pct === null ? amount(value) : `${formatCurrency(value)} (${formatPercent(pct, 2)})`;
  const ratio = (value: number | null) => value === null ? insufficient : formatPercent(value, 1);
  const dayLabel = (value: string | null) => value === null ? insufficient : value;
  const days = item.facts.holdDays === null ? insufficient : t("{count} days", { count: item.facts.holdDays });
  return <>
    <dl className="review-exit-quality__facts">
      <ExitQualityFact label={t("Max favorable excursion (MFE)")} value={amountWithPct(item.mfeAmount, item.mfePct)} />
      <ExitQualityFact label={t("Max adverse excursion (MAE)")} value={amountWithPct(item.maeAmount, item.maePct)} />
      <ExitQualityFact label={t("Exit efficiency")} value={ratio(item.exitEfficiency)} title={t("Share of the maximum floating profit kept at exit")} />
      <ExitQualityFact label={t("Profit giveback ratio")} value={ratio(item.givebackRatio)} title={t("How much of the maximum floating profit faded before exit")} />
      <ExitQualityFact label={t("Peak date")} value={dayLabel(item.facts.peakDate)} />
      <ExitQualityFact label={t("Trough date")} value={dayLabel(item.facts.troughDate)} />
      <ExitQualityFact label={t("Holding days")} value={days} />
      <ExitQualityFact label={t("Realized PnL")} value={item.realizedPnl === null ? insufficient : formatCurrency(item.realizedPnl)} />
      <ExitQualityFact label={t("Hold-first-buy baseline")} value={item.holdBaselinePnl === null ? insufficient : formatCurrency(item.holdBaselinePnl)} title={t("What the first buy alone would have produced at the window's last close")} />
      <ExitQualityFact label={t("Actual vs hold baseline")} value={item.holdBaselineDelta === null ? insufficient : formatCurrency(item.holdBaselineDelta)} title={t("Positive: your path beat holding the first buy; negative: holding would have done better")} />
    </dl>
    <p className="review-exit-quality__boundary">{t("Exit efficiency is the share of the maximum floating profit kept at exit. All values are measured on recorded daily price observations; intraday extremes are not visible.")}</p>
    {item.limitations.length ? <ul className="strategy-comparison-limits">{item.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul> : null}
  </>;
}

function TagAggregate({ pack, tag }: { pack: ReviewPackView; tag: string }) {
  const { t, formatPercent } = useLocale();
  const aggregate = playbookTagFor(pack, tag);
  if (!aggregate || aggregate.confidence === "insufficient" || aggregate.winRate === null) return <>{t("Sample insufficient")}</>;
  return <>{t("Episodes")} {aggregate.episodeCount} · {t("Win rate")} {formatPercent(aggregate.winRate, 0)}</>;
}

/**
 * Episode tag editor. Client-side validation mirrors the backend limits
 * (trim, dedupe, ≤24 chars, ≤8 tags); saving goes through the desktop runtime
 * and refreshes the review pack. Demo preview is read-only.
 */
function EpisodeTagsEditor({ pack, episodeId, subjectId, accountId, readOnly, onSaved }: {
  pack: ReviewPackView; episodeId: string; subjectId: string; accountId: string; readOnly: boolean; onSaved: () => void;
}) {
  const { t } = useLocale();
  const savedTags = useMemo(() => episodeTagsFor(pack, episodeId), [pack, episodeId]);
  // Local working list while editing; reset whenever the pack or episode changes
  // so stale edits can never be saved onto another episode.
  const [working, setWorking] = useState<string[] | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => { setWorking(null); setInput(""); setError(null); setSaveError(null); setSaving(false); }, [pack, episodeId]);
  const tags = working ?? savedTags;
  const dirty = working !== null;
  const reasonText = (reason: string) => reason === "tag_too_long"
    ? t("A tag is limited to {max} characters", { max: EPISODE_TAG_MAX_LENGTH })
    : reason === "too_many_tags"
      ? t("An episode can have at most {max} tags", { max: EPISODE_TAG_MAX_COUNT })
      : t("This tag was already added");
  const commitInput = () => {
    if (input.trim().length === 0) return;
    const result = addEpisodeTag(tags, input);
    if (!result.ok) { setError(reasonText(result.reason)); return; }
    setError(null);
    setWorking(result.tags);
    setInput("");
  };
  const save = () => {
    if (saving) return;
    setSaving(true); setSaveError(null);
    realUserApi.setEpisodeTags({ subject_id: subjectId, account_id: accountId, episode_id: episodeId, tags })
      .then(() => { setSaving(false); onSaved(); })
      .catch((value) => { setSaving(false); setSaveError(value instanceof Error ? value.message : String(value)); });
  };
  return <div className="review-tag-section">
    <p className="iw-kicker">{t("Playbook tags")}</p>
    {tags.length === 0 && !readOnly ? <p className="iw-subtle">{t("No tags yet. Add up to {max}, e.g. breakout, stop-loss executed.", { max: EPISODE_TAG_MAX_COUNT })}</p> : null}
    {tags.length === 0 && readOnly ? <p className="iw-subtle">{t("This episode has no tags in the example review pack.")}</p> : null}
    {tags.length > 0 ? <div className="review-tag-chips">
      {tags.map((tag) => (
        <span key={tag} className="review-tag-chip">
          <strong>{tag}</strong>
          <span className="review-tag-chip__aggregate"><TagAggregate pack={pack} tag={tag} /></span>
          {!readOnly ? <button type="button" className="review-tag-chip__remove" aria-label={t("Remove tag")}
            onClick={() => setWorking(removeEpisodeTag(tags, tag))}>×</button> : null}
        </span>
      ))}
    </div> : null}
    {readOnly
      ? <p className="review-tag-boundary">{t("Browser preview is a read-only example; tagging needs the desktop app.")}</p>
      : <div className="review-tag-input">
        <input
          value={input}
          maxLength={EPISODE_TAG_MAX_LENGTH}
          placeholder={t("Add a tag, press Enter")}
          aria-label={t("Add a tag, press Enter")}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); commitInput(); } }}
          onBlur={commitInput}
        />
        <button type="button" className="review-tag-save" disabled={!dirty || saving} onClick={save}>
          {saving ? t("Saving…") : t("Save tags")}
        </button>
      </div>}
    {error ? <p className="review-tag-error" role="alert">{error}</p> : null}
    {saveError ? <p className="review-tag-error" role="alert">{t("Save failed")}: {saveError}</p> : null}
    {!readOnly ? <p className="review-tag-boundary">{t("Tags are descriptive labels only; they do not change any recorded fact.")}</p> : null}
  </div>;
}

/** Episode-level review-pack section: exit quality facts plus tag editing. */
function ReviewPackEpisodeSection({ mode, subjectId, accountId, episodeId }: {
  mode: "demo" | "real_user"; subjectId: string; accountId: string; episodeId: string;
}) {
  const { t } = useLocale();
  const [reloadKey, setReloadKey] = useState(0);
  const { pack, loading, error } = useAccountReviewPack(subjectId, accountId, mode, reloadKey);
  const exitItem = pack ? episodeExitQuality(pack, episodeId) : null;
  return <section data-exit-quality className="iw-inset review-exit-quality">
    <div className="iw-panel-heading">
      <div>
        <p className="iw-kicker">{t("Exit quality")}</p>
        <h2>{t("What the recorded price path looked like from this episode")}</h2>
      </div>
      <span className="iw-subtle">{t("Account review pack")}</span>
    </div>
    {loading ? <StateNotice state="loading" compact title={t("Loading review pack…")} detail={t("Rebuilding from local canonical facts.")} /> : null}
    {error ? <StateNotice state="error" compact title={t("Review pack unavailable")} detail={error} /> : null}
    {pack && !loading && !error
      ? exitItem
        ? <ExitQualityBlock item={exitItem} />
        : <StateNotice state="insufficient" compact title={t("Insufficient data")} detail={t("This episode has no exit-quality record in the account review pack yet.")} />
      : null}
    {pack && !loading && !error
      ? <EpisodeTagsEditor pack={pack} episodeId={episodeId} subjectId={subjectId} accountId={accountId}
        readOnly={mode === "demo"} onSaved={() => setReloadKey((value) => value + 1)} />
      : null}
  </section>;
}

export function PositionEpisodePage() {
  const { episodeId } = useParams();
  const [search, setSearch] = useSearchParams();
  const sample = !isClassicWorkspace() && isEpisodeSample(search);
  const sampleSection = episodeSection(search);
  const setSampleSection = (section: EpisodeSection) => { const next = new URLSearchParams(search); next.set("section", section); setSearch(next, { replace: true }); };
  const optical = isOpticalReview(search);
  const { locale, t, formatNumber, formatPercent } = useLocale();
  const c = episodeSampleCopy[locale];
  const data = useDataMode();
  const [runtimeEntry, setRuntimeEntry] = useState<PositionEpisodeEntryView | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const demoEntry = episodeId ? getPositionEpisodeById(episodeId) : null;
  const showcaseChart = data.mode === "demo" && episodeId ? showcaseChartForEpisode(episodeId) : null;
  const entry = data.mode === "demo" ? (demoEntry && belongsToExample(demoEntry, data.exampleAccount) ? demoEntry : null)
    : runtimeEntry?.episode.episodeId === episodeId && runtimeEntry?.episode.subjectId === data.activeAccount?.subject_id && runtimeEntry?.episode.accountId === data.activeAccount?.account_id ? runtimeEntry : null;
  // Same-instrument rule replay fills for demo episodes, following the user's
  // persisted strategy choice (T1 artifact is the eager default).  Only
  // built-in ids are ever written to "toujing.strategy"; an unknown or
  // stale id falls back to the default so the select, the label and the
  // comparison all describe the same strategy.
  const [compareStrategyId, setCompareStrategyIdState] = useState<string>(() => {
    // URL param wins so a shared link renders the strategy it names;
    // localStorage keeps the user's last choice for plain navigation.
    const fromQuery = search.get("compareStrategy");
    if (fromQuery && RULE_REPLAY_STRATEGY_IDS.includes(fromQuery)) return fromQuery;
    const stored = typeof localStorage === "undefined" ? null : localStorage.getItem("toujing.strategy");
    return stored && RULE_REPLAY_STRATEGY_IDS.includes(stored) ? stored : "toujing_t1_breakout_trend";
  });
  const setCompareStrategyId = (id: string) => {
    setCompareStrategyIdState(id);
    localStorage.setItem("toujing.strategy", id);
    const next = new URLSearchParams(search);
    next.set("compareStrategy", id);
    setSearch(next, { replace: true });
  };
  const [comparisonView, setComparisonView] = useState<StrategyComparisonView>(strategyComparison);
  useEffect(() => {
    if (compareStrategyId === strategyComparison.strategyId) { setComparisonView(strategyComparison); return; }
    const slug = { toujing_dual_ma: "dual-ma", toujing_rsi_mean_reversion: "rsi-mean-reversion", toujing_turtle_s2_long: "turtle" }[compareStrategyId];
    if (!slug) return;
    let cancelled = false;
    import(`@/generated/strategy-comparison-${slug}.json`).then((module) => {
      if (!cancelled) setComparisonView(adaptStrategyComparison(module.default));
    }).catch(() => { if (!cancelled) setComparisonView(strategyComparison); });
    return () => { cancelled = true; };
  }, [compareStrategyId]);
  const comparisonRuleFills = useMemo(() => {
    if (data.mode !== "demo" || !entry) return null;
    const report = comparisonView.reports.find((item) => item.episodeId === entry.episode.episodeId);
    return report ? report.ruleFills.map((fill) => ({ day: fill.day, side: fill.side, price: fill.price, trigger: fill.trigger })) : null;
  }, [data.mode, entry, comparisonView]);
  // Real accounts: on-demand same-instrument comparison via the sidecar.
  const [realCompare, setRealCompare] = useState<
    { state: "loading" } | { state: "ready"; report: ComparisonReportView } | { state: "error"; reason: string } | null>(null);
  const realCompareGeneration = useRef(0);
  const loadRealCompare = () => {
    if (!episode.accountId) return;
    const requestedEpisodeId = episode.episodeId;
    const generation = ++realCompareGeneration.current;
    setRealCompare({ state: "loading" });
    realUserApi.strategyComparison(episode.subjectId, episode.accountId, requestedEpisodeId)
      .then((result) => {
        if (generation !== realCompareGeneration.current) return;
        if (result.status === "available" && result.report) {
          const report = adaptSingleComparisonReport(result.report);
          // Drop responses that describe a different Episode than the one
          // the user asked about: cross-episode data must never render.
          if (report.episodeId !== requestedEpisodeId) {
            setRealCompare({ state: "error", reason: "comparison_episode_mismatch" });
            return;
          }
          setRealCompare({ state: "ready", report });
        } else {
          setRealCompare({ state: "error", reason: result.reason ?? "comparison_unavailable" });
        }
      })
      .catch((value) => {
        if (generation !== realCompareGeneration.current) return;
        setRealCompare({ state: "error", reason: value instanceof Error ? value.message : String(value) });
      });
  };
  const currentVerdicts = useMemo(() => {
    if (data.mode !== "demo" || !entry) return [];
    return comparisonView.reports.find((item) => item.episodeId === entry.episode.episodeId)?.decisionVerdicts ?? [];
  }, [data.mode, entry, comparisonView]);
  const compareStrategyLabel = (id: string) => ({
    "toujing_t1_breakout_trend": "T1 · 突破趋势",
    "toujing_dual_ma": "双均线交叉 5/20",
    "toujing_rsi_mean_reversion": "RSI 均值回归 14",
    "toujing_turtle_s2_long": "海龟 S2",
  }[id] ?? id);
  const requestedDecisionId = search.get("decision");
  const episodeGuideActive = search.get("guide") === "episode-process";
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [selectedPathItemId, setSelectedPathItemId] = useState<string | null>(null);
  const [showBackground, setShowBackground] = useState(false);
  const chartRef = useRef<HTMLElement>(null);
  const sampleTop = useRef<HTMLDivElement>(null);
  useEffect(() => { sampleTop.current?.scrollIntoView({block:"start", behavior:"instant"}); }, [sample]);
  const selectedDecision = entry?.decisions.find((item) => item.decisionId === selectedDecisionId) ?? null;
  useEffect(() => {
    // Route parameter changes reuse this component instance; clear every
    // per-Episode selection and any in-flight comparison for the old Episode.
    setSelectedDecisionId(null); setSelectedPathItemId(null); setShowBackground(false);
    realCompareGeneration.current += 1;
    setRealCompare(null);
  }, [episodeId, data.mode, data.exampleAccount, data.activeAccount]);
  useEffect(() => {
    if (!entry || !requestedDecisionId) return;
    if (entry.decisions.some((decision) => decision.decisionId === requestedDecisionId)) setSelectedDecisionId(requestedDecisionId);
  }, [entry, requestedDecisionId]);
  useEffect(() => {
    let cancelled = false;
    setRuntimeEntry(null); setRuntimeError(null);
    if (data.mode !== "real_user" || !data.activeAccount || !episodeId) return;
    void realUserApi.episode(data.activeAccount.subject_id, data.activeAccount.account_id, episodeId).then((result) => {
      if (cancelled) return;
      if (result.status !== "available" || !result.entry) throw new Error(result.reason ?? "episode_unavailable");
      const view = adaptRuntimePositionEpisodeEntry(result.entry);
      if (view.episode.episodeId !== episodeId || view.episode.subjectId !== data.activeAccount!.subject_id || view.episode.accountId !== data.activeAccount!.account_id) throw new Error("episode_owner_mismatch");
      setRuntimeEntry(view);
    }).catch((value) => { if (!cancelled) setRuntimeError(value instanceof Error ? value.message : String(value)); });
    return () => { cancelled = true; };
  }, [data.mode, data.activeAccount, episodeId]);
  const chartEntry = useMemo(() => entry ? {...entry, pricePoints: showBackground ? entry.pricePoints : entry.pricePoints.filter((point) => point.segment === "episode")} : null, [entry, showBackground]);
  const observationTimes = useMemo(() => chartEntry ? uniqueDailyObservationTimes(chartEntry.pricePoints.map((point) => point.observedAt)) : [], [chartEntry]);
  const boundaryTimes = useMemo(() => entry ? [
    ...entry.decisions.map((decision) => Date.parse(decision.occurredAt)),
    ...entry.pathAnalysis.positionPath.points.map((point) => Date.parse(point.asOf)),
  ] : [], [entry]);
  const timeNavigation = useDailyTimeNavigation(episodeId ?? "", observationTimes, boundaryTimes);
  const requestedFactId = search.get("fact");
  useEffect(() => {
    const fact = entry?.reviewPresentation?.facts.find((item) => item.itemId === requestedFactId);
    if (!fact) return;
    setSelectedPathItemId(fact.itemId);
    timeNavigation.apply(factFocusDomain(Date.parse(fact.startAt), Date.parse(fact.endAt), observationTimes), "reset");
  }, [entry, requestedFactId]);
  useEffect(() => {
    if (!episodeGuideActive || showcaseChart || !entry || !requestedDecisionId) return;
    const decision = entry.decisions.find((item) => item.decisionId === requestedDecisionId);
    const occurredAt = decision ? Date.parse(decision.occurredAt) : NaN;
    if (!Number.isFinite(occurredAt)) return;
    // The guide can only focus a decision already owned by this loaded Episode.
    timeNavigation.apply(factFocusDomain(occurredAt, occurredAt, observationTimes), "reset");
  }, [entry, episodeGuideActive, observationTimes, requestedDecisionId, showcaseChart, timeNavigation]);
  if (!entry || !chartEntry) return <div className="space-y-5"><Button asChild variant="quiet"><Link to="/investments"><ArrowLeft />{t("Back to My Investments")}</Link></Button><StateNotice state={data.mode === "real_user" && data.activeAccount && !runtimeError ? "loading" : "insufficient"} title={t(runtimeError || !data.activeAccount && data.mode === "real_user" || data.mode === "demo" ? "This investment is not available in the selected account" : "Loading…")} detail={runtimeError ?? t(data.mode === "real_user" && data.activeAccount ? "Rebuilding from local canonical facts." : "Select its account or return to My Investments.")} /></div>;
  const episode = entry.episode;
  const result = entry.outcomeStory.episodeOutcome.actualResult;
  const formatCurrency = (value: number) => formatCurrencyValue(value, locale, entry.instrument.currency);
  const dateOnly = new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" });
  const date = (value: string) => Number.isNaN(Date.parse(value)) ? "—" : dateOnly.format(new Date(value));
  const review = entry.reviewPresentation ? {
    ...entry.reviewPresentation,
    facts: entry.reviewPresentation.facts.filter((fact) => isVisibleReviewPattern(
      entry.pathAnalysis.patterns.find((pattern) => pattern.patternId === fact.patternId)?.patternCode,
    )),
  } : null;
  const selectedFact = review?.facts.find((fact) => fact.itemId === selectedPathItemId) ?? null;
  const guidedDecision = episodeGuideActive && requestedDecisionId
    ? entry.decisions.find((item) => item.decisionId === requestedDecisionId) ?? null
    : null;
  const selectedPhase = selectedFact?.phaseId ? entry.pathAnalysis.phases.find((phase) => phase.phaseId === selectedFact.phaseId) ?? null : null;
  const phaseCounterfactual = selectedPhase ? entry.pathAnalysis.phaseCounterfactuals.find((item) => item.scenarioId === "omit_decision_phase_until_next_decision_v2" && item.decisionEventId === selectedPhase.decisionEventIds[0]) ?? null : null;
  const story = review?.storySteps.map((step) => {
    const phase = entry.pathAnalysis.phases.find((item) => item.phaseId === step.phaseId);
    if (!phase) return null;
    return t(({entry: "Opened with {quantity} shares", scaling_in: "{count} additions brought the holding to {quantity} shares", scaling_out: "{count} reductions left {quantity} shares", exit: "Finally closed the position"})[phase.phaseType], {count: step.decisionCount, quantity: formatNumber(phase.quantityAfter, 0)});
  }).filter((part): part is string => part !== null).join(t("Story separator"));
  const chartGroup = `episode-path-${episode.episodeId}`;
  const hasBackground = entry.pricePoints.some((point) => point.segment !== "episode");
  const instrumentName = data.mode === "demo"
    ? showcaseInstrumentName(entry.instrument.instrumentId, locale, entry.instrument.displayName)
    : t(entry.instrument.displayName);
  const exitGuide = () => { const next = new URLSearchParams(search); next.delete("guide"); setSearch(next, { replace: true }); };
  return <CurrencyProvider value={entry.instrument.currency}><div data-guide-scope="episode-process" className={cn("iw-episode pb-8", optical && "episode-review--optical optical-review-scope", sample && "episode-review-sample", showcaseChart && "iw-episode--standard")}>
    <div ref={sampleTop} className="iw-episode-toolbar"><Button asChild variant="quiet" size="sm" className="-ml-3"><Link to="/investments"><ArrowLeft />{t("My Investments")}</Link></Button><div className="episode-sample-switch"><span className="iw-subtle">{data.mode === "demo" ? exampleAccountLabel(data.exampleAccount, locale) : data.activeAccount?.display_name}</span></div></div>
    <header className="iw-episode-hero iw-inset"><div><p className="iw-kicker">{sample ? c.label : t("Investment episode")}</p><h1 className="iw-episode-title">{instrumentName}</h1><p className="iw-episode-period">{date(episode.openedAt)} → {episode.closedAt ? date(episode.closedAt) : t("Present")} · {t(episode.status === "open" ? "Holding" : "Closed")}</p>{story ? <p data-review-story className="iw-story">{story}{review?.abbreviated ? t("Further executions are listed below.") : t("Story full stop")}</p> : null}</div><div data-episode-result className="iw-outcome"><div><p className="iw-kicker">{t(result.resultKind === "marked" ? "Current marked result" : "Final realized result")}</p><p className={cn("iw-outcome-value", resultTone(result.resultSign))}>{formatCurrency(result.pnl)}</p>{result.returnValue !== null ? <p className="iw-subtle mt-2">{t("Position return")}: {formatPercent(result.returnValue, 2)}</p> : null}</div><p className="iw-outcome-foot">{result.resultKind === "marked" ? <>{t("This is a current mark, not a realized exit.")}<br />{t("Marked at {date}", {date: result.valuationAt ? date(result.valuationAt) : "—"})} · {t("Valuation price")}: {result.valuationPrice === null ? "—" : formatCurrency(result.valuationPrice)}</> : t("Final date: {date}", {date: episode.closedAt ? date(episode.closedAt) : "—"})}</p></div></header>
    {sample && <nav className="episode-sample-nav" aria-label={c.label}>{episodeSections.map((section) => <button key={section} aria-pressed={sampleSection === section} onClick={() => setSampleSection(section)}>{c[section]}</button>)}</nav>}
    {sampleSection === "process" ? <div className="episode-compare-strategy">
      <button type="button" className="workshop-save" onClick={() => {
        if (!entry) return;
        const card = buildReviewCard({
          episodeId: entry.episode.episodeId,
          openedAt: entry.episode.openedAt,
          closedAt: entry.episode.closedAt,
          status: entry.episode.status,
          durationDays: entry.episode.durationDays,
          decisions: entry.decisions.map((decision) => ({
            occurredAt: decision.occurredAt, decisionType: decision.decisionType,
          })),
          pricePoints: entry.pricePoints,
          result: entry.outcomeStory.episodeOutcome.actualResult,
        });
        const blob = new Blob([card.svg], { type: card.mimetype });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = card.filename;
        anchor.click();
        // Revoking synchronously can abort the download before WebKit's
        // WebView has started it; release the URL asynchronously instead.
        window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
      }}>{t("Review card")}</button>
      <span className="iw-subtle">{t("A desensitized summary you can share: no instrument names, no absolute amounts.")}</span>
    </div> : null}
    {data.mode === "demo" && sampleSection === "process" ? <div className="episode-compare-strategy">
      <span>{t("Rule replay strategy")}</span>
      <select aria-label={t("Rule replay strategy")} value={compareStrategyId} onChange={(event) => setCompareStrategyId(event.target.value)}>
        <option value="toujing_t1_breakout_trend">T1 · 突破趋势</option>
        <option value="toujing_dual_ma">双均线交叉 5/20</option>
        <option value="toujing_rsi_mean_reversion">RSI 均值回归 14</option>
        <option value="toujing_turtle_s2_long">海龟 S2</option>
      </select>
    </div> : null}
    {data.mode === "real_user" ? <div className="episode-compare-strategy">
      <button type="button" className="workshop-save" onClick={loadRealCompare}>
        {realCompare?.state === "loading" ? t("Running on history…") : t("Check against your strategy")}
      </button>
    </div> : null}
    {realCompare?.state === "ready" ? <section className="iw-inset strategy-panel strategy-decision-verdicts">
      <div className="strategy-panel__head">
        <p className="iw-kicker">{t("Check against your strategy")}</p>
        <span className="iw-subtle">{realCompare.report.instrument} · {realCompare.report.windowStart ?? "—"} → {realCompare.report.windowEnd ?? "—"}</span>
      </div>
      {realCompare.report.decisionVerdicts.map((verdict) => (
        <div key={verdict.executionId} className="strategy-decision-verdict">
          <span>{verdict.day}</span>
          <strong className={verdict.side === "BUY" ? "is-buy" : "is-sell"}>{verdict.side === "BUY" ? t("Buy") : t("Sell")}</strong>
          <em className={verdict.verdict === "aligned" ? "is-aligned" : verdict.verdict === "different" ? "is-different" : "is-insufficient"}>
            {verdict.verdict === "aligned" ? t("Rules match") : verdict.verdict === "different" ? t("Rules differ") : t("Insufficient data")}
          </em>
          <p className="strategy-trade__reason">{verdict.reasonText}</p>
        </div>
      ))}
      <ul className="strategy-comparison-limits">{realCompare.report.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
    </section> : null}
    {realCompare?.state === "error" ? <p className="iw-subtle">{t("Comparison unavailable")}: {realCompare.reason}</p> : null}
      
    <div className="iw-episode-main" hidden={sample && sampleSection !== "process"}>
      {episodeGuideActive ? <ChartGuide guideId="episode-process" onExit={exitGuide} /> : null}
      <section ref={chartRef} data-price-path data-guide="episode-chart" className={cn(showcaseChart ? "iw-chart-panel iw-inset" : "iw-chart-panel--series")}>
        {showcaseChart ? <InvestmentChartWorkspace entry={entry} market={showcaseChart.market} ruleFills={comparisonRuleFills} focus={guidedDecision ? { id: guidedDecision.decisionId, startAt: guidedDecision.occurredAt, endAt: guidedDecision.occurredAt } : selectedFact ? { id: selectedFact.itemId, startAt: selectedFact.startAt, endAt: selectedFact.endAt } : null} onSelectDecision={setSelectedDecisionId} /> : <EpisodeChartWorkspace
          entry={chartEntry}
          selectedDecisionId={selectedDecisionId}
          emphasizedDecisionIds={selectedFact?.decisionIds}
          highlightStart={selectedFact?.startAt}
          highlightEnd={selectedFact?.endAt}
          chartGroup={chartGroup}
          timeNavigation={timeNavigation}
          onSelectDecision={setSelectedDecisionId}
          onReset={selectedFact ? () => setSelectedPathItemId(null) : undefined}
          toolbar={hasBackground ? <button type="button" className="text-xs text-muted hover:text-foreground" aria-pressed={showBackground} onClick={() => setShowBackground((value) => !value)}>{t(showBackground ? "Hide outside-holding market context" : "Show outside-holding market context")}</button> : undefined}
        />}
        {showBackground && !showcaseChart ? <p className="episode-chart-workspace__context">{t("Outside-holding market context does not extend this investment's lifecycle.")}</p> : null}
        {sample && selectedFact && <div className="episode-focus-toolbar"><span>{c.selected}</span><button onClick={() => { setSelectedPathItemId(null); timeNavigation.reset(); }}>{c.clear}</button></div>}
        {selectedFact ? <div data-selected-phase className="mt-3 border-t border-border/60 pt-3"><p className="iw-subtle">{date(selectedFact.startAt)} → {date(selectedFact.endAt)}</p><div className="mt-2 flex flex-wrap gap-2">{selectedFact.decisionIds.map((id) => { const decision = entry.decisions.find((item) => item.decisionId === id); if (!decision) return null; return <Button key={id} variant="quiet" size="sm" onClick={() => setSelectedDecisionId(id)}>{date(decision.occurredAt)} · <DecisionName type={decision.decisionType} /></Button>; })}</div>{phaseCounterfactual ? <details className="mt-3"><summary className="cursor-pointer text-xs text-accent">{t("Historical comparison under fixed assumptions")}</summary><div className="mt-3"><CounterfactualBlock item={phaseCounterfactual} scope="phase" /></div></details> : null}</div> : null}
      </section>
    {review?.facts.length ? <aside data-review-facts className="iw-facts iw-inset"><div className="iw-facts-title"><p className="iw-kicker">{t("Review queue")}</p><h2 className="mt-1 text-sm font-semibold">{t("Facts worth revisiting")}</h2><p className="iw-subtle mt-1">{sample ? c.factHint : t("Select a fact to focus its recorded interval in the chart.")}</p></div>{review.facts.map((fact) => {
        const item = entry.pathAnalysis.presentationItems.find((item) => item.itemId === fact.itemId);
        if (!item) return null;
        const copy = pathItemCopy(item, entry.pathAnalysis.phases, entry.pathAnalysis.patterns, t, formatPercent, formatNumber);
        return <button type="button" key={fact.itemId} data-review-fact={fact.itemId} className="iw-fact" aria-pressed={selectedPathItemId === fact.itemId} onClick={() => { setSelectedPathItemId(fact.itemId); timeNavigation.apply(factFocusDomain(Date.parse(fact.startAt), Date.parse(fact.endAt), observationTimes), "reset"); chartRef.current?.scrollIntoView({block: "start", behavior: "smooth"}); }}><strong>{copy.title}</strong><span>{copy.detail}</span>{sample && <span className="episode-fact-action">{c.focus}<ArrowRight size={13} /></span>}</button>;
      })}</aside> : <aside className="iw-facts iw-inset"><div className="iw-facts-title"><p className="iw-kicker">{t("Review queue")}</p><h2 className="mt-1 text-sm font-semibold">{t("No review facts are available")}</h2><p className="iw-subtle mt-2">{t("The recorded investment path remains available below.")}</p></div></aside>}</div>
    {!(sample && sampleSection !== "process") ? <ReviewPackEpisodeSection
      mode={data.mode}
      subjectId={episode.subjectId}
      accountId={episode.accountId}
      episodeId={episode.episodeId}
    /> : null}
    {sampleSection === "process" ? <section className="iw-inset strategy-panel strategy-decision-verdicts">
        <div className="strategy-panel__head">
          <p className="iw-kicker">{t("Check against your strategy")}</p>
          <span className="iw-subtle">{compareStrategyLabel(compareStrategyId)}</span>
        </div>
        {currentVerdicts.length === 0
          ? <p className="strategy-compare__note">{t("This strategy makes no entry or exit signal for these decisions on their prior sessions.")}</p>
          : currentVerdicts.map((verdict) => (
            <div key={verdict.executionId} className="strategy-decision-verdict">
              <span>{verdict.day}</span>
              <strong className={verdict.side === "BUY" ? "is-buy" : "is-sell"}>{verdict.side === "BUY" ? t("Buy") : t("Sell")}</strong>
              <em className={verdict.verdict === "aligned" ? "is-aligned" : verdict.verdict === "different" ? "is-different" : "is-insufficient"}>
                {verdict.verdict === "aligned" ? t("Rules match") : verdict.verdict === "different" ? t("Rules differ") : t("Insufficient data")}
              </em>
              <span className="strategy-rule-chips">
                {verdict.ruleChecks.map((check) => (
                  <em key={check.rule} className={check.passed ? "is-aligned" : "is-different"}>{check.rule} {check.passed ? "✓" : "✗"}</em>
                ))}
              </span>
              <p className="strategy-trade__reason">{verdict.reasonText}</p>
            </div>
          ))}
        {comparisonView.ruleTable.length ? <>
          <p className="iw-kicker" style={{ marginTop: 10 }}>{t("This strategy checks your decisions with these rules")}</p>
          <ul className="strategy-rule-group">
            {comparisonView.ruleTable.map((rule) => (
              <li key={rule.ruleId}><code>{rule.ruleId}</code><span>{rule.statement}</span></li>
            ))}
          </ul>
        </> : null}
      </section> : null}


    <div className="iw-detail-grid" hidden={sample && sampleSection !== "executions" && sampleSection !== "evidence"}><section hidden={sample && sampleSection !== "executions"} data-all-executions data-guide="episode-ledger" className="iw-executions iw-inset"><div className="iw-panel-heading"><div><p className="iw-kicker">{t("Recorded ledger")}</p><h2>{t("All executions")}</h2></div><span className="iw-subtle">{t("Select an execution for before-and-after detail")}</span></div>{entry.decisions.map((decision) => <button type="button" key={decision.decisionId} data-decision-event-id={decision.decisionId} className="iw-execution-row" onClick={() => setSelectedDecisionId(decision.decisionId)}><span className="text-xs text-muted">{date(decision.occurredAt)}</span><span className="text-sm text-foreground"><DecisionName type={decision.decisionType} /></span><span className="font-mono text-xs text-muted">{formatNumber(decision.executedQuantity, 0)} @ {formatCurrency(decision.executionPrice)}</span><ArrowRight className="size-4 text-accent" /></button>)}</section>
    <section hidden={sample && sampleSection !== "evidence"}>{sample && <p className="episode-sample-description">{c.sourceHint}</p>}<details className="iw-disclosure iw-inset"><summary>{t("More recorded context")}</summary><div className="mt-4 space-y-3">{entry.pathAnalysis.presentationItems.map((item) => { const copy = pathItemCopy(item, entry.pathAnalysis.phases, entry.pathAnalysis.patterns, t, formatPercent, formatNumber); return <p key={item.itemId} className="text-xs leading-5 text-muted"><strong className="text-foreground">{copy.title}</strong> · {copy.detail}</p>; })}</div></details><details className="iw-disclosure iw-inset"><summary>{t("Evidence, method, and source")}</summary><div className="mt-4"><EvidenceLinks references={entry.evidenceReferences.filter((reference) => episode.evidenceRefs.includes(reference.evidenceId))} /></div><details className="mt-4"><summary className="cursor-pointer text-xs text-muted">{t("Technical details")}</summary><p className="mt-3 break-all font-mono text-[10px] leading-5">{episode.episodeId}<br />{episode.instrumentId}<br />{entry.outcomeStory.episodeOutcome.methodId}@{entry.outcomeStory.episodeOutcome.methodVersion}<br />{entry.pathAnalysis.methodId}@{entry.pathAnalysis.methodVersion}<br />{result.source.sourceRecordId}</p></details><p className="mt-3 text-xs text-muted">{t("This page describes recorded history and registered historical alternatives. It does not recommend, predict, or optimize a future action.")}</p></details></section></div>
    {optical && data.mode === "demo" ? <OpticalExampleBoundary /> : null}
    <DecisionDrawer entry={entry} decision={selectedDecision} open={selectedDecision !== null} onOpenChange={(open) => !open && setSelectedDecisionId(null)} optical={optical} />
  </div></CurrencyProvider>;
}
