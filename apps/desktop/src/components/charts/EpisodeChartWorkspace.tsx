import type { ReactNode } from "react";

import { PositionEpisodeTimeline } from "@/components/charts/PositionEpisodeTimeline";
import { PositionQuantityTimeline } from "@/components/charts/PositionQuantityTimeline";
import { TimeSeriesFrame } from "@/components/charts/TimeSeriesFrame";
import type { DailyTimeNavigationStore } from "@/components/charts/useDailyTimeNavigation";
import type { PositionEpisodeEntryView } from "@/data/positionEpisode";
import { useLocale } from "@/locales/LocaleProvider";

import "./episode-chart-workspace.css";

/**
 * The deterministic close-only chart surface used by every non-OHLC Episode.
 * It deliberately composes the two established timelines instead of deriving
 * candles, volume, or any other market fields that the Episode does not own.
 */
export function EpisodeChartWorkspace({
  entry,
  selectedDecisionId,
  emphasizedDecisionIds,
  highlightStart,
  highlightEnd,
  chartGroup,
  timeNavigation,
  onSelectDecision,
  onReset,
  toolbar,
}: {
  entry: PositionEpisodeEntryView;
  selectedDecisionId: string | null;
  emphasizedDecisionIds?: string[];
  highlightStart?: string | null;
  highlightEnd?: string | null;
  chartGroup?: string;
  timeNavigation: DailyTimeNavigationStore;
  onSelectDecision: (decisionId: string) => void;
  onReset?: () => void;
  toolbar?: ReactNode;
}) {
  const { t, locale } = useLocale();

  return (
    <TimeSeriesFrame
      title={t("Price, quantity, and actual executions")}
      subtitle={locale.startsWith("zh") ? "市场价格与实际成交；价格和持仓共用一个时间区间。" : "Market prices and recorded executions; price and holdings share one time window."}
      navigation={timeNavigation}
      toolbar={toolbar}
      className="episode-chart-workspace"
      onReset={onReset}
    >
      <div data-guide="episode-price-cost" className="episode-chart-workspace__price">
        <PositionEpisodeTimeline
          entry={entry}
          selectedDecisionId={selectedDecisionId}
          emphasizedDecisionIds={emphasizedDecisionIds}
          highlightStart={highlightStart}
          highlightEnd={highlightEnd}
          chartGroup={chartGroup}
          timeNavigation={timeNavigation}
          onSelectDecision={onSelectDecision}
          showNavigator={false}
          className="episode-chart-workspace__price-chart"
        />
      </div>
      <div data-quantity-path data-guide="episode-quantity" className="episode-chart-workspace__quantity">
        <div className="episode-chart-workspace__quantity-heading">
          <h3>{t("Position quantity")}</h3>
        </div>
        <PositionQuantityTimeline
          entry={entry}
          selectedDecisionId={selectedDecisionId}
          emphasizedDecisionIds={emphasizedDecisionIds}
          highlightStart={highlightStart}
          highlightEnd={highlightEnd}
          chartGroup={chartGroup}
          timeNavigation={timeNavigation}
          onSelectDecision={onSelectDecision}
          showNavigator={false}
          className="episode-chart-workspace__quantity-chart"
        />
      </div>
    </TimeSeriesFrame>
  );
}
