import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { formatCurrencyValue } from "@/lib/format";
import type { InvestmentEpisodeRowView } from "@/data/investments";
import { useLocale } from "@/locales/LocaleProvider";

export function FinancialObjectRow({ episode, compact = false }: { episode: InvestmentEpisodeRowView; compact?: boolean; primary?: boolean }) {
  const { locale, t, formatPercent } = useLocale();
  const date = (value: string) => new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  const result = episode.outcome;
  return <Link className="archive-row" data-compact={compact || undefined} to={`/investments/episodes/${episode.episodeId}`}>
    <div><strong className="block text-sm font-medium">{t(episode.displayName)}</strong><span className="mt-1 block text-xs text-muted">{t(episode.status === "open" ? "Holding" : "Closed")}</span></div>
    <div className="text-xs leading-6 text-muted">{date(episode.openedAt)} → {episode.closedAt ? date(episode.closedAt) : t("Present")}</div>
    <div className="flex items-center justify-between gap-3">
      <div>{result.availability === "available" && result.pnl !== null ? <>
        <strong className={`font-mono text-lg tabular-nums ${result.pnl < 0 ? "text-negative" : result.pnl > 0 ? "text-positive" : "text-foreground"}`}>{formatCurrencyValue(result.pnl, locale, episode.currency)}</strong>
        <p className="mt-1 text-xs text-muted">{t(result.result_kind === "marked" ? "Current marked result" : "Final realized result")}{result.return_value !== null ? ` · ${t("Position return")} ${formatPercent(result.return_value, 2)}` : ""}</p>
        {result.result_at ? <p className="mt-1 text-[11px] text-muted">{t("As of {date}", {date: date(result.result_at)})}</p> : null}
      </> : <><strong className="text-sm">{t("Result unavailable")}</strong><p className="mt-1 text-xs text-muted">{t(result.reason ?? "No authoritative result is available.")}</p></>}</div>
      <ArrowRight className="size-4 shrink-0 text-muted" aria-hidden="true" />
    </div>
  </Link>;
}
