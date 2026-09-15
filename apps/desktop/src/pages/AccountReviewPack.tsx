import { useEffect, useState } from "react";

import { StateNotice } from "@/components/common/StateNotice";
import {
  adaptReviewPack,
  prepareMonthlyHeatmap,
  type ReviewPackTiltFlagView,
  type ReviewPackView,
} from "@/data/reviewPack";
import { realUserApi } from "@/data/runtimeService";
import { useDataMode } from "@/data/DataModeProvider";
import { useLocale } from "@/locales/LocaleProvider";
import { downloadText, toCsv } from "@/lib/download";
import { formatCurrencyValue } from "@/lib/format";
import { cn } from "@/lib/utils";

import "./review-pack.css";

export type ReviewPackMode = "demo" | "real_user";

export interface AccountReviewPackState {
  pack: ReviewPackView | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads the account-level review pack: the demo artifact in browser preview,
 * the desktop runtime otherwise. A response describing another subject/account
 * is treated as unavailable — cross-account review data must never render.
 * Callers pass subject/account explicitly so an episode page can reuse it.
 */
export function useAccountReviewPack(
  subjectId: string | null,
  accountId: string | null,
  mode: ReviewPackMode,
  reloadKey: number,
): AccountReviewPackState {
  const [state, setState] = useState<{ pack: ReviewPackView | null; loading: boolean; error: string | null }>(
    { pack: null, loading: false, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ pack: null, loading: false, error: null });
    if (!subjectId || !accountId) return;
    setState({ pack: null, loading: true, error: null });
    const load: Promise<ReviewPackView> = mode === "demo"
      ? import("@/data/reviewPackDemo").then((module) => module.reviewPackDemo)
      : realUserApi.reviewPack({ subject_id: subjectId, account_id: accountId }).then((raw) => adaptReviewPack(raw));
    load.then((pack) => {
      if (cancelled) return;
      // Real accounts must never render another account's review pack. The
      // demo artifact describes the demo universe as a whole (it is validated
      // by the same fail-closed adapter); matching stays by episode_id there
      // and absent records render as honest insufficient states.
      if (mode !== "demo" && (pack.subjectId !== subjectId || pack.accountId !== accountId)) {
        throw new Error("review_pack_account_mismatch");
      }
      setState({ pack, loading: false, error: null });
    }).catch((value) => {
      if (!cancelled) setState({ pack: null, loading: false, error: value instanceof Error ? value.message : String(value) });
    });
    return () => { cancelled = true; };
  }, [subjectId, accountId, mode, reloadKey]);
  return state;
}

function Limitations({ items }: { items: string[] }) {
  if (!items.length) return null;
  return <ul className="strategy-comparison-limits">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>;
}

function HeatmapCell({ cell, maxAbs }: { cell: { month: string; realizedPnl: number; closedCount: number; winCount: number } | null; maxAbs: number }) {
  const { t, locale, formatNumber } = useLocale();
  if (!cell) return <div className="review-heatmap-cell is-empty" aria-hidden="true" />;
  // Color intensity only: a presentation-scale (|pnl| relative to the largest
  // reported month). The rendered number itself is the backend value, verbatim.
  const alpha = cell.realizedPnl === 0 ? 0.05 : 0.12 + 0.42 * (maxAbs > 0 ? Math.abs(cell.realizedPnl) / maxAbs : 0);
  const background = cell.realizedPnl > 0 ? `rgba(105, 213, 187, ${alpha.toFixed(3)})`
    : cell.realizedPnl < 0 ? `rgba(255, 143, 156, ${alpha.toFixed(3)})` : undefined;
  return <div className="review-heatmap-cell" style={{ backgroundColor: background }}
    title={t("Closed {closed} · Wins {wins}", { closed: cell.closedCount, wins: cell.winCount })}
    aria-label={`${cell.month} · ${t("Closed {closed} · Wins {wins}", { closed: cell.closedCount, wins: cell.winCount })}`}>
    <span className="review-heatmap-month">{Number(cell.month.slice(5))}</span>
    <span className={cn("review-heatmap-value", cell.realizedPnl > 0 && "is-positive", cell.realizedPnl < 0 && "is-negative")}>
      {formatCurrencyValue(cell.realizedPnl, locale, "CNY").replace(/\s/g, "")}
    </span>
    <span className="review-heatmap-sub">{formatNumber(cell.closedCount, 0)}</span>
  </div>;
}

function TiltFlagItem({ flag }: { flag: ReviewPackTiltFlagView }) {
  const { t, formatNumber, formatPercent } = useLocale();
  const sizeChange = flag.window.avgSizeChangePct === null
    ? t("Insufficient data")
    : formatPercent(flag.window.avgSizeChangePct, 1);
  return <div className="review-tilt-item">
    <div className="review-tilt-item__head">
      <strong>{t("Trigger date")}: {flag.triggerDate}</strong>
      <span className="review-tilt-item__trigger">{flag.trigger}</span>
    </div>
    <dl className="review-tilt-facts">
      <div><dt>{t("Trades in window")}</dt><dd>{flag.window.tradeCount === null ? "—" : formatNumber(flag.window.tradeCount, 0)}</dd></div>
      <div><dt>{t("Baseline trades")}</dt><dd>{flag.window.baselineTradeCount === null ? "—" : formatNumber(flag.window.baselineTradeCount, 0)}</dd></div>
      <div><dt>{t("Avg size change")}</dt><dd>{sizeChange}</dd></div>
      <div><dt>{t("Same-instrument rebuys")}</dt><dd>{flag.window.sameInstrumentRebuyCount === null ? "—" : formatNumber(flag.window.sameInstrumentRebuyCount, 0)}</dd></div>
    </dl>
    <p className="review-tilt-note">{flag.note}</p>
    <Limitations items={flag.limitations} />
  </div>;
}

/**
 * Account-level review panel: monthly realized-PnL heatmap, behavior
 * observation after consecutive losses, and the personal playbook. Pure
 * presentation of the validated review pack; the panel mounts its data load
 * only after the user expands it.
 */
export function AccountReviewPackPanel() {
  const data = useDataMode();
  const { t, locale, formatPercent } = useLocale();
  const demo = data.mode === "demo";
  const subjectId = demo ? data.exampleAccount.subjectId : data.activeAccount?.subject_id ?? null;
  const accountId = demo ? data.exampleAccount.accountId : data.activeAccount?.account_id ?? null;
  const [open, setOpen] = useState(false);
  // The panel is presentation-only; it never writes, so the pack loads once
  // per expansion (and per account change) with a fixed reload key. Passing
  // null ids while collapsed keeps the expensive review_pack rebuild from
  // firing on page mount — the hook skips loading until ids exist.
  const { pack, loading, error } = useAccountReviewPack(
    open ? subjectId : null, open ? accountId : null, data.mode, 0);
  const years = pack ? prepareMonthlyHeatmap(pack.calendar.months) : [];
  const maxAbs = pack ? Math.max(0, ...pack.calendar.months.map((month) => Math.abs(month.realizedPnl))) : 0;
  return <details className="iw-inset review-pack-panel" open={open}>
    <summary onClick={(event) => { event.preventDefault(); setOpen((value) => !value); }}>
      <div>
        <p className="iw-kicker">{t("Review panel")}</p>
        <h2>{t("Monthly review, behavior observation, playbook")}</h2>
        <p className="iw-subtle mt-1">{t("All numbers come from the account review pack; nothing is recalculated in the app.")}</p>
      </div>
      <span className="review-pack-panel__toggle" aria-hidden="true">{open ? "−" : "+"}</span>
    </summary>
    {open ? <div className="review-pack-grid">
      {error ? <StateNotice state="error" title={t("Review pack unavailable")} detail={error} /> : null}
      {loading ? <StateNotice state="loading" title={t("Loading review pack…")} detail={t("Rebuilding from local canonical facts.")} /> : null}
      {pack ? <>
        <section className="review-pack-section" aria-label={t("Monthly realized PnL")}>
          <div className="review-pack-section__head">
            <h3>{t("Monthly realized PnL")}</h3>
            <span className="iw-subtle">
              {t("Red/green follow the sign of realized PnL; hover a month for closed and win counts")}
              {pack && pack.calendar.months.length > 0 ? <button type="button" className="ml-2 underline underline-offset-2" onClick={() => exportCalendarCsv(pack.calendar.months, t)}>{t("Export CSV")}</button> : null}
            </span>
          </div>
          {years.length === 0 ? <StateNotice state="insufficient" compact title={t("Insufficient data")} detail={t("No monthly results were reported for this account yet.")} /> : years.map((year) => (
            <div key={year.year} className="review-heatmap-year">
              <span className="review-heatmap-year__label">{year.year}</span>
              <div className="review-heatmap">{year.cells.map((cell, index) => <HeatmapCell key={index} cell={cell} maxAbs={maxAbs} />)}</div>
            </div>
          ))}
          <Limitations items={pack.calendar.limitations} />
        </section>
        <section className="review-pack-section" aria-label={t("Behavior after consecutive losses")}>
          <div className="review-pack-section__head">
            <h3>{t("Behavior after consecutive losses")}</h3>
          </div>
          <p className="strategy-comparison-note">{t("Descriptive statistics only — this does not infer psychological motivation.")}</p>
          {pack.behaviorFlags.tilt.length === 0
            ? <StateNotice state="insufficient" compact title={t("No loss-streak behavior flags were recorded")} detail={t("Not enough closed episodes to compare behavior; flags appear after more history.")} />
            : pack.behaviorFlags.tilt.map((flag, index) => <TiltFlagItem key={index} flag={flag} />)}
          <Limitations items={pack.behaviorFlags.limitations} />
        </section>
        <section className="review-pack-section" aria-label={t("My playbook")}>
          <div className="review-pack-section__head">
            <h3>{t("My playbook")}</h3>
            <span className="iw-subtle">{t("Coverage")}: {pack.coverage.executionCount} · {t("Episodes")} {pack.coverage.episodeCount}</span>
          </div>
          {pack.playbook.tags.length === 0
            ? <StateNotice state="insufficient" compact title={t("Insufficient data")} detail={t("Tag episodes on the episode page to build your playbook.")} />
            : <table className="review-playbook-table">
              <thead><tr>
                <th>{t("Tag")}</th><th>{t("Episodes")}</th><th>{t("Win rate")}</th><th>{t("Total PnL")}</th><th>{t("Confidence")}</th>
              </tr></thead>
              <tbody>
                {pack.playbook.tags.map((tag) => {
                  const insufficient = tag.confidence === "insufficient" || tag.winRate === null;
                  return <tr key={tag.tag}>
                    <td>{tag.tag}</td>
                    <td>{tag.episodeCount}</td>
                    <td>{insufficient ? <span className="review-sample-insufficient">{t("Sample insufficient")}</span> : formatPercent(tag.winRate!, 1)}</td>
                    <td className={cn(tag.totalPnl > 0 && "is-positive", tag.totalPnl < 0 && "is-negative")}>{formatCurrencyValue(tag.totalPnl, locale, "CNY")}</td>
                    <td>{insufficient ? t("Sample insufficient") : t("Sufficient")}</td>
                  </tr>;
                })}
              </tbody>
            </table>}
          <p className="strategy-comparison-note">
            {t("{count} episodes have no tags yet. Open an episode page to tag it.", { count: pack.playbook.untaggedEpisodeCount })}
          </p>
          <Limitations items={pack.playbook.limitations} />
        </section>
      </> : null}
    </div> : null}
  </details>;
}

// Calendar CSV: one row per reported month, backend values verbatim.
function exportCalendarCsv(months: ReviewPackCalendarMonthView[], t: (source: string) => string) {
  const csv = toCsv(
    ["month", "realized_pnl", "closed_count", "win_count"],
    months.map((month) => [month.month, month.realizedPnl, month.closedCount, month.winCount]));
  downloadText("toujing-review-calendar.csv", csv);
}
