import { Braces, CircleDashed } from "lucide-react";
import { useState, type CSSProperties } from "react";

import type {
  SelfBaselineComparisonView,
  SelfBaselineWindow,
} from "@/data/selfBaseline";
import { allWindowsUseSameObservations } from "@/data/selfBaseline";
import { useLocale } from "@/locales/LocaleProvider";

import type { SelfBaselineSummaryView } from "@/data/selfBaseline";

const windowLabels: Record<SelfBaselineWindow, string> = {
  rolling_3m: "3 months",
  rolling_12m: "12 months",
  lifetime: "All history",
};

const lookbackLabels: Record<SelfBaselineWindow, string> = {
  rolling_3m: "3 calendar months",
  rolling_12m: "12 calendar months",
  lifetime: "All eligible recorded history",
};

const metricLabels: Record<string, string> = {
  portfolio_concentration_hhi: "Portfolio concentration HHI",
  mean_daily_turnover: "Turnover intensity",
};

function metricValue(
  metricId: string,
  value: number | null,
  formatNumber: (value: number, digits?: number) => string,
  formatPercent: (value: number, digits?: number) => string,
) {
  if (value === null) return "—";
  return metricId === "mean_daily_turnover"
    ? formatPercent(value, 2)
    : formatNumber(value, 4);
}

function MetricComparison({ comparison }: { comparison: SelfBaselineComparisonView }) {
  const { t, formatNumber, formatPercent, locale } = useLocale();
  const value = (item: number | null) => metricValue(
    comparison.metricId,
    item,
    formatNumber,
    formatPercent,
  );
  const date = (item: string | null) => item === null ? "—" : new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(item));
  const observationBasis = comparison.metricId === "portfolio_concentration_hhi"
    ? "{count} valid recorded states · {start} to {end}"
    : "{count} valid recorded dates · {start} to {end}";

  if (comparison.status !== "complete") {
    return (
      <article className="self-comparison self-comparison--insufficient">
        <div className="self-comparison__identity">
          <span>{t(metricLabels[comparison.metricId] ?? comparison.metricId)}</span>
          <strong>{value(comparison.currentValue)}</strong>
          <small>{t("Current recorded value")}</small>
        </div>
        <div className="self-comparison__insufficient">
          <CircleDashed aria-hidden="true" />
          <div>
            <strong>{t("Not enough self history")}</strong>
            <p>{t(comparison.insufficientReason ?? "The registered minimum has not been met.")}</p>
            <p>{t(observationBasis, {
              count: comparison.validN,
              start: date(comparison.observationStart),
              end: date(comparison.observationEnd),
            })}</p>
          </div>
        </div>
      </article>
    );
  }

  const markerStyle = {
    "--self-position": `${comparison.selfHistoricalPercentile}%`,
  } as CSSProperties;
  const rangeLabel = comparison.comparisonBand === "above_historical_iqr"
    ? "Current is above P75 of the recorded states"
    : comparison.comparisonBand === "below_historical_iqr"
      ? "Current is below P25 of the recorded states"
      : "Current is within the recorded-state IQR";
  const accessibleLabel = t(
    "{metric}: current {current}; P25 {p25}; median {median}; P75 {p75}; percentile {percentile}; based on {count} recorded observations.",
    {
      metric: t(metricLabels[comparison.metricId] ?? comparison.metricId),
      current: value(comparison.currentValue),
      p25: value(comparison.p25),
      median: value(comparison.median),
      p75: value(comparison.p75),
      percentile: formatNumber(comparison.selfHistoricalPercentile ?? 0, 0),
      count: comparison.validN,
    },
  );

  return (
    <article className="self-comparison">
      <div className="self-comparison__identity">
        <span>{t(metricLabels[comparison.metricId] ?? comparison.metricId)}</span>
        <strong>{value(comparison.currentValue)}</strong>
        <small>{t("Current recorded value")}</small>
      </div>
      <div className="self-comparison__distribution">
        <div className="self-comparison__summary">
          <strong>{t("{window} lookback · {position}", {
            window: t(windowLabels[comparison.window]),
            position: t(rangeLabel),
          })}</strong>
          <span>{t("Delta from recorded-state median {value}", { value: value(comparison.deltaFromMedian) })}</span>
        </div>
        <div
          className="self-range"
          role="img"
          aria-label={accessibleLabel}
          style={markerStyle}
        >
          <span className="self-range__line" aria-hidden="true" />
          <span className="self-range__iqr" aria-hidden="true" />
          <span className="self-range__tick self-range__tick--p25" aria-hidden="true" />
          <span className="self-range__tick self-range__tick--median" aria-hidden="true" />
          <span className="self-range__tick self-range__tick--p75" aria-hidden="true" />
          <span className="self-range__current" aria-hidden="true"><i /></span>
        </div>
        <dl className="self-range__values">
          <div><dt>P25</dt><dd>{value(comparison.p25)}</dd></div>
          <div><dt>{t("Median")}</dt><dd>{value(comparison.median)}</dd></div>
          <div><dt>P75</dt><dd>{value(comparison.p75)}</dd></div>
          <div className="self-range__percentile"><dt>{t("My recorded position")}</dt><dd>{t("Percentile {value}", { value: formatNumber(comparison.selfHistoricalPercentile ?? 0, 0) })}</dd></div>
        </dl>
        <p className="self-comparison__basis">
          {t(observationBasis, {
            count: comparison.validN,
            start: date(comparison.observationStart),
            end: date(comparison.observationEnd),
          })}
        </p>
      </div>
    </article>
  );
}

export function SelfBaselineSection({ summary }: { summary: SelfBaselineSummaryView }) {
  const { t, locale } = useLocale();
  const [selectedWindow, setSelectedWindow] = useState<SelfBaselineWindow>(summary.defaultWindow);
  const metricOrder = ["portfolio_concentration_hhi", "mean_daily_turnover"];
  const comparisons = metricOrder.map((metricId) => {
    const metric = summary.metrics.find((item) => item.metricId === metricId);
    if (!metric) throw new Error(`Missing Self baseline metric ${metricId}.`);
    const selected = metric.windows.find((item) => item.window === selectedWindow);
    if (!selected) throw new Error(`Missing Self baseline window ${selectedWindow}.`);
    return selected;
  });
  const sameObservationsAcrossWindows = allWindowsUseSameObservations(summary);
  const detailDate = (item: string | null) => item === null ? "—" : new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(item));
  return (
    <section className="twin-section self-baseline-section" aria-labelledby="twin-self-heading">
      <header className="twin-section__heading self-baseline-section__heading">
        <div><span className="eyebrow">02</span><h2 id="twin-self-heading">{t("Me now, compared with my recorded past")}</h2></div>
        <p>{t("A descriptive position within my own recorded observations—not a score, judgment, or prediction.")}</p>
      </header>
      <div className="self-window-switch" role="group" aria-label={t("Self comparison window")}>
        {(["rolling_3m", "rolling_12m", "lifetime"] as const).map((window) => (
          <button
            key={window}
            type="button"
            aria-pressed={selectedWindow === window}
            onClick={() => setSelectedWindow(window)}
          >
            {t(windowLabels[window])}
          </button>
        ))}
      </div>
      <div className="self-comparison-list">
        {comparisons.map((item) => <MetricComparison comparison={item} key={item.metricId} />)}
      </div>
      <p className="self-baseline-section__cadence">
        {t("Each valid recorded observation is weighted equally. Missing dates are not filled, so this is not a time-weighted description of where the portfolio spent most of the period.")}
      </p>
      {sameObservationsAcrossWindows ? (
        <p className="self-baseline-section__same-observations">
          {t("The available history is short, so 3 months, 12 months, and all history currently contain the same valid observations.")}
        </p>
      ) : null}
      <details className="self-method-details">
        <summary><Braces aria-hidden="true" />{t("View comparison basis")}</summary>
        <div className="self-method-details__metrics">
          {comparisons.map((item) => (
            <section key={item.metricId}>
              <h3>{t(metricLabels[item.metricId] ?? item.metricId)}</h3>
              <dl>
                <div><dt>{t("Window")}</dt><dd>{item.window}</dd></div>
                <div><dt>{t("Lookback")}</dt><dd>{t(lookbackLabels[item.window])}</dd></div>
                <div><dt>{t("Actual observations")}</dt><dd>{item.validN}</dd></div>
                <div><dt>{t("Observed range")}</dt><dd>{detailDate(item.observationStart)} – {detailDate(item.observationEnd)}</dd></div>
                <div><dt>{t("Observation unit")}</dt><dd>{t(item.observationUnit)}</dd></div>
                <div><dt>{t("Observation cadence")}</dt><dd>{t(item.observationCadence)}</dd></div>
                <div><dt>{t("Weighting")}</dt><dd>{t("Equal per observation")}</dd></div>
                <div><dt>{t("Time-weighted")}</dt><dd>{t("False")}</dd></div>
                <div><dt>{t("Source metric")}</dt><dd>{item.sourceMethodId} · v{item.sourceMethodVersion}</dd></div>
                <div><dt>{t("Quantile")}</dt><dd>{item.provenance.quantileMethod}</dd></div>
                <div><dt>{t("Percentile")}</dt><dd>{item.provenance.percentileMethod}</dd></div>
              </dl>
              <p>{item.limitations.map((limitation) => t(limitation)).join(" ")}</p>
            </section>
          ))}
        </div>
      </details>
    </section>
  );
}
