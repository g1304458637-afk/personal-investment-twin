import source from "@/generated/showcase-demo.json";

import { adaptStandardChartDemo, type StandardChartDemoView } from "./standardChart";

/**
 * The single shipped synthetic account is a presentation transport only.  It
 * deliberately sits apart from runtime account reads, so selecting the
 * showcase can never change a real account's scope.
 */
export type ShowcaseDemoSource = {
  data_tier: "synthetic";
  showcase: {
    subject_id: string;
    account_id: string;
    display_name: { zh: string; en: string };
    names: Record<string, { zh: string; en: string }>;
    as_of: string;
    source_version: string;
  };
  charts: unknown[];
  comparison_research: unknown;
  same_stock_compare_demo: unknown;
};

export const showcaseDemo = source as unknown as ShowcaseDemoSource;

if (showcaseDemo.data_tier !== "synthetic") {
  throw new Error("The desktop showcase must remain explicitly synthetic.");
}

export const showcaseCharts: readonly StandardChartDemoView[] = showcaseDemo.charts.map(adaptStandardChartDemo);

export function showcaseChartForEpisode(episodeId: string): StandardChartDemoView | null {
  return showcaseCharts.find((chart) => chart.entry.episode.episodeId === episodeId) ?? null;
}

/** Use the names registered in the generated showcase, never a client-side translation. */
export function showcaseInstrumentName(instrumentId: string, locale: string, fallback: string): string {
  const name = showcaseDemo.showcase.names[instrumentId];
  return name ? (locale === "zh-CN" ? name.zh : name.en) : fallback;
}
