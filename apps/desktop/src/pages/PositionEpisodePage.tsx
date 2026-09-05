import { formatCurrencyValue } from "@/lib/format";
import { ArrowLeft, ArrowRight, CircleDot, Database, Hash } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PositionEpisodeTimeline } from "@/components/charts/PositionEpisodeTimeline";
import { PositionQuantityTimeline } from "@/components/charts/PositionQuantityTimeline";
import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { explainabilityForEvidence, getPositionEpisodeById, positionEpisodeDemo } from "@/data/backendEvidence";
import { useDataMode } from "@/data/DataModeProvider";
import { realUserApi } from "@/data/runtimeService";
import { selectPrimaryCounterfactuals, type HistoricalCounterfactualView, type OutcomeResultSign, type OutcomeResultView, type OutcomeTransition } from "@/data/decisionOutcome";
import { adaptRuntimePositionEpisodeEntry, selectPrimaryPathItems, type DecisionPhaseView, type EpisodePatternObservationView, type PathPresentationItemView, type PositionDecisionType, type PositionDecisionView, type PositionEpisodeEntryView, type PositionEvidenceReferenceView, type PositionStateView } from "@/data/positionEpisode";
import { CurrencyProvider, useLocale } from "@/locales/LocaleProvider";
import { cn } from "@/lib/utils";

function DecisionName({ type }: { type: PositionDecisionType }) {
  const { t } = useLocale();
  return <>{{ open_position: t("Open position"), add_position: t("Add position"), reduce_position: t("Reduce position"), close_position: t("Close position / final sale") }[type]}</>;
}

function contextStatusLabel(status: "complete" | "partial" | "insufficient", t: (key: string) => string) {
  return t(status === "complete" ? "Context complete" : status === "partial" ? "Context partial" : "Context insufficient");
}

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
    return { title: t("Consecutive scaling in"), detail: t("Two or more consecutive adds are grouped as one scaling-in phase. Each fill remains a separate execution.") };
  }
  if (pattern?.patternCode === "consecutive_scaling_out") {
    return { title: t("Consecutive scaling out"), detail: t("Two or more consecutive reduces are grouped as one scaling-out phase. Close stays a separate exit phase.") };
  }
  if (pattern?.patternCode === "price_following_scale_sequence") {
    return { title: t("Scaling sequence aligned with the recorded price path"), detail: t("This episode recorded an add after a rising market path, then a later reduce or exit after a falling market path.") };
  }
  if (pattern?.patternCode === "high_quantity_during_daily_price_drawdown") {
    const qty = numericFact(pattern.facts, "quantity_at_daily_price_drawdown");
    const status = textFact(pattern.facts, "quantity_at_trough_status");
    const maxQty = numericFact(pattern.facts, "episode_max_quantity");
    const detail = status === "available" && qty !== null
      ? t("At the daily price-path trough, recorded quantity was {quantity}. Episode maximum quantity was {maxQuantity}.", { quantity: formatNumber(qty, 0), maxQuantity: formatNumber(maxQty ?? 0, 0) })
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
  return <div className="rounded-lg border border-accent/20 bg-accent/[0.045] p-4"><p className="text-[11px] font-medium uppercase tracking-[0.13em] text-accent">{t(scope === "phase" ? "If this scaling phase had been omitted" : "If this execution had been omitted")}</p><p className="mt-2 text-sm font-medium leading-6 text-foreground">{t(transitionKeys[item.comparison.resultTransition!])}</p><p className="mt-1 text-xs leading-5 text-muted">{t(scope === "phase" ? "This is one whole-phase replay, not the sum of single-event alternatives." : local ? "Measured through the next decision boundary on the recorded historical path." : "All later actual executions remain unchanged in this full-Episode historical path.")}</p><dl className="mt-3 grid grid-cols-3 gap-3 text-xs"><div><dt className="text-muted">{t("Actual")}</dt><dd className={cn("mt-1 font-mono text-sm", resultTone(item.actualResult.resultSign))}>{formatCurrency(item.actualResult.pnl)}</dd></div><div><dt className="text-muted">{t(scope === "phase" ? "Without this phase" : "Without this execution")}</dt><dd className={cn("mt-1 font-mono text-sm", resultTone(item.counterfactualResult.resultSign))}>{formatCurrency(item.counterfactualResult.pnl)}</dd></div><div><dt className="text-muted">{t("Difference · alternative − actual")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatCurrency(item.comparison.pnlDifference!)}</dd></div></dl>{horizon ? <p className="mt-3 text-[11px] text-muted">{t("Evaluation horizon")}: {horizon}</p> : null}<details className="mt-3 border-t border-border/60 pt-3 text-xs text-muted"><summary className="cursor-pointer font-medium text-foreground">{t("Scenario assumptions and method")}</summary><ul className="mt-2 space-y-1.5 leading-5">{item.heldConstant.map((fact) => <li key={fact}>· {t(fact)}</li>)}</ul><p className="mt-2 break-all font-mono text-[10px]">{item.scenarioId}@{item.scenarioVersion} · {item.priceBasis} · {item.frictionBasis}</p></details></div>;
}

function ExitFollowup({ entry }: { entry: PositionEpisodeEntryView }) {
  const { locale, t, formatCurrency, formatPercent } = useLocale();
  const item = entry.outcomeStory.exitFollowup;
  if (!item) return null;
  const explanation = explainabilityForEvidence(item.evidenceId);
  if (item.evidenceStatus !== "complete" || item.postExitAssetReturn === null) return <StateNotice state="insufficient" compact title={t("Exit follow-up Evidence is incomplete")} detail={item.evidenceReason ? t(item.evidenceReason) : t("The registered observation window is incomplete.")} />;
  return <div className="rounded-lg border border-border/70 bg-white/[0.025] p-4"><p className="text-[11px] font-medium uppercase tracking-[0.13em] text-accent">{t("Post-exit fixed-window market result")}</p><p className="mt-2 text-sm leading-6 text-foreground">{t("Over the registered {count}-session window after the exit, the asset market price returned {returnValue}.", { count: item.policySessions ?? "—", returnValue: formatPercent(item.postExitAssetReturn, 1) })}</p><dl className="mt-3 grid grid-cols-2 gap-3 text-xs"><div><dt className="text-muted">{t("Actual execution price at exit")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.actualExitPrice === null ? "—" : formatCurrency(item.actualExitPrice)}</dd></div><div><dt className="text-muted">{t("Exit-session market start price")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.exitSessionMarketPrice === null ? "—" : formatCurrency(item.exitSessionMarketPrice)}</dd></div><div><dt className="text-muted">{t("Fixed-window market end price")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{item.counterfactualExitPrice === null ? "—" : formatCurrency(item.counterfactualExitPrice)}</dd></div><div><dt className="text-muted">{t("Window end")}</dt><dd className="mt-1 text-sm text-foreground">{item.counterfactualExitTime ? new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(new Date(item.counterfactualExitTime)) : "—"}</dd></div></dl><p className="mt-3 text-xs leading-5 text-muted">{t("The fixed-window return starts from the market price on the exit session, not the actual execution price.")}</p><EvidenceExplainButton view={explanation} context={{ label: t("Position Episode") }} label="View evidence" className="mt-3" /></div>;
}

function DecisionDrawer({ entry, decision, open, onOpenChange }: { entry: PositionEpisodeEntryView; decision: PositionDecisionView | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  if (!decision) return null;
  const timestamp = new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(decision.occurredAt));
  const referenceById = new Map(entry.evidenceReferences.map((reference) => [reference.evidenceId, reference]));
  const references = decision.evidenceRefs.flatMap((id) => referenceById.get(id) ?? []);
  const counterfactuals = selectPrimaryCounterfactuals(entry.outcomeStory.counterfactuals, entry.decisions.map((item) => ({ decisionId: item.decisionId, eventType: item.decisionType }))).filter((item) => item.decisionEventId === decision.decisionId);
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="w-[min(96vw,680px)] overflow-y-auto"><div className="pr-10"><p className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent">{t("Actual execution")}</p><SheetTitle className="mt-2 text-xl font-semibold text-foreground"><DecisionName type={decision.decisionType} /></SheetTitle><SheetDescription className="mt-2 text-sm leading-6 text-muted">{t("Before, action, after, and result are copied from deterministic replay and Outcome records.")}</SheetDescription></div><dl className="mt-6 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-border/70 py-5 text-xs"><div className="col-span-2"><dt className="text-muted">{t("Occurred at")}</dt><dd className="mt-1 text-sm text-foreground">{timestamp}</dd></div><div><dt className="text-muted">{t("Execution price")}</dt><dd className="mt-1 font-mono text-base text-foreground">{formatCurrency(decision.outcome.executionPrice)}</dd></div><div><dt className="text-muted">{t("Execution quantity")}</dt><dd className="mt-1 font-mono text-base text-foreground">{formatNumber(decision.outcome.executedQuantity, 0)}</dd></div><div><dt className="text-muted">{t("Recorded fee")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatCurrency(decision.outcome.executionFee)}</dd></div><div><dt className="text-muted">Execution ID</dt><dd className="mt-1 break-all font-mono text-[10px] text-foreground">{decision.executionId}</dd></div></dl><div className="mt-6 grid gap-3 sm:grid-cols-2"><StateFacts state={decision.stateBefore} label={t("Before execution")} /><StateFacts state={decision.stateAfter} label={t("After execution")} /></div>{decision.outcome.immediateResult ? <div className="mt-4 rounded-lg border border-border/70 bg-white/[0.025] p-4"><p className="text-xs text-muted"><ResultLabel result={decision.outcome.immediateResult} scope="sale" /></p><p className={cn("mt-1 font-mono text-xl font-semibold", resultTone(decision.outcome.immediateResult.resultSign))}>{formatCurrency(decision.outcome.immediateResult.pnl)}</p></div> : null}{counterfactuals.length ? <div className="mt-7"><h3 className="text-sm font-semibold text-foreground">{t("Historical alternatives")}</h3><div className="mt-3 space-y-3">{counterfactuals.map((item) => <CounterfactualBlock key={item.counterfactualId} item={item} />)}</div></div> : null}{decision.decisionType === "close_position" ? <div className="mt-7"><ExitFollowup entry={entry} /></div> : null}<div className="mt-7"><h3 className="text-sm font-semibold text-foreground">{t("Linked decision Evidence")}</h3><div className="mt-3"><EvidenceLinks references={references} /></div></div><details className="mt-7 border-t border-border/70 pt-4 text-xs text-muted"><summary className="cursor-pointer font-medium text-foreground">{t("Technical details")}</summary><p className="mt-3 break-all font-mono text-[10px] leading-5">{decision.outcome.outcomeId}<br />{decision.outcome.methodId}@{decision.outcome.methodVersion}<br />{decision.outcome.executionSource.sourceRecordId}</p></details></SheetContent></Sheet>;
}

export function PositionEpisodePage() {
  const { episodeId } = useParams();
  const { locale, t, formatNumber, formatPercent } = useLocale();
  const data = useDataMode();
  const [runtimeEntry, setRuntimeEntry] = useState<PositionEpisodeEntryView | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const entry = data.mode === "demo" ? (episodeId ? getPositionEpisodeById(episodeId) : null) : runtimeEntry?.episode.episodeId === episodeId && runtimeEntry?.episode.subjectId === data.activeAccount?.subject_id && runtimeEntry?.episode.accountId === data.activeAccount?.account_id ? runtimeEntry : null;
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [selectedPathItemId, setSelectedPathItemId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());
  const formatCurrency = (value: number) => formatCurrencyValue(value, locale, entry?.instrument.currency ?? null);
  const selectedDecision = useMemo(() => entry?.decisions.find((decision) => decision.decisionId === selectedDecisionId) ?? null, [entry, selectedDecisionId]);
  useEffect(() => { setSelectedDecisionId(null); setSelectedPathItemId(null); }, [episodeId]);
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
  if (!entry) return <div className="space-y-5 pb-8"><Button asChild variant="quiet" size="sm"><Link to="/investments"><ArrowLeft />{t("Back to My Investments")}</Link></Button><StateNotice state={data.mode === "real_user" && !runtimeError ? "loading" : "empty"} title={runtimeError ? t("Position Episode not found") : t("Loading…")} detail={runtimeError ?? t(data.mode === "demo" ? "No generated lifecycle matches this Episode ID; the UI will not substitute another Episode." : "Rebuilding from local canonical facts.")} /></div>;
  const selectDecision = (decisionId: string, moveToRow = false) => { setSelectedDecisionId(decisionId); if (moveToRow) requestAnimationFrame(() => { const row = rowRefs.current.get(decisionId); row?.scrollIntoView({ behavior: "smooth", block: "center" }); row?.focus({ preventScroll: true }); }); };
  const episode = entry.episode;
  const result = entry.outcomeStory.episodeOutcome.actualResult;
  const dateOnly = new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" });
  const openedAt = dateOnly.format(new Date(episode.openedAt));
  const closedAt = episode.closedAt ? dateOnly.format(new Date(episode.closedAt)) : null;
  const asOf = entry.snapshot ? dateOnly.format(new Date(entry.snapshot.asOf)) : null;
  const episodeReferences = entry.evidenceReferences.filter((reference) => episode.evidenceRefs.includes(reference.evidenceId));
  const pathItems = selectPrimaryPathItems(entry.pathAnalysis);
  const selectedPathItem = pathItems.find((item) => item.itemId === selectedPathItemId) ?? pathItems[0] ?? null;
  const selectedPhase = selectedPathItem?.phaseId
    ? entry.pathAnalysis.phases.find((phase) => phase.phaseId === selectedPathItem.phaseId) ?? null
    : null;
  const selectedPattern = selectedPathItem?.patternId
    ? entry.pathAnalysis.patterns.find((pattern) => pattern.patternId === selectedPathItem.patternId) ?? null
    : null;
  const highlightStart = selectedPhase?.startedAt
    ?? (selectedPattern ? textFact(selectedPattern.facts, "window_start") ?? textFact(selectedPattern.facts, "peak_observed_at") : null);
  const highlightEnd = selectedPhase?.endedAt
    ?? (selectedPattern ? textFact(selectedPattern.facts, "window_end") ?? textFact(selectedPattern.facts, "trough_observed_at") : null);
  const emphasizedDecisionIds = selectedPhase?.decisionEventIds ?? selectedPattern?.decisionEventIds ?? [];
  const phaseCounterfactual = selectedPhase
    ? entry.pathAnalysis.phaseCounterfactuals.find((item) =>
      (item.scenarioId === "omit_decision_phase_until_next_decision_v2" || item.scenarioId === "omit_decision_phase_until_next_decision_v1")
      && item.decisionEventId === selectedPhase.decisionEventIds[0]) ?? null
    : null;
  const chartGroup = `episode-path-${episode.episodeId}`;
  const preEntry = entry.pathAnalysis.marketPath.preEntryContext;
  const showPreEntryContext = entry.pathAnalysis.marketPath.preEntryContextStatus !== "insufficient";
  const preEntrySentence = !showPreEntryContext || preEntry.priceReturn === null
    ? null
    : preEntry.priceReturn > 0
      ? t("Recorded pre-entry market observations show the price rose {percent}.", { percent: formatPercent(preEntry.priceReturn, 1) })
      : preEntry.priceReturn < 0
        ? t("Recorded pre-entry market observations show the price fell {percent}.", { percent: formatPercent(preEntry.priceReturn < 0 ? -preEntry.priceReturn : preEntry.priceReturn, 1) })
        : t("Recorded pre-entry market observations show the price was unchanged.");
  const longGap = entry.pathAnalysis.patterns.find((item) => item.patternCode === "long_no_execution_interval") ?? null;
  const drawdown = entry.pathAnalysis.marketPath.dailyPricePeakDrawdown;
  const segmentKinds = new Set(entry.pathAnalysis.marketPath.marketPathSegments.map((item) => item.kind));
  return <CurrencyProvider value={entry.instrument.currency}><div className="space-y-6 pb-8">
    <Button asChild variant="quiet" size="sm" className="-ml-3"><Link to="/investments"><ArrowLeft />{t("Back to My Investments")}</Link></Button>
    <PageHeader eyebrow={t("Episode Decision Story · recorded history")} title={t(entry.instrument.displayName)} description={t("Canonical instrument ID: {instrumentId}. Every result below comes from deterministic replay, Outcome, or registered Evidence.", { instrumentId: episode.instrumentId })} actions={<div className="flex items-center gap-2">{entry.instrument.isSynthetic ? <DemoBadge /> : <span className="rounded-full border border-positive/30 bg-positive/10 px-3 py-1.5 text-xs text-positive">{t("Local deterministic data")}</span>}<span className={cn("rounded-full border px-3 py-1.5 text-xs font-medium", episode.status === "open" ? "border-accent/35 bg-accent/10 text-accent" : "border-border bg-white/[0.04] text-foreground")}>{t(episode.status === "open" ? "Holding" : "Closed position")}</span></div>} showDemo={false} />
    <GlassPanel data-episode-result className="overflow-hidden p-0"><div className="grid gap-5 p-5 md:p-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(360px,.8fr)] lg:items-end"><div><p className="text-xs text-muted"><ResultLabel result={result} scope="episode" /></p><p className={cn("mt-2 font-mono text-4xl font-semibold tracking-tight", resultTone(result.resultSign))}>{formatCurrency(result.pnl)}</p>{result.returnValue !== null ? <p className="mt-2 font-mono text-sm text-foreground">{t("Position return")}: {formatPercent(result.returnValue, 2)}</p> : null}</div><dl className="grid grid-cols-2 gap-x-5 gap-y-3 text-xs sm:grid-cols-4 lg:grid-cols-2"><div><dt className="text-muted">{t("Opened")}</dt><dd className="mt-1 text-sm text-foreground">{openedAt}</dd></div><div><dt className="text-muted">{t(episode.status === "open" ? "As of" : "Closed")}</dt><dd className="mt-1 text-sm text-foreground">{episode.status === "open" ? asOf : closedAt}</dd></div><div><dt className="text-muted">{t("Duration")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{t(episode.durationKind === "so_far" ? "{count} calendar days so far" : "{count} calendar days", { count: episode.durationDays })}</dd></div><div><dt className="text-muted">{t("Recorded fees")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{t("Entry {entry} · Exit {exit}", { entry: formatCurrency(result.recordedEntryFees), exit: formatCurrency(result.recordedExitFees) })}</dd></div></dl></div>{episode.status === "open" ? <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border/70 bg-accent/[0.035] px-5 py-3 text-xs text-muted md:px-6"><span className="text-accent">{t("Marked at {date}", { date: result.valuationAt ? dateOnly.format(new Date(result.valuationAt)) : "—" })}</span><span>{t("Valuation price")}: {result.valuationPrice === null ? "—" : formatCurrency(result.valuationPrice)}</span><span>{t("This is a current mark, not a realized exit.")}</span></div> : null}<div data-path-summary className="grid gap-x-5 gap-y-3 border-t border-border/70 px-5 py-3 text-xs text-muted sm:grid-cols-2 lg:grid-cols-4 md:px-6"><div><dt className="text-muted">{t("Position changes")}</dt><dd className="mt-1 text-sm text-foreground">{t("{count} recorded position changes", { count: entry.decisions.length })}</dd></div><div><dt className="text-muted">{t("Maximum recorded quantity")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatNumber(entry.pathAnalysis.positionPath.maxQuantity, 0)}</dd></div><div><dt className="text-muted">{t("Valid daily market observations")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{entry.pathAnalysis.marketPath.episodeMarketPath.validObservationCount}</dd></div><div><dt className="text-muted">{t("Daily price-path drawdown")}</dt><dd className="mt-1 text-sm text-foreground">{drawdown && drawdown.quantityAtTroughStatus === "available" && drawdown.quantityAtTrough !== null ? t("Major daily price drawdown occurred while quantity was {quantity}.", { quantity: formatNumber(drawdown.quantityAtTrough, 0) }) : drawdown ? t("A major daily price-path drawdown is recorded; quantity at the trough is not assigned.") : t("No daily price-path drawdown is recorded.")}</dd></div>{longGap ? <div className="sm:col-span-2"><dt className="text-muted">{t("Long interval with no additional executions")}</dt><dd className="mt-1 text-sm text-foreground">{t("No additional executions were recorded for {count} calendar days.", { count: numericFact(longGap.facts, "calendar_days") ?? 0 })}</dd></div> : null}{segmentKinds.has("drawdown") || segmentKinds.has("recovery") ? <div className="sm:col-span-2"><dt className="text-muted">{t("Recorded market path segments")}</dt><dd className="mt-1 text-sm text-foreground">{Array.from(segmentKinds).map((kind) => t(`Market segment: ${kind}`)).join(" · ")}</dd></div> : null}</div></GlassPanel>
    <GlassPanel data-price-path className="overflow-hidden p-5 md:p-6"><SectionHeading eyebrow={t("Market path + cost path + actual fills")} title={t("Decision story chart")} description={t("Pre-entry, holding, and post-exit market observations stay visually separate. Holding uses a restrained markArea.")} />{preEntrySentence ? <p className="mt-3 text-sm leading-6 text-foreground">{preEntrySentence}</p> : null}<p className="mt-2 text-xs text-muted">{showPreEntryContext ? <>{t("Pre-entry context")}: {contextStatusLabel(entry.pathAnalysis.marketPath.preEntryContextStatus, t)} · </> : null}{t("Holding context")}: {contextStatusLabel(entry.pathAnalysis.marketPath.episodeContextStatus, t)}{episode.status === "closed" && entry.pathAnalysis.marketPath.postExitContextStatus !== "insufficient" ? <> · {t("Post-exit market path")}: {contextStatusLabel(entry.pathAnalysis.marketPath.postExitContextStatus, t)}</> : null}</p><div className="mt-5"><PositionEpisodeTimeline entry={entry} selectedDecisionId={selectedDecisionId} emphasizedDecisionIds={emphasizedDecisionIds} highlightStart={highlightStart} highlightEnd={highlightEnd} chartGroup={chartGroup} onSelectDecision={(id) => selectDecision(id, true)} /></div></GlassPanel>
    <GlassPanel data-quantity-path className="overflow-hidden p-5 md:p-6"><SectionHeading eyebrow={t("Authoritative position state")} title={t("Position evolution")} description={t("The step line uses replay state points only; it is not smoothed or forward-filled.")} /><div className="mt-3"><PositionQuantityTimeline entry={entry} selectedDecisionId={selectedDecisionId} emphasizedDecisionIds={emphasizedDecisionIds} highlightStart={highlightStart} highlightEnd={highlightEnd} chartGroup={chartGroup} onSelectDecision={(id) => selectDecision(id, true)} /></div></GlassPanel>
    <GlassPanel data-path-section className="overflow-hidden p-5 md:p-6"><SectionHeading eyebrow={t("Recorded path")} title={t("This episode path")} description={t("These 3–6 items are selected by the backend. The UI does not regroup phases or calculate market moves.")} /><div className="mt-5 grid gap-2">{pathItems.map((item) => { const copy = pathItemCopy(item, entry.pathAnalysis.phases, entry.pathAnalysis.patterns, t, formatPercent, formatNumber); const active = selectedPathItem?.itemId === item.itemId; return <button key={item.itemId} data-path-item-id={item.itemId} data-phase-id={item.phaseId ?? undefined} type="button" className={cn("w-full rounded-lg border px-4 py-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/50", active ? "border-accent/40 bg-accent/[0.07]" : "border-border/70 hover:bg-white/[0.025]")} onClick={() => setSelectedPathItemId(item.itemId)}><strong className="block text-sm font-medium text-foreground">{copy.title}</strong><span className="mt-1 block text-xs leading-5 text-muted">{copy.detail}</span></button>; })}</div></GlassPanel>
    {selectedPhase ? <GlassPanel data-selected-phase className="overflow-hidden p-5 md:p-6"><SectionHeading eyebrow={t("Selected phase")} title={{ entry: t("Entry phase"), scaling_in: t("Scaling in"), scaling_out: t("Scaling out"), exit: t("Exit phase") }[selectedPhase.phaseType]} description={t("Phase grouping is analytical. Every listed fill remains a separate Canonical Execution.")} /><dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 text-xs sm:grid-cols-4"><div><dt className="text-muted">{t("Started")}</dt><dd className="mt-1 text-sm text-foreground">{dateOnly.format(new Date(selectedPhase.startedAt))}</dd></div><div><dt className="text-muted">{t("Ended")}</dt><dd className="mt-1 text-sm text-foreground">{dateOnly.format(new Date(selectedPhase.endedAt))}</dd></div><div><dt className="text-muted">{t("Position quantity")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{formatNumber(selectedPhase.quantityBefore, 0)} → {formatNumber(selectedPhase.quantityAfter, 0)}</dd></div><div><dt className="text-muted">{t("Average cost")}</dt><dd className="mt-1 font-mono text-sm text-foreground">{selectedPhase.averageCostBefore === null ? "—" : formatCurrency(selectedPhase.averageCostBefore)} → {selectedPhase.averageCostAfter === null ? "—" : formatCurrency(selectedPhase.averageCostAfter)}</dd></div></dl><div className="mt-4 divide-y divide-border/70 border-y border-border/70">{selectedPhase.decisionEventIds.map((decisionId) => { const decision = entry.decisions.find((item) => item.decisionId === decisionId); if (!decision) return null; return <button key={decisionId} type="button" className="flex w-full items-center justify-between gap-3 px-1 py-3 text-left text-sm hover:bg-white/[0.025]" onClick={() => selectDecision(decisionId, true)}><span><DecisionName type={decision.decisionType} /><span className="mt-1 block text-xs text-muted">{dateOnly.format(new Date(decision.occurredAt))}</span></span><ArrowRight className="size-3.5 text-accent" aria-hidden="true" /></button>; })}</div>{phaseCounterfactual ? <div data-phase-counterfactual className="mt-5"><CounterfactualBlock item={phaseCounterfactual} scope="phase" /></div> : selectedPhase.phaseType === "entry" ? <p className="mt-4 text-xs leading-5 text-muted">{t("Entry is not a primary phase counterfactual in v1.")}</p> : null}</GlassPanel> : null}
    <GlassPanel className="overflow-hidden p-5 md:p-6"><SectionHeading eyebrow={t("Before → action → after → result")} title={t("Decision events")} description={t("Select any row for replay facts, historical alternatives, Evidence, and technical sources.")} /><div className="mt-5 divide-y divide-border/70 border-y border-border/70">{entry.decisions.map((decision) => { const immediate = decision.outcome.immediateResult; return <button key={decision.decisionId} ref={(node) => { if (node) rowRefs.current.set(decision.decisionId, node); else rowRefs.current.delete(decision.decisionId); }} data-decision-event-id={decision.decisionId} type="button" aria-expanded={selectedDecisionId === decision.decisionId} className={cn("grid w-full gap-3 px-2 py-4 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/50 sm:grid-cols-[130px_minmax(170px,.75fr)_minmax(220px,1fr)_auto] sm:items-center", selectedDecisionId === decision.decisionId ? "bg-accent/[0.07]" : "hover:bg-white/[0.025]")} onClick={() => selectDecision(decision.decisionId)}><span className="text-xs text-muted">{dateOnly.format(new Date(decision.occurredAt))}</span><span><strong className="block text-sm font-medium text-foreground"><DecisionName type={decision.decisionType} /></strong><span className="mt-1 block text-xs text-muted">{t(decision.side === "BUY" ? "Bought {quantity} @ {price}" : "Sold {quantity} @ {price}", { quantity: formatNumber(decision.outcome.executedQuantity, 0), price: formatCurrency(decision.outcome.executionPrice) })}</span></span><span className="text-xs leading-5 text-muted"><span className="block">{t("Position quantity {before} → {after}", { before: formatNumber(decision.outcome.before.quantity, 0), after: formatNumber(decision.outcome.after.quantity, 0) })}</span>{decision.side === "BUY" ? <span className="block">{t("Average cost {before} → {after}", { before: decision.outcome.before.averageCost === null ? "—" : formatCurrency(decision.outcome.before.averageCost), after: decision.outcome.after.averageCost === null ? "—" : formatCurrency(decision.outcome.after.averageCost) })}</span> : null}</span><span className="inline-flex items-center justify-end gap-2 text-right text-xs font-medium text-accent">{immediate ? <span className={resultTone(immediate.resultSign)}><ResultLabel result={immediate} scope="sale" /> · {formatCurrency(immediate.pnl)}</span> : t("View details")}<ArrowRight className="size-3.5 shrink-0" aria-hidden="true" /></span></button>; })}</div></GlassPanel>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.72fr)]"><GlassPanel className="p-5 md:p-6"><SectionHeading eyebrow={t("Existing Evidence")} title={t("Episode-level evidence references")} description={t("Evidence stays linked to its registered scope; Outcome counterfactuals are not relabeled as EvidenceRecord.")} /><div className="mt-4">{episodeReferences.length ? <EvidenceLinks references={episodeReferences} /> : <StateNotice state="insufficient" compact title={t("No Episode-level Evidence is linked")} detail={t("The position lifecycle remains valid without an inferred Evidence result.")} />}</div></GlassPanel><GlassPanel className="p-5 md:p-6" tone="quiet"><div className="flex items-center gap-2 text-xs text-muted"><Database className="size-3.5 text-accent" />{t("Deterministic source")}</div><p className="mt-3 font-mono text-xs text-foreground">{entry.pathAnalysis.methodId}@{entry.pathAnalysis.methodVersion}</p><p className="mt-1 font-mono text-xs text-muted">{entry.outcomeStory.episodeOutcome.methodId}@{entry.outcomeStory.episodeOutcome.methodVersion}</p><p className="mt-2 flex items-start gap-2 break-all font-mono text-[10px] leading-5 text-muted"><Hash className="mt-0.5 size-3 shrink-0" />{episode.episodeId}</p><p className="mt-4 text-xs leading-5 text-muted">{t("This page describes recorded history and registered historical alternatives. It does not recommend, predict, or optimize a future action.")}</p></GlassPanel></div>
    {data.mode === "demo" ? <div className="flex flex-wrap gap-2">{positionEpisodeDemo.entries.filter((candidate) => candidate.episode.episodeId !== episode.episodeId).map((candidate) => <Button key={candidate.episode.episodeId} asChild variant="quiet" size="sm"><Link to={`/investments/episodes/${candidate.episode.episodeId}`}><CircleDot />{t("View {symbol} · {status}", { symbol: t(candidate.instrument.displayName), status: t(candidate.episode.status === "open" ? "Holding" : "Closed position") })}</Link></Button>)}</div> : null}
    <DecisionDrawer entry={entry} decision={selectedDecision} open={selectedDecision !== null} onOpenChange={(open) => !open && setSelectedDecisionId(null)} />
  </div></CurrencyProvider>;
}
