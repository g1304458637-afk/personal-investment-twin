import { ArrowRight, CircleDashed } from "lucide-react";
import { Link } from "react-router-dom";

import { StatusBadge } from "@/components/common/StatusBadge";
import { EvidenceExplainButton } from "@/components/evidence/EvidenceInspector";
import type { ReviewObservationView } from "@/data/review";
import { useLocale, type TranslationValues } from "@/locales/LocaleProvider";

function localizedValues(
  t: (source: string, values?: TranslationValues) => string,
  values?: Record<string, string | number>,
): TranslationValues | undefined {
  if (!values) return undefined;
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, typeof value === "string" ? t(value) : value]),
  );
}

export function EvidenceObservationRow({
  observation,
  inspectorContext,
}: {
  observation: ReviewObservationView;
  inspectorContext: string;
}) {
  const { t } = useLocale();
  return (
    <article className="review-observation-row">
      <div className="review-observation-row__identity">
        <span>{t(observation.eyebrowKey)}</span>
        <h3>{t(observation.titleKey)}</h3>
      </div>
      <div className="review-observation-row__result">
        <strong>{t(observation.primary, localizedValues(t, observation.primaryValues))}</strong>
        <p>{t(observation.description, localizedValues(t, observation.descriptionValues))}</p>
      </div>
      <div className="review-observation-row__meta">
        {observation.status === "unavailable" ? (
          <span className="review-observation-row__unavailable"><CircleDashed aria-hidden="true" />{t("Unavailable")}</span>
        ) : (
          <StatusBadge status={observation.status} compact />
        )}
        <span>{observation.observationCount === null ? t("N not available") : `N=${observation.observationCount}`}</span>
      </div>
      <div className="review-observation-row__actions">
        <EvidenceExplainButton
          view={observation.explainability}
          label="View evidence"
          context={{ label: t(inspectorContext), title: t(observation.titleKey), detail: t("Synthetic offline fixture") }}
        />
        {observation.episodeId ? (
          <Link to={`/investments/episodes/${observation.episodeId}`}>
            {t("View related investment")} <ArrowRight aria-hidden="true" />
          </Link>
        ) : null}
      </div>
    </article>
  );
}
