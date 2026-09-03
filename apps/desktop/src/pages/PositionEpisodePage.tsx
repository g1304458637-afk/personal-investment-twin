import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CircleDot,
  Database,
  Hash,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PositionEpisodeTimeline } from "@/components/charts/PositionEpisodeTimeline";
import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge, StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  getPositionEpisodeById,
  positionEpisodeDemo,
} from "@/data/backendEvidence";
import type {
  PositionDecisionType,
  PositionDecisionView,
  PositionEpisodeEntryView,
  PositionEvidenceReferenceView,
  PositionStateView,
} from "@/data/positionEpisode";
import { useLocale } from "@/locales/LocaleProvider";

function DecisionName({ type }: { type: PositionDecisionType }) {
  const { t } = useLocale();
  const labels: Record<PositionDecisionType, string> = {
    open_position: t("Open position"),
    add_position: t("Add position"),
    reduce_position: t("Reduce position"),
    close_position: t("Close position / final sale"),
  };
  return <>{labels[type]}</>;
}

function StateFacts({ state, label }: { state: PositionStateView; label: string }) {
  const { t, formatCurrency, formatNumber } = useLocale();
  return (
    <div className="rounded-lg border border-border/70 bg-white/[0.025] p-4">
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">{label}</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
        <div>
          <dt className="text-muted">{t("Position quantity")}</dt>
          <dd className="mt-1 font-mono text-sm text-foreground tabular-nums">
            {formatNumber(state.quantity, 0)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("Average cost")}</dt>
          <dd className="mt-1 font-mono text-sm text-foreground tabular-nums">
            {state.averageCost === null ? "—" : formatCurrency(state.averageCost)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("Valuation price")}</dt>
          <dd className="mt-1 font-mono text-sm text-foreground tabular-nums">
            {state.valuationPrice === null ? "—" : formatCurrency(state.valuationPrice)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t("Market value")}</dt>
          <dd className="mt-1 font-mono text-sm text-foreground tabular-nums">
            {state.marketValue === null ? "—" : formatCurrency(state.marketValue)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function EvidenceLinks({
  references,
}: {
  references: PositionEvidenceReferenceView[];
}) {
  const { t } = useLocale();
  if (references.length === 0) {
    return (
      <StateNotice
        state="insufficient"
        compact
        title={t("No decision-level Evidence is linked")}
        detail={t("The Episode remains valid. Evidence is shown only when an existing deterministic record is explicitly linked to this execution.")}
      />
    );
  }
  return (
    <div className="space-y-2">
      {references.map((reference) => (
        <Link
          key={reference.evidenceId}
          to={`/evidence?selected=${reference.evidenceId}`}
          className="flex items-start justify-between gap-3 rounded-lg border border-border/70 bg-white/[0.025] p-3 transition-colors hover:bg-white/[0.05]"
        >
          <span className="min-w-0">
            <strong className="block truncate text-xs font-medium text-foreground">
              {reference.metricId}
            </strong>
            <span className="mt-1 block break-all font-mono text-[10px] text-muted">
              {reference.evidenceId}
            </span>
            {reference.reason ? (
              <span className="mt-1 block text-xs leading-5 text-muted">{t(reference.reason)}</span>
            ) : null}
          </span>
          <StatusBadge status={reference.status} compact />
        </Link>
      ))}
    </div>
  );
}

function DecisionDrawer({
  entry,
  decision,
  open,
  onOpenChange,
}: {
  entry: PositionEpisodeEntryView;
  decision: PositionDecisionView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  if (!decision) return null;
  const timestamp = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(decision.occurredAt));
  const referenceById = new Map(
    entry.evidenceReferences.map((reference) => [reference.evidenceId, reference]),
  );
  const references = decision.evidenceRefs.flatMap((id) => {
    const reference = referenceById.get(id);
    return reference ? [reference] : [];
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <div className="pr-10">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent">
            {t("Actual execution")}
          </p>
          <SheetTitle className="mt-2 text-xl font-semibold text-foreground">
            <DecisionName type={decision.decisionType} />
          </SheetTitle>
          <SheetDescription className="mt-2 text-sm leading-6 text-muted">
            {t("This event is classified from the actual execution and its vectorbt replay states. It is not a recommendation or signal.")}
          </SheetDescription>
        </div>

        <dl className="mt-6 grid grid-cols-2 gap-x-5 gap-y-4 border-y border-border/70 py-5 text-xs">
          <div className="col-span-2">
            <dt className="text-muted">{t("Occurred at")}</dt>
            <dd className="mt-1 text-sm text-foreground">{timestamp}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("Execution price")}</dt>
            <dd className="mt-1 font-mono text-base text-foreground tabular-nums">
              {formatCurrency(decision.executionPrice)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("Execution quantity")}</dt>
            <dd className="mt-1 font-mono text-base text-foreground tabular-nums">
              {formatNumber(decision.executedQuantity, 0)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("Recorded fee")}</dt>
            <dd className="mt-1 font-mono text-sm text-foreground tabular-nums">
              {formatCurrency(decision.fees)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Execution ID</dt>
            <dd className="mt-1 break-all font-mono text-[10px] text-foreground">
              {decision.executionId}
            </dd>
          </div>
        </dl>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <StateFacts state={decision.stateBefore} label={t("Before execution")} />
          <StateFacts state={decision.stateAfter} label={t("After execution")} />
        </div>
        <p className="mt-3 text-xs leading-5 text-muted">
          {t("Quantity, average cost, valuation price, and market value are copied from deterministic replay states; the UI does not recalculate them.")}
        </p>

        <div className="mt-7">
          <h3 className="text-sm font-semibold text-foreground">{t("Linked decision Evidence")}</h3>
          <div className="mt-3">
            <EvidenceLinks references={references} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function PositionEpisodePage() {
  const { episodeId } = useParams();
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  const entry = episodeId ? getPositionEpisodeById(episodeId) : null;
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const selectedDecision = useMemo(
    () =>
      entry?.decisions.find((decision) => decision.decisionId === selectedDecisionId) ??
      null,
    [entry, selectedDecisionId],
  );

  if (!entry) {
    return (
      <div className="space-y-5 pb-8">
        <Button asChild variant="quiet" size="sm">
          <Link to="/decisions"><ArrowLeft />{t("Back to decision evidence")}</Link>
        </Button>
        <StateNotice
          state="empty"
          title={t("Position Episode not found")}
          detail={t("No generated lifecycle matches this Episode ID; the UI will not substitute another Episode.")}
        />
      </div>
    );
  }

  const episode = entry.episode;
  const currentState = entry.snapshot?.positionState ?? null;
  const dateOnly = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const openedAt = dateOnly.format(new Date(episode.openedAt));
  const closedAt = episode.closedAt ? dateOnly.format(new Date(episode.closedAt)) : null;
  const asOf = entry.snapshot ? dateOnly.format(new Date(entry.snapshot.asOf)) : null;
  const valuationAt = currentState?.valuationAt
    ? dateOnly.format(new Date(currentState.valuationAt))
    : null;
  const episodeReferences = entry.evidenceReferences.filter((reference) =>
    episode.evidenceRefs.includes(reference.evidenceId),
  );

  return (
    <div className="space-y-6 pb-8">
      <Button asChild variant="quiet" size="sm" className="-ml-3">
        <Link to="/decisions"><ArrowLeft />{t("Back to decision evidence")}</Link>
      </Button>

      <PageHeader
        eyebrow={t("Position Episode · single-instrument lifecycle")}
        title={episode.instrumentId}
        description={t("The fixture does not provide an instrument name, so only its exact symbol is shown. No name is inferred.")}
        actions={
          <div className="flex items-center gap-2">
            <DemoBadge />
            <span
              className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                episode.status === "open"
                  ? "border-accent/35 bg-accent/10 text-accent"
                  : "border-border bg-white/[0.04] text-foreground"
              }`}
            >
              {t(episode.status === "open" ? "Holding" : "Closed position")}
            </span>
          </div>
        }
        showDemo={false}
      />

      <GlassPanel className="p-5 md:p-6">
        <dl className="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-muted"><CalendarDays className="size-3.5" />{t("Opened")}</dt>
            <dd className="mt-2 text-sm font-medium text-foreground">{openedAt}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-muted"><CalendarDays className="size-3.5" />{t(episode.status === "open" ? "As of" : "Closed")}</dt>
            <dd className="mt-2 text-sm font-medium text-foreground">{episode.status === "open" ? asOf : closedAt}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t(episode.durationKind === "so_far" ? "Held so far" : "Total holding time")}</dt>
            <dd className="mt-2 font-mono text-lg font-semibold text-foreground tabular-nums">
              {t("{count} days", { count: episode.durationDays })}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("Execution count")}</dt>
            <dd className="mt-2 font-mono text-lg font-semibold text-foreground tabular-nums">
              {formatNumber(episode.executionRefs.length, 0)}
            </dd>
          </div>
          {currentState ? (
            <div>
              <dt className="text-xs text-muted">{t("Current position")}</dt>
              <dd className="mt-2 font-mono text-lg font-semibold text-foreground tabular-nums">
                {formatNumber(currentState.quantity, 0)}
              </dd>
            </div>
          ) : null}
        </dl>
        {entry.snapshot && currentState ? (
          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border/70 pt-4 text-xs text-muted">
            <span className="text-accent">{t("As of {date}", { date: asOf ?? "—" })}</span>
            <span>{t("Latest valid valuation")}: {valuationAt ?? "—"}</span>
            <span>{t("Valuation price")}: {currentState.valuationPrice === null ? "—" : formatCurrency(currentState.valuationPrice)}</span>
            <span>{t("This is a current mark, not an exit or sale.")}</span>
          </div>
        ) : null}
      </GlassPanel>

      <GlassPanel className="overflow-hidden p-5 md:p-6">
        <SectionHeading
          eyebrow={t("Price + actual execution points")}
          title={t("Position decision timeline")}
          description={t("Select a real execution marker to inspect the replay state before and after it. The line uses recorded synthetic market observations.")}
        />
        <div className="mt-5">
          <PositionEpisodeTimeline entry={entry} onSelectDecision={setSelectedDecisionId} />
        </div>
        <div className="mt-5 divide-y divide-border/70 border-y border-border/70">
          {entry.decisions.map((decision) => (
            <button
              key={decision.decisionId}
              type="button"
              className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-3 text-left outline-none transition-colors hover:bg-white/[0.025] focus-visible:ring-2 focus-visible:ring-accent/50 sm:grid-cols-[160px_minmax(0,1fr)_auto]"
              onClick={() => setSelectedDecisionId(decision.decisionId)}
            >
              <span className="text-xs text-muted">
                {dateOnly.format(new Date(decision.occurredAt))}
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-medium text-foreground"><DecisionName type={decision.decisionType} /></strong>
                <span className="mt-0.5 block text-xs text-muted">
                  {t("Position quantity {before} → {after}", {
                    before: formatNumber(decision.stateBefore.quantity, 0),
                    after: formatNumber(decision.stateAfter.quantity, 0),
                  })}
                </span>
              </span>
              <span className="inline-flex items-center gap-1 text-xs font-medium text-accent">
                {formatCurrency(decision.executionPrice)}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </span>
            </button>
          ))}
        </div>
      </GlassPanel>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.72fr)]">
        <GlassPanel className="p-5 md:p-6">
          <SectionHeading
            eyebrow={t("Existing Evidence")}
            title={t("Episode-level evidence references")}
            description={t("These records describe the Episode as a whole. They are not silently attributed to any single execution.")}
          />
          <div className="mt-4">
            {episodeReferences.length ? (
              <EvidenceLinks references={episodeReferences} />
            ) : (
              <StateNotice
                state="insufficient"
                compact
                title={t("No Episode-level Evidence is linked")}
                detail={t("The position lifecycle remains valid without an inferred Evidence result.")}
              />
            )}
          </div>
        </GlassPanel>
        <GlassPanel className="p-5 md:p-6" tone="quiet">
          <div className="flex items-center gap-2 text-xs text-muted"><Database className="size-3.5 text-accent" />{t("Deterministic source")}</div>
          <p className="mt-3 font-mono text-xs text-foreground">{episode.replayMethodId}</p>
          <p className="mt-2 flex items-start gap-2 break-all font-mono text-[10px] leading-5 text-muted"><Hash className="mt-0.5 size-3 shrink-0" />{episode.episodeId}</p>
          <p className="mt-4 text-xs leading-5 text-muted">
            {t("Corporate actions and transfers are unsupported in v1 and must not be encoded as BUY or SELL decisions.")}
          </p>
        </GlassPanel>
      </div>

      <div className="flex flex-wrap gap-2">
        {positionEpisodeDemo.entries
          .filter((candidate) => candidate.episode.episodeId !== episode.episodeId)
          .map((candidate) => (
            <Button key={candidate.episode.episodeId} asChild variant="quiet" size="sm">
              <Link to={`/decisions/episodes/${candidate.episode.episodeId}`}>
                <CircleDot />
                {t("View {symbol} · {status}", {
                  symbol: candidate.episode.instrumentId,
                  status: t(candidate.episode.status === "open" ? "Holding" : "Closed position"),
                })}
              </Link>
            </Button>
          ))}
      </div>

      <DecisionDrawer
        entry={entry}
        decision={selectedDecision}
        open={selectedDecision !== null}
        onOpenChange={(open) => !open && setSelectedDecisionId(null)}
      />
    </div>
  );
}
