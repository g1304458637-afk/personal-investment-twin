import source from "@/generated/episode-lenses-demo.json";
import type { PositionEpisodeEntryView } from "./positionEpisode";

/** The generated artifact uses the same Python evaluator as the local account runtime. */
export function demoLensForEpisode(entry: PositionEpisodeEntryView): unknown {
  if (!entry.instrument.isSynthetic || entry.instrument.dataTier !== "synthetic") return null;
  const reports = (source as unknown as {reports: Record<string, unknown>[]}).reports;
  return reports.find(report => report.episode_id === entry.episode.episodeId
    && report.subject_id === entry.episode.subjectId && report.account_id === entry.episode.accountId
    && report.instrument_id === entry.episode.instrumentId) ?? null;
}
