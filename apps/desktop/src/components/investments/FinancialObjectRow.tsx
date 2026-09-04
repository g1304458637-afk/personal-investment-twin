import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import type { InvestmentEpisodeRowView } from "@/data/investments";
import { useLocale } from "@/locales/LocaleProvider";

export function FinancialObjectRow({
  episode,
  compact = false,
  primary = false,
}: {
  episode: InvestmentEpisodeRowView;
  compact?: boolean;
  primary?: boolean;
}) {
  const { locale, t, formatCurrency, formatNumber } = useLocale();
  const date = (value: string) => new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
  const isOpen = episode.status === "open";

  return (
    <Link
      className="financial-object-row"
      data-compact={compact || undefined}
      to={`/investments/episodes/${episode.episodeId}`}
      data-primary-demo={primary || undefined}
    >
      <div className="financial-object-row__identity">
        <div>
          <strong>{t(episode.displayName)}</strong>
          <span className="episode-status" data-status={episode.status}>
            {t(isOpen ? "In progress" : "Closed")}
          </span>
        </div>
        <code>{episode.instrumentId}</code>
        <span>
          {date(episode.openedAt)} → {episode.closedAt ? date(episode.closedAt) : t("Present")}
        </span>
      </div>

      <dl className="financial-object-row__facts">
        {isOpen ? (
          <>
            <div>
              <dt>{t("Quantity")}</dt>
              <dd>{episode.quantity === null ? "—" : formatNumber(episode.quantity, 2)}</dd>
            </div>
            <div>
              <dt>{t("Average cost")}</dt>
              <dd>{episode.averageCost === null ? "—" : formatCurrency(episode.averageCost)}</dd>
            </div>
            <div>
              <dt>{t("Current valuation price")}</dt>
              <dd>{episode.valuationPrice === null ? "—" : formatCurrency(episode.valuationPrice)}</dd>
            </div>
          </>
        ) : (
          <>
            <div>
              <dt>{t("Lifecycle")}</dt>
              <dd>{t("Closed investment experience")}</dd>
            </div>
            <div>
              <dt>{t("Duration")}</dt>
              <dd>{t("{count} days", { count: episode.durationDays })}</dd>
            </div>
          </>
        )}
      </dl>

      <span className="financial-object-row__disclosure">
        {compact ? t("View") : t("View investment experience")}
        <ArrowRight aria-hidden="true" />
      </span>
    </Link>
  );
}
